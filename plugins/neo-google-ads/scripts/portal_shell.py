#!/usr/bin/env python3
"""The frame every page of the management console sits in.

Two frames, really. The wide one is the console itself: a sidebar with the
five ways through it, a sticky header with the page title and whoever is
signed in, and a column of 1080 pixels for the content. The narrow one is
for the pages with a single job — signing in, the second factor, the
forced password change. A form of 54rem with two fields in it looks like a
mistake, because it is one.

Both come from the design system (ui_kits/portal). What is here is the
frame and the pieces that only the console uses: the sidebar, the step
rail of the setup, the six digit fields, the notice bar, the overlay. The
tokens and everything two pages share are in neo_design.

ABOUT JAVASCRIPT: the console got by without any, and almost all of it
still does. Two places need it and cannot be talked out of it. Passkeys
are a browser API — there is no form that does WebAuthn. And the six digit
fields want the focus to move along as you type. Both degrade: without
JavaScript the digit fields are six ordinary inputs that submit together,
and the sign-in page keeps password and second factor. Nothing is loaded
from anywhere; the handful of lines stands in the page.

German on the page because a person reads it, English in the code.
"""
from __future__ import annotations

import neo_design
from neo_design import esc, symbol

# Die Wege der Seitenleiste. Der Pfad ist englisch wie jeder andere
# technische Bezeichner hier, die Beschriftung deutsch wie jeder andere
# Text, den jemand liest.
WEGE = (
    ("/dashboard", "Übersicht", "dashboard"),
    ("/setup", "Einrichtung", "conversion_path"),
    ("/guardrails", "Schutzgrenzen", "shield_lock"),
    ("/check", "Prüfung", "checklist"),
    ("/clients", "Verbundene Apps", "devices"),
    ("/account", "Konto", "account_circle"),
)


