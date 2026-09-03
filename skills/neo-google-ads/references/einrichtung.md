# Zugang einrichten

Einmal pro Rechner. Danach steht der Zugang, bis das Google-Konto den
Zugriff widerruft.

## Was Google verlangt

Vier Dinge. Zwei davon stellt Google einer namentlich bekannten Person
aus, die kann kein Skript erzeugen:

| Was | Woher | Dauer |
| --- | --- | --- |
| OAuth-Client (ID und Geheimnis) | Google Cloud Console, Typ „Desktop-App" | 10 Minuten |
| Developer Token | API Center eines **Manager-Kontos** | Minuten bis Tage |
| Refresh Token | erledigt `google-ads-auth.py` im Browser | 1 Minute |
| Manager-Konto-ID | vorhanden, wenn fremde Konten betreut werden | — |

## Schritt 1: OAuth-Client

1. <https://console.cloud.google.com/apis/credentials>
2. Projekt anlegen (oder ein vorhandenes wählen).
3. Unter „APIs und Dienste" die **Google Ads API** aktivieren.
4. Zustimmungsbildschirm einrichten. Nutzertyp „Extern" genügt; solange
   die App im Testbetrieb ist, müssen die zugreifenden Google-Konten dort
   als Testnutzer eingetragen sein.
5. Anmeldedaten → Anmeldedaten erstellen → OAuth-Client-ID →
   **Desktop-App**.
6. Client-ID und Client-Geheimnis notieren.

## Schritt 2: Developer Token

1. In einem **Manager-Konto** (MCC) anmelden. Ein normales Ads-Konto hat
   kein API Center. Wer keines hat, legt unter
   <https://ads.google.com/home/tools/manager-accounts/> eines an; das
   kostet nichts.
2. <https://ads.google.com/aw/apicenter>
3. Token beantragen. Der Antrag fragt nach Zweck und Firma.

**Wichtig — die drei Zugriffsstufen:**

| Stufe | Wirkt auf | Grenze |
| --- | --- | --- |
| Test | nur Testkonten | Echte Konten antworten mit einem Fehler |
| Basic | echte Konten | 15.000 Operationen am Tag |
| Standard | echte Konten | praktisch unbegrenzt |

Ein frisch beantragter Token hat **Testzugriff**. Damit funktioniert
nichts an einem echten Konto — das ist kein Fehler der Werkzeuge. Der
Antrag auf Basic-Zugriff läuft über dieselbe Seite und wird in der Regel
innerhalb weniger Werktage beantwortet.

## Schritt 3: Verbinden

```bash
python3 <plugin>/scripts/google-ads-auth.py
```

Das Skript fragt die vier Angaben ab, öffnet den Zustimmungsbildschirm im
Browser, tauscht den Code gegen einen Refresh Token und schreibt alles
nach `~/.config/neo-google-ads/config.json` mit Rechten 0600.

Kein Browser auf dieser Maschine (Server, Container):

```bash
python3 <plugin>/scripts/google-ads-auth.py --paste-url
```

Dann wird die URL ausgegeben, auf einem beliebigen Rechner geöffnet, und
die Adresse, auf der der Browser landet, zurückkopiert. Sie lädt nicht —
das ist richtig so, der Code steht darin.

Das Google-Konto, das im Browser zustimmt, muss **Nutzer der
Ads-Konten** sein, um die es geht. Ein Google-Konto ohne Zugriff auf ein
Ads-Konto verbindet sich fehlerfrei und sieht nichts.

## Schritt 4: Prüfen

```bash
python3 <plugin>/scripts/google-ads-check.py
python3 <plugin>/scripts/google-ads-check.py --customer-id 123-456-7890
```

Sieben Prüfungen. Jede sagt bei einem Fehlschlag, was zu tun ist. Mit
`--customer-id` kommt eine achte dazu: ein Trockenlauf gegen das echte
Konto, der nichts verändert, aber beweist, dass der Schreibweg offen ist.

## Schritt 5: Schreiben freischalten

Ab Werk liest der Server nur.

```bash
python3 <plugin>/scripts/google-ads-auth.py --allow-write
```

