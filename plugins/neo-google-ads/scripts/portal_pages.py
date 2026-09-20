#!/usr/bin/env python3
"""The pages that belong to the portal itself: signing in, and the account.

Everything under /setup is about Google. Everything here is about the
person looking at it — signing in, the second factor, passkeys, the user
name, the e-mail address, the password, and which browsers are currently
signed in.

The two are deliberately separate files: the Google pages talk to Google's
API, these talk to portal_store, and neither needs to know how the other
works.

German on the page because a person reads it; English in the code, like
every other tool here.
"""
from __future__ import annotations

import google_ads_setup as ui
import portal_qr
import portal_shell as sh
import portal_store as store
import portal_totp as totp  # noqa: F401  (kept for callers importing from here)
from neo_design import esc, symbol


# --------------------------------------------------------------------------
# Passkeys im Browser. Die Kennwortanmeldung braucht davon nichts.
# --------------------------------------------------------------------------
PASSKEY_JS = """
(function () {
  var b64 = function (s) {
    s = String(s).replace(/-/g, '+').replace(/_/g, '/');
    while (s.length % 4) s += '=';
    var roh = atob(s), a = new Uint8Array(roh.length);
    for (var i = 0; i < roh.length; i++) a[i] = roh.charCodeAt(i);
    return a.buffer;
  };
  var url = function (buf) {
    var bytes = new Uint8Array(buf), s = '';
    for (var i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i]);
    return btoa(s).replace(/\\+/g, '-').replace(/\\//g, '_').replace(/=+$/, '');
  };
  window.neoPasskey = {
    b64: b64, url: url,
    holen: function (pfad) {
      return fetch(pfad, { method: 'POST', headers: { 'X-Neo': '1' } })
        .then(function (a) {
          // Mit Statuscode: "Der Server hat die Anfrage abgelehnt" allein
          // sagt niemandem, ob die Sitzung abgelaufen ist (303/403), der
          // Weg fehlt (404) oder Passkeys hier gar nicht gehen (400).
          if (!a.ok) throw new Error('Der Server hat die Anfrage abgelehnt ('
                                     + a.status + ').');
          return a.json();
        });
    },
    melden: function (kasten, text, schlecht) {
      if (!kasten) return;
      kasten.hidden = false;
      kasten.className = 'warnung' + (schlecht ? ' schlecht' : '');
      kasten.querySelector('span').textContent = text;
    }
  };
})();
"""

ANMELDEN_JS = PASSKEY_JS + """
(function () {
  var knopf = document.getElementById('passkey-knopf');
  if (!knopf || !window.PublicKeyCredential) { if (knopf) knopf.hidden = true; return; }
  var meldung = document.getElementById('passkey-meldung');
  var form = document.getElementById('passkey-form');
  knopf.addEventListener('click', function () {
    knopf.disabled = true;
    window.neoPasskey.melden(meldung, 'Der Browser fragt nach Fingerabdruck, Gesicht oder PIN …', false);
    window.neoPasskey.holen('/login/passkey/start').then(function (d) {
      d.challenge = window.neoPasskey.b64(d.challenge);
      (d.allowCredentials || []).forEach(function (c) { c.id = window.neoPasskey.b64(c.id); });
      return navigator.credentials.get({ publicKey: d });
    }).then(function (zeugnis) {
      var r = zeugnis.response;
      form.kennung.value = zeugnis.id;
      form.daten.value = window.neoPasskey.url(r.clientDataJSON);
      form.authenticator.value = window.neoPasskey.url(r.authenticatorData);
      form.signatur.value = window.neoPasskey.url(r.signature);
      form.benutzerkennung.value = r.userHandle ? window.neoPasskey.url(r.userHandle) : '';
      form.submit();
    }).catch(function (e) {
      knopf.disabled = false;
      window.neoPasskey.melden(meldung, e && e.name === 'NotAllowedError'
        ? 'Abgebrochen. Kennwort geht weiterhin.' : (e.message || 'Der Passkey hat nicht geantwortet.'), true);
    });
  });
})();
"""