ANWENDUNG_CSS = """
/* Der Ladebalken. Eine Seite dieser Konsole entsteht am Server und fragt
   dabei Google ab; das dauert. Der Browser zeigt bis dahin die alte Seite,
   also sah ein Klick aus wie nichts. Der Balken laeuft sofort los und
   verschwindet mit der neuen Seite. */
.laeuft{position:fixed;top:0;left:0;right:0;height:3px;z-index:200;
  pointer-events:none;overflow:hidden}
.laeuft::after{content:"";display:block;height:100%;width:0;
  background:var(--grad-accent);box-shadow:0 0 12px var(--neon);
  transition:width 6s cubic-bezier(.05,.8,.1,1)}
body.laedt .laeuft::after{width:92%}
body.laedt{cursor:progress}
@media (prefers-reduced-motion: reduce){
  .laeuft::after{transition:none}
  body.laedt .laeuft::after{width:100%}
}

.app{display:flex;min-height:100vh;background:var(--ink-950)}
.leiste{width:var(--sidebar-width);flex:none;padding:22px 14px;
  border-right:1px solid var(--line);background:var(--ink-900);display:flex;
  flex-direction:column;gap:26px;position:sticky;top:0;align-self:flex-start;
  min-height:100vh}
.leiste .marke{padding:4px 10px 0;display:block;text-decoration:none}
.leiste .marke svg{height:24px;width:auto;color:var(--neon);filter:var(--glow-logo)}
.leiste .marke .eyebrow{margin-top:10px;white-space:nowrap;letter-spacing:.11em;color:var(--faint)}
.leiste nav{display:grid;gap:2px}
.leiste nav a{display:flex;align-items:center;gap:12px;padding:10px 12px;
  border-radius:var(--radius-md);text-decoration:none;font-size:.93rem;
  font-weight:var(--weight-medium);color:var(--muted);
  transition:var(--transition-control)}
.leiste nav a:hover{color:var(--fg);background:var(--ink-750)}
.leiste nav a[aria-current=page]{color:var(--neon);background:var(--tint-neon-08);
  box-shadow:inset 0 0 0 1px color-mix(in srgb,var(--neon) 20%,transparent)}
.leiste nav .sym{flex:none}
.leiste .fuss{margin-top:auto;padding:12px 12px 0;border-top:1px solid var(--line);
  display:grid;gap:6px;justify-items:start}
.leiste .fuss .wo{font-size:.84rem;color:var(--muted);overflow-wrap:anywhere}

.blatt{flex:1;min-width:0;background:var(--ink-900);background-image:var(--page-glow);
  background-repeat:no-repeat}
.app-kopf{display:flex;align-items:center;gap:16px;padding:14px 32px;
  border-bottom:1px solid var(--line);position:sticky;top:0;z-index:5;
  background:color-mix(in srgb, var(--ink-900) 88%, transparent);
  backdrop-filter:blur(10px)}
.app-kopf .wo{font-size:.9rem;color:var(--muted)}
.app-kopf .wer{margin-left:auto;display:flex;align-items:center;gap:12px;
  font-size:.86rem;color:var(--muted)}
.app-kopf form{display:inline-flex;margin:0}
.app-inhalt{max-width:var(--measure-app);margin:0 auto;padding:36px 32px 80px}
.seitenkopf{display:flex;align-items:flex-end;gap:20px;margin-bottom:28px}
.seitenkopf .rechts{margin-left:auto;flex:none}

/* Schmale Seiten: Anmeldung, zweiter Faktor, erzwungenes Kennwort */
.schmal{max-width:var(--measure-narrow);margin:0 auto;padding:72px 20px 80px}
.schmal .marke{display:flex;justify-content:center}
.schmal .marke svg{height:26px;width:auto;color:var(--neon);filter:var(--glow-logo)}
.schmal .titel{text-align:center;margin:28px 0 22px}
.schmal .titel h1{font-size:var(--size-h1-sm)}
.schmal .titel .lead{margin:8px auto 0;font-size:.95rem}
.schmal .fuss{text-align:center;margin-top:26px}
.trenner{display:flex;align-items:center;gap:14px;margin:20px 0;color:var(--faint);
  font-size:.78rem;letter-spacing:var(--tracking-eyebrow);text-transform:uppercase}
.trenner::before,.trenner::after{content:"";flex:1;height:1px;background:var(--line)}

/* Sechs Ziffernfelder statt eines Kastens */
.otp{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:10px;
  margin-top:var(--space-2)}
.otp input{margin-top:0;padding:0;text-align:center;font-family:var(--font-mono);
  font-size:1.35rem;letter-spacing:.02em;min-height:56px;
  -moz-appearance:textfield;appearance:textfield}
.otp input::-webkit-outer-spin-button,.otp input::-webkit-inner-spin-button{
  -webkit-appearance:none;margin:0}
.otp.falsch input{border-color:var(--bad)}

/* Die Schiene der Einrichtung */
.schiene{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:26px}
.schiene a{flex:1 1 180px;display:flex;align-items:center;gap:10px;padding:12px 14px;
  border:1px solid var(--line);border-radius:var(--radius-md);background:var(--ink-850);
  color:var(--muted);text-decoration:none;font-size:.9rem;
  font-weight:var(--weight-medium);transition:var(--transition-control)}
.schiene a:hover{border-color:var(--border-hover);color:var(--fg)}
.schiene a[aria-current=step]{border-color:var(--border-accent);color:var(--fg);
  background:color-mix(in srgb,var(--neon) 6%,var(--ink-850));box-shadow:var(--shadow-1)}
.schiene a[aria-current=step] .nr{background:var(--grad-accent);
  color:var(--text-on-accent)}
.schiene a.erledigt .nr{background:var(--tint-neon-14);color:var(--neon)}
.schiene .nr{width:24px;height:24px;flex:none;border-radius:50%;display:grid;
  place-items:center;background:var(--ink-700);color:var(--faint);
  font:600 .74rem/1 var(--font-text)}

/* Hinweisbalken ueber einem Schirm */
.callout{display:flex;gap:var(--space-3);align-items:flex-start;
  padding:var(--space-4);border-radius:var(--radius-md);background:var(--ink-850);
  border:1px solid var(--line);color:var(--fg-soft);font-size:.9rem;line-height:1.55;
  margin:0 0 var(--space-6)}
.callout .sym{flex:none;color:var(--neon-dim)}

/* Ueberlagerung: dient als Dialog, kommt aber fertig vom Server */
.ueber{position:fixed;inset:0;z-index:100;display:grid;place-items:center;padding:24px;
  background:color-mix(in srgb, #000 62%, transparent);backdrop-filter:blur(6px)}
.ueber .tafel{width:100%;max-width:820px;max-height:88vh;overflow-y:auto;
  background:var(--grad-surface);border:1px solid var(--line-strong);
  border-radius:var(--radius-xl);box-shadow:var(--shadow-3);padding:var(--space-6)}
.ueber .tafel .kopf{display:flex;align-items:flex-start;gap:12px;margin-bottom:8px}
.ueber .tafel .kopf h2{font-size:1.3rem}
.ueber .tafel .kopf .zu{margin-left:auto;min-height:34px;padding:0 8px}

.zweispalt{display:grid;grid-template-columns:auto minmax(0,1fr);gap:24px;
  align-items:start}
.leise{color:var(--muted);font-size:.88rem;font-weight:var(--weight-body)}
.werkzeile{display:flex;align-items:center;gap:10px;flex-wrap:wrap}

@media (max-width:900px){
  .app{flex-direction:column}
  .leiste{width:auto;min-height:0;position:static;flex-direction:row;
    align-items:center;gap:14px;padding:12px 18px;border-right:none;
    border-bottom:1px solid var(--line);flex-wrap:wrap}
  .leiste .marke{padding:0}
  .leiste .marke .eyebrow{display:none}
  .leiste nav{display:flex;flex-wrap:wrap;gap:2px}
  .leiste nav a{padding:8px 10px;font-size:.88rem}
  .leiste .fuss{display:none}
  .app-kopf{padding:12px 18px}
  .app-kopf .wo{display:none}
  .app-inhalt{padding:24px 18px 64px}
  .zweispalt{grid-template-columns:1fr}
}
@media (max-width:640px){
  .otp{gap:6px}
  .otp input{min-height:48px;font-size:1.1rem}
  .leiste nav a span:not(.sym){display:none}
}
"""

