#!/usr/bin/env python3
"""Talks to the Google Ads API over REST, with a hand brake on writing.

This module is the shared layer under the MCP server, the setup helper
and the self-check. It does four things and nothing else:

    Configuration   read credentials from a file or the environment
    Access token    trade the refresh token for a short-lived token
    Requests        call the REST endpoints and translate the errors
    Guardrails      refuse writes that were not explicitly permitted

WHY THE GUARDRAILS EXIST. Every other call in this module spends real
money on someone's advertising account. A wrong budget field is not a
failed test, it is an invoice. So writing is off until it is switched
on, a write names the account it is allowed to touch, a budget cannot
jump further than a configured factor, and every write that goes out is
written to a log file before the answer comes back.

No dependencies beyond the standard library, so it runs in any CI and in
any Claude Code installation without an install step.

Configuration is read in this order, first hit wins:

    1. environment variables (GOOGLE_ADS_*), for CI
    2. the file named by GOOGLE_ADS_CONFIG
    3. ~/.config/neo-google-ads/config.json

Written by google-ads-auth.py, never by hand if it can be helped.

The guardrails follow the same rule: GOOGLE_ADS_ALLOW_WRITE,
GOOGLE_ADS_ALLOWED_CUSTOMER_IDS, GOOGLE_ADS_MAX_DAILY_BUDGET (in the
account currency, not micros), GOOGLE_ADS_MAX_BUDGET_INCREASE_FACTOR and
GOOGLE_ADS_MAX_OPERATIONS_PER_CALL override what the file says. A
container has no file to edit, and a writing server without an account
list and a budget ceiling is the thing these limits exist to prevent.
"""
from __future__ import annotations

import datetime
import json
import copy
import os
import pathlib
import time
import urllib.error
import urllib.parse
import urllib.request

# --------------------------------------------------------------------------
# Constants. The API version is pinned on purpose: Google sunsets versions
# roughly a year after release, and a silent jump to a newer one changes
# field names underneath a running configuration. Override it in the
# configuration when the pinned version reaches its sunset date.
# --------------------------------------------------------------------------

DEFAULT_API_VERSION = "v25"
API_HOST = "https://googleads.googleapis.com"
TOKEN_URL = "https://oauth2.googleapis.com/token"
TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"

# What the refresh token asks Google for. Four scopes since 2.6.0:
#
#   adwords               Google Ads, read and write (the guardrails decide)
#   webmasters            Search Console, read and write — writing is limited
#                         to sitemaps by the tools, not by the scope
#   analytics.readonly    Google Analytics reports. analytics.edit does NOT
#                         cover the Data API (runReport wants analytics or
#                         analytics.readonly), so the read scope stays.
#   analytics.edit        Google Analytics configuration — key events and
#                         custom dimensions only, again limited by the tools
#
# Deliberately NOT requested: analytics.manage.users (who may see the
# property) and the full analytics scope. A refresh token keeps the scopes
# it was issued with; an older one answers write calls with a hint to
# connect Google again.
ADS_SCOPE = "https://www.googleapis.com/auth/adwords"
SEARCH_CONSOLE_SCOPE = "https://www.googleapis.com/auth/webmasters"
ANALYTICS_SCOPE = "https://www.googleapis.com/auth/analytics.readonly"
ANALYTICS_EDIT_SCOPE = "https://www.googleapis.com/auth/analytics.edit"
OAUTH_SCOPE = f"{ADS_SCOPE} {SEARCH_CONSOLE_SCOPE} {ANALYTICS_SCOPE} {ANALYTICS_EDIT_SCOPE}"

# Search Console lives on two hosts: the classic Webmasters API (sites,
# search analytics, sitemaps) and the newer Search Console API (URL
# inspection). Google Analytics on two more: Admin (which properties) and
# Data (reports). None of them needs the developer-token header.
WEBMASTERS_API = "https://www.googleapis.com/webmasters/v3"
SEARCH_CONSOLE_API = "https://searchconsole.googleapis.com/v1"
ANALYTICS_ADMIN_API = "https://analyticsadmin.googleapis.com/v1beta"
ANALYTICS_DATA_API = "https://analyticsdata.googleapis.com/v1beta"

# Per service: its name in hints, the Cloud Console name of the API(s) to
# switch on, and the tool that lists what the login can read.
GOOGLE_SERVICES = {
    "search_console": ("Search Console", "\u201eGoogle Search Console API\u201c",
                       "search_console_sites",
                       "the site URL must match exactly, e.g. sc-domain:example.at or https://example.at/"),
    "analytics": ("Google Analytics", "\u201eGoogle Analytics Data API\u201c and \u201eGoogle Analytics Admin API\u201c",
                  "analytics_properties",
                  "pass the numeric property ID, e.g. 123456789"),
}

# Der Name, unter dem diese Anwendung auftritt: Seitentitel, Kopfzeile,
# Authenticator-App und der Anzeigename des Connectors in claude.ai.
#
# Er darf KEINE Google-Marke enthalten. Googles OAuth-Pruefung weist einen
# Anwendungsnamen mit "Google" darin ab, und der Name der Seite muss zu dem
# passen, der im Zustimmungsbildschirm steht. Beschreibende Saetze wie
# "Zugang zu Google Ads" sind davon nicht betroffen — nur der Name.
#
# Ueber GOOGLE_ADS_PORTAL_NAME aenderbar, damit der naechste Wechsel keine
# Codeaenderung braucht. SERVER_NAME bleibt davon unberuehrt: das ist die
# technische Kennung des MCP-Servers, keine Aufschrift.
PORTAL_NAME = os.environ.get("GOOGLE_ADS_PORTAL_NAME") or "NEO Digital AdsManagment"

