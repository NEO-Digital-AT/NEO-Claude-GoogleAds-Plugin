# Analyse

## Reihenfolge

Nicht mit den Zahlen anfangen. Zuerst muss klar sein, was das Konto
überhaupt misst und wie es gebaut ist — sonst bewertet man Zahlen, die
etwas anderes bedeuten, als man annimmt.

1. `account` — Währung, Zeitzone, Manager-Kennzeichen, Testkonto
2. `conversion_actions` — **was gilt als Conversion**
3. `campaigns` — was läuft, mit welchem Budget, welcher Gebotsstrategie
4. `budgets` — welche Budgets begrenzen, welche nicht
5. `ad_groups` — wie fein ist die Struktur
6. Erst jetzt Leistung: `keywords`, `search_terms`, `ads`

## Die siebzehn Berichte

Aufruf: `google_ads_report` mit `customer_id`, `report` und bei
Leistungsberichten `date_range` oder `start_date`/`end_date`.

| Bericht | Beantwortet | Zeitraum |
| --- | --- | --- |
| `account` | Währung, Zeitzone, Manager, Testkonto, Optimierungsfaktor | — |
| `campaigns` | Was läuft, was kostet es, was bringt es, Anteil möglicher Impressionen | ja |
| `ad_groups` | Wo liegt das Geld innerhalb einer Kampagne | ja |
| `keywords` | Welche Keywords kosten, welche liefern, Qualitätsfaktor | ja |
| `search_terms` | **Was Menschen wirklich getippt haben** | ja |
| `negative_keywords_campaign` | Was auf Kampagnenebene ausgeschlossen ist | — |
| `negative_keywords_ad_group` | Was auf Anzeigengruppenebene ausgeschlossen ist | — |
| `shared_negative_lists` | Welche gemeinsamen Ausschlusslisten es gibt | — |
| `ads` | Anzeigenstärke, Freigabestatus, Überschriften | ja |
| `budgets` | Budgethöhe und der Ressourcenname für eine Änderung | — |
| `landing_pages` | Welche Seiten hinter den Anzeigen liegen und wie sie laufen | ja |
| `devices` | Handy gegen Rechner gegen Tablet | ja |
| `locations` | Welche Regionen ein- und ausgeschlossen sind | — |
| `hours` | Wochentag und Stunde | ja |
| `conversion_actions` | Was gezählt wird, wie es zugeordnet wird | — |
| `recommendations` | Was Google selbst vorschlägt | — |
| `change_history` | Wer hat wann was geändert (30 Tage) | ja |

Zusatzbedingungen über `filter`, zum Beispiel
`"campaign.status = 'ENABLED'"` oder `"metrics.clicks > 10"`.

## Was jeder Bericht wirklich sagt

**`search_terms` ist der wichtigste Bericht.** Er zeigt die Lücke
zwischen dem, was gebucht wurde, und dem, was tatsächlich gesucht wurde.
Dort stehen die Suchbegriffe, für die Geld ausgegeben wurde, ohne dass
jemand sie je gebucht hat. Er ist die Quelle für ausschließende Keywords
und für neue Keywords zugleich. Zu beachten: Google zeigt aus
Datenschutzgründen nur Suchbegriffe mit ausreichendem Volumen — die
Summe der Klicks im Bericht liegt regelmäßig unter der Summe im
Keyword-Bericht. Die Differenz ist nicht auswertbar, und das wird gesagt,
nicht weggerechnet.

**`keywords` mit Qualitätsfaktor.** Der Qualitätsfaktor (1 bis 10) zerfällt
in drei Teile: erwartete Klickrate, Anzeigenrelevanz, Nutzererfahrung mit
der Landingpage. Alle drei stehen im Bericht. Ein Faktor unter 5 mit
nennenswerten Kosten ist ein Befund — aber der Faktor allein ist keine
Handlungsanweisung, er sagt nur, in welche Richtung zu schauen ist.

**`ads` mit Anzeigenstärke.** „Ausreichend" oder schlechter bei einer
responsiven Suchanzeige heißt meist: zu wenige Überschriften, zu wenig
Variation, Keywords fehlen im Text. `approval_status` ungleich `APPROVED`
ist wichtiger als jede Leistungszahl — eine abgelehnte Anzeige läuft nicht.

**`recommendations`.** Googles Vorschläge sind nicht neutral: ein Teil
davon erhöht schlicht die Ausgaben. Sie werden gelesen und einzeln
bewertet, nie pauschal angewandt.

**`change_history`.** Vor jeder Diagnose eines Leistungseinbruchs zu
lesen. Sehr oft war es eine Änderung und keine Marktbewegung.

## Datenmenge und Zeitraum

- Unter **30 Klicks** oder **5 Conversions** im Zeitraum: keine Aussage
  über Leistung. Das wird so gesagt.
- Standardzeitraum **LAST_30_DAYS**. Kürzer nur, wenn ein konkretes
  Ereignis untersucht wird.
- Ein Vergleich zweier Zeiträume ist nur dann einer, wenn beide gleich
  lang sind und keiner einen Feiertag, eine Aktion oder einen
  Saisonwechsel enthält, den der andere nicht hat.
- Conversions werden **nachträglich zugeordnet**. Die letzten drei bis
  sieben Tage sind unvollständig; wer sie mitbewertet, misst zu wenig
  Erfolg.

## Die Website mit ansehen

Wenn im Auftrag eine Seite genannt ist, gehört sie zur Analyse:

- Was wird angeboten, was ist die Zielhandlung, für wen.
- Passt die Landingpage zu den Keywords, die darauf zeigen — Bericht
  `landing_pages` gegen `keywords` gehalten.
- Wird die Zielhandlung überhaupt als Conversion gemessen — gegen
  `conversion_actions` gehalten.
- Welche Begriffe verwendet die Seite selbst. Sie sind Ausgangspunkt für
  `google_ads_keyword_ideas` mit `url` oder `site` als Saat.

## Der Befund

Ein Befund besteht aus vier Teilen, sonst ist er eine Meinung:

```
Beobachtung   Keyword "büromöbel" (BROAD): 412 EUR, 0 Conversions, 30 Tage
Bedeutung     3,2 % des Kontobudgets ohne messbaren Ertrag
Ursache       Suchbegriffe zeigen überwiegend Gebrauchtwaren-Absicht
Vorschlag     BROAD pausieren, PHRASE anlegen, 6 Suchbegriffe ausschließen
```

Ohne Zahl mit Zeitraum kein Befund. Ohne Ursache kein Vorschlag.
