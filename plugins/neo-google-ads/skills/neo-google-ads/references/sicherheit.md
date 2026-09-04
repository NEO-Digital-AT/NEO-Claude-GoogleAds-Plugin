# Sicherheit und Zugangsdaten

## Die vier Schutzgrenzen

Sie stehen unter `guardrails` in `~/.config/neo-google-ads/config.json`
und greifen im Werkzeug, nicht in der Absicht — auch dann, wenn diese
Regeln missachtet werden. Gesetzt werden sie mit
`google-ads-auth.py --allow-write`.

```json
"guardrails": {
  "write_enabled": false,
  "allowed_customer_ids": [],
  "max_daily_budget_micros": 0,
  "max_budget_increase_factor": 3.0,
  "max_operations_per_call": 200,
  "log_changes": true
}
```

| Grenze | Wirkung bei Verstoß |
| --- | --- |
| `write_enabled: false` | Jeder scharfe Schreibvorgang wird abgelehnt. Trockenläufe laufen. |
| `allowed_customer_ids` | Ein Konto außerhalb der Liste wird abgelehnt — auch im Trockenlauf. |
| `max_daily_budget_micros` | Ein Budget über der Grenze wird abgelehnt. 0 heißt: keine Grenze. |
| `max_budget_increase_factor` | Ein Sprung über den Faktor wird abgelehnt. Der aktuelle Wert wird dafür gelesen. |
| `max_operations_per_call` | Mehr Operationen als erlaubt werden abgelehnt. |

Die Kontoliste und der Schreibschalter gelten **auch für Trockenläufe**.
Ein Trockenlauf, der scharf abgelehnt würde, beantwortet sonst eine Frage,
die niemand gestellt hat.

Eine Grenze zu lockern ist eine Entscheidung des Kontoinhabers, mit Grund
und Datum. Der Agent lockert sie **nie** selbst, auch nicht kurz, auch
nicht, um eine freigegebene Maßnahme durchzubekommen. Passt die Maßnahme
nicht durch die Grenze, wird die Maßnahme vorgelegt — nicht die Grenze
verschoben.

## Zugangsdaten

- Die Datei liegt unter `~/.config/neo-google-ads/config.json`,
  **außerhalb jedes Repositorys**, mit Rechten `0600`.
- Sie enthält Client-Geheimnis, Refresh Token und Developer Token. Wer
  sie hat, kann Geld ausgeben.
- **Nie** in ein Repository, **nie** in eine Chatnachricht, **nie** in
  eine Fehlermeldung, **nie** in ein Protokoll. `google-ads-auth.py --show`
  gibt die Werte gekürzt aus; das ist die Fassung, die weitergereicht
  werden darf.
- Kompromittierter Zugang: Zugriff unter
  <https://myaccount.google.com/permissions> entziehen, OAuth-Client in
  der Cloud Console löschen, neuen anlegen, `google-ads-auth.py` erneut.
  Ein Token, das einmal offen lag, gilt als kompromittiert — löschen
  genügt nicht, es muss ersetzt werden.
- In einer CI kommen die Werte aus Geheimnisvariablen (`GOOGLE_ADS_*`),
  nicht aus einer Datei im Arbeitsverzeichnis.

## Änderungsprotokoll

Jeder Schreibversuch — Trockenlauf eingeschlossen — steht in
`~/.config/neo-google-ads/changes.jsonl`, eine Zeile je Versuch:
Zeitstempel, Konto, Trockenlauf ja/nein, Ergebnis, Begründung,
Operationen, Dauer.

- Gelesen wird es mit `google_ads_change_log`.
- Es wird **vor** der Antwort geschrieben, damit ein Absturz es nicht
  verschluckt.
- Es ist die lokale Sicht. Googles eigene Sicht steht im Bericht
  `change_history` und umfasst auch Änderungen über die Oberfläche.
  Bei einer Frage nach einer Änderung werden **beide** gelesen.
- Es wird nicht gelöscht und nicht gekürzt. Wird es zu groß, wird es
  archiviert, mit Datum.

## Datenschutz

- Ein Google-Ads-Konto enthält personenbezogene Daten: Nutzerlisten,
  Kundenabgleichlisten, Standortdaten, in Suchbegriffen gelegentlich
  Namen und Adressen.
- **Nie** Nutzerlisten oder Kundenabgleichdaten auslesen, ausgeben oder
  weitergeben, außer der Auftrag verlangt genau das und der Kontoinhaber
  hat schriftlich zugestimmt.
- Suchbegriffe können personenbezogene Angaben enthalten. Sie werden für
  die Analyse verwendet, aber nicht in Berichte übernommen, die das Konto
  verlassen.
- `google_ads_mutate` mit `offlineUserDataJobOperation` oder
  `uploadUserData` überträgt Kundendaten an Google. Das ist eine
  Auftragsverarbeitung mit eigener Rechtsgrundlage und **nie** eine
  Nebenwirkung einer Optimierung. Für die Pflichten in Österreich und der
  EU gilt der Skill `neo-recht`.
- Ein Screenshot oder ein Ausschnitt aus einem Konto, der weitergegeben
  wird, enthält die Kundennummer. Bei fremden Konten wird sie geschwärzt.

## Mandantentrennung

- Ein Aufruf betrifft genau ein Konto. `customer_id` wird **immer**
  ausdrücklich gesetzt, nie aus einem vorherigen Aufruf übernommen.
- Bei mehreren betreuten Konten steht **vor jeder Änderung** in der
  Antwort, um welches es geht — Name und Nummer, nicht nur die Nummer.
- `login_customer_id` ist das Manager-Konto, `customer_id` das Konto, in
  dem gearbeitet wird. Die beiden zu verwechseln führt zu
  `USER_PERMISSION_DENIED`, im ungünstigen Fall zu einer Änderung im
  falschen Konto.
- Endet eine Beauftragung, wird das Konto im selben Schritt aus
  `allowed_customer_ids` entfernt.

## Was der Agent nie tut

1. Schreiben ohne Freigabe für genau diesen Fall.
2. Eine Schutzgrenze lockern.
3. Ein Zugangsgeheimnis ausgeben, protokollieren oder weitergeben.
4. In einem Konto arbeiten, das nicht ausdrücklich genannt wurde.
5. `REMOVED` verwenden, wo `PAUSED` genügt.
6. Ein Ergebnis behaupten, das nicht nachgelesen wurde.
7. Kundendaten an Google übertragen, ohne dass es der Auftrag ist.
8. Einen fehlgeschlagenen Trockenlauf scharf wiederholen.
