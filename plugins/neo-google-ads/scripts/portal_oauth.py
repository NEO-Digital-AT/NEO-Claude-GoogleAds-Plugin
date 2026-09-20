#!/usr/bin/env python3
"""Die dritte Tür: OAuth 2.1, damit Claude den Server als Connector kennt.

WARUM ES DIESE DATEI GIBT

Der Server hatte zwei Türen: `/mcp` mit einem festen Zugangswort und
`/setup` mit einer Anmeldung für Menschen. Das feste Wort reicht für Claude
Code, wo man es in die Konfiguration schreibt. In den Claude-Apps (Web,
Desktop, Handy) kann man einen benutzerdefinierten Connector aber nicht mit
einem Wort im Kopf anlegen — dort läuft die Anmeldung über den OAuth-Teil
der MCP-Spezifikation. Fehlt der, fragt die Oberfläche nach Client-ID und
Secret, und es gibt nichts, was man dort eintragen könnte.

Das war ein Denkfehler im Aufbau, nicht eine fehlende Kleinigkeit: Die
Dokumentation behauptete, claude.ai brauche nur „ein Wort, das bleibt".

WAS HIER PASSIERT, IN EINEM SATZ

Claude fragt den Server, wie man sich anmeldet; der Server schickt den
Menschen ins eigene Portal; nach Passkey oder Kennwort und einer
Bestätigung bekommt Claude ein Token, das nur für diesen einen Server gilt.

DIE FÜNF ENTSCHEIDUNGEN, DIE MAN NICHT ANDERS TREFFEN DARF

1. PKCE MIT S256, IMMER. `plain` wird abgelehnt, ein fehlender
   `code_challenge` ebenso. Ohne PKCE könnte ein abgefangener Code von
   jemand anderem eingelöst werden; das ist der klassische Angriff auf
   diesen Ablauf und der Grund, warum OAuth 2.1 PKCE verpflichtend macht.

2. DIE RÜCKADRESSE MUSS EXAKT PASSEN. Kein Präfixvergleich, keine
   Platzhalter. `https://gut.example/cb` und `https://gut.example/cb.evil`
   fangen gleich an — wer auf Präfix prüft, verschenkt den Code.

3. DAS TOKEN GEHÖRT ZU DIESEM SERVER. Jedes Token trägt die Ressource, für
   die es ausgestellt wurde (RFC 8707), und `/mcp` weist ein Token ab, das
   für etwas anderes gedacht war. Sonst könnte ein Betreiber, bei dem sich
   jemand anmeldet, das erhaltene Token hier einlösen.

4. DIE REGISTRIERUNG IST OFFEN, ABER GEZÄHLT. Die Spezifikation verlangt
   dynamische Registrierung — sonst müsste man Client-ID und Secret von
   Hand austauschen, und genau das wollen wir ja loswerden. Eine offene
   Tür ohne Zähler wird irgendwann zugemüllt, deshalb die Obergrenze in
   `portal_store.OAUTH_MAX_CLIENTS` und nur `https`-Rückadressen (plus
   `http://localhost` für lokal laufende Clients).

5. EIN REGISTRIERTER CLIENT IST NOCH KEIN ZUGANG. Registrieren darf jeder,
   hereinkommen nur, wer sich im Portal anmeldet UND auf dem
   Bestätigungsbildschirm zustimmt. Der Bildschirm nennt Namen und
   Rückadresse des Clients — daran erkennt man einen fremden.

Deutsch auf dem Bildschirm, Englisch in den Protokollnamen: Die Felder
heißen so, wie die Spezifikation sie nennt, sonst versteht sie kein Client.
"""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
import urllib.parse

import google_ads_setup as ui
import portal_shell as sh
import portal_store as store
from neo_design import esc

