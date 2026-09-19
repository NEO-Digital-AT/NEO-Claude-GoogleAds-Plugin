#!/usr/bin/env python3
"""Die öffentliche Startseite, gebaut nach dem NEO-Designsystem.

Diese Seite hat zwei Auftraggeber. Der eine ist Googles Prüfung des
Brandings, die eine Startseite ohne Anmeldung verlangt, auf der der
Anwendungsname im Wortlaut des Zustimmungsbildschirms steht und erklärt
wird, wozu die Anwendung dient. Der andere ist der Betreiber, der sie
Kunden zeigt.

Aufbau und Texte stammen aus dem Designsystem (ui_kits/public/Seite.jsx),
die Farben, Maße und Bausteine aus dessen Tokens und base-Dateien. Das
Portal dahinter behält vorerst sein eigenes Aussehen; hier steht nur die
öffentliche Seite.

DREI STELLEN WEICHEN AB, jede aus einem Grund:

    Symbole     Das Designsystem lädt Material Symbols von Googles
                Schriftdienst nach. Diese Seite lädt nichts von fremden
                Rechnern: sie soll auch dann stehen, wenn ein Besucher
                Google blockiert, und eine Seite, die gerade wegen
                Datenschutz geprüft wird, sollte den Besuch nicht an
                einen Dritten melden. Die Symbole liegen deshalb als
                SVG im Quelltext, im selben 24er-Raster.
    Passkey     Der Entwurf nannte „Kennwort, zweiten Faktor und
                Passkey". Passkeys gibt es in dieser Anwendung nicht.
                Eine Sicherheitsaussage, die nicht stimmt, gehört auf
                keine Seite, erst recht nicht auf eine geprüfte.
    Scope       Der Entwurf kürzt die Berechtigung zu „…/auth/adwords".
                Hier steht sie vollständig: auf einer Seite, die Auskunft
                über Daten gibt, ist die ganze Angabe das Mindeste.

Kein Aufbauschritt, keine Fremdbibliothek, kein JavaScript.
"""
from __future__ import annotations

import html

import google_ads_client as gac

# --------------------------------------------------------------------------
# Stammdaten des Betreibers, wie im Designsystem hinterlegt
# --------------------------------------------------------------------------
# Firma und E-Mail stehen so schon in der Konfiguration; was dort gesetzt
# ist, gilt auch hier — sonst nennt der Seitentitel einen Betreiber und die
# Tabelle darunter einen anderen. Fuer Anschrift, Telefon und UID gibt es
# keine Schalter, die stehen fest.
FIRMA = gac.PORTAL_OPERATOR
INHABER = "Einzelunternehmen · Inhaber Erich Nigg"
ANSCHRIFT = "Nordweg 14, 8010 Graz, Österreich"
TELEFON_TEXT = "0316 231620"
TELEFON_WAHL = "+43316231620"
EMAIL = gac.PORTAL_CONTACT or "hallo@neo-digital.at"
UID = "ATU57275308"
NEO = "https://neo-digital.at"


def beiwort() -> str:
    """Was neben der Wortmarke steht: der Name ohne das, was das Logo schon sagt."""
    name = gac.PORTAL_NAME
    return name[4:].strip() if name.upper().startswith("NEO ") else name


def esc(wert) -> str:
    return html.escape(str(wert), quote=True)


# --------------------------------------------------------------------------
# Symbole. Ein 24er-Raster, Strich 1.8, rund abgeschlossen — passend zu den
# Material Symbols des Entwurfs, aber im eigenen Quelltext.
# --------------------------------------------------------------------------
_PFADE = {
    "login": "M14 4h5a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1h-5M10 8l4 4-4 4M14 12H3",
    "science": "M9 3h6M10 3v6.2L5.2 18A2 2 0 0 0 7 21h10a2 2 0 0 0 1.8-2.9L14 9.2V3"
               "M7.8 14h8.4",
    "location_on": "M12 21s7-5.6 7-11a7 7 0 1 0-14 0c0 5.4 7 11 7 11z M12 10.5v.01",
    "handyman": "M14.5 6.5a3.5 3.5 0 0 0 4.6 4.6L21 13l-8 8-2-2 8-8-1.9-1.9a3.5 3.5 0"
                " 0 0-4.6-4.6L14.5 6.5z M7 3l4 4-4 4-4-4z",
    "bolt": "M13 2 4 14h6l-1 8 9-12h-6l1-8z",
    "verified": "M12 2.5l2.4 2.1 3.2-.3.6 3.1 2.6 1.9-1.5 2.8 1.5 2.8-2.6 1.9-.6 3.1"
                "-3.2-.3L12 21.5l-2.4-2.1-3.2.3-.6-3.1L3.2 14.7l1.5-2.8-1.5-2.8 2.6-1.9"
                ".6-3.1 3.2.3L12 2.5z M8.6 12.2l2.3 2.3 4.5-4.6",
    "shield_lock": "M12 2.8l7 2.6v5.4c0 4.6-2.9 8.6-7 10.4-4.1-1.8-7-5.8-7-10.4V5.4l7-2.6z"
                   " M12 10v-.8a1.6 1.6 0 1 1 3.2 0v.8 M10.4 10h6.4v4.4h-6.4z",
    "query_stats": "M3 20V9 M8.5 20v-6 M14 20v-9 M19.5 20v-4 M3.5 11.5 8.5 7l4.5 3.5L20 4",
    "travel_explore": "M12 21a9 9 0 1 1 6.2-15.5 M3.2 9.8h17.6 M3.2 14.2h9"
                      " M12 3a14 14 0 0 0 0 18 M12 3a14 14 0 0 1 3.6 7"
                      " M17.3 17.3a3.2 3.2 0 1 0 4.5 4.5 3.2 3.2 0 0 0-4.5-4.5z",
    "payments": "M3 7.5h14a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2z"
                " M10 15.5a2.5 2.5 0 1 1 0-5 2.5 2.5 0 0 1 0 5z M5 4.5h16a2 2 0 0 1 2 2v9",
    "account_tree": "M4 3.5h5v4H4z M15 10.5h5v4h-5z M15 17.5h5v4h-5z"
                    " M6.5 7.5v10.5h6 M6.5 12.5h6",
    "description": "M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5z"
                   " M14 3v5h5 M9 13h6 M9 17h6",
    "link": "M10.5 13.5a4 4 0 0 0 5.7 0l2.6-2.6a4 4 0 1 0-5.7-5.7L11.6 6.7"
            " M13.5 10.5a4 4 0 0 0-5.7 0l-2.6 2.6a4 4 0 1 0 5.7 5.7l1.5-1.5",
    "forum": "M7 3h11a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2h-1v4l-4-4H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"
             " M5 17H4a2 2 0 0 1-2-2V8",
    "check_circle": "M12 21a9 9 0 1 1 0-18 9 9 0 0 1 0 18z M8 12.2l2.7 2.7L16 9.6",
    "speed": "M12 20a8 8 0 1 1 8-8 M12 12l4.5-4.5 M4.2 12H2 M22 12h-2.2 M12 4.2V2",
    "key": "M15.5 3a5.5 5.5 0 1 0-4.1 9.2L3 20.6V22h4v-2h2v-2h2l2.4-2.4A5.5 5.5 0 0 0 15.5 3z"
           " M16.8 7.2v.01",
}


