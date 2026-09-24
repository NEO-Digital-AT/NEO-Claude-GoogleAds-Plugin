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

    /dashboard          connection, accounts, access level, guardrails and the
                        last write attempts from the change log
    /setup              step 1 of the rail: the four values Google requires
    /setup/connect      step 2: starts the consent flow — also to reconnect
    /setup/accounts     step 3: which accounts may be written to (POST)
    /setup/callback     where Google returns; trades the code for a token
    /setup/paste        the fallback when the OAuth client is a desktop one
    /setup/token        replaces the access word for claude.ai (POST)
    /setup/disconnect   forgets the refresh token (POST, asks first)
    /guardrails         edits the guardrails (POST)
    /check              runs the connection checks and shows the result
    /check/permissions  measures which login header opens which account

The addresses are English like every other technical name here; what a
person reads on them is German.

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
import copy
import datetime
import hashlib
import html
import json
import os
import threading
import time
import pathlib
import secrets
import urllib.error
import urllib.parse
import urllib.request

import google_ads_client as gac
import oeffentliche_seite
import portal_shell as sh
from neo_design import symbol

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"

# Die vier Schritte der Einrichtung, in der Reihenfolge, in der sie
# auseinander folgen. Der letzte fuehrt aus der Schiene heraus: die
# Schutzgrenzen sind danach ein eigener Schirm, kein Schritt mehr.
SCHIENE = (("/setup", "Zugangsdaten", "key"),
           ("/setup/connect", "Mit Google verbinden", "link"),
           ("/setup/accounts", "Konten", "account_tree"),
           ("/guardrails", "Schutzgrenzen", "shield_lock"))
EINRICHTUNG_LEAD = ("Vier Schritte von den Zugangsdaten bis zur "
                    "freigegebenen Verbindung.")
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
    """Was neben der Wortmarke steht — dieselbe Regel wie auf der oeffentlichen Seite."""
    return oeffentliche_seite.beiwort()

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

# Wer gerade zusieht. Je Faden, weil der Server einer ist: zwei Abrufe
# duerfen sich nicht gegenseitig den Namen in der Kopfzeile ueberschreiben.
_viewer = threading.local()


def set_viewer(name: str = "", *, two_factor: bool = False) -> None:
    """Who the current request belongs to. Per thread, because the server is."""
    _viewer.name = name
    _viewer.two_factor = two_factor


def viewer() -> tuple[str, bool]:
    return getattr(_viewer, "name", ""), getattr(_viewer, "two_factor", False)


def set_host(host: str = "") -> None:
    """The host this request came in on. Only the sidebar shows it."""
    _viewer.host = host


def host() -> str:
    return getattr(_viewer, "host", "")


def konsole(titel: str, lead: str, weg: str, inhalt: str, *, aktionen: str = "",
            ueberlagerung: str = "", skript: str = "") -> bytes:
    """One page of the management console, in the frame from portal_shell.

    Everything the frame needs about the brand and the person looking at
    it is already known here, so a caller passes only its own page.
    """
    name, zwei = viewer()
    return sh.rahmen(
        titel=titel, lead=lead, weg=weg, inhalt=inhalt, benutzer=name,
        zwei_faktor=zwei, logo=logo_markup(), favicon=FAVICON, marke=MARKE,
        beiwort=marke_beiwort(), server=host(), aktionen=aktionen,
        ueberlagerung=ueberlagerung, skript=skript)


def schmale_seite(titel: str, lead: str, inhalt: str, *, fuss: str = "",
                  oben: str = "", skript: str = "") -> bytes:
    """A page with one job: signing in, the second factor, the new password."""
    return sh.schmale_seite(
        titel=titel, lead=lead, inhalt=inhalt, logo=logo_markup(),
        favicon=FAVICON, marke=MARKE, fuss=fuss, oben=oben, skript=skript)


def logo_markup() -> str:
    """The built-in word mark, or the operator's own file if one is there."""
    eigen = gac.CONFIG_FILE.parent / "logo.svg"
    if eigen.exists():
        try:
            return eigen.read_text(encoding="utf-8")
        except OSError:
            pass
    return LOGO


def esc(value) -> str:
    return html.escape(str(value if value is not None else ""))


# --------------------------------------------------------------------------
# Reading the current state
# --------------------------------------------------------------------------

# Der Stand kostet bei jedem Aufruf eine Kontenliste und eine Zeile je
# Konto bei Google — mehrere Sekunden. Zwischen Uebersicht, Schutzgrenzen
# und Pruefung hin und her zu klicken fragte das jedes Mal neu ab. Eine
# Minute Gedaechtnis nimmt das weg; alles, was etwas aendert, vergisst es.
_STAND: dict = {"zeit": 0.0, "wert": None}
STAND_GILT = 60.0


def vergiss_stand() -> None:
    """Nach jeder Aenderung: der naechste Aufruf fragt Google wieder."""
    _STAND["zeit"] = 0.0
    _STAND["wert"] = None


def load_state(frisch: bool = False) -> dict:
    """Der Stand, hoechstens eine Minute alt. frisch=True fragt neu."""
    if not frisch and _STAND["wert"] is not None:
        if time.monotonic() - _STAND["zeit"] < STAND_GILT:
            return _STAND["wert"]
    wert = _stand_lesen()
    _STAND["zeit"], _STAND["wert"] = time.monotonic(), wert
    return wert