PORTAL_CSS = neo_design.BASIS_CSS + ANWENDUNG_CSS


# --------------------------------------------------------------------------
# Das bisschen JavaScript, das wirklich keine Form ersetzt
# --------------------------------------------------------------------------
OTP_JS = """
(function(){
  var kasten = document.querySelector('.otp');
  if (!kasten) return;
  var felder = [].slice.call(kasten.querySelectorAll('input'));
  felder.forEach(function (feld, i) {
    feld.addEventListener('input', function () {
      feld.value = feld.value.replace(/\\D/g, '').slice(-1);
      if (feld.value && i < felder.length - 1) felder[i + 1].focus();
    });
    feld.addEventListener('keydown', function (e) {
      if (e.key === 'Backspace' && !feld.value && i > 0) felder[i - 1].focus();
      if (e.key === 'ArrowLeft' && i > 0) felder[i - 1].focus();
      if (e.key === 'ArrowRight' && i < felder.length - 1) felder[i + 1].focus();
    });
    feld.addEventListener('paste', function (e) {
      var text = (e.clipboardData || window.clipboardData).getData('text') || '';
      var ziffern = text.replace(/\\D/g, '').slice(0, felder.length);
      if (!ziffern) return;
      e.preventDefault();
      felder.forEach(function (f, k) { f.value = ziffern[k] || ''; });
      var letzte = Math.min(ziffern.length, felder.length) - 1;
      felder[letzte < 0 ? 0 : letzte].focus();
      if (ziffern.length === felder.length) feld.form.requestSubmit();
    });
  });
})();
"""


NAVIGATION_JS = """
(function () {
  var koerper = document.body;
  var an = function () { koerper.classList.add('laedt'); };
  document.addEventListener('click', function (e) {
    var verweis = e.target.closest && e.target.closest('a[href]');
    if (!verweis || e.defaultPrevented || e.button !== 0) return;
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    if (verweis.target === '_blank' || verweis.hasAttribute('download')) return;
    var ziel = verweis.getAttribute('href') || '';
    if (!ziel || ziel.charAt(0) === '#') return;
    if (/^(mailto|tel|javascript):/i.test(ziel)) return;
    if (verweis.origin && verweis.origin !== location.origin) return;
    an();
  });
  document.addEventListener('submit', an);
  // Zurueck aus dem Zwischenspeicher zeigt die alte Seite samt Balken.
  window.addEventListener('pageshow', function () {
    koerper.classList.remove('laedt');
  });
})();
"""

GRENZEN_JS = """
(function () {
  document.querySelectorAll('.kontogrenze').forEach(function (karte) {
    var schalter = karte.querySelector('.eigene-schalter');
    var felder = [].slice.call(karte.querySelectorAll('.grenzfeld input'));
    var texte = [].slice.call(karte.querySelectorAll('.grenzfeld span'));
    if (!schalter) return;
    var nachziehen = function () {
      var an = schalter.checked;
      karte.classList.toggle('akzent', an);
      felder.forEach(function (feld) { feld.disabled = !an; });
      texte.forEach(function (text) {
        text.textContent = an ? text.dataset.eigen : text.dataset.geerbt;
      });
    };
    schalter.addEventListener('change', nachziehen);
    nachziehen();
  });
})();
"""


