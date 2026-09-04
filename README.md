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

| Grenze | Ab Werk | Wirkung | Umgebungsvariable |
| --- | --- | --- | --- |
| `write_enabled` | **aus** | Ohne diesen Schalter geht kein scharfer Schreibvorgang durch | `GOOGLE_ADS_ALLOW_WRITE` |
| `allowed_customer_ids` | leer | Begrenzt, in welche Konten geschrieben werden darf | `GOOGLE_ADS_ALLOWED_CUSTOMER_IDS` |
| `max_daily_budget_micros` | 0 | Obergrenze je Tagesbudget | `GOOGLE_ADS_MAX_DAILY_BUDGET` (in Währung) |
| `max_budget_increase_factor` | 3.0 | Größter Sprung in einem Schritt | `GOOGLE_ADS_MAX_BUDGET_INCREASE_FACTOR` |

Sie stehen in der Konfigurationsdatei oder in der Umgebung — ein Container
hat keine Datei zum Bearbeiten, und ein schreibender Server ohne Kontoliste
und Budgetdeckel ist genau das, was diese Grenzen verhindern sollen.

Jeder Versuch — Trockenlauf eingeschlossen — steht mit Zeitstempel,
Konto, Begründung und Ergebnis im Änderungsprotokoll.

## In welchem Claude

Die Werkzeuge sind überall dieselben, nur die Tür ist eine andere.

| Wo | Wie |
| --- | --- |
| **Claude Code** | Plugin installieren, Server läuft als lokaler Prozess |
| **Claude Desktop** | derselbe Prozess, fünf Zeilen in `claude_desktop_config.json` |
| **claude.ai im Browser und am Handy** | `docker compose up` aus `deploy/` auf einem VPS, als Connector eingetragen |

Der Grund: Claude Code und die Desktop-App laufen auf deinem Rechner und
dürfen dort ein Programm starten. Browser und Handy können nur eine
Adresse aufrufen — dafür ist der HTTP-Weg da, mit Zugangswort und
optionalem Adressfilter auf Anthropics veröffentlichten Bereich.

Der vollständige Weg für alle drei steht in
`plugins/neo-google-ads/skills/neo-google-ads/references/claude-anbindung.md`.

Für den Browser liegt der Aufbau fertig unter `deploy/`: ein Container mit
dem Server, einer mit Caddy für HTTPS, eine `.env` für Zugangsdaten und
Schutzgrenzen. Der Server hat kein `ports:` — erreichbar ist er nur durch
Caddy.

```bash
cp .env.example .env && nano .env
mkdir -p data && sudo chown 10001:10001 data
docker compose up -d --build
```

Wer über Plesk ausrollt: `deploy/plesk-deploy.sh` nimmt dessen vier
Eigenheiten ab — jede Zeile im Aktionsfeld läuft in einer eigenen Shell,
der Agent hat einen kargen PATH, der Abo-Benutzer darf kein Docker, und
ohne echten Shell-Zugang steckt alles in einer Chroot-Jail. Ins Feld
kommt eine Zeile, der Rest steht in der Datei. Auf einem Plesk-Server entfällt Caddy — `docker-compose.plesk.yml` bindet an 127.0.0.1, und Plesks nginx reicht mit seinem eigenen Zertifikat durch.

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
| `google-ads-http.py` | Derselbe MCP-Server über Streamable HTTP, damit claude.ai im Browser und am Handy ihn als Connector erreichen kann. Zugangswort mit `--new-token`, `--anthropic-only` lässt nur Aufrufe aus Anthropics veröffentlichtem Adressbereich durch. TLS gehört vor den Prozess, in einen Reverse Proxy. |
| `google-ads-auth.py` | Verbinden über OAuth mit PKCE. `--paste-url` für Maschinen ohne Browser, `--allow-write` setzt die Schutzgrenzen, `--show` zeigt den Stand ohne Geheimnisse, `--env` gibt sie als Übergabeblock für eine Cloud-Sitzung aus. |
| `google-ads-check.py` | Misst die Verbindung in acht Prüfungen. Prüfung 7 verrät die Zugriffsstufe, die die API nie ausspricht — ein Explorer-Token hat die Planungswerkzeuge gesperrt. Prüfung 8 ist ein Trockenlauf gegen das echte Konto, der nichts verändert. Jede fehlgeschlagene Prüfung nennt die Abhilfe. |
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
