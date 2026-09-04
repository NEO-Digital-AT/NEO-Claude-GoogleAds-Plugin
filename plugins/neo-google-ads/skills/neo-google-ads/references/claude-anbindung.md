# Welcher Claude, welcher Weg

Die Werkzeuge sind in allen Fällen dieselben. Nur die Tür ist eine andere,
weil die drei Claude-Oberflächen verschieden an einen Server kommen.

| Wo | Wie | Aufwand |
| --- | --- | --- |
| **claude.ai im Browser und auf dem Handy** | `google-ads-http.py` läuft bei dir, claude.ai ruft die Adresse auf | eigener Server mit HTTPS |
| **Claude Code** | Plugin, startet den Server als lokalen Prozess | eingerichtet |
| **Claude Desktop** | derselbe lokale Prozess, in der Desktop-Konfiguration | fünf Zeilen JSON |

Der Grund für den Unterschied: Claude Code und die Desktop-App laufen auf
deinem Rechner und dürfen dort ein Programm starten. Die Weboberfläche und
die Handy-App laufen nicht bei dir — sie können nur eine Adresse aufrufen.

## claude.ai im Browser und auf dem Handy

Hier läuft nichts auf deinem Rechner. Der Server muss stehen, erreichbar
sein und sich selbst schützen. Dafür ist `google-ads-http.py` da: dieselben
Werkzeuge, dieselben Schutzgrenzen, andere Tür.

Der fertige Aufbau liegt unter `deploy/` — ein Container mit dem Server,
einer mit Caddy davor für HTTPS.

### Der Weg, von null

**Voraussetzung:** ein VPS mit Docker, und ein DNS-Eintrag, der auf ihn
zeigt. Caddy holt das Zertifikat erst, wenn die Adresse aufgelöst wird.

```bash
# 1. Auf dem VPS
git clone https://github.com/NEO-Digital-AT/NEO-Claude-GoogleAds-Plugin
cd NEO-Claude-GoogleAds-Plugin/deploy

# 2. Zugangsdaten und Grenzen eintragen
cp .env.example .env
nano .env                 # der Block aus: google-ads-auth.py --env
chmod 600 .env

# 3. Datenverzeichnis anlegen. Der Container läuft als UID 10001 und
#    braucht Schreibrecht darauf — sonst startet er und kann nichts ablegen.
mkdir -p data && sudo chown 10001:10001 data

# 4. Adresse eintragen
nano Caddyfile            # erste Zeile: die eigene Adresse

# 5. Starten
docker compose up -d --build
docker compose logs -f google-ads-mcp
```

Beim ersten Start erzeugt der Server ein Zugangswort in `data/http-token`,
falls keines da ist. Sichtbar machen:

```bash
docker compose exec google-ads-mcp cat /data/http-token
```

Prüfen, ob die Strecke steht — von einem beliebigen Rechner:

```bash
curl https://ads.mcp.neo-digital.at/health
```

Antwortet `{"status": "ok", ...}`, ist alles bereit. Der Pfad verrät nichts
über die Konten, nur dass ein Server da ist.

### In claude.ai eintragen

1. **Einstellungen → Connectors → Benutzerdefinierten Connector hinzufügen**
2. Adresse: `https://ads.mcp.neo-digital.at/mcp`
3. Als Kopfzeile: `Authorization: Bearer <das Zugangswort>`

### Wie der Aufbau sich schützt

| Riegel | Wirkung |
| --- | --- |
| Zugangswort | 64 Zeichen, in konstanter Zeit verglichen. Ohne es: 401 und sonst nichts |
| `--anthropic-only` | Nur Aufrufe aus Anthropics veröffentlichtem Ausgangsbereich. Ein erratenes Wort nützt von woanders nichts |
| Vertrauensgrenze für Proxys | `X-Forwarded-For` wird **nur** geglaubt, wenn die Verbindung selbst von einer privaten Adresse kommt. Sonst könnte jeder sich per Kopfzeile als Anthropic ausgeben |
| Kein Port nach außen | Der Server hat in `docker-compose.yml` kein `ports:` — nur Caddy erreicht ihn |
| Nicht als root | Der Container läuft als UID 10001 |
| Rumpfgrenze | Ein Aufruf über einer Million Zeichen wird ungelesen abgewiesen |

