# Änderungen

## Der Plan

Nichts wird umgesetzt, bevor der Kontoinhaber einen Plan gesehen und
freigegeben hat. Der Plan hat immer diesen Aufbau:

```
Konto:     Möbelhaus Beispiel (123-456-7890), EUR, Zeitzone Europe/Vienna
Zeitraum:  01.08.2026 bis 30.08.2026 (30 Tage)
Datenlage: 1.240 Klicks, 34 Conversions, 2.180 EUR — belastbar
Ziel laut Kontoinhaber: Anfragen, höchstens 60 EUR je Anfrage

Befund 1: 412 EUR ohne Ertrag auf einem weitgehend passenden Keyword
  Beleg      keyword_view, "büromöbel" BROAD: 412 EUR, 118 Klicks, 0 Conv.
  Ursache    search_terms zeigt 71 % Gebrauchtwaren- und Reparaturanfragen
  Maßnahme   a) Keyword auf PAUSED
             b) "büromöbel" als PHRASE neu anlegen, Gebot 0,85 EUR
             c) 6 ausschließende Keywords auf Kampagnenebene
  Wirkung    erwartet 380 bis 410 EUR im Monat frei, Volumen -60 %
  Risiko     PHRASE erfasst weniger; falls Anfragen einbrechen, ist a)
             in einem Schritt zurückzunehmen
  Rücknahme  Keyword wieder auf ENABLED, neue Ausschlüsse entfernen

Befund 2: ...

Reihenfolge: Befund 1 zuerst, 14 Tage messen, dann Befund 2.
Nächste Bewertung: 17.09.2026
```

Jeder Befund nennt **Beleg, Ursache, Maßnahme, Wirkung, Risiko,
Rücknahme**. Fehlt einer davon, ist der Befund nicht fertig.

## Reihenfolge der Umsetzung

Nie alles auf einmal. Wer sechs Dinge gleichzeitig ändert, weiß in zwei
Wochen nicht, welches davon gewirkt hat.

1. **Zuerst, was Geld spart** und nichts riskiert: ausschließende
   Keywords, offensichtlich erfolglose Keywords pausieren.
2. **Dann, was die Struktur verbessert**: Keywords umhängen, Anzeigen
   ergänzen.
3. **Zuletzt, was Geld kostet**: Budgets, Gebote, neue Kampagnen — und
   nur einzeln.

Zwischen zwei Schritten, die dieselbe Kampagne betreffen: **14 Tage**.
Bei automatischen Gebotsstrategien länger, die Lernphase dauert bis zu
drei Wochen.

## Trockenlauf

Jedes Schreibwerkzeug hat `dry_run`, Standard `true`. Der Trockenlauf
schickt die Operation an Google, dort laufen alle Prüfungen — Syntax,
Rechte, Grenzen, Richtlinien —, und es wird nichts geschrieben.

```
dry_run: true   ->  "VALIDATED — nothing was written"
dry_run: false  ->  "APPLIED — n operations written"
```

Regeln:

- **Immer** zuerst mit `dry_run: true`.
- `dry_run: false` **nur nach Freigabe**, und nur für die freigegebenen
  Punkte.
- Ein Trockenlauf, der scheitert, wird **nicht** scharf wiederholt. Erst
  die Ursache beheben.
- Der Trockenlauf prüft Regeln, nicht Sinn. Er sagt nicht, ob die
  Maßnahme klug ist.

## Begründung

Jeder Schreibaufruf trägt `reason`. Er landet wörtlich im
Änderungsprotokoll und ist die Antwort auf „warum steht das hier".

```
gut     "Suchbegriffe zeigen Gebrauchtwarenabsicht, 412 EUR ohne Conversion
         in 30 Tagen, freigegeben von E. Nigg am 03.09.2026"
schlecht "Optimierung"
```

## Rücknahme

Vor jeder Änderung muss klar sein, wie sie zurückgeht.

| Änderung | Rücknahme | Vollständig? |
| --- | --- | --- |
| Status auf PAUSED | Status auf ENABLED | ja |
| Keyword hinzugefügt | Keyword auf REMOVED | ja |
| Ausschluss hinzugefügt | Ausschluss entfernen | ja |
| Budget geändert | alten Wert zurückschreiben | ja, Ausgaben bleiben |
| Gebot geändert | altes Gebot zurückschreiben | ja |
| Status auf REMOVED | **keine** | **nein — deshalb nie** |
| Gebotsstrategie gewechselt | zurückwechseln | nein, Lernphase erneut |

Der alte Wert wird **vor** der Änderung gelesen und im Plan festgehalten.
„Ich stelle es zurück" ohne notierten Ausgangswert ist keine Rücknahme.

## Beleg nach der Umsetzung

Die Antwort des Schreibvorgangs allein reicht nicht — sie sagt, dass
Google die Operation angenommen hat, nicht, wie das Konto jetzt aussieht.
Deshalb **immer** danach lesen:

```
1. Schreiben        google_ads_set_status ... dry_run: false
2. Antwort zeigen   "APPLIED — 1 operation", Ressourcenname
3. Nachlesen        google_ads_report keywords, gefiltert auf dieses Keyword
4. Gegenüberstellen vorher PAUSED / jetzt ENABLED
5. Protokoll        google_ads_change_log, Eintrag mit Begründung
```

## Grenzen der API

- **15.000 Operationen am Tag** bei Basic-Zugriff. Eine Massenänderung
  über tausend Keywords ist zu planen, nicht zu improvisieren.
- **Höchstens 5.000 Operationen** in einem `mutate`-Aufruf; das Werkzeug
  begrenzt zusätzlich auf `max_operations_per_call` (Standard 200).
- `partial_failure: true` führt die gültigen Operationen aus und meldet
  die übrigen. Nützlich bei großen Keyword-Listen, gefährlich bei
  Änderungen, die zusammengehören — dort **false**, damit entweder alles
  oder nichts passiert.
- Ein Konto, in dem gerade jemand über die Oberfläche arbeitet, kann eine
  Änderung mit `CONCURRENT_MODIFICATION` ablehnen. Dann neu lesen und
  erneut versuchen, nicht blind wiederholen.

## Was der Agent nie selbst entscheidet

- Wie viel Geld ausgegeben wird.
- Welche Zielgruppe angesprochen wird.
- Was das Produkt kostet oder verspricht.
- Ob eine Kampagne abgeschaltet wird, weil sie „sich nicht rechnet" —
  ob sie sich rechnet, entscheidet der Kontoinhaber anhand von Zahlen,
  die der Agent liefert.
