# NEO Marketing-Plattform — Auftragsrahmen

Stand 2026-09-20 · Entwurf, Fassung 1
Entscheidungsakte nach `neo-technologiewahl` fehlt noch (siehe Abschnitt 10).

Dieses Dokument ist der Auftragsrahmen für ein neues, eigenständiges
Produkt. Wer damit zu bauen beginnt, liest Abschnitt 3 (Grenze
Basis/Plugin) und Abschnitt 9 (Stufenplan). Alles andere ist Begründung
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
   Migrationen —, nicht als Programmierarbeit *in* diesem Produkt.
   Eine Ausnahme gibt es: das Contao-Bundle (Abschnitt 5) ist PHP. Es ist
   klein, es liegt beim Kunden, es hat einen eigenen Lebenslauf und es
   wird gegen eine feste Schnittstelle gebaut. Das ist kein zweiter
   Stack, sondern ein Zubehörteil — für WordPress käme später ein
   gleichartiges hinzu.

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

### 3.3 Zwei Achsen: Verbindung und System

Eine Webseite zu erreichen und sie zu verstehen sind zwei verschiedene
Fragen, und sie kreuzen sich:

| Achse | Frage | Plugins |
| --- | --- | --- |
| **Verbindung** | Wie kommt man hin | Crawler (Basis), Git, FTP/SFTP, Live-Bundle, Headless-API |
| **System** | Was findet man dort | Contao, WordPress, Plain HTML, React, Headless |

Als ein Plugin gefasst, müsste jede Kombination einzeln gebaut werden:
Contao über Git, Contao live, WordPress über Git, WordPress über FTP.
Getrennt sind es Summanden statt Produkte.

**Verbindung ist Transport und Versionierung.**
Git legt einen eigenen Zweig an, ändert, öffnet die Merge-Anfrage; zwei
Stufen, Arbeitszweig nach `dev`, `dev` nach `main`. GitHub und GitLab
(auch mit eigener Domain) sind zwei Abgänge desselben Plugins, nicht zwei
Plugins. FTP/SFTP schreibt Dateien ohne Versionierung — einfacher und
gefährlicher. Das Live-Bundle schreibt unmittelbar in die Datenbank der
Installation (Abschnitt 5).

**System ist Verständnis.**
Das Contao-Plugin weiß, was ein Artikel ist, wo Inhalte liegen, wie eine
Migration aussieht und was man nicht anfassen darf. Ohne dieses Wissen
darf keine Verbindung schreiben — sonst zerstört der Transport, was er
nicht versteht.

### 3.4 Daraus folgt die Abstufung

| Vorhanden | Was geht |
| --- | --- |
| nur Crawler (Basis) | Webseite lesen, Werbung erzeugen |
| Crawler + System | Inhalt verstehen, Änderungen vorschlagen |
| + Live-Bundle | Texte ändern, sofort, ohne Deploy |
| + Git | alles ändern, über Zweig und Merge-Anfrage |
| + FTP | Dateien ändern, ohne Versionierung |

Jede Stufe ist für sich verkaufbar. Das ist beabsichtigt.


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

## 5 Das eigene Contao-Bundle

Contao hat keine Inhalts-API. Also liefert das Produkt eine mit: ein
Contao-Bundle (Symfony), das auf der Installation des Kunden liegt.

### 5.1 Was es tut

| Kann | Kann nicht |
| --- | --- |
| Artikel und Inhaltselemente auflisten (`tl_article`, `tl_content`) | Seiten anlegen oder löschen |
| Text und Überschrift eines vorhandenen Elements lesen | Elemente anlegen, verschieben, löschen |
| Text und Überschrift ändern — sofort, ohne Deploy | Einstellungen, Benutzer, Dateien, PHP |
| Seitenbaum als Zusammenhang lesen | Module, Layouts, Themes |

Die Beschränkung ist das Sicherheitsmerkmal, nicht eine fehlende
Ausbaustufe. Ein Zugang, der nur Text in vorhandenen Elementen ändern
kann, richtet im schlimmsten Fall Unsinn an — er zerstört keine Seite.
Wer mehr braucht, nimmt Git.

### 5.2 Wie es schreibt

