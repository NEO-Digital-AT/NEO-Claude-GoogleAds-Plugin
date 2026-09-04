---
description: Kampagnen optimieren — messen, Plan vorlegen, Freigabe abwarten, Trockenlauf, umsetzen, belegen
---

Optimiere die Kampagnen. **Die Reihenfolge ist verbindlich und wird nicht
abgekürzt:**

```
messen -> Plan vorlegen -> Freigabe abwarten -> Trockenlauf -> umsetzen -> belegen
```

Lade zuerst den Skill `neo-google-ads`, dazu `references/analyse.md`,
`references/aenderungen.md` und `references/keywords.md`.

## 1. Messen

Führe die Analyse aus `/neo-google-ads:neo-adsanalyse` vollständig durch.
**Ohne Messung kein Vorschlag.** Übernimm keine Befunde aus einem
früheren Lauf ohne sie erneut zu belegen — ein Konto ändert sich.

## 2. Plan vorlegen

Aufbau genau nach `references/aenderungen.md`: je Befund **Beleg,
Ursache, Maßnahme, Wirkung, Risiko, Rücknahme**. Dazu:

- Die **Reihenfolge** der Umsetzung: erst was spart, dann was strukturiert,
  zuletzt was kostet.
- Den **Ausgangswert** jeder Änderung, gelesen und notiert. Ohne notierten
  Ausgangswert gibt es keine Rücknahme.
- Den Zeitpunkt der nächsten Bewertung, frühestens 14 Tage später.

Markiere ausdrücklich, was ein **Blocker** ist — Budgeterhöhung,
Aktivierung, Entfernen, Strategiewechsel, `BROAD`-Keywords, neue
Kampagne, fremdes Konto, gelockerte Grenze. Jeder davon braucht eine
eigene Zusage.

**Halte hier an.** Führe nichts aus.

## 3. Freigabe abwarten

Der Kontoinhaber entscheidet Punkt für Punkt. Teilfreigabe ist der
Normalfall. Setze **nur** um, was freigegeben ist — nicht das
Naheliegende gleich mit.

Bleibt eine Antwort offen, frage nach. Schweigen ist keine Freigabe.

## 4. Trockenlauf

Jede freigegebene Maßnahme zuerst mit `dry_run: true`. Zeige die
Rückmeldung. Ein Trockenlauf, der scheitert, wird **nicht** scharf
wiederholt: erst die Ursache beheben, dann erneut trocken.

## 5. Umsetzen

`dry_run: false`, mit `reason` in ganzen Sätzen — Befund, Zahl, wer
freigegeben hat, Datum.

Eine Maßnahme nach der anderen. Nicht alles in einem Aufruf, außer die
Operationen gehören zusammen (dann `partial_failure: false`, damit
entweder alles oder nichts passiert).

## 6. Belegen

Für jede umgesetzte Maßnahme:

- [ ] Antwort des Schreibvorgangs mit Ressourcennamen
- [ ] **Nachgelesener** Zustand aus einem Bericht — die Schreibantwort
      allein reicht nicht
- [ ] Gegenüberstellung vorher/nachher
- [ ] Eintrag in `google_ads_change_log`
- [ ] Termin der nächsten Bewertung

Nenne zum Schluss, was **nicht** umgesetzt wurde und warum: nicht
freigegeben, am Trockenlauf gescheitert, an einer Schutzgrenze
abgewiesen. Eine Schutzgrenze wird dabei **nie** gelockert — passt eine
Maßnahme nicht durch, wird die Maßnahme vorgelegt, nicht die Grenze
verschoben.
