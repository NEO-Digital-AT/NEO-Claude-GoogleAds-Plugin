# Kampagnen und Anzeigen anlegen

Alles, was die sechs gezielten Schreibwerkzeuge nicht abdecken, läuft
über `google_ads_mutate`. Es nimmt die Operationsliste der API
unverändert entgegen — dieselbe Struktur, die Googles Dokumentation
beschreibt.

**Eine neue Kampagne ist ein Blocker.** Sie entsteht erst nach
ausdrücklicher Freigabe, und die Freigabe braucht den vollständigen Plan:
Ziel, Budget, Zielregion, Keywords, Anzeigentexte, Landingpage.

## Verkettung mit vorläufigen Kennungen

Ein Kampagnenaufbau besteht aus mehreren Objekten, die aufeinander
verweisen. In **einem** `mutate`-Aufruf lassen sie sich verketten: eine
negative Zahl als Kennung wird zur vorläufigen Kennung, auf die spätere
Operationen im selben Aufruf verweisen dürfen. Google löst sie beim
Anwenden auf. Bei einem Trockenlauf funktioniert das genauso.

```
customers/1234567890/campaignBudgets/-1   das Budget, das gleich entsteht
customers/1234567890/campaigns/-2         die Kampagne, die es benutzt
customers/1234567890/adGroups/-3          die Anzeigengruppe darin
```

Die Reihenfolge in der Liste ist die Reihenfolge der Ausführung: ein
Objekt muss vor seinem Verweis stehen.

## Rezept: Suchkampagne von Grund auf

Ein Aufruf, sechs Operationen. `1234567890` ist die Kundennummer.

```json
[
  {"campaignBudgetOperation": {"create": {
    "resourceName": "customers/1234567890/campaignBudgets/-1",
    "name": "Schreibtische — Tagesbudget",
    "amountMicros": "20000000",
    "deliveryMethod": "STANDARD",
    "explicitlyShared": false
  }}},

  {"campaignOperation": {"create": {
    "resourceName": "customers/1234567890/campaigns/-2",
    "name": "Suche — Schreibtische — AT",
    "status": "PAUSED",
    "advertisingChannelType": "SEARCH",
    "campaignBudget": "customers/1234567890/campaignBudgets/-1",
    "manualCpc": {"enhancedCpcEnabled": false},
    "networkSettings": {
      "targetGoogleSearch": true,
      "targetSearchNetwork": false,
      "targetContentNetwork": false,
      "targetPartnerSearchNetwork": false
    },
    "startDate": "2026-09-15",
    "geoTargetTypeSetting": {
      "positiveGeoTargetType": "PRESENCE",
      "negativeGeoTargetType": "PRESENCE"
    }
  }}},

  {"campaignCriterionOperation": {"create": {
    "campaign": "customers/1234567890/campaigns/-2",
    "location": {"geoTargetConstant": "geoTargetConstants/2040"}
  }}},

  {"adGroupOperation": {"create": {
    "resourceName": "customers/1234567890/adGroups/-3",
    "name": "Höhenverstellbare Schreibtische",
    "campaign": "customers/1234567890/campaigns/-2",
    "status": "ENABLED",
    "type": "SEARCH_STANDARD",
    "cpcBidMicros": "850000"
  }}},

  {"adGroupCriterionOperation": {"create": {
    "adGroup": "customers/1234567890/adGroups/-3",
    "status": "ENABLED",
    "keyword": {"text": "höhenverstellbarer schreibtisch", "matchType": "PHRASE"}
  }}},

  {"adGroupAdOperation": {"create": {
    "adGroup": "customers/1234567890/adGroups/-3",
    "status": "ENABLED",
    "ad": {
      "finalUrls": ["https://beispiel.at/schreibtische/hoehenverstellbar"],
      "responsiveSearchAd": {
        "path1": "schreibtische",
        "path2": "hoehenverstellbar",
        "headlines": [
          {"text": "Höhenverstellbare Tische", "pinnedField": "HEADLINE_1"},
          {"text": "Elektrisch, 70–120 cm"},
          {"text": "Lieferung in 5 Tagen"},
          {"text": "5 Jahre Garantie"},
          {"text": "Ab 389 Euro"}
        ],
        "descriptions": [
          {"text": "Stufenlos verstellbar, geprüfte Stabilität, Montage inklusive."},
          {"text": "Beratung im Haus. Lieferung österreichweit in fünf Werktagen."}
        ]
      }
    }
  }}}
]
```

