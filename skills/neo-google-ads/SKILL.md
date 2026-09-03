---
name: neo-google-ads
description: >
  NEO-Regeln für Google Ads. Diesen Skill laden bei jeder Arbeit an
  Google-Ads-Konten: Kampagnen analysieren, optimieren, anlegen oder
  pausieren, Keywords und ausschließende Keywords verwalten, Budgets und
  Gebote ändern, Suchbegriffe auswerten, Keyword-Recherche mit dem
  Keyword-Planer, Kontostruktur prüfen, Anzeigen bewerten, Empfehlungen
  von Google einordnen, Konten von Kunden betreuen. Ebenso beim Einrichten
  des Zugangs (OAuth, Developer Token, Manager-Konto), beim Setzen der
  Schutzgrenzen und wenn eine Website für Google Ads analysiert werden
  soll. Auch laden, wenn nur gelesen wird.
metadata:
  herkunft: NEO Digital — Vorgaben Erich Nigg, Stand 2026-09
  api: Google Ads API v25 über REST, MCP-Server im selben Plugin
---

# NEO-Regeln für Google Ads

## Wie diese Regeln zu lesen sind

| Wort | Bedeutung |
| --- | --- |
| **Nie**, **immer**, **muss** | Verbindlich. Ein Verstoß ist ein **Blocker**: die Änderung gilt als nicht fertig. |
| **Ausnahme** | Nur mit ausdrücklicher Freigabe des Kontoinhabers, festgehalten mit Grund und Datum. **Ohne Vermerk gibt es keine Ausnahme.** |
| **Sollte** | Begründet abweichbar, die Abweichung wird gemeldet. |

## Der Grundsatz: hier wird Geld ausgegeben

Jede Schreiboperation in diesem Skill verändert eine laufende Werbeschaltung.
Ein falsches Budgetfeld ist kein fehlgeschlagener Test, sondern eine
Rechnung. Ein zu breit gestelltes Keyword kostet an einem Wochenende mehr
als ein Monat Arbeit. Ein versehentlich pausiertes Konto kostet Umsatz,
und niemand merkt es am Sonntag.

Daraus folgt die Reihenfolge, die **nie** abgekürzt wird:

```
messen -> Plan vorlegen -> Freigabe abwarten -> Trockenlauf -> umsetzen -> belegen
```

- **Nie** wird geschrieben, bevor gemessen wurde. Kein Vorschlag ohne
  Zahlen aus dem Konto, mit Zeitraum und Datenmenge.
- **Nie** wird geschrieben, bevor der Kontoinhaber den Plan freigegeben
  hat. Freigabe heißt: er hat den Plan gelesen und zugestimmt. Schweigen
  ist keine Freigabe, „mach mal" ist keine Freigabe für einen Plan, den
  er nicht gesehen hat.
- **Immer** läuft jede Änderung zuerst als Trockenlauf (`dry_run: true`).
  Der Trockenlauf schickt die Operation durch Googles vollständige
  Regelprüfung und verändert nichts.
- **Immer** wird nach der Umsetzung belegt, was geschehen ist —
  mit den Rückmeldungen der API, nicht mit einer Behauptung.

Wer diese Reihenfolge einhält, kann jeden Schritt zurücknehmen. Wer sie
abkürzt, hat im Fehlerfall nur eine Rechnung und keine Erklärung.

## Was nie ohne ausdrückliche Freigabe geschieht

Diese acht Dinge sind **Blocker**. Es gibt keinen Anlass, bei dem sie ohne
eine ausdrückliche, auf genau diesen Fall bezogene Freigabe passieren:

1. **Ein Budget erhöhen.** Auch um „nur" zehn Prozent. Auch wenn die
   Kampagne begrenzt ist.
2. **Eine Kampagne oder Anzeigengruppe aktivieren**, die pausiert war.
   Pausiert ist eine Entscheidung, die jemand getroffen hat.
3. **Etwas entfernen** (`REMOVED`). Entfernen ist bei Google endgültig,
   ein Rückgängig gibt es nicht. Pausieren statt entfernen, immer.
4. **Die Gebotsstrategie wechseln.** Der Wechsel setzt die Lernphase
   zurück und kostet zwei bis drei Wochen Leistung.
5. **Keywords mit weitgehend passender Wortgruppe (`BROAD`) anlegen.**
   Sie sind die häufigste Ursache für verbrannte Budgets.
6. **Eine neue Kampagne anlegen.**
7. **Etwas in einem fremden Konto ändern**, für das keine schriftliche
   Beauftragung vorliegt.
8. **Die Schutzgrenzen lockern** — `write_enabled`, Kontoliste,
   Budgetdeckel, Steigerungsfaktor.

Ohne Freigabe zulässig ist: **lesen**, **rechnen**, **Trockenlauf**,
**Plan schreiben**.

