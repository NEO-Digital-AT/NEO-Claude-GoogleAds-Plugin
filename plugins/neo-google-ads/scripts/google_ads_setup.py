#!/usr/bin/env python3
"""A small management console for the Google Ads connection, in the browser.

Setting the connection up over SSH means copying an URL out of a terminal
where Ctrl-C interrupts rather than copies, pasting it back, and reading a
JSON file to see what happened. The container already answers on a public
HTTPS address, so it can serve a page instead, and the whole round trip
becomes three clicks.

It does not stop at the first connection, because that is not where the
work stops: accounts get added, a token gets replaced, a budget ceiling
turns out too low. Each of those otherwise means an SSH session and a hand
edit of the .env — on the file that decides what an AI may spend.

    /setup              status: connection, accounts, access level, guardrails,
                        and the last write attempts from the change log
    /setup/credentials  the four values Google requires (POST)
    /setup/connect      starts the consent flow — also to reconnect
    /setup/callback     where Google returns; trades the code for a token
    /setup/paste        the fallback when the OAuth client is a desktop one
    /setup/guardrails   edits the guardrails, accounts by tick box (POST)
    /setup/token        replaces the access word for both doors (POST)
    /setup/disconnect   forgets the refresh token (POST, asks first)
    /setup/check        runs the connection checks and shows the result

THE PAGE IS AS SENSITIVE AS THE SERVER ITSELF, so it lives behind the same
bearer token, offered as HTTP Basic auth: any user name, the token as the
password. That turns an existing secret into a browser login instead of
inventing a second one.

The page speaks German because a person reads it. Everything around it —
names, comments, log lines — stays English, like every other tool here.

A guardrail this page cannot show, it does not change. An account list that
failed to load would otherwise submit as "no boxes ticked", which the server
reads as "every account" — the widest setting there is, reached by a network
hiccup. The account section therefore carries a marker, and without it the
save leaves the authorisation exactly as it was.

No dependencies, no template engine, no JavaScript: one function per page,
HTML as text.
"""
from __future__ import annotations

import base64
import datetime
import hashlib
import html
import json
import os
import pathlib
import secrets
import urllib.error
import urllib.parse
import urllib.request

import google_ads_client as gac

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
PENDING_FILE = gac.CONFIG_FILE.parent / "pending-auth.json"

# The word mark, drawn as paths so it needs no font and no second file.
# It takes its colour from the surrounding text, so one variable changes
# the whole page. To use a real logo instead, drop an SVG at
# /data/logo.svg — it is served in place of this one.
LOGO = """<svg viewBox="0 0 132 40" role="img" aria-label="NEO Digital"
  fill="currentColor" xmlns="http://www.w3.org/2000/svg">
<path d="M0 40V0h7.2l17.4 26.6V0h6.6v40h-7.2L6.6 13.4V40H0z"/>
<path d="M40 40V0h25.6v6.4H46.6v9.4h17.2v6.4H46.6v11.4h19.4V40H40z"/>
<path d="M92.4 40c-11 0-19.4-8.6-19.4-20S81.4 0 92.4 0s19.4 8.6 19.4 20-8.4 20-19.4 20zm0-6.6c7.2 0 12.6-5.6 12.6-13.4S99.6 6.6 92.4 6.6 79.8 12.2 79.8 20s5.4 13.4 12.6 13.4z"/>
<rect x="120" y="30" width="10" height="10" rx="2"/>
</svg>"""

