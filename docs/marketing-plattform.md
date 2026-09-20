# NEO Marketing-Plattform — Auftragsrahmen

Stand 2026-09-20 · Entwurf, Fassung 1
Entscheidungsakte nach `neo-technologiewahl` fehlt noch (siehe Abschnitt 8).

Dieses Dokument ist der Auftragsrahmen für ein neues, eigenständiges
Produkt. Wer damit zu bauen beginnt, liest Abschnitt 3 (Grenze
Basis/Plugin) und Abschnitt 7 (Stufenplan). Alles andere ist Begründung
und kann später gelesen werden.

## 1 Was es heute gibt

Repository `NEO-Claude-GoogleAds-Plugin`, Fassung 2.9.0, 281 Prüffälle.

| Teil | Zustand |
| --- | --- |
| MCP-Server Google Ads (API v25, GAQL, lesend und schreibend) | läuft |
| Portal: Anmeldung, zweiter Faktor, Wiederherstellungscodes, Passkeys | läuft |
| Schutzgrenzen je Konto, Trockenlauf | läuft |
| OAuth-Einrichtung im Browser, Kontenliste, Prüfung, Diagnose | läuft |
| Öffentliche Seite nach dem NEO-Designsystem | läuft |
| Speicher | SQLite, eine Datei |
| Sprache | Python 3, nur Standardbibliothek |

Das ist ein Einzelplatzwerkzeug für einen Benutzer und eine Agentur. Es
kennt keine Mandanten, keine Rollen, keine Webseiten, keine Freigaben.
Fachlich ist es die Vorlage; technisch wird es nicht weitergebaut.

## 2 Technologieentscheidung

### 2.1 Festlegung

| Schicht | Festlegung |
| --- | --- |
| Laufzeit | .NET 10 (LTS) |
| Web und API | ASP.NET Core, REST nach dem Muster von LeoFlex, OpenAPI |
| Datenzugriff | EF Core |
| Datenbank | PostgreSQL |
| Frontend | Vue 3, Vuetify, TypeScript |
| Hintergrundarbeit | Hosted Service, Warteschlange in der Datenbank |
| Plugins | kompilierte Assemblies, geladen über `AssemblyLoadContext` |
| Auslieferung | Docker: eine Anwendung, eine Datenbank |

### 2.2 Warum

1. **Hausstandard.** Zwei Backend-Stacks sind ausgemacht: .NET Core und
   Laravel. LeoFlex läuft auf .NET Core. Die Regeln liegen fertig vor —
   `neo-dotnet`, `neo-api`, `neo-vue`.
2. **Das Produkt wird verkauft, der Quellcode bleibt zu.** In .NET ist
   ein Plugin eine kompilierte DLL. In PHP wäre jedes Plugin Quelltext
   und bräuchte ionCube oder SourceGuardian, dazu eine Lizenz auf jedem
   Kundenserver und eine passende Erweiterung im PHP des Kunden.
3. **Kein Fremdzugriff erwünscht.** Eine PHP-Agentur, die das System
   einsetzt, soll nicht darin herumprogrammieren. Kompilierter Code macht
   das ohne weiteres Zutun schwerer.
4. **Mandantentrennung und Hintergrundarbeit gehören zur Grundausstattung.**
   EF Core (Query Filter) und Hosted Services decken beides ab. In PHP
   bräuchte es zusätzliche Dienste neben dem Webserver.
5. **Der Einwand "zwei Technologien im Haus" zählt hier nicht.**
   Contao-Arbeit fällt als *Ergebnis* an — Datenbankinhalte, Twig-Vorlagen,
   Migrationen —, nicht als Programmierarbeit *in* diesem Produkt. Wer die
   Plattform betreibt, schreibt kein PHP.

### 2.3 Verworfen

| Weg | Grund |
| --- | --- |
| Laravel | Plugins wären offener Quelltext; Verschleierung und Lizenzbindung je Kundenserver nötig |
| Python (wie heute) | kein Hausstandard, kein Regelwerk, schwache Mandantentrennung |
| Node im Backend | kein Hausstandard |
| Inertia | im NEO-Regelwerk nicht vorgesehen — war ein Fehlvorschlag |

### 2.4 Noch zu klären

- Stützungsende von .NET 10 prüfen, bevor gebaut wird.
- Betriebsform beim Kunden: Docker oder Windows-Dienst.

## 3 Die Grenze: was Basis, was Plugin

