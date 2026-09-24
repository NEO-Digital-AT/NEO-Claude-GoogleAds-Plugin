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

Kein Aufbauschritt, keine Fremdbibliothek, nichts von einem fremden
Rechner. JavaScript steht genau an einer Stelle: die E-Mail-Adresse wird
zerlegt ausgeliefert, damit im Quelltext kein x@y steht, und die paar
Zeilen setzen sie wieder zu einem anklickbaren Verweis zusammen. Ohne sie
ist die Adresse trotzdem zu lesen — das Stilblatt setzt sie zusammen.
"""
from __future__ import annotations

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
        + _zeile("Wofür", "Google Ads, Search Console und Analytics lesen und — nach "
                          "Freigabe — ändern.",
                 "In Search Console nur Sitemaps, in Analytics nur Schlüsselereignisse und "
                 "benutzerdefinierte Dimensionen. Datenschutz-Einstellungen und Nutzerrechte "
                 "ändert die Anwendung nicht.")
        + _zeile("Wo sie liegen", "Nur auf dem Server, auf dem die Anwendung läuft.",
                 "Keine Weitergabe an Dritte, keine Auswertung über Konten hinweg.")
        + _zeile("Aufbewahrung", "Solange die Verbindung besteht; der Refresh Token "
                                 "ist jederzeit löschbar."))
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

BESCHREIBUNG = ("Google Ads im Gespräch steuern: Konten lesen, auswerten und "
                f"nach ausdrücklicher Freigabe ändern. Betrieben von {FIRMA}.")


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
            f"{_koennen()}\n"
            f"{_ablauf()}\n"
            f"{_sicherheit()}\n"
            f"{_transparenz()}\n"
            "</main>\n"
            f"{_fuss(logo)}\n"
            f"<script>{POSTFACH_JS}</script>\n"
            "</body></html>").encode("utf-8")