def _stand_lesen() -> dict:
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
    Zustimmungsbildschirms als Titel, und darunter in Saetzen, was die
    Anwendung tut und welche Daten sie warum anfasst. Sie zeigt nichts an,
    was nicht jeder sehen darf — kein Kontostand, keine Kennzahl, keine
    Kundennummer, und nichts aus der Konfiguration.

    Gebaut wird sie in oeffentliche_seite.py, nach dem NEO-Designsystem.
    Sie bringt ihr eigenes Aussehen mit und benutzt page() deshalb nicht:
    die Verwaltung dahinter ist ein Arbeitsgeraet, diese Seite ist eine
    Visitenkarte, und beide duerfen unterschiedlich aussehen.
    """
    set_viewer("")
    return oeffentliche_seite.seite(logo=logo_markup(), favicon=FAVICON,
                                    anmelden_url="/login")


def _zugriffsstufe(state: dict) -> tuple[str, str]:
    """What the access level of the Cloud project looks like from here.

    The API never says it out loud. What it does say is the error when a
    planner call is refused, and whether anything is readable at all.
    """
    codes = {a.get("code", "") for a in state["accounts"] if a.get("code")}
    if any("CLOUD_PROJECT_NOT_APPROVED" in code for code in codes):
        return "Test", "kein Zugriff auf echte Konten"
    if state["connected"] and any(not a["problem"] for a in state["accounts"]):
        return "Explorer", "mindestens — 11 von 13 Werkzeugen"
    return "unbekannt", "noch keine Antwort der API"


def geldbetrag(micros: int) -> str:
    """Micros als Betrag, mit dem Komma, das hier gelesen wird."""
    return f"{micros / 1_000_000:.2f}".replace(".", ",")


def dashboard_page(base_url: str, frisch: bool = False) -> bytes:
    """Was dieser Server gerade kann: Verbindung, Konten, Grenzen, Protokoll."""
    state = load_state(frisch)
    config = state["config"]
    rails = state["guardrails"]
    konten = state["accounts"]
    lesbar = sum(1 for a in konten if not a["problem"])

    if state["connected"]:
        schild = sh.zustand("verbunden", "ok")
    elif state["configured"]:
        schild = sh.zustand("Zugang abgelehnt", "bad")
    elif config.get("client_id"):
        schild = sh.zustand("noch nicht verbunden", "warn")
    else:
        schild = sh.zustand("nicht eingerichtet", "warn")

    stufe, stufe_notiz = _zugriffsstufe(state)
    deckel = rails.get("max_daily_budget_micros") or 0
    teile = [
        '<div class="grid-3" style="margin-bottom:20px">',
        sh.kennzahl("Konten lesbar",
                    f'{lesbar} <span style="color:var(--faint);font-weight:400">'
                    f'/ {len(konten)}</span>' if konten else "—",
                    neon=bool(lesbar), icon="account_tree"),
        sh.kennzahl("höchstes Tagesbudget",
                    geldbetrag(deckel) if deckel else "ohne Deckel",
                    icon="payments", notiz="je Budget, in der Kontowährung"),
        sh.kennzahl("Zugriffsstufe", stufe, icon="verified", notiz=stufe_notiz),
        sh.kennzahl("API-Fassung", esc(config.get("api_version", "—")), icon="bolt"),
        "</div>",
        '<div class="stack">',
    ]

    if state["error"]:
        teile.append(sh.karte("Meldung der API", f"<pre>{esc(state['error'])}</pre>",
                              art="schlecht"))

    # -- Verbindung --------------------------------------------------------
    def haben(key: str) -> str:
        return sh.zustand(key_name[key], "ok" if config.get(key) else "bad")

    key_name = {"client_secret": "Client-Geheimnis",
                "developer_token": "Developer Token",
                "refresh_token": "Refresh Token"}
    kennung = config.get("client_id", "")
    gekuerzt = kennung[:42] + ("…" if len(kennung) > 42 else "")
    teile.append(sh.karte(
        "Verbindung",
        sh.tabelle(
            sh.zeile("Client-ID", f'<span class="mono">{esc(gekuerzt) or "—"}</span>')
            + sh.zeile("Cloud-Projekt",
                       f'<span class="mono">'
                       f'{esc(gac.project_number_of(kennung) or "—")}</span>',
                       "Daran hängt die Zugriffsstufe, nicht am Developer Token.")
            + sh.zeile("Geheimnisse", " ".join(haben(k) for k in key_name))
            + sh.zeile("Verwaltungskonto",
                       f'<span class="mono">'
                       f'{esc(config.get("login_customer_id") or "—")}</span>')),
        zustand=schild,
        aktion='<a class="button quiet klein" href="/setup">Zugangsdaten</a>'
               + ('<a class="button quiet klein" href="/check">Verbindung prüfen</a>'
                  if state["configured"] else "")))

    # -- Konten ------------------------------------------------------------
    if konten:
        zeilen = []
        for konto in konten:
            if konto["problem"]:
                code = (f' <span class="mono leise">{esc(konto["code"])}</span>'
                        if konto.get("code") else "")
                wert = sh.zustand("nicht lesbar", "bad") + code
                notiz = konto["problem"]
            else:
                marke = " · Verwaltungskonto" if konto["manager"] else ""
                wert = (f'{esc(konto["name"] or "ohne Namen")} '
                        f'<span class="leise">{esc(konto["currency"])}{marke}</span>')
                notiz = ""
            zeilen.append(sh.zeile(konto["id"], wert, notiz, mono=True))
        nicht_lesbar = len(konten) - lesbar
        codes = {a.get("code", "") for a in konten if a.get("code")}
        if any("CLOUD_PROJECT_NOT_APPROVED" in code for code in codes):
            fuss = _stufe_hinweis(gac.project_number_of(kennung))
        elif nicht_lesbar:
            fuss = ('<p class="note">Ein Konto, das die API auflistet, aber nicht '
                    'lesen lässt, scheitert meist am Verwaltungskopf — der Fehler '
                    'nennt ihn nur nicht. Die Messung probiert jede Kombination durch '
                    'und sagt, welche geht.</p>')
        else:
            fuss = ""
        teile.append(sh.karte(
            "Konten", sh.tabelle("".join(zeilen)) + fuss,
            zustand=(sh.zustand(f"{nicht_lesbar} nicht lesbar", "warn")
                     if nicht_lesbar else sh.zustand("alle lesbar", "ok")),
            aktion='<a class="button quiet klein" href="/check/permissions">'
                   'Berechtigungen messen</a>'))

    # -- Schutzgrenzen -----------------------------------------------------
    erlaubt = rails.get("allowed_customer_ids") or []
    teile.append(sh.karte(
        "Schutzgrenzen",
        sh.tabelle(
            sh.zeile("Schreiben",
                     sh.zustand("eingeschaltet", "warn") if rails.get("write_enabled")
                     else sh.zustand("aus", "ok"))
            + sh.zeile("Erlaubte Konten",
                       f'<span class="mono">{esc(", ".join(erlaubt))}</span>'
                       if erlaubt else "alle zugänglichen")
            + sh.zeile("Budgetdeckel je Tag",
                       geldbetrag(deckel) if deckel else "keiner")
            + sh.zeile("Größter Budgetsprung",
                       f"Faktor {esc(rails.get('max_budget_increase_factor'))}")
            + sh.zeile("Operationen je Aufruf",
                       esc(rails.get("max_operations_per_call"))))
        + '<p class="note">Auch bei eingeschaltetem Schreiben ist jeder Aufruf zuerst '
          'ein Trockenlauf — scharf wird er erst nach ausdrücklicher Freigabe im '
          'Gespräch.</p>',
        zustand=(sh.zustand(f"{len(erlaubt)} Konten mit Schreibrecht", "warn")
                 if rails.get("write_enabled") and erlaubt else ""),
        aktion='<a class="button quiet klein" href="/guardrails">Bearbeiten</a>'))

    # -- Letzte Aenderungen ------------------------------------------------
    changes = recent_changes()
    if changes:
        zeilen = []
        for eintrag in changes:
            art = (sh.zustand("Trockenlauf", "neutral") if eintrag.get("dry_run")
                   else sh.zustand("scharf", "warn"))
            zeilen.append(sh.zeile(
                eintrag.get("time", "")[:16].replace("T", " "),
                f'{art} <span class="mono leise">{esc(eintrag.get("customer_id"))}'
                f'</span> · {esc(eintrag.get("operation_count"))} Operationen · '
                f'{esc(eintrag.get("result"))}',
                eintrag.get("reason") or "ohne Begründung", mono=True))
        teile.append(sh.karte("Letzte Änderungen", sh.tabelle("".join(zeilen))))

    # -- Die beiden Tueren -------------------------------------------------
    _, zwei = viewer()
    teile.append(sh.karte(
        "Die beiden Türen",
        sh.tabelle(
            sh.zeile("Portal", f'<span class="mono">{esc(base_url)}/login</span>',
                     "Benutzerkonto mit Kennwort" + (", zweiter Faktor an" if zwei
                                                     else " — zweiter Faktor noch aus"))
            + sh.zeile("MCP für claude.ai",
                       f'<span class="mono">{esc(base_url)}/mcp</span>',
                       "Zugangswort als Authorization: Bearer …"))
        + '<p class="note">Zwei Türen, zwei Schlüssel, mit Absicht. claude.ai kann '
          'kein Anmeldeformular ausfüllen und keinen zweiten Faktor eingeben — der '
          'Connector braucht deshalb ein festes Wort. Wer das Zugangswort wechselt, '
          'trägt den Connector neu ein; am Portal ändert sich dadurch nichts.</p>'
          '<div class="row" style="margin-top:18px">'
          '<a class="button quiet" href="/account">Konto und zweiter Faktor</a>'
          '<a class="button quiet" href="/setup/token">Zugangswort wechseln</a>'
          '</div>'))

    # -- Verbindung trennen ------------------------------------------------
    if config.get("refresh_token"):
        teile.append(sh.karte(
            "Verbindung trennen",
            '<p class="note" style="margin-top:0">Löscht den Refresh Token auf diesem '
            'Server. Die Zugangsdaten bleiben, sodass ein erneutes Verbinden ohne '
            'Eingaben auskommt. Der Zugriff des Google-Kontos wird damit nicht '
            'widerrufen — das geschieht unter <a href='
            '"https://myaccount.google.com/permissions" target="_blank" '
            'rel="noopener">myaccount.google.com/permissions</a>.</p>'
            '<form method="post" action="/setup/disconnect" style="margin-top:18px">'
            '<button class="danger" type="submit">Refresh Token löschen</button>'
            '</form>'))

    teile.append("</div>")
    return konsole("Übersicht", "Verbindung, Konten und Schutzgrenzen dieses Servers.",
                   "/dashboard", "".join(teile),
                   aktionen='<a class="button quiet klein" href="/dashboard?frisch=1">'
                            + symbol("refresh", 18) + 'Neu abfragen</a>')


def _stufe_hinweis(projekt: str) -> str:
    """Was zu tun ist, wenn das Cloud-Projekt noch auf Zugriffsstufe Test steht."""
    return (f'<p class="note"><b>Das ist nicht der Verwaltungskopf.</b> '
            f'<code>CLOUD_PROJECT_NOT_APPROVED_FOR_PRODUCTION</code> heißt: das '
            f'Google-Cloud-Projekt <span class="mono">{esc(projekt)}</span> darf noch '
            f'nicht auf echte Konten zugreifen — es steht auf Zugriffsstufe Test.</p>'
            f'<p class="note">Freischalten in der Google Cloud Console, in genau '
            f'diesem Projekt: <b>Google Ads API → Übersicht → Zugriffsstufe '
            f'hochstufen → Zugriff beantragen</b>. Die Markenprüfung des '
            f'Zustimmungsbildschirms muss vorher durch sein.</p>'
            f'<p class="note">Die nächste Stufe ist meist <b>Explorer</b>, und die '
            f'kommt oft sofort. Sie reicht für alles hier außer dem Keyword-Planer — '
            f'achtzehn der zwanzig Werkzeuge laufen damit. <b>Basic</b> braucht es erst '
            f'für den Planer und für mehr als 2.880 Operationen am Tag; darauf kann '
            f'Google bis zu zehn Werktage prüfen.</p>'
            f'<p class="note">Schneller geht es, wenn ein <b>anderes, bereits '
            f'freigeschaltetes Projekt</b> vorhanden ist: den OAuth-Client dort '
            f'anlegen und die neue Kennung hier eintragen. Dann ist nichts zu '
            f'beantragen.</p>'
            f'<div class="row" style="margin-top:16px">'
            f'<a class="button" href="/setup">Zugangsdaten bearbeiten</a>'
            f'<a class="button quiet" href="/check/permissions">Trotzdem messen</a>'
            f'</div>')


def credentials_page(message: str = "") -> bytes:
    state = load_state()
    config = state["config"]
    hinweis = sh.warnung(esc(message), "schlecht") if message else ""
    return konsole("Einrichtung", EINRICHTUNG_LEAD, "/setup",
                   sh.schiene(SCHIENE, 0) + hinweis + f"""