Über Contaos eigene Modelle und den Versionsverlauf, nicht über rohes
SQL. Damit steht jede Änderung in `tl_version`, und der Kunde kann sie im
eigenen Backend zurücknehmen — auch ohne das Produkt. Nach dem Schreiben
wird der Seiten-Cache gezielt verworfen.

### 5.3 Wie es gesichert ist

Das Bundle ist ein schreibender Zugang auf eine Live-Seite. Das ist die
heikelste Stelle des ganzen Entwurfs und wird entsprechend behandelt:

- Ein Zeichen (Token) je Installation, im Tresor des Mandanten.
- Jede Anfrage signiert, mit Zeitstempel und Einmalwert — eine
  abgefangene Anfrage lässt sich nicht wiederholen.
- Die erlaubten Felder stehen im Bundle, nicht in der Anfrage.
- Protokoll auf beiden Seiten: im Produkt als Vorgang, in Contao als
  Version.
- Im Contao-Backend abschaltbar, ohne Composer.

### 5.4 Wie es zum Kunden kommt

Nicht über Packagist. Ein eigener Composer-Speicher (Satis) hinter
Basis-Anmeldung; die Zugangsdaten sind der Lizenzschlüssel. Das Produkt
zeigt dem Benutzer die zwei Zeilen für seine `composer.json` und den
Befehl dazu. Abrufen kann das nur, wer das Produkt hat. Wer keinen
Composer-Zugriff hat, lädt an derselben Stelle ein ZIP.

Der Quelltext liegt in einem Git, aber in einem nicht öffentlichen.

### 5.5 Die Falle: live schreiben, wenn Git ausrollt

Wer Inhalte über Datenbankmigrationen aus dem Git ausrollt — so läuft es
bei NEO —, bekommt ein Problem: Eine Live-Änderung steht in der
Datenbank, nicht im Git, und der nächste Deploy überschreibt sie.

Regel dagegen: **Je Webseite wird festgelegt, welche Quelle führt.**

| Führend | Was das Produkt tut |
| --- | --- |
| Live | schreibt über das Bundle, Git bleibt außen vor |
| Git | schreibt nie live, immer als Zweig und Merge-Anfrage |
| beides | schreibt live **und** legt im selben Vorgang die Migration nach |

Der dritte Fall ist der bequemste und der teuerste. Er ist der Grund,
warum Git-Plugin und Contao-Bundle zusammengehören und keine
Alternativen sind.

### 5.6 WordPress braucht weniger

WordPress hat, was Contao fehlt: eine Inhalts-API im Kern
(`/wp-json/wp/v2/...`) mit Anwendungskennwörtern. Text in Beiträgen und
Seiten lässt sich damit ohne eigenes Plugin ändern.

Ein eigenes WordPress-Plugin lohnt erst dort, wo der Kern nicht
hinreicht: Seitenbaukästen wie Elementor oder Divi und Zusatzfelder legen
ihre Texte in Metafeldern ab, die die Kern-API nicht kennt.

Für den Vertrieb heißt das: WordPress ist billiger zu erreichen als
Contao und ist der weit größere Markt. Contao zuerst, weil es im Haus
eingesetzt wird; WordPress als Zweites, weil es verkauft.

## 6 KI-Anbindung

Der Kunde hinterlegt sein eigenes Modell. Vertrag dafür ist die
OpenAI-kompatible Chat-Schnittstelle: Basis-URL, Schlüssel, Modellname.
Alles andere wird darauf abgebildet.

| Anbieter | Weg |
| --- | --- |
| Requesty | OpenAI-kompatibel, EU-Modelle, ein Schlüssel für viele Modelle |
| OpenAI | unmittelbar |
| Azure OpenAI | OpenAI-kompatibel, eigene Basis-URL |
| andere Vermittler | OpenAI-kompatibel |
| eigener Server (Ollama, vLLM) | OpenAI-kompatibel |
| Anthropic | eigene Messages-API; über Requesty oder einen anderen Vermittler in OpenAI-Form erreichbar |

Ein Adapter, nicht zehn. Wer später die Messages-API unmittelbar
ansprechen will, schreibt einen zweiten Adapter — ein Plugin, kein Umbau.