def symbol(name: str, groesse: int = 24, farbe: str = "currentColor") -> str:
    """Ein Symbol als SVG. Unbekannte Namen ergeben nichts, nicht ihren Text."""
    pfad = _PFADE.get(name)
    if not pfad:
        return ""
    return (f'<svg class="sym" width="{groesse}" height="{groesse}" viewBox="0 0 24 24" '
            f'fill="none" stroke="{farbe}" stroke-width="1.8" stroke-linecap="round" '
            f'stroke-linejoin="round" aria-hidden="true" focusable="false">'
            f'<path d="{pfad}"/></svg>')


# --------------------------------------------------------------------------
# Das Aussehen: Tokens und Bausteine aus dem Designsystem
# --------------------------------------------------------------------------
DESIGN_CSS = """
:root{
  --ink-950:#060806; --ink-900:#0B0F0B; --ink-850:#0E130E; --ink-800:#12180F;
  --ink-750:#161D15; --ink-700:#1C241B;
  --line:#232C22; --line-soft:#1A211A; --line-strong:#33402F;
  --fg:#EAF0E9; --fg-soft:#C7D0C6; --muted:#A3ADA3; --faint:#778276;
  --neon:#a8f20d; --neon-up:#bcff33; --neon-dim:#7fb80a; --neon-deep:#3F5A08;
  --violett:#2a025f; --text-on-accent:#07120A;
  --warn:#FFB454; --bad:#FF6B5C;
  --tint-neon-08:color-mix(in srgb, var(--neon) 8%, transparent);
  --tint-neon-14:color-mix(in srgb, var(--neon) 14%, transparent);
  --grad-surface:linear-gradient(180deg,#151C14 0%,#11170F 100%);
  --grad-accent:linear-gradient(180deg,#bcff33 0%,#a8f20d 100%);
  --grad-hairline:linear-gradient(90deg,transparent,color-mix(in srgb,var(--neon) 35%,transparent),transparent);
  --page-glow:radial-gradient(120% 70% at 50% -10%, color-mix(in srgb,var(--neon) 7%,transparent) 0%, transparent 60%);

  --font-text:"Segoe UI Variable Text","Segoe UI",system-ui,-apple-system,"SF Pro Text",Roboto,"Helvetica Neue",Arial,sans-serif;
  --font-display:"Segoe UI Variable Display","Segoe UI",system-ui,-apple-system,"SF Pro Display",sans-serif;
  --font-mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace;
  --text-base:16px; --leading-base:1.62; --leading-heading:1.22; --leading-note:1.55;
  --size-display-xl:clamp(2.6rem, 1.6rem + 3.4vw, 4.4rem);
  --size-display:clamp(2rem, 1.4rem + 2vw, 3rem);
  --size-h2:1.18rem; --size-h3:1rem; --size-lead:1.06rem; --size-note:.875rem; --size-table:.94rem;
  --size-th:.72rem; --size-state:.78rem; --size-mono:.89em; --size-eyebrow:.74rem;
  --weight-body:400; --weight-medium:500; --weight-strong:600; --weight-display:680;
  --weight-h2:620; --weight-button:600;
  --tracking-display:-.03em; --tracking-h1:-.022em; --tracking-h2:-.012em;
  --tracking-eyebrow:.14em; --tracking-th:.08em;

  --space-1:4px; --space-2:8px; --space-3:12px; --space-4:16px; --space-5:20px;
  --space-6:24px; --space-7:32px; --space-8:40px; --space-9:56px;
  --radius-sm:8px; --radius-md:10px; --radius-lg:14px; --radius-xl:20px; --radius-pill:999px;
  --control-height:44px; --control-height-sm:34px;
  --measure-prose:62ch; --measure-site:1160px;

  --shadow-1:0 1px 2px rgba(0,0,0,.45), inset 0 1px 0 rgba(255,255,255,.035);
  --shadow-2:0 8px 24px -12px rgba(0,0,0,.75), inset 0 1px 0 rgba(255,255,255,.045);
  --shadow-3:0 24px 60px -24px rgba(0,0,0,.85), inset 0 1px 0 rgba(255,255,255,.05);
  --shadow-inset:inset 0 1px 2px rgba(0,0,0,.5);
  --glow-accent:0 0 0 1px color-mix(in srgb,var(--neon) 40%,transparent), 0 8px 28px -10px color-mix(in srgb,var(--neon) 45%,transparent);
  --glow-soft:0 0 0 1px color-mix(in srgb,var(--neon) 30%,transparent), 0 8px 26px -12px color-mix(in srgb,var(--neon) 45%,transparent);
  --glow-logo:drop-shadow(0 0 20px color-mix(in srgb,var(--neon) 30%,transparent));
  --dur-1:120ms; --dur-2:180ms; --ease-out:cubic-bezier(.2,.7,.3,1);
  --transition-control:background var(--dur-1) var(--ease-out), border-color var(--dur-1) var(--ease-out), color var(--dur-1) var(--ease-out), box-shadow var(--dur-2) var(--ease-out);
}
@media (prefers-reduced-motion: reduce){ :root{ --dur-1:0ms; --dur-2:0ms; --transition-control:none; } }

*{box-sizing:border-box}
html{color-scheme:dark;-webkit-text-size-adjust:100%;scroll-behavior:smooth;
  overflow-x:clip}
body{margin:0;background:var(--ink-900);background-image:var(--page-glow);
  background-repeat:no-repeat;color:var(--fg);
  font:var(--text-base)/var(--leading-base) var(--font-text);
  font-synthesis-weight:none;-webkit-font-smoothing:antialiased;
  -moz-osx-font-smoothing:grayscale;text-wrap:pretty}
img,svg{max-width:100%}
::selection{background:color-mix(in srgb,var(--neon) 30%,transparent)}

h1,h2,h3{font-family:var(--font-display);text-wrap:balance;margin:0}
h2{font-size:var(--size-h2);font-weight:var(--weight-h2);line-height:1.3;letter-spacing:var(--tracking-h2)}
h3{font-size:var(--size-h3);font-weight:var(--weight-strong);line-height:1.4}
p{margin:0 0 1em} p:last-child{margin-bottom:0}
p.lead{color:var(--muted);font-size:var(--size-lead);max-width:var(--measure-prose);margin:var(--space-3) 0 0}
a{color:var(--neon);text-decoration-color:color-mix(in srgb,var(--neon) 45%,transparent);
  text-underline-offset:.22em;transition:color var(--dur-1) var(--ease-out)}
a:hover{color:var(--neon-up);text-decoration-color:currentColor}
table{width:100%;border-collapse:collapse;font-size:var(--size-table);font-variant-numeric:tabular-nums}
th,td{text-align:left;padding:var(--space-3) var(--space-4);vertical-align:top;
  border-bottom:1px solid var(--line-soft)}
th{font-weight:var(--weight-strong);color:var(--faint);font-size:var(--size-th);
  text-transform:uppercase;letter-spacing:var(--tracking-th);white-space:nowrap;
  width:1%;padding-right:var(--space-6)}
tr:last-child th,tr:last-child td{border-bottom:none}
code,.mono{font-family:var(--font-mono);font-size:var(--size-mono);color:var(--neon);
  font-variant-ligatures:none;overflow-wrap:anywhere}

.button{display:inline-flex;align-items:center;justify-content:center;gap:var(--space-2);
  min-height:var(--control-height);padding:0 var(--space-5);border-radius:var(--radius-md);
  border:1px solid transparent;background:var(--grad-accent);color:var(--text-on-accent);
  font:inherit;font-weight:var(--weight-button);font-size:.94rem;letter-spacing:-.005em;
  cursor:pointer;text-decoration:none;white-space:nowrap;box-shadow:var(--shadow-1);
  transition:var(--transition-control)}
a.button,a.button:visited{color:var(--text-on-accent);text-decoration:none}
a.button:hover{background:var(--neon-up);color:var(--text-on-accent);box-shadow:var(--glow-accent)}
a.button:focus-visible{outline:2px solid var(--neon-up);outline-offset:2px}
.button.quiet,a.button.quiet{background:var(--ink-750);color:var(--fg);border-color:var(--line-strong)}
a.button.quiet:hover{background:var(--ink-700);border-color:var(--neon);color:var(--fg);box-shadow:var(--glow-soft)}
.button.klein{min-height:var(--control-height-sm);padding:0 var(--space-4);font-size:.86rem}

.card{position:relative;background:var(--grad-surface);border:1px solid var(--line);
  border-radius:var(--radius-lg);padding:var(--space-6);box-shadow:var(--shadow-2)}
.card.flach{box-shadow:var(--shadow-1);background:var(--ink-800)}
.card > h2:first-child{margin-bottom:var(--space-4)}
.card-kopf{display:flex;align-items:center;gap:var(--space-3);margin-bottom:var(--space-4)}
.card-kopf h2{margin:0}
.tile{background:var(--ink-800);border:1px solid var(--line);border-radius:var(--radius-md);
  padding:var(--space-4)}
.eyebrow{display:block;font-size:var(--size-eyebrow);letter-spacing:var(--tracking-eyebrow);
  text-transform:uppercase;color:var(--faint);font-weight:var(--weight-strong)}
.eyebrow.neon{color:var(--neon-dim)}
.note{color:var(--muted);font-size:var(--size-note);line-height:var(--leading-note);
  margin:var(--space-3) 0 0;max-width:var(--measure-prose)}
.row{display:flex;gap:var(--space-3);flex-wrap:wrap;align-items:center}
.row.eng{gap:var(--space-2)}
.state{display:inline-flex;align-items:center;gap:6px;white-space:nowrap;
  padding:3px 10px 3px 8px;border-radius:var(--radius-pill);font-size:var(--size-state);
  font-weight:var(--weight-strong);line-height:1.5;vertical-align:middle;
  font-family:var(--font-text);border:1px solid transparent}
.state::before{content:"";width:6px;height:6px;border-radius:50%;background:currentColor;
  flex:none;box-shadow:0 0 8px currentColor}
.state.neutral{background:var(--ink-700);color:var(--muted);border-color:var(--line)}
.grid-2{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:var(--space-4)}
.grid-3{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:var(--space-4)}
.grid-2.gleich,.grid-3.gleich{grid-auto-rows:1fr}
.grid-2.gleich > *,.grid-3.gleich > *{height:100%}
.kennzahl{font-family:var(--font-display);font-size:1.7rem;font-weight:var(--weight-display);
  letter-spacing:var(--tracking-h1);line-height:1.1}
.kennzahl.neon{color:var(--neon)}
nav.nav{display:flex;align-items:center;gap:var(--space-1);flex-wrap:wrap}
nav.nav a{display:inline-flex;align-items:center;padding:8px 14px;border-radius:var(--radius-pill);
  color:var(--muted);text-decoration:none;font-size:.92rem;font-weight:var(--weight-medium);
  transition:var(--transition-control)}
nav.nav a:hover{color:var(--fg);background:var(--ink-750)}

/* Seitenspezifisch */
.kopf{position:sticky;top:0;z-index:10;border-bottom:1px solid var(--line);
  background:color-mix(in srgb, var(--ink-900) 82%, transparent);backdrop-filter:blur(12px)}
.kopf .innen{max-width:var(--measure-site);margin:0 auto;padding:14px 28px;
  display:flex;align-items:center;gap:20px}
.kopf .marke{display:inline-flex;height:24px}
.kopf .marke svg{height:24px;width:auto;color:var(--neon);filter:var(--glow-logo)}
.kopf .wo{border-left:1px solid var(--line);padding-left:20px;white-space:nowrap}
.kopf nav.nav{margin-left:auto}
.spalte{max-width:var(--measure-site);margin:0 auto;padding:0 28px}
.hero{padding:88px 0 68px;display:grid;
  grid-template-columns:minmax(0,1.05fr) minmax(0,.95fr);gap:56px;align-items:center}
.hero h1{font-size:var(--size-display-xl);font-weight:var(--weight-display);
  letter-spacing:var(--tracking-display);line-height:1.06;margin:18px 0 0;max-width:15ch}
.hero .lead{font-size:1.14rem;margin-top:22px}
.hero .knoepfe{margin-top:30px}
.hero .merkmale{margin-top:26px;gap:20px;color:var(--muted);font-size:.86rem}
.bildrahmen{position:relative}
.bildrahmen .schein{position:absolute;inset:-12% -8%;pointer-events:none;filter:blur(8px);
  background:radial-gradient(60% 60% at 60% 35%, color-mix(in srgb,var(--neon) 16%,transparent), transparent 70%)}
.bildrahmen .tafel{position:relative;border-radius:var(--radius-xl);border:1px solid var(--line);
  background:var(--grad-surface);box-shadow:var(--shadow-3);padding:14px}
.bildrahmen svg.bild{display:block;width:100%;height:auto;border-radius:12px}
section.block{padding:80px 0;border-top:1px solid var(--line-soft)}
section.block > h2{font-size:var(--size-display);font-weight:var(--weight-display);
  letter-spacing:var(--tracking-display);line-height:1.15;margin:14px 0 0;max-width:24ch}
section.block .inhalt{margin-top:36px}
.kachel{display:grid;gap:12px;align-content:start}
.kachel .sym{color:var(--neon)}
.schrittkopf{display:flex;align-items:center;gap:10px}
.schrittnr{width:26px;height:26px;border-radius:50%;display:grid;place-items:center;
  background:var(--tint-neon-14);color:var(--neon);font:600 .78rem/1 var(--font-text)}
.schrittkopf .sym{color:var(--muted)}
.tile .sym{color:var(--muted)}
.kennzahlen{padding-bottom:8px}
footer.fuss{border-top:1px solid var(--line);background:var(--ink-950);margin-top:40px}
footer.fuss .innen{max-width:var(--measure-site);margin:0 auto;padding:40px 28px;
  display:flex;gap:28px;flex-wrap:wrap;align-items:center}
footer.fuss svg{height:20px;width:auto;color:var(--neon);opacity:.85}
footer.fuss .zeile{color:var(--faint);font-size:.84rem}
footer.fuss .links{margin-left:auto;gap:22px;font-size:.86rem}
.tabellennotiz{display:block;color:var(--muted);font-size:var(--size-note);margin-top:2px}

@media (max-width:900px){
  .hero{grid-template-columns:1fr;gap:36px;padding:56px 0 48px}
  .kopf nav.nav{display:none}
  section.block{padding:56px 0}
}
@media (max-width:640px){
  .spalte,.kopf .innen,footer.fuss .innen{padding-left:18px;padding-right:18px}
  .card{padding:var(--space-5)}
  .kopf .wo{display:none}
  footer.fuss .links{margin-left:0}
}
"""