Fragt nacheinander: Schreiben ein, welche Konten, Budgetdeckel,
Steigerungsfaktor. Die Antworten stehen anschließend in der
Konfiguration und gelten für jeden Aufruf.

## Windows

Zwei Dinge sind dort anders.

**Python heißt anders.** Windows kennt `python3` in der Regel nicht — je
nach Installationsweg heißt es `python` oder `py`. Der MCP-Server startet
sonst nicht, meist ohne sichtbaren Fehler: die Werkzeuge tauchen einfach
nicht auf. Prüfen in PowerShell:

```powershell
python --version
py --version
```

Antwortet keines davon mit einer 3er-Fassung, fehlt Python. Aus dem
Microsoft Store oder von <https://www.python.org/downloads/> — beim
Installer **„Add python.exe to PATH" ankreuzen**, sonst findet der Server
ihn nicht.

Meldet Windows beim Aufruf von `python3` den Store statt einer Fassung,
ist das der App-Ausführungsalias. Er ist kein Python. Abschalten unter
Einstellungen → Apps → Erweiterte App-Einstellungen → App-Ausführungsaliase.

Danach in den Benutzervariablen setzen (Einstellungen → System → Info →
Erweiterte Systemeinstellungen → Umgebungsvariablen), damit die
`.mcp.json` den richtigen Aufruf verwendet:

```
GOOGLE_ADS_PYTHON=python
```

Der Schalter steht in der `.mcp.json` als `${GOOGLE_ADS_PYTHON:-python3}`:
gesetzt gewinnt der eigene Wert, sonst bleibt `python3` für Linux und
macOS. Claude Code danach neu starten — Umgebungsvariablen werden beim
Start gelesen.

**Die Skripte werden anders aufgerufen.** Kein `python3`, kein
Schrägstrich nach vorn:

```powershell
python "$env:USERPROFILE\.claude\plugins\...\scripts\google-ads-auth.py"
```

Den Pfad findet man so:

```powershell
Get-ChildItem -Path $env:USERPROFILE\.claude -Recurse -Filter google-ads-auth.py |
  Select-Object -ExpandProperty FullName
```