KONTO_JS = PASSKEY_JS + """
(function () {
  var karte = document.getElementById('passkey-karte');
  if (!karte) return;
  var neu = document.getElementById('passkey-neu');
  var abbrechen = document.getElementById('passkey-ab');
  var warten = document.getElementById('passkey-warten');
  var benennen = document.getElementById('passkey-benennen');
  var meldung = document.getElementById('passkey-meldung');
  var form = document.getElementById('passkey-form');
  var name = form.name;

  if (!window.PublicKeyCredential) {
    neu.disabled = true;
    neu.title = 'Dieser Browser kann keine Passkeys.';
    return;
  }

  var vorschlag = function () {
    var ua = navigator.userAgent;
    var system = /Windows/.test(ua) ? 'Windows' : /Mac/.test(ua) ? 'macOS'
      : /Android/.test(ua) ? 'Android' : /iPhone|iPad/.test(ua) ? 'iOS'
      : 'Dieses Gerät';
    var browser = /Edg\\//.test(ua) ? 'Edge' : /Chrome\\//.test(ua) ? 'Chrome'
      : /Firefox\\//.test(ua) ? 'Firefox' : /Safari\\//.test(ua) ? 'Safari' : 'Browser';
    return system + ' · ' + browser;
  };

  var stufe = function (welche) {
    warten.hidden = welche !== 'warten';
    benennen.hidden = welche !== 'benennen';
    neu.hidden = welche !== 'aus';
    abbrechen.hidden = welche === 'aus';
    if (welche === 'aus') meldung.hidden = true;
  };

  abbrechen.addEventListener('click', function () { stufe('aus'); });

  karte.querySelectorAll('.vorschlag').forEach(function (knopf) {
    knopf.addEventListener('click', function () {
      name.value = knopf.dataset.wert || knopf.textContent.trim();
      name.focus();
    });
  });
  var eigenes = karte.querySelector('.vorschlag[data-eigen]');
  if (eigenes) { eigenes.dataset.wert = vorschlag(); eigenes.textContent = vorschlag(); }

  neu.addEventListener('click', function () {
    stufe('warten');
    window.neoPasskey.holen('/account/passkeys/start').then(function (d) {
      d.challenge = window.neoPasskey.b64(d.challenge);
      d.user.id = window.neoPasskey.b64(d.user.id);
      (d.excludeCredentials || []).forEach(function (c) {
        c.id = window.neoPasskey.b64(c.id);
      });
      return navigator.credentials.create({ publicKey: d });
    }).then(function (zeugnis) {
      form.kennung.value = zeugnis.id;
      form.daten.value = window.neoPasskey.url(zeugnis.response.clientDataJSON);
      form.zeugnis.value = window.neoPasskey.url(zeugnis.response.attestationObject);
      name.value = vorschlag();
      stufe('benennen');
      name.focus();
      name.select();
    }).catch(function (e) {
      stufe('aus');
      window.neoPasskey.melden(meldung, e && e.name === 'NotAllowedError'
        ? 'Abgebrochen — es wurde kein Passkey angelegt.'
        : (e.message || 'Der Browser hat keinen Passkey angelegt.'), true);
    });
  });
})();
"""


def _meldung(text: str, art: str = "") -> str:
    return sh.warnung(esc(text), art) if text else ""


# -- signing in ------------------------------------------------------------