# --------------------------------------------------------------------------
# Bausteine
# --------------------------------------------------------------------------
def _kachel(icon: str, titel: str, text: str) -> str:
    return (f'<div class="card kachel">{symbol(icon, 26)}'
            f'<h3>{esc(titel)}</h3>'
            f'<p class="note" style="margin:0">{esc(text)}</p></div>')


def _schritt(nr: str, icon: str, titel: str, text: str) -> str:
    return (f'<div class="card kachel">'
            f'<div class="schrittkopf"><span class="schrittnr">{esc(nr)}</span>'
            f'{symbol(icon, 22)}</div>'
            f'<h3>{esc(titel)}</h3>'
            f'<p class="note" style="margin:0">{esc(text)}</p></div>')


def _kennzahl(wert: str, label: str, icon: str, notiz: str, neon: bool = False) -> str:
    return (f'<div class="tile" style="display:grid;gap:6px">{symbol(icon, 22)}'
            f'<div class="kennzahl{" neon" if neon else ""}">{esc(wert)}</div>'
            f'<span class="eyebrow">{esc(label)}</span>'
            f'<span style="font-size:.82rem;color:var(--muted)">{esc(notiz)}</span></div>')


def _url_umbruch(url: str) -> str:
    """Eine URL mit Bruchstellen an den Schraegstrichen.

    Ohne sie bricht der lange Berechtigungsname mitten im Wort um — die
    Grundregel overflow-wrap:anywhere erlaubt das, weil sonst die Tabelle
    aufreisst. <wbr> bietet die besseren Stellen an und steht selbst in
    keinem Text: wer die Zeile kopiert, bekommt die URL am Stueck.
    """
    kopf, trenner, rest = esc(url).partition("://")
    if not trenner:
        return kopf
    return kopf + trenner + "<wbr>/".join(rest.split("/"))