Die Konfiguration landet unter `%USERPROFILE%\.config\neo-google-ads\`.
Die Dateirechte 0600 setzt Python auf Windows nur eingeschränkt um; die
Prüfung in `google-ads-check.py` meldet dort nichts. Wer den Rechner mit
anderen teilt, prüft die Berechtigungen im Explorer selbst.

## Claude Code im Browser

Eine Cloud-Sitzung hat **keinen Browser für die Zustimmung** und **behält
keine Dateien** — die VM wird nach einer Weile Untätigkeit verworfen. Der
Einrichtungsassistent läuft dort also nicht.

Der Weg ist ein anderer: **einmal auf dem eigenen Rechner verbinden, dann
die Zugangsdaten als Umgebungsvariablen hinterlegen.** Jedes Skript liest
sie und braucht dann keine Datei.

1. Auf dem Windows-Rechner `google-ads-auth.py` durchlaufen lassen, bis
   `google-ads-check.py` ohne Befund durchgeht.
2. Den Übergabeblock erzeugen:

   ```powershell
   python <pfad>\google-ads-auth.py --env
   ```

   Er fragt nach, bevor er etwas ausgibt, und schreibt dann sieben
   Zeilen im `.env`-Format.

3. Den Block in claude.ai/code unter **Umgebung → Umgebungsvariablen**
   einfügen. Sie werden beim Start jeder Sitzung übernommen; laufende
   Sitzungen behalten ihre alten Werte.

4. Den **Netzwerkzugriff** der Umgebung auf **Custom** stellen und diese
   beiden Namen eintragen, sonst kommt die Sitzung nicht an die API:

   ```
   googleads.googleapis.com
   oauth2.googleapis.com
   ```

   Die Stufe **Trusted** enthält sie nicht. „Standardliste der gängigen
   Paketverwaltungen zusätzlich" bleibt am besten angehakt.

5. In der Sitzung prüfen:

   ```bash
   python3 <pfad>/google-ads-check.py
   ```

**Was dabei zu beachten ist:**

- Der Block enthält Refresh Token, Client-Geheimnis und Developer Token
  im Klartext. Er gehört in die Umgebungsvariablen und **nirgendwo sonst
  hin** — nicht ins Repository, nicht in eine Nachricht, nicht in ein
  Ticket. Wer ihn liest, kann Geld ausgeben.
- **Von den Schutzgrenzen wandert nur der Schreibschalter mit.**
  Kontoliste, Budgetdeckel und Steigerungsfaktor stehen in der
  Konfigurationsdatei, die es in der Cloud nicht gibt. Eine Sitzung, die
  nur die Variablen hat, läuft ohne Kontoliste und ohne Budgetdeckel.
  Deshalb: `GOOGLE_ADS_ALLOW_WRITE` in einer Cloud-Umgebung **weglassen**,
  außer die Sitzung soll ausdrücklich schreiben dürfen — und dann eine
  Konfigurationsdatei über das Startskript der Umgebung anlegen, die die
  Grenzen mitbringt.
- `/plugin` gibt es in einer Cloud-Sitzung nicht. Das Plugin muss über
  das Repository kommen oder die Skripte werden direkt aus dem Checkout
  aufgerufen.
- Jede Sitzung startet mit einer frischen VM. Das Änderungsprotokoll
  einer Cloud-Sitzung ist am Ende weg; Googles eigener Verlauf (Bericht
  `change_history`) bleibt.

## Fehlerbilder

| Meldung | Ursache | Abhilfe |
| --- | --- | --- |
| `Configuration incomplete, missing: ...` | Kein Durchlauf von `google-ads-auth.py` | Skript ausführen |
| `Could not refresh the access token` | Zugriff widerrufen, oder OAuth-Client gelöscht | `google-ads-auth.py` erneut |
| `DEVELOPER_TOKEN_NOT_APPROVED` | Testzugriff gegen ein echtes Konto | Basic-Zugriff beantragen |
| `USER_PERMISSION_DENIED` | Kein Zugriff auf dieses Konto, oder `login_customer_id` fehlt | Manager-ID setzen |
| `CUSTOMER_NOT_ENABLED` | Konto stillgelegt oder ohne Zahlungsmittel | Im Ads-Konto klären |
| `no refresh token` beim Verbinden | Konto hatte diesem Client schon zugestimmt | Eintrag unter <https://myaccount.google.com/permissions> entfernen |
| Werkzeuge fehlen in Claude Code | Plugin nicht aktiv, oder `python3` nicht im Pfad | `/plugin`, dann `google-ads-mcp.py --check-config` |
| Werkzeuge fehlen unter Windows | `python3` gibt es dort meist nicht | `GOOGLE_ADS_PYTHON=python` setzen, Claude Code neu starten |
| In der Cloud-Sitzung keine Verbindung | Netzwerkstufe Trusted kennt die Google-Ads-Hosts nicht | Auf Custom stellen, beide Hosts eintragen |

## Ohne Konfigurationsdatei betreiben

Für eine CI oder einen Server nimmt jedes Skript die Werte auch aus der
Umgebung; sie schlagen die Datei:

```
GOOGLE_ADS_CLIENT_ID, GOOGLE_ADS_CLIENT_SECRET, GOOGLE_ADS_REFRESH_TOKEN,
GOOGLE_ADS_DEVELOPER_TOKEN, GOOGLE_ADS_LOGIN_CUSTOMER_ID,
GOOGLE_ADS_API_VERSION, GOOGLE_ADS_ALLOW_WRITE=1, GOOGLE_ADS_CONFIG=<pfad>
```

Den fertigen Block liefert `google-ads-auth.py --env` von einem Rechner,
auf dem die Verbindung schon steht.

## API-Fassung

Der Server ist auf **v25** festgelegt. Google stellt Fassungen etwa ein
Jahr nach Erscheinen ab; ein stiller Sprung würde Feldnamen unter einer
laufenden Konfiguration ändern. Beim Abstellen wird `api_version` in der
Konfiguration hochgezogen und danach `google-ads-check.py` ausgeführt.