# Wer die Anwendung betreibt und wie man ihn erreicht. Googles Pruefung des
# Brandings will beides auf der oeffentlichen Startseite sehen, zusammen mit
# einer Beschreibung des Zwecks — und den Anwendungsnamen im Wortlaut des
# Zustimmungsbildschirms.
PORTAL_OPERATOR = os.environ.get("GOOGLE_ADS_PORTAL_OPERATOR") or "NEO Digital"
PORTAL_CONTACT = os.environ.get("GOOGLE_ADS_PORTAL_CONTACT") or ""

# Impressum und Datenschutz stehen auf der Unternehmensseite. Googles
# Pruefung will die Adressen sehen, nicht eigene Seiten hier.
PORTAL_IMPRESSUM = (os.environ.get("GOOGLE_ADS_PORTAL_IMPRESSUM")
                    or "https://www.neo-digital.at/impressum")
PORTAL_DATENSCHUTZ = (os.environ.get("GOOGLE_ADS_PORTAL_DATENSCHUTZ")
                      or "https://www.neo-digital.at/datenschutz")

CONFIG_DIR = pathlib.Path(
    os.environ.get("GOOGLE_ADS_HOME")
    or pathlib.Path.home() / ".config" / "neo-google-ads"
)
CONFIG_FILE = pathlib.Path(os.environ.get("GOOGLE_ADS_CONFIG") or CONFIG_DIR / "config.json")
CHANGE_LOG = CONFIG_DIR / "changes.jsonl"

# Fields that may come from the environment instead of the file.
ENV_FIELDS = {
    "client_id": "GOOGLE_ADS_CLIENT_ID",
    "client_secret": "GOOGLE_ADS_CLIENT_SECRET",
    "refresh_token": "GOOGLE_ADS_REFRESH_TOKEN",
    "developer_token": "GOOGLE_ADS_DEVELOPER_TOKEN",
    "login_customer_id": "GOOGLE_ADS_LOGIN_CUSTOMER_ID",
    "api_version": "GOOGLE_ADS_API_VERSION",
}

# Defaults for the guardrails. Deliberately restrictive: a fresh install
# reads but does not write, and switching writing on is a decision the
# account owner makes once, in writing.
DEFAULT_GUARDRAILS = {
    "write_enabled": False,
    "allowed_customer_ids": [],       # empty means: every accessible account
    "max_daily_budget_micros": 0,     # 0 means: no ceiling
    "max_budget_increase_factor": 3.0,
    "max_operations_per_call": 200,
    "log_changes": True,
    # Grenzen je Konto. Wer mehrere Kunden betreut, hat fuer jeden andere
    # Zahlen: ein kampagnenstarker darf am Tag 120 bewegen, ein kleiner 8.
    # Was hier nicht steht, erbt das Konto aus den Werten darueber.
    #
    #   "per_account": {"5691007627": {"max_daily_budget_micros": 120000000}}
    #
    # Der Schreibschalter und die Kontenliste stehen bewusst NICHT hier:
    # ob ein Konto ueberhaupt beschrieben werden darf, entscheidet
    # allowed_customer_ids, und das an einer Stelle statt an zweien.
    "per_account": {},
}

# Welche der drei Zahlen ein Konto fuer sich setzen darf. Der Schalter und
# die Kontenliste fehlen mit Absicht — siehe oben.
PER_ACCOUNT_FIELDS = ("max_daily_budget_micros", "max_budget_increase_factor",
                      "max_operations_per_call")

# Die Schutzgrenzen koennen auch aus der Umgebung kommen: ein Container
# startet ohne Konfigurationsdatei, und ohne diese Variablen liefe ein
# Server in Docker, der schreiben darf, ohne Kontenliste und ohne
# Budgetdeckel an.
#
# SIE GELTEN NUR FUER DIE ERSTE INBETRIEBNAHME. Sobald die Konsole die
# Schutzgrenzen einmal gespeichert hat, steht in der Konfiguration ein
# eigener Block, und dann gilt der — die Umgebung wird nicht mehr
# angesehen. Vorher war es umgekehrt: die Variable gewann bei jedem Start
# und die Konsole zeigte das Feld gesperrt. Das passt zu einem Server,
# dessen Betreiber die .env nie anfasst; hier bedient derselbe Mensch
# beides, und eine Einstellung, die sich nicht einstellen laesst, ist
# dann nur im Weg.
GUARDRAIL_ENV = {
    "write_enabled": "GOOGLE_ADS_ALLOW_WRITE",
    "allowed_customer_ids": "GOOGLE_ADS_ALLOWED_CUSTOMER_IDS",
    "max_daily_budget_micros": "GOOGLE_ADS_MAX_DAILY_BUDGET",
    "max_budget_increase_factor": "GOOGLE_ADS_MAX_BUDGET_INCREASE_FACTOR",
    "max_operations_per_call": "GOOGLE_ADS_MAX_OPERATIONS_PER_CALL",
    "log_changes": "GOOGLE_ADS_LOG_CHANGES",
}


def per_account_sauber(roh) -> dict:
    """Reads guardrails.per_account and throws away what is not a limit.

    A hand-edited file is the normal case here, so a typo must not become
    a limit that quietly does not apply. Anything unreadable is dropped —
    the account then inherits the values above it, which is the stricter
    reading of a broken line.
    """
    sauber: dict = {}
    if not isinstance(roh, dict):
        return sauber
    for kennung, werte in roh.items():
        if not isinstance(werte, dict):
            continue
        try:
            konto = normalize_customer_id(kennung)
        except GoogleAdsError:
            continue
        eintrag = {}
        for feld in PER_ACCOUNT_FIELDS:
            if feld not in werte or werte[feld] in (None, ""):
                continue
            try:
                zahl = float(werte[feld])
            except (TypeError, ValueError):
                continue
            if zahl < 0:
                continue
            eintrag[feld] = (zahl if feld == "max_budget_increase_factor"
                             else int(zahl))
        if eintrag:
            sauber[konto] = eintrag
    return sauber


