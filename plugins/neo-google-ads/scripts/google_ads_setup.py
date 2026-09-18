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

THE PAGE IS AS SENSITIVE AS THE SERVER ITSELF, so it lives behind the
portal's sign-in — a real account with a password and, if switched on, a
second factor. That is portal_store and portal_pages; this file assumes a
person got past them and draws the Google half.

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
import threading
import pathlib
import secrets
import urllib.error
import urllib.parse
import urllib.request

import google_ads_client as gac

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
PENDING_FILE = gac.CONFIG_FILE.parent / "pending-auth.json"

# Der Name, unter dem diese Anwendung auftritt: im Seitentitel, in der
# Kopfzeile und in der Authenticator-App.
#
# Er darf KEINE Google-Marke enthalten. Googles OAuth-Pruefung weist einen
# Anwendungsnamen mit "Google" darin ab, und der Name der Seite muss zu dem
# passen, der im Zustimmungsbildschirm eingetragen ist. Beschreibende Saetze
# wie "Zugang zu Google Ads" sind davon nicht betroffen — nur der Name.
#
# Sie steht in google_ads_client.py, weil der MCP-Server denselben Namen
# als Anzeigenamen des Connectors braucht und beide Dateien ihn teilen.
MARKE = gac.PORTAL_NAME


def marke_beiwort() -> str:
    """Was neben der Wortmarke steht: der Name ohne das, was das Logo schon sagt."""
    return MARKE[4:].strip() if MARKE.upper().startswith("NEO ") else MARKE

# Das Favicon, wie geliefert: grünes Zeichen auf dem Markenviolett. Als
# data:-URI eingebettet, damit die Seite eine Datei weniger ausliefern muss
# und im Tab sofort steht — ein zweiter Abruf für 500 Byte lohnt nicht.
FAVICON = "data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20viewBox%3D%220%200%2016%2016%22%3E%3Crect%20width%3D%2216%22%20height%3D%2216%22%20fill%3D%22%232a025f%22%2F%3E%3Cg%20fill%3D%22%23a8f20d%22%3E%3Cpolygon%20points%3D%223.98%207.6%204.54%208.03%204.54%2013.86%202.2%2013.86%202.2%206.26%203.98%207.6%22%2F%3E%3Cpolygon%20points%3D%2213.8%202.14%2013.8%209.75%2012.02%208.4%2011.46%207.97%2011.46%202.14%2013.8%202.14%22%2F%3E%3Cpolygon%20points%3D%2213.8%2010.92%2013.8%2013.86%2013.8%2013.86%2011.46%2012.09%204.54%206.85%202.2%205.08%202.2%202.14%202.2%202.14%204.54%203.91%2011.46%209.15%2013.8%2010.92%22%2F%3E%3C%2Fg%3E%3C%2Fsvg%3E"