def _zeile(label: str, wert: str, notiz: str = "") -> str:
    ergaenzung = f'<span class="tabellennotiz">{esc(notiz)}</span>' if notiz else ""
    return f'<tr><th>{esc(label)}</th><td>{wert}{ergaenzung}</td></tr>'


def _block(kennung: str, eyebrow: str, titel: str, inhalt: str, lead: str = "") -> str:
    lead_html = f'<p class="lead" style="margin-top:14px">{esc(lead)}</p>' if lead else ""
    return (f'<section class="block" id="{kennung}">'
            f'<span class="eyebrow neon">{esc(eyebrow)}</span>'
            f'<h2>{esc(titel)}</h2>{lead_html}'
            f'<div class="inhalt">{inhalt}</div></section>')


# --------------------------------------------------------------------------
# Das Hero-Bild. Gezeichnet, nicht fotografiert: dieselbe Machart wie die
# Beitragsbilder auf neo-digital.at/blog — dunkler Grund, das Neongruen als
# einziger Akzent, das Violett nur als Schein in der Ecke, flache Formen
# ohne Verlaufsspielerei. Es zeigt den Ablauf, um den es auf der Seite
# geht: ein Konto wird gelesen, ein Fund markiert, die Antwort kommt als
# Text, und geschrieben wird erst nach dem Trockenlauf und einem Ja.
#
# Als SVG im Quelltext, aus demselben Grund wie die Symbole: die Seite
# laedt nichts nach. Ein Bild, das mitgeliefert wird, kann auch nicht
# fehlen.
# --------------------------------------------------------------------------
HERO_SVG = """<svg class="bild" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 520"
     role="img" aria-label="Ein Konto wird gelesen, ausgewertet und nach Freigabe geändert">
<defs>
  <radialGradient id="hb-violett" cx="18%" cy="8%" r="78%">
    <stop offset="0%" stop-color="#43159A" stop-opacity=".62"/>
    <stop offset="55%" stop-color="#2a025f" stop-opacity=".26"/>
    <stop offset="100%" stop-color="#2a025f" stop-opacity="0"/>
  </radialGradient>
  <radialGradient id="hb-schein" cx="80%" cy="70%" r="48%">
    <stop offset="0%" stop-color="#a8f20d" stop-opacity=".13"/>
    <stop offset="100%" stop-color="#a8f20d" stop-opacity="0"/>
  </radialGradient>
  <linearGradient id="hb-balken" x1="0" y1="1" x2="0" y2="0">
    <stop offset="0%" stop-color="#3F5A08"/>
    <stop offset="100%" stop-color="#a8f20d"/>
  </linearGradient>
  <linearGradient id="hb-kante" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0%" stop-color="#a8f20d" stop-opacity="0"/>
    <stop offset="50%" stop-color="#a8f20d" stop-opacity=".55"/>
    <stop offset="100%" stop-color="#a8f20d" stop-opacity="0"/>
  </linearGradient>
  <pattern id="hb-raster" width="22" height="22" patternUnits="userSpaceOnUse">
    <circle cx="1.6" cy="1.6" r="1.1" fill="#EAF0E9" fill-opacity=".055"/>
  </pattern>
  <filter id="hb-weich" x="-30%" y="-30%" width="160%" height="160%">
    <feGaussianBlur stdDeviation="11"/>
  </filter>
</defs>

<rect width="800" height="520" fill="#0B0F0B"/>
<rect width="800" height="520" fill="url(#hb-raster)"/>
<rect width="800" height="520" fill="url(#hb-violett)"/>
<rect width="800" height="520" fill="url(#hb-schein)"/>

<!-- Die Diagonale der Wortmarke, als ruhige Fuehrungslinie -->
<path d="M-40 470 L300 170 L300 250 L40 480 Z" fill="#a8f20d" fill-opacity=".05"/>

<!-- Konto-Fenster: was gelesen wird -->
<g transform="translate(64 96)">
  <rect width="352" height="252" rx="18" fill="#12180F" stroke="#232C22"/>
  <rect x="1" y="1" width="350" height="1" rx=".5" fill="#EAF0E9" fill-opacity=".05"/>
  <circle cx="26" cy="28" r="4.5" fill="#33402F"/>
  <circle cx="42" cy="28" r="4.5" fill="#33402F"/>
  <circle cx="58" cy="28" r="4.5" fill="#33402F"/>
  <rect x="86" y="23" width="118" height="10" rx="5" fill="#1C241B"/>

  <!-- Balken: Ausgaben je Kampagne, einer sticht heraus -->
  <g transform="translate(28 74)">
    <rect x="0"   y="86" width="26" height="60"  rx="5" fill="url(#hb-balken)" fill-opacity=".55"/>
    <rect x="42"  y="54" width="26" height="92"  rx="5" fill="url(#hb-balken)" fill-opacity=".55"/>
    <rect x="84"  y="104" width="26" height="42" rx="5" fill="url(#hb-balken)" fill-opacity=".55"/>
    <rect x="126" y="18" width="26" height="128" rx="5" fill="url(#hb-balken)"/>
    <rect x="126" y="18" width="26" height="128" rx="5" fill="none" stroke="#bcff33" stroke-opacity=".7"/>
    <rect x="168" y="70" width="26" height="76"  rx="5" fill="url(#hb-balken)" fill-opacity=".55"/>
    <rect x="210" y="96" width="26" height="50"  rx="5" fill="url(#hb-balken)" fill-opacity=".55"/>
    <rect x="252" y="62" width="26" height="84"  rx="5" fill="url(#hb-balken)" fill-opacity=".55"/>
    <line x1="-6" y1="152" x2="290" y2="152" stroke="#232C22"/>
  </g>

  <!-- Der Fund, markiert -->
  <g transform="translate(140 60)">
    <rect x="0" y="0" width="128" height="30" rx="8" fill="#0E130E" stroke="#a8f20d" stroke-opacity=".45"/>
    <circle cx="17" cy="15" r="4" fill="#a8f20d"/>
    <rect x="30" y="10" width="84" height="9" rx="4.5" fill="#a8f20d" fill-opacity=".38"/>
  </g>
</g>

<!-- Gespraech: die KI antwortet und fragt nach Freigabe -->
<g transform="translate(436 150)">
  <rect width="300" height="88" rx="16" fill="#12180F" stroke="#232C22"/>
  <rect x="1" y="1" width="298" height="1" rx=".5" fill="#EAF0E9" fill-opacity=".05"/>
  <rect x="22" y="24" width="210" height="9" rx="4.5" fill="#C7D0C6" fill-opacity=".34"/>
  <rect x="22" y="44" width="256" height="9" rx="4.5" fill="#C7D0C6" fill-opacity=".22"/>
  <rect x="22" y="64" width="134" height="9" rx="4.5" fill="#C7D0C6" fill-opacity=".22"/>
  <path d="M34 88 L34 104 L52 88 Z" fill="#12180F" stroke="#232C22"/>
</g>

<g transform="translate(436 268)">
  <rect width="300" height="112" rx="16" fill="#151C14" stroke="#33402F"/>
  <rect x="1" y="1" width="298" height="1" rx=".5" fill="#EAF0E9" fill-opacity=".06"/>
  <text x="22" y="34" font-family="ui-monospace,Menlo,monospace" font-size="13"
        fill="#778276" letter-spacing=".08em">TROCKENLAUF</text>
  <rect x="22" y="48" width="180" height="9" rx="4.5" fill="#C7D0C6" fill-opacity=".26"/>

  <!-- Freigabeknopf -->
  <rect x="22" y="70" width="128" height="30" rx="9" fill="#a8f20d"/>
  <path d="M40 85 l6 6 l12 -13" fill="none" stroke="#07120A" stroke-width="2.6"
        stroke-linecap="round" stroke-linejoin="round"/>
  <rect x="66" y="80" width="68" height="10" rx="5" fill="#07120A" fill-opacity=".72"/>
  <rect x="162" y="70" width="80" height="30" rx="9" fill="none" stroke="#33402F"/>
</g>

<!-- Verbindungsbogen vom Konto zum Gespraech -->
<path d="M420 214 C 448 214, 448 194, 470 194" fill="none" stroke="#a8f20d"
      stroke-opacity=".5" stroke-width="1.6" stroke-dasharray="5 6"/>
<circle cx="470" cy="194" r="3.2" fill="#a8f20d"/>

<!-- Weicher Markenschein unter dem Freigabeknopf -->
<ellipse cx="522" cy="356" rx="96" ry="26" fill="#a8f20d" fill-opacity=".14" filter="url(#hb-weich)"/>

<rect x="64" y="424" width="672" height="1.5" fill="url(#hb-kante)"/>
</svg>"""


