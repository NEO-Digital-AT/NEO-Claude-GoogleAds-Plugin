---
description: Google-Ads-Zugang einrichten und messen — OAuth, Developer Token, Manager-Konto, Schutzgrenzen
---

Richte den Google-Ads-Zugang ein und **weise nach, dass er funktioniert**.
Behauptet zählt nicht.

Lade zuerst den Skill `neo-google-ads` und
`references/einrichtung.md`.

## 1. Stand feststellen

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/google-ads-check.py"
```

Der Selbsttest sagt, was fehlt. Läuft er ohne Befund durch, ist der
Zugang bereits eingerichtet — dann nur noch Schritt 5.

## 2. Voraussetzungen klären

Frage nach, was der Selbsttest nicht wissen kann:

1. Gibt es einen **OAuth-Client** (Cloud Console, Typ Desktop-App)?
2. Gibt es einen **Developer Token** — und hat er **Test-** oder
   **Basic-Zugriff**? Ein Test-Token arbeitet nur an Testkonten. Das ist
   die häufigste Ursache für „geht nicht" und kein Fehler der Werkzeuge.
3. Gibt es ein **Manager-Konto (MCC)**? Ohne eines gibt es kein API
   Center und damit keinen Developer Token.
4. Sollen **fremde Konten** betreut werden? Dann ist die Manager-ID
   Pflicht und die Kontoliste in den Schutzgrenzen ebenso.

Fehlt etwas davon, nenne den Weg dorthin aus `references/einrichtung.md`
und **halte an**. Nichts davon lässt sich umgehen.

## 3. Verbinden

Der Projektinhaber führt das aus — es öffnet einen Browser und fragt
nach Geheimnissen, die nicht durch den Chat gehen:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/google-ads-auth.py"
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/google-ads-auth.py" --paste-url   # ohne Browser
```

**Frage nie nach Client-Geheimnis, Developer Token oder Refresh Token.**
Sie gehören in das Skript, nicht in eine Nachricht.

## 4. Messen

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/google-ads-check.py" --customer-id <konto>
```

Sieben Prüfungen plus Schreibweg. Zeige die Ausgabe. Bei einem Befund:
die Abhilfe steht in derselben Zeile, danach erneut messen.

## 5. Schutzgrenzen setzen

Nur wenn geschrieben werden soll. Erkläre vorher, was der Schalter
bedeutet, und lass den Projektinhaber ausführen:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/google-ads-auth.py" --allow-write
```

Empfehle dabei:

- Bei fremden Konten: `allowed_customer_ids` **einzeln füllen**, nie leer
  lassen.
- Budgetdeckel auf einen mit dem Kunden vereinbarten Wert.
- Steigerungsfaktor bei 2.0 bis 3.0 belassen.

## 6. Abnahme

Zeige zum Schluss:

- [ ] Ausgabe von `google-ads-check.py` ohne Befund
- [ ] Liste der zugänglichen Konten mit Namen und Währung
- [ ] Zustand der Schutzgrenzen (`google-ads-auth.py --show`)
- [ ] Ob der Developer Token Test- oder Basic-Zugriff hat
- [ ] Eine echte Leseabfrage, etwa `google_ads_report` mit `account`
