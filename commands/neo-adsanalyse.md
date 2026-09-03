---
description: Ein Google-Ads-Konto messen und befunden — Struktur, Leistung, Suchbegriffe, Verschwendung. Ändert nichts.
---

Analysiere das Konto. **Diese Analyse verändert nichts** — kein
Schreibaufruf, auch kein Trockenlauf, außer der Projektinhaber verlangt
ihn ausdrücklich.

Lade zuerst den Skill `neo-google-ads` und `references/analyse.md`.

## 1. Konto und Kontext

`google_ads_accounts`. Bei mehreren Konten **fragen**, nie raten.

Dann die fünf Fragen aus dem Skill, deren Antworten in keinem Konto
stehen: Was zählt als Conversion, welches Ziel, was darf eine Conversion
kosten, welcher Zeitraum, was ist saisonal. Ohne sie ist jede Bewertung
geraten — frage, bevor du misst.

## 2. Struktur lesen

In dieser Reihenfolge, mit `google_ads_report`:

`account` → `conversion_actions` → `campaigns` → `budgets` → `ad_groups`

Halte fest: Währung, Zeitzone, was gezählt wird, wie viele Kampagnen
laufen, welche Gebotsstrategien, welche Budgets begrenzen.

**Prüfe `conversion_actions` genau.** Ein Konto, das Seitenaufrufe zählt,
hat hervorragende Zahlen und verkauft nichts. Steht dort etwas
Fragwürdiges, ist das der erste Befund — vor jeder Leistungszahl.

## 3. Leistung messen

`keywords`, `search_terms`, `ads`, `landing_pages`, `devices`, `hours`.
Zeitraum `LAST_30_DAYS`, sofern nichts anderes vereinbart ist.

Nenne bei jeder Aussage **Zeitraum und Datenmenge**. Unter 30 Klicks oder
5 Conversions: sag, dass die Datenlage keine Aussage trägt. Die letzten
drei bis sieben Tage sind bei Conversions unvollständig.

## 4. Verschwendung suchen

Danach wird zuerst gesucht, weil sie ohne Risiko abzustellen ist:

- Suchbegriffe mit Kosten und ohne Conversion (`search_terms`)
- Keywords mit Kosten und ohne Conversion (`keywords`)
- `BROAD`-Keywords und was sie tatsächlich einsammeln
- Anzeigen, die nicht freigegeben sind (`ads`, `approval_status`)
- Kampagnen am Budgetlimit gegen Kampagnen ohne Ertrag
- Landingpages, die zum Keyword nicht passen

## 5. Website ansehen

Ist eine Seite genannt: ansehen. Angebot, Zielhandlung, Zielgruppe. Passt
sie zu den Keywords, die darauf zeigen? Wird die Zielhandlung überhaupt
gemessen?

## 6. Befunden

Jeder Befund nach dem Muster im Skill: **Beobachtung, Bedeutung, Ursache,
Vorschlag**. Ohne Zahl mit Zeitraum kein Befund. Ohne Ursache kein
Vorschlag.

Sortiere nach Geld, nicht nach Aufwand: der teuerste Befund zuerst.

## 7. Abschluss

- Was ist gut. Auch das gehört zum Befund.
- Die drei wichtigsten Befunde mit Betrag.
- Was du **nicht** beurteilen konntest und warum — zu wenig Daten,
  fehlende Angabe, kein Zugriff.
- Der Hinweis, dass `/neo-google-ads:neo-adsoptimierung` daraus einen
  Plan macht, der dann freizugeben ist.