def otp_felder(name: str = "code", falsch: bool = False) -> str:
    """Sechs Felder fuer sechs Ziffern.

    Ohne JavaScript sind es sechs gewoehnliche Eingaben, die zusammen
    abgeschickt werden; der Server setzt sie wieder zusammen. Das
    Skript oben schiebt nur den Schreibzeiger weiter.
    """
    felder = "".join(
        f'<input type="text" name="{esc(name)}" inputmode="numeric" '
        f'pattern="[0-9]*" maxlength="1" autocomplete="{"one-time-code" if i == 0 else "off"}" '
        f'aria-label="Ziffer {i + 1} von 6"{" autofocus" if i == 0 else ""}>'
        for i in range(6))
    return f'<div class="otp{" falsch" if falsch else ""}">{felder}</div>'


# --------------------------------------------------------------------------
# Bausteine
# --------------------------------------------------------------------------
def karte(titel: str = "", inhalt: str = "", *, zustand: str = "",
          aktion: str = "", art: str = "", kennung: str = "") -> str:
    """Eine Karte mit Kopf: Titel links, Zustand daneben, Handlung rechts."""
    klassen = "card" + (f" {art}" if art else "")
    marke = f' id="{esc(kennung)}"' if kennung else ""
    kopf = ""
    if titel or aktion:
        rechts = f'<div class="rechts">{aktion}</div>' if aktion else ""
        kopf = (f'<div class="card-kopf"><h2>{esc(titel)}'
                f'{" " + zustand if zustand else ""}</h2>{rechts}</div>')
    return f'<div class="{klassen}"{marke}>{kopf}{inhalt}</div>'


def zeile(label: str, wert: str, notiz: str = "", *, mono: bool = False) -> str:
    """Eine Zeile einer Angabentabelle: Beschriftung, Wert, darunter der Hinweis."""
    kl = ' class="mono"' if mono else ""
    ergaenzung = f'<span class="notiz">{esc(notiz)}</span>' if notiz else ""
    return f'<tr><th{kl}>{esc(label)}</th><td>{wert}{ergaenzung}</td></tr>'


def tabelle(zeilen: str, leer: str = "keine Einträge") -> str:
    return f"<table>{zeilen or f'<tr><td>{esc(leer)}</td></tr>'}</table>"


def zustand(text: str, art: str = "neutral") -> str:
    """Eine Zustandspille. art ist ok, warn, bad oder neutral."""
    return f'<span class="state {art}">{esc(text)}</span>'


def hinweis(text: str, icon: str = "info") -> str:
    return f'<div class="callout">{symbol(icon, 20)}<span>{text}</span></div>'


def warnung(text: str, art: str = "") -> str:
    """Ein Balken in der Farbe der Lage. art ist leer, gut oder schlecht."""
    if not text:
        return ""
    icon = {"gut": "check_circle", "schlecht": "error"}.get(art, "warning")
    klasse = f" {art}" if art else ""
    return f'<div class="warnung{klasse}">{symbol(icon, 20)}<span>{text}</span></div>'


def feld(name: str, beschriftung: str, hinweis_text: str = "", *, art: str = "text",
         wert: str = "", extra: str = "") -> str:
    zusatz = f"<span>{esc(hinweis_text)}</span>" if hinweis_text else ""
    return (f'<label>{esc(beschriftung)}{zusatz}'
            f'<input type="{art}" name="{esc(name)}" value="{esc(wert)}" {extra}></label>')


def ankreuzzeile(name: str, titel: str, notiz: str = "", *, wert: str = "1",
                 an: bool = False, gesperrt: bool = False, kennung: str = "",
                 klasse: str = "") -> str:
    haken = " checked" if an else ""
    sperre = " disabled" if gesperrt else ""
    marke = f' class="{esc(klasse)}"' if klasse else ""
    unten = f'<span class="note">{esc(notiz)}</span>' if notiz else ""
    kenn = f'<span class="mono">{esc(kennung)}</span>' if kennung else ""
    return (f'<label class="kasten"><input type="checkbox" name="{esc(name)}" '
            f'value="{esc(wert)}"{haken}{sperre}{marke}>'
            f'<span class="kasten-text"><b>{esc(titel)}</b>{kenn}{unten}</span></label>')


def kennzahl(label: str, wert: str, *, neon: bool = False, notiz: str = "",
             icon: str = "") -> str:
    bild = symbol(icon, 22) if icon else ""
    unten = (f'<span style="font-size:.82rem;color:var(--muted)">{esc(notiz)}</span>'
             if notiz else "")
    return (f'<div class="tile" style="display:grid;gap:6px;align-content:start">{bild}'
            f'<div class="kennzahl{" neon" if neon else ""}">{wert}</div>'
            f'<span class="eyebrow">{esc(label)}</span>{unten}</div>')


