# Welcher Claude, welcher Weg

Die Werkzeuge sind in allen Fällen dieselben. Nur die Tür ist eine andere,
weil die drei Claude-Oberflächen verschieden an einen Server kommen.

| Wo | Wie | Aufwand |
| --- | --- | --- |
| **Claude Code** | Plugin, startet den Server als lokalen Prozess | eingerichtet |
| **Claude Desktop** (Windows, macOS) | derselbe lokale Prozess, in der Desktop-Konfiguration | fünf Zeilen JSON |
| **claude.ai im Browser, Claude auf dem Handy** | Server läuft bei dir und ist über HTTPS erreichbar | eigener Server nötig |

Der Grund für den Unterschied: Claude Code und die Desktop-App laufen auf
deinem Rechner und dürfen dort ein Programm starten. Die Weboberfläche und
die Handy-App laufen nicht bei dir — sie können nur eine Adresse aufrufen.

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

## claude.ai im Browser und auf dem Handy

Hier läuft nichts auf deinem Rechner. Der Server muss stehen, erreichbar
sein und sich selbst schützen. Dafür ist `google-ads-http.py` da: dieselben
Werkzeuge, dieselben Schutzgrenzen, andere Tür.

### Was du brauchst

- Einen Rechner, der läuft, wenn du Claude benutzt — ein kleiner Server, ein
  VPS, ein Raspberry Pi im Büro. Kein Webhosting-Paket: es muss ein
  Python-Prozess dauerhaft laufen dürfen.
- Eine **HTTPS**-Adresse. Claude verbindet sich nicht über http.
- Einen Reverse Proxy, der das Zertifikat verwaltet (Caddy, nginx,
  Traefik). Das ist der übliche Weg; `--tls-cert` gibt es, ist aber die
  zweite Wahl.

### Einrichten

```bash
# 1. Ein Zugangswort erzeugen (einmal)
python3 google-ads-http.py --new-token

# 2. Server starten, nur auf localhost, der Proxy macht den Rest
python3 google-ads-http.py --port 8788 --anthropic-only
```

`--anthropic-only` lässt nur Aufrufe aus dem von Anthropic veröffentlichten
Adressbereich durch. Damit ist ein erratenes Zugangswort wertlos, solange
der Angreifer nicht auch aus diesem Bereich kommt. **Einschalten, außer der
Proxy verschluckt die Absenderadresse** — dann muss er sie als
`X-Forwarded-For` weitergeben.

Caddy als Proxy, zwei Zeilen:

```
ads-mcp.deine-domain.at {
    reverse_proxy 127.0.0.1:8788
}
```

Caddy holt das Zertifikat selbst. Bei nginx entsprechend `proxy_pass` plus
`proxy_set_header X-Forwarded-For $remote_addr;`.

Als Dienst, damit er einen Neustart übersteht (systemd):

```ini
[Unit]
Description=NEO Google Ads MCP
After=network.target

[Service]
User=neo
ExecStart=/usr/bin/python3 /opt/neo-google-ads/scripts/google-ads-http.py \
          --port 8788 --anthropic-only
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

### In claude.ai eintragen

1. **Einstellungen → Connectors → Benutzerdefinierten Connector hinzufügen**
2. Adresse: `https://ads-mcp.deine-domain.at/mcp`
3. Beim Zugangswort den Header eintragen:
   `Authorization: Bearer <das erzeugte Wort>`

Prüfen, ob der Server überhaupt antwortet — von außen, ohne Zugangswort:

```bash
curl https://ads-mcp.deine-domain.at/health
```

Antwortet `{"status": "ok", ...}`, steht die Strecke. Der `/health`-Pfad
verrät nichts über die Konten, nur dass ein Server da ist.

### Was dabei zu bedenken ist

- **Das Zugangswort ist der Schlüssel zu deinen Werbekonten.** Wer es hat,
  kann lesen und — falls das Schreiben eingeschaltet ist — Geld ausgeben.
  Es gehört in einen Passwortspeicher, nicht in eine Nachricht.
- **Schreiben in einer Weboberfläche ist eine eigene Entscheidung.** Der
  Schreibschalter und die Kontoliste stehen in der Konfigurationsdatei auf
  dem Server, nicht in claude.ai. Ein Server, der nur lesen soll, bleibt
  auf `write_enabled: false` — dann sind Trockenläufe möglich und mehr
  nicht.
- **Die Antwortgröße ist begrenzt**, in claude.ai auf etwa 150.000 Zeichen.
  Die Berichte kürzen ohnehin auf `limit` Zeilen und sagen, wenn sie
  gekürzt haben.
- **Zeitgrenze fünf Minuten.** Reicht für jede Abfrage dieses Servers.
- Wer den Server abschaltet, verliert den Connector nicht — er antwortet
  nur nicht mehr. Beim nächsten Start ist er wieder da.

## Was du in welcher Oberfläche tust

Die Regeln des Skills gelten überall gleich: messen, Plan vorlegen,
Freigabe abwarten, Trockenlauf, umsetzen, belegen. Praktisch verteilt es
sich so:

| Aufgabe | Wo es sich anbietet |
| --- | --- |
| Kampagnen und Suchbegriffe ansehen, Fragen stellen | claude.ai, auch vom Handy |
| Auswertung mit einer Website zusammen, Berichte schreiben | Claude Code |
| Änderungen umsetzen | dort, wo die Schutzgrenzen gesetzt sind — in der Regel lokal |

Ein Server, der nur liest, darf ruhig im Browser hängen. Der schreibende
Zugang gehört auf den Rechner, auf dem auch die Kontoliste und der
Budgetdeckel stehen.
