#!/usr/bin/env python3
"""The portal's own database: accounts, sessions, two factor, audit trail.

Until now the management pages were guarded by the same bearer token the
MCP endpoint uses, offered as HTTP Basic auth. That is fine for a door
only one person ever opens, and wrong for everything that comes after:
there is nobody to name in an audit line, no second factor to add, no way
to change a user name, and no way to end one browser's session without
locking out the connector as well.

So the portal gets accounts, and they live in SQLite — one file next to
the configuration, no server, no dependency.

    users            name, e-mail, password, the two-factor secret
    recovery_codes   ten one-shot codes for the day the phone is gone
    sessions         one row per signed-in browser, revocable
    passkeys         the public half of a WebAuthn key, one row per device
    challenges       the one-shot random string a passkey has to sign
    events           who did what, when, from where
    attempts         failed sign-ins, for the lockout

WHAT IS STORED AND WHAT IS NOT: passwords go through scrypt with a random
salt per account; recovery codes are hashed the same way; session cookies
are random and only their hash is kept, so the table cannot be turned back
into a working cookie. The two-factor secret is the one value that has to
be kept as it is, because the algorithm needs it — which is why the file
is 0600 and the container mounts it as private data.

The bearer token stays exactly where it was. claude.ai cannot fill in a
sign-in form, so the MCP endpoint keeps its own key, and the two doors are
now genuinely separate.
"""
from __future__ import annotations

import base64
import contextlib
import datetime
import hashlib
import hmac
import os
import pathlib
import secrets
import sqlite3

SCHEMA_VERSION = 3
CHALLENGE_MINUTES = 5
SESSION_HOURS = 12
SESSION_COOKIE = "neo_portal"
MIN_PASSWORD = 12
LOCKOUT_TRIES = 8
LOCKOUT_MINUTES = 15
RECOVERY_COUNT = 10

# OAuth. Der Code lebt nur so lange, wie ein Browser fuer eine Weiterleitung
# braucht; das Zugangstoken eine Stunde; das Erneuerungstoken einen Monat und
# wird bei jedem Gebrauch getauscht. Die Obergrenze fuer Clients ist da, weil
# die dynamische Registrierung offen sein MUSS (die Spezifikation verlangt es)
# und eine offene Tuer ohne Zaehler irgendwann zugemuellt wird.
OAUTH_CODE_SECONDS = 60
OAUTH_ACCESS_HOURS = 1
OAUTH_REFRESH_DAYS = 30
OAUTH_MAX_CLIENTS = 50

# scrypt parameters. 2**15 keeps a single check near a tenth of a second on
# a small VPS, which is slow for an attacker and unnoticeable for a person.
SCRYPT_N = 1 << 15
SCRYPT_R = 8
SCRYPT_P = 1


def _maxmem(n: int, r: int) -> int:
    """OpenSSL refuses above 32 MB unless told otherwise, and 2**15 needs it.

    The working set is 128 * N * r bytes — 32 MB at these parameters, which
    is exactly the default ceiling, so the call fails. Asking for twice
    that leaves room and keeps the parameters where they belong.
    """
    return max(128 * n * r * 2, 64 * 1024 * 1024)


def now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def database_path(config_dir: pathlib.Path) -> pathlib.Path:
    return config_dir / "portal.db"


