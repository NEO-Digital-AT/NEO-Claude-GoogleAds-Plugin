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

**Das Geheimnis erscheint genau einmal.** Google speichert es gehasht und
zeigt es nur unmittelbar nach dem Erstellen; danach stehen in der Console
nur noch die letzten vier Zeichen. Wer das Fenster schließt, ohne zu
kopieren oder die JSON herunterzuladen, sieht es nie wieder — es ist dann
verloren, nicht versteckt.

Ist es weg, wird ein zweites erzeugt statt eines neuen Clients:
<https://console.cloud.google.com/auth/clients> → Client anklicken →
rechts **Geheimnis hinzufügen**. Ein Client darf mehrere haben; das alte
bleibt gültig und kann später entfernt werden. In der Liste der
Anmeldedaten führt auch das **Download-Symbol** zum Ziel — die JSON
enthält Kennung und Geheimnis zusammen.

**Die Client-ID ist kein Geheimnis.** Sie steht bei jeder Anmeldung
sichtbar in der Browser-Adresse. Das Client-Geheimnis dagegen wird
behandelt wie ein Passwort: nie in eine Nachricht, nie in ein Ticket, nie
in ein Repository.

## Schritt 2: Developer Token

1. In einem **Manager-Konto** (MCC) anmelden. Ein normales Ads-Konto hat
   kein API Center. Wer keines hat, legt unter
   <https://ads.google.com/home/tools/manager-accounts/> eines an; das
   kostet nichts.
2. <https://ads.google.com/aw/apicenter>
3. Token beantragen. Der Antrag fragt nach Zweck und Firma.

**Wichtig — die vier Zugriffsstufen:**

| Stufe | Wirkt auf | Grenze am Tag | Freigabe |
| --- | --- | --- | --- |
| Test | nur Testkonten | 15.000 | sofort |
| Explorer | echte Konten | 2.880 | oft sofort |
| Basic | echte Konten | 15.000 | etwa 5 Werktage |
| Standard | echte Konten | unbegrenzt | etwa 10 Werktage, für große Anbieter |

Ein frisch beantragter Token hat **Testzugriff**. Damit funktioniert
nichts an einem echten Konto — das ist kein Fehler der Werkzeuge.

**Explorer ist der schnelle Weg an ein echtes Konto**: Google vergibt die
Stufe in vielen Fällen ohne Wartezeit. Zwei Einschränkungen dabei:

- 2.880 Operationen am Tag. Für Analyse und gezielte Änderungen reicht
  das; eine Massenänderung über tausende Keywords nicht.
- **Die Planungswerkzeuge sind gesperrt.** `google_ads_keyword_ideas` und
  `google_ads_keyword_metrics` — also der Keyword-Planer — antworten mit
  einem Fehler. Ebenso Kontoanlage, Nutzerverwaltung und Abrechnung.
  Alles Übrige funktioniert.

Wer den Keyword-Planer braucht oder mehr Operationen, beantragt auf
derselben Seite **Basic**.

## Schritt 2b: Wenn es kein Verwaltungskonto gibt

Das API Center existiert **nur** in einem Verwaltungskonto. Ein normales
Konto hat den Menüpunkt nicht — er ist nicht versteckt, er ist nicht da.
Wer `https://ads.google.com/aw/apicenter` in einem normalen Konto aufruft,
landet im Kontowähler, und keine Auswahl führt weiter.

Ein bestehendes Kundenkonto lässt sich **nicht** in ein Verwaltungskonto
umwandeln. Es muss ein neues her:

<https://ads.google.com/home/tools/manager-accounts/> → Verwaltungskonto
erstellen. Es kostet nichts, braucht keine Kampagnen, kein Budget und
keine Zahlungsdaten. Bei der Frage nach dem Zweck ist „Konten anderer
verwalten" richtig, sobald fremde Konten dazukommen sollen.

### Wenn Google das Anlegen verweigert

„Die zulässige Höchstzahl von Verwaltungskonten, die Sie erstellen
können, wurde erreicht." — diese Meldung trifft auch Konten mit **zwei
oder drei** Google-Ads-Konten. Es ist ein eigenes, von Google nicht
veröffentlichtes Limit auf das **Erstellen** von Verwaltungskonten, nicht
das Limit von 20 Konten je E-Mail-Adresse. Aufgelöste Konten zählen
offenbar weiter mit.

Zwei Wege, in dieser Reihenfolge:

1. **Andere E-Mail-Adresse.** Das Limit hängt am Google-Konto. Eine
   zweite Adresse der eigenen Firma — etwa `googleads-api@…` — genügt.
   Der Developer Token und der Kontozugriff sind **getrennt**: der Token
   kommt aus dem Verwaltungskonto, die Zustimmung im Browser gibt das
   Konto, das die Kampagnen sieht. Beide dürfen verschiedene Konten sein.
2. **Support fragen.** In Google Ads: Hilfe → Kontakt. Das Limit ist
   anhebbar; als Grund genügt der API-Zugang.

### Die eigenen Konten mit dem Verwaltungskonto verknüpfen

Nötig, sobald der Antrag auf Basic-Zugriff läuft: Google verlangt dafür,
dass die verwalteten Konten unter dem Verwaltungskonto hängen, das den
Token hält.

**Im Verwaltungskonto:**

1. Linkes Menü → Einstellungen → oben **Einstellungen für Unterkonten**
2. Pluszeichen → **Vorhandenes Konto verknüpfen**
3. Kundennummer eintragen, **Anfrage senden**. Je Konto einmal.

