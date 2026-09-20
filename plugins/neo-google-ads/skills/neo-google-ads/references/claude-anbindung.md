# Welcher Claude, welcher Weg

Die Werkzeuge sind in allen Fällen dieselben. Nur die Tür ist eine andere,
weil die drei Claude-Oberflächen verschieden an einen Server kommen.

| Wo | Wie | Aufwand |
| --- | --- | --- |
| **claude.ai im Browser und auf dem Handy** | `google-ads-http.py` läuft bei dir, claude.ai ruft die Adresse auf | eigener Server mit HTTPS |
| **Claude Code** | Plugin, ruft denselben Server über HTTP auf | Adresse und Zugangswort |
| **Claude Desktop** | lokaler Prozess, in der Desktop-Konfiguration | fünf Zeilen JSON |

Claude Code könnte beides — ein Programm starten oder eine Adresse
aufrufen. Dieses Plugin nimmt die Adresse, damit Schutzgrenzen, Kontenliste
und Änderungsprotokoll an einer einzigen Stelle liegen und nicht zweimal
gepflegt werden müssen. Die Desktop-App startet den Server als lokalen
Prozess; die Weboberfläche und die Handy-App laufen nicht bei dir und
können ohnehin nur eine Adresse aufrufen.

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

# 2. Zugangsdaten, Grenzen und das erste Portal-Konto eintragen
cp .env.example .env
nano .env                 # INIT_USER und INIT_PASS setzen; die Google-Daten
                          # entweder hier oder später im Portal
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

Beim ersten Start legt der Server das Portal-Konto aus `INIT_USER` und
`INIT_PASS` an und erzeugt ein Zugangswort in `data/http-token`, falls
keines da ist. Das Zugangswort ist für claude.ai, nicht für die Anmeldung. **Über Plesk steht es am Ende des
Bereitstellungsprotokolls**, zusammen mit der Adresse der Verwaltung und
der MCP-Adresse — es dafür über SSH zu holen ist ein Schritt, den niemand
gehen sollte: wer das Protokoll lesen kann, erreicht den Server ohnehin.

Ohne Plesk:

```bash
docker compose exec google-ads-mcp cat /data/http-token
```

Prüfen, ob die Strecke steht — von einem beliebigen Rechner:

```bash
curl https://ads.mcp.neo-digital.at/health
```

Antwortet `{"status": "ok", ...}`, ist alles bereit. Der Pfad verrät nichts
über die Konten, nur dass ein Server da ist.

### Die Verwaltungskonsole

Unter `/setup` liegt die Konsole. Sie zeigt den Status der Verbindung, die
Konten mit Namen und Währung, die Zugriffsstufe des Developer Tokens, die
Schutzgrenzen und die letzten Einträge des Änderungsprotokolls.

Sie ist nicht nur für den ersten Tag. Alles, was später anfällt, geht dort
ohne SSH und ohne Handgriff an der `.env`:

| Was | Wo |
| --- | --- |
| Zugangsdaten eintragen oder ändern | Zugangsdaten bearbeiten |
| Verbinden, neu verbinden, neu genehmigen | Mit Google verbinden |
| Weitere Konten zum Schreiben berechtigen | Schutzgrenzen bearbeiten |
| Budgetdeckel, Sprungfaktor, Operationen je Aufruf | Schutzgrenzen bearbeiten |
| Schreiben ein- und ausschalten | Schutzgrenzen bearbeiten |
| Verbindung trennen | Refresh Token löschen |
| Zugangswort wechseln | Zugangswort wechseln |
| Verbindung prüfen | Verbindung prüfen |

**Konten werden angehakt, nicht getippt.** Unter *Schutzgrenzen bearbeiten*
steht jedes zugängliche Konto mit Name, Währung und Kontonummer als
Kästchen. Kommt ein Kundenkonto dazu, genügt ein Haken. Eine Nummer von
Hand einzutragen ist nirgends nötig.

Zwei Dinge macht die Seite bewusst nicht:

- **Was in der `.env` steht, zeigt sie gesperrt** und schreibt die
  Variable dazu. Die Umgebung gewinnt gegen die Datei; ein Feld, dessen
  Änderung nie greifen würde, nimmt die Seite gar nicht erst an.