**Die Basis kennt Mandanten, Menschen, Vorgänge und Werbung.
Ein Plugin kennt ein fremdes System.**

Alles, was jeder Betreiber braucht, ist Basis. Ein Plugin spricht mit
genau einem fremden System.

### 3.1 Basis

| Bereich | Inhalt |
| --- | --- |
| Mandanten | Kunde, mehrere Webseiten je Kunde, Trennung der Daten |
| Menschen und Rechte | Administrator, Marketing, Lesen; Urlaubsvertretung mit Zeitraum |
| Zugangstresor | verschlüsselte Zugänge je Mandant (Google, Git, KI, FTP); nie im Klartext, nie im Protokoll |
| Vorgänge | jede Änderung ist ein Vorgang: Vorschlag, Freigabe, Ausführung, Nachweis |
| Freigaben | zwei Stufen, mit Vorher/Nachher |
| KI-Anbindung | Requesty als Vermittler, EU-Modelle; Modell und Prompt je Mandant einstellbar |
| Google Ads | Konten, Kampagnen, Anzeigen, Budgets |
| Schutzgrenzen | Standard und Überschreibung je Konto, Trockenlauf, Höchstwerte |
| Crawler | öffentliche Webseite lesen, ohne Zugang, ohne Git |
| Konsole | Befehlseingabe für alles, was die Oberfläche kann |
| Aufträge | Warteschlange, asynchron, sichtbarer Fortschritt, Wiederholung |
| Protokoll | wer, wann, was, womit, mit welchem Ergebnis |
| Plugin-Verwaltung | hochladen, aktivieren, Fassung, Abhängigkeiten, Lizenz |

Google Ads bleibt in der Basis — nicht weil es klein wäre, sondern weil
ohne Werbung vom Produkt nichts übrig bleibt.

Der Crawler bleibt in der Basis, weil er der kleinste vollständige Fall
ist: Webseite lesen, Werbung daraus erzeugen. Ohne ihn kann ein neuer
Mandant gar nichts.

### 3.2 Plugin

Ein Plugin dockt an vier Stellen an, sonst nirgends:

| Andockpunkt | Was es liefert |
| --- | --- |
| Analyse | liest ein fremdes System, gibt Befunde zurück |
| Bericht | eine Kachel oder Seite mit eigenen Zahlen |
| Aktion | führt einen freigegebenen Vorgang aus |
| Einstellungen | eine Seite je Mandant für dessen Zugänge |

Mehr Andockpunkte gibt es zu Beginn nicht. Wer mehr braucht, begründet es.
Die Grenze eng zu halten ist die einzige Möglichkeit, sie später noch
verschieben zu können.

### 3.3 Git oder Contao — zwei Plugins, nicht eines

Sie beantworten verschiedene Fragen:

| Frage | Antworten |
| --- | --- |
| **Quelle** — woher kommt der Inhalt | Crawler (Basis), Git, FTP, Datenbank |
| **Inhaltsmodell** — wie ist er aufgebaut | Contao, WordPress, Plain HTML, React, Headless |

Eine Webseite braucht beides, und beides kreuzt sich: Contao über Git,
Contao über FTP, WordPress über Git. Als ein Plugin gefasst, müsste jede
Kombination einzeln gebaut werden.

**Git** ist ein Plugin mit zwei Abgängen — GitHub und GitLab (auch mit
eigener Domain) —, nicht zwei Plugins. Es liefert: eigenes Konto je
Mandant, klonen, Zweig anlegen, ändern, Merge-Anfrage. Zwei Merge-Stufen:
Arbeitszweig nach `dev`, `dev` nach `main`.

**Contao** ist das Plugin, das weiß, wie ein Contao-Inhalt aussieht.
Tatsache dazu: **Contao hat im Kern keine Inhalts-API.**
`contao/manager-api` verwaltet nur die Installation. Schreiben geht über
(a) Datenbankinhalte plus Migration im Git, (b) ein Fremdbundle, das beim
Kunden installiert sein muss, (c) Twig-Vorlagen im Git. Tragfähig sind
(a) und (c), und beide brauchen Git.

Daraus folgt die Abstufung, und sie ist beabsichtigt:

| Vorhanden | Was geht |
| --- | --- |
| nur Crawler (Basis) | Webseite lesen, Werbung erzeugen |
| Crawler + Contao | Inhalt verstehen, Vorschläge machen, nicht schreiben |
| Crawler + Contao + Git | Inhalt ändern, als Merge-Anfrage im Git des Kunden |