STYLE = """
/* Ein Farbschema, dunkel. Kein prefers-color-scheme: die Seite ist dunkel,
   überall. Jeder Wert unten ist mit dem Kontrastrechner aus neo-design
   gemessen; die schwächste Paarung liegt bei 5,7:1 und damit über AA. */
:root {
  --bg:      #0B0F0B;   /* Grund                                        */
  --card:    #141814;   /* Karten, 1 Stufe heller                       */
  --line:    #242C24;   /* Rahmen, nur Fläche — kein Text darauf        */
  --fg:      #E8EDE8;   /* Fließtext            16,3:1 auf --bg         */
  --muted:   #A3ADA3;   /* Nebentext             7,7:1 auf --card       */
  --neon:    #39FF14;   /* Akzent               13,2:1 auf --card       */
  --neon-dim:#2BC410;   /* Akzent auf Flächen, wo Neon zu laut wäre     */
  --warn:    #FFB454;   /* Hinweis              10,2:1 auf --card       */
  --bad:     #FF6B5C;   /* Befund                6,4:1 auf --card       */
}
* { box-sizing: border-box; }
html { color-scheme: dark; }
body { margin: 0; background: var(--bg); color: var(--fg);
  font: 16px/1.55 system-ui, -apple-system, "Segoe UI", sans-serif;
  -webkit-font-smoothing: antialiased; }
main { max-width: 54rem; margin: 0 auto; padding: 2.5rem 1rem 5rem; }

header.marke { display: flex; align-items: center; gap: .9rem;
  padding-bottom: 1.5rem; margin-bottom: 2rem;
  border-bottom: 1px solid var(--line); }
header.marke svg { height: 1.55rem; width: auto; color: var(--neon);
  filter: drop-shadow(0 0 14px color-mix(in srgb, var(--neon) 45%, transparent)); }
header.marke .wo { margin-left: auto; color: var(--muted); font-size: .82rem;
  letter-spacing: .08em; text-transform: uppercase; }

h1 { font-size: 1.6rem; margin: 0 0 .3rem; letter-spacing: -.01em; }
h2 { font-size: 1.05rem; margin: 0 0 .9rem; letter-spacing: .01em; }
p.lead { color: var(--muted); margin: 0 0 2rem; max-width: 42rem; }

.card { background: var(--card); border: 1px solid var(--line);
  border-radius: .7rem; padding: 1.35rem; margin-bottom: 1rem; }
.card.akzent { border-color: color-mix(in srgb, var(--neon) 35%, var(--line)); }

table { width: 100%; border-collapse: collapse; font-size: .94rem; }
th, td { text-align: left; padding: .6rem .7rem; vertical-align: top;
  border-bottom: 1px solid var(--line); }
th { font-weight: 600; color: var(--muted); font-size: .78rem;
  text-transform: uppercase; letter-spacing: .06em; white-space: nowrap; }
tr:last-child th, tr:last-child td { border-bottom: none; }

code, .mono, pre { font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; }
code, .mono { font-size: .89em; color: var(--neon); }
pre { background: var(--bg); border: 1px solid var(--line); border-radius: .45rem;
  padding: .9rem; overflow-x: auto; font-size: .85rem; margin: 0;
  color: var(--fg); white-space: pre-wrap; word-break: break-all; }

.state { display: inline-block; padding: .12rem .6rem; border-radius: 1rem;
  font-size: .76rem; font-weight: 700; letter-spacing: .04em;
  text-transform: uppercase; vertical-align: middle; }
.state.ok   { background: color-mix(in srgb, var(--neon) 16%, transparent);
              color: var(--neon); }
.state.warn { background: color-mix(in srgb, var(--warn) 16%, transparent);
              color: var(--warn); }
.state.bad  { background: color-mix(in srgb, var(--bad) 16%, transparent);
              color: var(--bad); }

label { display: block; margin: 1.35rem 0 .3rem; font-weight: 600; font-size: .92rem; }
label:first-child { margin-top: 0; }
label span { display: block; font-weight: 400; color: var(--muted);
  font-size: .85rem; margin-top: .2rem; line-height: 1.45; }
input[type=text], input[type=password] { width: 100%; padding: .6rem .75rem;
  margin-top: .45rem; border: 1px solid var(--line); border-radius: .45rem;
  background: var(--bg); color: var(--fg);
  font-family: ui-monospace, Menlo, monospace; font-size: .9rem; }
input:focus-visible { outline: 2px solid var(--neon); outline-offset: 1px;
  border-color: transparent; }

button, .button { display: inline-block; padding: .6rem 1.2rem; border-radius: .45rem;
  border: 1px solid transparent; background: var(--neon); color: #07120A;
  font: inherit; font-weight: 700; font-size: .93rem; cursor: pointer;
  text-decoration: none; margin-top: 1.4rem; }
button:hover, .button:hover { background: #55FF38; }
button:focus-visible, .button:focus-visible { outline: 2px solid var(--fg);
  outline-offset: 2px; }
button.quiet, .button.quiet { background: transparent; color: var(--fg);
  border-color: var(--line); }
button.quiet:hover, .button.quiet:hover { border-color: var(--neon);
  color: var(--neon); }
button.danger { background: transparent; color: var(--bad);
  border-color: color-mix(in srgb, var(--bad) 45%, transparent); }
button.danger:hover { background: color-mix(in srgb, var(--bad) 14%, transparent); }

label.kasten { display: flex; gap: .7rem; align-items: flex-start;
  margin: .7rem 0; padding: .7rem .8rem; border: 1px solid var(--line);
  border-radius: .45rem; font-weight: 400; cursor: pointer; }
label.kasten:hover { border-color: color-mix(in srgb, var(--neon) 40%, var(--line)); }
label.kasten input { accent-color: var(--neon); width: 1.1rem; height: 1.1rem;
  margin-top: .15rem; flex: none; }
label.kasten input:disabled { opacity: .5; }
.kasten-text { display: block; }
.kasten-text b { display: block; font-size: .95rem; }
.kasten-text .mono { display: block; color: var(--muted); font-size: .84rem; }
.kasten-text .note { margin-top: .2rem; }
.row { display: flex; gap: .7rem; flex-wrap: wrap; align-items: center; }
.note { color: var(--muted); font-size: .87rem; margin-top: .8rem; line-height: 1.5; }
.warnung { border-left: 3px solid var(--warn); padding: .1rem 0 .1rem .8rem;
           margin: 0 0 1rem; color: var(--text); font-size: .9rem;
           line-height: 1.55; }
a { color: var(--neon); text-underline-offset: .2em; }
a:hover { color: #7CFF5C; }

@media (max-width: 34rem) {
  main { padding: 1.5rem .85rem 3.5rem; }
  header.marke { gap: .7rem; }
  header.marke .wo { display: none; }
  th, td { padding: .5rem .35rem; font-size: .88rem; }
  th { font-size: .72rem; }
  table, tbody, tr, th, td { display: block; }
  th { border: none; padding-bottom: .15rem; }
  td { padding-top: 0; padding-bottom: .8rem; }
}
"""


def logo_markup() -> str:
    """The built-in word mark, or the operator's own file if one is there."""
    eigen = gac.CONFIG_FILE.parent / "logo.svg"
    if eigen.exists():
        try:
            return eigen.read_text(encoding="utf-8")
        except OSError:
            pass
    return LOGO