# --------------------------------------------------------------------------
# Die Abschnitte
# --------------------------------------------------------------------------
def _kopfleiste(anmelden_url: str, logo: str) -> str:
    punkte = (("#koennen", "Was es kann"), ("#ablauf", "Ablauf"),
              ("#sicherheit", "Sicherheit"), ("#transparenz", "Transparenz"))
    nav = "".join(f'<a href="{p}">{esc(t)}</a>' for p, t in punkte)
    return (f'<header class="kopf"><div class="innen">'
            f'<a class="marke" href="{esc(NEO)}" target="_blank" rel="noopener"'
            f' aria-label="{esc(FIRMA)}">{logo}</a>'
            f'<span class="eyebrow wo">{esc(beiwort())}</span>'
            f'<nav class="nav">{nav}</nav>'
            f'<a class="button klein" href="{esc(anmelden_url)}">Anmelden</a>'
            f'</div></header>')


def _hero(anmelden_url: str) -> str:
    return (
        '<section class="hero">'
        '<div>'
        '<span class="eyebrow neon">Google Ads × Künstliche Intelligenz</span>'
        '<h1>Google Ads steuern — <span style="color:var(--neon)">im Gespräch</span>.</h1>'
        f'<p class="lead">{esc(gac.PORTAL_NAME)} verbindet Google Ads mit Claude. '
        'Die KI liest ganze Konten, findet Streuverluste, erklärt Zahlen im Klartext '
        'und setzt Änderungen um — Keywords, Budgets, Gebote, Kampagnenstruktur. '
        'Jede einzelne erst nach ausdrücklicher Freigabe.</p>'
        f'<div class="row knoepfe">'
        f'<a class="button" href="{esc(anmelden_url)}">{symbol("login", 20)}'
        f'Zur Verwaltung anmelden</a>'
        f'<a class="button quiet" href="#koennen">Was es kann</a></div>'
        f'<div class="row merkmale">'
        f'<span class="row eng">{symbol("science", 18)}'
        f'Trockenlauf vor jedem Schreiben</span>'
        f'<span class="row eng">{symbol("location_on", 18)}'
        f'Daten bleiben auf dem Server</span></div>'
        '</div>'
        '<div class="bildrahmen"><div class="schein"></div>'
        f'<div class="tafel">{HERO_SVG}</div></div>'
        '</section>')


