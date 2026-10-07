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
                Passkey", als es noch keine Passkeys gab; die Seite liess
                sie damals weg. Seit das Portal sie kann, stehen sie da.
                Eine Sicherheitsaussage, die nicht stimmt, gehört auf
                keine Seite, erst recht nicht auf eine geprüfte.
    Scope       Der Entwurf kürzt die Berechtigung zu „…/auth/adwords".
                Hier steht sie vollständig: auf einer Seite, die Auskunft
                über Daten gibt, ist die ganze Angabe das Mindeste.

Kein Aufbauschritt, keine Fremdbibliothek, nichts von einem fremden
Rechner. JavaScript steht genau an einer Stelle: die E-Mail-Adresse wird
zerlegt ausgeliefert, damit im Quelltext kein x@y steht, und die paar
Zeilen setzen sie wieder zu einem anklickbaren Verweis zusammen. Ohne sie
ist die Adresse trotzdem zu lesen — das Stilblatt setzt sie zusammen.
"""
from __future__ import annotations

import functools
import importlib.util
import pathlib
import sys

import google_ads_client as gac
import neo_design
from neo_design import esc, symbol

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


def postfach(adresse: str) -> str:
    """Eine E-Mail-Adresse, die im Quelltext der Seite nicht als eine dasteht.

    WAS DAS KANN UND WAS NICHT. Eine Adresse, die auf der Seite zu lesen
    sein soll, laesst sich nicht verschluesseln: der Browser muss sie
    anzeigen, also geht sie im Klartext ueber die Leitung. Verschleiern
    laesst sie sich, und zwar in zwei Stufen:

        im Quelltext   steht kein Stueck, das wie eine Adresse aussieht —
                       kein x@y. Das Zeichen dazwischen kommt aus dem
                       Stilblatt, die beiden Haelften aus Attributen.
                       Damit laufen alle Erntemaschinen ins Leere, die
                       den Seitenquelltext mit einem Muster absuchen, und
                       das sind fast alle.
        im Seitenbaum  steht auch nach dem Laden kein mailto:. Wer einen
                       Browser laufen laesst und danach alle Verweise
                       einsammelt — der zweithaeufigste Weg — findet
                       ebenfalls nichts. Die Adresse entsteht erst beim
                       Klick, und nur als Ziel des Sprungs.

    WAS BLEIBT: wer genau diese Seite ansieht, liest die Adresse, wie
    jeder Besucher sie liest, und setzt sie von Hand zusammen. Dagegen
    hilft nur, sie gar nicht anzuzeigen — und das verlangt Googles
    Pruefung ausdruecklich nicht. Weiter reicht Verschleierung nicht, und
    Behauptungen darueber hinaus waeren unehrlich.

    Ohne JavaScript steht die Adresse trotzdem lesbar da, nur nicht
    anklickbar: das Stilblatt setzt sie zusammen. Das ist Absicht — ein
    Pruefer, der kein Skript laufen laesst, muss den Kontakt finden.
    """
    kopf, _, rumpf = adresse.partition("@")
    if not rumpf:
        return esc(adresse)
    return (f'<span class="postfach" role="link" tabindex="0" '
            f'title="E-Mail-Adresse — anklicken zum Schreiben" '
            f'data-k="{esc(kopf)}" data-d="{esc(rumpf)}"></span>')


def beiwort() -> str:
    """Was neben der Wortmarke steht: der Name ohne das, was das Logo schon sagt."""
    name = gac.PORTAL_NAME
    return name[4:].strip() if name.upper().startswith("NEO ") else name


# --------------------------------------------------------------------------
# Das Aussehen. Die Tokens und Grundbausteine stehen in neo_design;
# hier steht nur, was keine andere Seite braucht.
# --------------------------------------------------------------------------
SEITEN_CSS = """
html{scroll-behavior:smooth;overflow-x:clip}
/* Die E-Mail-Adresse steht in zwei Attributen; das Zeichen dazwischen
   kommt von hier. Im Quelltext der Seite steht damit kein x@y. */
.postfach::after{content:attr(data-k) "\\0040" attr(data-d)}
.postfach{color:var(--neon);cursor:pointer;
  text-decoration:underline;text-decoration-color:color-mix(in srgb,var(--neon) 45%,transparent);
  text-underline-offset:.22em}
.postfach:hover{color:var(--neon-up);text-decoration-color:currentColor}
.postfach:focus-visible{outline:2px solid var(--neon-up);outline-offset:2px}
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
  letter-spacing:var(--tracking-display);line-height:1.06;margin:18px 0 0;max-width:17ch}
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
.grid-4{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:var(--space-4,16px)}
.grid-4.gleich{grid-auto-rows:1fr}
/* Sechs Kacheln mit Fliesstext: drei nebeneinander, zwei Reihen. Das
   auto-fit-Raster der Grundbausteine machte am breiten Bildschirm vier
   Spalten daraus — vier sind fuer Fliesstext zu eng, und 4 + 2 laesst
   eine halbe Reihe leer. */