# Die NEO-Wortmarke, wie sie aus Illustrator kommt — nur ohne die
# eingebettete Klasse: fill="currentColor" am Wurzelelement laesst sie die
# Akzentfarbe der Seite annehmen, sodass eine Variable alles aendert. Eine
# eigene Datei unter /data/logo.svg wird stattdessen ausgeliefert.
LOGO = """<svg viewBox="0 0 449.49 143.2" role="img" aria-label="NEO Digital"
  fill="currentColor" xmlns="http://www.w3.org/2000/svg">
<polygon points="21.72 66.74 28.64 71.98 28.64 143.2 0 143.2 0 50.29 21.72 66.74"/>
<polygon points="141.67 0 141.67 92.92 119.95 76.47 113.04 71.23 113.04 0 141.67 0"/>
<polygon points="141.67 107.29 141.67 143.2 141.66 143.2 113.04 121.52 28.64 57.61 0 35.92 0 0 .01 0 28.64 21.69 113.04 85.6 141.67 107.29"/>
<rect x="153.14" y="0" width="141.67" height="28.64"/>
<rect x="153.14" y="114.56" width="141.67" height="28.64"/>
<rect x="153.14" y="57.28" width="141.67" height="28.64"/>
<path d="M420.85 28.64v85.92h-85.92V28.64h85.92ZM449.49 0H306.29v143.2h143.2V0h0Z"/>
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
  --neon:    #a8f20d;   /* NEO-Grün             13,1:1 auf --card       */
  --neon-dim:#7fb80a;   /* dasselbe Grün ruhiger  7,5:1 auf --card       */
  --neon-up: #bcff33;   /* heller, für Hover     16,1:1 auf --bg         */
  --warn:    #FFB454;   /* Hinweis              10,2:1 auf --card       */
  /* Das Markenviolett. NUR auf hellen Flächen: auf --bg läge es bei
     1,3:1 und wäre schlicht unsichtbar. Hier steht es deshalb allein auf
     der weißen Kachel des QR-Codes, wo es 16,4:1 erreicht. */
  --violett: #2a025f;
  --bad:     #FF6B5C;   /* Befund                6,4:1 auf --card       */
}
* { box-sizing: border-box; }
html { color-scheme: dark; }
body { margin: 0; background: var(--bg); color: var(--fg);
  font: 16px/1.6 "Segoe UI Variable Text", "Segoe UI", system-ui, -apple-system,
        "SF Pro Text", Roboto, "Helvetica Neue", Arial, sans-serif;
  font-synthesis-weight: none;
  -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale; }

/* Überschriften enger und schwerer als der Fließtext: bei einer Seite ohne
   Bilder macht die Typografie die Gliederung, nicht das Layout. */
h1, h2, h3 { font-family: "Segoe UI Variable Display", "Segoe UI", system-ui,
             -apple-system, "SF Pro Display", sans-serif;
             letter-spacing: -.021em; text-wrap: balance; }
h1 { font-size: 1.9rem; font-weight: 650; line-height: 1.2; margin: 0 0 .5rem; }
h2 { font-size: 1.12rem; font-weight: 620; letter-spacing: -.012em;
     margin: 2rem 0 .8rem; }
p.lead { color: var(--muted); font-size: 1.02rem; max-width: 42em;
         margin: 0 0 1.8rem; }
table { font-variant-numeric: tabular-nums; }
main { max-width: 54rem; margin: 0 auto; padding: 2.5rem 1rem 5rem; }

header.marke { display: flex; align-items: center; gap: 1rem;
  padding-bottom: 1.5rem; margin-bottom: 2rem;
  border-bottom: 1px solid var(--line); }
header.marke svg { height: 1.55rem; width: auto; color: var(--neon);
  filter: drop-shadow(0 0 18px color-mix(in srgb, var(--neon) 28%, transparent)); }
header.marke .button.klein { margin-left: 1rem; padding: .38rem .9rem;
                            font-size: .85rem; }
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

/* Ein Zustand ist eine Fußnote zur Überschrift, kein zweiter Titel. Also
   klein, in Grundschrift, mit einem Punkt davor statt Versalien in einer
   farbigen Pille. */
.state { display: inline-flex; align-items: center; gap: .4rem;
  padding: .16rem .55rem .16rem .5rem; border-radius: .35rem;
  font-size: .8rem; font-weight: 600; letter-spacing: 0;
  vertical-align: middle; position: relative; top: -.12em;
  font-family: inherit; }
.state::before { content: ""; width: .42rem; height: .42rem; border-radius: 50%;
  background: currentColor; flex: none; }
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
input[type=text], input[type=password], input[type=email] {
  width: 100%; padding: .62rem .8rem;
  margin-top: .45rem; border: 1px solid var(--line); border-radius: .45rem;
  background: var(--bg); color: var(--fg);
  font-family: ui-monospace, Menlo, monospace; font-size: .9rem;
  transition: border-color .12s, box-shadow .12s; }
input[type=text]:hover, input[type=password]:hover, input[type=email]:hover {
  border-color: color-mix(in srgb, var(--neon) 30%, var(--line)); }
/* Ein Ring, kein Rahmen: 1px in der Markenfarbe plus ein weicher Schein.
   Der 2px-Umriss von vorher sass aussen auf der Ecke und wirkte wie ein
   Fehler, nicht wie ein Fokus. */
input:focus { outline: none; border-color: var(--neon);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--neon) 22%, transparent); }
input[type=text]:-webkit-autofill, input[type=password]:-webkit-autofill {
  -webkit-text-fill-color: var(--fg);
  -webkit-box-shadow: 0 0 0 40rem var(--bg) inset; }

button, .button { display: inline-block; padding: .62rem 1.15rem; border-radius: .5rem;
  border: 1px solid transparent; background: var(--neon); color: #07120A;
  font: inherit; font-weight: 620; font-size: .92rem; cursor: pointer;
  letter-spacing: -.005em; transition: background .12s, border-color .12s;
  text-decoration: none; margin-top: 1.4rem; }
button:hover, .button:hover { background: var(--neon-up); }
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
/* Der QR-Code bleibt weiss auf weiss: ein Scanner erwartet dunkel auf hell,
   und eine Umkehrung kostet auf manchen Kameras die Erkennung. */
/* Feste Breite statt voller Kachel: ein Code von 57 Modulen wird sonst
   riesig und schiebt alles andere aus dem Bild. 15rem reichen jeder
   Telefonkamera aus Armlänge. */
.qr svg { display: block; width: 15rem; max-width: 100%; height: auto; }
ol.schritte { margin: .6rem 0 0; padding-left: 1.3rem; color: var(--fg);
             font-size: .9rem; line-height: 1.6; }
ol.schritte li { margin-bottom: .35rem; }
ol.schritte li::marker { color: var(--neon-dim); font-weight: 700; }
ol.codes { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr));
           gap: .45rem 1.2rem; margin: 0; padding-left: 1.4rem; }
ol.codes li { font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
              font-size: 1rem; letter-spacing: .04em; }
@media (max-width: 34rem) { ol.codes { grid-template-columns: 1fr; } }
.card.schlecht { border-color: color-mix(in srgb, var(--bad) 45%, var(--line)); }
/* Die schmale Spalte: Anmeldung und zweiter Faktor. Eine Karte, zwei
   Felder, mittig — und das Logo darüber statt einer Kopfleiste. */
body.schmal main { max-width: 25rem; padding-top: 4.5rem; }
body.schmal header.marke { justify-content: center; border-bottom: none;
  padding-bottom: 0; margin-bottom: 2.2rem; }
body.schmal header.marke svg { height: 2.1rem; }
body.schmal header.marke .wo { display: none; }
body.schmal h1 { font-size: 1.45rem; text-align: center; }
body.schmal p.lead { text-align: center; margin-bottom: 1.6rem; font-size: .95rem; }
body.schmal button[type=submit] { width: 100%; padding: .72rem 1rem; }
body.schmal .card { padding: 1.5rem 1.35rem; margin-bottom: 1.1rem; }
body.schmal .card p.note:last-of-type { margin-bottom: 0; }
body.schmal form { margin: 0; }
body.schmal > main > p.note { text-align: center; margin-top: 1.8rem;
  font-size: .82rem; }
@media (max-width: 34rem) { body.schmal main { padding-top: 2.5rem; } }

/* Die weiße Kachel des QR-Codes ist die einzige helle Fläche der Seite —
   und damit die einzige, auf der das Markenviolett lesbar ist. */
.qr { background: #fff; border-radius: .6rem; padding: 1.1rem 1.1rem .8rem;
      display: flex; flex-direction: column; align-items: center; gap: .5rem;
      width: fit-content; margin: 0 auto; }
.qr figcaption { color: var(--violett); font-size: .8rem; font-weight: 600;
                 letter-spacing: .01em; }

nav.nav { display: flex; align-items: center; gap: 1.1rem; flex-wrap: wrap;
          margin: -1rem 0 2rem; padding-bottom: 1rem;
          border-bottom: 1px solid var(--line); font-size: .9rem; }
nav.nav .wer { margin-left: auto; color: var(--muted); display: flex;
               align-items: center; gap: .5rem; }
nav.nav form.raus { margin: 0; }
nav.nav .button { padding: .35rem .8rem; font-size: .85rem; }
@media (max-width: 34rem) {
  nav.nav .wer { margin-left: 0; width: 100%; order: -1; }
}
.warnung { border-left: 3px solid var(--warn); padding: .1rem 0 .1rem .8rem;
           margin: 0 0 1rem; color: var(--text); font-size: .9rem;
           line-height: 1.55; }
a { color: var(--neon); text-underline-offset: .2em; }
a:hover { color: #c4ff4d; }

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


_viewer = threading.local()


def set_viewer(name: str = "", *, two_factor: bool = False) -> None:
    """Who the current request belongs to. Per thread, because the server is."""
    _viewer.name = name
    _viewer.two_factor = two_factor


def viewer() -> tuple[str, bool]:
    return getattr(_viewer, "name", ""), getattr(_viewer, "two_factor", False)


def navigation() -> str:
    name, two_factor = viewer()
    if not name:
        return ""
    schild = ('<span class="state ok">2FA</span>' if two_factor
              else '<span class="state warn">ohne 2FA</span>')
    return (f'<nav class="nav"><a href="/setup">Übersicht</a>'
            f'<a href="/setup/guardrails">Schutzgrenzen</a>'
            f'<a href="/konto">Konto</a>'
            f'<span class="wer">{esc(name)} {schild}</span>'
            f'<form method="post" action="/abmelden" class="raus">'
            f'<button class="button quiet" type="submit">Abmelden</button></form></nav>')


# Auf den oeffentlichen Seiten steht oben rechts nur der Weg hinein. Er
# sitzt in der Kopfleiste selbst, damit keine leere Zeile darunter klafft.
OEFFENTLICHER_KOPF = '<a class="button quiet klein" href="/anmelden">Anmelden</a>' 


def logo_markup() -> str:
    """The built-in word mark, or the operator's own file if one is there."""
    eigen = gac.CONFIG_FILE.parent / "logo.svg"
    if eigen.exists():
        try:
            return eigen.read_text(encoding="utf-8")
        except OSError:
            pass
    return LOGO