@contextlib.contextmanager
def open_database(path: pathlib.Path):
    """A connection with foreign keys on and the file kept private."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fresh = not path.exists()
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    try:
        if fresh:
            os.chmod(path, 0o600)
        _migrate(connection)
        yield connection
        connection.commit()
    finally:
        connection.close()


def _migrate(connection: sqlite3.Connection) -> None:
    connection.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id             INTEGER PRIMARY KEY,
        username       TEXT NOT NULL UNIQUE COLLATE NOCASE,
        email          TEXT NOT NULL DEFAULT '',
        password_hash  TEXT NOT NULL,
        must_change    INTEGER NOT NULL DEFAULT 0,
        totp_secret    TEXT NOT NULL DEFAULT '',
        totp_confirmed INTEGER NOT NULL DEFAULT 0,
        totp_last_step INTEGER NOT NULL DEFAULT -1,
        created        TEXT NOT NULL,
        last_login     TEXT NOT NULL DEFAULT '',
        last_address   TEXT NOT NULL DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS recovery_codes (
        id        INTEGER PRIMARY KEY,
        user_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        code_hash TEXT NOT NULL,
        used_at   TEXT NOT NULL DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS sessions (
        token_hash TEXT PRIMARY KEY,
        user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created    TEXT NOT NULL,
        seen       TEXT NOT NULL,
        expires    TEXT NOT NULL,
        address    TEXT NOT NULL DEFAULT '',
        agent      TEXT NOT NULL DEFAULT '',
        stage      TEXT NOT NULL DEFAULT 'full'
    );
    CREATE TABLE IF NOT EXISTS events (
        id       INTEGER PRIMARY KEY,
        at       TEXT NOT NULL,
        username TEXT NOT NULL DEFAULT '',
        address  TEXT NOT NULL DEFAULT '',
        what     TEXT NOT NULL,
        detail   TEXT NOT NULL DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS attempts (
        id       INTEGER PRIMARY KEY,
        at       TEXT NOT NULL,
        address  TEXT NOT NULL DEFAULT '',
        username TEXT NOT NULL DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS passkeys (
        id            INTEGER PRIMARY KEY,
        user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        credential_id TEXT NOT NULL UNIQUE,
        public_key    TEXT NOT NULL,
        sign_count    INTEGER NOT NULL DEFAULT 0,
        name          TEXT NOT NULL DEFAULT '',
        created       TEXT NOT NULL,
        used          TEXT NOT NULL DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS challenges (
        challenge TEXT PRIMARY KEY,
        purpose   TEXT NOT NULL,
        user_id   INTEGER NOT NULL DEFAULT 0,
        expires   TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS oauth_clients (
        client_id     TEXT PRIMARY KEY,
        secret_hash   TEXT NOT NULL DEFAULT '',
        name          TEXT NOT NULL DEFAULT '',
        redirect_uris TEXT NOT NULL,
        created       TEXT NOT NULL,
        last_used     TEXT NOT NULL DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS oauth_codes (
        code_hash    TEXT PRIMARY KEY,
        client_id    TEXT NOT NULL,
        user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        redirect_uri TEXT NOT NULL,
        challenge    TEXT NOT NULL,
        scope        TEXT NOT NULL DEFAULT '',
        resource     TEXT NOT NULL DEFAULT '',
        expires      TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS oauth_tokens (
        token_hash TEXT PRIMARY KEY,
        kind       TEXT NOT NULL,
        client_id  TEXT NOT NULL,
        user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        scope      TEXT NOT NULL DEFAULT '',
        resource   TEXT NOT NULL DEFAULT '',
        created    TEXT NOT NULL,
        expires    TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS oauth_tokens_user ON oauth_tokens(user_id);
    CREATE INDEX IF NOT EXISTS attempts_at ON attempts(at);
    CREATE INDEX IF NOT EXISTS events_at ON events(at);
    """)


# -- passwords -------------------------------------------------------------

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(password.encode("utf-8"), salt=salt,
                             n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32,
                             maxmem=_maxmem(SCRYPT_N, SCRYPT_R))
    return "$".join(("scrypt", str(SCRYPT_N), str(SCRYPT_R), str(SCRYPT_P),
                     base64.b64encode(salt).decode(),
                     base64.b64encode(derived).decode()))


def verify_password(stored: str, password: str) -> bool:
    try:
        kind, n, r, p, salt, expected = stored.split("$")
        if kind != "scrypt":
            return False
        derived = hashlib.scrypt(password.encode("utf-8"),
                                 salt=base64.b64decode(salt),
                                 n=int(n), r=int(r), p=int(p), dklen=32,
                                 maxmem=_maxmem(int(n), int(r)))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(derived, base64.b64decode(expected))


def password_complaint(password: str) -> str:
    """Empty when the password will do. One sentence when it will not."""
    if len(password) < MIN_PASSWORD:
        return f"Das Kennwort braucht mindestens {MIN_PASSWORD} Zeichen."
    if password.lower() in ("passwort1234", "kennwort1234", "123456789012"):
        return "Dieses Kennwort steht in jeder Liste."
    return ""


# -- accounts --------------------------------------------------------------