<form method="post" action="/setup/credentials"><div class="card">
<div class="card-kopf"><h2>Die vier Angaben, die Google verlangt</h2></div>
<p class="note" style="margin-top:0;margin-bottom:20px">Zwei davon stellt Google
einer namentlich bekannten Person aus — sie können nicht erzeugt werden.</p>
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

<div class="row" style="margin-top:24px">
<button type="submit">Speichern und weiter</button>
<a class="button quiet" href="/dashboard">Abbrechen</a></div>
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
        return konsole("Einrichtung", EINRICHTUNG_LEAD, "/setup",
                       sh.schiene(SCHIENE, 1)
                       + sh.karte("Noch nicht so weit",
                                  '<p class="note" style="margin-top:0">Client-ID und '
                                  'Geheimnis fehlen noch.</p>'
                                  '<div class="row" style="margin-top:18px">'
                                  '<a class="button" href="/setup">Zugangsdaten '
                                  'eintragen</a></div>', art="akzent"))

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

    return konsole("Einrichtung", EINRICHTUNG_LEAD, "/setup",
                   sh.schiene(SCHIENE, 1) + f"""
<div class="card"><div class="card-kopf"><h2>Mit Google verbinden</h2></div>
<p class="note" style="margin-top:0">Melde dich mit dem Google-Konto an, das deine
Ads-Konten sieht — nicht zwingend das des Verwaltungskontos.</p>
<div class="row" style="margin-top:20px">
<a class="button" href="{esc(url)}">{symbol("link", 20)}Bei Google anmelden und
zustimmen</a>
<a class="button quiet" href="/setup/accounts">Weiter zu den Konten</a></div>
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
<a href="/setup">Zugangsdaten bearbeiten</a> eintragen. Das
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
<div class="row" style="margin-top:18px">
<button type="submit">Adresse auswerten</button>
<a class="button quiet" href="/dashboard">Zurück zur Übersicht</a></div>
</form></div>""")


