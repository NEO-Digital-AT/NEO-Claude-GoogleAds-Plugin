#!/usr/bin/env python3
"""The pages that belong to the portal itself: signing in, and the account.

Everything under /setup is about Google. Everything here is about the
person looking at it — signing in, the second factor, the user name, the
e-mail address, the password, and which browsers are currently signed in.

The two are deliberately separate files: the Google pages talk to Google's
API, these talk to portal_store, and neither needs to know how the other
works.

German on the page because a person reads it; English in the code, like
every other tool here.
"""
from __future__ import annotations

import google_ads_setup as ui
import portal_qr
import portal_store as store
import portal_totp as totp

esc = ui.esc


def _feld(name: str, beschriftung: str, hinweis: str = "", *, art: str = "text",
          wert: str = "", extra: str = "") -> str:
    zusatz = f"<span>{esc(hinweis)}</span>" if hinweis else ""
    return (f'<label>{esc(beschriftung)}{zusatz}'
            f'<input type="{art}" name="{name}" value="{esc(wert)}" {extra}></label>')


def _meldung(text: str, art: str = "akzent") -> str:
    return f'<div class="card {art}"><p>{esc(text)}</p></div>' if text else ""


# -- signing in ------------------------------------------------------------

def login_page(message: str = "", username: str = "", *, first_run: bool = False) -> bytes:
    """The front door. Deliberately says nothing about what is behind it."""
    ui.set_viewer("")
    hinweis = ""
    if first_run:
        hinweis = ('<div class="card akzent"><h2 style="margin-top:0">Erste Anmeldung</h2>'
                   '<p class="note" style="margin-top:0">Das Konto stammt aus '
                   '<code>INIT_USER</code> und <code>INIT_PASS</code> in der '
                   '<code>.env</code>. Nach der Anmeldung Kennwort ändern und die '
                   'beiden Zeilen aus der <code>.env</code> entfernen — sie werden '
                   'nicht mehr gebraucht und stehen sonst im Klartext auf dem '
                   'Server.</p></div>')
    return ui.page("Anmeldung", f"""
<h1>Anmeldung</h1>
<p class="lead">Verwaltung des Google-Ads-Zugangs</p>
{hinweis}
{_meldung(message, "schlecht") if message else ""}
<form method="post" action="/anmelden">
<div class="card">
{_feld("benutzer", "Benutzername oder E-Mail", wert=username,
       extra='autocomplete="username" autofocus required')}
{_feld("kennwort", "Kennwort", art="password",
       extra='autocomplete="current-password" required')}
</div>
<button type="submit">Anmelden</button>
</form>
<p class="note">Kennwort vergessen? Das wird auf dem Server zurückgesetzt, mit
<code>--set-password</code>. Per E-Mail geht hier nichts hinaus.</p>""",
                   schmal=True)


def second_factor_page(message: str = "", *, name: str = "") -> bytes:
    """Step two. The session exists but counts for nothing until this passes."""
    ui.set_viewer("")
    wer = f"Angemeldet als {esc(name)}" if name else "Kennwort stimmt"
    return ui.page("Bestätigung", f"""
<h1>Zweiter Faktor</h1>
<p class="lead">{wer} — jetzt der Code aus der App</p>
{_meldung(message, "schlecht") if message else ""}
<form method="post" action="/anmelden/code">
<div class="card">
{_feld("code", "Sechsstelliger Code",
       extra='inputmode="numeric" autocomplete="one-time-code" pattern="[0-9 ]*" '
             'autofocus required')}
<p class="note">Kein Telefon zur Hand? Statt des Codes einen
Wiederherstellungscode eingeben — jeder gilt genau einmal.</p>
</div>
<button type="submit">Bestätigen</button>
</form>
<p class="note"><a href="/abbrechen">Abbrechen und neu anmelden</a></p>""",
                   schmal=True)


# -- the account -----------------------------------------------------------