- **Was sie nicht anzeigen kann, ändert sie nicht.** Lässt sich die
  Kontenliste gerade nicht lesen, hieße „kein Kästchen angehakt“ sonst
  „alle Konten erlaubt“ — die weiteste Einstellung, erreicht durch eine
  Störung. Stattdessen sagt die Seite, dass die Liste fehlt, zeigt die
  berechtigten Nummern an und lässt die Berechtigung beim Speichern
  unberührt.

### Anmeldung, Konto und zweiter Faktor

Das Portal hat eigene Benutzerkonten. Sie liegen in `data/portal.db`
(SQLite), nicht in der `.env`.

**Das erste Konto** legt der Container beim allerersten Start an, aus
`INIT_USER` und `INIT_PASS` in der `.env`. Danach werden die beiden Zeilen
nicht mehr gelesen — ein vorhandenes Konto wird nie überschrieben oder
wiederhergestellt. Weil das Kennwort dort im Klartext steht, verlangt das
Portal bei der ersten Anmeldung sofort ein neues und zeigt vorher nichts
anderes an. Danach können beide Zeilen aus der `.env` verschwinden.

Fehlen sie, legt der erste Start ein Konto `admin` mit einem zufälligen
Kennwort an und schreibt es ins Bereitstellungsprotokoll.

**Unter /account** lässt sich alles ändern, was zum Konto gehört:
Benutzername, E-Mail, Kennwort. Ein Kennwortwechsel beendet auf Wunsch
alle anderen Sitzungen; der Browser, in dem gewechselt wurde, bleibt
angemeldet. Darunter stehen die angemeldeten Browser mit Zeitpunkt und
Adresse, samt Schalter, alle anderen abzumelden.

**Passkeys** stehen dort ebenfalls: ein Gerät anmelden, benennen, fertig. Der private Schlüssel bleibt auf dem Gerät, der Server kennt nur den öffentlichen Teil und prüft damit die Unterschrift. Ein Passkey ersetzt Kennwort und Code zusammen, weil das Gerät vorher selbst nach Finger, Gesicht oder PIN fragt.

**Zwei-Faktor** wird dort eingeschaltet: QR-Code scannen, einen Code
eingeben, fertig. Erst der bestätigte Code schaltet ihn scharf — ein
Geheimnis, das nie bewiesen wurde, sperrt sonst nur aus. Danach erscheinen
einmalig zehn Wiederherstellungscodes. Jeder gilt genau einmal und ersetzt
den Code aus der App.

Der QR-Code wird auf dem Server gezeichnet, ohne Fremdbibliothek und ohne
externen Dienst: das Geheimnis verlässt die Maschine nicht. Wer keine
Kamera hat, tippt den Schlüssel ab — er steht daneben.

Es gilt jede App, die TOTP kann: Google Authenticator, Aegis, 1Password,
Bitwarden.

**Ein Code gilt einmal.** Wer sich anmeldet und dreißig Sekunden später
noch einmal, braucht den nächsten Code. Das ist kein Fehler, sondern der
Schutz davor, dass ein abgefangener Code ein zweites Mal wirkt.

**Nach acht Fehlversuchen** ist fünfzehn Minuten Ruhe, gezählt nach Adresse
und nach Benutzername.

### Ausgesperrt

Es gibt keinen Versand per E-Mail und kein „Kennwort vergessen“ im
Browser. Dieser Server verschickt nichts, und ein Rücksetzlink im Postfach
wäre ein weiterer Weg hinein. Wer an den Server kommt, kommt an die
Datenbank — dort wird zurückgesetzt:

```bash
cd /var/www/vhosts/ads.mcp.neo-digital.at/git/ads.mcp/deploy
docker compose -f docker-compose.plesk.yml exec google-ads-mcp \
    python3 /app/scripts/google-ads-http.py --list-users
```

| Befehl | Wofür |
| --- | --- |
| `--list-users` | Welche Konten es gibt, ob 2FA an ist, letzte Anmeldung |
| `--add-user NAME` | Ein weiteres Konto anlegen, fragt nach dem Kennwort |
| `--set-password NAME` | Kennwort setzen, beendet alle Sitzungen, hebt die Sperre auf |
| `--disable-2fa NAME` | Zweiten Faktor abschalten — für das verlorene Telefon |

