# GAQL

Die Abfragesprache der Google Ads API. Nur lesend — mit GAQL lässt sich
nichts verändern. `google_ads_query` nimmt sie entgegen; die siebzehn
vorbereiteten Berichte in `google_ads_report` sind fertige GAQL-Abfragen
und der bessere Ausgangspunkt.

## Aufbau

```sql
SELECT   campaign.name, metrics.clicks, metrics.cost_micros
FROM     campaign
WHERE    segments.date DURING LAST_30_DAYS
  AND    campaign.status = 'ENABLED'
ORDER BY metrics.cost_micros DESC
LIMIT    50
```

Genau **eine** Ressource nach `FROM`. Kein `JOIN`, kein `GROUP BY`, kein
`SUM`, kein `COUNT`. Verwandte Felder liefert die Ressource mit — von
`keyword_view` aus sind `campaign.name` und `ad_group.name` erreichbar,
ohne dass etwas verbunden werden müsste.

## Die wichtigsten Ressourcen

| `FROM` | Eine Zeile ist | Metriken |
| --- | --- | --- |
| `customer` | das Konto | ja |
| `campaign` | eine Kampagne | ja |
| `ad_group` | eine Anzeigengruppe | ja |
| `keyword_view` | ein positives Keyword | ja |
| `ad_group_criterion` | ein Kriterium, auch ausschließende | nein |
| `campaign_criterion` | ein Kriterium auf Kampagnenebene | nein |
| `search_term_view` | ein tatsächlich gesuchter Begriff | ja |
| `ad_group_ad` | eine Anzeige | ja |
| `campaign_budget` | ein Budget | nein |
| `landing_page_view` | eine Zielseite | ja |
| `change_event` | eine Änderung im Konto | nein |
| `recommendation` | ein Vorschlag von Google | nein |
| `google_ads_field` | ein Feld des Datenmodells | nein |

## Segmente

Ein Segment zerlegt jede Zeile in mehrere. `segments.device` macht aus
einer Kampagnenzeile drei — je Gerät eine.

| Segment | Wirkung |
| --- | --- |
| `segments.date` | je Tag eine Zeile |
| `segments.device` | je Gerät |
| `segments.day_of_week`, `segments.hour` | je Wochentag, je Stunde |
| `segments.conversion_action_name` | je Conversion-Art |
| `segments.keyword.info.text` | das auslösende Keyword im Suchbegriffsbericht |

**Falle:** Ein Segment verändert die Summen. Wer `segments.device`
auswählt und die Kosten addiert, bekommt dasselbe Ergebnis wie ohne — wer
aber eine einzelne Zeile für „die Kampagne" hält, liest ein Drittel.

## Zeiträume

```sql
WHERE segments.date DURING LAST_30_DAYS
WHERE segments.date BETWEEN '2026-08-01' AND '2026-08-31'
WHERE segments.date >= '2026-08-01'
```

Verfügbar: `TODAY`, `YESTERDAY`, `LAST_7_DAYS`, `LAST_14_DAYS`,
`LAST_30_DAYS`, `THIS_MONTH`, `LAST_MONTH`, `THIS_WEEK_MON_TODAY`,
`LAST_BUSINESS_WEEK`.

**Ohne Datumsbedingung liefern Metriken die Werte seit Kontobeginn.** Das
ist selten gemeint und sieht auf den ersten Blick nach einem sehr
erfolgreichen Konto aus.

## Operatoren

```sql
=  !=  >  >=  <  <=
IN (…)        NOT IN (…)
LIKE '%tisch%'   NOT LIKE
CONTAINS ANY (…)  CONTAINS ALL (…)   -- für Listenfelder
IS NULL       IS NOT NULL
BETWEEN … AND …
DURING …
```

Zeichenketten stehen in **einfachen** Anführungszeichen. Aufzählungswerte
ebenso: `campaign.status = 'ENABLED'`, nicht `= ENABLED`.

## Die Antwort trägt die Namen der Abfrage

Googles REST-Schnittstelle antwortet in camelCase (`costMicros`), GAQL
fragt in snake_case (`metrics.cost_micros`). Der MCP-Server gleicht das
an: die Antwort trägt genau die Namen, die abgefragt wurden, und die
Verschachtelung ist flachgezogen.

```
Abfrage    SELECT campaign.name, metrics.cost_micros FROM campaign
Antwort    {"campaign.name": "Suche — AT",
            "metrics.cost_micros": "412350000",
            "metrics.cost_amount": 412.35}
```

Das `_amount`-Feld legt der Server dazu; in der API gibt es das nicht.

## Fallen

- **`metrics.cost_micros` ist in Millionstel.** 1 Euro = 1.000.000.
  Der MCP-Server legt bei jedem Millionstel-Feld ein lesbares Feld
  (`..._amount`) daneben.
- **`metrics.ctr` ist ein Anteil**, kein Prozentwert: 0,0432 ist 4,32 %.
- **`status != 'REMOVED'` gehört fast immer dazu.** Entfernte Objekte
  bleiben abfragbar und verfälschen jede Liste.
- **Metriken auf Ressourcen ohne Metriken** ergeben eine Fehlermeldung,
  keine Nullen. `campaign_budget` hat keine `metrics.clicks`.
- **Conversion-Zahlen sind nachträglich.** Die letzten drei bis sieben
  Tage sind unvollständig.
- **Nicht jedes Feld ist mit jedem kombinierbar.** Welche Felder
  zusammenpassen, sagt `google_ads_fields` im Feld `selectable_with`.
- **`LIMIT` begrenzt die Abfrage, `limit` das Werkzeug.** Der Server
  liefert standardmäßig 200 Zeilen und sagt, wenn er gekürzt hat.

## Nützliche Abfragen

Keywords mit Kosten und ohne Conversion:

```sql
SELECT campaign.name, ad_group.name, ad_group_criterion.keyword.text,
       ad_group_criterion.keyword.match_type, metrics.cost_micros,
       metrics.clicks, metrics.conversions
FROM   keyword_view
WHERE  segments.date DURING LAST_30_DAYS
  AND  metrics.cost_micros > 20000000
  AND  metrics.conversions = 0
  AND  ad_group_criterion.status = 'ENABLED'
ORDER BY metrics.cost_micros DESC
```

Kampagnen, die am Budget hängen:

```sql
SELECT campaign.name, campaign_budget.amount_micros,
       metrics.cost_micros, metrics.search_budget_lost_impression_share
FROM   campaign
WHERE  segments.date DURING LAST_30_DAYS
  AND  campaign.status = 'ENABLED'
ORDER BY metrics.search_budget_lost_impression_share DESC
```

Teure Suchbegriffe ohne Ertrag:

```sql
SELECT search_term_view.search_term, campaign.name,
       metrics.cost_micros, metrics.clicks, metrics.conversions
FROM   search_term_view
WHERE  segments.date DURING LAST_30_DAYS
  AND  metrics.conversions = 0
  AND  metrics.clicks >= 5
ORDER BY metrics.cost_micros DESC
```

Anzeigen, die nicht laufen:

```sql
SELECT campaign.name, ad_group.name, ad_group_ad.ad.id,
       ad_group_ad.policy_summary.approval_status,
       ad_group_ad.policy_summary.policy_topic_entries
FROM   ad_group_ad
WHERE  ad_group_ad.policy_summary.approval_status != 'APPROVED'
  AND  ad_group_ad.status = 'ENABLED'
```