def _kennzahlen() -> str:
    return ('<div class="grid-3 gleich kennzahlen">'
            + _kennzahl("13", "Werkzeuge", "handyman",
                        "Analyse, Keywords, Budgets, Berichte", neon=True)
            + _kennzahl("Sekunden", "statt Tabellen-Abende", "bolt",
                        "ganze Konten auf einmal gelesen")
            + _kennzahl("Jede Änderung", "einzeln freigegeben", "verified",
                        "Trockenlauf gegen Googles Regelprüfung")
            + _kennzahl("100 %", "EU-Hosting", "shield_lock",
                        "ein Server, keine Weitergabe")
            + '</div>')


def _koennen() -> str:
    kacheln = (
        ("query_stats", "Konto verstehen",
         "Kampagnen, Anzeigengruppen, Keywords, Suchbegriffe, Budgets und "
         "Kennzahlen werden gelesen und in Zusammenhang gebracht. Fragen wie "
         "„Wo verbrenne ich Geld?“ bekommen eine belegte Antwort."),
        ("travel_explore", "Suchbegriffe ausmisten",
         "Welche Suchanfragen wirklich Geld kosten, welche konvertieren, welche "
         "als ausschließendes Keyword gehören — gefunden und als fertige Liste "
         "vorgeschlagen."),
        ("payments", "Budgets und Gebote",
         "Verteilung über Kampagnen prüfen, Ausreißer erkennen, Tagesbudgets und "
         "Gebote anpassen — innerhalb der gesetzten Ober- und Sprunggrenzen."),
        ("account_tree", "Struktur aufräumen",
         "Kampagnen und Anzeigengruppen pausieren, aktivieren, umbenennen, "
         "Keywords pflegen — auch in größeren Stapeln, begrenzt auf die erlaubten "
         "Konten."),
        ("description", "Berichte im Klartext",
         "Monatsbericht, Vorher-Nachher, Vergleich zweier Zeiträume — als Text, "
         "den ein Kunde ohne Ads-Wissen versteht, nicht als Zahlenfriedhof."),
        ("science", "Erst proben, dann handeln",
         "Jeder schreibende Aufruf läuft zuerst als Trockenlauf gegen Googles "
         "eigene Regelprüfung. Scharf wird er nur mit ausdrücklicher Freigabe im "
         "Gespräch."),
    )
    inhalt = ('<div class="grid-2 gleich">'
              + "".join(_kachel(*k) for k in kacheln) + "</div>")
    return _block(
        "koennen", "Was es kann", "Ein Analyst, der das ganze Konto im Kopf hat.",
        inhalt,
        lead="Die KI arbeitet direkt auf den Live-Daten des Kontos — nicht auf "
             "einem Export von letzter Woche. Sie beantwortet Fragen in ganzen "
             "Sätzen, begründet jede Empfehlung mit Zahlen und kann sie auf "
             "Wunsch gleich umsetzen.")