def env_seeds() -> set:
    """Which guardrails the environment would start a fresh server with.

    Only interesting until the console has saved once: from then on the
    configuration file answers, and this set is no longer consulted.
    """
    return {feld for feld, name in GUARDRAIL_ENV.items()
            if (os.environ.get(name) or "").strip()}


def _guardrails_from_env(guardrails: dict) -> dict:
    """Reads the guardrails from the environment, where they are set.

    GOOGLE_ADS_MAX_DAILY_BUDGET is given in the account currency, not in
    micros: nobody types 50000000 for fifty euros without eventually
    typing it wrong, and getting that wrong is the expensive mistake this
    limit exists to catch.
    """
    def gesetzt(name: str) -> str | None:
        """Der Wert einer Umgebungsvariablen, oder None, wenn sie leer ist.

        Eine leere Zeile in der .env ist KEINE Angabe. Vorher zaehlte sie
        als eine: GOOGLE_ADS_ALLOWED_CUSTOMER_IDS= ergab eine leere
        Kontenliste, und die heisst "alle zugaenglichen" — die weiteste
        Einstellung, die es gibt. Zugleich galt die Variable als gesetzt,
        also sperrte die Konsole die Kaestchen, und der Betreiber konnte
        es dort nicht mehr richtigstellen. Ein leer gelassenes Feld in
        einer Vorlage darf nicht die gefaehrlichste Wirkung haben.
        """
        value = os.environ.get(name)
        return None if value is None or not value.strip() else value

    def flag(name: str, current: bool) -> bool:
        value = gesetzt(name)
        if value is None:
            return current
        return value.strip().lower() in ("1", "true", "yes", "on", "ja")

    guardrails["write_enabled"] = flag(GUARDRAIL_ENV["write_enabled"],
                                       guardrails["write_enabled"])
    guardrails["log_changes"] = flag(GUARDRAIL_ENV["log_changes"],
                                     guardrails["log_changes"])

    accounts = gesetzt(GUARDRAIL_ENV["allowed_customer_ids"])
    if accounts is not None:
        guardrails["allowed_customer_ids"] = [
            "".join(c for c in part if c.isdigit())
            for part in accounts.split(",") if part.strip()
        ]

    budget = gesetzt(GUARDRAIL_ENV["max_daily_budget_micros"])
    if budget is not None:
        try:
            guardrails["max_daily_budget_micros"] = int(round(float(budget) * 1_000_000))
        except ValueError:
            raise GoogleAdsError(
                f"{GUARDRAIL_ENV['max_daily_budget_micros']}='{budget}' is not a number. "
                "Give the ceiling in your account currency, for example 50 for fifty."
            ) from None

    for field, caster in (("max_budget_increase_factor", float),
                          ("max_operations_per_call", int)):
        raw = gesetzt(GUARDRAIL_ENV[field])
        if raw is not None:
            try:
                guardrails[field] = caster(raw)
            except ValueError:
                raise GoogleAdsError(
                    f"{GUARDRAIL_ENV[field]}='{raw}' is not a number."
                ) from None
    return guardrails


class GoogleAdsError(Exception):
    """An error the caller is meant to read, not a stack trace."""

    def __init__(self, message: str, *, detail: object = None, status: int = 0):
        super().__init__(message)
        self.message = message
        self.detail = detail
        self.status = status


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

def load_config(path: pathlib.Path | None = None) -> dict:
    """Reads the configuration, environment first, and checks it is complete."""
    path = path or CONFIG_FILE
    data: dict = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise GoogleAdsError(f"Configuration file {path} is not valid JSON: {exc}") from exc

    for field, env_name in ENV_FIELDS.items():
        value = os.environ.get(env_name)
        if value:
            data[field] = value

    # copy.deepcopy, nicht dict(): sonst teilen sich alle Aufrufe dieselbe
    # Liste und dasselbe per_account-Verzeichnis aus DEFAULT_GUARDRAILS.
    guardrails = copy.deepcopy(DEFAULT_GUARDRAILS)
    gespeichert = data.get("guardrails")
    if gespeichert:
        guardrails.update(gespeichert)
    else:
        # Erste Inbetriebnahme: es gibt noch keine gespeicherten Grenzen,
        # also gelten die aus der Umgebung. Ab dem ersten Speichern in der
        # Konsole steht der Block in der Datei und die Umgebung schweigt.
        guardrails = _guardrails_from_env(guardrails)
    guardrails["per_account"] = per_account_sauber(guardrails.get("per_account"))
    data["guardrails"] = guardrails
    data.setdefault("api_version", DEFAULT_API_VERSION)

    missing = [f for f in ("client_id", "client_secret", "refresh_token", "developer_token")
               if not data.get(f)]
    if missing:
        raise GoogleAdsError(
            "Configuration incomplete, missing: " + ", ".join(missing)
            + f". Run google-ads-auth.py to create {path}."
        )
    return data


def save_config(data: dict, path: pathlib.Path | None = None) -> pathlib.Path:
    """Writes the configuration readable by its owner only."""
    path = path or CONFIG_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(path)
    os.chmod(path, 0o600)
    return path


def normalize_customer_id(customer_id: str | int) -> str:
    """Strips the hyphens Google writes in the interface but rejects in the API.

    A Google Ads customer ID is exactly ten digits. Checking the length is
    not pedantry: a typo that keeps some digits would otherwise pass here
    and come back as a permission error from the API, which reads like a
    problem with the account rather than with the number.
    """
    digits = "".join(c for c in str(customer_id) if c.isdigit())
    if len(digits) != 10:
        raise GoogleAdsError(
            f"'{customer_id}' is not a customer ID. Expected ten digits, "
            f"got {len(digits)}. Hyphens are allowed: 123-456-7890."
        )
    return digits