**Neue Kampagnen werden auf `PAUSED` angelegt.** Erst wird das Ergebnis
gelesen und geprüft — Anzeigenfreigabe, Keywords, Zielregion —, dann
entscheidet der Kontoinhaber über das Aktivieren.

## Regeln für responsive Suchanzeigen

- Mindestens **3 Überschriften** und **2 Beschreibungen**; Google erlaubt
  bis zu 15 und 4. Weniger als 8 Überschriften kostet Anzeigenstärke.
- Überschrift höchstens **30 Zeichen**, Beschreibung höchstens **90**.
  Umlaute zählen als ein Zeichen. Zu lange Texte lehnt die API ab, der
  Trockenlauf zeigt es.
- **Nie mehr als eine Überschrift anheften** (`pinnedField`). Jede
  Anheftung nimmt Google eine Kombination und senkt die Anzeigenstärke.
  Anheften nur, wo etwas an erster Stelle stehen muss.
- Texte enthalten **keine erfundenen Angaben**: keine Preise, Fristen,
  Garantien, Auszeichnungen oder Bestände, die nicht belegt sind. Alle
  Angaben kommen von der Website oder vom Kontoinhaber.
- Keine Ausrufezeichen in Überschriften, keine Versalien, keine doppelten
  Leerzeichen — Google lehnt das ab.
- Der `finalUrls`-Eintrag zeigt auf die Seite, die zum Keyword passt,
  nicht auf die Startseite.

## Weitere häufige Operationen

**Gebotsanpassung für Geräte** (Handy 20 Prozent höher):

```json
[{"campaignBidModifierOperation": {"create": {
  "campaign": "customers/1234567890/campaigns/456",
  "device": {"type": "MOBILE"},
  "bidModifier": 1.2
}}}]
```

**Gemeinsame Ausschlussliste anlegen und der Kampagne zuweisen:**

```json
[
  {"sharedSetOperation": {"create": {
    "resourceName": "customers/1234567890/sharedSets/-1",
    "name": "Kontoweite Ausschlüsse",
    "type": "NEGATIVE_KEYWORDS"
  }}},
  {"sharedCriterionOperation": {"create": {
    "sharedSet": "customers/1234567890/sharedSets/-1",
    "keyword": {"text": "gratis", "matchType": "PHRASE"}
  }}},
  {"campaignSharedSetOperation": {"create": {
    "campaign": "customers/1234567890/campaigns/456",
    "sharedSet": "customers/1234567890/sharedSets/-1"
  }}}
]
```

**Zeitplan** (Montag bis Freitag, 8 bis 18 Uhr):

```json
[{"campaignCriterionOperation": {"create": {
  "campaign": "customers/1234567890/campaigns/456",
  "adSchedule": {
    "dayOfWeek": "MONDAY", "startHour": 8, "startMinute": "ZERO",
    "endHour": 18, "endMinute": "ZERO"
  }
}}}]
```

Ein Zeitplan wirkt einschränkend: sobald **ein** Zeitfenster gesetzt ist,
läuft die Kampagne außerhalb aller gesetzten Fenster nicht mehr. Also
alle gewünschten Tage in einem Aufruf anlegen.

## Wenn ein Feld unklar ist

`google_ads_fields` mit `name_contains` zeigt, welche Felder es gibt, ob
sie auswählbar und filterbar sind und womit sie kombiniert werden dürfen.
Die verbindliche Quelle bleibt Googles Referenz zur eingesetzten Fassung
(v25) — **nachschlagen, nicht erinnern**. Ein Feldname aus dem Gedächtnis
ist die häufigste Ursache für eine abgelehnte Operation.