def count_users(connection) -> int:
    return connection.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]


def find_user(connection, username: str):
    return connection.execute(
        "SELECT * FROM users WHERE username = ? COLLATE NOCASE", (username,)).fetchone()


def user_by_id(connection, user_id: int):
    return connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def create_user(connection, username: str, password: str, *, email: str = "",
                must_change: bool = False) -> int:
    cursor = connection.execute(
        "INSERT INTO users (username, email, password_hash, must_change, created)"
        " VALUES (?, ?, ?, ?, ?)",
        (username.strip(), email.strip(), hash_password(password),
         1 if must_change else 0, now()))
    return cursor.lastrowid


def set_password(connection, user_id: int, password: str) -> None:
    connection.execute(
        "UPDATE users SET password_hash = ?, must_change = 0 WHERE id = ?",
        (hash_password(password), user_id))


def set_identity(connection, user_id: int, username: str, email: str) -> None:
    connection.execute("UPDATE users SET username = ?, email = ? WHERE id = ?",
                       (username.strip(), email.strip(), user_id))


def note_login(connection, user_id: int, address: str) -> None:
    connection.execute("UPDATE users SET last_login = ?, last_address = ? WHERE id = ?",
                       (now(), address, user_id))


# -- two factor ------------------------------------------------------------

def begin_totp(connection, user_id: int, secret: str) -> None:
    """Stores an unconfirmed secret. It counts only once a code proved it."""
    connection.execute(
        "UPDATE users SET totp_secret = ?, totp_confirmed = 0, totp_last_step = -1"
        " WHERE id = ?", (secret, user_id))


def confirm_totp(connection, user_id: int, step: int, codes: list[str]) -> None:
    connection.execute(
        "UPDATE users SET totp_confirmed = 1, totp_last_step = ? WHERE id = ?",
        (step, user_id))
    connection.execute("DELETE FROM recovery_codes WHERE user_id = ?", (user_id,))
    connection.executemany(
        "INSERT INTO recovery_codes (user_id, code_hash) VALUES (?, ?)",
        [(user_id, hash_password(code)) for code in codes])


def disable_totp(connection, user_id: int) -> None:
    connection.execute(
        "UPDATE users SET totp_secret = '', totp_confirmed = 0, totp_last_step = -1"
        " WHERE id = ?", (user_id,))
    connection.execute("DELETE FROM recovery_codes WHERE user_id = ?", (user_id,))


def note_totp_step(connection, user_id: int, step: int) -> None:
    connection.execute("UPDATE users SET totp_last_step = ? WHERE id = ?", (step, user_id))


def spend_recovery_code(connection, user_id: int, presented: str) -> bool:
    """A recovery code works once. Returns whether this one did."""
    cleaned = presented.strip().lower().replace(" ", "")
    for row in connection.execute(
            "SELECT id, code_hash FROM recovery_codes"
            " WHERE user_id = ? AND used_at = ''", (user_id,)):
        if verify_password(row["code_hash"], cleaned):
            connection.execute("UPDATE recovery_codes SET used_at = ? WHERE id = ?",
                               (now(), row["id"]))
            return True
    return False


def recovery_left(connection, user_id: int) -> int:
    return connection.execute(
        "SELECT COUNT(*) AS n FROM recovery_codes WHERE user_id = ? AND used_at = ''",
        (user_id,)).fetchone()["n"]


# -- sessions --------------------------------------------------------------

def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def start_session(connection, user_id: int, *, address: str = "", agent: str = "",
                  stage: str = "full") -> str:
    token = secrets.token_urlsafe(32)
    expires = (datetime.datetime.now(datetime.timezone.utc)
               + datetime.timedelta(hours=SESSION_HOURS)).isoformat(timespec="seconds")
    connection.execute(
        "INSERT INTO sessions (token_hash, user_id, created, seen, expires, address,"
        " agent, stage) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (_token_hash(token), user_id, now(), now(), expires, address, agent[:200], stage))
    return token


def read_session(connection, token: str):
    """The session row, or None when it is missing, expired or unknown."""
    if not token:
        return None
    row = connection.execute("SELECT * FROM sessions WHERE token_hash = ?",
                             (_token_hash(token),)).fetchone()
    if row is None:
        return None
    if row["expires"] <= now():
        connection.execute("DELETE FROM sessions WHERE token_hash = ?", (row["token_hash"],))
        return None
    connection.execute("UPDATE sessions SET seen = ? WHERE token_hash = ?",
                       (now(), row["token_hash"]))
    return row


def promote_session(connection, token: str) -> None:
    """Second factor passed: the half-open session becomes a real one."""
    connection.execute("UPDATE sessions SET stage = 'full' WHERE token_hash = ?",
                       (_token_hash(token),))


def end_session(connection, token: str) -> None:
    connection.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))