def page(title: str, body: str, *, schmal: bool = False, leiste: str = "",
         kopf_rechts: str = "") -> bytes:
    """One HTML document. No framework, no build step, nothing to update.

    schmal is for the pages with one job and two fields — signing in, the
    second factor. A form of 54rem width with two inputs in it looks like
    a mistake, because it is one: the eye has to travel the whole line to
    find a field that is 20 characters long.
    """
    klasse = " class=\"schmal\"" if schmal else ""
    # Eine schmale Seite hat genau eine Aufgabe. Eine Navigationsleiste
    # darüber böte Wege an, die alle sofort hierher zurückführen — auf der
    # erzwungenen Kennwortseite tat sie genau das.
    if not leiste:
        leiste = "" if schmal else navigation()
    # Auf der Startseite heisst die Seite wie die Anwendung — dann nicht
    # zweimal dasselbe in den Titel schreiben.
    titel_zeile = title if title == MARKE else f"{title} — {MARKE}"
    return (f"""<!doctype html>
<html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark">
<meta name="robots" content="noindex, nofollow">
<link rel="icon" href="{FAVICON}">
<title>{html.escape(titel_zeile)}</title>
<style>{STYLE}</style></head>
<body{klasse}><main>
<header class="marke">{logo_markup()}<span class="wo">{esc(marke_beiwort())}</span>{kopf_rechts}</header>
{leiste}
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
                 "problem": "", "code": ""}
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
            # Nicht nur die erste Zeile: die ist Googles eigener Satz
            # ("The caller does not have permission") und nennt weder das
            # Konto noch den Grund. Der Fehlercode steht darunter.
            code = gac.error_code_of(exc)
            entry["problem"] = exc.message.splitlines()[0]
            entry["code"] = code
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

def startseite(base_url: str = "") -> bytes:
    """Die oeffentliche Startseite. Ohne Anmeldung, mit Absicht.

    Googles Pruefung des Brandings hat drei Dinge bemaengelt, und alle
    drei haengen an dieser einen Seite:

        "Fuer den Zugriff auf Ihre Startseite ist eine Anmeldung
         erforderlich."       -> / leitete auf /anmelden
        "Auf Ihrer Startseite wird nicht erklaert, wozu die App dient."
        "Der ... Anwendungsname stimmt nicht mit dem Anwendungsnamen auf
         der Startseite ueberein."

    Also: erreichbar ohne Anmeldung, der Name im Wortlaut des
    Zustimmungsbildschirms als Ueberschrift, und darunter in Saetzen, was
    die Anwendung tut und welche Daten sie warum anfasst. Sie zeigt
    nichts an, was nicht jeder sehen darf — kein Kontostand, keine
    Kennzahl, keine Kundennummer.
    """
    kontakt = (f'<a href="mailto:{esc(gac.PORTAL_CONTACT)}">'
               f'{esc(gac.PORTAL_CONTACT)}</a>' if gac.PORTAL_CONTACT else
               '<span class="note">(GOOGLE_ADS_PORTAL_CONTACT ist nicht gesetzt)</span>')
    set_viewer("")
    return page(MARKE, f"""
<h1>{esc(MARKE)}</h1>
<p class="lead">Ein Werkzeug zur Verwaltung von Google-Ads-Konten,
betrieben von {esc(gac.PORTAL_OPERATOR)} für die eigenen Konten und die
betreuter Kunden.</p>

<div class="card">
<h2 style="margin-top:0">Wozu diese Anwendung dient</h2>
<p style="margin-top:0">{esc(MARKE)} liest Kampagnen, Anzeigengruppen,
Keywords, Suchbegriffe, Budgets und Kennzahlen aus den Google-Ads-Konten,
zu denen der angemeldete Nutzer bereits Zugang hat, und bereitet sie zur
Auswertung auf. Nach ausdrücklicher Freigabe im Einzelfall schreibt sie
auch zurück: Keywords und ausschließende Keywords pflegen, Status von
Kampagnen und Anzeigengruppen ändern, Budgets und Gebote anpassen.</p>
<p>Jeder schreibende Aufruf läuft zuerst als Trockenlauf gegen Googles
eigene Regelprüfung und verändert dabei nichts. Scharf wird er nur, wenn
er einzeln bestätigt wird. Budgetobergrenzen und eine Liste erlaubter
Konten begrenzen, was überhaupt möglich ist; jeder Versuch steht mit
Zeitpunkt, Konto, Begründung und Ergebnis im Änderungsprotokoll.</p>
</div>

<div class="card">
<h2 style="margin-top:0">Welche Google-Daten verwendet werden</h2>
<table>
<tr><th>Berechtigung</th><td class="mono">{esc(gac.OAUTH_SCOPE)}</td></tr>
<tr><th>Wofür</th><td>Zugriff auf die Google Ads API, um die oben
genannten Daten zu lesen und — nach Freigabe — zu ändern.</td></tr>
<tr><th>Wo die Daten liegen</th><td>Ausschließlich auf dem Server, auf
dem diese Anwendung läuft. Es gibt keine Weitergabe an Dritte und keine
Auswertung über Konten hinweg.</td></tr>
</table>
<p class="note">Die Anwendung greift nur auf Konten zu, für die das
verbundene Google-Konto ohnehin schon berechtigt ist. Sie kann keine
Berechtigung erteilen, die nicht bereits in Google Ads besteht.</p>
</div>

<div class="card">
<h2 style="margin-top:0">Wer sie betreibt</h2>
<table>
<tr><th>Betreiber</th><td>{esc(gac.PORTAL_OPERATOR)}</td></tr>
<tr><th>Kontakt</th><td>{kontakt}</td></tr>
<tr><th>Zugang</th><td>Nicht öffentlich. Die Verwaltung steht nur
Mitarbeitern des Betreibers offen.</td></tr>
</table>
</div>

<div class="row">
<a class="button" href="/anmelden">Zur Verwaltung anmelden</a>
<a class="button quiet" href="{esc(gac.PORTAL_IMPRESSUM)}"
   target="_blank" rel="noopener">Impressum</a>
<a class="button quiet" href="{esc(gac.PORTAL_DATENSCHUTZ)}"
   target="_blank" rel="noopener">Datenschutz</a>
</div>

<div class="card">
<h2 style="margin-top:0">In English</h2>
<p class="note" style="margin-top:0"><b>{esc(MARKE)}</b> is an internal
tool operated by {esc(gac.PORTAL_OPERATOR)} to manage Google Ads accounts
— its own and those of the clients it looks after. It reads campaigns, ad
groups, keywords, search terms, budgets and performance figures from the
accounts the signed-in user already has access to, and writes back only
after an explicit, case-by-case approval. Every write runs as a dry run
against Google's own validation first. Data stays on the server this runs
on and is never shared with third parties. Access is restricted to staff
of the operator.</p>
</div>""", kopf_rechts=OEFFENTLICHER_KOPF)


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
<tr><th>Cloud-Projekt</th><td class="mono">{esc(gac.project_number_of(config.get('client_id','')) or '—')}<br>
<span class="note">Daran hängt die Zugriffsstufe, nicht am Developer Token.</span></td></tr>
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
                code = (f'<br><span class="mono" style="font-size:.8rem">'
                        f'{esc(account["code"])}</span>' if account.get("code") else "")
                rechts = (f'<span class="state bad">nicht lesbar</span>{code}<br>'
                          f'<span class="note">{esc(account["problem"])}</span>')
            else:
                marks = " · Verwaltungskonto" if account["manager"] else ""
                rechts = (f'{esc(account["name"] or "ohne Namen")} '
                          f'<span class="note">{esc(account["currency"])}{marks}</span>')
            zeilen.append(f'<tr><th class="mono">{esc(account["id"])}</th>'
                          f'<td>{rechts}</td></tr>')
        lesbar = sum(1 for a in state["accounts"] if not a["problem"])
        nicht_lesbar = len(state["accounts"]) - lesbar
        codes = {a.get("code", "") for a in state["accounts"] if a.get("code")}
        projekt = gac.project_number_of(config.get("client_id", ""))
        hinweis = ""
        if any("CLOUD_PROJECT_NOT_APPROVED" in c for c in codes):
            # Der Fehlercode ist eindeutig. Dann nicht auf den
            # Verwaltungskopf raten und auch nicht zum Messen schicken:
            # keine Kopfzeile der Welt hebt eine fehlende Freigabe auf.
            hinweis = (f'<p class="note"><b>Das ist nicht der Verwaltungskopf.</b> '
                       f'<code>CLOUD_PROJECT_NOT_APPROVED_FOR_PRODUCTION</code> heißt: '
                       f'das Google-Cloud-Projekt '
                       f'<span class="mono">{esc(projekt)}</span> darf noch nicht auf '
                       f'echte Konten zugreifen — es steht auf Zugriffsstufe Test.</p>'
                       f'<p class="note">Freischalten in der Google Cloud Console, in '
                       f'genau diesem Projekt: <b>Google Ads API → Übersicht → '
                       f'Zugriffsstufe hochstufen → Zugriff beantragen</b>. Die '
                       f'Markenprüfung des Zustimmungsbildschirms muss vorher durch '
                       f'sein. Google stuft oft sofort hoch, prüft sonst bis zu zehn '
                       f'Werktage.</p>'
                       f'<p class="note">Schneller geht es, wenn ein <b>anderes, bereits '
                       f'freigeschaltetes Projekt</b> vorhanden ist: den OAuth-Client '
                       f'dort anlegen und die neue Kennung hier eintragen. Dann ist '
                       f'nichts zu beantragen.</p>'
                       f'<div class="row">'
                       f'<a class="button" href="/setup/credentials">Zugangsdaten '
                       f'bearbeiten</a>'
                       f'<a class="button quiet" href="/setup/diagnose">Trotzdem '
                       f'messen</a></div>')
        elif nicht_lesbar:
            hinweis = ('<p class="note">Ein Konto, das die API auflistet, aber nicht '
                       'lesen lässt, scheitert meist am Verwaltungskopf — der Fehler '
                       'nennt ihn nur nicht. Die Messung probiert jede Kombination '
                       'durch und sagt, welche geht.</p>'
                       '<a class="button" href="/setup/diagnose">'
                       'Berechtigungen messen</a>')
        parts.append(f"""<div class="card">
<h2 style="margin-top:0">Konten <span class="note">{lesbar} von
{len(state['accounts'])} lesbar</span></h2>
<table>{''.join(zeilen)}</table>{hinweis}</div>""")

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

    wer, zwei = viewer()
    parts.append(f"""<div class="card">
<h2 style="margin-top:0">Die beiden Türen</h2>
<table>
<tr><th>Portal</th><td class="mono">{esc(base_url)}/anmelden<br>
<span class="note">Benutzerkonto mit Kennwort{', zweiter Faktor an'
  if zwei else ' — zweiter Faktor noch aus'}</span></td></tr>
<tr><th>MCP für claude.ai</th><td class="mono">{esc(base_url)}/mcp<br>
<span class="note">Zugangswort als <code>Authorization: Bearer …</code></span></td></tr>
</table>
<p class="note">Zwei Türen, zwei Schlüssel, mit Absicht. claude.ai kann kein
Anmeldeformular ausfüllen und keinen zweiten Faktor eingeben — der Connector
braucht deshalb ein festes Wort. Ein Mensch am Bildschirm kann beides, und
soll es auch. Wer das Zugangswort wechselt, trägt den Connector neu ein; am
Portal ändert sich dadurch nichts.</p>
<div class="row">
<a class="button quiet" href="/konto">Konto und zweiter Faktor</a>
<a class="button quiet" href="/setup/token">Zugangswort für claude.ai wechseln</a>
</div></div>""")
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
<div class="card akzent">
<h2 style="margin-top:0">Diese Rückadresse muss bei Google eingetragen sein</h2>
<pre>{esc(redirect_uri)}</pre>
<p class="note" style="margin-top:0">Sie steht <b>nicht</b> in den
Einstellungen der Google Auth Platform, sondern am OAuth-Client selbst:</p>
<ol class="schritte">
<li><a href="https://console.cloud.google.com/auth/clients" target="_blank"
rel="noopener">console.cloud.google.com/auth/clients</a> — in der Konsole
ist das <b>Google Auth Platform → Clients</b>, nicht Branding, Zielgruppe
oder Datenzugriff.</li>
<li>Den Client anklicken (nicht nur die Zeile markieren).</li>
<li>Abschnitt <b>Autorisierte Weiterleitungs-URIs</b> → <b>URI
hinzufügen</b> → Adresse von oben einfügen → speichern.</li>
</ol>
<p class="note"><b>Kein solcher Abschnitt da?</b> Dann ist der Client vom Typ
<b>Desktop</b>, und der hat gar kein Feld dafür — Google nagelt ihn auf
<code>127.0.0.1</code> fest. Für dieses Portal braucht es einen Client vom Typ
<b>Webanwendung</b>: auf derselben Seite <b>Client erstellen</b> → Typ
<b>Webanwendung</b> → Rückadresse eintragen → neue Kennung und neues
Geheimnis unter
<a href="/setup/credentials">Zugangsdaten bearbeiten</a> eintragen. Das
Developer Token bleibt, wie es ist.</p>
<p class="note">Änderungen an einem Client brauchen bei Google manchmal ein
paar Minuten, bis sie greifen.</p>
</div>
<div class="card">
<h2 style="margin-top:0">Notweg für einen Desktop-Client</h2>
<p class="note">Wer den Client nicht wechseln will: nach der Zustimmung landet
der Browser auf einer Adresse, die nicht lädt. Die ganze Adresszeile hier
einfügen. Der Weg funktioniert, verlangt aber bei jeder neuen Verbindung
wieder Kopieren und Einfügen.</p>
<form method="post" action="/setup/paste">
<input type="text" name="pasted" placeholder="http://127.0.0.1:…/?state=…&amp;code=…"
       autocomplete="off" spellcheck="false">
<button type="submit">Adresse auswerten</button>
</form></div>
<p><a href="/setup">Zurück zur Übersicht</a></p>""")


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