def pkce_pair() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).decode().rstrip("=")
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return verifier, base64.urlsafe_b64encode(digest).decode().rstrip("=")


def exchange_code(pasted_or_query: str) -> tuple[bool, str]:
    """Trades an authorisation code for a refresh token. Returns (ok, message)."""
    vergiss_stand()
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
        marke = sh.zustand("Fehler", "bad")
    zweiter = (f'<a class="button quiet" href="{esc(nochmal)}">{esc(nochmal_text)}</a>'
               if nochmal else "")
    return konsole(kopf, "", "/dashboard", sh.karte(
        inhalt=f'<p style="margin-top:0">{esc(message)}</p>'
               f'<div class="row" style="margin-top:18px">'
               f'<a class="button" href="/dashboard">Zurück zur Übersicht</a>'
               f'{zweiter}</div>',
        art="" if ok else "schlecht"))


def check_page() -> bytes:
    """Dieselben Prüfungen wie google-ads-check.py, als Tabelle.

    Jede Zeile traegt ihren eigenen Zustand. Vorher stand neben jeder
    Zeile "ok", auch neben der, die "gesperrt" sagte — eine Pille, die
    dem Satz daneben widerspricht, ist schlimmer als keine.
    """
    state = load_state()
    zeilen = []

    def zeile(name: str, art: str, text: str) -> None:
        marke = {"ok": sh.zustand("ok", "ok"),
                 "hinweis": sh.zustand("Hinweis", "warn"),
                 "befund": sh.zustand("Befund", "bad")}[art]
        zeilen.append(f'<tr><th>{esc(name)}</th><td>{marke} {esc(text)}</td></tr>')

    zeile("Konfiguration", "ok" if state["configured"] else "befund",
          "vollständig" if state["configured"] else state["error"].splitlines()[0])
    if state["configured"]:
        zeile("Zugang", "ok" if state["connected"] else "befund",
              "die API antwortet" if state["connected"]
              else state["error"].splitlines()[0])
        lesbar = [a for a in state["accounts"] if not a["problem"]]
        alle = len(state["accounts"])
        if not lesbar:
            art = "befund"
        elif len(lesbar) < alle:
            art = "hinweis"
        else:
            art = "ok"
        zeile("Konten", art, f"{len(lesbar)} von {alle} lesbar")

        if lesbar:
            client = gac.Client(state["config"])
            try:
                client.call("POST", f"customers/{lesbar[0]['id']}:"
                                    "generateKeywordHistoricalMetrics",
                            {"keywords": ["test"], "language": "languageConstants/1001",
                             "geoTargetConstants": ["geoTargetConstants/2040"],
                             "keywordPlanNetwork": "GOOGLE_SEARCH"})
                zeile("Keyword-Planer", "ok",
                      "verfügbar — Zugriffsstufe Basic oder höher")
            except gac.GoogleAdsError:
                zeile("Keyword-Planer", "hinweis",
                      "gesperrt — Zugriffsstufe Explorer. Achtzehn der zwanzig Werkzeuge "
                      "laufen, der Keyword-Planer nicht")

    # Search Console und Analytics hängen NICHT an der Ads-Zugriffsstufe,
    # sondern an zwei anderen Dingen: der Berechtigung im gespeicherten
    # Google-Login (seit 2.5.0 dabei, ältere Logins haben sie nicht) und den
    # eingeschalteten APIs im Cloud-Projekt. Die Zeilen nennen, was fehlt.
    if state["configured"] and state["connected"]:
        try:
            properties = gac.Client(state["config"]).search_console_sites()
            lesbare = [p for p in properties if p.get("permissionLevel") != "siteUnverifiedUser"]
            zeile("Search Console", "ok" if lesbare else "hinweis",
                  f"{len(lesbare)} Property lesbar" if len(lesbare) == 1
                  else f"{len(lesbare)} Properties lesbar")
        except gac.GoogleAdsError as exc:
            hinweis = exc.message.splitlines()
            zeile("Search Console", "hinweis",
                  (hinweis[-1].replace("Hint: ", "").strip() if len(hinweis) > 1 else hinweis[0]))
        try:
            konten = gac.Client(state["config"]).analytics_account_summaries()
            anzahl = sum(len(k.get("propertySummaries") or []) for k in konten)
            zeile("Google Analytics", "ok" if anzahl else "hinweis",
                  f"{anzahl} Property lesbar" if anzahl == 1 else f"{anzahl} Properties lesbar")
        except gac.GoogleAdsError as exc:
            hinweis = exc.message.splitlines()
            zeile("Google Analytics", "hinweis",
                  (hinweis[-1].replace("Hint: ", "").strip() if len(hinweis) > 1 else hinweis[0]))

    rails = state["guardrails"]
    if not rails.get("write_enabled"):
        zeile("Schutzgrenzen", "ok", "Schreiben aus — nur Trockenläufe")
    else:
        konten = rails.get("allowed_customer_ids") or []
        # Schreiben ein ohne Kontenliste heisst ALLE zugaenglichen Konten.
        # Das ist die weiteste Einstellung, die es gibt, und kein "ok".
        zeile("Schutzgrenzen", "ok" if konten else "hinweis",
              f"Schreiben ein, erlaubt: {', '.join(konten)}" if konten
              else "Schreiben ein, aber KEIN Konto angehakt — das heißt alle "
                   "zugänglichen")

    return konsole(
        "Verbindung geprüft",
        "Dieselben Prüfungen wie google-ads-check.py — gemessen, nicht geraten.",
        "/check",
        sh.karte("Ergebnis", f"<table>{''.join(zeilen)}</table>",
                 aktion='<a class="button quiet klein" href="/check/permissions">'
                        'Berechtigungen messen</a>'))


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
                   f"Die nächste Stufe ist meist <b>Explorer</b> und kommt oft sofort; "
                   f"sie reicht für alles außer dem Keyword-Planer. Oder den "
                   f"OAuth-Client in einem bereits freigeschalteten Projekt anlegen. "
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

    return konsole(
        "Berechtigungen",
        "Welcher Verwaltungskopf öffnet welches Konto — für jedes Konto wurde eine "
        "Zeile gelesen: ohne Kopf, mit sich selbst und mit jedem anderen "
        "zugänglichen Konto, bis eines ging.",
        "/check", f"""<div class="stack">
<div class="card"><table>{"".join(zeilen)}</table></div>
<div class="card akzent"><p style="margin-top:0">{schluss}</p></div>
{uebernehmen}
</div>
<p class="note">Eingestellt ist derzeit
<span class="mono">{esc(eingestellt) or "(kein Verwaltungskonto)"}</span>.
Die Messung selbst verändert nichts — sie liest je Konto eine Zeile.</p>""")