# --------------------------------------------------------------------------
# The client
# --------------------------------------------------------------------------

def project_number_of(client_id: str) -> str:
    """Die Nummer des Google-Cloud-Projekts, aus der Client-ID gelesen.

    Eine OAuth-Client-ID hat die Form <Projektnummer>-<Kennung>.apps.
    googleusercontent.com. Die Nummer davor benennt das Cloud-Projekt —
    und damit das, woran die Zugriffsstufe haengt.

    Das ist die schnellste Antwort auf die teuerste Verwechslung: einen
    neuen Client in einem NEUEN Projekt anzulegen setzt die Stufe zurueck
    auf Test, und dann ist kein einziges echtes Konto mehr lesbar,
    waehrend die Kontenliste weiter erscheint.
    """
    kopf = (client_id or "").split("-", 1)[0].strip()
    return kopf if kopf.isdigit() else ""


def error_code_of(exc: "GoogleAdsError") -> str:
    """The API's own error code, e.g. authorizationError=USER_PERMISSION_DENIED.

    _translate already puts it on the second line of the message; this
    digs it back out so a caller can show it instead of Google's opening
    sentence, which says only "The caller does not have permission" and
    names neither the account nor the reason.
    """
    payload = getattr(exc, "detail", None) or {}
    for detail in (payload.get("error") or {}).get("details") or []:
        for item in detail.get("errors") or []:
            code = item.get("errorCode") or {}
            for key, value in code.items():
                return f"{key}={value}"
    for line in exc.message.splitlines()[1:]:
        stripped = line.strip()
        if "=" in stripped and " — " in stripped:
            return stripped.split(" — ")[0]
    return ""


def _woher(rails: dict, feld: str) -> str:
    """Says whether a limit is this account's own or the one above it.

    A refusal that does not say where the number came from sends the
    reader to the wrong file.
    """
    if feld in (rails.get("_eigene_felder") or ()):
        return " (the account's own limit, guardrails.per_account)"
    return f" (the default, guardrails.{feld})"