def _ablauf() -> str:
    schritte = (
        ("1", "link", "Konto verbinden",
         "Einmal mit dem Google-Konto anmelden, das die Ads-Konten ohnehin sieht. "
         "Die Anwendung kann keine Berechtigung erteilen, die nicht bereits in "
         "Google Ads besteht."),
        ("2", "forum", "Fragen stellen",
         "In Claude nachfragen: Analyse, Vorschlag, Bericht. Die Antwort kommt mit "
         "den Zahlen, auf denen sie beruht."),
        ("3", "check_circle", "Freigeben",
         "Nichts ändert sich ohne ein ausdrückliches Ja. Jeder Versuch steht mit "
         "Zeitpunkt, Konto, Begründung und Ergebnis im Änderungsprotokoll."),
    )
    inhalt = ('<div class="grid-3 gleich">'
              + "".join(_schritt(*s) for s in schritte) + "</div>")
    return _block("ablauf", "So läuft es ab", "Drei Schritte, dann arbeitet es.",
                  inhalt)


def _sicherheit() -> str:
    kacheln = (
        ("account_tree", "Erlaubte Konten",
         "Nur ausdrücklich angehakte Konten dürfen geschrieben werden. Kein Haken, "
         "kein Schreibzugriff."),
        ("payments", "Budgetdeckel",
         "Höchstes Tagesbudget je Budget und größter Sprung in einem Schritt — ein "
         "Faktor 2 heißt: höchstens verdoppeln."),
        ("speed", "Operationen je Aufruf",
         "Begrenzt den Schaden eines einzelnen Fehlgriffs auf eine überschaubare "
         "Zahl von Änderungen."),
        # Der Entwurf nennt hier zusaetzlich Passkeys. Die gibt es nicht.
        ("key", "Zwei Türen, zwei Schlüssel",
         "Menschen über Kennwort und zweiten Faktor; claude.ai über ein eigenes "
         "Zugangswort, das jederzeit gewechselt werden kann."),
    )
    inhalt = ('<div class="grid-2 gleich">'
              + "".join(_kachel(*k) for k in kacheln) + "</div>")
    return _block(
        "sicherheit", "Schutzgrenzen",
        "Mächtig — aber nur so weit, wie der Betreiber es erlaubt.", inhalt,
        lead="Was überhaupt möglich ist, steht fest, bevor die KI etwas "
             "vorschlägt. Alles darüber hinaus wird abgelehnt, bevor Google es zu "
             "sehen bekommt.")