def page(title: str, body: str) -> bytes:
    """One HTML document. No framework, no build step, nothing to update."""
    return (f"""<!doctype html>
<html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark">
<meta name="robots" content="noindex, nofollow">
<title>{html.escape(title)} — NEO Google Ads</title>
<style>{STYLE}</style></head>
<body><main>
<header class="marke">{logo_markup()}<span class="wo">Google Ads</span></header>
{body}</main></body></html>""").encode("utf-8")


def esc(value) -> str:
    return html.escape(str(value if value is not None else ""))


# --------------------------------------------------------------------------
# Reading the current state
# --------------------------------------------------------------------------

def load_state() -> dict:
    """Everything the status page shows, gathered in one place."""
    state: dict = {"configured": False, "connected": False, "error": "",
                   "accounts": [], "guardrails": {}, "config": {}}
    try:
        config = gac.load_config()
    except gac.GoogleAdsError as exc:
        state["error"] = exc.message
        raw = {}
        if gac.CONFIG_FILE.exists():
            try:
                raw = json.loads(gac.CONFIG_FILE.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                raw = {}
        for field, name in gac.ENV_FIELDS.items():
            if os.environ.get(name):
                raw[field] = os.environ[name]
        state["config"] = raw
        state["guardrails"] = dict(gac.DEFAULT_GUARDRAILS)
        return state

    state["configured"] = True
    state["config"] = config
    state["guardrails"] = config["guardrails"]
    client = gac.Client(config)
    try:
        ids = client.list_accessible_customers()
    except gac.GoogleAdsError as exc:
        state["error"] = exc.message
        return state

    state["connected"] = True
    for customer_id in ids:
        entry = {"id": customer_id, "name": "", "currency": "", "manager": False,
                 "problem": ""}
        try:
            rows = client.search(
                customer_id,
                "SELECT customer.descriptive_name, customer.currency_code, "
                "customer.manager, customer.status FROM customer LIMIT 1",
                max_rows=1)
            if rows:
                customer = rows[0].get("customer", {})
                entry["name"] = customer.get("descriptiveName", "")
                entry["currency"] = customer.get("currencyCode", "")
                entry["manager"] = bool(customer.get("manager"))
                entry["status"] = customer.get("status", "")
        except gac.GoogleAdsError as exc:
            entry["problem"] = exc.message.splitlines()[0]
        state["accounts"].append(entry)
    return state


def recent_changes(limit: int = 5) -> list[dict]:
    if not gac.CHANGE_LOG.exists():
        return []
    entries = []
    for line in gac.CHANGE_LOG.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        entry.pop("operations", None)
        entry.pop("detail", None)
        entries.append(entry)
    return list(reversed(entries))[:limit]


# --------------------------------------------------------------------------
# Pages
# --------------------------------------------------------------------------

def status_page(base_url: str) -> bytes:
    state = load_state()
    config = state["config"]
    rails = state["guardrails"]

    if state["connected"]:
        badge = '<span class="state ok">verbunden</span>'
    elif state["configured"]:
        badge = '<span class="state bad">Zugang abgelehnt</span>'
    elif config.get("client_id"):
        badge = '<span class="state warn">noch nicht verbunden</span>'
    else:
        badge = '<span class="state warn">nicht eingerichtet</span>'

    parts = [f"<h1>Google Ads {badge}</h1>",
             '<p class="lead">Verbindung, Konten und Schutzgrenzen dieses Servers.</p>']

    if state["error"]:
        parts.append('<div class="card"><h2 style="margin-top:0">Meldung der API</h2>'
                     f'<pre>{esc(state["error"])}</pre></div>')

    # -- Zugangsdaten ------------------------------------------------------
    have = lambda key: "gesetzt" if config.get(key) else "fehlt"  # noqa: E731
    parts.append(f"""<div class="card">
<h2 style="margin-top:0">Zugangsdaten</h2>
<table>
<tr><th>Client-ID</th><td class="mono">{esc(config.get('client_id','') [:42])}{'…' if len(config.get('client_id','')) > 42 else ''}</td></tr>
<tr><th>Client-Geheimnis</th><td>{have('client_secret')}</td></tr>
<tr><th>Developer Token</th><td>{have('developer_token')}</td></tr>
<tr><th>Refresh Token</th><td>{have('refresh_token')}</td></tr>
<tr><th>Verwaltungskonto</th><td class="mono">{esc(config.get('login_customer_id') or '—')}</td></tr>
<tr><th>API-Fassung</th><td class="mono">{esc(config.get('api_version','—'))}</td></tr>
</table>
<div class="row">
<a class="button quiet" href="/setup/credentials">Zugangsdaten bearbeiten</a>
{'<a class="button" href="/setup/connect">Mit Google verbinden</a>'
 if config.get('client_id') and config.get('client_secret') else ''}
{'<a class="button quiet" href="/setup/check">Verbindung prüfen</a>' if state['configured'] else ''}
</div></div>""")

    # -- Konten ------------------------------------------------------------
    if state["accounts"]:
        zeilen = []
        for account in state["accounts"]:
            if account["problem"]:
                rechts = f'<span class="state bad">nicht lesbar</span><br>' \
                         f'<span class="note">{esc(account["problem"])}</span>'
            else:
                marks = " · Verwaltungskonto" if account["manager"] else ""
                rechts = (f'{esc(account["name"] or "ohne Namen")} '
                          f'<span class="note">{esc(account["currency"])}{marks}</span>')
            zeilen.append(f'<tr><th class="mono">{esc(account["id"])}</th>'
                          f'<td>{rechts}</td></tr>')
        lesbar = sum(1 for a in state["accounts"] if not a["problem"])
        parts.append(f"""<div class="card">
<h2 style="margin-top:0">Konten <span class="note">{lesbar} von
{len(state['accounts'])} lesbar</span></h2>
<table>{''.join(zeilen)}</table></div>""")

    # -- Schutzgrenzen -----------------------------------------------------
    schreiben = ('<span class="state warn">eingeschaltet</span>'
                 if rails.get("write_enabled") else '<span class="state ok">aus</span>')
    konten = ", ".join(rails.get("allowed_customer_ids") or []) or "alle zugänglichen"
    deckel = rails.get("max_daily_budget_micros") or 0
    parts.append(f"""<div class="card">
<h2 style="margin-top:0">Schutzgrenzen</h2>
<table>
<tr><th>Schreiben</th><td>{schreiben}</td></tr>
<tr><th>Erlaubte Konten</th><td class="mono">{esc(konten)}</td></tr>
<tr><th>Budgetdeckel je Tag</th><td>{f'{deckel / 1_000_000:.2f}' if deckel else 'keiner'}</td></tr>
<tr><th>Größter Budgetsprung</th><td>Faktor {esc(rails.get('max_budget_increase_factor'))}</td></tr>
<tr><th>Operationen je Aufruf</th><td>{esc(rails.get('max_operations_per_call'))}</td></tr>
</table>
<p class="note">Auch bei eingeschaltetem Schreiben ist jeder Aufruf zuerst ein
Trockenlauf — scharf wird er erst nach ausdrücklicher Freigabe im Gespräch.</p>
<a class="button quiet" href="/setup/guardrails">Schutzgrenzen bearbeiten</a></div>""")

    # -- Letzte Änderungen -------------------------------------------------
    changes = recent_changes()
    if changes:
        zeilen = []
        for entry in changes:
            art = "Trockenlauf" if entry.get("dry_run") else "<b>scharf</b>"
            zeilen.append(
                f'<tr><th class="mono">{esc(entry.get("time","")[:16].replace("T", " "))}</th>'
                f'<td>{art} · {esc(entry.get("customer_id"))} · '
                f'{esc(entry.get("operation_count"))} Operationen · '
                f'{esc(entry.get("result"))}<br>'
                f'<span class="note">{esc(entry.get("reason") or "ohne Begründung")}'
                f'</span></td></tr>')
        parts.append(f'<div class="card"><h2 style="margin-top:0">Letzte Änderungen</h2>'
                     f'<table>{"".join(zeilen)}</table></div>')

    # -- Verbindung trennen ------------------------------------------------
    if config.get("refresh_token"):
        parts.append("""<div class="card">
<h2 style="margin-top:0">Verbindung trennen</h2>
<p class="note">Löscht den Refresh Token auf diesem Server. Die Zugangsdaten
bleiben, sodass ein erneutes Verbinden ohne Eingaben auskommt. Der Zugriff
des Google-Kontos wird damit nicht widerrufen — das geschieht unter
<a href="https://myaccount.google.com/permissions" target="_blank"
rel="noopener">myaccount.google.com/permissions</a>.</p>
<form method="post" action="/setup/disconnect">
<button class="danger" type="submit">Refresh Token löschen</button>
</form></div>""")

    parts.append(f"""<div class="card">
<h2 style="margin-top:0">Zugang zu dieser Seite</h2>
<table>
<tr><th>Adresse</th><td class="mono">{esc(base_url)}/setup</td></tr>
<tr><th>Benutzername</th><td>beliebig — geprüft wird nur das Kennwort</td></tr>
<tr><th>Kennwort</th><td>das Zugangswort des Servers</td></tr>
<tr><th>MCP-Adresse</th><td class="mono">{esc(base_url)}/mcp</td></tr>
</table>
<p class="note">Dasselbe Wort öffnet beide Türen. Ein Wechsel gilt sofort und
für beide — der Connector in claude.ai muss danach neu eingetragen werden.</p>
<a class="button quiet" href="/setup/token">Zugangswort wechseln</a></div>""")
    return page("Status", "".join(parts))


def credentials_page(message: str = "") -> bytes:
    state = load_state()
    config = state["config"]
    hinweis = f'<div class="card"><p>{esc(message)}</p></div>' if message else ""
    return page("Zugangsdaten", f"""
<h1>Zugangsdaten</h1>
<p class="lead">Die vier Angaben, die Google verlangt. Zwei davon stellt Google
einer namentlich bekannten Person aus — sie können nicht erzeugt werden.</p>
{hinweis}
<form method="post" action="/setup/credentials"><div class="card">
<label>Client-ID
<span>Google Cloud Console → Anmeldedaten → OAuth-Client. Für den Weg über
diese Seite: Typ <b>Webanwendung</b>, mit der Rückadresse, die unten steht.</span>
<input type="text" name="client_id" value="{esc(config.get('client_id',''))}"
       autocomplete="off" spellcheck="false"></label>

<label>Client-Geheimnis
<span>Wird von Google nur einmal angezeigt. Leer lassen behält das gespeicherte.</span>
<input type="password" name="client_secret" placeholder="{'gespeichert' if config.get('client_secret') else ''}"
       autocomplete="off"></label>

<label>Developer Token
<span>API Center eines Verwaltungskontos. Leer lassen behält das gespeicherte.</span>
<input type="password" name="developer_token" placeholder="{'gespeichert' if config.get('developer_token') else ''}"
       autocomplete="off"></label>

<label>Verwaltungskonto (Kundennummer)
<span>Zehn Ziffern, Bindestriche erlaubt. Leer lassen, wenn die Konten direkt
erreicht werden.</span>
<input type="text" name="login_customer_id"
       value="{esc(config.get('login_customer_id',''))}" autocomplete="off"></label>

<button type="submit">Speichern</button>
<a class="button quiet" href="/setup">Zurück</a>
</div></form>""")


def connect_page(base_url: str, force_paste: bool = False) -> bytes:
    """Starts the consent flow, in whichever way the OAuth client allows."""
    try:
        config = gac.load_config()
    except gac.GoogleAdsError:
        config = {}
        if gac.CONFIG_FILE.exists():
            config = json.loads(gac.CONFIG_FILE.read_text(encoding="utf-8"))
    if not config.get("client_id") or not config.get("client_secret"):
        return page("Verbinden", """<h1>Verbinden</h1>
<div class="card"><p>Client-ID und Geheimnis fehlen noch.</p>
<a class="button" href="/setup/credentials">Zugangsdaten eintragen</a></div>""")

    verifier, challenge = pkce_pair()
    state_value = secrets.token_urlsafe(24)
    redirect_uri = f"{base_url}/setup/callback"
    url = AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": config["client_id"], "redirect_uri": redirect_uri,
        "response_type": "code", "scope": gac.OAUTH_SCOPE,
        "access_type": "offline", "prompt": "consent",
        "code_challenge": challenge, "code_challenge_method": "S256",
        "state": state_value,
    })
    PENDING_FILE.parent.mkdir(parents=True, exist_ok=True)
    PENDING_FILE.write_text(json.dumps({
        "verifier": verifier, "state": state_value, "redirect_uri": redirect_uri,
    }) + "\n", encoding="utf-8")
    os.chmod(PENDING_FILE, 0o600)

    return page("Verbinden", f"""<h1>Mit Google verbinden</h1>
<p class="lead">Melde dich mit dem Google-Konto an, das deine Ads-Konten sieht —
nicht zwingend das des Verwaltungskontos.</p>
<div class="card">
<a class="button" href="{esc(url)}">Bei Google anmelden und zustimmen</a>
<p class="note">Danach kommst du hierher zurück. Steht die App noch auf
„Test“, erscheint eine Warnung; unter „Erweitert“ lässt sie sich
übergehen. Im Testmodus läuft die Verbindung allerdings nach sieben Tagen
ab — für den Dauerbetrieb gehört die App auf „In Produktion“.</p>
</div>
<div class="card">
<h2 style="margin-top:0">Diese Rückadresse muss bei Google eingetragen sein</h2>
<pre>{esc(redirect_uri)}</pre>
<p class="note">Google Cloud Console → Anmeldedaten → dein OAuth-Client →
Autorisierte Weiterleitungs-URIs. Das geht nur bei einem Client vom Typ
<b>Webanwendung</b>. Bei einem Desktop-Client kommt stattdessen
<code>redirect_uri_mismatch</code> — dann den Weg unten nehmen.</p>
</div>
<div class="card">
<h2 style="margin-top:0">Desktop-Client: Adresse von Hand zurückgeben</h2>
<p class="note">Nach der Zustimmung landet der Browser auf einer Adresse, die
nicht lädt. Die ganze Adresszeile hier einfügen.</p>
<form method="post" action="/setup/paste">
<input type="text" name="pasted" placeholder="http://127.0.0.1:…/?state=…&amp;code=…"
       autocomplete="off" spellcheck="false">
<button type="submit">Adresse auswerten</button>
</form></div>
<p><a href="/setup">Zurück zum Status</a></p>""")