class Client:
    """One configured connection to the Google Ads API."""

    def __init__(self, config: dict | None = None, *, timeout: int = 120):
        self.config = config if config is not None else load_config()
        self.guardrails = self.config["guardrails"]
        self.api_version = self.config.get("api_version") or DEFAULT_API_VERSION
        self.timeout = timeout
        self._token = ""
        self._token_expires = 0.0

    # -- authentication ----------------------------------------------------

    def access_token(self) -> str:
        """Returns a valid access token, refreshing it a minute before it dies."""
        if self._token and time.time() < self._token_expires - 60:
            return self._token

        payload = urllib.parse.urlencode({
            "client_id": self.config["client_id"],
            "client_secret": self.config["client_secret"],
            "refresh_token": self.config["refresh_token"],
            "grant_type": "refresh_token",
        }).encode("utf-8")
        request = urllib.request.Request(TOKEN_URL, data=payload, method="POST")
        request.add_header("Content-Type", "application/x-www-form-urlencoded")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            raise GoogleAdsError(
                "Could not refresh the access token. The refresh token is probably "
                "revoked or the OAuth client changed. Run google-ads-auth.py again.",
                detail=detail, status=exc.code,
            ) from exc
        except urllib.error.URLError as exc:
            raise GoogleAdsError(f"Cannot reach {TOKEN_URL}: {exc.reason}") from exc

        self._token = body["access_token"]
        self._token_expires = time.time() + int(body.get("expires_in", 3600))
        return self._token

    def granted_scopes(self) -> set[str]:
        """The scopes the stored login really carries, as Google reports them.

        Google's consent screen lets the user untick single permissions, and
        a login from before 2.6.0 lacks the write scopes. Asking tokeninfo is
        the only way to know without trying a write.
        """
        url = f"{TOKENINFO_URL}?access_token={urllib.parse.quote(self.access_token())}"
        try:
            with urllib.request.urlopen(url, timeout=self.timeout) as response:
                info = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, json.JSONDecodeError) as exc:
            raise GoogleAdsError(f"Cannot read the permissions of the login: {exc}") from exc
        return set(str(info.get("scope") or "").split())

    # -- transport ---------------------------------------------------------

    def _headers(self, login_customer_id: str | None = None) -> dict:
        """The three headers every call carries, plus the manager header.

        login_customer_id has three states on purpose, because the header
        is the usual reason an account cannot be read and a diagnosis has
        to be able to try all three:

            None   take whatever the configuration says (the default)
            ""     send NO login-customer-id at all
            value  send exactly this one

        The previous version could not express "send none": an empty
        string fell back to the configuration, so the only way to try
        without the header was to overwrite config in place — shared
        state, in a server that answers requests on several threads.
        """
        headers = {
            "Authorization": f"Bearer {self.access_token()}",
            "developer-token": self.config["developer_token"],
            "Content-Type": "application/json",
        }
        login = self.config.get("login_customer_id") or "" \
            if login_customer_id is None else login_customer_id
        if login:
            headers["login-customer-id"] = normalize_customer_id(login)
        return headers

    def call(self, method: str, path: str, body: dict | None = None,
             *, login_customer_id: str | None = None) -> dict:
        """One REST call. Raises GoogleAdsError with the API's own wording."""
        url = f"{API_HOST}/{self.api_version}/{path.lstrip('/')}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(url, data=data, method=method)
        for key, value in self._headers(login_customer_id).items():
            request.add_header(key, value)

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raise self._translate(exc) from exc
        except urllib.error.URLError as exc:
            raise GoogleAdsError(f"Cannot reach {url}: {exc.reason}") from exc

    def _translate(self, exc: urllib.error.HTTPError) -> GoogleAdsError:
        """Turns the API's nested error envelope into one readable sentence.

        A Google Ads failure arrives as error.details[].errors[], each with
        an errorCode object whose single key names the failing rule. Read
        raw it is unusable; the message below names rule, wording and the
        field that triggered it.
        """
        raw = exc.read().decode("utf-8", "replace")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return GoogleAdsError(f"HTTP {exc.code} from the Google Ads API: {raw[:800]}",
                                  status=exc.code)

        error = payload.get("error") or {}
        lines: list[str] = []
        for detail in error.get("details") or []:
            for item in detail.get("errors") or []:
                code = item.get("errorCode") or {}
                name = ": ".join(f"{k}={v}" for k, v in code.items()) or "error"
                location = item.get("location") or {}
                where = ".".join(
                    str(f.get("fieldName", "")) for f in location.get("fieldPathElements") or []
                )
                text = item.get("message", "")
                lines.append(f"{name} — {text}" + (f" (field: {where})" if where else ""))

        summary = error.get("message") or f"HTTP {exc.code}"
        if lines:
            summary += "\n  " + "\n  ".join(lines)
        if exc.code == 401:
            summary += "\n  Hint: the access token was rejected. Run google-ads-auth.py again."
        if exc.code == 403:
            # Not the developer token: Google sunset those on 9 September
            # 2026 and the header is now ignored. What decides access is
            # the Google Cloud project behind the OAuth credentials.
            summary += ("\n  Hint: the Google Cloud project behind these OAuth "
                        "credentials is probably not approved for production yet — "
                        "a new project starts at Test access and may only read test "
                        "accounts. Cloud Console -> Google Ads API -> Overview -> "
                        "upgrade the access level. The project is the number before "
                        "the dash in the client ID.")
        return GoogleAdsError(summary, detail=payload, status=exc.code)

    # -- Search Console and Analytics (reading) ------------------------------

    def google_call(self, method: str, url: str, body: dict | None = None,
                    *, service: str = "search_console") -> dict:
        """One call to a plain Google API (Search Console, Analytics): bearer token only.

        Deliberately separate from call(): no developer-token, no
        login-customer-id, and an error envelope of a different shape.
        """
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(url, data=data, method=method)
        request.add_header("Authorization", f"Bearer {self.access_token()}")
        request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raise self._translate_google(exc, service) from exc
        except urllib.error.URLError as exc:
            raise GoogleAdsError(f"Cannot reach {url}: {exc.reason}") from exc

    def _translate_google(self, exc: urllib.error.HTTPError,
                          service: str = "search_console") -> GoogleAdsError:
        """Google's standard error envelope, plus the three causes that matter.

        Search Console and Analytics fail for reasons that have nothing to
        do with the request: the refresh token predates the scope, the API
        is not switched on in the Cloud project, or the Google account
        behind the token has no access to the property. Each gets a hint
        that says what to do — the raw message says none of that.
        """
        name, apis, list_tool, id_hint = GOOGLE_SERVICES[service]
        raw = exc.read().decode("utf-8", "replace")
        try:
            error = (json.loads(raw) or {}).get("error") or {}
        except json.JSONDecodeError:
            return GoogleAdsError(f"HTTP {exc.code} from the {name} API: {raw[:800]}",
                                  status=exc.code)

        message = error.get("message") or f"HTTP {exc.code}"
        reasons = {str(d.get("reason", "")) for d in error.get("details") or [] if isinstance(d, dict)}
        reasons |= {str(e.get("reason", "")) for e in error.get("errors") or [] if isinstance(e, dict)}
        lower = message.lower()

        if "ACCESS_TOKEN_SCOPE_INSUFFICIENT" in reasons or "insufficient authentication scopes" in lower:
            message += (f"\n  Hint: the stored Google login lacks this {name} permission — it "
                        "predates it, or the box was left unticked. Connect Google once more "
                        "in the console (or run google-ads-auth.py) and allow every "
                        f"{name} permission on Google's consent screen.")
        elif "SERVICE_DISABLED" in reasons or "has not been used in project" in lower or "is disabled" in lower:
            message += (f"\n  Hint: switch on the {apis} in the Google Cloud project behind "
                        "these OAuth credentials (APIs & Services -> Library). "
                        "The project is the number before the dash in the client ID.")
        elif exc.code == 403:
            message += (f"\n  Hint: the Google account behind this login has no access to this "
                        f"property, or not enough to change it (writing needs full access in "
                        f"Search Console, the Editor role in Analytics). {list_tool} lists the "
                        f"ones it can read; {id_hint}.")
        return GoogleAdsError(message, detail=error, status=exc.code)

    def search_console_sites(self) -> list[dict]:
        return self.google_call("GET", f"{WEBMASTERS_API}/sites").get("siteEntry") or []

    def search_console_query(self, site_url: str, body: dict) -> dict:
        site = urllib.parse.quote(site_url, safe="")
        return self.google_call("POST", f"{WEBMASTERS_API}/sites/{site}/searchAnalytics/query", body)

    def search_console_sitemaps(self, site_url: str) -> list[dict]:
        site = urllib.parse.quote(site_url, safe="")
        return self.google_call("GET", f"{WEBMASTERS_API}/sites/{site}/sitemaps").get("sitemap") or []

    def search_console_inspect(self, site_url: str, url: str, language: str = "de-AT") -> dict:
        return self.google_call("POST", f"{SEARCH_CONSOLE_API}/urlInspection/index:inspect",
                                {"inspectionUrl": url, "siteUrl": site_url, "languageCode": language})

    def analytics_account_summaries(self) -> list[dict]:
        summaries, token = [], ""
        while True:
            url = f"{ANALYTICS_ADMIN_API}/accountSummaries?pageSize=200"
            if token:
                url += "&pageToken=" + urllib.parse.quote(token)
            page = self.google_call("GET", url, service="analytics")
            summaries.extend(page.get("accountSummaries") or [])
            token = page.get("nextPageToken") or ""
            if not token:
                return summaries

    def analytics_report(self, property_id: str, body: dict) -> dict:
        return self.google_call("POST", f"{ANALYTICS_DATA_API}/properties/{property_id}:runReport",
                                body, service="analytics")

    def analytics_metadata(self, property_id: str) -> dict:
        return self.google_call("GET", f"{ANALYTICS_DATA_API}/properties/{property_id}/metadata",
                                service="analytics")

    def _google_pages(self, url: str, key: str, service: str) -> list[dict]:
        """Every page of a Google list call, joined."""
        items, token = [], ""
        while True:
            page_url = url + ("&" if "?" in url else "?") + "pageSize=200"
            if token:
                page_url += "&pageToken=" + urllib.parse.quote(token)
            page = self.google_call("GET", page_url, service=service)
            items.extend(page.get(key) or [])
            token = page.get("nextPageToken") or ""
            if not token:
                return items

    def analytics_property(self, property_id: str) -> dict:
        return self.google_call("GET", f"{ANALYTICS_ADMIN_API}/properties/{property_id}",
                                service="analytics")

    def analytics_data_retention(self, property_id: str) -> dict:
        return self.google_call("GET", f"{ANALYTICS_ADMIN_API}/properties/{property_id}/dataRetentionSettings",
                                service="analytics")

    def analytics_key_events(self, property_id: str) -> list[dict]:
        return self._google_pages(f"{ANALYTICS_ADMIN_API}/properties/{property_id}/keyEvents",
                                  "keyEvents", "analytics")

    def analytics_custom_dimensions(self, property_id: str) -> list[dict]:
        return self._google_pages(f"{ANALYTICS_ADMIN_API}/properties/{property_id}/customDimensions",
                                  "customDimensions", "analytics")

    # -- Search Console and Analytics (writing) ------------------------------

    def google_write(self, target: str, method: str, url: str, body: dict | None = None, *,
                     service: str, operation: dict, reason: str = "") -> dict:
        """The one door for LIVE writes to Search Console and Analytics.

        Neither API knows validateOnly. The dry run therefore happens in the
        MCP server — it reads the current state and describes the change —
        and never comes through here. What does come through is real: the
        master switch must be on, and the attempt is logged before the
        answer goes back, failures included. allowed_customer_ids does not
        apply; it names Google Ads accounts, and a property is none.
        """
        if not self.guardrails.get("write_enabled"):
            raise GoogleAdsError(
                "Writing is switched off. Switch it on in the console (Schutzgrenzen -> "
                "Schreiben erlauben) once the owner has agreed to it; until then only the "
                "dry run is possible."
            )
        started = time.time()
        try:
            answer = self.google_call(method, url, body, service=service)
        except GoogleAdsError as exc:
            self.log_change(target, [operation], dry_run=False, reason=reason,
                            result="error", detail=exc.message)
            raise
        self.log_change(target, [operation], dry_run=False, reason=reason, result="ok",
                        detail=answer, duration_ms=int((time.time() - started) * 1000))
        return answer

    def search_console_submit_sitemap(self, site_url: str, sitemap_url: str, *,
                                      reason: str = "") -> dict:
        site = urllib.parse.quote(site_url, safe="")
        feed = urllib.parse.quote(sitemap_url, safe="")
        return self.google_write(f"search_console:{site_url}", "PUT",
                                 f"{WEBMASTERS_API}/sites/{site}/sitemaps/{feed}",
                                 service="search_console", reason=reason,
                                 operation={"submit_sitemap": sitemap_url})

    def search_console_delete_sitemap(self, site_url: str, sitemap_url: str, *,
                                      reason: str = "") -> dict:
        site = urllib.parse.quote(site_url, safe="")
        feed = urllib.parse.quote(sitemap_url, safe="")
        return self.google_write(f"search_console:{site_url}", "DELETE",
                                 f"{WEBMASTERS_API}/sites/{site}/sitemaps/{feed}",
                                 service="search_console", reason=reason,
                                 operation={"delete_sitemap": sitemap_url})

    def analytics_create_key_event(self, property_id: str, event_name: str,
                                   counting_method: str, *, reason: str = "") -> dict:
        body = {"eventName": event_name, "countingMethod": counting_method}
        return self.google_write(f"analytics:{property_id}", "POST",
                                 f"{ANALYTICS_ADMIN_API}/properties/{property_id}/keyEvents",
                                 body, service="analytics", reason=reason,
                                 operation={"create_key_event": body})

    def analytics_delete_key_event(self, property_id: str, resource_name: str, *,
                                   reason: str = "") -> dict:
        return self.google_write(f"analytics:{property_id}", "DELETE",
                                 f"{ANALYTICS_ADMIN_API}/{resource_name}",
                                 service="analytics", reason=reason,
                                 operation={"delete_key_event": resource_name})

    def analytics_create_custom_dimension(self, property_id: str, dimension: dict, *,
                                          reason: str = "") -> dict:
        return self.google_write(f"analytics:{property_id}", "POST",
                                 f"{ANALYTICS_ADMIN_API}/properties/{property_id}/customDimensions",
                                 dimension, service="analytics", reason=reason,
                                 operation={"create_custom_dimension": dimension})

    def analytics_archive_custom_dimension(self, property_id: str, resource_name: str, *,
                                           reason: str = "") -> dict:
        return self.google_write(f"analytics:{property_id}", "POST",
                                 f"{ANALYTICS_ADMIN_API}/{resource_name}:archive", {},
                                 service="analytics", reason=reason,
                                 operation={"archive_custom_dimension": resource_name})

    # -- reading -----------------------------------------------------------

    def list_accessible_customers(self) -> list[str]:
        """The accounts this refresh token may see, as bare customer IDs."""
        answer = self.call("GET", "customers:listAccessibleCustomers")
        return [name.split("/")[-1] for name in answer.get("resourceNames", [])]

    def search(self, customer_id: str, query: str, *,
               max_rows: int = 10000,
               login_customer_id: str | None = None) -> list[dict]:
        """Runs a GAQL query and follows the pages until max_rows is reached.

        The request body carries the query and nothing else. pageSize was
        removed here on purpose: the API documents it as deprecated and
        answers PAGE_SIZE_NOT_SUPPORTED when it appears, which arrives as
        a bare "Request contains an invalid argument" and looks like a
        problem with the account rather than with the request. To limit a
        result, put LIMIT in the query, which is what GAQL is for.
        """
        customer_id = normalize_customer_id(customer_id)
        login_customer_id = self.login_for(customer_id, login_customer_id)
        rows: list[dict] = []
        page_token = ""
        while True:
            body: dict = {"query": query}
            if page_token:
                body["pageToken"] = page_token
            answer = self.call("POST", f"customers/{customer_id}/googleAds:search", body,
                               login_customer_id=login_customer_id)
            rows.extend(answer.get("results", []))
            page_token = answer.get("nextPageToken", "")
            if not page_token or len(rows) >= max_rows:
                break
        return rows[:max_rows]

    def login_for(self, customer_id: str,
                  login_customer_id: str | None = None) -> str | None:
        """Which manager header this one account needs.

        A single login_customer_id in the configuration assumes every
        account hangs under the same manager. That is often false: some
        are reached directly, some through one manager, some through
        another. The measurement on /setup/diagnose writes what it found
        into account_logins, and this is where that is read back.

        An explicit argument always wins. A stored empty string means
        "this account wants no manager header" — which is why the lookup
        tests for the key rather than for a truthy value.
        """
        if login_customer_id is not None:
            return login_customer_id
        per_account = self.config.get("account_logins") or {}
        return per_account.get(normalize_customer_id(customer_id))

    def probe_account(self, customer_id: str,
                      login_customer_id: str | None = None) -> tuple[bool, str, str]:
        """One read against one account with one header setting.

        Returns (worked, error code, full message). Changes nothing and
        reads a single row, so a whole matrix of these costs little.
        """
        # Ausdruecklich an login_for vorbei: diese Messung ermittelt die
        # Zuordnung gerade erst und darf sich nicht auf sie stuetzen.
        if login_customer_id is None:
            login_customer_id = self.config.get("login_customer_id") or ""
        try:
            self.search(customer_id, "SELECT customer.id FROM customer LIMIT 1",
                        max_rows=1, login_customer_id=login_customer_id)
            return True, "", ""
        except GoogleAdsError as exc:
            return False, error_code_of(exc), exc.message

    def permission_matrix(self, customer_ids: list[str]) -> list[dict]:
        """Which manager header makes which account readable. Measured, not guessed.

        USER_PERMISSION_DENIED names neither the header nor the link that
        is missing, so reading the message is guesswork. This tries every
        combination that could be right — no header, the account itself,
        and each other accessible account as the manager — and reports
        what actually happened.

        It stops at the first setting that works for an account, so the
        common case costs one call per account and only a broken one
        costs the full row.
        """
        results = []
        for customer_id in customer_ids:
            candidates: list[tuple[str, str | None]] = [
                ("wie eingestellt", None),
                ("ohne Verwaltungskopf", ""),
                ("das Konto selbst", customer_id),
            ]
            candidates += [("Verwaltungskonto " + other, other)
                           for other in customer_ids if other != customer_id]

            row = {"id": customer_id, "works_with": None, "works_label": "",
                   "attempts": [], "code": "", "message": ""}
            # Deduplicated by the header that actually goes out, not by the
            # argument: "as configured" sends the configured manager, which
            # appears again further down the list by name. Without this the
            # same call is made twice for every account.
            configured = self.config.get("login_customer_id") or ""
            seen: set[str] = set()
            for label, login in candidates:
                key = configured if login is None else login
                if key in seen:
                    continue
                seen.add(key)
                ok, code, message = self.probe_account(customer_id, login)
                row["attempts"].append({"label": label, "login": login,
                                        "ok": ok, "code": code})
                if ok:
                    row["works_with"] = key
                    row["works_label"] = label
                    break
                if not row["code"]:
                    row["code"], row["message"] = code, message
            results.append(row)
        return results

    # -- writing -----------------------------------------------------------

    def mutate(self, customer_id: str, operations: list[dict], *, dry_run: bool = True,
               partial_failure: bool = False, login_customer_id: str | None = None,
               response_content_type: str = "RESOURCE_NAME_ONLY",
               reason: str = "") -> dict:
        """Sends mutate operations. Refuses everything the guardrails forbid.

        dry_run maps to the API's validateOnly: the request is checked
        against every rule Google would apply, and nothing is changed. It
        is the default because the expensive mistake here is a write that
        was meant as a question.
        """
        customer_id = normalize_customer_id(customer_id)
        login_customer_id = self.login_for(customer_id, login_customer_id)
        self.check_write_allowed(customer_id, operations, dry_run=dry_run)

        body = {
            "mutateOperations": operations,
            "validateOnly": bool(dry_run),
            "partialFailure": bool(partial_failure),
            "responseContentType": response_content_type,
        }
        started = time.time()
        try:
            answer = self.call("POST", f"customers/{customer_id}/googleAds:mutate", body,
                               login_customer_id=login_customer_id)
        except GoogleAdsError as exc:
            self.log_change(customer_id, operations, dry_run=dry_run, reason=reason,
                            result="error", detail=exc.message)
            raise
        self.log_change(customer_id, operations, dry_run=dry_run, reason=reason,
                        result="ok", detail=answer,
                        duration_ms=int((time.time() - started) * 1000))
        return answer

    # -- guardrails --------------------------------------------------------

    def rails_for(self, customer_id: str) -> dict:
        """The guardrails as they apply to one account.

        Everything the account does not set for itself comes from the
        values above it, and nothing else is consulted: what the console
        stored is what applies.
        """
        rails = dict(self.guardrails)
        eigene = (self.guardrails.get("per_account") or {}).get(
            normalize_customer_id(customer_id)) or {}
        for feld in PER_ACCOUNT_FIELDS:
            if feld in eigene:
                rails[feld] = eigene[feld]
        rails["_eigene_felder"] = sorted(f for f in PER_ACCOUNT_FIELDS if f in eigene)
        return rails

    def check_write_allowed(self, customer_id: str, operations: list[dict],
                            *, dry_run: bool) -> None:
        """Four questions before anything leaves the machine.

        A dry run passes the switch and the account list too: a validation
        that would be refused live must be refused now, otherwise the dry
        run answers a question nobody asked.
        """
        rails = self.rails_for(customer_id)

        if not rails.get("write_enabled") and not dry_run:
            raise GoogleAdsError(
                "Writing is switched off. Set guardrails.write_enabled to true in "
                f"{CONFIG_FILE} (or export GOOGLE_ADS_ALLOW_WRITE=1) once the account "
                "owner has agreed to it."
            )

        allowed = [normalize_customer_id(c) for c in (rails.get("allowed_customer_ids") or [])]
        if allowed and customer_id not in allowed:
            raise GoogleAdsError(
                f"Account {customer_id} is not in guardrails.allowed_customer_ids. "
                "Add it there before changing anything in it."
            )

        limit = int(rails.get("max_operations_per_call") or 0)
        if limit and len(operations) > limit:
            raise GoogleAdsError(
                f"{len(operations)} operations in one call, the limit for account "
                f"{customer_id} is {limit}"
                f"{_woher(rails, 'max_operations_per_call')}. "
                "Split the change into smaller steps so each one can be reviewed."
            )

        for operation in operations:
            self._check_budget(operation, customer_id, rails)

    def _check_budget(self, operation: dict, customer_id: str,
                      rails: dict | None = None) -> None:
        """Stops a budget from leaving the agreed range.

        Two ways to lose money by one keystroke: writing euros where the
        API wants micros (a factor of a million), and raising a budget by
        an order of magnitude in one step. Both are caught here.
        """
        budget_op = operation.get("campaignBudgetOperation")
        if not budget_op:
            return
        resource = budget_op.get("create") or budget_op.get("update") or {}
        amount = resource.get("amountMicros")
        if amount in (None, ""):
            return
        amount = int(amount)

        rails = rails if rails is not None else self.rails_for(customer_id)
        ceiling = int(rails.get("max_daily_budget_micros") or 0)
        if ceiling and amount > ceiling:
            raise GoogleAdsError(
                f"Budget {amount / 1_000_000:.2f} per day is above the ceiling of "
                f"{ceiling / 1_000_000:.2f} for account {customer_id}"
                f"{_woher(rails, 'max_daily_budget_micros')}. "
                "Raise the ceiling deliberately or lower the budget."
            )

        factor = float(rails.get("max_budget_increase_factor") or 0)
        name = budget_op.get("update", {}).get("resourceName")
        if not factor or not name:
            return
        current = self._current_budget_micros(customer_id, name)
        if current and amount > current * factor:
            raise GoogleAdsError(
                f"Budget would go from {current / 1_000_000:.2f} to "
                f"{amount / 1_000_000:.2f} per day, more than the factor of {factor} "
                f"for account {customer_id}"
                f"{_woher(rails, 'max_budget_increase_factor')}. Take a smaller step, "
                "or raise the factor after agreeing on it."
            )

    def _current_budget_micros(self, customer_id: str, resource_name: str) -> int:
        """Reads the budget that is in place now, so the step can be measured."""
        query = ("SELECT campaign_budget.amount_micros FROM campaign_budget "
                 f"WHERE campaign_budget.resource_name = '{resource_name}'")
        try:
            rows = self.search(customer_id, query + " LIMIT 1", max_rows=1)
        except GoogleAdsError:
            return 0
        if not rows:
            return 0
        return int(rows[0].get("campaignBudget", {}).get("amountMicros") or 0)

    # -- evidence ----------------------------------------------------------

    def log_change(self, customer_id: str, operations: list[dict], *, dry_run: bool,
                   result: str, reason: str = "", detail: object = None,
                   duration_ms: int = 0) -> None:
        """Appends one line per write attempt, dry runs included.

        The log is the answer to 'who changed this and why'. It is written
        before the caller sees the answer, so a crash cannot swallow it.
        """
        if not self.guardrails.get("log_changes", True):
            return
        entry = {
            "time": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            "customer_id": customer_id,
            "dry_run": dry_run,
            "result": result,
            "reason": reason,
            "operation_count": len(operations),
            "operations": operations,
            "duration_ms": duration_ms,
            "detail": detail,
        }
        try:
            CHANGE_LOG.parent.mkdir(parents=True, exist_ok=True)
            with CHANGE_LOG.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
            os.chmod(CHANGE_LOG, 0o600)
        except OSError:
            pass  # A log that cannot be written must not stop the change.