def save_account_logins(form: dict) -> tuple[bool, str]:
    """Schreibt die gemessene Zuordnung in die Konfiguration."""
    vergiss_stand()
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
    vergiss_stand()
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


def env_startwerte() -> dict:
    """Welche Schutzgrenzen die Umgebung fuer eine frische Anlage mitbringt.

    Sie gelten nur, solange die Konsole noch nie gespeichert hat. Danach
    steht in der Konfiguration ein eigener Block, und der entscheidet —
    die Variablen werden dann nicht mehr angesehen. Diese Liste dient
    also nur dem Hinweis auf der Seite, nicht mehr der Sperre.
    """
    # Leere Variablen zaehlen nicht: eine leer gelassene Zeile aus der
    # Vorlage ist keine Angabe.
    return {field: name for field, name in gac.GUARDRAIL_ENV.items()
            if (os.environ.get(name) or "").strip()}


def grenzen_gespeichert() -> bool:
    """Ob in der Konfigurationsdatei schon ein eigener Block steht."""
    if not gac.CONFIG_FILE.exists():
        return False
    try:
        gespeichert = json.loads(gac.CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(gespeichert.get("guardrails"))


def _kontenkaesten(state: dict, erlaubt: set) -> str:
    """Die zugaenglichen Konten zum Anhaken, statt Nummern zu tippen.

    Der Merker konten_gestellt sagt dem Speichern, dass diese Liste
    wirklich gestellt wurde. Ohne ihn bliebe eine gescheiterte Abfrage als
    "kein Haken" stehen — und kein Haken heisst ALLE Konten.
    """
    def kasten(wert: str, titel: str, zusatz: list, an: bool,
               lesbar: bool = True) -> str:
        zeile = sh.ankreuzzeile("konto", titel, " · ".join(zusatz), wert=wert, an=an,
                                gesperrt=not lesbar, kennung=wert)
        # Ein gesperrtes Ankreuzfeld schickt seinen Wert nicht mit. Stand das
        # Konto schon in der Berechtigung, verschwaende es beim Speichern
        # still — also faehrt der Wert versteckt mit. Ankreuzen laesst sich
        # so trotzdem nichts, was gerade nicht lesbar ist.
        if not lesbar and an:
            zeile += f'<input type="hidden" name="konto" value="{esc(wert)}">'
        return zeile

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
                              zusatz, account["id"] in erlaubt,
                              lesbar=not account["problem"]))
    for verwaist in sorted(erlaubt - {a["id"] for a in state["accounts"]}):
        kaesten.append(kasten(verwaist, "steht gerade nicht in der Liste", [], True))

    if state["accounts"]:
        return ("".join(kaesten)
                + '<input type="hidden" name="konten_gestellt" value="1">')
    if kaesten:
        grund = f' ({esc(state["error"].splitlines()[0])})' if state["error"] else ""
        return (sh.warnung(f"Die Kontenliste ließ sich gerade nicht lesen{grund}. Was "
                           f"berechtigt ist, steht unten und bleibt beim Speichern "
                           f"unverändert. Zum Ändern zuerst die Verbindung prüfen.")
                + "".join(kaesten))
    return ('<p class="note">Noch keine Konten gelesen. Erst verbinden, dann stehen '
            'sie hier zum Anhaken.</p>')


def accounts_page(message: str = "") -> bytes:
    """Schritt 3 der Schiene: welche Konten überhaupt beschrieben werden dürfen."""
    state = load_state()
    erlaubt = set(state["guardrails"].get("allowed_customer_ids") or [])
    return konsole(
        "Einrichtung", EINRICHTUNG_LEAD, "/setup",
        sh.schiene(SCHIENE, 2)
        + (sh.warnung(esc(message), "gut") if message else "")
        + '<form method="post" action="/setup/accounts">'
        + sh.karte(
            "Gelesene Konten",
            '<p class="note" style="margin-top:0;margin-bottom:16px">Alles, was das '
            'verbundene Google-Konto sieht. Ein Haken heißt: hier darf später auch '
            'geschrieben werden. Kein Haken bei keinem Konto heißt '
            '<b>alle zugänglichen</b> — bei eingeschaltetem Schreiben ist das selten '
            'gemeint.</p>'
            + _kontenkaesten(state, erlaubt)
            + '<div class="row" style="margin-top:22px">'
              '<button type="submit">Weiter zu den Schutzgrenzen</button>'
              '<a class="button quiet" href="/setup/connect">Zurück</a></div>',
            aktion='<a class="button quiet klein" href="/check/permissions">'
                   'Berechtigungen messen</a>')
        + "</form>")