def pkce_pair() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).decode().rstrip("=")
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return verifier, base64.urlsafe_b64encode(digest).decode().rstrip("=")


def exchange_code(pasted_or_query: str) -> tuple[bool, str]:
    """Trades an authorisation code for a refresh token. Returns (ok, message)."""
    if not PENDING_FILE.exists():
        return False, ("Keine offene Anmeldung. Der Vorgang muss über „Mit Google "
                       "verbinden“ beginnen.")
    pending = json.loads(PENDING_FILE.read_text(encoding="utf-8"))
    parsed = urllib.parse.urlparse(pasted_or_query.strip())
    query = urllib.parse.parse_qs(parsed.query or pasted_or_query.strip().lstrip("?"))

    if (query.get("state") or [""])[0] != pending["state"]:
        return False, ("Die Rückmeldung trägt einen anderen Prüfwert als der "
                       "Server vergeben hat. Bitte neu beginnen.")
    code = (query.get("code") or [""])[0]
    if not code:
        return False, f"Google meldet: {(query.get('error') or ['kein Code'])[0]}"

    config = json.loads(gac.CONFIG_FILE.read_text(encoding="utf-8")) \
        if gac.CONFIG_FILE.exists() else {}
    for field, name in gac.ENV_FIELDS.items():
        if os.environ.get(name):
            config.setdefault(field, os.environ[name])

    payload = urllib.parse.urlencode({
        "code": code, "client_id": config["client_id"],
        "client_secret": config["client_secret"],
        "redirect_uri": pending["redirect_uri"],
        "grant_type": "authorization_code",
        "code_verifier": pending["verifier"],
    }).encode("utf-8")
    request = urllib.request.Request(gac.TOKEN_URL, data=payload, method="POST")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400]
        return False, ("Google hat den Code abgelehnt. Ein Code gilt nur wenige "
                       f"Minuten. Antwort: {detail}")
    except urllib.error.URLError as exc:
        return False, f"Google war nicht erreichbar: {exc.reason}"

    token = body.get("refresh_token", "")
    if not token:
        return False, ("Google hat keinen Refresh Token geschickt. Das passiert, "
                       "wenn das Konto dieser Anwendung schon zugestimmt hat. Den "
                       "Eintrag unter myaccount.google.com/permissions entfernen "
                       "und erneut verbinden.")

    config["refresh_token"] = token
    config.setdefault("api_version", gac.DEFAULT_API_VERSION)
    config["guardrails"] = dict(gac.DEFAULT_GUARDRAILS, **(config.get("guardrails") or {}))
    gac.save_config(config)
    PENDING_FILE.unlink(missing_ok=True)
    return True, "Verbunden. Der Refresh Token ist gespeichert."