## 4 Plugin-Technik

### 4.1 Ordnerstruktur — überall gleich

```
plugins/
  neo.contao/
    plugin.json          Manifest
    Neo.Contao.dll       kompiliert
    Controllers/
    Domain/
    Services/
    Views/               Vue-Komponenten, vorübersetzt
    Migrations/
    assets/
```

Jedes Plugin sieht so aus. Keine Ausnahme, auch nicht für eigene.

### 4.2 Manifest

`id`, `name`, `version`, `requires` (Basisfassung), `depends` (andere
Plugins), `provides` (welche der vier Andockpunkte), `license`
(frei oder kostenpflichtig), `signature`.

### 4.3 Laden

Beim Start liest die Basis den Plugin-Ordner, prüft Signatur und Lizenz,
lädt jede DLL in einen eigenen `AssemblyLoadContext` und meldet ihre
Andockpunkte an. Ein Plugin mit unpassender Basisfassung wird nicht
geladen und steht in der Verwaltung als "nicht geladen" samt Grund.
Eigene Migrationen laufen beim Aktivieren, nicht beim Start.

### 4.4 Verteilung

| Weg | Wofür |
| --- | --- |
| ZIP hochladen | immer möglich, auch für eigene Plugins |
| aus Git laden | eigene, nicht veröffentlichte Plugins |
| Marktplatz | eigener Git-Marktplatz von NEO Digital, teils frei, teils kostenpflichtig |

Lizenzspeicher mit Tarifen, Mandantenzahl, Testzeitraum und monatlicher
Gebühr ist vorgesehen, wird aber **jetzt nicht gebaut**. Bis dahin genügt
die Signaturprüfung.

## 5 Google Ads im Einzelnen

### 5.1 Mehrere Verwaltungskonten

Eine Agentur kann mehr als ein Verwaltungskonto (MCC) haben. Deshalb:

- Ein Verwaltungskonto ist ein eigener Datensatz mit eigenem
  OAuth-Zugang, eigener `login-customer-id` und eigener Zugriffsstufe.
- Ein Mandant hängt an einem Kundenkonto, das Kundenkonto an einem
  Verwaltungskonto.
- Schutzgrenzen gelten je Kundenkonto, unabhängig vom Verwaltungskonto.

Damit entfällt das Problem der zwei Anmeldungen: Der Mitarbeiter meldet
sich an der Plattform an, nicht bei Google.

### 5.2 Steuerung, ohne Google Ads zu öffnen

| Vorgang | Weg |
| --- | --- |
| Kundenkonto einladen | `CustomerClientLink`, Status `PENDING` |
| Einladung zurückziehen | derselbe Dienst, Status `CANCELED` |
| Verbindung trennen | Status `INACTIVE` |
| Unterkonten auflisten | GAQL auf `customer_client` |
| Kundenkonto neu anlegen | `CustomerService.CreateCustomerClient` |
| Benutzerzugriff einsehen | `customer_user_access` |

Jeder dieser Vorgänge ist freigabepflichtig, kein Knopf ohne Rückfrage.

### 5.3 Zugriffsstufen und der Keyword-Planer

| Stufe | Was geht |
| --- | --- |
| Test | nur Testkonten |
| Explorer | begrenzt, echte Konten |
| Basic | Tagesgrenze für Abrufe |
| Standard | ohne Tagesgrenze |

Der Keyword-Planer (`KeywordPlanIdeaService`) setzt die höchste Stufe
voraus und muss bei Google beantragt werden. Bis die Freigabe vorliegt,
greift der Notausgang: Der Benutzer gibt die Begriffe im Keyword-Planer
selbst ein, lädt das Ergebnis als CSV herunter und in die Plattform
hoch. Die Plattform rechnet damit weiter, als käme es aus der API.

Deshalb: **Keyword-Planer ist ein Plugin, der CSV-Weg ist Basis.**

## 6 Der Ablauf, um den herum gebaut wird

1. Mandant anlegen, Webseite eintragen, Zugänge hinterlegen.
2. Webseite analysieren — crawlen, mit Git-Plugin auch lesen: Was bietet
   der Kunde, welche Begriffe, welche Seiten, welche Lücken.
3. Werbung vorschlagen: Kampagnen, Anzeigengruppen, Anzeigen, Begriffe,
   Budgets.