def end_all_sessions(connection, user_id: int, *, except_token: str = "") -> int:
    keep = _token_hash(except_token) if except_token else ""
    cursor = connection.execute(
        "DELETE FROM sessions WHERE user_id = ? AND token_hash <> ?", (user_id, keep))
    return cursor.rowcount


def sessions_for(connection, user_id: int) -> list:
    return connection.execute(
        "SELECT * FROM sessions WHERE user_id = ? ORDER BY seen DESC", (user_id,)).fetchall()


def sweep(connection) -> None:
    """Drops what has expired. Called on every sign-in, which is often enough."""
    connection.execute("DELETE FROM sessions WHERE expires <= ?", (now(),))
    cutoff = (datetime.datetime.now(datetime.timezone.utc)
              - datetime.timedelta(days=30)).isoformat(timespec="seconds")
    connection.execute("DELETE FROM attempts WHERE at <= ?", (cutoff,))
    connection.execute(
        "DELETE FROM events WHERE id NOT IN"
        " (SELECT id FROM events ORDER BY id DESC LIMIT 500)")
    connection.execute("DELETE FROM oauth_codes WHERE expires <= ?", (now(),))
    connection.execute("DELETE FROM oauth_tokens WHERE expires <= ?", (now(),))


# -- lockout and audit -----------------------------------------------------

def record_attempt(connection, address: str, username: str) -> None:
    connection.execute("INSERT INTO attempts (at, address, username) VALUES (?, ?, ?)",
                       (now(), address, username[:100]))


def clear_attempts(connection, address: str, username: str) -> None:
    connection.execute("DELETE FROM attempts WHERE address = ? OR username = ?",
                       (address, username[:100]))


def lift_lockout(connection) -> int:
    """Clears every recorded failed attempt.

    Called when somebody with access to the server resets a password or
    switches a second factor off. Those are recovery actions: leaving the
    lockout in place would mean the operator fixes the account and the
    person still cannot get in for another quarter of an hour. The lockout
    counts by address as well as by name, so clearing only the name would
    not do it.
    """
    cursor = connection.execute("DELETE FROM attempts")
    return cursor.rowcount


def locked_out(connection, address: str, username: str) -> int:
    """Minutes still to wait, or 0. Counts by address and by name."""
    since = (datetime.datetime.now(datetime.timezone.utc)
             - datetime.timedelta(minutes=LOCKOUT_MINUTES)).isoformat(timespec="seconds")
    row = connection.execute(
        "SELECT COUNT(*) AS n, MIN(at) AS first FROM attempts"
        " WHERE at > ? AND (address = ? OR username = ?)",
        (since, address, username[:100])).fetchone()
    if row["n"] < LOCKOUT_TRIES:
        return 0
    first = datetime.datetime.fromisoformat(row["first"])
    passed = (datetime.datetime.now(datetime.timezone.utc) - first).total_seconds() / 60
    return max(1, int(LOCKOUT_MINUTES - passed) + 1)


def log_event(connection, what: str, *, username: str = "", address: str = "",
              detail: str = "") -> None:
    connection.execute(
        "INSERT INTO events (at, username, address, what, detail) VALUES (?, ?, ?, ?, ?)",
        (now(), username[:100], address, what, detail[:300]))