def result_page(ok: bool, message: str, *, nochmal: str = "",
                nochmal_text: str = "Noch einmal versuchen") -> bytes:
    """Ein Ergebnis, ein Weg weiter.

    Vorher standen hier zwei Knöpfe, die beide nur zurückführten — einer
    davon mit der Aufschrift „Zum Status", was niemandem sagt, wohin er
    führt. Jetzt gibt es einen Weg zurück, der ihn beim Namen nennt, und
    daneben nur dann einen zweiten, wenn der Aufrufer wirklich eine
    Wiederholung anzubieten hat.
    """
    if ok:
        kopf = "Erledigt"
        marke = ""
    else:
        kopf = "Hat nicht geklappt"
        marke = '<span class="state bad">Fehler</span>'
    zweiter = (f'<a class="button quiet" href="{esc(nochmal)}">{esc(nochmal_text)}</a>'
               if nochmal else "")
    return page(kopf, f"""<h1>{esc(kopf)} {marke}</h1>
<div class="card"><p style="margin-top:0">{esc(message)}</p>
<div class="row"><a class="button" href="/setup">Zurück zur Übersicht</a>
{zweiter}</div></div>""")


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
<a class="button" href="/setup">Zurück zur Übersicht</a>""")


def diagnose_page() -> bytes:
    """Misst, welcher Verwaltungskopf welches Konto lesbar macht.

    Der Fehler USER_PERMISSION_DENIED nennt weder die Kopfzeile noch die
    fehlende Verknüpfung. Statt daraus zu raten, probiert diese Seite
    jede Kombination durch, die richtig sein könnte, und zeigt, was
    tatsächlich passiert ist.
    """
    state = load_state()
    if not state["configured"]:
        return result_page(False, "Erst Zugangsdaten eintragen und verbinden.")

    client = gac.Client(state["config"])
    try:
        ids = client.list_accessible_customers()
    except gac.GoogleAdsError as exc:
        return result_page(
            False, "Schon die Kontenliste ist nicht lesbar: "
                   + exc.message.splitlines()[0]
                   + " — dann liegt es nicht am Verwaltungskopf, sondern am "
                     "Developer Token oder am angemeldeten Google-Konto.")

    eingestellt = state["config"].get("login_customer_id") or ""
    matrix = client.permission_matrix(ids)

    zeilen = []
    for row in matrix:
        if row["works_with"] is None:
            wie = ('<span class="state bad">gar nicht lesbar</span>'
                   + (f'<br><span class="mono" style="font-size:.8rem">'
                      f'{esc(row["code"])}</span>' if row["code"] else ""))
        elif row["works_with"] == "":
            wie = ('<span class="state ok">lesbar</span> '
                   '<span class="note">ohne Verwaltungskopf</span>')
        elif row["works_with"] == row["id"]:
            wie = ('<span class="state ok">lesbar</span> '
                   '<span class="note">mit sich selbst als Verwaltungskonto</span>')
        else:
            wie = ('<span class="state ok">lesbar</span> '
                   f'<span class="note">mit Verwaltungskonto '
                   f'<span class="mono">{esc(row["works_with"])}</span></span>')
        versuche = " · ".join(
            ("✓ " if v["ok"] else "✗ ") + esc(v["label"]) for v in row["attempts"])
        zeilen.append(f'<tr><th class="mono">{esc(row["id"])}</th><td>{wie}'
                      f'<br><span class="note">{versuche}</span></td></tr>')

    lesbar = [r for r in matrix if r["works_with"] is not None]
    ohne_kopf = [r for r in lesbar if r["works_with"] == ""]
    passend = {r["works_with"] for r in lesbar if r["works_with"]}

    projekt = gac.project_number_of(state["config"].get("client_id") or "")
    projekt_gesperrt = any("CLOUD_PROJECT_NOT_APPROVED" in (r.get("code") or "")
                           for r in matrix)
    if projekt_gesperrt:
        schluss = (f"<b>Es liegt nicht am Verwaltungskopf.</b> Die API antwortet mit "
                   f"<code>CLOUD_PROJECT_NOT_APPROVED_FOR_PRODUCTION</code>: das "
                   f"Google-Cloud-Projekt <span class=\"mono\">"
                   f"{esc(gac.project_number_of(state['config'].get('client_id') or ''))}"
                   f"</span> steht auf Zugriffsstufe Test und darf nur Testkonten "
                   f"lesen. Keine Kopfzeile ändert daran etwas.<br><br>"
                   f"Freischalten in der Cloud Console in genau diesem Projekt: "
                   f"<b>Google Ads API → Übersicht → Zugriffsstufe hochstufen → "
                   f"Zugriff beantragen</b>. Die Markenprüfung muss vorher durch sein. "
                   f"Oder den OAuth-Client in einem bereits freigeschalteten Projekt "
                   f"anlegen — das dauert Minuten statt Tage. "
                   f"<a href=\"https://developers.google.com/google-ads/api/docs/access-levels\" "
                   f"target=\"_blank\" rel=\"noopener\">Zugriffsstufen</a>")
    elif not lesbar:
        schluss = ((f"<b>Dieser OAuth-Client gehört zum Google-Cloud-Projekt "
                    f"<span class=\"mono\">{esc(projekt)}</span>.</b> Steht diese "
                    f"Nummer nicht auch vor der Client-ID, mit der es früher schon "
                    f"einmal gelesen werden konnte, ist das die Ursache — und der "
                    f"schnellste Weg ist, den Client im <b>alten</b> Projekt neu "
                    f"anzulegen statt Zugriff für dieses zu beantragen.<br><br>"
                    if projekt else "")
                   + "<b>Kein einziges Konto ist lesbar, mit keiner Kopfzeile.</b> "
                   "Dann liegt es nicht an einer fehlenden Verknüpfung — die "
                   "betrifft immer nur einzelne Konten, nie alle.<br><br>"
                   "Die wahrscheinlichste Ursache ist die <b>Zugriffsstufe des "
                   "Google-Cloud-Projekts</b>. Sie hängt am Projekt, nicht am "
                   "Developer Token, und Google sagt dazu: <i>„After you've "
                   "enabled Google Ads API, your Google Cloud project is granted "
                   "Test access“</i> — und Test-Zugriff darf <i>„only make Google "
                   "Ads API requests against test accounts“</i>. Ein <b>frisch "
                   "angelegtes Projekt steht also auf Test</b> und weist jedes "
                   "echte Konto ab.<br><br>"
                   "Wer gerade einen neuen OAuth-Client gebaut hat, sollte prüfen, "
                   "ob der im <b>selben</b> Cloud-Projekt liegt wie der alte. Liegt "
                   "er in einem neuen, ist die Stufe dort zurück auf Test, und der "
                   "Zugriff muss neu beantragt werden: "
                   "<a href=\"https://developers.google.com/google-ads/api/docs/access-levels\" "
                   "target=\"_blank\" rel=\"noopener\">Zugriffsstufen</a>. "
                   "Die zweite Möglichkeit: das angemeldete Google-Konto hat auf "
                   "diese Ads-Konten gar keinen Zugriff mehr.")
    elif len(ohne_kopf) == len(lesbar) and eingestellt:
        schluss = (f"<b>Alles ist ohne Verwaltungskopf lesbar.</b> Das eingestellte "
                   f"Verwaltungskonto <span class=\"mono\">{esc(eingestellt)}</span> "
                   f"passt zu keinem dieser Konten — entweder sind sie nicht darunter "
                   f"verknüpft, oder das angemeldete Google-Konto ist gar kein Nutzer "
                   f"dieses Verwaltungskontos. Trag es unter "
                   f"<a href=\"/setup/credentials\">Zugangsdaten bearbeiten</a> leer ein.")
    elif len(passend) == 1 and not ohne_kopf:
        einziges = next(iter(passend))
        schluss = (f"Alle lesbaren Konten hängen am Verwaltungskonto "
                   f"<span class=\"mono\">{esc(einziges)}</span>."
                   + ("" if einziges == eingestellt else
                      f" Eingestellt ist aber <span class=\"mono\">"
                      f"{esc(eingestellt) or '(leer)'}</span> — das gehört geändert."))
    else:
        schluss = ("Die Konten brauchen unterschiedliche Verwaltungsköpfe. Ein "
                   "einzelner Wert in den Zugangsdaten kann nicht für alle stimmen; "
                   "der Server nimmt deshalb je Konto den, der hier funktioniert hat.")

    gefunden = {r["id"]: r["works_with"] for r in lesbar}
    gespeichert = state["config"].get("account_logins") or {}
    if gefunden and gefunden != gespeichert:
        felder = "".join(
            f'<input type="hidden" name="zuordnung" value="{esc(k)}:{esc(v)}">'
            for k, v in sorted(gefunden.items()))
        uebernehmen = f"""<div class="card">