def account_page(user, sessions, *, recovery_left: int = 0, message: str = "",
                 trouble: str = "", current_token_hash: str = "") -> bytes:
    """User name, e-mail, password, second factor, and the open sessions."""
    zwei = bool(user["totp_confirmed"])
    ui.set_viewer(user["username"], two_factor=zwei)

    zeilen = []
    for sitzung in sessions:
        hier = sitzung["token_hash"] == current_token_hash
        wo = sitzung["address"] or "unbekannt"
        womit = (sitzung["agent"] or "").split(")")[0][:60] or "unbekannt"
        marke = '<span class="state ok">dieser Browser</span>' if hier else ""
        wann = sitzung["seen"][:16].replace("T", " ")
        zeilen.append(f'<tr><th class="mono">{esc(wann)}</th>'
                      f'<td>{esc(wo)} {marke}'
                      f'<br><span class="note">{esc(womit)}</span></td></tr>')

    if zwei:
        zwei_karte = f"""<div class="card">
<h2 style="margin-top:0">Zwei-Faktor-Anmeldung <span class="state ok">an</span></h2>
<p class="note" style="margin-top:0">Ohne den Code aus der App kommt niemand
weiter, auch nicht mit dem richtigen Kennwort. Es sind noch
<b>{recovery_left}</b> von {store.RECOVERY_COUNT} Wiederherstellungscodes übrig.</p>
<div class="row">
<form method="post" action="/konto/2fa/neu"><button class="button quiet" type="submit">
Neue Wiederherstellungscodes</button></form>
<form method="post" action="/konto/2fa/aus">
<button class="danger" type="submit">Zwei-Faktor abschalten</button></form>
</div>
<p class="note">Abschalten verlangt das Kennwort nicht noch einmal — die
Sitzung hier gilt bereits als bestätigt. Wer den Zugang verloren hat, kommt
über <code>google-ads-http.py --disable-2fa &lt;Benutzer&gt;</code> auf dem
Server wieder hinein.</p></div>"""
    else:
        zwei_karte = """<div class="card akzent">
<h2 style="margin-top:0">Zwei-Faktor-Anmeldung <span class="state warn">aus</span></h2>
<p class="note" style="margin-top:0">Diese Seite darf Werbebudget verschieben und
steht offen im Netz. Ein zweiter Faktor kostet einmal dreißig Sekunden.</p>
<a class="button" href="/konto/2fa">Einrichten</a></div>"""

    return ui.page("Konto", f"""
<h1>Konto</h1>
<p class="lead">Anmeldedaten, zweiter Faktor und die offenen Sitzungen.</p>
{_meldung(message)}
{_meldung(trouble, "schlecht") if trouble else ""}

<div class="card">
<h2 style="margin-top:0">Name und E-Mail</h2>
<form method="post" action="/konto/name">
{_feld("benutzer", "Benutzername", wert=user["username"], extra="required")}
{_feld("email", "E-Mail", "Nur zur Anzeige. Der Server verschickt nichts.",
       art="email", wert=user["email"])}
<button type="submit">Speichern</button></form></div>

<div class="card">
<h2 style="margin-top:0">Kennwort</h2>
<form method="post" action="/konto/kennwort">
{_feld("alt", "Bisheriges Kennwort", art="password",
       extra='autocomplete="current-password" required')}
{_feld("neu", "Neues Kennwort",
       f"Mindestens {store.MIN_PASSWORD} Zeichen.", art="password",
       extra='autocomplete="new-password" required')}
{_feld("wieder", "Noch einmal", art="password",
       extra='autocomplete="new-password" required')}
<label class="kasten"><input type="checkbox" name="alle_abmelden" checked>
<span class="kasten-text"><b>Andere Sitzungen beenden</b>
<span class="note">Empfohlen. Der Browser hier bleibt angemeldet.</span></span></label>
<button type="submit">Kennwort ändern</button></form></div>

{zwei_karte}

<div class="card">
<h2 style="margin-top:0">Angemeldete Browser</h2>
<table>{"".join(zeilen) or '<tr><td>keine</td></tr>'}</table>
<form method="post" action="/konto/sitzungen">
<button class="button quiet" type="submit">Alle anderen abmelden</button></form></div>""")