Alle vier fragen Kennwörter verdeckt ab und schreiben sie nirgends hin.

### In claude.ai eintragen

1. **Einstellungen → Connectors → Benutzerdefinierten Connector hinzufügen**
2. Adresse: `https://ads.mcp.neo-digital.at/mcp`
3. Als Kopfzeile: `Authorization: Bearer <das Zugangswort>`

Das Zugangswort entsteht beim **ersten** Start, liegt in `data/http-token`
und bleibt dort. Eine Bereitstellung erzeugt **kein** neues: das
Verzeichnis ist gemountet, der Server findet das vorhandene und lässt es in
Ruhe.

Wechseln lässt es sich im Portal unter **Übersicht → Zugangswort für
claude.ai wechseln**. Das alte gilt dann sofort nicht mehr, und der
Connector ist neu einzutragen. Die Portal-Konten bleiben davon unberührt.

Vergessen kann man es nicht: es steht in `data/http-token` auf dem Server.

### Eigenes Logo

Eine Datei `logo.svg` in das Datenverzeichnis legen
(`deploy/data/logo.svg`), dann steht sie statt der eingebauten Wortmarke im
Kopf. Nimmt das SVG `fill="currentColor"`, übernimmt es die Akzentfarbe der
Seite.

### Die Adresse festnageln

In die `.env` gehört:

```
GOOGLE_ADS_PUBLIC_URL=https://ads.mcp.neo-digital.at
```

Ohne diese Zeile leitet der Server seine eigene Adresse aus den Köpfen des
Reverse Proxys ab. **Plesks Docker-Proxy-Regeln schicken kein
`X-Forwarded-Proto`**, dann hält sich der Server für `http://…` — und
daraus folgen zwei Fehler: die Rückadresse für OAuth ist falsch, und der
Sitzungskeks bekommt kein `Secure`. Mit der Zeile ist nichts geraten.

Wer stattdessen die nginx-Direktiven von Hand einträgt (siehe unten), hat
das Problem nicht — aber die Zeile schadet auch dann nicht.

### Zwei Türen, zwei Schlüssel

| Tür | Wer | Womit |
| --- | --- | --- |
| `/login` | ein Mensch | Benutzerkonto, Kennwort, wahlweise zweiter Faktor — oder ein Passkey, der beides in einem Schritt ersetzt |
| `/mcp` | claude.ai | ein festes Zugangswort als `Authorization: Bearer` |

Das ist Absicht. claude.ai kann kein Formular ausfüllen und keinen Code aus
einer App eingeben — der Connector braucht ein Wort, das bleibt. Ein Mensch
kann beides, und soll es auch. Keiner der beiden Schlüssel öffnet die
andere Tür: ein Wechsel des Zugangsworts rührt die Konten nicht an, ein
Kennwortwechsel stört den Connector nicht.

Deshalb gilt `--anthropic-only` auch nur für `/mcp`. Es würde sonst den
Betreiber vom eigenen Portal aussperren, weil der nicht aus Anthropics
Adressbereich kommt.

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

**Kein Caddy auf einem Plesk-Server.** Plesks nginx belegt bereits Port 80
und 443, und Plesk verwaltet für die Domain schon ein Let's-Encrypt-
Zertifikat. Ein zweiter Webserver im Container streitet nur mit ihm um die
Ports. Dafür liegt `docker-compose.plesk.yml` daneben: derselbe Server,
ohne Caddy, gebunden an `127.0.0.1:8788`. Das Bereitstellungsskript nimmt
sie automatisch, wo sie liegt — es ist nichts umzustellen.

Durchgereicht wird über Plesk: **Domain → Apache & nginx → Zusätzliche
nginx-Direktiven**:

```nginx
location / {
    proxy_pass http://127.0.0.1:8788;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;

    # Die echte Absenderadresse, nicht die angehängte Kette. Ohne sie
    # kann der Server --anthropic-only nicht anwenden und sieht nur nginx.
    proxy_set_header X-Forwarded-For $remote_addr;

    # claude.ai lässt einem Aufruf bis zu fünf Minuten Zeit.
    proxy_read_timeout 300s;
    proxy_send_timeout 300s;
    proxy_buffering off;
}
```