def result_page(ok: bool, message: str) -> bytes:
    zustand = '<span class="state ok">erledigt</span>' if ok \
        else '<span class="state bad">fehlgeschlagen</span>'
    return page("Ergebnis", f"""<h1>Ergebnis {zustand}</h1>
<div class="card"><p>{esc(message)}</p>
<div class="row"><a class="button" href="/setup">Zum Status</a>
{'<a class="button quiet" href="/setup/connect">Erneut versuchen</a>' if not ok else ''}
</div></div>""")


def check_page() -> bytes:
    """Runs the same checks as google-ads-check.py and shows them as a table."""
    state = load_state()
    zeilen = []

    def zeile(name, ok, text):
        marke = ('<span class="state ok">ok</span>' if ok
                 else '<span class="state bad">Befund</span>')
        zeilen.append(f'<tr><th>{esc(name)}</th><td>{marke} {esc(text)}</td></tr>')

    zeile("Konfiguration", state["configured"],
          "vollständig" if state["configured"] else state["error"].splitlines()[0])
    if state["configured"]:
        zeile("Zugang", state["connected"],
              "die API antwortet" if state["connected"]
              else state["error"].splitlines()[0])
        lesbar = [a for a in state["accounts"] if not a["problem"]]
        zeile("Konten", bool(lesbar),
              f"{len(lesbar)} von {len(state['accounts'])} lesbar")

        if lesbar:
            client = gac.Client(state["config"])
            try:
                client.call("POST", f"customers/{lesbar[0]['id']}:"
                                    "generateKeywordHistoricalMetrics",
                            {"keywords": ["test"], "language": "languageConstants/1001",
                             "geoTargetConstants": ["geoTargetConstants/2040"],
                             "keywordPlanNetwork": "GOOGLE_SEARCH"})
                zeile("Keyword-Planer", True, "verfügbar — Zugriffsstufe Basic oder höher")
            except gac.GoogleAdsError:
                zeile("Keyword-Planer", True,
                      "gesperrt — Zugriffsstufe Explorer. Elf der dreizehn Werkzeuge "
                      "laufen, der Keyword-Planer nicht")

    rails = state["guardrails"]
    zeile("Schutzgrenzen", True,
          "Schreiben aus" if not rails.get("write_enabled")
          else f"Schreiben ein, Konten: "
               f"{', '.join(rails.get('allowed_customer_ids') or ['ALLE']) }")

    return page("Prüfung", f"""<h1>Verbindung geprüft</h1>
<p class="lead">Dieselben Prüfungen wie <code>google-ads-check.py</code>.</p>
<div class="card"><table>{''.join(zeilen)}</table></div>
<a class="button" href="/setup">Zurück zum Status</a>""")