.grid-3x{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:var(--space-4,16px)}
.grid-3x.gleich{grid-auto-rows:1fr}
.grid-3x.gleich > *{height:100%}
.grid-3x > .card + .card,.grid-4 > .card + .card{margin-top:0}
.grid-4.gleich > *{height:100%}
.card-kopf h3{margin:0}
/* --faint (#778276) erreicht auf der helleren Kartenflaeche (#151C14) nur
   4,34:1 — zu wenig fuer die kleinen Beschriftungen. Auf Karten deshalb
   eine Spur heller: 4,9:1, gemessen. */
.card th,.card .eyebrow{color:#808B7F}
.quelle{display:grid;gap:14px;align-content:start}
.quelle-kopf{display:flex;align-items:center;justify-content:space-between;gap:12px}
.quelle-kopf .sym{color:var(--neon)}
.quelle h3{margin:0}
.quelle-teil{display:grid;gap:6px}
.quelle-teil ul{margin:0;padding:0;list-style:none;display:grid;gap:6px}
.quelle-teil li{position:relative;padding-left:18px;color:var(--fg-soft);font-size:.92rem;
  line-height:1.45}
.quelle-teil li::before{content:"";position:absolute;left:2px;top:.62em;width:7px;height:7px;
  border-radius:50%;background:var(--line-strong)}
.quelle-teil.aendert li::before{background:var(--neon)}
.quelle-teil.nie li::before{background:none;border:1.5px solid var(--muted);width:6px;height:6px}
ul.rechte{margin:0;padding:0;list-style:none;display:grid;gap:10px;min-width:0}
ul.rechte li{min-width:0}
ul.rechte .mono{display:block;overflow-wrap:anywhere}
#transparenz td{overflow-wrap:anywhere}
.hero h1 .ganz{white-space:nowrap}
footer.fuss{border-top:1px solid var(--line);background:var(--ink-950);margin-top:40px}
footer.fuss .innen{max-width:var(--measure-site);margin:0 auto;padding:40px 28px;
  display:flex;gap:28px;flex-wrap:wrap;align-items:center}
footer.fuss svg{height:20px;width:auto;color:var(--neon);opacity:.85}
footer.fuss .zeile{color:var(--faint);font-size:.84rem}
footer.fuss .links{margin-left:auto;gap:22px;font-size:.86rem}

@media (max-width:1100px){
  .grid-4,.grid-3x{grid-template-columns:repeat(2,minmax(0,1fr))}
}
@media (max-width:900px){
  .hero{grid-template-columns:1fr;gap:36px;padding:56px 0 48px}
  .kopf nav.nav{display:none}
  .kopf .innen > .button{margin-left:auto}
  section.block{padding:56px 0}
}
@media (max-width:640px){
  .grid-4,.grid-3x{grid-template-columns:1fr}
  /* „Online-Marketing" bricht nicht um; die Schrift wird so klein, dass
     das Wort auch auf 320 px in die Spalte passt (9,3 px Breite je px
     Schriftgroesse, gemessen). */
  .hero h1{font-size:min(var(--size-display-xl), 9.4vw)}
  /* Beschriftung ueber dem Wert statt daneben, wie in der Verwaltung:
     „BERECHTIGUNGEN" und eine lange Adresse passen nicht nebeneinander. */
  #transparenz table,#transparenz tbody,#transparenz tr,#transparenz th,
  #transparenz td{display:block;width:auto}
  #transparenz th{border-bottom:none;padding-bottom:2px}
  #transparenz td{padding-top:0}
  .spalte,.kopf .innen,footer.fuss .innen{padding-left:18px;padding-right:18px}
  .card{padding:var(--space-5)}
  .kopf .wo{display:none}
  footer.fuss .links{margin-left:0}
}
"""

DESIGN_CSS = neo_design.BASIS_CSS + SEITEN_CSS


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
    ergaenzung = f'<span class="notiz">{esc(notiz)}</span>' if notiz else ""
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
# geht: drei Quellen — bezahlte Klicks, organische Suche, Verhalten auf
# der Website — laufen in einem Gespraech zusammen, und geschrieben wird
# erst nach dem Trockenlauf und einem Ja.
#
# Die Beschriftungen stehen in #A3ADA3 (7,5:1 auf der Kartenflaeche); das
# fruehere #778276 lag mit 4,34:1 knapp unter AA.
#
# Als SVG im Quelltext, aus demselben Grund wie die Symbole: die Seite
# laedt nichts nach. Ein Bild, das mitgeliefert wird, kann auch nicht
# fehlen.
# --------------------------------------------------------------------------
HERO_SVG = """<svg class="bild" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 520"
     role="img" aria-label="Zahlen aus Google Ads, Search Console und Analytics laufen in einem Gespräch zusammen; geändert wird erst nach Trockenlauf und Freigabe">
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
  <linearGradient id="hb-flaeche" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0%" stop-color="#a8f20d" stop-opacity=".34"/>
    <stop offset="100%" stop-color="#a8f20d" stop-opacity="0"/>
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

<!-- Quelle 1: Google Ads — Ausgaben je Kampagne, eine sticht heraus -->
<g transform="translate(56 78)">
  <rect width="356" height="92" rx="16" fill="#12180F" stroke="#232C22"/>
  <rect x="1" y="1" width="354" height="1" rx=".5" fill="#EAF0E9" fill-opacity=".05"/>
  <text x="20" y="30" font-family="ui-monospace,Menlo,monospace" font-size="12"
        fill="#A3ADA3" letter-spacing=".08em">GOOGLE ADS</text>
  <rect x="20" y="44" width="92" height="8" rx="4" fill="#C7D0C6" fill-opacity=".2"/>
  <rect x="20" y="60" width="64" height="8" rx="4" fill="#C7D0C6" fill-opacity=".14"/>
  <g transform="translate(150 18)">
    <rect x="0"   y="34" width="18" height="34" rx="4" fill="url(#hb-balken)" fill-opacity=".55"/>
    <rect x="30"  y="22" width="18" height="46" rx="4" fill="url(#hb-balken)" fill-opacity=".55"/>
    <rect x="60"  y="44" width="18" height="24" rx="4" fill="url(#hb-balken)" fill-opacity=".55"/>
    <rect x="90"  y="2"  width="18" height="66" rx="4" fill="url(#hb-balken)"/>
    <rect x="90"  y="2"  width="18" height="66" rx="4" fill="none" stroke="#bcff33" stroke-opacity=".7"/>
    <rect x="120" y="28" width="18" height="40" rx="4" fill="url(#hb-balken)" fill-opacity=".55"/>
    <rect x="150" y="40" width="18" height="28" rx="4" fill="url(#hb-balken)" fill-opacity=".55"/>
  </g>
</g>

<!-- Quelle 2: Search Console — die Position steigt -->
<g transform="translate(56 186)">
  <rect width="356" height="92" rx="16" fill="#12180F" stroke="#232C22"/>
  <rect x="1" y="1" width="354" height="1" rx=".5" fill="#EAF0E9" fill-opacity=".05"/>
  <text x="20" y="30" font-family="ui-monospace,Menlo,monospace" font-size="12"
        fill="#A3ADA3" letter-spacing=".08em">SEARCH CONSOLE</text>
  <rect x="20" y="44" width="84" height="8" rx="4" fill="#C7D0C6" fill-opacity=".2"/>
  <rect x="20" y="60" width="104" height="8" rx="4" fill="#C7D0C6" fill-opacity=".14"/>
  <g transform="translate(150 16)">
    <line x1="0" y1="66" x2="176" y2="66" stroke="#232C22"/>
    <polyline points="0,58 30,54 60,46 90,48 120,30 150,22 172,10" fill="none"
              stroke="#a8f20d" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>
    <circle cx="120" cy="30" r="3.4" fill="#a8f20d"/>
    <circle cx="172" cy="10" r="4.6" fill="#0E130E" stroke="#bcff33" stroke-width="2"/>
  </g>
</g>

<!-- Quelle 3: Analytics — Besuche ueber die Zeit -->
<g transform="translate(56 294)">
  <rect width="356" height="92" rx="16" fill="#12180F" stroke="#232C22"/>
  <rect x="1" y="1" width="354" height="1" rx=".5" fill="#EAF0E9" fill-opacity=".05"/>
  <text x="20" y="30" font-family="ui-monospace,Menlo,monospace" font-size="12"
        fill="#A3ADA3" letter-spacing=".08em">ANALYTICS</text>
  <rect x="20" y="44" width="100" height="8" rx="4" fill="#C7D0C6" fill-opacity=".2"/>
  <rect x="20" y="60" width="72" height="8" rx="4" fill="#C7D0C6" fill-opacity=".14"/>
  <g transform="translate(150 16)">
    <path d="M0 50 C 22 44, 34 30, 56 34 S 92 52, 114 36 S 150 14, 176 20 L176 66 L0 66 Z"
          fill="url(#hb-flaeche)"/>
    <path d="M0 50 C 22 44, 34 30, 56 34 S 92 52, 114 36 S 150 14, 176 20" fill="none"
          stroke="#a8f20d" stroke-opacity=".8" stroke-width="2"/>
    <line x1="0" y1="66" x2="176" y2="66" stroke="#232C22"/>
  </g>
</g>

<!-- Drei Leitungen laufen im Gespraech zusammen -->
<g fill="none" stroke="#a8f20d" stroke-opacity=".5" stroke-width="1.6" stroke-dasharray="5 6">
  <path d="M412 124 C 446 124, 446 188, 474 188"/>
  <path d="M412 232 C 446 232, 446 192, 474 192"/>
  <path d="M412 340 C 450 340, 446 196, 474 196"/>
</g>
<circle cx="474" cy="192" r="3.4" fill="#a8f20d"/>

<!-- Gespraech: die KI antwortet und fragt nach Freigabe -->
<g transform="translate(474 140)">
  <rect width="282" height="96" rx="16" fill="#12180F" stroke="#232C22"/>
  <rect x="1" y="1" width="280" height="1" rx=".5" fill="#EAF0E9" fill-opacity=".05"/>
  <rect x="22" y="24" width="196" height="9" rx="4.5" fill="#C7D0C6" fill-opacity=".34"/>
  <rect x="22" y="44" width="238" height="9" rx="4.5" fill="#C7D0C6" fill-opacity=".22"/>
  <rect x="22" y="64" width="150" height="9" rx="4.5" fill="#C7D0C6" fill-opacity=".22"/>
  <path d="M34 96 L34 112 L52 96 Z" fill="#12180F" stroke="#232C22"/>
</g>

<g transform="translate(474 268)">
  <rect width="282" height="112" rx="16" fill="#151C14" stroke="#33402F"/>
  <rect x="1" y="1" width="280" height="1" rx=".5" fill="#EAF0E9" fill-opacity=".06"/>
  <text x="22" y="34" font-family="ui-monospace,Menlo,monospace" font-size="13"
        fill="#A3ADA3" letter-spacing=".08em">TROCKENLAUF</text>
  <rect x="22" y="48" width="170" height="9" rx="4.5" fill="#C7D0C6" fill-opacity=".26"/>

  <!-- Freigabeknopf -->
  <rect x="22" y="70" width="128" height="30" rx="9" fill="#a8f20d"/>
  <path d="M40 85 l6 6 l12 -13" fill="none" stroke="#07120A" stroke-width="2.6"
        stroke-linecap="round" stroke-linejoin="round"/>
  <rect x="66" y="80" width="68" height="10" rx="5" fill="#07120A" fill-opacity=".72"/>
  <rect x="162" y="70" width="80" height="30" rx="9" fill="none" stroke="#33402F"/>
</g>

<!-- Weicher Markenschein unter dem Freigabeknopf -->
<ellipse cx="560" cy="356" rx="96" ry="26" fill="#a8f20d" fill-opacity=".14" filter="url(#hb-weich)"/>

<rect x="56" y="428" width="700" height="1.5" fill="url(#hb-kante)"/>
</svg>"""


# --------------------------------------------------------------------------
# Wie viele Werkzeuge der Server hat — gezaehlt, nicht abgeschrieben
# --------------------------------------------------------------------------
# Auf der alten Seite stand „13 Werkzeuge", als es laengst 25 waren. Die
# Zahlen kommen deshalb aus dem Server selbst: aus der Liste, die er
# Claude ausliefert. Der HTTP-Server hat das Modul schon geladen und
# bekommt es aus sys.modules; sonst wird es einmal nachgeladen.
@functools.lru_cache(maxsize=1)
def werkzeuge() -> dict:
    """Werkzeuge je Dienst: {"google_ads": 13, "search_console": 6, ...}."""
    modul = sys.modules.get("google_ads_mcp")
    if modul is None:
        pfad = pathlib.Path(__file__).with_name("google-ads-mcp.py")
        spec = importlib.util.spec_from_file_location("google_ads_mcp", pfad)
        modul = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modul)
    zaehler = {"google_ads": 0, "search_console": 0, "analytics": 0}
    for name in modul.HANDLERS:
        for dienst in zaehler:
            if name.startswith(dienst + "_"):
                zaehler[dienst] += 1
    zaehler["gesamt"] = len(modul.HANDLERS)
    return zaehler


# --------------------------------------------------------------------------
# Die Abschnitte
# --------------------------------------------------------------------------
def _kopfleiste(anmelden_url: str, logo: str) -> str:
    punkte = (("#quellen", "Datenquellen"), ("#koennen", "Was es kann"),
              ("#ablauf", "Ablauf"), ("#sicherheit", "Sicherheit"),
              ("#transparenz", "Transparenz"))
    nav = "".join(f'<a href="{p}">{esc(t)}</a>' for p, t in punkte)
    return (f'<header class="kopf"><div class="innen">'
            f'<a class="marke" href="{esc(NEO)}" target="_blank" rel="noopener"'
            f' aria-label="{esc(FIRMA)}">{logo}</a>'
            f'<span class="eyebrow wo">{esc(beiwort())}</span>'
            f'<nav class="nav" aria-label="Abschnitte">{nav}</nav>'
            f'<a class="button klein" href="{esc(anmelden_url)}">Anmelden</a>'
            f'</div></header>')


def _hero(anmelden_url: str) -> str:
    return (
        '<section class="hero">'
        '<div>'
        '<span class="eyebrow neon">Google Ads · Search Console · Analytics × KI</span>'
        '<h1><span class="ganz">Online-Marketing</span> steuern — '
        '<span class="ganz" style="color:var(--neon)">im Gespräch</span>.</h1>'
        f'<p class="lead">{esc(gac.PORTAL_NAME)} verbindet Google Ads, die Google Search '
        'Console und Google Analytics mit Claude. Die KI liest bezahlte Klicks, die '
        'organische Suche und das Verhalten auf der Website zusammen, findet '
        'Streuverluste, erklärt Zahlen im Klartext und setzt Änderungen um — jede '
        'einzelne erst nach ausdrücklicher Freigabe.</p>'
        f'<div class="row knoepfe">'
        f'<a class="button" href="{esc(anmelden_url)}">{symbol("login", 20)}'
        f'Zur Verwaltung anmelden</a>'
        f'<a class="button quiet" href="#quellen">Datenquellen ansehen</a></div>'
        f'<div class="row merkmale">'
        f'<span class="row eng">{symbol("science", 18)}'
        f'Trockenlauf vor jedem Schreiben</span>'
        f'<span class="row eng">{symbol("location_on", 18)}'
        f'Server in Deutschland</span></div>'
        '</div>'
        '<div class="bildrahmen"><div class="schein"></div>'
        f'<div class="tafel">{HERO_SVG}</div></div>'
        '</section>')


def _kennzahlen() -> str:
    zahl = werkzeuge()
    return ('<div class="grid-4 gleich kennzahlen">'
            + _kennzahl(str(zahl["gesamt"]), "Werkzeuge", "handyman",
                        "für Ads, Search Console und Analytics", neon=True)
            + _kennzahl("3", "Google-Dienste", "link",
                        "über eine einzige Anmeldung")
            + _kennzahl("Jede Änderung", "einzeln freigegeben", "verified",
                        "erst Trockenlauf, dann ein Ja")
            + _kennzahl("Deutschland", "Serverstandort", "shield_lock",
                        "Zugang und Protokoll liegen dort")
            + '</div>')


def _liste(titel: str, punkte: tuple[str, ...], art: str = "") -> str:
    eintraege = "".join(f"<li>{esc(p)}</li>" for p in punkte)
    return (f'<div class="quelle-teil {art}"><span class="eyebrow">{esc(titel)}</span>'
            f'<ul>{eintraege}</ul></div>')


def _quelle(icon: str, titel: str, zahl: int, liest: tuple, aendert: tuple,
            nie: tuple) -> str:
    return (f'<div class="card quelle">'
            f'<div class="quelle-kopf">{symbol(icon, 26)}'
            f'<span class="state neutral">{zahl} Werkzeuge</span></div>'
            f'<h3>{esc(titel)}</h3>'
            + _liste("Liest", liest)
            + _liste("Ändert — nach Freigabe", aendert, "aendert")
            + _liste("Ändert nie", nie, "nie")
            + '</div>')


def _quellen() -> str:
    zahl = werkzeuge()
    karten = (
        _quelle("ads_click", "Google Ads", zahl["google_ads"],
                ("Kampagnen, Anzeigengruppen, Anzeigen und Budgets",
                 "Keywords mit Qualitätsfaktor und die tatsächlichen Suchbegriffe",
                 "Landingpages, Geräte, Regionen, Tageszeiten, Conversions",
                 "Googles Empfehlungen und den Änderungsverlauf",
                 "Keyword-Planer mit Suchvolumen und Gebotsspannen"),
                ("Keywords und ausschließende Keywords",
                 "Status, Tagesbudgets und Gebote",
                 "Kampagnen und Anzeigen anlegen"),
                ("Budgets über den gesetzten Deckel hinaus",
                 "Mehr Änderungen auf einmal, als die Grenze je Aufruf erlaubt")),
        _quelle("travel_explore", "Google Search Console", zahl["search_console"],
                ("Suchanfragen und Seiten mit Klicks, Impressionen, Klickrate "
                 "und Position",
                 "Ob eine Seite im Google-Index ist, und wenn nicht, warum",
                 "Eingereichte Sitemaps mit Fehlern und Warnungen"),
                ("Sitemaps einreichen und entfernen",),
                ("Nutzer und Berechtigungen der Property",)),
        _quelle("monitoring", "Google Analytics 4", zahl["analytics"],
                ("Berichte mit frei wählbaren Dimensionen und Kennzahlen",
                 "Einstellungen samt Aufbewahrungsdauer der Daten",
                 "Schlüsselereignisse und benutzerdefinierte Dimensionen"),
                ("Ereignisse als Schlüsselereignis markieren",
                 "Ereignisparameter als Dimension registrieren"),
                ("Datenschutz-Einstellungen: Aufbewahrung, Google Signale, "
                 "Datenfreigabe",
                 "Nutzerverwaltung",
                 "Dimensionen, die nach personenbezogenen Daten aussehen")),
    )
    inhalt = (f'<div class="grid-3 gleich">{"".join(karten)}</div>'
              '<p class="note" style="margin-top:18px">Analytics zählt nur Besucher, '
              'die auf der jeweiligen Website der Statistik zugestimmt haben. Jede '
              'Antwort aus Analytics sagt das dazu, damit eine kleine Zahl nicht als '
              'wenig Besuch gelesen wird.</p>')
    return _block(
        "quellen", "Datenquellen", "Drei Quellen, ein Gespräch.", inhalt,
        lead="Jede Quelle beantwortet eine andere Frage: Was kostet ein Klick? Wie "
             "findet man die Website ohne Anzeige? Was passiert danach auf der "
             "Seite? Erst zusammen ergeben sie das ganze Bild.")


def _koennen() -> str:
    kacheln = (
        ("query_stats", "Konto verstehen",
         "Kampagnen, Keywords, Suchbegriffe, Budgets und Kennzahlen werden gelesen "
         "und in Zusammenhang gebracht. Fragen wie „Wo verbrenne ich Geld?“ "
         "bekommen eine belegte Antwort."),
        ("travel_explore", "Bezahlt und organisch nebeneinander",
         "Für welche Suchbegriffe wird bezahlt, obwohl die Website dafür ohnehin "
         "weit oben steht — und wo fehlt sie in der normalen Suche, sodass nur die "
         "Anzeige hilft? Anzeigen-Suchbegriffe und Search Console in einer Antwort."),
        ("conversion_path", "Vom Klick zur Anfrage",
         "Welche Kampagne bringt Besucher, die bleiben und anfragen? Klicks und "
         "Kosten aus Google Ads, Sitzungen und Schlüsselereignisse aus Analytics, "
         "zusammengeführt."),
        ("checklist", "Suchbegriffe ausmisten",
         "Welche Suchanfragen Geld kosten, welche zu Anfragen führen und welche als "
         "ausschließendes Keyword gehören — gefunden und als fertige Liste "
         "vorgeschlagen."),
        ("visibility", "Indexierung prüfen",
         "Ist eine Seite bei Google aufgenommen, und wenn nicht, warum? Die "
         "URL-Prüfung liefert den Status, den letzten Besuch des Crawlers und die "
         "Adresse, die Google als maßgeblich ansieht."),
        ("description", "Berichte im Klartext",
         "Monatsbericht, Vorher-Nachher, Vergleich zweier Zeiträume — über alle "
         "drei Quellen, als Text, den ein Kunde ohne Fachwissen versteht."),
    )
    inhalt = ('<div class="grid-3x gleich">'
              + "".join(_kachel(*k) for k in kacheln) + "</div>")
    return _block(
        "koennen", "Was es kann", "Ein Analyst, der alle Zahlen im Kopf hat.",
        inhalt,
        lead="Die KI arbeitet direkt auf den Live-Daten — nicht auf einem Export von "
             "letzter Woche. Sie beantwortet Fragen in ganzen Sätzen, begründet jede "
             "Empfehlung mit Zahlen und kann sie auf Wunsch gleich umsetzen.")


def _ablauf() -> str:
    schritte = (
        ("1", "link", "Google verbinden",
         "Einmal mit dem Google-Konto anmelden, das Ads, Search Console und "
         "Analytics ohnehin sieht. Die Anwendung bekommt keinen Zugriff, den dieses "
         "Konto nicht schon hat."),
        ("2", "forum", "Fragen stellen",
         "In Claude nachfragen: Analyse, Vorschlag, Bericht. Die Antwort kommt mit "
         "den Zahlen, auf denen sie beruht, und nennt die Quelle."),
        ("3", "check_circle", "Freigeben",
         "Nichts ändert sich ohne ein ausdrückliches Ja. Vorher läuft jede Änderung "
         "als Trockenlauf, und jeder Versuch steht mit Zeitpunkt, Ziel, Begründung "
         "und Ergebnis im Änderungsprotokoll."),
    )
    inhalt = ('<div class="grid-3 gleich">'
              + "".join(_schritt(*s) for s in schritte) + "</div>")
    return _block("ablauf", "So läuft es ab", "Drei Schritte, dann arbeitet es.",
                  inhalt)


def _sicherheit() -> str:
    kacheln = (
        ("lock", "Hauptschalter",
         "Schreiben ist ab Werk aus. Erst der Betreiber schaltet es ein, und der "
         "Schalter gilt für alle drei Dienste."),
        ("science", "Erst proben, dann handeln",
         "Bei Google Ads prüft Google selbst jede Änderung vorab, ohne sie "
         "auszuführen. Search Console und Analytics kennen das nicht — dort zeigt "
         "die Vorschau den aktuellen Stand und was sich ändern würde."),
        ("account_tree", "Erlaubte Konten",
         "In Google Ads lässt sich das Schreiben auf einzelne, angehakte Konten "
         "beschränken. Alle anderen bleiben dann unberührt."),
        ("payments", "Budgetdeckel",
         "Höchstes Tagesbudget und größter Sprung in einem Schritt — ein Faktor 2 "
         "heißt: höchstens verdoppeln. Dazu eine Obergrenze für Änderungen je "
         "Aufruf."),
        ("shield_lock", "Datenschutz geht vor",
         "Einstellungen, die bestimmen, wie viel über Besucher erhoben wird, und "
         "die Nutzerverwaltung fasst die Anwendung nicht an. Parameter, die nach "
         "personenbezogenen Daten aussehen, lehnt sie als Dimension ab."),
        ("key", "Zwei Türen, zwei Schlüssel",
         "Menschen melden sich mit Kennwort und zweitem Faktor oder mit Passkey an. "
         "Die Claude-Apps verbinden sich über OAuth und lassen sich einzeln wieder "
         "entfernen; lokale Werkzeuge nutzen ein eigenes Zugangswort."),
    )
    inhalt = ('<div class="grid-3x gleich">'
              + "".join(_kachel(*k) for k in kacheln) + "</div>")
    return _block(
        "sicherheit", "Schutzgrenzen",
        "Mächtig — aber nur so weit, wie der Betreiber es erlaubt.", inhalt,
        lead="Was überhaupt möglich ist, steht fest, bevor die KI etwas "
             "vorschlägt. Alles darüber hinaus wird abgelehnt, bevor Google es zu "
             "sehen bekommt.")


# Wofuer jede Berechtigung gebraucht wird, in der Reihenfolge von
# OAUTH_SCOPE. Eine Berechtigung ohne Zeile hier waere auf der Seite nicht
# erklaert — der Selbsttest prueft, dass jede eine hat.
ZWECK = {
    gac.ADS_SCOPE: "Google Ads lesen und — nach Freigabe — ändern.",
    gac.SEARCH_CONSOLE_SCOPE: "Search Console lesen; ändern nur Sitemaps.",
    gac.ANALYTICS_SCOPE: "Berichte und Einstellungen aus Analytics lesen.",
    gac.ANALYTICS_EDIT_SCOPE: "Analytics ändern, nur Schlüsselereignisse und "
                              "benutzerdefinierte Dimensionen.",
}


def _transparenz() -> str:
    rechte = "".join(
        f'<li><span class="mono">{_url_umbruch(scope)}</span>'
        f'<span class="notiz">{esc(ZWECK.get(scope, ""))}</span></li>'
        for scope in gac.OAUTH_SCOPE.split())
    google = (
        _zeile("Berechtigungen", f'<ul class="rechte">{rechte}</ul>')
        + _zeile("Gespeichert", "Auf dem Server: der Zugang zu Google, die "
                                "Einstellungen und das Änderungsprotokoll.",
                 "Berichte und Kennzahlen werden abgerufen, wenn eine Frage sie "
                 "braucht, und nicht gespeichert.")
        + _zeile("Weitergabe", "An Claude (Anthropic), und nur, was im Gespräch "
                               "abgefragt wird — damit die KI antworten kann.",
                 "Kein Verkauf, keine Werbung, keine Weitergabe an andere, keine "
                 "Auswertung über Konten hinweg.")
        + _zeile("Standort", "Server in Deutschland (IONOS Cloud, Berlin).")
        + _zeile("Aufbewahrung", "Solange die Verbindung besteht. Der Zugang ist "
                                 "jederzeit löschbar — in der Verwaltung oder unter "
                                 '<a href="https://myaccount.google.com/permissions" '
                                 'target="_blank" rel="noopener">'
                                 'myaccount.google.com/<wbr>permissions</a>.'))
    betreiber = (
        _zeile("Firma", esc(FIRMA), INHABER)
        + _zeile("Anschrift", esc(ANSCHRIFT))
        + _zeile("Telefon", f'<a href="tel:{esc(TELEFON_WAHL)}">{esc(TELEFON_TEXT)}</a>')
        + _zeile("E-Mail", postfach(EMAIL) if EMAIL else
                 '<span class="note">nicht gesetzt — '
                 'GOOGLE_ADS_PORTAL_CONTACT in der .env</span>')
        + _zeile("UID-Nr.", f'<span class="mono">{esc(UID)}</span>')
        + _zeile("Zugang", 'Nicht öffentlich. '
                           '<span class="state neutral">nur Mitarbeiter</span>'))
    inhalt = (
        '<div class="grid-2">'
        f'<div class="card"><div class="card-kopf"><h3>Google-Daten</h3></div>'
        f'<table>{google}</table></div>'
        f'<div class="card"><div class="card-kopf"><h3>Betreiber</h3></div>'
        f'<table>{betreiber}</table></div>'
        '</div>'
        '<div class="card flach" style="margin-top:16px" lang="en">'
        '<h3 style="margin-bottom:8px">In English</h3>'
        '<p class="note" style="margin-top:0;max-width:none">'
        f'<b>{esc(gac.PORTAL_NAME)}</b> connects Google Ads, Google Search Console '
        'and Google Analytics to Claude. It reads campaigns, keywords, search terms, '
        'budgets and performance figures, organic search performance and index '
        'status, and Analytics reports and settings — only from the accounts and '
        'properties the signed-in Google user already has access to. It writes back '
        'only after an explicit, case-by-case approval: keywords, negative keywords, '
        'status, budgets and bids in Google Ads; sitemaps in Search Console; key '
        'events and custom dimensions in Analytics. Every write runs as a dry run '
        'first. Privacy settings and user management are never changed. Data is '
        'passed to Claude (Anthropic) only as far as a question requires; it is not '
        'sold, not used for advertising and not shared with anyone else. The server '
        'in Germany stores the Google access token, settings and a change log, not '
        f'reports. The tool is operated by {esc(FIRMA)} (Graz, Austria) for its own '
        'accounts and those of the clients it looks after; access is restricted to '
        'staff of the operator.</p></div>')
    return _block(
        "transparenz", "Transparenz",
        "Welche Daten, wohin sie gehen, wer dahintersteht.", inhalt,
        lead="Google verlangt diese Angaben für die Freigabe der Anwendung — und sie "
             "gehören ohnehin auf jede Seite, die fremde Marketing-Konten anfasst.")


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
# Die einzigen JavaScript-Zeilen dieser Seite. Sie laden nichts und
# rechnen nichts; sie haengen einen Klickgriff an den Platzhalter der
# E-Mail-Adresse. Die Adresse selbst entsteht erst im Griff, beim Klick —
# nicht beim Laden. Siehe postfach() weiter oben.
POSTFACH_JS = """
(function () {
  document.querySelectorAll('.postfach').forEach(function (platz) {
    var springen = function () {
      // Erst hier entsteht die Adresse — vorher steht sie nirgends im
      // Seitenbaum, also findet sie auch kein Sammler, der den Browser
      // laufen laesst und danach die Verweise abgreift.
      location.href = 'mail' + 'to:' + platz.dataset.k
        + String.fromCharCode(64) + platz.dataset.d;
    };
    platz.addEventListener('click', springen);
    platz.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); springen(); }
    });
  });
})();
"""

BESCHREIBUNG = ("Google Ads, Search Console und Analytics im Gespräch steuern: "
                "Zahlen lesen, auswerten und nach ausdrücklicher Freigabe ändern. "
                f"Betrieben von {FIRMA}.")


def seite(*, logo: str, favicon: str, anmelden_url: str = "/login") -> bytes:
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
            f"{_quellen()}\n"
            f"{_koennen()}\n"
            f"{_ablauf()}\n"
            f"{_sicherheit()}\n"
            f"{_transparenz()}\n"
            "</main>\n"
            f"{_fuss(logo)}\n"
            f"<script>{POSTFACH_JS}</script>\n"
            "</body></html>").encode("utf-8")