def schiene(schritte, jetzt: int) -> str:
    """Die vier Schritte der Einrichtung als anklickbare Leiste."""
    teile = []
    for i, (pfad, label, icon) in enumerate(schritte):
        if i == jetzt:
            marke, klasse = ' aria-current="step"', ""
        elif i < jetzt:
            marke, klasse = "", ' class="erledigt"'
        else:
            marke, klasse = "", ""
        teile.append(f'<a href="{esc(pfad)}"{marke}{klasse}>'
                     f'<span class="nr">{i + 1}</span>{symbol(icon, 18)}'
                     f'<span>{esc(label)}</span></a>')
    return f'<div class="schiene">{"".join(teile)}</div>'


# --------------------------------------------------------------------------
# Die beiden Rahmen
# --------------------------------------------------------------------------
def _kopf(titel: str, favicon: str, marke: str, skript: str = "") -> str:
    # Der Ladebalken haengt an jeder Seite, das uebrige Skript nur dort,
    # wo die Seite es braucht.
    js = f"<script>{NAVIGATION_JS}{skript}</script>"
    return (f"<!doctype html>\n"
            f'<html lang="de"><head><meta charset="utf-8">\n'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f'<meta name="color-scheme" content="dark">\n'
            f'<meta name="robots" content="noindex, nofollow">\n'
            f'<link rel="icon" href="{favicon}">\n'
            f"<title>{esc(titel)} — {esc(marke)}</title>\n"
            f"<style>{PORTAL_CSS}</style></head>\n"), js


def rahmen(*, titel: str, lead: str, weg: str, inhalt: str, benutzer: str,
           zwei_faktor: bool, logo: str, favicon: str, marke: str, beiwort: str,
           server: str = "", aktionen: str = "", ueberlagerung: str = "",
           skript: str = "") -> bytes:
    """Die Konsole: Seitenleiste, Kopfzeile, eine Spalte Inhalt."""
    kopf, js = _kopf(titel, favicon, marke, skript)
    hier = ' aria-current="page"'
    nav = "".join(
        f'<a href="{esc(pfad)}"{hier if pfad == weg else ""}>'
        f'{symbol(icon, 20)}<span>{esc(label)}</span></a>'
        for pfad, label, icon in WEGE)
    unten = ""
    if server:
        unten = (f'<div class="fuss"><span class="eyebrow">Server</span>'
                 f'<span class="wo">{esc(server)}</span>'
                 f'{zustand("MCP erreichbar", "ok")}</div>')
    schild = zustand("2FA", "ok") if zwei_faktor else zustand("ohne 2FA", "warn")
    rechts = f'<div class="rechts">{aktionen}</div>' if aktionen else ""
    # Ein leerer Vorspann hinterliess eine leere Zeile unter der Ueberschrift.
    vorspann = f'<p class="lead">{esc(lead)}</p>' if lead else ""
    return (kopf + f"""<body><div class="laeuft" aria-hidden="true"></div>
<div class="app">
<aside class="leiste">
<a class="marke" href="/dashboard">{logo}<span class="eyebrow">{esc(beiwort)}</span></a>
<nav>{nav}</nav>
{unten}
</aside>
<div class="blatt">
<header class="app-kopf">
<span class="wo">{esc(titel)}</span>
<div class="wer"><span>{esc(benutzer)}</span>{schild}
<form method="post" action="/logout">
<button class="ghost klein" type="submit">Abmelden</button></form></div>
</header>
<main class="app-inhalt">
<div class="seitenkopf"><div style="min-width:0"><h1>{esc(titel)}</h1>
{vorspann}</div>{rechts}</div>
{inhalt}
</main></div></div>{ueberlagerung}{js}</body></html>""").encode("utf-8")


def schmale_seite(*, titel: str, lead: str, inhalt: str, logo: str, favicon: str,
                  marke: str, fuss: str = "", oben: str = "",
                  skript: str = "") -> bytes:
    """Die Seiten mit genau einer Aufgabe: anmelden, bestätigen, Kennwort setzen.

    Keine Navigationsleiste: sie böte Wege an, die alle sofort hierher
    zurückführen — auf der erzwungenen Kennwortseite tat sie genau das.
    """
    kopf, js = _kopf(titel, favicon, marke, skript)
    unten = f'<div class="fuss">{fuss}</div>' if fuss else ""
    return (kopf + f"""<body><div class="laeuft" aria-hidden="true"></div>
<main class="schmal">
<div class="marke">{logo}</div>
<div class="titel"><h1>{esc(titel)}</h1><p class="lead">{esc(lead)}</p></div>
{oben}{inhalt}{unten}
</main>{js}</body></html>""").encode("utf-8")