4. Vorschlag geht als Vorgang in die Freigabe, mit Vorher/Nachher und,
   wo die Webseite betroffen ist, mit Screenshot.
5. Nach Freigabe ausführen: in Google Ads schreiben oder eine
   Merge-Anfrage im Git des Kunden öffnen.
6. Ergebnis messen, zurückmelden, nachbessern.

Nichts davon ohne Freigabe. Nichts davon im Vordergrund: Jeder Schritt
ist ein Auftrag in der Warteschlange mit sichtbarem Zustand. Ein Klick
antwortet sofort, auch wenn die Arbeit dahinter Minuten dauert.

## 7 Stufenplan

### Stufe 1 — jetzt bauen

- Gerüst: .NET 10, ASP.NET Core, EF Core, PostgreSQL, Vue 3 mit Vuetify
- Anmeldung, zweiter Faktor, Passkeys, Sitzungen — fachlich aus dem
  heutigen Portal übernommen
- Mandanten, Webseiten, Benutzer, Rollen, Urlaubsvertretung
- Zugangstresor
- Google Ads: Verbindung, mehrere Verwaltungskonten, Kontenliste, lesen
- Schutzgrenzen je Konto
- Vorgänge mit zweistufiger Freigabe und Protokoll
- Auftragswarteschlange, asynchron, sichtbarer Fortschritt
- Crawler
- KI-Anbindung über Requesty
- Konsole
- Plugin-Lader mit den vier Andockpunkten — auch wenn es anfangs kein
  einziges Plugin gibt. Wer ihn später einzieht, baut die Basis um.

### Stufe 2 — danach

- Git-Plugin (GitHub und GitLab), zwei Merge-Stufen
- Contao-Plugin: lesen über Git, schreiben über Migration und Twig
- Screenshots im Freigabeweg
- Keyword-Planer-Plugin und CSV-Import
- Verwaltungskonto-Steuerung: einladen, trennen, Konto anlegen
- Berichte

### Stufe 3 — bei Marktreife

- Marktplatz und Lizenzspeicher, Tarife, Testzeitraum
- WordPress-Plugin
- Headless CMS, React, Plain HTML
- Weitere Kanäle: Meta, LinkedIn, Microsoft Ads
- Cloud-Betrieb von NEO aus

### Bewusst nicht

- **Kein MCP-Server als Pflichtteil.** Ob die Plattform zusätzlich einen
  MCP-Zugang anbietet, ist eine spätere Frage, keine Grundlage.
- **Keine Oberfläche, die nur mit KI bedienbar ist.** Alles muss auch von
  Hand gehen. Stark KI-getrieben, nicht ausschließlich.
- **Keine Änderung an einer Kundenwebseite ohne Freigabe** — auch nicht
  "nur ein Text".

## 8 Offene Entscheidungen

| Nr. | Frage | Vorschlag |
| --- | --- | --- |
| 1 | .NET 10 endgültig? Entscheidungsakte nach `neo-technologiewahl` | ja |
| 2 | Google Ads in der Basis oder als erstes Plugin? | Basis |
| 3 | Name und eigenes Repository für das Produkt | offen |
| 4 | Läuft das heutige Python-Werkzeug weiter, bis Stufe 1 steht? | ja, unverändert |
| 5 | Preise und Tarife | erst bei Marktreife |

## 9 Geltende Regeln

| Skill | Wofür |
| --- | --- |
| `neo-grundregeln` | Prozess, Freigaben, Auftragsliste, Belegpflicht |
| `neo-technologiewahl` | Abschnitt 2, die fehlende Entscheidungsakte |
| `neo-dotnet` | Aufbau, Mandantentrennung, EF Core |
| `neo-api` | REST nach dem Muster von LeoFlex |
| `neo-vue`, `neo-design`, `neo-komponenten` | Oberfläche |
| `neo-ki` | KI-Anbindung, Prompts, Modellwahl |
| `neo-sicherheit` | Zugangstresor, Protokoll, Rechte |
| `neo-code` | Regeln deutsch, Code englisch |
| `neo-doku` | trockene Sprache, IST-Zustand |
| `neo-contao` | für das Contao-Plugin |
| `neo-betrieb`, `neo-deployment` | Auslieferung und Betrieb |
| `neo-recht` | Lizenz, Verkauf, Auftragsverarbeitung |