Das Zertifikat holt Plesk unter **SSL/TLS-Zertifikate → Let's Encrypt**.
Erst danach ist die Adresse über https erreichbar.

Ins Feld **Bereitstellungsaktionen** kommt genau eine Zeile:

```
/bin/bash /var/www/vhosts/<domain>/<verzeichnis>/deploy/plesk-deploy.sh
```

**Die Probe muss der Befehl sein, der später läuft.** Zwei Fallen liegen
hier dicht beieinander: Wer mit `docker info` prüft und danach
`docker compose` ausführt, bringt eine korrekt eingegrenzte sudo-Regel zu
Fall — sie erlaubt compose, nicht info, und die Probe scheitert, bevor
irgendetwas versucht wird. Wer mit `docker compose version` prüft, beweist
nur, dass der Client da ist; den Dienst berührt der Befehl nicht. Das
Skript nimmt `docker compose ps`: braucht den Dienst, und die Regel deckt
es ab.

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

Drei Dinge im `data/`-Verzeichnis sind es wert:

- `config.json` bzw. die `.env` — sonst ist die Einrichtung erneut fällig.
- `portal.db` — die Konten samt Zwei-Faktor. Ohne sie ist der erste
  Start wieder der erste Start: das Konto käme erneut aus `INIT_USER`,
  und jeder zweite Faktor wäre neu einzurichten.
- `changes.jsonl` — das Änderungsprotokoll. Es ist die Antwort auf „wer
  hat das geändert und warum", und ein Container ist schnell neu gebaut.

`portal.db` enthält Kennwort-Prüfsummen und die Zwei-Faktor-Geheimnisse.
Eine Sicherung davon ist so schützenswert wie die `.env`.

### Aktualisieren

```bash
git pull && docker compose up -d --build
```

Die Zugangsdaten liegen im gemounteten `data/` und in der `.env`, nicht im
Image — ein Neubau verliert nichts.

## Claude Code

Claude Code spricht denselben Server an wie claude.ai. Im Plugin steht
dafür nur noch die Adresse und das Zugangswort:

```json
{
  "mcpServers": {
    "neo-google-ads": {
      "type": "http",
      "url": "${GOOGLE_ADS_MCP_URL:-https://ads.mcp.neo-digital.at/mcp}",
      "headers": {
        "Authorization": "Bearer ${GOOGLE_ADS_MCP_TOKEN}"
      }
    }
  }
}
```

Zwei Umgebungsvariablen entscheiden, wohin es geht:

| Variable | Pflicht | Wofür |
| --- | --- | --- |
| `GOOGLE_ADS_MCP_TOKEN` | ja | Das Zugangswort aus `data/http-token`. Ohne es kommt 401 und sonst nichts |
| `GOOGLE_ADS_MCP_URL` | nein | Eine andere Adresse als `https://ads.mcp.neo-digital.at/mcp` — ein zweiter Server, ein Testaufbau |

**Das Zugangswort gehört nicht ins Repository.** Es steht in der Umgebung,
nicht in der `.mcp.json` — diese Datei ist öffentlich.

macOS und Linux, in `~/.zshrc` bzw. `~/.bashrc`:

```bash
export GOOGLE_ADS_MCP_TOKEN='<das Zugangswort>'
```

Windows, in den Benutzervariablen (Einstellungen → System → Info →
Erweiterte Systemeinstellungen → Umgebungsvariablen):

```
GOOGLE_ADS_MCP_TOKEN=<das Zugangswort>
```

Claude Code danach neu starten — Umgebungsvariablen werden beim Start
gelesen. Ob die Strecke steht, sagt:

```bash
claude mcp list
```

Dort muss `neo-google-ads` mit `✓ Connected` stehen.

Was damit entfällt: Python auf dem Rechner, der Durchlauf von
`google-ads-auth.py`, die Zugangsdaten in `~/.config/neo-google-ads/`. Das
liegt jetzt alles auf dem Server, und die Schutzgrenzen gelten für jede
Oberfläche gleich. Wer den lokalen Prozess trotzdem will, findet ihn im
nächsten Abschnitt — dieselbe Datei, andere Tür.

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