def two_factor_page(secret: str, uri: str, message: str = "", *,
                    username: str = "") -> bytes:
    """The QR code, the secret in writing, and the field that proves it works."""
    ui.set_viewer(username)
    bild = portal_qr.svg(portal_qr.matrix(uri.encode("utf-8")))
    lesbar = " ".join(secret[i:i + 4] for i in range(0, len(secret), 4))
    return ui.page("Zwei-Faktor einrichten", f"""
<h1>Zwei-Faktor einrichten</h1>
<p class="lead">Code scannen, dann einmal bestätigen. Erst danach gilt der
zweite Faktor — ein Geheimnis, das nie bewiesen wurde, sperrt sonst nur aus.</p>
{_meldung(message, "schlecht") if message else ""}
<div class="card">
<figure class="qr">{bild}<figcaption>NEO Google Ads</figcaption></figure>
<p class="note">Google Authenticator, Aegis, 1Password, Bitwarden — jede App,
die TOTP kann.</p>
</div>
<div class="card">
<h2 style="margin-top:0">Ohne Kamera</h2>
<p class="note" style="margin-top:0">Denselben Schlüssel von Hand eintragen:</p>
<pre>{esc(lesbar)}</pre>
<p class="note">Typ: zeitbasiert · 6 Stellen · 30 Sekunden · SHA1</p>
</div>
<form method="post" action="/konto/2fa">
<div class="card">
{_feld("code", "Code aus der App",
       "Bestätigt, dass die App und dieser Server dieselbe Uhr meinen.",
       extra='inputmode="numeric" pattern="[0-9 ]*" autocomplete="one-time-code" '
             'autofocus required')}
</div>
<button type="submit">Einschalten</button>
<a class="button quiet" href="/konto">Abbrechen</a>
</form>""")


def recovery_page(codes: list[str], *, username: str = "", neu: bool = False) -> bytes:
    """Shown exactly once. Only the hashes stay behind."""
    ui.set_viewer(username, two_factor=True)
    liste = "".join(f"<li>{esc(code)}</li>" for code in codes)
    return ui.page("Wiederherstellungscodes", f"""
<h1>Wiederherstellungscodes</h1>
<p class="lead">{'Neue Codes — die alten gelten nicht mehr.' if neu
                 else 'Zwei-Faktor ist an.'} Diese Liste erscheint
<b>nur dieses eine Mal</b>. Gespeichert sind hier nur ihre Prüfsummen.</p>
<div class="card akzent">
<ol class="codes">{liste}</ol>
<p class="note">Jeder Code gilt einmal und ersetzt den Code aus der App.
Ausdrucken oder in den Passwortspeicher legen — nicht in dieselbe App, in der
auch der zweite Faktor liegt.</p>
</div>
<a class="button" href="/konto">Gespeichert, weiter</a>""")


def change_password_page(message: str = "", *, username: str = "") -> bytes:
    """Forced on a seeded account, so the .env password does not stay in use."""
    ui.set_viewer(username)
    return ui.page("Kennwort ändern", f"""
<h1>Kennwort ändern</h1>
<p class="lead">Dieses Konto läuft noch mit dem Kennwort aus der
<code>.env</code>. Solange das so ist, steht es im Klartext auf dem Server.</p>
{_meldung(message, "schlecht") if message else ""}
<form method="post" action="/konto/kennwort">
<div class="card">
{_feld("neu", "Neues Kennwort", f"Mindestens {store.MIN_PASSWORD} Zeichen.",
       art="password", extra='autocomplete="new-password" autofocus required')}
{_feld("wieder", "Noch einmal", art="password",
       extra='autocomplete="new-password" required')}
</div>
<button type="submit">Übernehmen</button>
</form>
<p class="note">Angemeldet als {esc(username)} —
<a href="/abbrechen">doch abmelden</a></p>""", schmal=True)