def login_page(message: str = "", username: str = "", *, first_run: bool = False,
               passkeys: bool = False) -> bytes:
    """The front door. Deliberately says nothing about what is behind it."""
    ui.set_viewer("")
    oben = _meldung(message, "schlecht")
    if first_run:
        oben += sh.karte(
            "Erste Anmeldung",
            '<p class="note" style="margin-top:0">Das Konto stammt aus '
            '<code>INIT_USER</code> und <code>INIT_PASS</code> in der '
            '<code>.env</code>. Nach der Anmeldung Kennwort ändern und die beiden '
            'Zeilen aus der <code>.env</code> entfernen — sie werden nicht mehr '
            'gebraucht und stehen sonst im Klartext auf dem Server.</p>',
            art="akzent")

    weg_passkey = ""
    if passkeys:
        weg_passkey = f"""
<div class="trenner">oder</div>
<div id="passkey-meldung" class="warnung" hidden><span></span></div>
<button id="passkey-knopf" class="quiet breit" type="button">
{symbol("passkey", 20)}Mit Passkey anmelden</button>
<form id="passkey-form" method="post" action="/login/passkey" hidden>
<input type="hidden" name="kennung"><input type="hidden" name="daten">
<input type="hidden" name="authenticator"><input type="hidden" name="signatur">
<input type="hidden" name="benutzerkennung"></form>"""

    return ui.schmale_seite(
        "Anmeldung", "Verwaltung deiner Ads-Konten",
        f"""<form method="post" action="/login">
{sh.karte(inhalt=sh.feld("benutzer", "Benutzername oder E-Mail", wert=username,
                         extra='autocomplete="username" autofocus required')
          + sh.feld("kennwort", "Kennwort", art="password",
                    extra='autocomplete="current-password" required')
          + '<button class="breit" type="submit" style="margin-top:22px">Anmelden</button>')}
</form>{weg_passkey}""",
        oben=oben,
        fuss='<span class="note" style="font-size:.82rem">Kennwort vergessen? Das wird '
             'auf dem Server zurückgesetzt, mit <code>--set-password</code>. Per '
             'E-Mail geht hier nichts hinaus.</span>',
        skript=ANMELDEN_JS if passkeys else "")


def second_factor_page(message: str = "", *, name: str = "") -> bytes:
    """Step two. The session exists but counts for nothing until this passes."""
    ui.set_viewer("")
    wer = f"Angemeldet als {name}" if name else "Kennwort stimmt"
    return ui.schmale_seite(
        "Zweiter Faktor", f"{wer} — jetzt der Code aus der App",
        f"""<form method="post" action="/login/code">
{sh.karte(inhalt='<label style="margin-bottom:2px">Sechsstelliger Code</label>'
          + sh.otp_felder(falsch=bool(message))
          + '<p class="note">Kein Telefon zur Hand? Statt des Codes einen '
            'Wiederherstellungscode eingeben — jeder gilt genau einmal.</p>'
          + sh.feld("wieder", "Wiederherstellungscode",
                    "Nur falls die App nicht erreichbar ist.",
                    extra='autocomplete="off" spellcheck="false"')
          + '<button class="breit" type="submit" style="margin-top:22px">Bestätigen</button>')}
</form>""",
        oben=_meldung(message, "schlecht"),
        fuss='<a href="/login/cancel" style="font-size:.86rem">Abbrechen und neu '
             'anmelden</a>',
        skript=sh.OTP_JS)


def change_password_page(message: str = "", *, username: str = "") -> bytes:
    """Forced on a seeded account, so the .env password does not stay in use."""
    ui.set_viewer(username)
    return ui.schmale_seite(
        "Kennwort ändern",
        "Dieses Konto läuft noch mit dem Kennwort aus der .env. Solange das so "
        "ist, steht es im Klartext auf dem Server.",
        f"""<form method="post" action="/account/password">
{sh.karte(inhalt=sh.feld("neu", "Neues Kennwort",
                         f"Mindestens {store.MIN_PASSWORD} Zeichen.", art="password",
                         extra='autocomplete="new-password" autofocus required')
          + sh.feld("wieder", "Noch einmal", art="password",
                    extra='autocomplete="new-password" required')
          + '<button class="breit" type="submit" style="margin-top:22px">Übernehmen</button>')}
</form>""",
        oben=_meldung(message, "schlecht"),
        fuss=f'<span class="note">Angemeldet als {esc(username)} — '
             f'<a href="/login/cancel">doch abmelden</a></span>')


# -- the account -----------------------------------------------------------

def _sitzungszeilen(sessions, current_token_hash: str) -> str:
    zeilen = []
    for sitzung in sessions:
        hier = sitzung["token_hash"] == current_token_hash
        wo = sitzung["address"] or "unbekannt"
        womit = (sitzung["agent"] or "").split(")")[0][:60] or "unbekannt"
        marke = " " + sh.zustand("dieser Browser", "ok") if hier else ""
        wann = sitzung["seen"][:16].replace("T", " ")
        zeilen.append(sh.zeile(wann, esc(wo) + marke, womit, mono=True))
    return "".join(zeilen)


