#!/usr/bin/env python3
"""Serves the same Google Ads tools over HTTP, for Claude in the browser.

google-ads-mcp.py speaks stdio, which is what Claude Code and the Claude
desktop app launch. Claude on the web and on a phone cannot launch a local
process — it reaches a URL. This script wraps the identical tool handlers
in a Streamable HTTP endpoint so the same thirteen tools appear in
claude.ai as a custom connector.

Nothing about the tools changes. The guardrails, the dry runs and the
change log are the ones in google_ads_client.py, because this is the same
code with a different door.

THERE ARE TWO DOORS ON THE INTERNET, and they are locked differently
because the two callers can do different things.

    /mcp      for claude.ai. A bearer token compared in constant time,
              optionally only from Anthropic's published egress range, and
              a body limit that refuses an oversized request unread. No
              sign-in form: a connector cannot fill one in.

    /setup    for a person. A portal account with a password, an optional
              second factor, a session cookie that is HttpOnly and
              SameSite, a lockout after repeated failures, and a refusal
              of any form that did not come from this server. See
              portal_store.py.

Neither key opens the other door. Changing the bearer token does not touch
the accounts, and changing a password does not disturb the connector.

The address filter reads X-Forwarded-For only when the connection itself
comes from a trusted proxy address — otherwise anyone could claim to be
Anthropic in a header and walk past the filter.

A missing or wrong token gets a 401 and nothing else — no tool list, no
hint about what is behind it.

TLS IS NOT THIS SCRIPT'S JOB. Claude requires https, and a certificate
belongs to a reverse proxy that already renews it (nginx, Caddy, Traefik).
Run this on localhost, put the proxy in front. --tls-cert exists for the
case where there is no proxy, and it is the second choice.

    google-ads-http.py --token-file ~/.config/neo-google-ads/http-token
    google-ads-http.py --port 8788 --anthropic-only
    google-ads-http.py --new-token           print a fresh token and exit

No dependencies beyond the standard library.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime
import getpass
import hmac
import http.cookies
import http.server
import ipaddress
import json
import os
import pathlib
import secrets
import socketserver
import ssl
import sys
import urllib.parse
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import importlib.util  # noqa: E402


def load_mcp():
    """Imports the stdio server despite the hyphen in its file name."""
    path = pathlib.Path(__file__).parent / "google-ads-mcp.py"
    spec = importlib.util.spec_from_file_location("google_ads_mcp", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mcp = load_mcp()
import google_ads_setup as setup  # noqa: E402
import portal_pages as portal  # noqa: E402
import portal_store as store
import portal_webauthn as webauthn  # noqa: E402
import portal_totp as totp  # noqa: E402

# Anthropic publishes the range its servers call out from. Restricting to it
# turns a guessed token into a useless one, because the guess has to come
# from the right address as well.
ANTHROPIC_EGRESS = ipaddress.ip_network("160.79.104.0/21")

MAX_BODY = 1_000_000          # A JSON-RPC call for this API never approaches this.
TOKEN_FILE = mcp.CHANGE_LOG.parent / "http-token"


def load_token(path: pathlib.Path) -> str:
    """Reads the token, creating one on the first start.

    A container that refuses to start because nobody created a token yet
    is a container nobody can create a token in. So the first start makes
    one and prints it. Every later start finds it in the mounted volume
    and leaves it alone — the password does not change under the operator
    on each deployment.
    """
    if not path.exists():
        token = write_token(path)
        print(f"No token at {path} — created one.", file=sys.stderr)
        print(f"  token: {token}", file=sys.stderr)
        return token
    token = path.read_text(encoding="utf-8").strip()
    if len(token) < 32:
        raise SystemExit(f"The token in {path} is shorter than 32 characters. "
                         "Delete it to have a new one generated, or write a longer one.")
    return token


def write_token(path: pathlib.Path) -> str:
    token = secrets.token_urlsafe(48)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(token + "\n", encoding="utf-8")
    os.chmod(path, 0o600)
    return token


class Handler(http.server.BaseHTTPRequestHandler):
    """One request. Authenticate, hand to the JSON-RPC layer, answer."""

    protocol_version = "HTTP/1.1"
    server_version = "neo-google-ads/1.2"
    sys_version = ""            # Do not advertise the Python version.

    token = ""
    anthropic_only = False
    path_prefix = "/mcp"
    setup_enabled = False
    token_path = ""
    database_path = None
    public_url = ""
    # A reverse proxy sits on a private address: the loopback interface, or
    # a container network. Nothing on the public internet is trusted to
    # describe who it is forwarding for.
    trusted_proxies = (
        ipaddress.ip_network("127.0.0.0/8"),
        ipaddress.ip_network("::1/128"),
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
        ipaddress.ip_network("fd00::/8"),
    )

    # -- helpers -----------------------------------------------------------

    def _client_ip(self):
        """The caller's address — trusting X-Forwarded-For only from a proxy.

        A header can say anything. If the address filter believed every
        X-Forwarded-For it saw, an attacker would simply claim to be
        Anthropic and the filter would be decoration. So the header counts
        only when the connection itself comes from an address in
        trusted_proxies; from anywhere else the socket address wins.
        """
        try:
            direct = ipaddress.ip_address(self.client_address[0])
        except ValueError:
            return None

        forwarded = self.headers.get("X-Forwarded-For", "")
        if not forwarded:
            return direct
        if not any(direct in network for network in self.trusted_proxies):
            self.log_line(f"ignoring X-Forwarded-For from untrusted {direct}")
            return direct
        try:
            return ipaddress.ip_address(forwarded.split(",")[0].strip())
        except ValueError:
            return direct

    def _send(self, status: int, payload: dict | None = None, *, headers: dict | None = None):
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8") \
            if payload is not None else b""
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _authorized(self) -> bool:
        """Address first, then token — both in constant time where it matters.

        Only the MCP endpoint goes through here. The portal pages have
        their own sign-in and deliberately skip the address filter: the
        person opening them sits at a desk, not in Anthropic's network,
        and --anthropic-only would lock them out of their own server.
        """
        if self.anthropic_only:
            address = self._client_ip()
            if address is None or address not in ANTHROPIC_EGRESS:
                self.log_line(f"refused: address {address} outside the Anthropic range")
                return False
        header = self.headers.get("Authorization", "")
        presented = header[7:].strip() if header.lower().startswith("bearer ") else ""
        if not presented:
            presented = self.headers.get("X-Api-Key", "").strip()
        if not presented or not hmac.compare_digest(presented, self.token):
            self.log_line("refused: bad or missing token")
            return False
        return True

    # -- the portal's own sign-in ------------------------------------------

    def _session_token(self) -> str:
        jar = http.cookies.SimpleCookie()
        try:
            jar.load(self.headers.get("Cookie", ""))
        except http.cookies.CookieError:
            return ""
        biscuit = jar.get(store.SESSION_COOKIE)
        return biscuit.value if biscuit else ""

    def _cookie_header(self, token: str = "", *, clear: bool = False) -> str:
        """HttpOnly so no script can read it, Lax so Google may redirect back."""
        secure = "; Secure" if self._https() else ""
        if clear:
            return (f"{store.SESSION_COOKIE}=; Path=/; Max-Age=0; HttpOnly; "
                    f"SameSite=Lax{secure}")
        return (f"{store.SESSION_COOKIE}={token}; Path=/; "
                f"Max-Age={store.SESSION_HOURS * 3600}; HttpOnly; SameSite=Lax{secure}")

    @staticmethod
    def _host_of(url: str) -> str:
        """The host of a URL or a Host header, lower case, default port dropped."""
        raw = url.split(",")[0].strip()
        parsed = urllib.parse.urlsplit(raw if "//" in raw else "//" + raw)
        host = (parsed.hostname or "").lower()
        try:
            port = parsed.port
        except ValueError:
            port = None
        return host if port in (None, 80, 443) else f"{host}:{port}"

    def _own_host(self) -> str:
        """The name this request came in under, as the browser used it.

        Deliberately NOT the pinned --public-url. That one exists to fix
        the scheme for the redirect URI; using it here would mean that
        reaching the portal under any other name — a second hostname, the
        address itself, a tunnel — refuses every form with a message about
        an attack. It would also buy nothing: a page on another site
        cannot make the browser send this host as its Origin either way.
        """
        return self._host_of(self.headers.get("X-Forwarded-Host")
                             or self.headers.get("Host") or "")

    def _scheme(self) -> str:
        """Whether the browser reached us over TLS — asked six ways.

        A reverse proxy is supposed to say so in X-Forwarded-Proto, and
        most do. Plesk's Docker proxy rules do not, and getting this wrong
        is not cosmetic: the redirect URI handed to Google would read http,
        and the session cookie would lose its Secure flag.
        """
        if self.public_url:
            return urllib.parse.urlsplit(self.public_url).scheme or "http"
        forwarded = (self.headers.get("X-Forwarded-Proto")
                     or self.headers.get("X-Forwarded-Scheme") or "")
        first = forwarded.split(",")[0].strip().lower()
        if first in ("http", "https"):
            return first
        if (self.headers.get("X-Forwarded-Ssl") or "").strip().lower() == "on":
            return "https"
        if (self.headers.get("X-Forwarded-Port") or "").strip() == "443":
            return "https"
        if isinstance(getattr(self.connection, "context", None), ssl.SSLContext):
            return "https"
        # Last resort: the browser itself says how it reached the proxy.
        for header in ("Origin", "Referer"):
            value = self.headers.get(header) or ""
            if value.lower().startswith("https://") \
                    and self._host_of(value) == self._own_host():
                return "https"
        return "http"

    def _pinned_host(self) -> str:
        """The host from --public-url, when one was pinned."""
        return self._host_of(self.public_url) if self.public_url else ""

    def _https(self) -> bool:
        return self._scheme() == "https"

    def _same_origin(self) -> bool:
        """A cross-site POST is refused outright.

        Compared by HOST, not by full origin. The scheme is whatever the
        proxy in front chose to mention, and a proxy that forgets
        X-Forwarded-Proto would otherwise make every form on the site look
        like an attack — which is exactly what happened behind Plesk. The
        host is the part that decides whether this is the same site, and
        the part an attacker cannot fake in a browser.
        """
        mine = self._own_host()
        if not mine:
            return False
        for header in ("Origin", "Referer"):
            value = self.headers.get(header)
            if value and value.strip().lower() != "null":
                return self._host_of(value) == mine
        return False        # Neither header: not a browser form. Refuse.

    def _signed_in(self, connection):
        """(user, session) when signed in and past the second factor."""
        row = store.read_session(connection, self._session_token())
        if row is None:
            return None, None
        user = store.user_by_id(connection, row["user_id"])
        if user is None:
            return None, None
        return user, row

    def _base_url(self) -> str:
        """The address a browser reached this server on, as Google must see it."""
        if self.public_url:
            return self.public_url.rstrip("/")
        return f"{self._scheme()}://{self._own_host()}".rstrip("/")

    def _send_html(self, body: bytes, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        # same-origin, NOT no-referrer. With no-referrer a browser drops the
        # Referer and serialises Origin as the string "null" on the form
        # POST that follows — which made the same-site check refuse every
        # sign-in. same-origin still sends nothing to a third party, and
        # keeps the header the check needs on our own forms.
        self.send_header("Referrer-Policy", "same-origin")
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, where: str, *, cookie: str = ""):
        self.send_response(303)
        self.send_header("Location", where)
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _read_form(self) -> dict:
        try:
            length = min(int(self.headers.get("Content-Length") or 0), 100_000)
        except ValueError:
            return {}
        raw = self.rfile.read(length).decode("utf-8", "replace") if length else ""
        return urllib.parse.parse_qs(raw)

    def _unauthorized(self):
        # The 401 carries the WWW-Authenticate header the MCP spec asks for,
        # so a client that wants to negotiate knows what it is looking at.
        self._send(401, {"error": "unauthorized"},
                   headers={"WWW-Authenticate": 'Bearer realm="neo-google-ads"'})

    def log_line(self, text: str) -> None:
        stamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
        print(f"{stamp} {self.client_address[0]} {text}", file=sys.stderr, flush=True)

    def log_message(self, *args):
        pass  # Replaced by log_line, so the access log stays one line per call.

    # -- verbs -------------------------------------------------------------

    def do_GET(self):  # noqa: N802
        """Health check and, when switched on, the management pages."""
        path = urllib.parse.urlparse(self.path).path.rstrip("/") or "/"
        if path in ("/health", "/healthz"):
            self._send(200, {"status": "ok", "server": mcp.SERVER_NAME,
                             "version": mcp.SERVER_VERSION,
                             "protocol_versions": list(mcp.PROTOCOL_VERSIONS)})
            return

        # Die oeffentlichen Seiten zuerst, ohne jede Anmeldung. Googles
        # Pruefung des Brandings kommt sonst nicht an die Startseite und
        # weist die Anwendung ab — genau das ist passiert.
        if self.setup_enabled and path == "/":
            self.log_line("public: /")
            try:
                self._send_html(setup.startseite(self._base_url()))
            except Exception as exc:  # noqa: BLE001
                print(traceback.format_exc(), file=sys.stderr)
                self._send_html(setup.result_page(False, f"{type(exc).__name__}: {exc}"), 500)
            return

        if self.setup_enabled and self._is_portal_path(path):
            self._portal_request(path, "GET")
            return

        self._send(404, {"error": "not found"})

    # -- portal routing ----------------------------------------------------

    # Was ein Fremder sehen darf. Der Passkey-Weg gehoert dazu: er ersetzt
    # gerade das Kennwort, kann also nicht hinter der Anmeldung liegen.
    OPEN_PATHS = ("/login", "/login/code", "/login/cancel",
                  "/login/passkey", "/login/passkey/start")

    # Die Wege der Konsole. Englisch wie jeder technische Name hier; was
    # darauf steht, ist deutsch.
    PORTAL_ROOTS = ("/dashboard", "/setup", "/guardrails", "/check", "/account")

    @staticmethod
    def _is_portal_path(path: str) -> bool:
        if path in Handler.OPEN_PATHS or path == "/logout":
            return True
        return any(path == root or path.startswith(root + "/")
                   for root in Handler.PORTAL_ROOTS)

    def _portal_request(self, path: str, verb: str) -> None:
        """Every page behind the sign-in goes through here, in one place."""
        if verb == "POST" and not self._same_origin():
            woher = self.headers.get("Origin") or self.headers.get("Referer") or "(nichts)"
            self.log_line(f"portal: cross-site POST refused for {path}: "
                          f"{woher} against host {self._own_host() or '(none)'}")
            self._send_html(setup.result_page(
                False, f"Dieses Formular kam nicht von dieser Seite. Der Browser "
                       f"nennt als Herkunft {self._host_of(woher) or 'nichts'}, "
                       f"dieser Server heißt {self._own_host() or '(unbekannt)'}. "
                       f"Stimmt das nicht überein, fehlt dem Reverse Proxy der "
                       f"Host-Kopf — oder GOOGLE_ADS_PUBLIC_URL steht falsch."), 403)
            return
        try:
            with store.open_database(self.database_path) as connection:
                user, session = self._signed_in(connection)
                if user is not None and session["stage"] != "full":
                    # Password accepted, second factor still outstanding.
                    if path in ("/login/code", "/login/cancel"):
                        self._portal_open(connection, path, verb, user, session)
                        return
                    self._redirect("/login/code")
                    return
                if user is None:
                    if path in self.OPEN_PATHS:
                        self._portal_open(connection, path, verb, None, None)
                        return
                    self._redirect("/login")
                    return
                if user["must_change"] and path not in ("/account/password", "/logout"):
                    self._send_html(portal.change_password_page(username=user["username"]))
                    return
                setup.set_viewer(user["username"],
                                 two_factor=bool(user["totp_confirmed"]))
                setup.set_host(self._own_host())
                self.log_line(f"portal: {verb} {path} as {user['username']}")
                self._portal_closed(connection, path, verb, user, session)
        except Exception as exc:  # noqa: BLE001
            print(traceback.format_exc(), file=sys.stderr)
            self._send_html(setup.result_page(False, f"{type(exc).__name__}: {exc}"), 500)

    def _portal_open(self, connection, path, verb, user, session) -> None:
        """The pages a stranger may see: sign in, and the second factor."""
        address = str(self._client_ip() or "")
        if path == "/login/cancel":
            if session is not None:
                store.end_session(connection, self._session_token())
            self._redirect("/login", cookie=self._cookie_header(clear=True))
            return
        if path == "/login" and verb == "GET":
            self._send_html(portal.login_page(
                first_run=store.count_users(connection) == 0,
                passkeys=store.count_passkeys(connection) > 0))
            return
        if path == "/login" and verb == "POST":
            self._sign_in(connection, address)
            return
        if path == "/login/passkey/start" and verb == "POST":
            self._passkey_challenge(connection)
            return
        if path == "/login/passkey" and verb == "POST":
            self._passkey_sign_in(connection, address)
            return
        if path == "/login/code" and verb == "GET":
            self._send_html(portal.second_factor_page(
                name=user["username"] if user else ""))
            return
        if path == "/login/code" and verb == "POST":
            self._second_factor(connection, user, address)
            return
        self._redirect("/login")

    # -- passkeys ----------------------------------------------------------
    #
    # Der Name des Servers, wie WebAuthn ihn meint: rp_id ist der Rechner
    # ohne Anschluss, die Herkunft ist, was der Browser in clientDataJSON
    # schreibt. Beides kommt aus derselben Quelle wie die Herkunftspruefung
    # der Formulare, damit nicht zwei Stellen verschieden raten.

    def _rp_id(self) -> str:
        return self._own_host().split(":")[0]

    def _origin(self) -> str:
        return f"{self._scheme()}://{self._own_host()}"

    def _send_json_or_refuse(self, payload: dict) -> None:
        """The browser asks for this with fetch, so it gets JSON, not a page."""
        self._send(200, payload)

    def _passkey_challenge(self, connection) -> None:
        """A fresh one-shot random string for signing in with a passkey."""
        if store.count_passkeys(connection) == 0:
            self._send(404, {"error": "no passkeys"})
            return
        challenge = store.new_challenge(connection, "login")
        # Keine allowCredentials: wer sich anmelden will, ist noch niemand.
        # Eine Liste hier wuerde jedem Besucher verraten, welche Geraete
        # dieses Portal kennt.
        self._send_json_or_refuse(webauthn.anmeldung_beginnen(
            challenge=challenge, rp_id=self._rp_id()))

    def _passkey_sign_in(self, connection, address: str) -> None:
        form = self._read_form()
        einzeln = lambda name: (form.get(name) or [""])[0]  # noqa: E731
        try:
            daten = webauthn.b64url_decode(einzeln("daten"))
            challenge = json.loads(daten.decode("utf-8")).get("challenge", "")
            gut, _ = store.spend_challenge(connection, challenge, "login")
            if not gut:
                raise webauthn.PasskeyError("Die Anfrage ist abgelaufen. "
                                            "Bitte noch einmal.")
            schluessel = store.passkey_by_credential(connection, einzeln("kennung"))
            if schluessel is None:
                raise webauthn.PasskeyError("Dieser Passkey ist hier nicht "
                                            "hinterlegt.")
            zaehler = webauthn.anmeldung_pruefen(
                client_daten=daten,
                authenticator=webauthn.b64url_decode(einzeln("authenticator")),
                signatur=webauthn.b64url_decode(einzeln("signatur")),
                gespeicherter_schluessel=schluessel["public_key"],
                challenge=challenge, herkunft=self._origin(),
                rp_id=self._rp_id(), zaehler=schluessel["sign_count"])
        except (webauthn.PasskeyError, ValueError, UnicodeDecodeError) as exc:
            meldung = str(exc) if isinstance(exc, webauthn.PasskeyError) else (
                "Die Antwort des Browsers war unlesbar.")
            store.record_attempt(connection, address, "(passkey)")
            store.log_event(connection, "passkey refused", address=address,
                            detail=meldung[:120])
            self.log_line(f"portal: passkey refused ({meldung})")
            self._send_html(portal.login_page(meldung, passkeys=True), 401)
            return

        user = store.user_by_id(connection, schluessel["user_id"])
        if user is None:
            self._send_html(portal.login_page(
                "Zu diesem Passkey gibt es kein Konto mehr.", passkeys=True), 401)
            return
        store.note_passkey_use(connection, schluessel["id"], zaehler)
        store.clear_attempts(connection, address, user["username"])
        # Ein Passkey ist Besitz und Merkmal in einem Schritt. Er ersetzt
        # damit auch den zweiten Faktor — sonst waere er umstaendlicher als
        # das Kennwort, das er ablosen soll.
        token = store.start_session(connection, user["id"], address=address,
                                    agent=self.headers.get("User-Agent", ""),
                                    stage="full")
        store.note_login(connection, user["id"], address)
        store.log_event(connection, "signed in with a passkey",
                        username=user["username"], address=address,
                        detail=schluessel["name"])
        self.log_line(f"portal: {user['username']} signed in with a passkey")
        self._redirect("/account" if user["must_change"] else "/dashboard",
                       cookie=self._cookie_header(token))

    def _sign_in(self, connection, address: str) -> None:
        form = self._read_form()
        name = (form.get("benutzer") or [""])[0].strip()
        password = (form.get("kennwort") or [""])[0]
        store.sweep(connection)

        warten = store.locked_out(connection, address, name)
        if warten:
            self.log_line(f"portal: locked out {name or '(no name)'} from {address}")
            self._send_html(portal.login_page(
                f"Zu viele Fehlversuche. Noch {warten} Minuten warten.", name), 429)
            return

        user = store.find_user(connection, name)
        if user is None and "@" in name:
            user = connection.execute(
                "SELECT * FROM users WHERE email = ? COLLATE NOCASE", (name,)).fetchone()
        # The same answer either way: a wrong name and a wrong password must
        # not be distinguishable, or the form becomes a name directory.
        if user is None or not store.verify_password(user["password_hash"], password):
            store.record_attempt(connection, address, name)
            store.log_event(connection, "sign-in refused", username=name, address=address)
            self.log_line(f"portal: sign-in refused for {name or '(no name)'}")
            self._send_html(portal.login_page(
                "Benutzername oder Kennwort stimmt nicht.", name), 401)
            return

        store.clear_attempts(connection, address, name)
        zwei = bool(user["totp_confirmed"])
        token = store.start_session(connection, user["id"], address=address,
                                    agent=self.headers.get("User-Agent", ""),
                                    stage="totp" if zwei else "full")
        if zwei:
            store.log_event(connection, "password accepted, second factor pending",
                            username=user["username"], address=address)
            self._redirect("/login/code", cookie=self._cookie_header(token))
            return
        store.note_login(connection, user["id"], address)
        store.log_event(connection, "signed in", username=user["username"], address=address)
        self.log_line(f"portal: {user['username']} signed in")
        self._redirect("/account" if user["must_change"] else "/dashboard",
                       cookie=self._cookie_header(token))

    def _second_factor(self, connection, user, address: str) -> None:
        if user is None:
            self._redirect("/login")
            return
        presented = self._code_from_form(self._read_form())
        warten = store.locked_out(connection, address, user["username"])
        if warten:
            self._send_html(portal.second_factor_page(
                f"Zu viele Fehlversuche. Noch {warten} Minuten warten.",
                name=user["username"]), 429)
            return

        ok, step = totp.check(user["totp_secret"], presented,
                              last_step=user["totp_last_step"])
        if ok:
            store.note_totp_step(connection, user["id"], step)
        elif store.spend_recovery_code(connection, user["id"], presented):
            ok = True
            store.log_event(connection, "recovery code used",
                            username=user["username"], address=address,
                            detail=f"{store.recovery_left(connection, user['id'])} left")
            self.log_line(f"portal: {user['username']} used a recovery code")
        if not ok:
            store.record_attempt(connection, address, user["username"])
            store.log_event(connection, "second factor refused",
                            username=user["username"], address=address)
            self._send_html(portal.second_factor_page(
                "Der Code stimmt nicht — oder er wurde schon verwendet.",
                name=user["username"]), 401)
            return

        store.clear_attempts(connection, address, user["username"])
        store.promote_session(connection, self._session_token())
        store.note_login(connection, user["id"], address)
        store.log_event(connection, "signed in with second factor",
                        username=user["username"], address=address)
        self.log_line(f"portal: {user['username']} signed in (2FA)")
        self._redirect("/dashboard")

    def _portal_closed(self, connection, path, verb, user, session) -> None:
        """Everything that needs a signed-in person."""
        address = str(self._client_ip() or "")
        if path == "/logout":
            store.end_session(connection, self._session_token())
            store.log_event(connection, "signed out", username=user["username"],
                            address=address)
            self._redirect("/login", cookie=self._cookie_header(clear=True))
            return
        if path in self.OPEN_PATHS:
            # Schon angemeldet. Die Anmeldeseite noch einmal aufzurufen ist
            # kein Fehler, sondern ein Lesezeichen — also weiterleiten,
            # statt eine 404 zu zeigen.
            self._redirect("/dashboard")
            return
        if path == "/account" or path.startswith("/account/"):
            self._account(connection, path, verb, user, session, address)
            return
        if verb == "GET":
            self._setup_get(path)
        else:
            self._setup_post(path)

    # -- the account pages -------------------------------------------------

    def _account(self, connection, path, verb, user, session, address) -> None:
        def zeigen(message="", trouble="", ueberlagerung=""):
            frisch = store.user_by_id(connection, user["id"])
            self._send_html(portal.account_page(
                frisch, store.sessions_for(connection, user["id"]),
                recovery_left=store.recovery_left(connection, user["id"]),
                message=message, trouble=trouble,
                passkeys=store.passkeys_for(connection, user["id"]),
                ueberlagerung=ueberlagerung,
                current_token_hash=session["token_hash"]))

        if path == "/account" and verb == "GET":
            zeigen()
            return

        form = self._read_form() if verb == "POST" else {}

        if path == "/account/name" and verb == "POST":
            name = (form.get("benutzer") or [""])[0].strip()
            email = (form.get("email") or [""])[0].strip()
            if not name:
                zeigen(trouble="Ein Benutzername muss dastehen.")
                return
            andere = store.find_user(connection, name)
            if andere is not None and andere["id"] != user["id"]:
                zeigen(trouble="Diesen Benutzernamen gibt es schon.")
                return
            store.set_identity(connection, user["id"], name, email)
            store.log_event(connection, "name or e-mail changed",
                            username=name, address=address,
                            detail=f"was {user['username']}")
            self.log_line(f"portal: {user['username']} is now {name}")
            zeigen("Gespeichert.")
            return

        if path == "/account/password" and verb == "POST":
            self._change_password(connection, user, form, address, zeigen)
            return

        if path == "/account/sessions" and verb == "POST":
            beendet = store.end_all_sessions(connection, user["id"],
                                             except_token=self._session_token())
            store.log_event(connection, "other sessions ended",
                            username=user["username"], address=address,
                            detail=f"{beendet}")
            zeigen(f"{beendet} andere Sitzung(en) beendet."
                   if beendet else "Es gab keine anderen Sitzungen.")
            return

        if path == "/account/passkeys/start" and verb == "POST":
            vorhandene = [k["credential_id"]
                          for k in store.passkeys_for(connection, user["id"])]
            self._send(200, webauthn.registrierung_beginnen(
                challenge=store.new_challenge(connection, "register", user["id"]),
                rp_id=self._rp_id(), marke=setup.MARKE,
                benutzer_kennung=str(user["id"]), benutzername=user["username"],
                vorhandene=vorhandene))
            return

        if path == "/account/passkeys" and verb == "POST":
            self._add_passkey(connection, user, form, address, zeigen)
            return

        if path == "/account/passkeys/delete" and verb == "POST":
            kennung = (form.get("kennung") or [""])[0]
            if store.remove_passkey(connection, user["id"], kennung):
                store.log_event(connection, "passkey removed",
                                username=user["username"], address=address)
                self.log_line(f"portal: {user['username']} removed a passkey")
                zeigen("Passkey entfernt.")
            else:
                zeigen(trouble="Diesen Passkey gibt es hier nicht.")
            return

        if path == "/account/2fa" and verb == "GET":
            if user["totp_confirmed"]:
                zeigen(trouble="Zwei-Faktor ist bereits eingeschaltet.")
                return
            secret = totp.new_secret()
            store.begin_totp(connection, user["id"], secret)
            uri = totp.provisioning_uri(secret, user["username"],
                                        f"{setup.MARKE} ({self._host_name()})")
            zeigen(ueberlagerung=portal.two_factor_overlay(secret, uri))
            return

        if path == "/account/2fa" and verb == "POST":
            self._confirm_two_factor(connection, user, form, address, zeigen)
            return

        if path == "/account/2fa/off" and verb == "POST":
            store.disable_totp(connection, user["id"])
            store.log_event(connection, "second factor switched off",
                            username=user["username"], address=address)
            self.log_line(f"portal: {user['username']} switched 2FA off")
            zeigen("Zwei-Faktor ist aus. Das Kennwort allein öffnet diese Seite jetzt.")
            return

        if path == "/account/2fa/new" and verb == "POST":
            if not user["totp_confirmed"]:
                zeigen(trouble="Zwei-Faktor ist nicht eingeschaltet.")
                return
            codes = totp.recovery_codes(store.RECOVERY_COUNT)
            store.confirm_totp(connection, user["id"], user["totp_last_step"], codes)
            store.log_event(connection, "recovery codes replaced",
                            username=user["username"], address=address)
            self._send_html(portal.recovery_page(codes, username=user["username"],
                                                 neu=True))
            return

        self._send_html(setup.result_page(False, "Diese Seite gibt es nicht."), 404)

    def _add_passkey(self, connection, user, form, address, zeigen) -> None:
        einzeln = lambda name: (form.get(name) or [""])[0]  # noqa: E731
        try:
            daten = webauthn.b64url_decode(einzeln("daten"))
            challenge = json.loads(daten.decode("utf-8")).get("challenge", "")
            gut, wer = store.spend_challenge(connection, challenge, "register")
            if not gut or wer != user["id"]:
                raise webauthn.PasskeyError("Die Anfrage ist abgelaufen. "
                                            "Bitte noch einmal.")
            kennung, schluessel, zaehler = webauthn.registrierung_pruefen(
                client_daten=daten,
                zeugnis=webauthn.b64url_decode(einzeln("zeugnis")),
                challenge=challenge, herkunft=self._origin(), rp_id=self._rp_id())
        except (webauthn.PasskeyError, ValueError, UnicodeDecodeError) as exc:
            meldung = str(exc) if isinstance(exc, webauthn.PasskeyError) else (
                "Die Antwort des Browsers war unlesbar.")
            self.log_line(f"portal: passkey not stored ({meldung})")
            zeigen(trouble=meldung)
            return
        if store.passkey_by_credential(connection, kennung) is not None:
            zeigen(trouble="Dieses Gerät ist schon hinterlegt.")
            return
        store.add_passkey(connection, user["id"], kennung, schluessel,
                          einzeln("name").strip(), zaehler)
        store.log_event(connection, "passkey added", username=user["username"],
                        address=address, detail=einzeln("name")[:60])
        self.log_line(f"portal: {user['username']} added a passkey")
        zeigen("Passkey gespeichert. Ab jetzt geht die Anmeldung auch damit.")

    def _change_password(self, connection, user, form, address, zeigen) -> None:
        neu = (form.get("neu") or [""])[0]
        wieder = (form.get("wieder") or [""])[0]
        erzwungen = bool(user["must_change"])

        def klagen(text):
            if erzwungen:
                self._send_html(portal.change_password_page(text,
                                                            username=user["username"]))
            else:
                zeigen(trouble=text)

        # A forced first change has no old password to give: the one from
        # the .env is what just got the person in here.
        if not erzwungen:
            alt = (form.get("alt") or [""])[0]
            if not store.verify_password(user["password_hash"], alt):
                store.record_attempt(connection, address, user["username"])
                klagen("Das bisherige Kennwort stimmt nicht.")
                return
        if neu != wieder:
            klagen("Die beiden Eingaben sind nicht gleich.")
            return
        klage = store.password_complaint(neu)
        if klage:
            klagen(klage)
            return

        store.set_password(connection, user["id"], neu)
        beendet = 0
        if erzwungen or (form.get("alle_abmelden") or [""])[0]:
            beendet = store.end_all_sessions(connection, user["id"],
                                             except_token=self._session_token())
        store.log_event(connection, "password changed", username=user["username"],
                        address=address, detail=f"{beendet} other sessions ended")
        self.log_line(f"portal: {user['username']} changed the password")
        if erzwungen:
            self._redirect("/dashboard")
            return
        zeigen("Kennwort geändert."
               + (f" {beendet} andere Sitzung(en) beendet." if beendet else ""))

    def _confirm_two_factor(self, connection, user, form, address, zeigen) -> None:
        secret = user["totp_secret"]
        if not secret:
            zeigen(trouble="Die Einrichtung ist abgelaufen. Bitte neu beginnen.")
            return
        presented = self._code_from_form(form)
        ok, step = totp.check(secret, presented, last_step=-1)
        if not ok:
            uri = totp.provisioning_uri(secret, user["username"],
                                        f"{setup.MARKE} ({self._host_name()})")
            zeigen(ueberlagerung=portal.two_factor_overlay(
                secret, uri,
                "Der Code stimmt nicht. Stimmt die Uhrzeit auf dem Telefon?"))
            return
        codes = totp.recovery_codes(store.RECOVERY_COUNT)
        store.confirm_totp(connection, user["id"], step, codes)
        store.log_event(connection, "second factor switched on",
                        username=user["username"], address=address)
        self.log_line(f"portal: {user['username']} switched 2FA on")
        self._send_html(portal.recovery_page(codes, username=user["username"]))

    @staticmethod
    def _code_from_form(form: dict) -> str:
        """Six digit fields, or one recovery code — whichever was filled in.

        The second factor arrives as six separate inputs that all carry the
        name code. Joining them here keeps everything behind this point
        unaware that the field was ever split.
        """
        wieder = (form.get("wieder") or [""])[0].strip()
        if wieder:
            return wieder
        return "".join(teil.strip() for teil in form.get("code") or [])

    def _host_name(self) -> str:
        return (self.headers.get("X-Forwarded-Host")
                or self.headers.get("Host") or "neo-google-ads").split(":")[0]

    def _setup_get(self, path: str):
        if path == "/dashboard":
            self._send_html(setup.dashboard_page(self._base_url()))
        elif path == "/setup":
            self._send_html(setup.credentials_page())
        elif path == "/setup/connect":
            self._send_html(setup.connect_page(self._base_url()))
        elif path == "/setup/accounts":
            self._send_html(setup.accounts_page())
        elif path == "/setup/token":
            self._send_html(setup.token_page(pathlib.Path(self.token_path)))
        elif path == "/guardrails":
            self._send_html(setup.guardrails_page())
        elif path == "/check":
            self._send_html(setup.check_page())
        elif path == "/check/permissions":
            self._send_html(setup.diagnose_page())
        elif path == "/setup/callback":
            query = urllib.parse.urlparse(self.path).query
            ok, message = setup.exchange_code("?" + query)
            self._send_html(setup.result_page(
                ok, message, nochmal="" if ok else "/setup/connect",
                nochmal_text="Verbindung noch einmal aufbauen"))
        else:
            self._send_html(setup.result_page(False, "Diese Seite gibt es nicht."), 404)

    def _setup_post(self, path: str):
        form = self._read_form()
        if path == "/setup":
            ok, message = setup.save_credentials(form)
            if ok:
                self._redirect("/setup/connect")
            else:
                self._send_html(setup.credentials_page(message))
        elif path == "/setup/accounts":
            ok, message = setup.save_accounts(form)
            self.log_line(f"setup: allowed accounts saved ({message})" if ok
                          else f"setup: allowed accounts refused ({message})")
            if ok:
                self._redirect("/guardrails")
            else:
                self._send_html(setup.accounts_page(message))
        elif path == "/setup/paste":
            ok, message = setup.exchange_code((form.get("pasted") or [""])[0])
            self._send_html(setup.result_page(
                ok, message, nochmal="" if ok else "/setup/connect",
                nochmal_text="Verbindung noch einmal aufbauen"))
        elif path == "/setup/token":
            _, neues = setup.rotate_token(pathlib.Path(self.token_path))
            self.__class__.token = neues
            self.log_line("setup: access word replaced")
            self._send_html(setup.token_page(pathlib.Path(self.token_path), neues))
        elif path == "/guardrails":
            ok, message = setup.save_guardrails(form)
            if ok:
                self.log_line("setup: guardrails changed")
            self._send_html(setup.guardrails_page(message))
        elif path == "/check/permissions":
            ok, message = setup.save_account_logins(form)
            self.log_line(f"setup: account logins saved ({message})" if ok
                          else f"setup: account logins refused ({message})")
            self._send_html(setup.result_page(ok, message))
        elif path == "/setup/disconnect":
            ok, message = setup.disconnect()
            self._send_html(setup.result_page(ok, message))
        else:
            self._send_html(setup.result_page(False, "Diese Seite gibt es nicht."), 404)

    def do_POST(self):  # noqa: N802
        path = urllib.parse.urlparse(self.path).path.rstrip("/") or "/"
        if self.setup_enabled and self._is_portal_path(path):
            self._portal_request(path, "POST")
            return

        if self.path.rstrip("/") not in (self.path_prefix.rstrip("/"), ""):
            self._send(404, {"error": "not found"})
            return
        if not self._authorized():
            self._unauthorized()
            return

        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self._send(400, {"error": "bad Content-Length"})
            return
        if length > MAX_BODY:
            self._send(413, {"error": f"body larger than {MAX_BODY} bytes"})
            return

        raw = self.rfile.read(length) if length else b""
        try:
            message = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self._send(400, {"jsonrpc": "2.0", "id": None,
                             "error": {"code": -32700, "message": f"Parse error: {exc}"}})
            return

        # A batch is a list; the spec allows it and Claude does not send one,
        # but answering it is three lines and refusing it would be a surprise.
        if isinstance(message, list):
            answers = [a for a in (self._one(m) for m in message) if a is not None]
            if not answers:
                self._send(202)
                return
            self._send(200, answers)
            return

        answer = self._one(message)
        if answer is None:
            self._send(202)          # notification: accepted, nothing to say
            return
        self._send(200, answer)

    def _one(self, message: dict) -> dict | None:
        """Runs one JSON-RPC message through the same handler stdio uses."""
        if not isinstance(message, dict):
            return {"jsonrpc": "2.0", "id": None,
                    "error": {"code": -32600, "message": "Invalid Request"}}
        request_id = message.get("id")
        method = message.get("method", "")
        self.log_line(f"{method} id={request_id}")
        try:
            result = mcp.handle(method, message.get("params") or {})
        except LookupError:
            if request_id is None:
                return None
            return {"jsonrpc": "2.0", "id": request_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"}}
        except Exception as exc:  # noqa: BLE001
            print(traceback.format_exc(), file=sys.stderr)
            if request_id is None:
                return None
            # The type and message, never the traceback: this answer leaves the machine.
            return {"jsonrpc": "2.0", "id": request_id,
                    "error": {"code": -32603,
                              "message": f"Internal error: {type(exc).__name__}"}}
        if request_id is None or result is None:
            return None
        return {"jsonrpc": "2.0", "id": request_id, "result": result}


def seed_first_account(database: pathlib.Path) -> None:
    """Creates the very first account, so the door has a key on day one.

    INIT_USER and INIT_PASS in the .env are read once: the moment an
    account exists, they are ignored, so leaving them in the file does not
    quietly reset anything or recreate a user that was deliberately
    renamed. They do sit in the .env in clear text, which is why the
    account is marked must_change and the portal insists on a new password
    before it shows anything else.

    Without them, the first start writes a random password to the log —
    the same reasoning as the bearer token: a container nobody can sign
    into is a container nobody can configure.
    """
    with store.open_database(database) as connection:
        if store.count_users(connection):
            return
        name = (os.environ.get("INIT_USER") or "").strip()
        password = os.environ.get("INIT_PASS") or ""
        if name and password:
            klage = store.password_complaint(password)
            store.create_user(connection, name, password, email=name if "@" in name else "",
                              must_change=True)
            store.log_event(connection, "first account created from INIT_USER")
            print(f"First account created from INIT_USER: {name}", file=sys.stderr)
            if klage:
                print(f"  note: {klage} You will be asked to change it.", file=sys.stderr)
            print("  Remove INIT_USER and INIT_PASS from the .env once you are in.",
                  file=sys.stderr)
            return
        password = secrets.token_urlsafe(18)
        store.create_user(connection, "admin", password, must_change=True)
        store.log_event(connection, "first account created with a generated password")
        print("No account yet, and no INIT_USER/INIT_PASS — created one:", file=sys.stderr)
        print(f"  user:     admin\n  password: {password}", file=sys.stderr)
        print("  It must be changed at the first sign-in.", file=sys.stderr)


def account_command(options, database: pathlib.Path) -> int | None:
    """The commands for the day the browser cannot help: run on the server.

    There is no password reset by e-mail, and that is deliberate. This
    server sends no mail, and a reset link that arrives in an inbox is one
    more way in. Whoever can run these commands already has the database.
    """
    if options.list_users:
        with store.open_database(database) as connection:
            rows = connection.execute(
                "SELECT username, email, totp_confirmed, must_change, last_login,"
                " last_address FROM users ORDER BY username").fetchall()
        if not rows:
            print("No accounts yet.")
            return 0
        print(f"{'user':<28} {'2FA':<5} {'change':<7} {'last sign-in':<20} e-mail")
        for row in rows:
            print(f"{row['username']:<28} {'yes' if row['totp_confirmed'] else 'no':<5} "
                  f"{'yes' if row['must_change'] else 'no':<7} "
                  f"{(row['last_login'] or '-')[:19]:<20} {row['email']}")
        return 0

    name = options.set_password or options.disable_2fa or options.add_user
    if not name:
        return None
    with store.open_database(database) as connection:
        user = store.find_user(connection, name)
        if options.add_user:
            if user is not None:
                print(f"{name} already exists.", file=sys.stderr)
                return 1
            password = getpass.getpass(f"New password for {name}: ")
            if password != getpass.getpass("Again: "):
                print("The two entries differ.", file=sys.stderr)
                return 1
            klage = store.password_complaint(password)
            if klage:
                print(klage, file=sys.stderr)
                return 1
            store.create_user(connection, name, password)
            store.log_event(connection, "account created on the server", username=name)
            print(f"{name} created.")
            return 0
        if user is None:
            print(f"No account named {name}.", file=sys.stderr)
            return 1
        if options.disable_2fa:
            store.disable_totp(connection, user["id"])
            store.end_all_sessions(connection, user["id"])
            store.lift_lockout(connection)
            store.log_event(connection, "second factor switched off on the server",
                            username=name)
            print(f"Second factor switched off for {name}, all sessions ended, "
                  "lockout lifted.")
            return 0
        password = getpass.getpass(f"New password for {name}: ")
        if password != getpass.getpass("Again: "):
            print("The two entries differ.", file=sys.stderr)
            return 1
        klage = store.password_complaint(password)
        if klage:
            print(klage, file=sys.stderr)
            return 1
        store.set_password(connection, user["id"], password)
        ended = store.end_all_sessions(connection, user["id"])
        store.lift_lockout(connection)
        store.log_event(connection, "password set on the server", username=name)
        print(f"Password set for {name}. {ended} session(s) ended, lockout lifted.")
        return 0


class ThreadingServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Serve the Google Ads MCP tools over HTTP for claude.ai.")
    parser.add_argument("--host", default="127.0.0.1",
                        help="address to bind (default 127.0.0.1, for a reverse proxy)")
    parser.add_argument("--port", type=int, default=8788)
    parser.add_argument("--path", default="/mcp", help="path of the MCP endpoint")
    parser.add_argument("--token-file", default=str(TOKEN_FILE),
                        help=f"file holding the bearer token (default {TOKEN_FILE})")
    parser.add_argument("--new-token", action="store_true",
                        help="write a fresh token to --token-file and exit")
    parser.add_argument("--anthropic-only", action="store_true",
                        help="refuse callers outside Anthropic's published egress range")
    parser.add_argument("--setup", action="store_true",
                        help=("serve the management portal: sign-in, account, two "
                              "factor and the Google pages at /setup"))
    parser.add_argument("--database", default=None, metavar="FILE",
                        help="the portal's SQLite file (default: next to the config)")
    parser.add_argument("--public-url", default=os.environ.get("GOOGLE_ADS_PUBLIC_URL", ""),
                        metavar="URL",
                        help=("the address browsers reach this server on, e.g. "
                              "https://ads.example.at. Pins the redirect URI and the "
                              "same-site check instead of deriving them from proxy "
                              "headers. Also read from GOOGLE_ADS_PUBLIC_URL."))
    parser.add_argument("--list-users", action="store_true",
                        help="list the portal accounts and exit")
    parser.add_argument("--add-user", metavar="NAME",
                        help="create a portal account, asking for the password")
    parser.add_argument("--set-password", metavar="NAME",
                        help="set an account's password and end its sessions")
    parser.add_argument("--disable-2fa", metavar="NAME",
                        help="switch an account's second factor off, for a lost phone")
    parser.add_argument("--trusted-proxy", action="append", default=[], metavar="CIDR",
                        help=("address or network whose X-Forwarded-For header is believed. "
                              "Repeatable. Defaults to the loopback and private ranges, "
                              "which is where a reverse proxy sits."))
    parser.add_argument("--tls-cert", help="certificate file, if no reverse proxy terminates TLS")
    parser.add_argument("--tls-key", help="private key file, with --tls-cert")
    options = parser.parse_args()

    database = pathlib.Path(options.database).expanduser() if options.database \
        else store.database_path(mcp.CHANGE_LOG.parent)
    handled = account_command(options, database)
    if handled is not None:
        return handled

    token_path = pathlib.Path(options.token_file).expanduser()
    if options.new_token:
        token = write_token(token_path)
        print(f"Token written to {token_path} (readable by you only).\n")
        print(token)
        print("\nEnter it in claude.ai when adding the connector, as the header")
        print("  Authorization: Bearer <token>")
        return 0

    # Refusing to start without credentials is right for a server whose only
    # job is to answer MCP calls — but wrong when --setup is on, because the
    # setup pages exist precisely for the machine that has none yet. With
    # them, an incomplete configuration is a state to fix in the browser,
    # not a reason to stay down.
    try:
        mcp.load_config()
    except mcp.GoogleAdsError as exc:
        if not options.setup:
            print(exc.message, file=sys.stderr)
            print("\nStart with --setup to configure it in a browser instead.",
                  file=sys.stderr)
            return 1
        print(f"Not configured yet: {exc.message.splitlines()[0]}", file=sys.stderr)
        print("The MCP endpoint answers with an error until that is fixed at /setup.",
              file=sys.stderr)

    if options.setup:
        seed_first_account(database)
    Handler.database_path = database
    Handler.public_url = (options.public_url or "").strip().rstrip("/")
    if Handler.public_url and "//" not in Handler.public_url:
        print("--public-url needs the scheme too, for example "
              "https://ads.example.at", file=sys.stderr)
        return 1
    Handler.token = load_token(token_path)
    Handler.anthropic_only = options.anthropic_only
    Handler.path_prefix = options.path
    Handler.setup_enabled = options.setup
    Handler.token_path = str(token_path)
    if options.trusted_proxy:
        try:
            Handler.trusted_proxies = tuple(
                ipaddress.ip_network(entry, strict=False) for entry in options.trusted_proxy)
        except ValueError as exc:
            print(f"--trusted-proxy: {exc}", file=sys.stderr)
            return 1

    server = ThreadingServer((options.host, options.port), Handler)
    scheme = "http"
    if options.tls_cert:
        if not options.tls_key:
            print("--tls-cert needs --tls-key.", file=sys.stderr)
            return 1
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(options.tls_cert, options.tls_key)
        server.socket = context.wrap_socket(server.socket, server_side=True)
        scheme = "https"

    print(f"neo-google-ads over HTTP on {scheme}://{options.host}:{options.port}{options.path}",
          file=sys.stderr)
    print(f"  token:      {token_path}", file=sys.stderr)
    print(f"  callers:    {'Anthropic egress range only' if options.anthropic_only else 'any'}",
          file=sys.stderr)
    print(f"  proxies:    {', '.join(str(n) for n in Handler.trusted_proxies)}",
          file=sys.stderr)
    print(f"  TLS:        {'this process' if options.tls_cert else 'expected from a proxy'}",
          file=sys.stderr)
    print("  health:     GET /health", file=sys.stderr)
    if options.setup:
        print(f"  portal:     GET /login     (accounts in {database})", file=sys.stderr)
        print(f"  address:    {Handler.public_url or 'derived from the proxy headers'}",
              file=sys.stderr)
        print("  recovery:   --list-users, --set-password NAME, --disable-2fa NAME",
              file=sys.stderr)
    with contextlib.suppress(KeyboardInterrupt):
        server.serve_forever()
    server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