Einstellbar je Mandant: Basis-URL, Schlüssel (im Tresor), Modell,
Höchstkosten je Vorgang. Der Betreiber setzt einen Standard, der Mandant
darf ihn überschreiben — dasselbe Muster wie bei den Schutzgrenzen.


## 7 Google Ads im Einzelnen

### 7.1 Mehrere Verwaltungskonten

Eine Agentur kann mehr als ein Verwaltungskonto (MCC) haben. Deshalb:

- Ein Verwaltungskonto ist ein eigener Datensatz mit eigenem
  OAuth-Zugang, eigener `login-customer-id` und eigener Zugriffsstufe.
- Ein Mandant hängt an einem Kundenkonto, das Kundenkonto an einem
  Verwaltungskonto.
- Schutzgrenzen gelten je Kundenkonto, unabhängig vom Verwaltungskonto.

Damit entfällt das Problem der zwei Anmeldungen: Der Mitarbeiter meldet
sich an der Plattform an, nicht bei Google.

### 7.2 Steuerung, ohne Google Ads zu öffnen

| Vorgang | Weg |
| --- | --- |
| Kundenkonto einladen | `CustomerClientLink`, Status `PENDING` |
| Einladung zurückziehen | derselbe Dienst, Status `CANCELED` |
| Verbindung trennen | Status `INACTIVE` |
| Unterkonten auflisten | GAQL auf `customer_client` |
| Kundenkonto neu anlegen | `CustomerService.CreateCustomerClient` |
| Benutzerzugriff einsehen | `customer_user_access` |

Jeder dieser Vorgänge ist freigabepflichtig, kein Knopf ohne Rückfrage.

### 7.3 Zugriffsstufen und der Keyword-Planer

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

## 8 Der Ablauf, um den herum gebaut wird

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

## 9 Stufenplan

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
- KI-Anbindung über eine OpenAI-kompatible Schnittstelle, Modell und
  Schlüssel je Mandant einstellbar
- Konsole
- Plugin-Lader mit den vier Andockpunkten — auch wenn es anfangs kein
  einziges Plugin gibt. Wer ihn später einzieht, baut die Basis um.

### Stufe 2 — danach

- Git-Plugin (GitHub und GitLab), zwei Merge-Stufen
- Contao-Plugin: den gefundenen Inhalt verstehen
- Contao-Bundle für Live-Textänderungen, samt Composer-Speicher hinter
  Lizenzanmeldung (Abschnitt 5)
- FTP/SFTP-Plugin
- Screenshots im Freigabeweg
- Keyword-Planer-Plugin und CSV-Import
- Verwaltungskonto-Steuerung: einladen, trennen, Konto anlegen
- Berichte

### Stufe 3 — bei Marktreife

- Marktplatz und Lizenzspeicher, Tarife, Testzeitraum
- WordPress: zuerst über die Kern-API, später ein eigenes Plugin für
  Seitenbaukästen und Zusatzfelder
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
- **Das Bundle legt keine Seiten an und löscht nichts.** Es ändert Text
  in vorhandenen Elementen, sonst nichts. Wer mehr will, nimmt Git.

## 10 Offene Entscheidungen

| Nr. | Frage | Vorschlag |
| --- | --- | --- |
| 1 | .NET 10 endgültig? Entscheidungsakte nach `neo-technologiewahl` | ja |
| 2 | Google Ads in der Basis oder als erstes Plugin? | Basis |
| 3 | Name und eigenes Repository für das Produkt | offen |
| 3a | Contao-Bundle offen oder nur für Kunden? | nur für Kunden |
| 3b | Führende Quelle je Webseite: Live, Git oder beides | je Webseite |
| 4 | Läuft das heutige Python-Werkzeug weiter, bis Stufe 1 steht? | ja, unverändert |
| 5 | Preise und Tarife | erst bei Marktreife |

## 11 Geltende Regeln

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
| `neo-contao`, `neo-php` | für das Contao-Bundle und das Contao-Plugin |
| `neo-betrieb`, `neo-deployment` | Auslieferung und Betrieb |
| `neo-recht` | Lizenz, Verkauf, Auftragsverarbeitung |
