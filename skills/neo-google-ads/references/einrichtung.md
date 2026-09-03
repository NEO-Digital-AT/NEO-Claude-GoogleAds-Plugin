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

## Ohne Konfigurationsdatei betreiben

Für eine CI oder einen Server nimmt jedes Skript die Werte auch aus der
Umgebung; sie schlagen die Datei:

```
GOOGLE_ADS_CLIENT_ID, GOOGLE_ADS_CLIENT_SECRET, GOOGLE_ADS_REFRESH_TOKEN,
GOOGLE_ADS_DEVELOPER_TOKEN, GOOGLE_ADS_LOGIN_CUSTOMER_ID,
GOOGLE_ADS_API_VERSION, GOOGLE_ADS_ALLOW_WRITE=1, GOOGLE_ADS_CONFIG=<pfad>
```

## API-Fassung

Der Server ist auf **v25** festgelegt. Google stellt Fassungen etwa ein
Jahr nach Erscheinen ab; ein stiller Sprung würde Feldnamen unter einer
laufenden Konfiguration ändern. Beim Abstellen wird `api_version` in der
Konfiguration hochgezogen und danach `google-ads-check.py` ausgeführt.