def _grenzfelder(kennung: str, eigene: dict, standard: dict, aktiv: bool) -> str:
    """Die drei Zahlen eines Kontos.

    DIE FELDER SIND IMMER SCHREIBBAR. Vorher sperrte sie der Server nach
    dem gespeicherten Stand — und ein gesperrtes Feld schickt seinen Wert
    nicht mit. Wer den Haken setzte, konnte die Zahlen also nicht
    eintragen, und ohne Zahlen fiel der Haken beim Speichern wieder weg:
    eigene Grenzen liessen sich ueberhaupt nicht anlegen.

    Ob die Zahlen gelten, entscheidet allein der Haken beim Speichern. Das
    Skript unten graut sie zusaetzlich aus, solange er nicht gesetzt ist —
    das ist Beiwerk, kein Verschluss: ohne Skript steht alles offen und
    funktioniert trotzdem.
    """
    def wert(feld: str) -> str:
        roh = eigene.get(feld, standard.get(feld))
        if feld == "max_daily_budget_micros":
            return f"{(roh or 0) / 1_000_000:.2f}"
        return esc(roh)

    geerbt = "Aus dem Standard geerbt, bis der Haken oben sitzt."
    felder = (
        ("Tagesbudget je Budget", f"budget_{kennung}", "max_daily_budget_micros",
         "In der Kontowährung. 0 heißt: keine Obergrenze."),
        ("Größter Sprung", f"faktor_{kennung}", "max_budget_increase_factor",
         "Faktor. 2 heißt: höchstens verdoppeln."),
        ("Operationen je Aufruf", f"ops_{kennung}", "max_operations_per_call",
         "Begrenzt den Schaden eines Fehlgriffs."),
    )
    zeilen = "".join(
        f'<label>{esc(beschriftung)}'
        f'<span data-eigen="{esc(hinweis)}" data-geerbt="{esc(geerbt)}">'
        f'{esc(hinweis if aktiv else geerbt)}</span>'
        f'<input type="text" name="{esc(name)}" value="{wert(feld)}"></label>'
        for beschriftung, name, feld, hinweis in felder)
    return (f'<div class="grid-3 grenzfeld" '
            f'style="align-items:start;margin-top:16px">{zeilen}</div>')


def _kontogrenze(konto: dict, eigene: dict, standard: dict, erlaubt: set) -> str:
    """Eine Karte je Konto: darf es beschrieben werden, und mit welchen Grenzen.

    Die versteckte Zeile grenze_gestellt sagt dem Speichern, welche Konten
    diese Seite ueberhaupt gezeigt hat. Nur die darf es anfassen — was
    gerade nicht in der Liste stand, bleibt, wie es war.
    """
    kaputt = bool(konto["problem"])
    hat_eigene = bool(eigene)
    kennung = konto["id"]
    if kaputt:
        schild = sh.zustand("nicht lesbar", "bad")
    elif kennung in erlaubt:
        schild = sh.zustand("Schreiben ein", "warn")
    else:
        schild = sh.zustand("nur lesen", "ok")
    woher = sh.zustand("eigene Grenzen" if hat_eigene else "erbt Standard", "neutral")

    dabei = [konto.get("currency") or ""]
    if konto.get("manager"):
        dabei.append("Verwaltungskonto")
    beiwerk = " · ".join(teil for teil in dabei if teil)
    kopf = (f'<div class="card-kopf" style="flex-wrap:wrap">'
            f'<h2 class="werkzeile">'
            f'{symbol("account_tree" if konto.get("manager") else "description", 20)}'
            f'{esc(konto["name"] or "ohne Namen")}'
            f'<span class="mono leise">{esc(kennung)}</span>'
            f'<span class="leise">{esc(beiwerk)}</span></h2>'
            f'<div class="rechts">{schild} {woher}</div></div>')
    merker = f'<input type="hidden" name="grenze_gestellt" value="{esc(kennung)}">'

    if kaputt:
        # Nicht lesbar heisst: hier laesst sich nichts einstellen. Was
        # eingestellt WAR, faehrt versteckt mit, statt still zu verschwinden.
        bleibt = ""
        if kennung in erlaubt:
            bleibt += f'<input type="hidden" name="konto" value="{esc(kennung)}">'
        if hat_eigene:
            bleibt += f'<input type="hidden" name="eigene" value="{esc(kennung)}">'
            for feld, name in (("max_daily_budget_micros", "budget"),
                               ("max_budget_increase_factor", "faktor"),
                               ("max_operations_per_call", "ops")):
                if feld in eigene:
                    roh = (f"{eigene[feld] / 1_000_000:.2f}"
                           if feld == "max_daily_budget_micros" else eigene[feld])
                    bleibt += (f'<input type="hidden" name="{name}_{esc(kennung)}" '
                               f'value="{esc(roh)}">')
        return (f'<div class="card flach">{kopf}'
                f'<p class="note" style="margin-top:0">Dieses Konto lässt sich derzeit '
                f'nicht lesen — Grenzen greifen erst, wenn der Zugriff steht.</p>'
                f'{merker}{bleibt}</div>')

    return (f'<div class="card kontogrenze{" akzent" if hat_eigene else ""}">{kopf}'
            f'<div class="row" style="gap:20px">'
            f'<div style="flex:1 1 260px">'
            + sh.ankreuzzeile("konto", "Schreiben erlauben",
                              "Ohne Haken sind für dieses Konto nur Trockenläufe "
                              "möglich.", wert=kennung, an=kennung in erlaubt)
            + '</div><div style="flex:1 1 260px">'
            + sh.ankreuzzeile("eigene", "Eigene Grenzen",
                              "Ohne Haken gilt der Standard weiter unten.",
                              wert=kennung, an=hat_eigene,
                              klasse="eigene-schalter")
            + '</div></div>'
            + _grenzfelder(kennung, eigene, standard, hat_eigene)
            + merker + "</div>")


def _standardkarte(rails: dict) -> str:
    deckel = rails.get("max_daily_budget_micros") or 0
    felder = (
        ("Höchstes Tagesbudget je Budget", "max_daily_budget",
         f"{deckel / 1_000_000:.2f}",
         "In der Kontowährung. 0 heißt: keine Obergrenze."),
        ("Größter Sprung in einem Schritt", "max_budget_increase_factor",
         esc(rails.get("max_budget_increase_factor")),
         "Faktor. 2 heißt: höchstens verdoppeln."),
        ("Operationen je Aufruf", "max_operations_per_call",
         esc(rails.get("max_operations_per_call")),
         "Begrenzt den Schaden eines einzelnen Fehlgriffs."),
    )
    zeilen = "".join(
        f'<label>{esc(beschriftung)}<span>{esc(hinweis)}</span>'
        f'<input type="text" name="{name}" value="{wert}"></label>'
        for beschriftung, name, wert, hinweis in felder)
    return sh.karte(
        "Gilt für jedes Konto ohne eigene Grenzen",
        '<p class="note" style="margin-top:0;margin-bottom:4px">Auch neue Konten '
        'starten mit diesen Werten.</p>'
        f'<div class="grid-3" style="align-items:start;margin-top:16px">{zeilen}</div>')