def save_credentials(form: dict) -> tuple[bool, str]:
    """Writes the four values, keeping stored secrets when a field is left empty."""
    config = {}
    if gac.CONFIG_FILE.exists():
        try:
            config = json.loads(gac.CONFIG_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            config = {}

    client_id = (form.get("client_id") or [""])[0].strip()
    if not client_id:
        return False, "Die Client-ID darf nicht leer sein."
    config["client_id"] = client_id

    for field in ("client_secret", "developer_token"):
        value = (form.get(field) or [""])[0].strip()
        if value:
            config[field] = value
        elif not config.get(field):
            return False, f"Das Feld {field} ist noch nicht gesetzt."

    login = (form.get("login_customer_id") or [""])[0].strip()
    if login:
        try:
            config["login_customer_id"] = gac.normalize_customer_id(login)
        except gac.GoogleAdsError as exc:
            return False, exc.message
    else:
        config["login_customer_id"] = ""

    config.setdefault("api_version", gac.DEFAULT_API_VERSION)
    config["guardrails"] = dict(gac.DEFAULT_GUARDRAILS, **(config.get("guardrails") or {}))
    gac.CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    gac.CONFIG_FILE.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n",
                               encoding="utf-8")
    os.chmod(gac.CONFIG_FILE, 0o600)
    return True, "Gespeichert."


def env_overrides() -> dict:
    """Which guardrails come from the environment and are therefore fixed here.

    A value set in the container's .env wins over the configuration file.
    Editing it on this page would write something that never takes effect,
    so the form shows it as locked and names where it comes from instead of
    quietly losing the change.
    """
    return {field: name for field, name in gac.GUARDRAIL_ENV.items()
            if os.environ.get(name) is not None}