**Im jeweiligen Kundenkonto** (Konto wechseln):

4. **Verwaltung** → **Zugriff und Sicherheit** → Reiter **Manager** →
   Einladung **annehmen**

Wer in beiden Konten Administrator ist, erledigt beide Seiten selbst.
Aufgelöste Konten werden nicht verknüpft.

Danach ist die Kundennummer des Verwaltungskontos die
`login_customer_id`, und das Konto, in dem gearbeitet wird, die
`customer_id`. Die zu verwechseln ist die häufigste Ursache für
`USER_PERMISSION_DENIED`.

## Schritt 3: Verbinden

```bash
python3 <plugin>/scripts/google-ads-auth.py
```

Das Skript fragt die vier Angaben ab, öffnet den Zustimmungsbildschirm im
Browser, tauscht den Code gegen einen Refresh Token und schreibt alles
nach `~/.config/neo-google-ads/config.json` mit Rechten 0600.

### Auf einem Server, ohne Browser

`--paste-url` hält den Prozess an, bis die Adresse eingefügt ist. Auf
einem Terminal ist das eine Falle: **Strg+C heißt dort „abbrechen", nicht
„kopieren"** — der übliche Griff zum Kopieren der URL beendet genau den
Prozess, der auf sie wartet. Deshalb gibt es den Ablauf in zwei Schritten,
zwischen denen nichts läuft:

```bash
# Schritt 1 — druckt die URL und beendet sich
python3 <plugin>/scripts/google-ads-auth.py --auth-url --env-file deploy/.env

# URL in Ruhe kopieren, im Browser öffnen, zustimmen.
# Der Browser landet auf einer 127.0.0.1-Adresse, die nicht lädt —
# das ist richtig so, der Code steht darin. Ganze Adresszeile kopieren.

# Schritt 2 — Adresse als Argument
python3 <plugin>/scripts/google-ads-auth.py --auth-code 'http://127.0.0.1:.../?state=...&code=...'
```

**`--env-file` erspart das Abtippen.** Wer die `.env` für den Container
schon gefüllt hat, hat Client-ID, Geheimnis und Developer Token dort
stehen; das Skript liest sie von dort und fragt nichts mehr. Ohne die
Angabe fragt es wie gehabt.

Zum Kopieren im Terminal: in den meisten Linux-Terminals **Strg+Umschalt+C**,
in PuTTY genügt das Markieren mit der Maus.

Das Google-Konto, das im Browser zustimmt, muss **Nutzer der
Ads-Konten** sein, um die es geht. Ein Google-Konto ohne Zugriff auf ein
Ads-Konto verbindet sich fehlerfrei und sieht nichts.

## Schritt 4: Prüfen

```bash
python3 <plugin>/scripts/google-ads-check.py
python3 <plugin>/scripts/google-ads-check.py --customer-id 123-456-7890
```

Acht Prüfungen. Jede sagt bei einem Fehlschlag, was zu tun ist. Die
letzten beiden brauchen `--customer-id`, weil sie ein Konto zum Zielen
brauchen:

- **Prüfung 7** stellt dem Keyword-Planer eine winzige Frage und verrät
  damit die Zugriffsstufe, die die API nie ausspricht. Antwortet er
  nicht, ist es ein Explorer-Token: elf der dreizehn Werkzeuge laufen,
  der Keyword-Planer nicht.
- **Prüfung 8** ist ein Trockenlauf gegen das echte Konto. Er verändert
  nichts, beweist aber, dass der Schreibweg offen ist.

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

Antwortet keines davon mit einer 3er-Fassung, fehlt Python.

**Der einfachste Weg: Python aus dem Microsoft Store.** Diese Fassung
legt `python3` mit an, damit läuft der Server ohne weitere Einstellung —
genau wie unter Linux und macOS. Store öffnen, „Python 3.13" (oder neuer)
installieren, fertig.

Der Installer von <https://www.python.org/downloads/> geht auch, legt aber
nur `python` und `py` an, kein `python3`. Dann ist **eine** Einstellung
nötig, in den Benutzervariablen (Einstellungen → System → Info →
Erweiterte Systemeinstellungen → Umgebungsvariablen):

```
GOOGLE_ADS_PYTHON=python
```

Der Schalter steht in der `.mcp.json` als `${GOOGLE_ADS_PYTHON:-python3}`:
gesetzt gewinnt der eigene Wert, sonst bleibt `python3`. Claude Code danach
neu starten — Umgebungsvariablen werden beim Start gelesen.

Meldet Windows beim Aufruf von `python3` den Store, **obwohl** Python
installiert ist, ist das der App-Ausführungsalias, der sich vordrängt. Er
ist kein Python. Abschalten unter Einstellungen → Apps → Erweiterte
App-Einstellungen → App-Ausführungsaliase.

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
| Keyword-Planer antwortet mit einem Fehler, sonst läuft alles | Token hat Explorer-Zugriff, Planungswerkzeuge gesperrt | Basic beantragen |
| `USER_PERMISSION_DENIED` | Kein Zugriff auf dieses Konto, oder `login_customer_id` fehlt | Manager-ID setzen |
| `CUSTOMER_NOT_ENABLED` | Konto stillgelegt oder ohne Zahlungsmittel | Im Ads-Konto klären |
| `no refresh token` beim Verbinden | Konto hatte diesem Client schon zugestimmt | Eintrag unter <https://myaccount.google.com/permissions> entfernen |
| Nur eine Client-ID, kein Geheimnis | Google zeigt es nur einmal beim Erstellen | Client anklicken, **Geheimnis hinzufügen** |
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