<h2 style="margin-top:0">Ergebnis übernehmen</h2>
<p class="note" style="margin-top:0">Speichert je Konto den Kopf, der eben
funktioniert hat. Danach liest der Server jedes Konto so, wie es gelesen
werden will — statt für alle denselben Wert zu raten.</p>
<form method="post" action="/setup/diagnose">{felder}
<button type="submit">Zuordnung übernehmen</button></form></div>"""
    elif gefunden:
        uebernehmen = ('<div class="card"><p class="note" style="margin:0">'
                       'Diese Zuordnung ist bereits gespeichert.</p></div>')
    else:
        uebernehmen = ""

    return page("Berechtigungen", f"""
<h1>Welcher Verwaltungskopf öffnet welches Konto</h1>
<p class="lead">Gemessen, nicht geraten: für jedes Konto wurde eine Zeile
gelesen — ohne Verwaltungskopf, mit sich selbst und mit jedem anderen
zugänglichen Konto, bis eines ging.</p>
<div class="card"><table>{"".join(zeilen)}</table></div>
<div class="card akzent"><p style="margin-top:0">{schluss}</p></div>
{uebernehmen}
<p class="note">Eingestellt ist derzeit
<span class="mono">{esc(eingestellt) or "(kein Verwaltungskonto)"}</span>.
Die Messung selbst verändert nichts — sie liest je Konto eine Zeile.</p>
<a class="button quiet" href="/setup">Zurück zur Übersicht</a>""")


def save_account_logins(form: dict) -> tuple[bool, str]:
    """Schreibt die gemessene Zuordnung in die Konfiguration."""
    zuordnung = {}
    for eintrag in form.get("zuordnung") or []:
        konto, _, login = eintrag.partition(":")
        try:
            konto = gac.normalize_customer_id(konto)
            login = gac.normalize_customer_id(login) if login else ""
        except gac.GoogleAdsError as exc:
            return False, exc.message
        zuordnung[konto] = login

    config = {}
    if gac.CONFIG_FILE.exists():
        try:
            config = json.loads(gac.CONFIG_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            config = {}
    config["account_logins"] = zuordnung
    gac.CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    gac.CONFIG_FILE.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n",
                               encoding="utf-8")
    os.chmod(gac.CONFIG_FILE, 0o600)
    ohne = sum(1 for v in zuordnung.values() if not v)
    return True, (f"{len(zuordnung)} Konten zugeordnet"
                  + (f", davon {ohne} ohne Verwaltungskopf" if ohne else "") + ".")


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
<a class="button" href="/setup">Zurück zur Übersicht</a></div>""")
    return page("Zugangswort", """<h1>Zugangswort wechseln</h1>
<p class="lead">Der Schlüssel des MCP-Endpunkts — das, was claude.ai als
<code>Authorization: Bearer …</code> mitschickt.</p>
<div class="card">
<p>Mit deiner Anmeldung an diesem Portal hat das Wort nichts zu tun. Ein
Wechsel sperrt niemanden hier aus; er macht nur das alte Wort sofort
ungültig. Der Connector in claude.ai trägt das alte und muss danach neu
eingetragen werden — bis dahin antwortet der Server ihm mit einer
Abweisung.</p>
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