## Die vier Schutzgrenzen

Sie sitzen im Werkzeug, nicht in der Absicht. Sie greifen auch dann, wenn
diese Regeln missachtet werden — das ist ihr Zweck.

| Grenze | Standard | Wirkung |
| --- | --- | --- |
| `write_enabled` | **aus** | Ohne diesen Schalter geht kein scharfer Schreibvorgang durch. |
| `allowed_customer_ids` | leer | Leer heißt: alle zugänglichen Konten. Bei Kundenbetreuung **immer** füllen. |
| `max_daily_budget_micros` | 0 | Obergrenze je Tagesbudget. 0 heißt: keine. Bei Kundenkonten **immer** setzen. |
| `max_budget_increase_factor` | 3.0 | Größter Sprung in einem Schritt. Fängt den Vertipper um den Faktor 1000 ab. |

Gesetzt werden sie mit `google-ads-auth.py --allow-write`. Wer sie
lockert, hält Grund und Datum fest. Details in
`references/sicherheit.md`.

## Der Kontext entscheidet über alles andere

**Nie** eine Zahl bewerten, bevor diese fünf Dinge bekannt sind. Ohne sie
ist jede Empfehlung geraten:

1. **Was zählt als Conversion?** Bericht `conversion_actions`. Ein Konto,
   das Seitenaufrufe als Conversion zählt, hat einen wunderbaren CPA und
   verkauft nichts.
2. **Welches Ziel hat der Kontoinhaber?** Umsatz, Anfragen, Bekanntheit,
   Termine. Danach richtet sich, welche Kennzahl überhaupt zählt.
3. **Wie viel darf eine Conversion kosten?** Ohne diese Zahl ist „zu
   teuer" eine Meinung.
4. **Welche Datenmenge liegt vor?** Unter 30 Klicks oder 5 Conversions
   im Zeitraum ist jede Aussage über Leistung Rauschen. Das wird gesagt,
   nicht überspielt.
5. **Was ist saisonal?** Ein Vergleich der letzten 30 Tage mit den 30
   davor über einen Feiertag hinweg misst den Feiertag.

Fehlt eine dieser Angaben, wird sie **gefragt**, bevor gearbeitet wird.
Die Antworten stehen in keinem Konto.

## Das Verfahren in acht Schritten

Wenn der Auftrag lautet „optimiere meine Kampagnen für die Seite X":

1. **Konto finden.** `google_ads_accounts`. Bei mehreren Konten fragen,
   welches gemeint ist — nie raten.
2. **Kontext klären.** Die fünf Fragen oben.
3. **Struktur lesen.** Berichte `account`, `campaigns`, `ad_groups`,
   `budgets`, `conversion_actions`. Erst verstehen, wie das Konto gebaut
   ist, dann bewerten.
4. **Die Website ansehen**, wenn sie im Auftrag genannt ist. Was wird
   angeboten, was ist die Zielhandlung, passt die Landingpage zu den
   Keywords, die darauf zeigen. Bericht `landing_pages` dazu.
5. **Leistung messen.** `keywords`, `search_terms`, `ads`, `devices`,
   `hours`. Zeitraum nennen, Datenmenge nennen.
6. **Plan vorlegen.** Aufbau in `references/aenderungen.md`. Jede
   Maßnahme mit Beleg, erwarteter Wirkung und Risiko. Nichts wird
   ausgeführt.
7. **Freigabe abwarten.** Der Kontoinhaber entscheidet, welche Punkte
   umgesetzt werden. Auch „alle" ist seine Entscheidung, nicht die
   Annahme des Agenten.
8. **Umsetzen und belegen.** Erst Trockenlauf, dann scharf, dann das
   Ergebnis mit den Antworten der API zeigen. Bei Änderungen an mehreren
   Stellen: einzeln, nicht in einem Rutsch.

Nach jeder Änderung, die Leistung beeinflusst: **frühestens nach 14 Tagen**
neu bewerten. Vorher misst man die Lernphase, nicht die Maßnahme.

## Kundenkonten

Ein fremdes Konto ist kein eigenes.

- **Nie** in einem Kundenkonto schreiben ohne schriftliche Beauftragung
  für genau dieses Konto.
- Das Konto steht in `allowed_customer_ids`, einzeln. Nicht „alle".
- `max_daily_budget_micros` ist gesetzt, auf einen mit dem Kunden
  vereinbarten Wert.
- Der Zugriff läuft über das Manager-Konto (`login_customer_id`), nicht
  über einen persönlichen Zugang des Kunden.
- Das Änderungsprotokoll (`google_ads_change_log`) ist die Antwort auf
  „wer hat das geändert". Jede Änderung trägt eine Begründung im Feld
  `reason` — in ganzen Sätzen, nicht „Optimierung".