def _transparenz() -> str:
    google = (
        _zeile("Berechtigung",
               f'<span class="mono">{_url_umbruch(gac.OAUTH_SCOPE)}</span>')
        + _zeile("Wofür", "Lesen der Ads-Daten und — nach Freigabe — Ändern.")
        + _zeile("Wo sie liegen", "Nur auf dem Server, auf dem die Anwendung läuft.",
                 "Keine Weitergabe an Dritte, keine Auswertung über Konten hinweg.")
        + _zeile("Aufbewahrung", "Solange die Verbindung besteht; der Refresh Token "
                                 "ist jederzeit löschbar."))
    betreiber = (
        _zeile("Firma", esc(FIRMA), INHABER)
        + _zeile("Anschrift", esc(ANSCHRIFT))
        + _zeile("Telefon", f'<a href="tel:{esc(TELEFON_WAHL)}">{esc(TELEFON_TEXT)}</a>')
        + _zeile("E-Mail", f'<a href="mailto:{esc(EMAIL)}">{esc(EMAIL)}</a>')
        + _zeile("UID-Nr.", f'<span class="mono">{esc(UID)}</span>')
        + _zeile("Zugang", 'Nicht öffentlich. '
                           '<span class="state neutral">nur Mitarbeiter</span>'))
    inhalt = (
        '<div class="grid-2">'
        f'<div class="card"><div class="card-kopf"><h2>Google-Daten</h2></div>'
        f'<table>{google}</table></div>'
        f'<div class="card"><div class="card-kopf"><h2>Betreiber</h2></div>'
        f'<table>{betreiber}</table></div>'
        '</div>'
        '<div class="card flach" style="margin-top:16px">'
        '<h3 style="margin-bottom:8px">In English</h3>'
        '<p class="note" style="margin-top:0;max-width:none">'
        f'<b>{esc(gac.PORTAL_NAME)}</b> connects Google Ads to Claude. It reads '
        'campaigns, ad groups, keywords, search terms, budgets and performance '
        'figures from the accounts the signed-in user already has access to, '
        'analyses them, and writes back — keywords, negative keywords, status, '
        'budgets and bids — only after an explicit, case-by-case approval. Every '
        'write runs as a dry run against Google&#39;s own validation first. Data '
        'stays on the server this runs on and is never shared with third parties. '
        f'The tool is operated by {esc(FIRMA)} (Graz, Austria) for its own accounts '
        'and those of the clients it looks after; access is restricted to staff of '
        'the operator.</p></div>')
    return _block(
        "transparenz", "Transparenz",
        "Welche Daten, wo sie liegen, wer dahintersteht.", inhalt,
        lead="Google verlangt diese Angaben für die Freigabe der Anwendung — und "
             "sie gehören ohnehin auf jede Seite, die fremde Werbekonten anfasst.")


def _fuss(logo: str) -> str:
    return (
        f'<footer class="fuss"><div class="innen">'
        f'<a href="{esc(NEO)}" target="_blank" rel="noopener"'
        f' aria-label="{esc(FIRMA)}">{logo}</a>'
        f'<span class="zeile">© 2026 {esc(FIRMA)} · Erich Nigg · '
        f'Nordweg 14, 8010 Graz · '
        f'<a href="tel:{esc(TELEFON_WAHL)}" style="color:inherit">'
        f'{esc(TELEFON_TEXT)}</a> · UID {esc(UID)}</span>'
        f'<div class="row links">'
        f'<a href="{esc(gac.PORTAL_IMPRESSUM)}" target="_blank" rel="noopener">'
        f'Impressum</a>'
        f'<a href="{esc(gac.PORTAL_DATENSCHUTZ)}" target="_blank" rel="noopener">'
        f'Datenschutz</a>'
        f'<a href="{esc(NEO)}" target="_blank" rel="noopener">neo-digital.at</a>'
        f'</div></div></footer>')


# --------------------------------------------------------------------------
# Die ganze Seite
# --------------------------------------------------------------------------
BESCHREIBUNG = ("Google Ads im Gespräch steuern: Konten lesen, auswerten und "
                f"nach ausdrücklicher Freigabe ändern. Betrieben von {FIRMA}.")


def seite(*, logo: str, favicon: str, anmelden_url: str = "/anmelden") -> bytes:
    """Die öffentliche Startseite als fertiges HTML-Dokument.

    logo und favicon kommen von aussen, damit dieses Modul nichts aus dem
    Portal importieren muss — der Betreiber kann seine eigene Wortmarke
    hinterlegen, und die Seite soll sie dann auch zeigen.
    """
    return ("<!doctype html>\n"
            '<html lang="de"><head><meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            '<meta name="color-scheme" content="dark">\n'
            f'<meta name="description" content="{esc(BESCHREIBUNG)}">\n'
            '<meta name="robots" content="noindex, nofollow">\n'
            f'<link rel="icon" href="{favicon}">\n'
            f"<title>{esc(gac.PORTAL_NAME)}</title>\n"
            f"<style>{DESIGN_CSS}</style></head>\n"
            "<body>\n"
            f"{_kopfleiste(anmelden_url, logo)}\n"
            '<main class="spalte">\n'
            f"{_hero(anmelden_url)}\n"
            f"{_kennzahlen()}\n"
            f"{_koennen()}\n"
            f"{_ablauf()}\n"
            f"{_sicherheit()}\n"
            f"{_transparenz()}\n"
            "</main>\n"
            f"{_fuss(logo)}\n"
            "</body></html>").encode("utf-8")
