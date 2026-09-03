# Keywords und Ausschlüsse

## Die drei Übereinstimmungstypen

| Typ | Schreibweise in der Oberfläche | Reichweite | Kontrolle |
| --- | --- | --- | --- |
| `EXACT` | `[schreibtisch kaufen]` | eng | hoch |
| `PHRASE` | `"schreibtisch kaufen"` | mittel | mittel |
| `BROAD` | `schreibtisch kaufen` | weit | gering |

Seit Google die Bedeutung statt der Zeichenfolge auswertet, erfasst auch
`EXACT` naheliegende Varianten und `PHRASE` deutlich mehr, als der Name
vermuten lässt. `BROAD` erfasst alles, was Googles Modell für verwandt
hält — bei knappen Budgets ist das der schnellste Weg, Geld zu verlieren.

**Regel:** Neue Keywords werden als `PHRASE` angelegt. `EXACT` für
Begriffe mit belegter Conversion-Historie. `BROAD` ist ein Blocker und
braucht eine ausdrückliche Freigabe — sinnvoll fast nur mit automatischer
Gebotsstrategie, ausreichend Conversion-Daten und gepflegten Ausschlüssen.

## Wann ein Keyword aufgenommen wird

Alle vier Punkte müssen zutreffen:

1. Es ist im `search_terms`-Bericht als tatsächliche Suche belegt, **oder**
   es hat im Keyword-Planer messbares Volumen.
2. Die Absicht dahinter passt zum Angebot. „günstig", „gebraucht",
   „selber bauen", „Job", „Reparatur" sind eigene Absichten.
3. Es gibt eine Landingpage, die genau dazu passt.
4. Es liegt in der richtigen Anzeigengruppe — eine Anzeigengruppe, ein
   Thema. Wer zwanzig unterschiedliche Keywords in eine Gruppe legt,
   bekommt eine Anzeige, die zu keinem davon passt.

## Ausschließende Keywords

Der wirksamste Hebel und der mit dem geringsten Risiko.

### Die drei Ebenen

| Ebene | Werkzeugparameter | Wofür |
| --- | --- | --- |
| Konto/Liste | `level: "shared_set"` | Was nie passt: „gratis", „Job", „gebraucht" |
| Kampagne | `level: "campaign"` | Was zu dieser Kampagne nicht passt |
| Anzeigengruppe | `level: "ad_group"` | Abgrenzung zwischen Gruppen derselben Kampagne |

Eine gemeinsame Liste (`shared_set`) ist einer Wiederholung in jeder
Kampagne vorzuziehen: sie wird an einer Stelle gepflegt und wirkt überall.
Vorhandene Listen zeigt der Bericht `shared_negative_lists`.

### Übereinstimmung bei Ausschlüssen

Ausschlüsse verhalten sich **anders** als positive Keywords: Sie erfassen
keine Varianten. Kein Plural, keine Tippfehler, keine Synonyme.

- `PHRASE`-Ausschluss `"gebraucht"` blockt „schreibtisch gebraucht", aber
  nicht „gebrauchte schreibtische".
- Deshalb: Ein- und Mehrzahl beide aufnehmen, häufige Schreibweisen
  ebenso.
- `EXACT`-Ausschluss blockt nur genau diese Suche. Für einen einzelnen
  auffälligen Suchbegriff richtig, für ein Thema zu eng.

**Regel:** `PHRASE` als Standard, `EXACT` für einzelne Suchbegriffe,
`BROAD`-Ausschlüsse nur bei einzelnen Wörtern, die in keinem Zusammenhang
passen — sie blocken jede Suche, die alle Wörter enthält, und schneiden
schnell mehr weg als gedacht.

### Das Verfahren

```
1. google_ads_report search_terms, LAST_30_DAYS, nach Kosten sortiert
2. Aussortieren: falsche Absicht, falsches Produkt, falscher Ort,
   Informationssuche ohne Kaufabsicht, Bewerbungen, Konkurrenznamen
3. Zu Themen bündeln, nicht Begriff für Begriff
4. Ebene wählen (Liste / Kampagne / Anzeigengruppe)
5. Trockenlauf
6. Vorlegen: Liste, Ebene, erwartete Ersparnis aus den Kosten
7. Nach Freigabe scharf, dann in 14 Tagen search_terms erneut
```

**Vor dem Ausschließen immer prüfen, was sonst noch blockiert wird.**
Ein Ausschluss `"möbel"` legt eine ganze Kampagne still. Beim geringsten
Zweifel: eng ausschließen und den `keywords`-Bericht danach gegenlesen.

### Was nie ausgeschlossen wird

- Ein Suchbegriff mit Conversions, weil er teuer aussieht. Erst rechnen.
- Ein Begriff mit weniger als 20 Klicks. Zu wenig Daten.
- Der eigene Markenname, auch wenn er günstig konvertiert.
- Etwas, das in einer anderen Kampagne gewollt ist — Ausschlüsse auf
  Kontoebene wirken überall.

## Keyword-Recherche

`google_ads_keyword_ideas` — Ideen mit Suchvolumen, Wettbewerb und
Gebotsspanne. Saat wahlweise:

| Saat | Feld | Wann |
| --- | --- | --- |
| Begriffe | `keywords` | Thema bekannt |
| Seite | `url` | Ideen zu genau einer Landingpage |
| Website | `site` | Überblick über das ganze Angebot |
| beides | `keywords` + `url` | Thema bekannt, Seite soll einengen |

Standardwerte: Sprache `1001` (Deutsch), Region `2040` (Österreich).
Weitere Regionen: `2276` Deutschland, `2756` Schweiz.

`google_ads_keyword_metrics` misst eine **vorhandene** Liste, ohne neue
zu erfinden — für die Frage „lohnt sich das, was wir schon haben".

**Zahlen richtig lesen:**

- `avg_monthly_searches` ist über zwölf Monate gemittelt und gerundet.
  Bei saisonalen Begriffen sagt der Mittelwert wenig — `monthly_volumes`
  zeigt den Verlauf.
- `competition` misst den Wettbewerb **unter Werbetreibenden**, nicht die
  Schwierigkeit in der organischen Suche.
- Die Gebotsspanne (`low_top_of_page_bid` bis `high_top_of_page_bid`) ist
  eine Schätzung für die Anzeige oberhalb der Ergebnisse, keine Zusage.
- Volumen ist keine Absicht. 40.000 Suchen im Monat auf „schreibtisch"
  sind weniger wert als 300 auf „höhenverstellbarer schreibtisch kaufen".

## Gebote

`google_ads_set_bid` wirkt nur, wo manuell geboten wird. Bei
`MAXIMIZE_CONVERSIONS`, `TARGET_CPA`, `TARGET_ROAS` oder
`MAXIMIZE_CONVERSION_VALUE` nimmt Google die Gebote selbst in die Hand —
ein gesetztes CPC-Gebot wird dann angenommen und ignoriert. Vor jeder
Gebotsänderung `campaigns` lesen und `bidding_strategy_type` prüfen.
