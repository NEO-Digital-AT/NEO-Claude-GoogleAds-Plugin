# NEO-Claude-GoogleAds-Plugin

Google Ads für Claude Code: lesender und schreibender Zugriff über einen
mitgelieferten MCP-Server, dazu die Arbeitsregeln, nach denen geschrieben
werden darf.

Ein Marktplatz mit einem Plugin. Getrennt von
[NEO-Claude-Plugins](https://github.com/NEO-Digital-AT/NEO-Claude-Plugins),
weil es etwas anderes ist: die dortigen Plugins beschreiben Arbeitsregeln,
dieses führt Änderungen an Werbekonten aus.

## Was es kann

**Lesen** — sechs Werkzeuge: zugängliche Konten, siebzehn vorbereitete
Berichte (Kampagnen, Anzeigengruppen, Keywords mit Qualitätsfaktor,
Suchbegriffe, ausschließende Keywords auf drei Ebenen, Anzeigen, Budgets,
Landingpages, Geräte, Regionen, Tageszeiten, Conversion-Aktionen, Googles
Empfehlungen, Änderungsverlauf, Kontoeinstellungen), freie GAQL-Abfragen,
Feldkatalog, Keyword-Planer, Suchvolumen.

**Schreiben** — sechs Werkzeuge: Keywords, ausschließende Keywords,
Status, Budgets, Gebote, und der rohe Mutate-Endpunkt für alles Übrige
(neue Kampagnen, Anzeigen, Gebotsanpassungen, gemeinsame Listen).

**Belegen** — ein Werkzeug: das Änderungsprotokoll.

## Schreiben ist ein Verfahren, kein Aufruf

```
messen -> Plan vorlegen -> Freigabe abwarten -> Trockenlauf -> umsetzen -> belegen
```

Jeder Schreibaufruf ist **zuerst ein Trockenlauf** gegen Googles eigene
Regelprüfung und verändert nichts. Scharf wird er nur mit ausdrücklicher
Angabe.

Darunter sitzen vier Schutzgrenzen im Werkzeug, nicht in der Absicht:

| Grenze | Ab Werk | Wirkung |
| --- | --- | --- |
| `write_enabled` | **aus** | Ohne diesen Schalter geht kein scharfer Schreibvorgang durch |
| `allowed_customer_ids` | leer | Begrenzt, in welche Konten geschrieben werden darf |
| `max_daily_budget_micros` | 0 | Obergrenze je Tagesbudget |
| `max_budget_increase_factor` | 3.0 | Größter Sprung in einem Schritt |

Jeder Versuch — Trockenlauf eingeschlossen — steht mit Zeitstempel,
Konto, Begründung und Ergebnis im Änderungsprotokoll.

## Installation

```
/plugin marketplace add NEO-Digital-AT/NEO-Claude-GoogleAds-Plugin
/plugin install neo-google-ads@neo-claude-googleads
```

Danach einmalig verbinden:

```bash
python3 <plugin>/scripts/google-ads-auth.py
python3 <plugin>/scripts/google-ads-check.py
```

Der vollständige Weg mit allen Voraussetzungen steht in
`plugins/neo-google-ads/skills/neo-google-ads/references/einrichtung.md`
— einschließlich der Abschnitte für **Windows** und **Claude Code im
Browser**, die beide Eigenheiten haben.

### Was Google verlangt

Zwei Dinge stellt Google einer namentlich bekannten Person aus. Kein
Skript kann sie erzeugen, und **jeder** eigene Google-Ads-Zugang braucht
sie — auch Googles eigener MCP-Server:

| Was | Woher | Dauer |
| --- | --- | --- |
| OAuth-Client (ID und Geheimnis) | Google Cloud Console, Typ Desktop-App | 10 Minuten |
| Developer Token | API Center eines **Manager-Kontos** | sofort bis 10 Werktage |

Der Developer Token hat vier Stufen. **Explorer** wird oft ohne Wartezeit
vergeben und arbeitet an echten Konten, sperrt aber die Planungswerkzeuge
— der Keyword-Planer läuft damit nicht. Für ihn und für mehr als 2.880
Operationen am Tag braucht es **Basic**.

## Werkzeuge

Alle laufen ohne Abhängigkeiten und taugen als Tor in einer CI.

| Werkzeug | Wofür |
| --- | --- |
| `google-ads-mcp.py` | Der MCP-Server. Dreizehn Werkzeuge über die REST-Schnittstelle der Google Ads API v25. Spricht beide MCP-Fassungen — `initialize` und `server/discover`. `--list-tools` und `--check-config` zur Diagnose. |
| `google-ads-auth.py` | Verbinden über OAuth mit PKCE. `--paste-url` für Maschinen ohne Browser, `--allow-write` setzt die Schutzgrenzen, `--show` zeigt den Stand ohne Geheimnisse, `--env` gibt sie als Übergabeblock für eine Cloud-Sitzung aus. |
| `google-ads-check.py` | Misst die Verbindung in sieben Prüfungen, mit `--customer-id` als achte einen Trockenlauf gegen das echte Konto. Jede fehlgeschlagene Prüfung nennt die Abhilfe. |
| `google-ads-selftest.py` | Weist ohne Netz und ohne Zugangsdaten nach, dass die Handbremse hält: 35 Fälle in sechs Gruppen. Gegen sabotierte Fassungen geprüft — jede fiel auf. |

## Regeln

Der Skill `neo-google-ads` legt fest, wie gearbeitet wird: acht Blocker
ohne Freigabeweg, fünf Kontextfragen, deren Antworten in keinem Konto
stehen, Regeln für Kundenkonten und eine Abnahmeliste.

| Datei | Inhalt |
| --- | --- |
| `references/einrichtung.md` | Zugang, Developer Token, Windows, Claude Code im Browser, Fehlerbilder |
| `references/analyse.md` | Die siebzehn Berichte, was sie beantworten, in welcher Reihenfolge |
| `references/aenderungen.md` | Aufbau des Plans, Trockenlauf, Umsetzung, Rücknahme |
| `references/keywords.md` | Übereinstimmungstypen, ausschließende Keywords, Suchbegriffe |
| `references/kampagnenbau.md` | Neue Kampagnen und Anzeigen über den Mutate-Endpunkt |
| `references/gaql.md` | GAQL: Aufbau, Segmente, Fallen |
| `references/sicherheit.md` | Schutzgrenzen, Zugangsdaten, Datenschutz, Protokoll |

Dazu drei Befehle — `/neo-google-ads:neo-adseinrichtung`,
`/neo-google-ads:neo-adsanalyse`, `/neo-google-ads:neo-adsoptimierung` —
und der Fachagent `ads-betreuung`.

## Prüfen

```bash
python3 plugins/neo-google-ads/scripts/google-ads-selftest.py
```

Läuft ohne Netz und ohne Zugangsdaten. Exit 0, wenn alle Fälle bestehen.