def guardrails_page(message: str = "") -> bytes:
    """The page that replaces editing the .env by hand."""
    state = load_state()
    rails = state["guardrails"]
    fest = env_overrides()
    erlaubt = set(rails.get("allowed_customer_ids") or [])

    def gesperrt(field: str) -> str:
        if field not in fest:
            return ""
        return (f'<span class="note">Kommt aus der Umgebung '
                f'(<code>{esc(fest[field])}</code>) und ist hier nicht änderbar. '
                f'Aus der <code>.env</code> entfernen, um ihn hier zu setzen.</span>')

    # Die Konten zum Anhaken, statt Nummern zu tippen.
    def kasten(wert: str, titel: str, zusatz: list[str], an: bool) -> str:
        sperre = " disabled" if "allowed_customer_ids" in fest else ""
        rand = f'<span class="note">{esc(" · ".join(zusatz))}</span>' if zusatz else ""
        return (f'<label class="kasten"><input type="checkbox" name="konto" '
                f'value="{esc(wert)}"{" checked" if an else ""}{sperre}>'
                f'<span class="kasten-text"><b>{esc(titel)}</b>'
                f'<span class="mono">{esc(wert)}</span>{rand}</span></label>')

    kaesten = []
    for account in state["accounts"]:
        zusatz = []
        if account.get("currency"):
            zusatz.append(account["currency"])
        if account.get("manager"):
            zusatz.append("Verwaltungskonto")
        if account["problem"]:
            zusatz.append("nicht lesbar")
        kaesten.append(kasten(account["id"], account["name"] or "ohne Namen",
                              zusatz, account["id"] in erlaubt))
    # Berechtigte Konten, die gerade nicht in der Liste stehen, gingen sonst
    # beim Speichern still verloren.
    for verwaist in sorted(erlaubt - {a["id"] for a in state["accounts"]}):
        kaesten.append(kasten(verwaist, "steht gerade nicht in der Liste", [], True))

    if state["accounts"]:
        konten_feld = ("".join(kaesten)
                       + '<input type="hidden" name="konten_gestellt" value="1">')
    elif kaesten:
        # Die Liste liess sich nicht lesen. Ohne den Merker rührt das Speichern
        # die Berechtigung nicht an — sonst hiesse ein Klick nach einer
        # Störung plötzlich "alle Konten", und das in die andere Richtung.
        grund = f' ({esc(state["error"].splitlines()[0])})' if state["error"] else ""
        konten_feld = (f'<p class="warnung">Die Kontenliste liess sich gerade nicht '
                       f'lesen{grund}. Was berechtigt ist, steht unten und bleibt beim '
                       f'Speichern unverändert. Zum Ändern zuerst die Verbindung '
                       f'prüfen.</p>' + "".join(kaesten))
    else:
        konten_feld = ('<p class="note">Noch keine Konten gelesen. Erst verbinden, '
                       'dann stehen sie hier zum Anhaken.</p>')

    hinweis = f'<div class="card akzent"><p>{esc(message)}</p></div>' if message else ""
    deckel = rails.get("max_daily_budget_micros") or 0
    schreibt = "checked" if rails.get("write_enabled") else ""

    return page("Schutzgrenzen", f"""
<h1>Schutzgrenzen</h1>
<p class="lead">Was überhaupt möglich ist. Ob eine einzelne Änderung dann
geschieht, entscheidet die Freigabe im Gespräch — jeder Schreibaufruf ist
zuerst ein Trockenlauf.</p>
{hinweis}
<form method="post" action="/setup/guardrails">

<div class="card">
<h2 style="margin-top:0">Schreiben</h2>
<label class="kasten"><input type="checkbox" name="write_enabled" {schreibt}
  {'disabled' if 'write_enabled' in fest else ''}>
<span class="kasten-text"><b>Schreiben erlauben</b>
<span class="note">Ohne diesen Haken sind nur Trockenläufe möglich. Lesen
geht immer.</span></span></label>
{gesperrt('write_enabled')}
</div>

<div class="card">
<h2 style="margin-top:0">Konten, in die geschrieben werden darf</h2>
<p class="note" style="margin-top:0">Kein Haken heißt <b>alle zugänglichen</b> —
bei eingeschaltetem Schreiben ist das selten gemeint.</p>
{konten_feld}
{gesperrt('allowed_customer_ids')}
</div>

<div class="card">
<h2 style="margin-top:0">Budget</h2>
<label>Höchstes Tagesbudget je Budget
<span>In deiner Kontowährung. 0 heißt: keine Obergrenze.</span>
<input type="text" name="max_daily_budget" value="{deckel / 1_000_000:.2f}"
  {'disabled' if 'max_daily_budget_micros' in fest else ''}></label>
{gesperrt('max_daily_budget_micros')}

<label>Größter Sprung in einem Schritt
<span>Faktor. 2 heißt: höchstens verdoppeln.</span>
<input type="text" name="max_budget_increase_factor"
  value="{esc(rails.get('max_budget_increase_factor'))}"
  {'disabled' if 'max_budget_increase_factor' in fest else ''}></label>
{gesperrt('max_budget_increase_factor')}

<label>Operationen je Aufruf
<span>Begrenzt den Schaden eines einzelnen Fehlgriffs.</span>
<input type="text" name="max_operations_per_call"
  value="{esc(rails.get('max_operations_per_call'))}"
  {'disabled' if 'max_operations_per_call' in fest else ''}></label>
{gesperrt('max_operations_per_call')}
</div>

<button type="submit">Speichern</button>
<a class="button quiet" href="/setup">Abbrechen</a>
</form>""")