def guardrails_page(message: str = "") -> bytes:
    """Die Seite, die das Bearbeiten der .env von Hand ersetzt."""
    state = load_state()
    rails = state["guardrails"]
    je_konto = rails.get("per_account") or {}
    erlaubt = set(rails.get("allowed_customer_ids") or [])
    deckel = rails.get("max_daily_budget_micros") or 0
    lesbar = [a for a in state["accounts"] if not a["problem"]]
    schreibend = [a for a in lesbar if not erlaubt or a["id"] in erlaubt]
    hoechstes = max([je_konto.get(a["id"], {}).get("max_daily_budget_micros", deckel)
                     for a in state["accounts"]] + [deckel])

    karten = "".join(_kontogrenze(konto, je_konto.get(konto["id"]) or {}, rails,
                                  erlaubt)
                     for konto in state["accounts"])
    if not karten and erlaubt:
        grund = (f' ({esc(state["error"].splitlines()[0])})' if state.get("error")
                 else "")
        liste = "".join(f'<li class="mono">{esc(kennung)}</li>'
                        for kennung in sorted(erlaubt))
        karten = (sh.warnung(f"Die Kontenliste ließ sich gerade nicht lesen{grund}. "
                             f"Berechtigt ist unverändert, was hier steht; zum Ändern "
                             f"zuerst die Verbindung prüfen.")
                  + sh.karte("Derzeit berechtigt",
                             f'<ol class="codes">{liste}</ol>', art="flach"))
    elif not karten:
        karten = sh.karte(inhalt='<p class="note" style="margin-top:0">Noch keine '
                                 'Konten gelesen. Erst verbinden, dann steht hier je '
                                 'Konto eine Karte.</p>', art="flach")

    # Der Hinweis auf die .env steht nur, solange sie noch etwas zu sagen hat.
    startwerte = ""
    if not grenzen_gespeichert() and env_startwerte():
        startwerte = sh.hinweis(
            "Diese Werte stammen aus der <code>.env</code> und sind Anfangswerte. "
            "Sobald hier einmal gespeichert wurde, entscheidet diese Seite — die "
            "Variablen werden dann nicht mehr angesehen.")

    zaehler = (f'{len(schreibend)} <span style="color:var(--faint);font-weight:400">'
               f'/ {len(state["accounts"])}</span>' if state["accounts"] else "—")
    inhalt = (
        (sh.warnung(esc(message), "gut") if message else "")
        + startwerte
        + sh.hinweis("Grenzen gelten <b>je Konto</b>. Ein kampagnenstarker Kunde darf "
                     "120 am Tag bewegen, ein kleiner 8 — der Standard unten greift "
                     "nur, wo ein Konto keine eigenen Werte gesetzt hat.")
        + '<div class="grid-3 gleich" style="margin-bottom:24px">'
        + sh.kennzahl("Konten mit Schreibrecht", zaehler,
                      neon=bool(rails.get("write_enabled")))
        + sh.kennzahl("Höchstes Tagesbudget",
                      geldbetrag(hoechstes) if hoechstes else "ohne Deckel")
        + sh.kennzahl("Eigene Grenzen gesetzt",
                      f"{len(je_konto)} {'Konto' if len(je_konto) == 1 else 'Konten'}")
        + '</div>'
        + '<form method="post" action="/guardrails">'
        + sh.karte("Schreiben",
                   sh.ankreuzzeile("write_enabled", "Schreiben erlauben",
                                   "Der Hauptschalter über allem. Ohne diesen Haken "
                                   "sind nur Trockenläufe möglich, gleich was je "
                                   "Konto steht. Lesen geht immer.",
                                   an=bool(rails.get("write_enabled"))),
                   zustand=(sh.zustand("eingeschaltet", "warn")
                            if rails.get("write_enabled")
                            else sh.zustand("aus", "ok")))
        + '<span class="eyebrow neon" style="margin-top:32px;display:block">Je Konto'
          '</span>'
        + '<p class="note" style="margin:8px 0 0">Kein Haken bei <b>keinem</b> Konto '
          'heißt <b>alle zugänglichen</b> — bei eingeschaltetem Schreiben ist das '
          'selten gemeint.</p>'
        + f'<div class="stack" style="margin:14px 0 32px">{karten}</div>'
        + '<span class="eyebrow neon" style="display:block;margin-bottom:14px">'
          'Standard</span>'
        + _standardkarte(rails)
        + '<div class="row" style="margin-top:20px">'
          '<button type="submit">Speichern</button>'
          '<a class="button quiet" href="/dashboard">Abbrechen</a></div>'
        + '</form>'
        + '<p class="note">Auch mit Schreibrecht ist jeder Aufruf zuerst ein '
          'Trockenlauf — scharf wird er erst nach ausdrücklicher Freigabe im '
          'Gespräch.</p>')

    return konsole(
        "Schutzgrenzen",
        "Was überhaupt möglich ist. Ob eine einzelne Änderung dann geschieht, "
        "entscheidet die Freigabe im Gespräch.",
        "/guardrails", inhalt, skript=sh.GRENZEN_JS)


def _zahl_aus(form: dict, name: str, faktor: int, ganzzahlig: bool):
    """Eine Zahl aus dem Formular. Gibt (gefunden, Wert, Klage) zurueck.

    Ein leeres Feld ist keine Null, sondern keine Angabe: sonst macht ein
    versehentlich geleertes Feld aus einem Budgetdeckel ein "kein Deckel".
    """
    roh = (form.get(name) or [""])[0].strip().replace(",", ".")
    if not roh:
        return False, None, ""
    try:
        wert = float(roh) * faktor
    except ValueError:
        return False, None, f"„{roh}“ ist keine Zahl."
    if wert < 0:
        return False, None, "Negative Werte ergeben hier keinen Sinn."
    return True, (int(wert) if ganzzahlig else wert), ""


# Formularfeld, Ziel in den Schutzgrenzen, Faktor, ganzzahlig
STANDARDFELDER = (("max_daily_budget", "max_daily_budget_micros", 1_000_000, True),
                  ("max_budget_increase_factor", "max_budget_increase_factor", 1, False),
                  ("max_operations_per_call", "max_operations_per_call", 1, True))