# Was ein Token dürfen kann. Bewusst nur zwei: Wer lesen darf, sieht Zahlen;
# wer schreiben darf, ändert Gebote und Budgets. Eine feinere Einteilung
# würde eine Oberfläche brauchen, in der man sie auch versteht.
SCOPES = {
    "ads:read": "Kampagnen, Keywords, Suchbegriffe und Berichte lesen",
    "ads:write": "Änderungen vornehmen — Gebote, Budgets, Keywords, Status",
}
DEFAULT_SCOPE = "ads:read ads:write"

# Diese Werkzeuge ändern etwas. Ein Token ohne `ads:write` kommt an sie
# nicht heran. Die Liste steht hier und nicht im MCP-Server, weil sie eine
# Frage der Berechtigung ist und keine des Werkzeugs.
WRITE_TOOLS = frozenset({
    "google_ads_add_keywords",
    "google_ads_add_negative_keywords",
    "google_ads_set_status",
    "google_ads_set_budget",
    "google_ads_set_bid",
    "google_ads_mutate",
})


class OAuthError(Exception):
    """Ein Fehler, den die Spezifikation benennt.

    `redirectable` sagt, ob er an die Rückadresse gehen darf. Bei einer
    kaputten oder unbekannten Rückadresse darf er das NICHT — sonst würde
    der Server auf eine beliebige fremde Adresse weiterleiten, sobald
    jemand sie in die Anfrage schreibt.
    """

    def __init__(self, code: str, description: str = "", *, redirectable: bool = True,
                 status: int = 400, redirect_uri: str = "", state: str = ""):
        super().__init__(description or code)
        self.code = code
        self.description = description
        self.redirectable = redirectable
        self.status = status
        # Erst gesetzt, sobald die Rueckadresse geprueft ist. Vorher waere
        # eine Weiterleitung dorthin genau die offene Weiterleitung, die man
        # nicht bauen darf.
        self.redirect_uri = redirect_uri
        self.state = state

    def payload(self) -> dict:
        out = {"error": self.code}
        if self.description:
            out["error_description"] = self.description
        return out


# --------------------------------------------------------------------------
# Die zwei Auskunftsdokumente, denen ein Client folgt
# --------------------------------------------------------------------------

def protected_resource_metadata(base: str, mcp_path: str) -> dict:
    """RFC 9728 — „wer stellt für diesen Server Token aus?"

    Das ist das erste, was ein Client abruft, nachdem ihn ein 401 mit dem
    passenden `WWW-Authenticate` darauf gestoßen hat.
    """
    return {
        "resource": resource_url(base, mcp_path),
        "authorization_servers": [base],
        "scopes_supported": sorted(SCOPES),
        "bearer_methods_supported": ["header"],
        "resource_documentation": f"{base}/",
    }


def authorization_server_metadata(base: str) -> dict:
    """RFC 8414 — wo Anmeldung, Tokenausgabe und Registrierung liegen."""
    return {
        "issuer": base,
        "authorization_endpoint": f"{base}/authorize",
        "token_endpoint": f"{base}/token",
        "registration_endpoint": f"{base}/register",
        "scopes_supported": sorted(SCOPES),
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        # NUR S256. `plain` wäre zulässig, aber wertlos: Der Prüfwert stünde
        # dann im Klartext in derselben Anfrage, die ein Angreifer abfängt.
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["client_secret_post",
                                                  "client_secret_basic", "none"],
        "resource_indicators_supported": True,
    }


def resource_url(base: str, mcp_path: str) -> str:
    return base.rstrip("/") + "/" + mcp_path.strip("/")


def challenge_header(base: str, mcp_path: str, *, error: str = "") -> str:
    """Der 401-Kopf, dem der Client folgt.

    `resource_metadata` ist der eigentliche Faden. Stand dort nur `realm`,
    wusste der Client, dass ein Token fehlt, aber nicht, wo er eines
    bekommt — genau der Zustand vor dieser Datei.
    """
    teile = ['Bearer realm="neo-google-ads"',
             f'resource_metadata="{base}/.well-known/oauth-protected-resource"']
    if error:
        teile.append(f'error="{error}"')
    return ", ".join(teile)