Steht ein anderer Proxy davor als der aus dem Compose-Aufbau, muss er die
echte Absenderadresse als `X-Forwarded-For` weitergeben, und seine eigene
Adresse muss privat sein oder über `--trusted-proxy` genannt werden.

### Bereitstellung über Plesk

Plesk kann bei jedem Push neu ausrollen. Vier Eigenheiten stehen dem im
Weg, und `deploy/plesk-deploy.sh` nimmt sie alle vier:

| Eigenheit | Folge |
| --- | --- |
| **Jede Zeile im Feld „Bereitstellungsaktionen" läuft in einer eigenen Shell** | Eine Variable aus Zeile 1 gibt es in Zeile 2 nicht. `cd` wirkt nicht weiter, `set -e` schützt nur seine Zeile. Deshalb steht alles in einer Datei und im Feld nur ihr Aufruf. |
| **Der Agent hat einen kargen PATH** | `docker` allein wird nicht gefunden. Das Skript sucht es unter den bekannten Pfaden. |
| **Der Abo-Benutzer darf kein Docker** | Das Skript versucht es direkt, dann über `sudo -n`, und druckt bei Fehlschlag die fertige sudoers-Regel. |
| **Ohne echten Shell-Zugang läuft alles in einer Chroot-Jail** | Dort ist Docker nicht erreichbar. In Plesk unter Webhosting-Zugriff `/bin/bash` einstellen, nicht die chrooted-Variante. |

Ins Feld **Bereitstellungsaktionen** kommt genau eine Zeile:

```
/bin/bash /var/www/vhosts/<domain>/<verzeichnis>/deploy/plesk-deploy.sh
```

**Docker-Rechte: nicht über die Gruppe.** Der verbreitete Rat lautet
`usermod -aG docker <benutzer>`. Wer Docker steuern darf, kann jedes
Verzeichnis des Wirts in einen Container einhängen — das ist root mit
anderem Namen, und auf einem Plesk-Server mit Kundendomains eine schlechte
Idee. Eine sudo-Regel für genau zwei Befehle reicht; das Skript druckt sie
aus, wenn sie fehlt.

`.env` und `data/` kommen **nicht** über Git — sie stehen in der
`.gitignore`. Einmal von Hand anlegen, danach überstehen sie jede
Bereitstellung.

Das Skript endet mit einem Fehler, wenn der Server nicht antwortet, und
legt die letzten Protokollzeilen ins Plesk-Protokoll. Eine grüne
Bereitstellung heißt damit: der Server läuft wirklich.

### Sichern

Zwei Dinge im `data/`-Verzeichnis sind es wert:

- `config.json` bzw. die `.env` — sonst ist die Einrichtung erneut fällig.
- `changes.jsonl` — das Änderungsprotokoll. Es ist die Antwort auf „wer
  hat das geändert und warum", und ein Container ist schnell neu gebaut.

### Aktualisieren

```bash
git pull && docker compose up -d --build
```

Die Zugangsdaten liegen im gemounteten `data/` und in der `.env`, nicht im
Image — ein Neubau verliert nichts.

## Claude Desktop

Der stdio-Server, den Claude Code startet, ist derselbe, den die Desktop-App
starten kann. Es ist keine Änderung nötig, nur ein Eintrag.

Datei anlegen oder ergänzen:

```
Windows   %APPDATA%\Claude\claude_desktop_config.json
macOS     ~/Library/Application Support/Claude/claude_desktop_config.json
```