KONTOFELDER = (("budget", "max_daily_budget_micros", 1_000_000, True),
               ("faktor", "max_budget_increase_factor", 1, False),
               ("ops", "max_operations_per_call", 1, True))


def save_accounts(form: dict) -> tuple[bool, str]:
    """Schritt 3 der Schiene speichert nur die Kontenliste, sonst nichts.

    Die Schutzgrenzen daneben bleiben, wie sie sind: dieser Schritt fragt
    nach den Konten und darf keine Budgetgrenze mitverstellen, nur weil
    sein Formular sie nicht mitschickt.
    """
    return save_guardrails({"konto": form.get("konto") or [],
                            "konten_gestellt": form.get("konten_gestellt") or [],
                            "write_enabled": _bisheriges_schreiben()})


def _bisheriges_schreiben() -> list:
    """Was gerade eingestellt ist — als Formularwert, damit es so bleibt."""
    return ["1"] if _gespeicherte_grenzen().get("write_enabled") else []


def _gespeicherte_grenzen() -> dict:
    """Die Grenzen, wie sie in der Datei stehen — ohne die Umgebung.

    Gespeichert wird gegen die Datei, nicht gegen den zusammengesetzten
    Stand: sonst schriebe der erste Klick in der Konsole die Anfangswerte
    aus der .env fest, auch wo der Betreiber nichts angefasst hat.
    """
    rails = copy.deepcopy(gac.DEFAULT_GUARDRAILS)
    if gac.CONFIG_FILE.exists():
        try:
            gespeichert = json.loads(gac.CONFIG_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return rails
        if gespeichert.get("guardrails"):
            rails.update(gespeichert["guardrails"])
        else:
            # Noch nie gespeichert: was die Umgebung vorgibt, ist der Stand,
            # den der Betreiber gerade vor sich sieht.
            rails = gac._guardrails_from_env(rails)  # noqa: SLF001
    return rails


def save_guardrails(form: dict) -> tuple[bool, str]:
    """Schreibt die Schutzgrenzen in die Konfigurationsdatei.

    Jeder Abschnitt des Formulars traegt einen Merker. Fehlt er, laesst
    das Speichern diesen Abschnitt unberuehrt — ein Formular, das die
    Konten nicht anzeigen konnte, darf die Berechtigung nicht als "kein
    Haken" lesen, denn kein Haken heisst ALLE Konten.
    """
    vergiss_stand()
    config = {}
    if gac.CONFIG_FILE.exists():
        try:
            config = json.loads(gac.CONFIG_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            config = {}
    rails = _gespeicherte_grenzen()
    rails["write_enabled"] = bool(form.get("write_enabled"))

    unberuehrt = False
    if not form.get("konten_gestellt") and not form.get("grenze_gestellt"):
        unberuehrt = True
    else:
        konten = []
        for wert in form.get("konto") or []:
            try:
                konten.append(gac.normalize_customer_id(wert))
            except gac.GoogleAdsError as exc:
                return False, exc.message
        rails["allowed_customer_ids"] = konten

    for feldname, ziel, faktor, ganzzahlig in STANDARDFELDER:
        gefunden, wert, klage = _zahl_aus(form, feldname, faktor, ganzzahlig)
        if klage:
            return False, klage
        if gefunden:
            rails[ziel] = wert

    # -- Grenzen je Konto --------------------------------------------------
    gezeigt = []
    for roh in form.get("grenze_gestellt") or []:
        try:
            gezeigt.append(gac.normalize_customer_id(roh))
        except gac.GoogleAdsError as exc:
            return False, exc.message
    if gezeigt:
        mit_eigenen = set()
        for roh in form.get("eigene") or []:
            try:
                mit_eigenen.add(gac.normalize_customer_id(roh))
            except gac.GoogleAdsError as exc:
                return False, exc.message
        je_konto = dict(gac.per_account_sauber(rails.get("per_account")))
        for kennung in gezeigt:
            if kennung not in mit_eigenen:
                je_konto.pop(kennung, None)
                continue
            eintrag = {}
            for vorsilbe, ziel, faktor, ganzzahlig in KONTOFELDER:
                gefunden, wert, klage = _zahl_aus(form, f"{vorsilbe}_{kennung}",
                                                  faktor, ganzzahlig)
                if klage:
                    return False, f"Konto {kennung}: {klage}"
                if gefunden:
                    eintrag[ziel] = wert
            # Ein Haken ohne eine einzige Zahl waere eine Zusage ohne Inhalt.
            # Dann gilt weiter der Standard, und die Karte sagt das auch.
            if eintrag:
                je_konto[kennung] = eintrag
            else:
                je_konto.pop(kennung, None)
        rails["per_account"] = je_konto

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
    eigene = len(rails.get("per_account") or {})
    if eigene:
        meldung += (f" {eigene} {'Konto' if eigene == 1 else 'Konten'} "
                    f"mit eigenen Grenzen.")
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
        return konsole("Zugangswort", "Ab sofort gilt das neue Wort.",
                       "/dashboard", f"""<div class="card akzent">
<p>Ab sofort gilt dieses Wort. Das alte ist ungültig — auch für den
Connector in claude.ai, der neu eingetragen werden muss.</p>
<pre>{esc(neues)}</pre>
<p class="note">Jetzt in einen Passwortspeicher übernehmen. Diese Seite zeigt
es kein zweites Mal; danach steht es nur noch in
<code>{esc(token_file)}</code> auf dem Server.</p>
<div class="row" style="margin-top:18px">
<a class="button" href="/dashboard">Zurück zur Übersicht</a></div></div>""")
    return konsole("Zugangswort",
                   "Der Schlüssel des MCP-Endpunkts — das, was claude.ai als "
                   "Authorization: Bearer … mitschickt.",
                   "/dashboard", """<div class="card">
<p>Mit deiner Anmeldung an diesem Portal hat das Wort nichts zu tun. Ein
Wechsel sperrt niemanden hier aus; er macht nur das alte Wort sofort
ungültig. Der Connector in claude.ai trägt das alte und muss danach neu
eingetragen werden — bis dahin antwortet der Server ihm mit einer
Abweisung.</p>
<form method="post" action="/setup/token" class="row" style="margin-top:18px">
<button class="danger" type="submit">Neues Zugangswort erzeugen</button>
<a class="button quiet" href="/dashboard">Abbrechen</a>
</form></div>""")


def disconnect() -> tuple[bool, str]:
    """Forgets the refresh token, keeps everything else."""
    vergiss_stand()
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