# --------------------------------------------------------------------------
# Dynamische Registrierung (RFC 7591)
# --------------------------------------------------------------------------

def register(connection, body: bytes, base: str) -> dict:
    try:
        payload = json.loads(body.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise OAuthError("invalid_client_metadata", "Der Rumpf ist kein JSON.",
                         redirectable=False)
    if not isinstance(payload, dict):
        raise OAuthError("invalid_client_metadata", "Erwartet wird ein JSON-Objekt.",
                         redirectable=False)

    uris = payload.get("redirect_uris") or []
    if not isinstance(uris, list) or not uris:
        raise OAuthError("invalid_redirect_uri", "redirect_uris fehlt.",
                         redirectable=False)
    sauber = []
    for uri in uris[:5]:
        if not isinstance(uri, str) or not _redirect_allowed(uri):
            raise OAuthError(
                "invalid_redirect_uri",
                f"Nicht erlaubt: {uri!r}. Zugelassen sind https-Adressen und "
                "http://localhost bzw. http://127.0.0.1 für lokal laufende Clients.",
                redirectable=False)
        sauber.append(uri)

    if store.count_clients(connection) >= store.OAUTH_MAX_CLIENTS:
        raise OAuthError(
            "invalid_client_metadata",
            f"Es sind bereits {store.OAUTH_MAX_CLIENTS} Clients registriert. "
            "Nicht mehr benutzte im Portal entfernen.",
            redirectable=False, status=403)

    name = str(payload.get("client_name") or "Unbenannte Anwendung")[:80]
    zugang = store.register_client(connection, name, sauber)
    store.log_event(connection, "OAuth-Client registriert",
                    detail=f"{name} — {sauber[0]}")
    return {
        "client_id": zugang["client_id"],
        "client_secret": zugang["client_secret"],
        # 0 = läuft nicht ab. Ein Secret, das ohne Vorwarnung ungültig wird,
        # reisst die Verbindung mitten im Betrieb ab.
        "client_secret_expires_at": 0,
        "client_id_issued_at": _epoch(),
        "client_name": name,
        "redirect_uris": sauber,
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "client_secret_post",
        "scope": DEFAULT_SCOPE,
    }


def _redirect_allowed(uri: str) -> bool:
    """https überall, http nur auf dem eigenen Rechner.

    Ein Client, der auf dem Gerät des Benutzers läuft (Claude Desktop),
    hört auf einem lokalen Port — dort gibt es kein Zertifikat und auch
    keinen Weg durchs Netz, auf dem jemand mithören könnte.
    """
    try:
        teile = urllib.parse.urlsplit(uri)
    except ValueError:
        return False
    if teile.fragment or not teile.netloc:
        return False
    if teile.scheme == "https":
        return True
    return teile.scheme == "http" and teile.hostname in ("localhost", "127.0.0.1", "::1")


# --------------------------------------------------------------------------
# /authorize — die Anfrage prüfen, bevor ein Mensch sie zu sehen bekommt
# --------------------------------------------------------------------------

def parse_authorize(connection, query: str, base: str, mcp_path: str) -> dict:
    felder = {k: v[0] for k, v in urllib.parse.parse_qs(query, keep_blank_values=True).items()}

    client_id = felder.get("client_id", "")
    client = store.client_by_id(connection, client_id) if client_id else None
    if client is None:
        # Unbekannter Client: NICHT weiterleiten. Wohin auch — die Adresse
        # in der Anfrage ist dann durch nichts gedeckt.
        raise OAuthError("invalid_client", "Dieser Client ist hier nicht registriert.",
                         redirectable=False)

    erlaubt = store.client_redirect_uris(client)
    redirect_uri = felder.get("redirect_uri", "")
    if not redirect_uri and len(erlaubt) == 1:
        redirect_uri = erlaubt[0]
    # Exakter Vergleich. Siehe Kopf der Datei, Punkt 2.
    if redirect_uri not in erlaubt:
        raise OAuthError("invalid_request",
                         "Die Rückadresse gehört nicht zu diesem Client.",
                         redirectable=False)

    anfrage = {
        "client": client,
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": felder.get("state", ""),
        "scope": _scope_or_default(felder.get("scope", "")),
        "challenge": felder.get("code_challenge", ""),
        "method": felder.get("code_challenge_method", ""),
        "resource": felder.get("resource", ""),
    }

    # Ab hier darf ein Fehler an die Rückadresse — sie ist geprüft.
    def zurueck(code: str, text: str) -> OAuthError:
        return OAuthError(code, text, redirect_uri=redirect_uri,
                          state=anfrage["state"])

    if felder.get("response_type") != "code":
        raise zurueck("unsupported_response_type",
                      "Dieser Server kennt nur response_type=code.")
    if not anfrage["challenge"]:
        raise zurueck("invalid_request", "code_challenge fehlt (PKCE ist Pflicht).")
    if anfrage["method"] != "S256":
        raise zurueck("invalid_request", "code_challenge_method muss S256 sein.")

    unsere = resource_url(base, mcp_path)
    if anfrage["resource"] and not _same_resource(anfrage["resource"], unsere):
        raise zurueck("invalid_target",
                      f"Dieser Server stellt nur Token für {unsere} aus.")
    anfrage["resource"] = unsere
    return anfrage


def _scope_or_default(wunsch: str) -> str:
    gewuenscht = [s for s in wunsch.split() if s in SCOPES]
    return " ".join(gewuenscht) if gewuenscht else DEFAULT_SCOPE


def _same_resource(gewuenscht: str, unsere: str) -> bool:
    """Vergleich ohne abschließenden Schrägstrich — sonst scheitert es an Kosmetik."""
    return gewuenscht.rstrip("/") == unsere.rstrip("/")


def error_redirect(anfrage_oder_uri, fehler: OAuthError, state: str = "") -> str:
    ziel = anfrage_oder_uri if isinstance(anfrage_oder_uri, str) \
        else anfrage_oder_uri["redirect_uri"]
    return _mit_parametern(ziel, {**fehler.payload(), "state": state})


def success_redirect(anfrage: dict, code: str) -> str:
    return _mit_parametern(anfrage["redirect_uri"],
                           {"code": code, "state": anfrage["state"]})


def _mit_parametern(uri: str, werte: dict) -> str:
    teile = urllib.parse.urlsplit(uri)
    vorhanden = urllib.parse.parse_qsl(teile.query, keep_blank_values=True)
    vorhanden += [(k, v) for k, v in werte.items() if v]
    return urllib.parse.urlunsplit(
        (teile.scheme, teile.netloc, teile.path,
         urllib.parse.urlencode(vorhanden), teile.fragment))


# --------------------------------------------------------------------------
# Der Bestätigungsbildschirm
# --------------------------------------------------------------------------

def consent_page(anfrage: dict, *, username: str, ticket: str, message: str = "") -> bytes:
    """Was fragt da an, und was darf es danach?

    Name UND Rückadresse stehen darauf. Der Name ist frei wählbar — wer
    sich „Claude" nennt, ist damit noch lange nicht Claude. Die Adresse
    dagegen ist die Stelle, an die der Code wirklich geht, und sie lässt
    sich nicht schönreden.
    """
    # Als Tabelle, nicht als Aufzaehlung: Der Bestand hat kein Stilbild fuer
    # <ul>, und eine ungestylte Liste faellt auf dieser Seite auf.
    rechte = "".join(
        sh.zeile("darf", esc(SCOPES[s])) for s in anfrage["scope"].split() if s in SCOPES)
    warnung = ""
    if "ads:write" in anfrage["scope"].split():
        warnung = ('<p class="note" style="margin:14px 0 0">Darunter ist das Recht, '
                   'Gebote und Budgets zu ändern — also Geld auszugeben. Die '
                   'Schutzgrenzen unter „Schutzgrenzen" gelten weiterhin.</p>')

    karte = sh.karte(
        esc(anfrage["client"]["name"] or "Unbenannte Anwendung"),
        f"""<table>
{sh.zeile("Rückadresse", f'<code>{esc(anfrage["redirect_uri"])}</code>',
          "Dorthin geht der Zugangscode. Kennst du diese Adresse nicht, brich ab.")}
{sh.zeile("Angemeldet als", esc(username))}
</table>
<p style="margin:18px 0 6px"><strong>Diese Anwendung darf dann:</strong></p>
<table>{rechte}</table>{warnung}""",
        art="akzent")

    return ui.schmale_seite(
        "Zugriff erlauben?",
        "Eine Anwendung möchte in deinem Namen auf die Google-Ads-Werkzeuge zugreifen",
        f"""{karte}
<form method="post" action="/authorize" style="margin-top:18px">
<input type="hidden" name="ticket" value="{esc(ticket)}">
<button class="breit" type="submit" name="antwort" value="ja">Erlauben</button>
<button class="quiet breit" type="submit" name="antwort" value="nein"
        style="margin-top:10px">Ablehnen</button>
</form>""",
        oben=(f'<div class="warnung"><span>{esc(message)}</span></div>' if message else ""),
        fuss='<span class="note" style="font-size:.82rem">Erteilte Zugriffe stehen '
             'unter „Konto" und lassen sich dort jederzeit wieder entziehen.</span>')


# --------------------------------------------------------------------------
# /token
# --------------------------------------------------------------------------

def exchange(connection, felder: dict, *, base: str, mcp_path: str,
             basic: tuple[str, str] | None = None) -> dict:
    """Code gegen Token, oder Erneuerungstoken gegen ein neues Paar."""
    art = felder.get("grant_type", "")
    if art == "authorization_code":
        return _exchange_code(connection, felder, base, mcp_path, basic)
    if art == "refresh_token":
        return _exchange_refresh(connection, felder, basic)
    raise OAuthError("unsupported_grant_type",
                     "Dieser Server kennt authorization_code und refresh_token.",
                     redirectable=False)


def _client_from(connection, felder: dict, basic: tuple[str, str] | None):
    """Client-ID und, wo vorhanden, das Secret — aus Formular oder Basic-Kopf."""
    client_id = felder.get("client_id", "")
    secret = felder.get("client_secret", "")
    if basic:
        client_id = client_id or basic[0]
        secret = secret or basic[1]
    client = store.client_by_id(connection, client_id) if client_id else None
    if client is None:
        raise OAuthError("invalid_client", "Unbekannter Client.",
                         redirectable=False, status=401)
    # Ein Secret haben alle hier registrierten Clients (die Registrierung
    # vergibt immer eines). Ein Client, der keines mitschickt, ist damit
    # nicht der, für den er sich ausgibt.
    if not secret or not store.client_secret_matches(client, secret):
        raise OAuthError("invalid_client", "Client-Secret stimmt nicht.",
                         redirectable=False, status=401)
    return client


def _exchange_code(connection, felder, base, mcp_path, basic) -> dict:
    client = _client_from(connection, felder, basic)
    code = felder.get("code", "")
    if not code:
        raise OAuthError("invalid_request", "code fehlt.", redirectable=False)

    zeile = store.spend_code(connection, code)
    if zeile is None:
        raise OAuthError("invalid_grant", "Der Code ist unbekannt oder abgelaufen.",
                         redirectable=False)
    if zeile["client_id"] != client["client_id"]:
        raise OAuthError("invalid_grant", "Der Code gehört zu einem anderen Client.",
                         redirectable=False)
    if zeile["redirect_uri"] != felder.get("redirect_uri", zeile["redirect_uri"]):
        raise OAuthError("invalid_grant",
                         "Die Rückadresse weicht von der beim Anmelden ab.",
                         redirectable=False)

    verifier = felder.get("code_verifier", "")
    if not verifier or not verify_pkce(verifier, zeile["challenge"]):
        raise OAuthError("invalid_grant", "code_verifier passt nicht zum code_challenge.",
                         redirectable=False)

    gewuenscht = felder.get("resource", "")
    if gewuenscht and not _same_resource(gewuenscht, zeile["resource"]):
        raise OAuthError("invalid_target", "Andere Ressource als beim Anmelden.",
                         redirectable=False)

    store.note_client_use(connection, client["client_id"])
    return _paar(connection, client_id=client["client_id"], user_id=zeile["user_id"],
                 scope=zeile["scope"], resource=zeile["resource"])


def _exchange_refresh(connection, felder, basic) -> dict:
    client = _client_from(connection, felder, basic)
    zeile = store.spend_refresh(connection, felder.get("refresh_token", ""))
    if zeile is None or zeile["client_id"] != client["client_id"]:
        raise OAuthError("invalid_grant",
                         "Das Erneuerungstoken ist unbekannt, abgelaufen oder "
                         "gehört zu einem anderen Client.", redirectable=False)
    # Enger werden darf man, weiter nicht.
    wunsch = felder.get("scope", "")
    scope = zeile["scope"]
    if wunsch:
        enger = [s for s in wunsch.split() if s in scope.split()]
        scope = " ".join(enger) if enger else scope
    store.note_client_use(connection, client["client_id"])
    return _paar(connection, client_id=client["client_id"], user_id=zeile["user_id"],
                 scope=scope, resource=zeile["resource"])


def _paar(connection, *, client_id: str, user_id: int, scope: str, resource: str) -> dict:
    access = store.issue_token(connection, kind="access", client_id=client_id,
                               user_id=user_id, scope=scope, resource=resource)
    refresh = store.issue_token(connection, kind="refresh", client_id=client_id,
                                user_id=user_id, scope=scope, resource=resource)
    return {
        "access_token": access,
        "token_type": "Bearer",
        "expires_in": store.OAUTH_ACCESS_HOURS * 3600,
        "refresh_token": refresh,
        "scope": scope,
    }


def verify_pkce(verifier: str, challenge: str) -> bool:
    digest = hashlib.sha256(verifier.encode("ascii", "ignore")).digest()
    errechnet = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return secrets.compare_digest(errechnet, challenge)


def basic_auth(header: str) -> tuple[str, str] | None:
    """`Authorization: Basic …` am Token-Endpunkt, urldecodiert wie im RFC."""
    if not header.lower().startswith("basic "):
        return None
    try:
        roh = base64.b64decode(header[6:].strip() + "==").decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None
    if ":" not in roh:
        return None
    name, _, wort = roh.partition(":")
    return (urllib.parse.unquote_plus(name), urllib.parse.unquote_plus(wort))


# --------------------------------------------------------------------------
# Was ein Token am MCP-Endpunkt darf
# --------------------------------------------------------------------------

def token_for_resource(connection, presented: str, resource: str):
    """Das Zugangstoken — aber nur, wenn es für DIESEN Server ausgestellt wurde."""
    zeile = store.read_token(connection, presented, "access")
    if zeile is None:
        return None
    if zeile["resource"] and not _same_resource(zeile["resource"], resource):
        return None
    return zeile


def write_refused(message: dict, scope: str) -> str:
    """'' wenn erlaubt, sonst der Name des Werkzeugs, das fehlt.

    Geprüft wird im HTTP-Teil, bevor die Nachricht den MCP-Server erreicht:
    Der wird auch über stdio benutzt, wo es keine Token und keine Scopes
    gibt, und soll von beidem nichts wissen müssen.
    """
    if "ads:write" in scope.split():
        return ""
    if not isinstance(message, dict) or message.get("method") != "tools/call":
        return ""
    name = ((message.get("params") or {}).get("name") or "")
    return name if name in WRITE_TOOLS else ""


def _epoch() -> int:
    import time
    return int(time.time())