- Endet die Beauftragung, wird das Konto aus `allowed_customer_ids`
  entfernt. Im selben Schritt.

## Fertig heißt gemessen

Eine Änderung gilt als fertig, wenn **alle** Punkte zutreffen:

- [ ] Der Trockenlauf lief und wurde von Google angenommen.
- [ ] Der Kontoinhaber hat den Plan freigegeben, auf diesen Fall bezogen.
- [ ] Der scharfe Lauf lief, und seine Antwort ist gezeigt — die
      Ressourcennamen der geänderten Objekte, nicht eine Zusammenfassung.
- [ ] Ein Lesevorgang **nach** der Änderung bestätigt den neuen Zustand.
      Die Antwort des Schreibvorgangs allein reicht nicht.
- [ ] Das Änderungsprotokoll enthält den Eintrag mit Begründung.
- [ ] Der Zeitpunkt der nächsten Bewertung ist genannt.

Behauptet zählt nicht. Gemessen zählt.

## Werkzeuge

Der MCP-Server im selben Plugin stellt dreizehn Werkzeuge bereit. Sechs
lesen, sechs schreiben, eines zeigt, was geschrieben wurde.

| Werkzeug | Zweck |
| --- | --- |
| `google_ads_accounts` | Zugängliche Konten mit Währung, Zeitzone, Manager-Kennzeichen |
| `google_ads_report` | Sechzehn vorbereitete Berichte, siehe `references/analyse.md` |
| `google_ads_query` | Freie GAQL-Abfrage, siehe `references/gaql.md` |
| `google_ads_fields` | Welche Felder existieren — bei abgelehnter Abfrage |
| `google_ads_keyword_ideas` | Keyword-Planer: Ideen mit Suchvolumen und Gebotsspanne |
| `google_ads_keyword_metrics` | Suchvolumen für eine vorhandene Liste |
| `google_ads_add_keywords` | Keywords in eine Anzeigengruppe |
| `google_ads_add_negative_keywords` | Ausschließende Keywords, drei Ebenen |
| `google_ads_set_status` | Aktivieren, pausieren, entfernen |
| `google_ads_set_budget` | Tagesbudget ändern |
| `google_ads_set_bid` | CPC-Gebot setzen |
| `google_ads_mutate` | Alles Übrige, roh — Kampagnen, Anzeigen, Gebotsanpassungen |
| `google_ads_change_log` | Was dieser Server geschrieben hat |

Sind die Werkzeuge nicht verfügbar, ist der Zugang nicht eingerichtet:
`references/einrichtung.md`, dann `scripts/google-ads-check.py`. Unter
Windows heißt Python meist `python` und nicht `python3` — dann bleibt die
Werkzeugliste leer, ohne dass ein Fehler erscheint. In einer Cloud-Sitzung
gibt es weder Browser noch bleibende Dateien; dort kommen die Zugangsdaten
aus Umgebungsvariablen. Beides steht in `references/einrichtung.md`.

Dazu vier Skripte, die von Hand laufen:

| Skript | Zweck |
| --- | --- |
| `google-ads-auth.py` | Verbinden, Schutzgrenzen setzen (`--allow-write`), Stand zeigen (`--show`), Zugangsdaten für eine Cloud-Sitzung ausgeben (`--env`) |
| `google-ads-check.py` | Misst die Verbindung in sieben Prüfungen, mit `--customer-id` auch den Schreibweg |
| `google-ads-selftest.py` | Weist ohne Netz nach, dass die Schutzgrenzen greifen — 34 Fälle |
| `google-ads-mcp.py` | Der Server selbst; `--list-tools` und `--check-config` zur Diagnose |

Darunter liegt `google_ads_client.py`: Konfiguration, Zugangstausch, HTTP,
Fehlerübersetzung und die Schutzgrenzen. Keine ausführbare Datei — wer eine
Grenze verstehen will, liest sie dort.

## Vertiefungen

| Datei | Inhalt |
| --- | --- |
| `references/einrichtung.md` | Zugang einrichten, Developer Token, Manager-Konto, Fehlerbilder |
| `references/analyse.md` | Die siebzehn Berichte, was sie beantworten, in welcher Reihenfolge |
| `references/aenderungen.md` | Aufbau des Plans, Trockenlauf, Umsetzung, Rücknahme |
| `references/keywords.md` | Keywords, Übereinstimmungstypen, ausschließende Keywords, Suchbegriffe |
| `references/kampagnenbau.md` | Neue Kampagnen und Anzeigen über `google_ads_mutate` |
| `references/gaql.md` | GAQL: Aufbau, Segmente, Fallen |
| `references/sicherheit.md` | Schutzgrenzen, Zugangsdaten, Datenschutz, Protokoll |