def recent_events(connection, limit: int = 12) -> list:
    return connection.execute(
        "SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()


# -- passkeys --------------------------------------------------------------
#
# Gespeichert wird nur der oeffentliche Teil. Der private Schluessel
# verlaesst das Geraet nie — deshalb ist diese Tabelle auch dann nicht
# gefaehrlich, wenn jemand die Datei in die Hand bekommt: mit einem
# oeffentlichen Schluessel meldet sich niemand an.

def count_passkeys(connection: sqlite3.Connection) -> int:
    return connection.execute("SELECT COUNT(*) FROM passkeys").fetchone()[0]


def passkeys_for(connection: sqlite3.Connection, user_id: int) -> list:
    return connection.execute(
        "SELECT * FROM passkeys WHERE user_id = ? ORDER BY created", (user_id,)
    ).fetchall()


def passkey_by_credential(connection: sqlite3.Connection, credential_id: str):
    return connection.execute(
        "SELECT * FROM passkeys WHERE credential_id = ?", (credential_id,)).fetchone()


def add_passkey(connection: sqlite3.Connection, user_id: int, credential_id: str,
                public_key: str, name: str, sign_count: int = 0) -> None:
    connection.execute(
        "INSERT INTO passkeys (user_id, credential_id, public_key, sign_count, "
        "name, created) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, credential_id, public_key, sign_count, name[:60] or "Passkey", now()))


def note_passkey_use(connection: sqlite3.Connection, passkey_id: int,
                     sign_count: int) -> None:
    connection.execute("UPDATE passkeys SET used = ?, sign_count = ? WHERE id = ?",
                       (now(), sign_count, passkey_id))


def remove_passkey(connection: sqlite3.Connection, user_id: int,
                   credential_id: str) -> bool:
    cursor = connection.execute(
        "DELETE FROM passkeys WHERE user_id = ? AND credential_id = ?",
        (user_id, credential_id))
    return cursor.rowcount > 0


# -- challenges ------------------------------------------------------------
#
# Eine Challenge gilt einmal und fuenf Minuten. Sie steht in der Datenbank
# und nicht im Cookie, damit dieselbe Zufallszahl nicht zweimal
# unterschrieben werden kann: abgeholt heisst geloescht.

def new_challenge(connection: sqlite3.Connection, purpose: str,
                  user_id: int = 0) -> str:
    wert = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    ablauf = (datetime.datetime.now(datetime.timezone.utc)
              + datetime.timedelta(minutes=CHALLENGE_MINUTES))
    connection.execute("DELETE FROM challenges WHERE expires < ?", (now(),))
    connection.execute(
        "INSERT INTO challenges (challenge, purpose, user_id, expires) "
        "VALUES (?, ?, ?, ?)",
        (wert, purpose, user_id, ablauf.isoformat(timespec="seconds")))
    return wert


def spend_challenge(connection: sqlite3.Connection, challenge: str,
                    purpose: str) -> tuple[bool, int]:
    """Takes the challenge away and says whether it was still good for this."""
    row = connection.execute(
        "SELECT * FROM challenges WHERE challenge = ?", (challenge,)).fetchone()
    if row is None:
        return False, 0
    connection.execute("DELETE FROM challenges WHERE challenge = ?", (challenge,))
    if row["purpose"] != purpose or row["expires"] < now():
        return False, 0
    return True, row["user_id"]


# -- OAuth -----------------------------------------------------------------
#
# Drei kurze Tabellen und kein Schluesselmaterial. Die Token sind
# Zufallszahlen, gespeichert wird nur ihr SHA-256 — genau wie bei den
# Sitzungen. Das ist Absicht:
#
#   * Wer die Datenbank liest, hat damit noch kein gueltiges Token.
#   * Entziehen heisst eine Zeile loeschen. Bei einem signierten Token
#     (JWT) braeuchte es dafuer eine Sperrliste, die man auch wieder
#     pflegen muss — fuer EINEN Server ist das reine Zusatzarbeit.
#
# Ein Token traegt IMMER die Ressource, fuer die es ausgestellt wurde. Der
# MCP-Endpunkt prueft das und weist ein Token ab, das fuer einen anderen
# Server gedacht war. Ohne diese Bindung koennte ein Betreiber, bei dem man
# sich anmeldet, das erhaltene Token bei einem fremden Server einloesen.
#
# ⚠️ WER ETWAS HERAUSGIBT ODER ENTZIEHT, SCHREIBT ES VORHER FEST.
#
# Die Portalantwort verlaesst den Server, BEVOR open_database() die
# Transaktion festschreibt: Der Handler sendet noch innerhalb des
# with-Blocks. Fuer eine Seite, die man liest, ist das egal. Fuer alles,
# womit der Empfaenger sofort weiterarbeitet, ist es ein Fenster:
#
#   * Entfernen meldete "entfernt", und das Token funktionierte noch —
#     der naechste Aufruf kam an, bevor die Loeschung committed war.
#     Im Selbsttest fiel das in rund jedem zehnten Lauf auf.
#   * Ein Autorisierungscode ging in der Weiterleitung hinaus, bevor er in
#     der Datenbank stand; der Tausch dagegen kam manchmal zu frueh.
#   * Dasselbe fuer frisch ausgestellte Token.
#
# Deshalb committen create_code, issue_token und delete_client selbst.
# Ein zweites commit() am Ende des with-Blocks kostet nichts.


def _now_plus(*, seconds: int = 0, hours: int = 0, days: int = 0) -> str:
    return (datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(seconds=seconds, hours=hours,
                                 days=days)).isoformat(timespec="seconds")


def count_clients(connection) -> int:
    return connection.execute("SELECT COUNT(*) FROM oauth_clients").fetchone()[0]


def register_client(connection, name: str, redirect_uris: list[str]) -> dict:
    """Legt einen Client an und gibt seine Zugangsdaten EINMAL heraus."""
    client_id = "neo-" + secrets.token_urlsafe(18)
    secret = secrets.token_urlsafe(32)
    connection.execute(
        "INSERT INTO oauth_clients (client_id, secret_hash, name, redirect_uris, "
        "created) VALUES (?, ?, ?, ?, ?)",
        (client_id, _token_hash(secret), name[:80], "\n".join(redirect_uris), now()))
    return {"client_id": client_id, "client_secret": secret}


def client_by_id(connection, client_id: str):
    return connection.execute(
        "SELECT * FROM oauth_clients WHERE client_id = ?", (client_id,)).fetchone()


def client_secret_matches(row, presented: str) -> bool:
    return hmac.compare_digest(row["secret_hash"], _token_hash(presented))


def client_redirect_uris(row) -> list[str]:
    return [u for u in (row["redirect_uris"] or "").split("\n") if u]


def note_client_use(connection, client_id: str) -> None:
    connection.execute("UPDATE oauth_clients SET last_used = ? WHERE client_id = ?",
                       (now(), client_id))


def create_code(connection, *, client_id: str, user_id: int, redirect_uri: str,
                challenge: str, scope: str, resource: str) -> str:
    code = secrets.token_urlsafe(32)
    connection.execute(
        "INSERT INTO oauth_codes (code_hash, client_id, user_id, redirect_uri, "
        "challenge, scope, resource, expires) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (_token_hash(code), client_id, user_id, redirect_uri, challenge, scope,
         resource, _now_plus(seconds=OAUTH_CODE_SECONDS)))
    connection.commit()          # siehe Regel oben: erst festschreiben, dann herausgeben
    return code


def spend_code(connection, code: str):
    """Holt den Code und loescht ihn im selben Atemzug — er gilt genau einmal.

    ⚠️ Das `commit()` hier ist kein Schoenheitsfehler, sondern der Kern:
    Ohne es wird die Loeschung zurueckgerollt, sobald die weitere Pruefung
    im Aufrufer eine Ausnahme wirft — und genau das tut sie bei falschem
    `code_verifier`. Der Code waere danach WIEDER GUELTIG und beliebig oft
    einloesbar. Im Test fiel das als „ein einmal abgelehnter Code ist
    verbraucht: 200" auf. Ein Autorisierungscode muss beim ersten Gebrauch
    verfallen, ob der Gebrauch geglueckt ist oder nicht.
    """
    digest = _token_hash(code)
    row = connection.execute("SELECT * FROM oauth_codes WHERE code_hash = ?",
                             (digest,)).fetchone()
    connection.execute("DELETE FROM oauth_codes WHERE code_hash = ?", (digest,))
    connection.commit()
    if row is None or row["expires"] <= now():
        return None
    return row


def issue_token(connection, *, kind: str, client_id: str, user_id: int,
                scope: str, resource: str) -> str:
    token = secrets.token_urlsafe(40)
    expires = _now_plus(hours=OAUTH_ACCESS_HOURS) if kind == "access" \
        else _now_plus(days=OAUTH_REFRESH_DAYS)
    connection.execute(
        "INSERT INTO oauth_tokens (token_hash, kind, client_id, user_id, scope, "
        "resource, created, expires) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (_token_hash(token), kind, client_id, user_id, scope, resource, now(), expires))
    connection.commit()          # siehe Regel oben
    return token


def read_token(connection, token: str, kind: str):
    row = connection.execute(
        "SELECT * FROM oauth_tokens WHERE token_hash = ? AND kind = ?",
        (_token_hash(token), kind)).fetchone()
    if row is None or row["expires"] <= now():
        return None
    return row


def spend_refresh(connection, token: str):
    """Erneuerungstoken werden getauscht, nicht wiederverwendet."""
    row = read_token(connection, token, "refresh")
    connection.execute("DELETE FROM oauth_tokens WHERE token_hash = ?",
                       (_token_hash(token),))
    return row


def connections_for(connection, user_id: int) -> list:
    """Verbundene Anwendungen, eine Zeile je Client."""
    return connection.execute(
        "SELECT c.client_id, c.name, MIN(t.created) AS seit, MAX(t.created) AS zuletzt,"
        "       COUNT(*) AS anzahl"
        "  FROM oauth_tokens t JOIN oauth_clients c ON c.client_id = t.client_id"
        " WHERE t.user_id = ? GROUP BY c.client_id ORDER BY zuletzt DESC",
        (user_id,)).fetchall()


def revoke_connection(connection, user_id: int, client_id: str) -> int:
    cursor = connection.execute(
        "DELETE FROM oauth_tokens WHERE user_id = ? AND client_id = ?",
        (user_id, client_id))
    connection.execute("DELETE FROM oauth_codes WHERE user_id = ? AND client_id = ?",
                       (user_id, client_id))
    return cursor.rowcount


def clients_with_usage(connection) -> list:
    """Alle registrierten Clients, mit den noch lebenden Zugaengen dazu.

    Abgelaufene Token zaehlen nicht mit: Sie sind bereits wirkungslos, und
    sie wuerden die Zahl aufblasen, auf die jemand schaut, wenn er
    entscheidet, ob er eine Anwendung entfernen kann.
    """
    return connection.execute(
        "SELECT c.client_id, c.name, c.redirect_uris, c.created, c.last_used,"
        "       COUNT(DISTINCT t.user_id) AS nutzer_anzahl,"
        "       COALESCE(GROUP_CONCAT(DISTINCT u.username), '') AS nutzer"
        "  FROM oauth_clients c"
        "  LEFT JOIN oauth_tokens t"
        "         ON t.client_id = c.client_id AND t.expires > ?"
        "  LEFT JOIN users u ON u.id = t.user_id"
        " GROUP BY c.client_id"
        " ORDER BY (c.last_used = '') ASC, c.last_used DESC, c.created DESC",
        (now(),)).fetchall()


def client_grants(connection, client_id: str) -> int:
    """Wie viele Konten diesem Client gerade einen gueltigen Zugang haben."""
    return connection.execute(
        "SELECT COUNT(DISTINCT user_id) FROM oauth_tokens"
        " WHERE client_id = ? AND expires > ?", (client_id, now())).fetchone()[0]


def delete_client(connection, client_id: str) -> dict:
    """Entfernt einen Client mitsamt allem, was auf ihn ausgestellt wurde.

    Die Token muessen mit: Ein Zugang, dessen Client nicht mehr existiert,
    waere sonst weiter gueltig — entfernen soll aber heissen, dass die
    Anwendung ab sofort draussen ist.
    """
    token = connection.execute(
        "DELETE FROM oauth_tokens WHERE client_id = ?", (client_id,)).rowcount
    connection.execute("DELETE FROM oauth_codes WHERE client_id = ?", (client_id,))
    weg = connection.execute(
        "DELETE FROM oauth_clients WHERE client_id = ?", (client_id,)).rowcount
    connection.commit()          # siehe Regel oben: entzogen ist erst, was festgeschrieben ist
    return {"client": weg, "token": token}