def _passkeyzeilen(passkeys) -> str:
    zeilen = []
    for schluessel in passkeys:
        benutzt = schluessel["used"][:10] if schluessel["used"] else "noch nie"
        weg = (f'<form method="post" action="/account/passkeys/delete" '
               f'style="display:inline">'
               f'<input type="hidden" name="kennung" value="{esc(schluessel["id"])}">'
               f'<button class="ghost klein" type="submit">Entfernen</button></form>')
        zeilen.append(
            f'<tr><th style="text-transform:none;letter-spacing:0;font-size:.9rem;'
            f'color:var(--fg);width:auto">'
            f'<span class="werkzeile">{symbol("passkey", 20)}'
            f'{esc(schluessel["name"])}</span></th>'
            f'<td><span class="leise">angelegt {esc(schluessel["created"][:10])} · '
            f'zuletzt {esc(benutzt)}</span></td>'
            f'<td style="width:1%;text-align:right">{weg}</td></tr>')
    return "".join(zeilen)


def account_page(user, sessions, *, recovery_left: int = 0, message: str = "",
                 trouble: str = "", current_token_hash: str = "",
                 passkeys=(), passkeys_moeglich: bool = True,
                 ueberlagerung: str = "") -> bytes:
    """User name, e-mail, password, second factor, passkeys, open sessions."""
    zwei = bool(user["totp_confirmed"])
    ui.set_viewer(user["username"], two_factor=zwei)

    if zwei:
        zwei_karte = sh.karte(
            "Zwei-Faktor-Anmeldung",
            f'<p class="note" style="margin-top:0">Ohne den Code aus der App kommt '
            f'niemand weiter, auch nicht mit dem richtigen Kennwort. Es sind noch '
            f'<b>{recovery_left}</b> von {store.RECOVERY_COUNT} '
            f'Wiederherstellungscodes übrig.</p>'
            f'<div class="row" style="margin-top:20px">'
            f'<form method="post" action="/account/2fa/new">'
            f'<button class="quiet" type="submit">Neue Wiederherstellungscodes</button>'
            f'</form>'
            f'<form method="post" action="/account/2fa/off">'
            f'<button class="danger" type="submit">Zwei-Faktor abschalten</button>'
            f'</form></div>'
            f'<p class="note">Wer den Zugang verloren hat, kommt über '
            f'<code>google-ads-http.py --disable-2fa &lt;Benutzer&gt;</code> auf dem '
            f'Server wieder hinein.</p>',
            zustand=sh.zustand("an", "ok"))
    else:
        zwei_karte = sh.karte(
            "Zwei-Faktor-Anmeldung",
            '<p class="note" style="margin-top:0">Diese Seite darf Werbebudget '
            'verschieben und steht offen im Netz. Ein zweiter Faktor kostet einmal '
            'dreißig Sekunden.</p>'
            '<div class="row" style="margin-top:20px">'
            f'<a class="button" href="/account/2fa">{symbol("shield_lock", 20)}'
            'Zwei-Faktor einschalten</a></div>',
            zustand=sh.zustand("aus", "warn"), art="akzent")

    # Der Ablauf des Entwurfs: der Knopf startet die Abfrage des Geraets,
    # waehrenddessen steht die Wartemeldung, und erst wenn der Schluessel
    # da ist, erscheint die Karte mit dem Namensfeld. Ohne JavaScript geht
    # WebAuthn ueberhaupt nicht, also bleiben beide Stufen verborgen und
    # der Knopf sperrt sich selbst — ein Namensfeld, das ins Leere fuehrt,
    # stand vorher dauerhaft in der Karte.
    vorschlaege = ("Büro-PC · Windows Hello", "iPhone · Face ID",
                   "YubiKey · Schlüsselbund")
    knoepfe = ('<button type="button" class="ghost klein vorschlag" data-eigen="1">'
               'Dieses Gerät</button>')
    knoepfe += "".join(
        f'<button type="button" class="ghost klein vorschlag">{esc(wort)}</button>'
        for wort in vorschlaege)

    passkey_karte = sh.karte(
        "Passkeys",
        '<p class="note" style="margin-top:0;margin-bottom:14px">Ein Passkey ersetzt '
        'Kennwort und Code in einem Schritt. Der Schlüssel bleibt auf dem Gerät; der '
        'Server kennt nur den öffentlichen Teil.</p>'
        '<div id="passkey-meldung" class="warnung" hidden><span></span></div>'

        f'<div id="passkey-warten" class="card flach werkzeile" '
        f'style="gap:16px;margin-bottom:16px" hidden>{symbol("passkey", 32)}'
        f'<div><b style="display:block">Der Browser fragt nach Fingerabdruck, '
        f'Gesicht oder PIN …</b><span class="note" style="display:block;'
        f'margin-top:4px">Bestätige die Abfrage des Geräts. Danach bekommt der '
        f'Passkey einen Namen.</span></div></div>'

        + '<form id="passkey-form" method="post" action="/account/passkeys">'
          '<input type="hidden" name="kennung"><input type="hidden" name="daten">'
          '<input type="hidden" name="zeugnis">'
          '<div id="passkey-benennen" class="card akzent" '
          'style="margin-bottom:16px" hidden>'
          '<div class="card-kopf"><h2>Gerät benennen '
        + sh.zustand("Schlüssel angelegt", "ok") + '</h2></div>'
        + sh.feld("name", "Bezeichnung des Geräts",
                  "Frei wählbar — der Name steht später in dieser Liste und im "
                  "Anmeldeprotokoll. Nimm etwas, das du in einem Jahr noch "
                  "zuordnest.",
                  extra='autocomplete="off" maxlength="60"')
        + f'<div class="row eng" style="margin-top:12px">'
          f'<span class="eyebrow" style="margin-right:4px">Vorschläge</span>'
          f'{knoepfe}</div>'
          '<div class="row" style="margin-top:18px">'
          '<button type="submit">Passkey speichern</button></div>'
          '</div></form>'

        + sh.tabelle(_passkeyzeilen(passkeys), "noch keiner angelegt")
        + '<p class="note">Einen Passkey zu entfernen ist endgültig — das Gerät '
          'meldet sich danach wieder mit Kennwort und Code an.</p>',
        aktion=f'<button id="passkey-neu" class="quiet klein" type="button"'
               f'{"" if passkeys_moeglich else " disabled"}>'
               + symbol("add", 18) + 'Passkey hinzufügen</button>'
               + '<button id="passkey-ab" class="ghost klein" type="button" hidden>'
                 'Abbrechen</button>',
        kennung="passkey-karte")
    if not passkeys_moeglich:
        # Ueber eine nackte Adresse laesst der Browser WebAuthn nicht zu. Das
        # einmal auszusprechen ist besser als ein Knopf, der immer scheitert.
        passkey_karte = passkey_karte.replace(
            '<div id="passkey-meldung" class="warnung" hidden><span></span></div>',
            sh.warnung("Dieser Server wird gerade über eine IP-Adresse aufgerufen. "
                       "Passkeys verlangen einen Hostnamen — unter "
                       "ads.mcp.neo-digital.at gehen sie, unter 1.2.3.4 nicht."))

    inhalt = f"""<div class="stack">
{sh.karte("Name und E-Mail",
          '<form method="post" action="/account/name"><div class="grid-2">'
          + sh.feld("benutzer", "Benutzername", wert=user["username"], extra="required")
          + sh.feld("email", "E-Mail", "Nur zur Anzeige. Der Server verschickt nichts.",
                    art="email", wert=user["email"])
          + '</div><button type="submit" style="margin-top:22px">Speichern</button>'
            '</form>')}
{sh.karte("Kennwort",
          '<form method="post" action="/account/password">'
          '<div class="grid-3" style="align-items:start">'
          + sh.feld("alt", "Bisheriges Kennwort", "Zur Sicherheit noch einmal.",
                    art="password", extra='autocomplete="current-password" required')
          + sh.feld("neu", "Neues Kennwort", f"Mindestens {store.MIN_PASSWORD} Zeichen.",
                    art="password", extra='autocomplete="new-password" required')
          + sh.feld("wieder", "Noch einmal", "Muss übereinstimmen.", art="password",
                    extra='autocomplete="new-password" required')
          + '</div><div style="margin-top:18px">'
          + sh.ankreuzzeile("alle_abmelden", "Andere Sitzungen beenden",
                            "Empfohlen. Der Browser hier bleibt angemeldet.", an=True)
          + '</div><button type="submit" style="margin-top:22px">Kennwort ändern'
            '</button></form>')}
{zwei_karte}
{passkey_karte}
{sh.karte("Angemeldete Browser",
          sh.tabelle(_sitzungszeilen(sessions, current_token_hash), "keine"),
          aktion='<form method="post" action="/account/sessions">'
                 '<button class="quiet klein" type="submit">Alle anderen abmelden'
                 '</button></form>')}
</div>"""

    return ui.konsole(
        "Konto", "Anmeldedaten, zweiter Faktor, Passkeys und die offenen Sitzungen.",
        "/account", _meldung(message, "gut") + _meldung(trouble, "schlecht") + inhalt,
        ueberlagerung=ueberlagerung,
        skript=KONTO_JS + (sh.OTP_JS if ueberlagerung else ""))


