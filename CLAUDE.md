# NEO-Claude-GoogleAds-Plugin

Betriebsart: Regelwerk und Werkzeug (Claude-Code-Marktplatz mit einem Plugin)
Stack: Markdown, Python 3 (Standardbibliothek)
Sprachen: Regeln deutsch, Werkzeuge englisch — siehe unten
Zweigmodell: `main` mit Arbeitszweig (kein `dev`)
Schwester-Repository: NEO-Claude-Plugins (die übrigen NEO-Regeln)

## Was hier liegt und was nicht

Dieses Repository enthält **ein** Plugin: `neo-google-ads`. Es gibt einem
Agenten lesenden und schreibenden Zugriff auf Google-Ads-Konten und die
Regeln, nach denen er das tun darf.

Es liegt getrennt von `NEO-Claude-Plugins`, weil es etwas anderes ist als
die übrigen NEO-Plugins: die beschreiben Arbeitsregeln, dieses **führt
Änderungen an fremden Werbekonten aus**. Wer es installiert, trifft eine
Entscheidung über Geld und Kundendaten, nicht über Codestil.

## Geltende Regeln

Die NEO-Kernregeln gelten, soweit sie hier greifen. Verbindlich sind:

| Skill | Wofür in diesem Projekt |
| --- | --- |
| `neo-grundregeln` | Prozess, Freigaben, Belegpflicht, Selbstkontrolle |
| `neo-code` | Aufbau und Lesbarkeit der Werkzeuge, Sprache im System |
| `neo-doku` | Trockene Sprache, IST-Zustand, keine Marketingsprache, keine Emojis |
| `neo-sicherheit` | Umgang mit Zugangsdaten, Protokollierung, Mandantentrennung |

## Besonderheiten dieses Projekts

- **Die Regeln sind deutsch, die Werkzeuge sind englisch.** Jede Datei
  unter `scripts/` hat englische Kommentare, Bezeichner, Meldungen und
  Dateinamen; jede Regeldatei ist deutsch.
- **Kein Werkzeug hat Abhängigkeiten.** Python nur Standardbibliothek.
  Jedes muss in einer fremden CI ohne Installation laufen.
- **Hier wird Geld ausgegeben.** Jede Änderung an den Schreibpfaden oder
  an den Schutzgrenzen in `google_ads_client.py` ist eine Änderung mit
  finanzieller Wirkung. Sie wird gegen `google-ads-selftest.py` geprüft,
  und der Selbsttest wird im selben Schritt erweitert, wenn eine neue
  Grenze dazukommt.
- **Ein Werkzeug gilt erst als fertig, wenn es gegen eine absichtlich
  kaputte und eine saubere Vorlage geprüft wurde** und beide das
  erwartete Ergebnis liefern. Für die Schutzgrenzen heißt das: eine
  sabotierte Fassung muss im Selbsttest auffallen. Behauptet, nicht
  gemessen, zählt nicht.
- **Die API-Fassung ist festgelegt** (`DEFAULT_API_VERSION` in
  `google_ads_client.py`). Google stellt Fassungen etwa ein Jahr nach
  Erscheinen ab; wer sie hochzieht, prüft danach mit
  `google-ads-check.py` gegen ein echtes Konto und zieht die Feldnamen
  in den vorbereiteten Berichten nach.
- **Keine Zugangsdaten im Repository.** Sie liegen unter
  `~/.config/neo-google-ads/config.json` mit Rechten 0600. Die
  `.gitignore` deckt den Fall ab, dass jemand sie hierher zeigen lässt.
- **Versionen:** Wer eine Regel oder ein Werkzeug ändert, hebt die
  Fassung in `plugins/neo-google-ads/.claude-plugin/plugin.json`. Neue
  Werkzeuge oder geänderte Schalter sind eine Nebenversion, keine
  Fehlerkorrektur. Die Beschreibung in `.claude-plugin/marketplace.json`
  wird im selben Schritt angeglichen — sie ist eine Kopie.
- **Zahlen in der Doku werden gegen den Code geprüft.** Wie viele
  Werkzeuge, wie viele Berichte, wie viele Prüfungen: steht an mehreren
  Stellen und muss überall stimmen.