def save_guardrails(form: dict) -> tuple[bool, str]:
    """Writes the guardrails to the configuration file.

    Values that the environment sets are skipped: writing them would
    produce a file that says one thing while the server does another.
    """
    config = {}
    if gac.CONFIG_FILE.exists():
        try:
            config = json.loads(gac.CONFIG_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            config = {}
    rails = dict(gac.DEFAULT_GUARDRAILS, **(config.get("guardrails") or {}))
    fest = env_overrides()
    uebergangen = []

    if "write_enabled" in fest:
        uebergangen.append(gac.GUARDRAIL_ENV["write_enabled"])
    else:
        rails["write_enabled"] = bool(form.get("write_enabled"))

    unberuehrt = False
    if "allowed_customer_ids" in fest:
        uebergangen.append(gac.GUARDRAIL_ENV["allowed_customer_ids"])
    elif not form.get("konten_gestellt"):
        # Das Formular kam von einer Seite, die die Konten nicht anzeigen
        # konnte. Kein Haken hiesse dort nicht "keine Einschränkung", sondern
        # nur "nichts gesehen" — also wird hier nichts angerührt.
        unberuehrt = True
    else:
        konten = []
        for wert in form.get("konto") or []:
            try:
                konten.append(gac.normalize_customer_id(wert))
            except gac.GoogleAdsError as exc:
                return False, exc.message
        rails["allowed_customer_ids"] = konten

    # Formularfeld, Ziel in den Schutzgrenzen, Faktor, ganzzahlig
    zahlen = (("max_daily_budget", "max_daily_budget_micros", 1_000_000, True),
              ("max_budget_increase_factor", "max_budget_increase_factor", 1, False),
              ("max_operations_per_call", "max_operations_per_call", 1, True))
    for feldname, ziel, faktor, ganzzahlig in zahlen:
        if ziel in fest:
            uebergangen.append(gac.GUARDRAIL_ENV[ziel])
            continue
        roh = (form.get(feldname) or [""])[0].strip().replace(",", ".")
        if not roh:
            continue
        try:
            wert = float(roh) * faktor
        except ValueError:
            return False, f"„{roh}“ ist keine Zahl."
        if wert < 0:
            return False, "Negative Werte ergeben hier keinen Sinn."
        rails[ziel] = int(wert) if ganzzahlig else wert

    config["guardrails"] = rails
    config.setdefault("api_version", gac.DEFAULT_API_VERSION)
    gac.CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    gac.CONFIG_FILE.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n",
                               encoding="utf-8")
    os.chmod(gac.CONFIG_FILE, 0o600)

    meldung = "Gespeichert."
    if unberuehrt:
        meldung += (" Die Kontenberechtigung blieb unverändert, weil die Kontenliste "
                    "beim Aufbau der Seite nicht lesbar war.")
    if uebergangen:
        meldung += (" Übergangen wurde, was die Umgebung vorgibt: "
                    + ", ".join(sorted(set(uebergangen)))
                    + ". Diese Werte gelten weiter aus der .env.")
    return True, meldung


def rotate_token(token_file: pathlib.Path) -> tuple[bool, str]:
    """Replaces the access word with a fresh one.

    Kept next to the other management actions because the alternative is
    an SSH session for something the page already has the authority to do.
    The old word stops working the moment this returns.
    """
    import secrets as _secrets
    token = _secrets.token_urlsafe(48)
    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text(token + "\n", encoding="utf-8")
    os.chmod(token_file, 0o600)
    return True, token


def token_page(token_file: pathlib.Path, neues: str = "") -> bytes:
    if neues:
        return page("Zugangswort", f"""<h1>Neues Zugangswort</h1>
<div class="card akzent">
<p>Ab sofort gilt dieses Wort. Das alte ist ungültig — auch für den
Connector in claude.ai, der neu eingetragen werden muss.</p>
<pre>{esc(neues)}</pre>
<p class="note">Jetzt in einen Passwortspeicher übernehmen. Diese Seite zeigt
es kein zweites Mal; danach steht es nur noch in
<code>{esc(token_file)}</code> auf dem Server.</p>
<a class="button" href="/setup">Zum Status</a></div>""")
    return page("Zugangswort", """<h1>Zugangswort wechseln</h1>
<p class="lead">Das Wort ist zugleich das Kennwort dieser Seite und der
Schlüssel des MCP-Endpunkts.</p>
<div class="card">
<p>Ein Wechsel macht das alte Wort sofort ungültig. Der Connector in
claude.ai trägt das alte und muss danach neu eingetragen werden — bis dahin
antwortet der Server ihm mit einer Abweisung.</p>
<form method="post" action="/setup/token">
<button class="danger" type="submit">Neues Zugangswort erzeugen</button>
<a class="button quiet" href="/setup">Abbrechen</a>
</form></div>""")


def disconnect() -> tuple[bool, str]:
    """Forgets the refresh token, keeps everything else."""
    if not gac.CONFIG_FILE.exists():
        return False, "Es gibt keine Konfiguration."
    config = json.loads(gac.CONFIG_FILE.read_text(encoding="utf-8"))
    if not config.pop("refresh_token", None):
        return False, "Es war kein Refresh Token gespeichert."
    gac.CONFIG_FILE.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n",
                               encoding="utf-8")
    os.chmod(gac.CONFIG_FILE, 0o600)
    PENDING_FILE.unlink(missing_ok=True)
    return True, ("Der Refresh Token ist gelöscht. Die Zugangsdaten bleiben, ein "
                  "erneutes Verbinden kommt ohne Eingaben aus.")