```json
{
  "mcpServers": {
    "neo-google-ads": {
      "command": "python",
      "args": ["C:\\Pfad\\zu\\scripts\\google-ads-mcp.py"],
      "env": {
        "PYTHONUNBUFFERED": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONIOENCODING": "utf-8"
      }
    }
  }
}
```

- Unter Windows `"python"`, unter macOS und Linux `"python3"`. Die Regel ist
  dieselbe wie in `einrichtung.md`.
- Der Pfad muss **absolut** sein. In JSON werden Backslashes verdoppelt.
- Claude Desktop danach **vollständig beenden** und neu starten — das
  Schließen des Fensters genügt nicht, das Programm läuft im Infobereich
  weiter.
- Die Zugangsdaten kommen aus derselben Datei wie bei Claude Code. Wer
  `google-ads-auth.py` schon durchlaufen hat, ist fertig.

Danach erscheinen die dreizehn Werkzeuge im Werkzeugmenü der Desktop-App.

## Was du in welcher Oberfläche tust

Die Regeln des Skills gelten überall gleich: messen, Plan vorlegen,
Freigabe abwarten, Trockenlauf, umsetzen, belegen. Praktisch verteilt es
sich so:

| Aufgabe | Wo es sich anbietet |
| --- | --- |
| Kampagnen und Suchbegriffe ansehen, Fragen stellen | claude.ai, auch vom Handy |
| Auswertung mit einer Website zusammen, Berichte schreiben | Claude Code |
| Änderungen umsetzen | dort, wo die Schutzgrenzen gesetzt sind — in der Regel lokal |

## Schreiben aus dem Browser: zwei Ebenen, nicht eine

Der häufigste Denkfehler ist, den Schreibschalter für die Freigabe zu
halten. Er ist es nicht. Es sind zwei Ebenen, und beide müssen zutreffen.

**Ebene 1, einmal, in der `.env`: was überhaupt möglich ist.**
`GOOGLE_ADS_ALLOW_WRITE=true` öffnet den Weg. Die Kontoliste sagt, in
welche Konten geschrieben werden darf, der Budgetdeckel, wie hoch ein
Tagesbudget höchstens gesetzt werden kann, der Steigerungsfaktor, wie weit
es in einem Schritt springen darf. Das ist der Rahmen, und er wird nicht
im Gespräch verschoben — passt eine Maßnahme nicht hindurch, wird die
Maßnahme vorgelegt, nicht die Grenze.

**Ebene 2, jedes Mal, im Gespräch: ob genau diese Änderung jetzt passiert.**
Jeder Schreibaufruf ist zuerst ein Trockenlauf. Der Agent misst, legt einen
Plan vor und wartet. Erst wenn du zustimmst, läuft derselbe Aufruf scharf.
Ohne deine Zustimmung passiert nichts — auch bei eingeschaltetem Schalter,
auch wenn der Vorschlag offensichtlich richtig ist.

So sieht das aus:

```
Du     Die Anzeigen in der Kampagne X laufen schlecht, schau dir das an
Claude [misst] Drei Befunde. Vorschlag: zwei Überschriften ergänzen,
       ein Keyword pausieren, sechs Suchbegriffe ausschließen.
       [Trockenlauf] Google nimmt alle drei an. Nichts wurde geändert.
Du     Mach 1 und 3, 2 lass noch
Claude [setzt 1 und 3 scharf um, liest nach, zeigt den neuen Zustand]
```

Der Trockenlauf ist dabei mehr als eine Höflichkeit: er schickt die
Operation durch Googles vollständige Regelprüfung. Ein Anzeigentext, der
zu lang ist, ein Keyword mit falschem Übereinstimmungstyp, ein Budget über
dem Deckel — all das fällt auf, bevor du zustimmst.

Ein Server, der nur liest, ist trotzdem eine überlegenswerte Wahl für den
Browser: Analysieren geht damit vollständig, und der schreibende Zugang
bleibt dort, wo du am Rechner sitzt.