def two_factor_overlay(secret: str, uri: str, message: str = "") -> str:
    """The setup of the second factor, over the account page.

    It is a page, not a dialog conjured up by JavaScript: the server draws
    the QR code, so the secret never has to reach the browser as anything
    but a picture, and the whole thing works with scripting switched off.
    """
    bild = portal_qr.svg(portal_qr.matrix(uri.encode("utf-8")))
    lesbar = " ".join(secret[i:i + 4] for i in range(0, len(secret), 4))
    return f"""<div class="ueber"><div class="tafel">
<div class="kopf"><h2>Zwei-Faktor einschalten</h2>
<a class="button ghost zu" href="/account" aria-label="Schließen">
{symbol("close", 20)}</a></div>
<p class="note" style="margin-top:0;margin-bottom:20px;max-width:none">Code scannen,
dann einmal bestätigen. Erst danach gilt der zweite Faktor — ein Geheimnis, das nie
bewiesen wurde, sperrt sonst nur aus.</p>
{_meldung(message, "schlecht")}
<div class="zweispalt">
<figure class="qr">{bild}<figcaption>{esc(ui.MARKE)}</figcaption></figure>
<div style="min-width:0">
<ol class="schritte">
<li>App öffnen — Google Authenticator, Aegis, 1Password, Bitwarden.</li>
<li>Code scannen oder den Schlüssel von Hand eintragen.</li>
<li>Den sechsstelligen Code unten bestätigen.</li>
</ol>
<div style="margin-top:16px"><pre>{esc(lesbar)}</pre></div>
<p class="note" style="margin-top:8px">Typ: zeitbasiert · 6 Stellen · 30 Sekunden
· SHA1</p>
</div></div>
<form method="post" action="/account/2fa">
<div style="margin-top:24px;padding-top:20px;border-top:1px solid var(--line-soft)">
<label style="margin-top:0">Code aus der App</label>
{sh.otp_felder(falsch=bool(message))}
<p class="note" style="margin-top:10px">Bestätigt, dass die App und dieser Server
dieselbe Uhr meinen.</p>
</div>
<div class="row" style="margin-top:24px">
<button type="submit">Einschalten</button>
<a class="button quiet" href="/account">Abbrechen</a>
</div></form>
</div></div>"""


def recovery_page(codes: list[str], *, username: str = "", neu: bool = False) -> bytes:
    """Shown exactly once. Only the hashes stay behind."""
    ui.set_viewer(username, two_factor=True)
    liste = "".join(f"<li>{esc(code)}</li>" for code in codes)
    lead = ("Neue Codes — die alten gelten nicht mehr." if neu
            else "Zwei-Faktor ist an.")
    return ui.konsole(
        "Wiederherstellungscodes",
        f"{lead} Diese Liste erscheint nur dieses eine Mal.",
        "/account",
        sh.karte(inhalt=f'<span class="eyebrow neon">Erscheint nur dieses eine Mal'
                        f'</span><ol class="codes" style="margin-top:12px">{liste}</ol>'
                        f'<p class="note">Jeder Code gilt einmal und ersetzt den Code '
                        f'aus der App. Ausdrucken oder in den Passwortspeicher legen — '
                        f'nicht in dieselbe App, in der auch der zweite Faktor liegt.'
                        f'</p>', art="akzent")
        + '<div class="row" style="margin-top:20px">'
          '<a class="button" href="/account">Gespeichert, weiter</a></div>')
