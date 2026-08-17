# Research: Code Abundance — Taos ICM-2026-Argument, übertragen auf Coding-Agenten
<!-- doc: repo-only -->

## Übersetzungshinweis

Deutsche Fassung von
[`research-code-abundance-goals-and-values.md`](research-code-abundance-goals-and-values.md),
übersetzt vom Stand des Commits `b9fe31d` (17.08.2026). Maßgeblich ist die
englische Fassung. Weicht dieses Dokument von ihr ab, ist dieses Dokument
veraltet: Es ist eine Kopie im Sinne von
[`sdd/CONTENT-RULES.md`](../CONTENT-RULES.md) Regel 4, kein zweiter
Ursprungsort. Kein Mechanismus hält die beiden synchron. Wer die englische
Fassung ändert, muss diese Datei entweder mitziehen oder die Abweichung hier
vermerken.

Fachbegriffe bleiben englisch, weil sie Eigennamen bestimmter Quellen sind
(Storeys *cognitive debt*, Taos *Working Hypothesis*) und eine deutsche
Erfindung die Rückverfolgbarkeit zur Quelle zerstören würde. Bei der ersten
Verwendung steht eine deutsche Erläuterung daneben. Zitate stehen im englischen
Original mit anschließender deutscher Wiedergabe.

## Kontext

Terence Taos öffentlicher Vortrag auf dem Internationalen Mathematikerkongress
2026, _Mathematics in the age of AI_ (24. Juli 2026,
[Folien](https://teorth.github.io/tao-web/slides/age-of-ai-icm-2026.pdf)),
entfaltet ein Argument, dessen Form nicht spezifisch mathematisch ist. Dieser
Eintrag überträgt es auf die Softwareentwicklung mit Coding-Agenten, prüft jede
übertragene Behauptung an publizierter Evidenz, markiert die Stellen, an denen
die Analogie bricht, und leitet konkrete Vorschläge ab.

Die Übertragung lohnt sich, weil Taos Zug strukturell und nicht metaphorisch
ist. Er weigert sich, über Leistungsfähigkeit zu streiten, setzt sie
konditional voraus und fragt stattdessen, was die Gemeinschaft eigentlich will.
Das erweist sich als die schwierigere und deutlich vernachlässigtere Frage. Die
Softwareentwicklung hat dieselbe vernachlässigte Frage, eine isomorphe
Produktionskette und eine zusätzliche Stufe, die es in der Mathematik nicht
gibt.

**Quellenlage.** Die Folien Taos wurden vollständig aus dem PDF gelesen. Mehrere
der unten zitierten Primärquellen waren aus dieser Umgebung nicht erreichbar
(der Egress-Proxy sperrt `arxiv.org`, `dora.dev`, `martinfowler.com`,
`simonwillison.net`, `leidendeclaration.ai`, `flowverify.co`, `polvara.me`,
`queue.acm.org`). Die betreffenden Zahlen stammen aus Suchmaschinen-Extraktionen
der Primärdokumente, nicht aus den Dokumenten selbst, und sind in der Tabelle in
§ 4 entsprechend gekennzeichnet. Polvaras Essay wurde als Text von der Person
beigesteuert, die darauf hingewiesen hat; siehe die Anmerkung unter jener
Tabelle. Die Repo-Zahlen im Anhang wurden durch Ausführen des jeweils genannten
Befehls ermittelt.

## 1. Das Ausgangsargument

Taos Struktur, auf ihre tragenden Teile verdichtet.

1. **Die Frage zerlegen.** „Wie soll die mathematische Gemeinschaft auf moderne
   KI reagieren?" zerfällt in eine Teilfrage nach der Leistungsfähigkeit und
   eine dazu orthogonale Teilfrage nach Zielen und Werten. Nahezu die gesamte
   öffentliche Debatte spielt sich in der ersten ab.

2. **Konditionalisieren statt streiten.** Er formuliert eine _AI Capability
   Conjecture_ als Schablone voller Platzhalter („some AI tools will, at some
   expense, with some supervision, accomplish some research-level tasks…"),
   merkt an, dass die Evidenz durch Berichtsverzerrung und nicht offengelegte
   Kosten kontaminiert ist, und weigert sich dann, sie zu entscheiden. Er nimmt
   eine _Working Hypothesis_ (Arbeitshypothese) an, wonach eine hinreichend
   starke Form zutrifft, und bittet das Publikum um konditionales Argumentieren.
   „Evidence for or against the Working Hypothesis is orthogonal to the rest of
   my talk." Auf Deutsch: Evidenz für oder gegen die Arbeitshypothese steht
   orthogonal zum Rest des Vortrags.

3. **Fragen, was wir tatsächlich wollen.** Die _Goals and Values Question_ fragt
   nach den wirklichen Zielen, „not just the explicit goals that we communicate
   to the public (or to funding agencies), but also the implicit goals that we
   actually seek in practice" — also nicht nur nach den expliziten Zielen, die
   man der Öffentlichkeit oder Fördergebern kommuniziert, sondern auch nach den
   impliziten, die man in der Praxis tatsächlich verfolgt. Historisch waren
   diese Ziele positiv korreliert, sodass eines als Stellvertreter für die
   anderen dienen konnte und die meisten implizit bleiben durften.

4. **Goodhart zerreißt die Korrelation.** Unter starker Optimierung divergieren
   die Ziele. Tao nennt „the inherently ungrounded nature of generative AI, as
   well as the financial incentives of AI companies" als Gründe dafür, dass
   dieses Versagen besonders wahrscheinlich ist: die grundsätzliche
   Ungeerdetheit generativer KI und die finanziellen Anreize der KI-Unternehmen.

5. **Das Ziel verfeinern, bis es ehrlich ist.** Er iteriert das Ziel des
   Problemlösens viermal. Probleme lösen → und sie verifizieren → und sie klar
   kommunizieren → und sie verdauen, akzeptieren und in die maßgebliche Theorie
   des Fachs einarbeiten lassen. Jede Verfeinerung fügt eine Stufe der
   Produktionskette hinzu: Generierung, Verifikation, Darstellung
   (*exposition*), Publikation, Kanonisierung (*canonicalization*).

6. **Sehen, wo die Kette stockt.** Billige Generierung bei unveränderter
   nachgelagerter Kapazität erzeugt „impedance mismatches" (Impedanz-
   fehlanpassungen) beziehungsweise „proof indigestion" auf jeder Stufe:
   Beweise, die auf Verifikation warten; verifizierte Beweise, die auf eine
   lesbare Darstellung warten; korrekte und lesbare Beweise, die das Peer-Review
   überfluten; publizierte Beweise, die nie in eine maßgebliche Form gebracht
   werden. „We will transition from an era of proof scarcity to an era of proof
   abundance." Auf Deutsch: Wir gehen von einer Ära der Beweisknappheit in eine
   Ära des Beweisüberflusses über.

7. **Empfehlen.** Drei Dinge: die verantwortliche Offenlegung von KI-Unter-
   stützung normalisieren, statt sie in die Verdecktheit zu drängen; die
   Betonung von Generierung und Erstautorschaft hin zur Verdauung verschieben;
   und eine Faustregel — „if the authors cannot convincingly demonstrate that
   they can give a clear, expert-level talk on their results, that is correct
   and properly attributed, then the result should not be published." Auf
   Deutsch: Wer nicht überzeugend zeigen kann, dass er über sein Ergebnis einen
   klaren Fachvortrag halten kann, der korrekt ist und die Beiträge sauber
   zuordnet, sollte das Ergebnis nicht publizieren.

Zwei weitere Beobachtungen aus dem Vortrag übertragen sich ungewöhnlich gut.

- **Reibung ist Information.** Ein überpolierter Beweis stellt routinemäßige und
  schwierige Schritte als gleich leicht dar. Von Menschen geschriebene Beweise
  „retain some natural friction that prompts the reader to slow down", behalten
  also eine natürliche Reibung, die den Lesenden zum Langsamerwerden veranlasst.
  Aktuelle KI-Darstellung „dwells at length on trivialities, while passing very
  briefly through (or even obscuring) the most interesting and novel portions":
  sie verweilt ausführlich bei Trivialitäten und geht über die interessantesten
  und neuartigsten Teile sehr knapp hinweg oder verdeckt sie sogar.
- **Kanonische Arbeit ist das Substrat der Werkzeuge.** „The success of AI tools
  in mathematics crucially relies upon the canonical theories that human
  mathematicians have painstakingly built over the centuries." Der Erfolg der
  KI-Werkzeuge in der Mathematik beruht entscheidend auf den kanonischen
  Theorien, die Menschen über Jahrhunderte mühsam aufgebaut haben. Die
  langsamste, am wenigsten automatisierbare Stufe ist genau die, von der die
  Automatisierung abhängt.

## 2. Die Übertragung

### 2.1 Die Working Hypothesis für Software

In Taos Schablonenform:

> **Working Hypothesis (Software).** Coding-Agenten werden hinreichend bald in
> der Lage sein, einen hinreichenden Anteil produktiver Softwareentwicklungs-
> aufgaben zu erledigen, mit hinreichendem Erfolg, hinreichender Qualität,
> Aufsicht und Kosten.

Die erste Unähnlichkeit ist unmittelbar und wichtig: **In der Software ist diese
Hypothese weit weniger umstritten, und die Kontamination, vor der Tao warnt, ist
schlimmer.** Die Verbreitung ist nahezu vollständig. Der Stack Overflow
Developer Survey 2025 nennt 84 % der Entwickelnden, die KI-Werkzeuge nutzen oder
zu nutzen planen, gegenüber 76 % im Jahr 2024, während das Vertrauen in die
Gegenrichtung läuft: 46 % misstrauen der Korrektheit der Ausgaben, 29 %
vertrauen ihr. Die CloudBees-Erhebung 2026 unter 213 Technologieverantwortlichen
in Unternehmen berichtet, dass KI 61 % der durchschnittlichen
Unternehmens-Codebasis erzeugt oder mit erzeugt.

Die Software-Gemeinschaft hat die Working Hypothesis also faktisch bereits
angenommen, ohne je das Gespräch über Ziele und Werte geführt zu haben, das Tao
einfordert. Das ist die umgekehrte Reihenfolge zur Mathematik, und es ist der
zentrale Grund, warum das übertragene Argument dringlich statt spekulativ ist.

Auch die Kontaminationswarnung trifft härter. Tao merkt an, öffentliche Evidenz
zur Leistungsfähigkeit sei „highly subject to reporting bias and non-scientific
incentives, with some important costs and variables remaining undisclosed",
also stark von Berichtsverzerrung und unwissenschaftlichen Anreizen geprägt, bei
teilweise unveröffentlichten Kosten und Variablen. Das, was der
Softwareentwicklung einer kontrollierten Studie am nächsten kommt, fand das
Gegenteil des Marketings: Der randomisiert kontrollierte Versuch von METR (2025)
mit 16 erfahrenen Open-Source-Entwickelnden über 246 reale Aufgaben maß eine
_Verlangsamung_ um 19 % durch KI-Werkzeuge, während dieselben Personen im
Nachhinein eine Beschleunigung um 20 % schätzten. METR selbst führt das Ergebnis
inzwischen als historisch. Der Punkt ist nicht, dass es weiterhin gilt, sondern
dass eine Wahrnehmungs-Realitäts-Lücke von rund 39 Prozentpunkten überhaupt
messbar war und dass fast keine andere Behauptung zur Leistungsfähigkeit in der
Softwareentwicklung je so geprüft wurde.

### 2.2 Die Goals and Values Question für Software

> **Goals and Values Question (Software).** Was sind die genauen Ziele einer
> Softwareorganisation und der Praxis der Softwareentwicklung? Nicht nur die
> Ziele, die man der Geschäftsführung, dem Aufsichtsrat oder dem Markt nennt,
> sondern die impliziten, die tatsächlich verfolgt werden.

Eine ehrliche Liste, parallel zu Taos:

- Funktionierende Features an Nutzende ausliefern.
- Systeme bauen, die in fünf Jahren noch änderbar sind.
- Das System gut genug verstehen, um es im Störungsfall zu betreiben.
- Das System sicher und regelkonform halten.
- Ein Team aufbauen und halten.
- Die nächste Generation von Entwickelnden ausbilden.
- Zur Allmende beitragen (Bibliotheken, Standards, publiziertes Wissen).
- Artefakte von dauerhaftem handwerklichem Wert schaffen.

Wie in der Mathematik waren diese Ziele historisch korreliert. Das Schreiben des
Features _war_ der Weg, es zu verstehen; wer es verstand, war die Person, die es
betreiben konnte; und das Betreiben war der Weg, auf dem aus Junioren Seniores
wurden. Die Korrelation war so verlässlich, dass die Branche ihre Messinstrumente
darauf baute: Der *truck factor* schätzt vorhandenes Wissen, indem er den
Autorschafts-Fußabdruck misst, weil Code tippen und Code verstehen im Paket
kamen.

**Agenten zerlegen das Paket.** Das ist die softwarespezifische Form von Taos
Divergenzdiagramm, und sie ist präzise benannt worden: „The Substrate Collapse"
(arXiv 2606.20882) argumentiert, ein truck factor über einer von Agenten
geschriebenen Codebasis „still returns a number, and the number is meaningless —
not approximately, but in the precise sense that the thing it measures, the
distribution of authorship footprint, has stopped being correlated with the thing
it was used to estimate, the distribution of retained theory." Auf Deutsch: Er
liefert weiterhin eine Zahl, und die Zahl ist bedeutungslos, nicht näherungsweise,
sondern in dem genauen Sinn, dass das Gemessene, die Verteilung des
Autorschafts-Fußabdrucks, aufgehört hat, mit dem Geschätzten zu korrelieren, der
Verteilung der behaltenen Theorie. Der Mechanismus ist exakt Taos: „you couldn't
write a retry mechanism without briefly holding the failure modes in your head" —
man konnte keinen Wiederholungsmechanismus schreiben, ohne die Fehlerfälle kurz
im Kopf zu halten. Jetzt kann man es.

Die tiefe Fassung davon ist 40 Jahre alt. Peter Naurs _Programming as Theory
Building_ (1985) hält fest, dass nicht das Programm das Artefakt ist, sondern die
Theorie des Programms, die in den Köpfen der Bauenden sitzt. Code ist eine
Projektion der Theorie, und geht die Theorie verloren, wird der Code
unwartbar, unabhängig von seiner Qualität. Naurs Argument läuft über den
Vergleich zweier Teams, die einen Compiler bauen: Die Gruppe, die ihn von Grund
auf gebaut hatte, konnte ihn sicher erweitern; eine zweite Gruppe, der der
fertige Code _und_ eine vollständige Dokumentation übergeben wurde, konnte es
nicht, weil die Theorie die Übersetzung in Text nicht überlebt. Seine
Schlussfolgerung, dass man die Theorie nur durch aktive Mitarbeit an der
Entwicklung erwirbt, ist das genaue Software-Gegenstück zu Taos Kanonisierungs-
stufe: der langsamste, am wenigsten automatisierbare und wertvollste Schritt.

### 2.3 Drei Schulden, nicht eine

„Verstehen" ist keine einzelne Größe, und sie als eine zu behandeln verdeckt die
Gegenmittel. Margaret-Anne Storeys _triple debt model_ („From Technical Debt to
Cognitive and Intent Debt: Rethinking Software Health in the Age of AI", arXiv
2603.22106 / ACM Queue, 2026) zerlegt sie in drei Schichten, die unabhängig
voneinander versagen:

| Schuld | Wo sie sitzt | Was fehlt | Taos Stufe |
|---|---|---|---|
| Technical debt | Im Code | Modularität, Kohärenz, saubere Abhängigkeiten | Verifikation |
| Cognitive debt | In den Menschen | Geteiltes Verständnis, wie das System funktioniert | Kanonisierung |
| Intent debt | In externalisierten Artefakten | Das festgehaltene _Warum_: Ziele, Randbedingungen, Entscheidungsgeschichte | Darstellung |

Nützlich ist vor allem die Zuordnung zu Taos Produktionskette aus § 2.5. Sie
besagt, dass die drei Schulden nicht drei Sichten auf ein Problem sind, sondern
drei verschiedene Stufenversagen mit verschiedenen Gegenmitteln: **Technical debt
wird durch Refactoring getilgt, cognitive debt allein durch Beteiligung, und
intent debt allein durch Aufschreiben.** Nichts, was man am Code tut, tilgt die
beiden anderen.

**Intent debt ist der Begriff, der Taos Rahmen fehlt, und er ist
agentenspezifisch.** Taos Sorge bei der Darstellung ist, dass ein menschlicher
Leser durch überpolierte Prosa in die Irre geführt wird. Intent debt ist auf eine
Weise schlimmer, für die die Mathematik kein Gegenstück hat: Die nie
externalisierte Begründung ist dem Agenten nicht bloß nicht verfügbar, der Agent
_erfindet einen Ersatz_. Eine ungenannte Randbedingung wird nicht als Lücke
gelesen, sie wird mit der statistisch plausibelsten Annahme gefüllt. So wird eine
seltene finanzielle Schutzmaßnahme „wegoptimiert". Eine Begründung, die im Kopf
einer erfahrenen Person sitzt, zählt nicht, denn ein Modell kann keine Köpfe
lesen. Das ist ein erheblich härteres Argument für Architecture Decision Records
als das pädagogische, und es ist der Grund, warum Intent-Dateien nach Art von
`AGENTS.md` tragend sind und nicht Höflichkeitsdokumentation.

**Warum die Reibung wichtig war.** Giorgio Polvaras Essay _The Persistence of
Theory_ (19. Juni 2026), über den dieses Modell in diesen Eintrag gelangt ist,
liefert den Mechanismus über Brooks' Unterscheidung zwischen akzidenteller und
essenzieller Komplexität. Agenten sind ein Killer akzidenteller Komplexität: Sie
beseitigen die Reibung von Syntax, Projektaufsetzen und Bibliotheksarchäologie
und lassen die essenzielle Schwierigkeit unberührt, nämlich zu entscheiden, was
gebaut werden soll. Der Haken ist, dass **die Reibung dem theory building nicht
äußerlich war, sondern der Vorgang, durch den die Theorie entstand.** Das Ringen
mit der API einer Bibliothek war der Weg, auf dem das mentale Modell dieser
Bibliothek entstand. Nimmt man die Reibung weg, kommt der Code ohne dieses Modell
an. Das ist eine stärkere Behauptung als Taos, dessen Reibungsargument den
Lesenden zum Langsamerwerden bringen soll. Hier ist die Reibung für die
schreibende Seite tragend.

**Die Messung existiert, und sie ist die beste Evidenz in diesem Eintrag.**
Anthropics randomisiert kontrollierter Versuch (veröffentlicht am 29. Januar
2026) setzte 52 Juniorentwickelnde an eine unbekannte Python-Bibliothek, Trio,
mit und ohne KI-Unterstützung. Die KI-Gruppe erreichte im anschließenden
Verständnistest im Mittel 50 % gegenüber 67 % der handschreibenden Gruppe, eine
Lücke von 17 Punkten, wobei das Debugging am stärksten abfiel. Dabei war sie nur
etwa zwei Minuten schneller, ein Unterschied ohne statistische Signifikanz.
Tempo brachte nichts und kostete Verständnis.

Wichtiger als die Schlagzeile ist das Ergebnis zum Interaktionsmuster.
Teilnehmende, die die KI für konzeptionelle Fragen und Erklärungen nutzten,
erreichten 65 % oder mehr; wer die Codeerzeugung vollständig delegierte, lag
unter 40 %. **Nicht das Werkzeug entschied das Ergebnis, sondern die Art der
Nutzung.** Das ist die stärkste verfügbare Evidenz für die Vortragsregel in § 6,
denn sie zeigt, dass die Verständniskosten vermeidbar und nicht wesensmäßig sind.
Und es ist ein direkt gemessenes Verständnisergebnis, also genau das Instrument,
dessen Fehlen dieser Eintrag der Branche vorhält.

Der Technology Radar Vol. 34 von Thoughtworks (April 2026) setzt _codebase
cognitive debt_ auf **Hold** und definiert sie als „the growing gap between a
system's implementation and a team's shared understanding of how and why it
works", also als die wachsende Lücke zwischen der Implementierung eines Systems
und dem geteilten Verständnis eines Teams davon, wie und warum es funktioniert.
Dasselbe Versagen, benannt von einem Praktikerhaus statt von der Forschung.

**Eine Behauptung im Modell ist nicht gedeckt.** Polvaras Darstellung der Tabelle
hält fest, generative KI _verringere_ technical debt, indem sie Refactoring und
Testschreiben automatisiere. Die Evidenz in § 3 sagt für die Codeschicht das
Gegenteil: Duplikation verachtfacht, refaktorierte Zeilen von 24,1 % auf 9,5 %
gefallen, Sicherheits-Bestehensquoten unverändert bei rund 55 %. Der Essay
widerspricht sich hier selbst und führt die Verdopplung des Churn und das
Überholen des Refactorings durch Copy-Paste in einem späteren Abschnitt an. Die
Dreiteilung überlebt das; die Behauptung, eine Schicht heile sich nun selbst,
nicht. Richtig gelesen verschlimmert KI _alle drei_ Schulden, und nur die
kognitive und die intentionale Schicht sind neu.

**Das Modell ist diagnostisch, und seine Gegenmittel sind Tilgungsmittel.** Das
ist seine wesentliche Beschränkung, und sie zu korrigieren ist das Nützlichste,
was dieser Eintrag beitragen kann. Storey und Polvara beantworten die Frage
„was tut man gegen die Schuld" beide mit Arbeit, die nach dem Entstehen der
Schuld geleistet wird: Architecture Decision Records schreiben, Pair Programming
betreiben, KI-freie Kontrollpunkte einplanen, den Code einer Kollegin erklären.
Das sind Rückzahlungen. Sie setzen voraus, dass die Schuld aufgenommen wurde und
nun bedient wird.

Es gibt eine dritte Haltung, die das Modell nicht benennt: **den Arbeitsablauf so
anordnen, dass die Schuld gar nicht erst aufgenommen werden kann.** Prävention
unterscheidet sich von Tilgung darin, was sie festlegt. Sie fixiert die
_Reihenfolge_ der Schritte, statt eine spätere Pflicht hinzuzufügen:

| Schuld | Tilgungsmittel | Präventive Kontrolle |
|---|---|---|
| Technical | Refactoring-Sprints, Aufräum-Backlogs | Merge-Gates: Konformitätssuiten, Coverage-Untergrenzen, Mutationstests |
| Intent | Das ADR hinterher schreiben | Das _Warum_ wird verlangt, bevor der Code existiert: keine Implementierung ohne Spec-Abschnitt, Entscheidungsprotokolle nach Annahme unveränderlich |
| Cognitive | Pair Programming, KI-freie Kontrollpunkte, Erklären an Kollegen | Die Beteiligung im Ablauf selbst vorschreiben: den Fehler reproduzieren und den Test scheitern sehen, bevor korrigiert wird; die Ripple-Menge der Änderung vor Beginn lesen; Verhalten durch Ausführen prüfen, nie durch Typprüfung |

**Bei cognitive debt ist der Unterschied keine Vorliebe. Er ist die ganze
Partie.** Die drei Schulden unterscheiden sich darin, ob sie spät bedient werden
können, und das ist die Asymmetrie, die keine der beiden Quellen herausarbeitet.
Technical debt ist voll rückzahlbar: Schlecht geformter Code kann zu jedem
späteren Zeitpunkt in Form gebracht werden, von jemandem, der das Original nie
gesehen hat. Intent debt ist teilweise rückzahlbar: Begründungen lassen sich
nachträglich rekonstruieren, verlustbehaftet, aber rekonstruieren. **Cognitive
debt ist überhaupt nicht rückzahlbar, weil es keine spätere Handlung gibt, die
bewirkt, dass man etwas in dem Moment verstanden hat, in dem man es brauchte.**
Das Fenster, in dem die Theorie hätte entstehen können, war das Fenster, in dem
die Arbeit geschah. Ist es zu, bleibt keine zu bedienende Schuld, sondern eine
Tatsache über das System: Niemand hält seine Theorie.

Deshalb ist die präventive Spalte die tragende, und sie deckt sich mit der
Evidenz, statt bloß ordentlicher zu sein. Der Anthropic-Versuch fand das
Verständnisergebnis durch die Art der Nutzung bestimmt, nicht durch den Zugang
zum Werkzeug, also dadurch, _wie die Arbeit während ihres Vollzugs geordnet
war_. Genau das legt eine präventive Kontrolle fest, und genau dorthin reicht
kein späteres Gegenmittel. Naur kommt vom anderen Ende zum selben Ergebnis: Die
Theorie wird nur durch aktive Mitarbeit an der Entwicklung erworben, was eine
Aussage darüber ist, wann Verstehen entsteht, und nicht darüber, welche Dokumente
danach existieren.

### 2.4 Goodhart, angewandt

Jede herkömmliche Entwicklungsmetrik misst Menge, Tempo oder Frequenz
menschlicher Anstrengung, und jede davon kann ein Agent nun ohne entsprechenden
Wert aufblähen: Codezeilen, Commit-Zahl, PR-Zahl, Story Points und neuerdings
Token-Verbrauch, in der bereits benannten Praxis des „tokenmaxxing". Taos
Formulierung gilt wörtlich: Wird ein Maß zum Ziel, hört es auf, ein gutes Maß zu
sein. Die Ungeerdetheit generativer KI und die finanziellen Anreize der Anbieter
machen Software dafür ungewöhnlich anfällig.

Bemerkenswert ist, dass die DORA-Metriken teilweise überleben, weil zwei von
ihnen, Änderungsfehlerrate und Wiederherstellungszeit, Ergebnisse statt
Anstrengung messen. Das ist das Unterscheidungsmerkmal: **Metriken, die messen,
was infolge der Arbeit geschah, überleben; Metriken, die messen, wie viel Arbeit
geschah, nicht.**

### 2.5 Die Produktionskette, mit einer zusätzlichen Stufe

| Taos Stufe | Software-Entsprechung | Was sie hervorbringt |
|---|---|---|
| Beweisgenerierung | Codegenerierung | Ein unverifizierter Diff |
| Beweisverifikation | Tests, Typen, CI, statische Analyse, formale Methoden | Ein Diff, der seine Prüfungen besteht |
| Beweisdarstellung | Commit-Nachrichten, PR-Beschreibungen, Dokumentation, Kommentare, ADRs | Ein Diff, dem ein Reviewer folgen kann |
| Beweispublikation | Code-Review und Merge | Ein Diff im Hauptzweig |
| — | **Betrieb** | Ein Diff, der in Produktion läuft, unter jemandes Rufbereitschaft |
| Beweiskanonisierung | Die geteilte Theorie des Teams: Architektur, Konventionen, Bibliotheken, Einarbeitungsmaterial | Eine Änderung, aufgenommen in das Verständnis des Systems |

Die zusätzliche Stufe ist der größte strukturelle Unterschied, und sie fällt zu
Ungunsten der Software aus. Ein publizierter Beweis, den niemand ganz versteht,
liegt reglos in der Literatur; er weckt niemanden um drei Uhr nachts. Software
tut das. Eine Fachperson, die in der Rufbereitschaftsliteratur 2026 zitiert wird,
formuliert es genau: „the team's ratio of 'code in production' to 'code we
understand deeply enough to debug under pressure' has shifted, and it's shifted
in the wrong direction for incident response." Das Verhältnis von Code in
Produktion zu Code, den man tief genug versteht, um ihn unter Druck zu
debuggen, hat sich verschoben, und zwar in die für die Störungsbearbeitung
falsche Richtung.

Tao fragt für die Mathematik: „Could we have a verified proof of a major result
that no human understands enough to explain it?" Könnten wir einen verifizierten
Beweis eines bedeutenden Resultats haben, den kein Mensch gut genug versteht, um
ihn zu erklären? Die Software-Fassung ist weder hypothetisch noch rhetorisch:
**Wir betreiben bereits Systeme, die niemand gut genug versteht, um sie zu
erklären, und sie fallen aus.**

## 3. Impedance mismatch, Stufe für Stufe

Taos Vorhersage lautet, dass bei billiger Generierung jede nachgelagerte Stufe
stockt. In der Software ist das keine Vorhersage. Für jede Stufe gibt es
gemessene Evidenz.

**Generierung ist billig und wird billiger.** Das ist die Prämisse, und sie ist
erfüllt.

**Verifikation ist teilweise billig, und das ist eine Falle.** Der echte Vorteil
der Software gegenüber der Mathematik ist ein ausgereifter Bestand partieller
Orakel: Tests, Typen, CI, Fuzzing, statische Analyse. Ihre Abdeckung ist jedoch
schmaler, als sie aussieht. Veracodes GenAI Code Security Report (2025, 80
kuratierte Aufgaben über mehr als 100 Modelle) fand, dass Modelle bei freier Wahl
in 45 % der Fälle die unsichere Umsetzung wählten; das Update Frühjahr 2026
nennt eine syntaktische Korrektheit über 95 % bei Sicherheits-Bestehensquoten um
55 %, über zwei Jahre praktisch unverändert. Das tiefere Problem ist das
**oracle problem** (Orakelproblem): Schreibt derselbe Agent den Code und seine
Tests, optimieren die Tests auf Bestehen statt auf Korrektheit, und die
Verifikationsstufe entartet still zu einer zweiten Generierungsstufe.

**Die Darstellung verfällt genau so, wie Tao es beschreibt.** Seine Klage über
KI-geschriebene Beweise, makellose Oberfläche, unverhältnismäßige Aufmerksamkeit
für Trivialitäten, kein Bezug zur Vorliteratur, hat eine direkte Messung. Eine
Untersuchung von 23.247 agentengeschriebenen Pull Requests über fünf Agenten
(MSR 2026) fand, dass unter den stark inkonsistenten PRs das häufigste Versagen
„Beschreibung behauptet nicht implementierte Änderungen" war (45,4 %), gefolgt
von Untertreibung des Umfangs (22,0 %) und Platzhalterbeschreibungen (18,8 %).
Diese PRs hatten eine um 51,7 Prozentpunkte geringere Annahmequote (28,3 %
gegenüber 80,0 %) und brauchten das 3,5-Fache an Zeit bis zum Merge. Agenten
schreiben auf Commit-Ebene bessere Nachrichten als Menschen und auf PR-Ebene
schlechtere Zusammenfassungen. Sie sind also gut in lokaler Beschreibung und
schlecht darin, zu sagen, was die Änderung bedeutet, was Taos Klage in anderer
Form ist.

**Die Publikation ist der sichtbare Stau.** Hier ist die Verdauungsstörung der
Software am lautesten. Berichtete Telemetrie 2026: mediane Review-Zeit um 441,5 %
gestiegen über 22.000 Entwickelnde (Faros AI) gegenüber einem Aufgabendurchsatz
von plus 33,7 %; KI-unterstützte PRs rund 2,5-mal größer und mit etwa 5-mal
längerer Wartezeit auf Reviewende über 8,1 Millionen PRs (LinearB); Durchsatz auf
Feature-Zweigen im Jahresvergleich plus 59 %, während der Durchsatz auf dem
_Hauptzweig_ im Median der Teams fiel (CircleCI). Dieses letzte Paar ist der
impedance mismatch in einer einzigen Statistik: mehr Arbeit fließt in die
Leitung, weniger kommt heraus.

Im Open Source hat der Stau bereits Dinge zerstört. Das Jazzband-Kollektiv
stellte den Betrieb ein und nannte untragbare Mengen KI-erzeugter Spam-PRs und
Issues als Grund; Godot-Maintainer beschreiben die Triage von KI-Schrott als
demoralisierend; curl beendete sein Bug-Bounty-Programm, weil es zum Magneten
für Einreichungen mit geringem Aufwand wurde. Der Mechanismus verdient eine
präzise Benennung, weil er allgemeiner ist als KI: **Agentische Generierung
beseitigt den aufwandsbasierten Gegendruck, der Einreichungen geringer Qualität
bislang selbstbegrenzend machte.** Peer-Review war nie als Filter entworfen; es
funktionierte, weil das Erstellen einer Einreichung teuer war.

**Der Betrieb verfällt.** CloudBees (2026, n = 213): 81 % der
Technologieverantwortlichen berichten von Produktionsproblemen im Zusammenhang
mit KI-erzeugtem Code. Der DORA-Bericht 2025 (n ≈ 5.000 Fachleute) findet
KI-Einsatz gleichzeitig mit erhöhtem Durchsatz _und_ erhöhter Instabilität der
Auslieferung verbunden. Eine Lightrun-Erhebung (April 2026) nennt 43 % der
KI-erzeugten Codeänderungen, die in Produktion debuggt werden müssen.

**Die Kanonisierung verfällt am stärksten, und leise.** GitClears Auswertung von
211 Millionen geänderten Zeilen (Januar 2020 bis Dezember 2024) fand einen
Rückgang refaktorierter, also verschobener Zeilen von 24,1 % auf 9,5 % der
Änderungen, eine Verachtfachung duplizierter Codeblöcke im Jahr 2024 und einen
Anstieg des innerhalb von zwei Wochen nach dem Commit überarbeiteten Codes von
3,1 % auf 5,7 %. Vor Taos Folie gelesen sind das keine Codequalitätszahlen.
Refactoring und Konsolidierung _sind_ Kanonisierung: der Akt, eine Lösung in die
maßgebliche Form des Systems zu bringen. Ein gemessener Einbruch des
Refactoring-Anteils ist ein gemessener Einbruch jener Stufe, die Tao „the most
valuable part of the entire process" nennt, den wertvollsten Teil des ganzen
Vorgangs.

Die Architekturforschung kommt aus anderer Richtung an denselben Ort: Agenten
erreichen strukturelle Modularität und scheitern an semantischer Kohäsion, was
eine „modular mirage" erzeugt, in der Dateitrennung nicht logischer Trennung
entspricht (arXiv 2605.02741).

**Und die Substratabhängigkeit gilt.** Taos Beobachtung, dass KI-Mathematik von
mühsam kanonisierter menschlicher Theorie abhängt, hat ein direktes
Software-Gegenstück: Agenten arbeiten deutlich besser mit verbreiteten, gut
dokumentierten Bibliotheken, die in den Trainingsdaten dicht vertreten sind, und
verwenden Nischenbibliotheken oder neue Bibliotheken falsch. Für Menschen
geschriebene Dokumentation reicht dafür oft nicht. Das ist das schärfste
praktische Argument dagegen, die Kanonisierung verfallen zu lassen: **Die Stufe,
die die Agenten nicht leisten können, ist die Stufe, die bestimmt, wie gut die
Agenten arbeiten.**

## 4. Zahlen und ihre Herleitung

Gemäß [`CLAUDE.md` Prinzip 9](../../CLAUDE.md#principles) nennt jede Zahl ihre
Quelle. „Extraktion" bedeutet, dass das Primärdokument aus dieser Umgebung nicht
erreichbar war und die Zahl aus einer Suchmaschinen-Extraktion davon stammt.

| Zahl | Quelle | Stichprobe / Datum | Zugang |
|---|---|---|---|
| 19 % Verlangsamung; 20 % wahrgenommene Beschleunigung | METR-RCT | 16 Entwickelnde, 246 Aufgaben, Juli 2025 | Extraktion |
| 84 % nutzen/planen KI; 46 % misstrauen; 66 % „fast richtig"; 45 % verlieren Zeit beim Debuggen | Stack Overflow Developer Survey 2025 | veröffentlicht Dez. 2025 | Extraktion |
| 61 % der Unternehmens-Codebasis KI-geschrieben; 81 % berichten Produktionsprobleme | CloudBees State of Code Abundance | n = 213 Führungskräfte, Mai 2026, ±8 % | Extraktion |
| Durchsatz und Instabilität steigen gemeinsam; sieben Fähigkeiten | DORA State of AI-assisted Software Development 2025 | rund 5.000 Fachleute | Extraktion |
| Review-Zeit +441,5 %; Durchsatz +33,7 % | Faros AI, Telemetrie 2026 | 22.000 Entwickelnde | Extraktion (sekundär) |
| PRs 2,5-mal größer, 5-mal längere Wartezeit | LinearB-Benchmarks | 8,1 Mio. PRs, 2026 | Extraktion (sekundär) |
| Durchsatz Feature-Zweige +59 %, Hauptzweig fällt | CircleCI, Daten 2026 | — | Extraktion (sekundär) |
| Refactoring 24,1 % → 9,5 %; Duplikation 8-fach; Churn 3,1 % → 5,7 % | GitClear AI Code Quality | 211 Mio. Zeilen, Jan. 2020 bis Dez. 2024 | Extraktion |
| 45 % unsichere Wahl; rund 55 % Sicherheits-Bestehensquote | Veracode GenAI Code Security 2025 / Frühjahr 2026 | 80 Aufgaben, über 100 Modelle | Extraktion |
| 1,7 % stark inkonsistente PRs; 45,4 % behaupten nicht implementierte Änderungen; 28,3 % gegen 80,0 % Annahme; 3,5-fache Merge-Zeit | Message-Code-Inconsistency-Studie (arXiv 2601.04886) | 23.247 agentische PRs, 5 Agenten, 974 annotiert | Extraktion |
| 43 % der KI-Änderungen brauchen Debugging in Produktion | Lightrun-Erhebung | April 2026 | Extraktion (sekundär) |
| 50 % gegen 67 % Verständnis; 17 Punkte Lücke; rund 2 Min. schneller, nicht signifikant; 65 %+ bei konzeptionellen Fragen gegen unter 40 % bei Delegation | Anthropic, „How AI assistance impacts the formation of coding skills" | RCT, 52 Juniorentwickelnde, veröffentlicht 29.01.2026 | Extraktion |
| _Codebase cognitive debt_ auf Hold | Thoughtworks Technology Radar Vol. 34 | April 2026 | Extraktion |
| Triple debt model | Storey, arXiv 2603.22106 / ACM Queue | analytisch, 2026 | Extraktion, erreicht über Polvara (unten) |
| Argument zur Entwertung des truck factor | „The Substrate Collapse" (arXiv 2606.20882) | analytisch, Juni 2026 | Extraktion |
| Modular mirage | arXiv 2605.02741 | 2026 | Extraktion |
| SDD-Artefaktzahlen | dieses Repository | `ls`-Befehle im Anhang | direkt |

Eine Zeile braucht statt einer Zitation die Angabe ihrer Herkunft. Polvaras Essay
ist aus dieser Umgebung nicht erreichbar. `polvara.me` liefert unter der
Egress-Richtlinie der Organisation 403, ebenso `queue.acm.org`, `arxiv.org` und
`margaretstorey.com`, und die Suche indexiert ihn nicht. Der hier verwendete Text
wurde direkt von der Person beigesteuert, die auf ihn hingewiesen hat, und seine
Behauptungen wurden vor der Verwendung gegen unabhängig erreichbare Quellen
geprüft: Die Zeilen zu Anthropic und Thoughtworks wurden so verifiziert, und eine
Behauptung des Essays wurde auf dieser Grundlage zurückgewiesen (§ 2.3, letzter
Absatz). Seine eigene Fußzeile hält fest, dass er mit einem
KI-Deep-Research-Werkzeug recherchiert und von seinem Autor redigiert wurde, was
ein Grund für die Prüfung ist und kein Einwand gegen den Essay.

Vier Vorbehalte zu dieser Tabelle. Die Zeilen zu Faros, LinearB, CircleCI und
Lightrun sind Anbietertelemetrie, berichtet über einen sekundären Aggregator, und
Anbieter von Review-Werkzeugen haben ein Interesse an einer Review-Krise. Die
GitClear-Korrelation ist zeitlich, nicht kausal; in 2020 bis 2024 fallen auch ein
Einstellungseinbruch und ein Zinszyklus. Der Anthropic-Versuch ist
anbieterpublizierte Forschung über die eigene Produktkategorie und klein (52
Junioren, eine unbekannte Bibliothek, eine Aufgabe); mildernd wirkt, dass sein
Hauptergebnis gegen das kommerzielle Interesse des Publizierenden läuft, was die
seltenere Richtung der Verzerrung ist. Und Taos eigene Warnung gilt für die ganze
Tabelle: Dies ist weitgehend unkontrollierte Evidenz, erhoben unter kommerziellen
Anreizen. Sie ist konsistent, was etwas wert ist, aber Konsistenz über verzerrte
Quellen hinweg ist schwächer, als sie sich anfühlt.

## 5. Wo die Analogie bricht

Treue verlangt, die Unähnlichkeiten zu markieren, und fünf davon wiegen schwer
genug, um die Empfehlungen zu verändern.

**Das Peer-Review der Software ist weit schwächer als das der Mathematik.** Tao
kann sich auf Herausgeber, Gutachter und die Annahme durch die Gemeinschaft als
Rückhalt stützen, der „cannot be optimized purely by the authors and their AI
tools", also nicht allein von Autoren und ihren KI-Werkzeugen wegoptimiert werden
kann. Das Software-Gegenstück ist typischerweise eine Kollegin unter Termindruck,
in einem privaten Repository, ohne externen Nachweis und ohne Gutachten. Wo Tao
befürchtet, KI-Ausstoß werde das Peer-Review _überfluten_, war das Review der
Software schon vorher das schwache Glied. Die Daten von 2026 zeigen, dass
Reviewende agentengeschriebene PRs bereitwilliger freigeben, obwohl diese im
Mittel mehr technical debt tragen. **Der Rückhalt, auf den Tao sich stützt,
existiert in der Software nicht in vergleichbarer Stärke. Software kann seine
Fassung des Problems also nicht dadurch lösen, dass es nur das Review schützt.
Es muss eine Kapazität aufbauen, die die Mathematik bereits hatte.**

**Software hat billige partielle Orakel, die Mathematik nicht.** Das ist der
echte Vorteil der Software, und er sollte entschieden genutzt werden. Eine
Testsuite ist eine schwächere Garantie als ein Lean-Beweis, aber unvergleichlich
billiger als ein Gutachter, und sie läuft für immer bei jeder Änderung. Die
Forschung zu formalen Methoden konvergiert 2026 darauf, Verifizierer als
Grundwahrheits-Orakel zu nutzen, gerade weil KI-erzeugte Tests die blinden
Flecken des Erzeugers erben. Die strategische Folgerung: Software sollte in die
Stufe investieren, in der es einen Vorteil gegenüber der Mathematik hat, statt
deren gutachterzentrierte Antwort unbesehen zu übernehmen.

**Software ist löschbar, Mathematik ist kumulativ.** Ein falscher Beweis
verunreinigt die Literatur dauerhaft; falscher Code kann zurückgenommen werden.
Das schneidet in beide Richtungen, und die zweite ist schlimmer:
zurückgenommener Code ist trotzdem gelaufen, hat trotzdem Daten preisgegeben,
trotzdem Geld gekostet. Die Fehler der Software sind billiger zu _entfernen_ und
teurer zu _machen_.

**Der Verständnisverlust der Software verstärkt sich selbst, der der Mathematik
nicht.** Das ist die Unähnlichkeit mit den schärfsten Folgen, und sie stammt aus
dem Schuldenmodell in § 2.3. Cognitive debt nährt sich selbst: Code kommt
schneller an, als das Team Theorie bilden kann; die dünnere Theorie macht das
Team weniger fähig, ohne Unterstützung zu arbeiten; und die Antwort darauf, ohne
Unterstützung weniger arbeitsfähig zu sein, ist, mehr zu delegieren. Die
Mathematik hat keine vergleichbare Schleife. Wer den letzten KI-gestützten Beweis
weniger verstanden hat, wird dadurch nicht abhängiger von KI für den nächsten;
der Beweis ist ein terminales Artefakt, und der Kanon des Fachs ist öffentlich
und geteilt. Eine Codebasis wird fortlaufend von derselben kleinen Gruppe wieder
betreten, sodass jede Delegationsrunde die Kosten der nächsten nicht delegierten
Runde erhöht.

Die praktische Folge ist, dass Taos Gradualismus sich nicht überträgt. Er kann
die Verdauungsstörung als Rückstand beschreiben, der sich anhäuft und mit
Richtlinienänderungen abgearbeitet werden kann. Eine positive Rückkopplung lässt
sich nicht später mit denselben Mitteln abarbeiten; sie muss gedämpft werden,
solange das Team noch die Fähigkeit zum Dämpfen hat.

Zusammen mit dem Argument zur Nichtrückzahlbarkeit in § 2.3 entscheidet das die
Wahl zwischen den beiden Haltungen, statt sie dem Geschmack zu überlassen.
Cognitive debt ist die eine Schuld, die von selbst wächst _und_ nicht rückwirkend
bedient werden kann. Gegen eine Größe mit beiden Eigenschaften sind
Tilgungsmittel nicht die schwächere Option gegenüber präventiven Kontrollen, sie
sind keine Option. Prävention ist die einzige Kontrolle, die innerhalb des
Fensters wirkt, in dem das Ergebnis noch bestimmt wird. Das ist eine stärkere
Behauptung als „Prozessdisziplin ist gute Praxis" und der Grund, warum dieser
Eintrag die Anordnung des Arbeitsablaufs als technische Kontrolle behandelt und
nicht als kulturelle Vorliebe.

**Agenten können die Theorie nicht halten, und das ist strukturell und keine
Fähigkeitslücke.** Ein verlockender Ausweg aus alledem wäre, dass Agenten die
Theorie stattdessen halten. Sie bilden durchaus eine: Ein Coding-Agent stellt
Hypothesen auf, prüft sie und überarbeitet sein Modell eines Systems, was
erkennbar theory building ist. Aber sie sind Amnestiker. Die Theorie lebt in
einem flüchtigen Kontextfenster und wird in jeder Sitzung neu aufgebaut, und
Sitzungszusammenfassungen sind verlustbehaftete Kompressionen genau jenes
impliziten Gehalts, der laut Naur die Übersetzung in Text nicht überlebt.
Schlimmer noch: Getrennt arbeitende Agenten bilden subtil unvereinbare lokale
Theorien desselben Systems, was Architekturdrift aus einer neuen Richtung ist.

Deshalb rettet die Working Hypothesis aus § 2.1 das Argument nicht. Ein stärkerer
Agent schreibt besseren Code; er sammelt nicht die sitzungs- und
agentenübergreifende geteilte Theorie an, aus der Taos Kanonisierungsstufe
besteht. Die Stufe bleibt konstruktionsbedingt menschlich, nicht aufgrund
gegenwärtiger Beschränkungen.

Eine Einschränkung, aus einem Versuch mit dem Verfasser dieses Eintrags selbst,
berichtet im Anhang. Amnesie begrenzt, was ein Agent _behält_; sie begrenzt
nicht, wie billig die Theorie zu Sitzungsbeginn _wiederaufgebaut_ werden kann,
und diese Kosten sind eine Eigenschaft der Artefakte und nicht des Agenten. Wo
die festgehaltene Begründung an den Stellen sitzt, an denen die Argumentation
strittig war, ist der Wiederaufbau schnell genug, um die Ökonomie seiner
Einforderung zu verändern. Die Stufe bleibt menschlich, denn nichts hiervon
sammelt sich über Sitzungen hinweg an, aber die Rekonstruktionskosten sind eine
Entwurfsgröße und keine Konstante.

**Verstehen ist in der Software instrumentell und in der Mathematik final, aber
der Unterschied ist dünner, als er zunächst wirkt.** Thurstons Satz, den Tao
zitiert, „the measure of our success is whether what we do enables people to
understand and think more clearly", macht das Verstehen zum Produkt: Das Maß
unseres Erfolgs ist, ob das, was wir tun, Menschen befähigt, klarer zu verstehen
und zu denken. In der Software ist das Produkt funktionierende Systeme, und
Verstehen ist ein Mittel. So weit trägt es, und das ist der ehrliche Grund,
warum Teams versucht sein werden, die Verdauungsstufe zu überspringen: Sie
können es, eine Zeit lang.

Ein früherer Entwurf dieses Eintrags hörte hier auf. Das war zu sauber. Angesichts
der obigen Rückkopplung ist Verstehen in der Software nicht bloß eine Eingabe
unter anderen, die gegen Liefergeschwindigkeit eingetauscht werden kann. Es ist
die Größe, die bestimmt, ob die Delegationsschleife stabil oder divergent ist.
Ein Mittel, das man auf null herunterfahren kann und trotzdem ein System hat, ist
instrumentell. Ein Mittel, dessen Abbau seinen eigenen Abbau beschleunigt, ist
eine Regelgröße und muss als solche geführt werden. Das Argument, die Verdauung
nicht zu überspringen, ist deshalb stärker als „Änderung, Störungsbearbeitung,
Sicherheitsprüfung und Audit lösen alle Verstehen ein, und sie kommen später als
der Liefertermin" — obwohl sie das tun.

## 6. Vorschläge

Taos drei Empfehlungen übertragen sich direkt. Fünf weitere sind
softwarespezifisch und folgen aus den obigen Unähnlichkeiten.

**1. Offenlegung normalisieren, nicht in die Verdecktheit drängen.** Taos
schlimmster Fall sind Autoren, die KI verdeckt nutzen und das verschweigen, um
Kritik zu entgehen. Open Source hat sich bereits auf einen Mechanismus geeinigt:
den Git-Trailer `Assisted-by:`. Die Richtlinie des Linux-Kernels zu
KI-Programmierassistenten schreibt `Assisted-by: AGENT_NAME:MODEL_VERSION` vor
und ist ausdrücklich darin, dass Agenten kein `Signed-off-by` setzen dürfen; die
Haftung bleibt beim Menschen. Fedora verlangt Offenlegung, wenn ein wesentlicher
Teil eines Beitrags unverändert aus einem Werkzeug stammt. QEMU bewegt sich von
einem pauschalen Verbot hin zu einer offenlegungsbasierten Annahme für
mechanische Änderungen, Tests, Dokumentation und kleine Korrekturen.

Der betriebliche Nutzen ist kein moralischer. Er besteht darin, dass
Herkunftsdaten bis zur Störung überleben: Um drei Uhr nachts sagen sie einem, ob
die Änderung, auf die man starrt, gründlich reviewt oder schnell durchgewunken
wurde, und wen man wecken muss.

**2. Betonung von der Generierung zur Verdauung verschieben.** Tao: die Betonung
von Beweisgenerierung und Erstautorschaft senken, die von Darstellung,
Publikation und Kanonisierung erhöhen. Die Software-Fassung ist konkret und
unbeliebt: **Menschen für Review-Durchsatz, Konsolidierung, Löschen und
Dokumentation befördern, nicht für PR-Zahlen.** Angesichts des Einbruchs beim
Refactoring-Anteil ist die Arbeit mit der größten Hebelwirkung im Jahr 2026
vermutlich das Konsolidieren dessen, was Agenten bereits produziert haben. Kaum
ein Vergütungssystem belohnt sie.

**3. Die Vortragsregel, übertragen.** Tao: Wer über das Ergebnis keinen klaren
Fachvortrag halten kann, der korrekt ist und die Beiträge sauber zuordnet, soll
nicht publizieren. Die Software-Fassung:

> **Wenn niemand im Team die Änderung auf Review-Tiefe erklären kann — warum
> dieser Ansatz, was er bricht, wie er ausfällt und wie man ihn in Produktion
> debuggen würde — wird sie nicht gemergt.**

Das ist eine stärkere Behauptung als „reviewt es". Es ist eine Behauptung über
eine benannte Person, die die Theorie hält. Sie ist im Review-Gespräch prüfbar,
sie degradiert würdevoll, denn die Antwort darf „noch nicht" lauten, und sie ist
der einzige Vorschlag hier, der die Betriebsstufe unmittelbar verteidigt.

Zwei unabhängige Stützen kamen nach dem Entwurf dieses Vorschlags hinzu, und
beide stärken ihn. Polvara gelangt von Naur statt von Tao aus zu derselben
Praxis und empfiehlt, von Entwickelnden zu verlangen, KI-erzeugten Code Kollegen
mündlich zu erklären. Dieselbe Prüfung, hergeleitet aus der Theoriebildung statt
aus mathematischen Publikationsnormen, was ein schwaches Indiz dafür ist, dass
die Prüfung die natürliche ist und kein Artefakt der Übertragung. Und der
Anthropic-Versuch aus § 2.3 liefert den Mechanismus: Die Verständnislücke folgte
der Art der Nutzung, nicht dem Werkzeugzugang. Eine Regel, die Erklärung
erzwingt, ist deshalb nicht bloß eine nachträgliche Prüfung des Verstehens. Sie
verändert, wie der Code überhaupt erst gelesen wird, und dort wurde die
Aufteilung 65 gegen 40 Prozent entschieden.

**4. Verifikation adversarial machen und nie einen Agenten den Kreis schließen
lassen.** Den Orakelvorteil der Software nutzen, aber das oracle problem
respektieren: Der Agent, der die Implementierung schreibt, sollte nicht der
alleinige Urheber der Eigenschaft sein, gegen die geprüft wird. Praktische
Formen sind von Menschen geschriebene Tests bei agentengeschriebener
Implementierung, eigenschaftsbasierte Tests über agentenerzeugtem Code, formale
Zwillinge, die gegen die Implementierung geprüft werden, und Mutationstests, die
prüfen, ob die Tests selbst Zähne haben. Die allgemeine Regel: **Spezifikation
und Implementierung sollten nicht denselben Urheber haben, ob Mensch oder
nicht.**

**5. Das Harness als das Lieferbare behandeln.** Der zentrale Befund von DORA
2025 ist, dass KI vorhandene Fähigkeit verstärkt, statt sie zu liefern, und der
Bericht nennt sieben Fähigkeiten, die die Richtung der Verstärkung entscheiden,
darunter eine klare Haltung zur KI, starke Versionskontrolle, kleine Chargen und
gute interne Plattformen. Die Folgerung für Teams, die Agenten einführen: Die
Gates, Hooks, Prüfungen und Spezifikationen, die einen Agenten einschränken,
sind nicht Overhead um die Arbeit herum. Bei billiger Generierung _sind_ sie die
Arbeit, weil sie der einzige Teil sind, der nicht mit dem Token-Verbrauch
skaliert.

**6. Natürliche Reibung in der Darstellung erhalten.** Taos widersinnigster
Punkt: Überpoliertes Schreiben stellt routinemäßige und schwierige Schritte als
gleich leicht dar und entfernt die Reibung, die Lesenden sagt, langsamer zu
werden; „Fehler" in menschlicher Darstellung können helfen. Die Software-Fassung
lautet, festzuhalten, was schwer war: die gescheiterten Ansätze, die
Randbedingung, die den Entwurf erzwang, den subtilen Teil. Genau dafür ist ein
Architecture Decision Record da, und genau das lässt eine agentengeschriebene
PR-Beschreibung systematisch weg, weil der Agent nichts schwer fand.

**7. Die Ausbildungskette ausdrücklich verteidigen.** Tao führt die Ausbildung
der nächsten Generation unter den Zielen auf, die mit den anderen korreliert
waren, und warnt, dass sie auseinanderlaufen können. In der Software ist die
Divergenz bereits gemessen: Stellenausschreibungen für Einsteigende seit 2022
stark rückläufig, Junior-Beschäftigung Monat für Monat sinkend, und eine
Harvard-Studie von 2025 fand einen Rückgang der Junior-Beschäftigung um 9 bis
10 % innerhalb von 18 Monaten nach Einführung von KI-Assistenten in einem
Unternehmen. Im gebündelten Regime lernten Junioren, indem sie die Arbeit taten,
die heute Agenten tun. **Wer in fünf Jahren Seniores will, muss den
Ausbildungsweg jetzt bewusst bezahlen, weil die kostenlose Fassung ein
Nebenprodukt des zerbrochenen Bündels war.** Das ist das Ziel, das am ehesten
stillschweigend wegoptimiert wird, weil seine Kosten sofort anfallen und sein
Nutzen nach dem aktuellen Planungshorizont eintritt.

**8. Metriken wählen, die Goodhart überleben.** Mengen- und Aufwandsindikatoren
ausmustern: Zeilen, Commits, PR-Zahl, Story Points, Token-Verbrauch.
Ergebnismaße behalten: Änderungsfehlerrate, Wiederherstellungszeit, Störungen je
Änderung und den Anteil der Änderungen, deren Urheber sie erklären kann.
Akzeptieren, dass der über Autorschaft berechnete truck factor kein Maß
behaltenen Verstehens mehr ist, und entweder Verstehen direkt instrumentieren
oder die Zahl nicht mehr zitieren.

Ein Vorbehalt zu diesem Vorschlag, im Anschluss an § 2.3. Verstehen zu messen ist
eine zweitbeste Kontrolle, nicht die primäre. Eine Messung berichtet über ein
Fenster, das bereits geschlossen ist, und cognitive debt kann danach nicht mehr
bedient werden. Ein Team, das seinen Arbeitsablauf so geordnet hat, dass
Verstehen dem Handeln vorausgeht, also reproduzieren vor korrigieren, die
Ripple-Menge vor Beginn lesen, ausführen statt typprüfen, hat bereits dort
gehandelt, wo das Ergebnis bestimmt wurde, und braucht die Messung vor allem, um
zu bemerken, dass die Ordnung leise nicht mehr eingehalten wird. Die Metrik dient
der Prüfung der Kontrolle, nicht ihrem Ersatz.

## 7. Was eine Leidener Erklärung für Software sagen müsste

Tao verweist auf die
[Leiden Declaration on AI and Mathematics](https://leidendeclaration.ai) (Juni
2026, unterstützt von der Internationalen Mathematischen Union) als
ausgezeichneten Ausgangspunkt. Sie fordert einzelne Forschende auf, KI-Nutzung
offenzulegen, Verantwortung für die Korrektheit zu übernehmen und Vorarbeiten zu
zitieren; sie fordert Fachgesellschaften auf, Publikations- und Review-
Richtlinien zu entwickeln; und sie stellt der Politik Fragen zu Regulierung und
öffentlicher Infrastruktur. Sie verbietet KI nicht, sie verlangt ausdrückliche
Normen der Gemeinschaft.

Die Software hat kein Gegenstück, und die Bausteine dafür liegen bereits über die
oben zitierten Open-Source-Richtlinien verstreut. Zusammengesetzt lauten die
Mindestklauseln:

1. **Offenlegung.** KI-Unterstützung wird an der Änderung deklariert, in
   maschinenlesbarer Form, die in die Versionskontrolle übergeht und die
   Person erreicht, die die Störung bearbeitet.
2. **Menschliche Haftung.** Eine benannte Person zeichnet. Agenten dürfen
   genannt werden; verantwortlich sein dürfen sie nicht.
3. **Verstehen vor dem Merge.** Eine benannte Person kann die Änderung auf
   Review-Tiefe erklären. Andernfalls wird nicht gemergt.
4. **Unabhängige Verifikation.** Spezifikation und Implementierung haben nicht
   denselben Urheber.
5. **Verdauung ist Arbeit.** Review, Konsolidierung, Löschen und Dokumentation
   sind erstklassige technische Beiträge und werden entsprechend ausgestattet
   und belohnt.
6. **Die Ausbildungskette schützen.** Organisationen legen dar, wie
   Entwickelnde Systemverständnis erwerben, nachdem Codeschreiben es nicht mehr
   verleiht.
7. **Ehrliche Messung.** Aufwands- und Mengenindikatoren werden ausgemustert;
   Ergebnismaße und Verständnismaße treten an ihre Stelle.

Die Klausel, die die Software braucht und die Mathematik nicht, ist (3), wegen
der Betriebsstufe. Die Klausel, die die Mathematik hat und für die der Software
die Institutionen fehlen, ist die Annahme durch die Gemeinschaft. Deshalb muss
(5) eine ausdrückliche Ressourcenzusage sein und kein Appell an
Berufsnormen.

## Anhang: remote-store als durchgearbeitetes Beispiel

Dieses Repository ist ein ungewöhnlich vollständiger Fall des Arguments, weil
sein Prozess für genau die Bedingungen gebaut wurde, die Tao beschreibt. Die
Zuordnung und die Lücken.

Zahlen ermittelt durch Ausführen im Wurzelverzeichnis des Repositorys:
`ls sdd/adrs/[0-9]*.md | wc -l` → 38; `ls sdd/specs/*.md | wc -l` → 50;
`ls sdd/traces/[!_]*.yml | wc -l` → 279; `ls sdd/formal/*.dfy | wc -l` → 4.

| Stufe | Vorhandene Mechanik | Einschätzung |
|---|---|---|
| Generierung | `.claude/skills/`, `CLAUDE.md` | Eingeschränkt statt maximiert. Skills kodieren Arbeitsabläufe; Hooks erzwingen, was Anweisungen nur erbitten. |
| Verifikation | Konformitätssuite, `hatch run all`, Coverage-Gate, Mutationsspur, Dafny-Zwillinge unter `sdd/formal/`, TLA+-Modelle | Stärkste Stufe. Die Dafny-Zwillinge und die Mutationstests sind direkte Antworten auf Vorschlag 4: Spezifikation und Implementierung haben tatsächlich nicht denselben Urheber. |
| Darstellung | ADRs, [`sdd/CONTENT-RULES.md`](../CONTENT-RULES.md), CHANGELOG-Disziplin, Docstring-Paritätsprüfungen | Der Sechsmonatstest und „keine pseudopräzisen Werte in der Erzählung" sind Anti-Drift-Regeln, also genau das Versagen der Darstellungsstufe, das Tao beschreibt. |
| Publikation | `/pr`, `/rvw-pr`, `/fix-pr`, `/ship`; konvergenzgetriebenes Review ([ADR-0033](../adrs/0033-ship-convergence-driven-review.md)) | Bis zur Konvergenz zu reviewen statt bis zu einer Rundenzahl ist die ausdrückliche Absage an eine Goodhart-anfällige Metrik. |
| Betrieb | CI-Betriebshandbuch, Health Checks, Benchmark-Spur | Vorhanden, aber im Vergleich die dünnste Stufe, was für eine Bibliothek statt eines Dienstes zu erwarten ist. |
| Kanonisierung | [`sdd/000-process.md`](../000-process.md) („Specs sind die Wahrheitsquelle"), der Ripple-Check, [`sdd/DRIFT-RULES.md`](../DRIFT-RULES.md), 279 Traces, `sdd/BACKLOG.md` | Das ist die kennzeichnende Investition. Die meisten Repositorys haben auf dieser Stufe nichts. |

Durch die Schuldenzerlegung aus § 2.3 gelesen ist dieses Repository ein Fall der
**präventiven** Spalte und nicht der Tilgungsspalte, und das ist die zutreffende
Beschreibung. Es misst cognitive und intent debt nicht und bedient sie nicht; es
ordnet die Arbeit so, dass keine von beiden aufgenommen wird. Der Unterschied ist
wichtig, weil das Messen einer Schuld und das Bauen gegen sie von außen identisch
aussehen, beide erzeugen die Abwesenheit der Schuld, und nur das Zweite überlebt
das Argument zur Nichtrückzahlbarkeit.

Die Kontrollen sind ausdrücklich und älter als dieser Eintrag:

| Schuld | Kontrolle | Wo sie steht |
|---|---|---|
| Intent | Keine Implementierung ohne Spec-Abschnitt; Entscheidungsprotokolle nach Annahme unveränderlich, abgelöst statt bearbeitet | [`sdd/000-process.md`](../000-process.md) Regeln 1 und 4 |
| Intent | Specs sind gegenüber dem Code maßgeblich, sodass das festgehaltene _Warum_ nicht still hinter die Implementierung zurückfallen kann | [`sdd/000-process.md`](../000-process.md) Regel 3 |
| Cognitive | Fehlerkorrekturen reproduzieren den Fehler und sehen den Test scheitern, _bevor_ korrigiert wird; Features laufen SPEC → TEST → IMPLEMENT | [`sdd/000-process.md`](../000-process.md) Regel 6 |
| Cognitive | Verhalten wird durch Ausführen geprüft, nie durch Typprüfung; Fehler werden reproduziert, bevor Korrekturen behauptet werden | [`CLAUDE.md`](../../CLAUDE.md) Prinzip 6 |
| Cognitive | Die Ripple-Menge der Änderung wird _vor_ Beginn gelesen, nicht am Ende der Prüfung | [`sdd/CLAUDE-REFERENCE.md`](../CLAUDE-REFERENCE.md) Pre-work-Index |
| Cognitive | Zahlen nennen den Befehl, aus dem sie stammen, ausgeführt vor dem Schreiben des Satzes | [`CLAUDE.md`](../../CLAUDE.md) Prinzip 9 |

Jeder Eintrag der kognitiven Spalte legt eine _Reihenfolge_ fest: verstehen, dann
handeln. Das ist dieselbe Größe, die der Anthropic-Versuch als entscheidend
befand, hier als Prozess kodiert statt individueller Gewohnheit überlassen. Der
Pre-work-Index ist der klarste Fall: Es gibt ihn, weil stichprobenartig geprüfte
PRs die Ripple-Tabelle erst am Ende der Prüfung heranzogen, was eine Diagnose
genau dieses Versagens und eine genau darauf gerichtete Kontrolle ist.

**Naur stützt diese Anordnung; ein früherer Entwurf dieses Eintrags ließ ihn
dagegen argumentieren.** Jener Entwurf führte Naurs zweites Compiler-Team an, dem
vollständiger Code und vollständige Dokumentation übergeben wurden und das das
System nicht erweitern konnte, als Beleg dafür, dass die schriftlichen Artefakte
des Repositorys keine Theorie vermitteln können. Der Schluss war falsch. Gruppe B
scheiterte, weil ihr ein fertiges Artefakt übergeben wurde, nicht weil
schriftlich festgehaltene Intention wertlos wäre; Naurs eigenes Gegenmittel ist
aktive Mitarbeit an der Entwicklung. Ein Arbeitsablauf, der das Reproduzieren des
Fehlers, das Lesen der Ripple-Menge und das Ausführen des Verhaltens verlangt,
_ist_ diese Mitarbeit, vorgeschrieben. Die schriftlichen Artefakte sind hier kein
Ersatz dafür, und der Prozess verlangt das auch nicht von ihnen.

**Die Traces sitzen auf der Intent-Schicht, und die Grenze lohnt sich sauber zu
halten.** Trace-Dateien halten fest, was ein Agent tatsächlich gelesen hat,
markiert mit `unclear` oder `misleading`, wo ein Dokument den Lesenden im Stich
ließ, aggregiert von `hatch run report-trace-outcomes`. Das misst, ob
externalisierte Begründung auffindbar und nutzbar war, ein Instrument der
Intent-Schicht, und ein gutes. Es ist nicht die Kontrolle der kognitiven Schicht;
das sind die Regeln in der Tabelle oben. Die Warnung des Schemas, „cleaned-up
'ideal' traces silently lie to the aggregator", aufgeräumte Idealtraces belügen
den Aggregator stillschweigend, ist Taos Reibungsargument, angewandt auf
Prozessdaten.

**Prinzip 9 ist die Vortragsregel im Kleinen.** Zu verlangen, dass eine Zahl den
Befehl nennt, aus dem sie stammt, hergeleitet vor dem Schreiben des Satzes, ist
dieselbe Forderung: Zeige, dass du die Behauptung verteidigen kannst, oder
publiziere sie nicht. [ADR-0037](../adrs/0037-whole-file-gate-and-derived-figures.md)
hält die gemessenen Fehlermodi fest, die dazu geführt haben.

**Ein Verständnisversuch und sein Befund.** Nach dem Entwurf dieses Eintrags
wurde sein Verfasser gefragt, ob er tatsächlich ein Modell davon halte, was
remote-store ist und warum es so gebaut ist. Der Test lief im Stil des
Repositorys selbst: das Modell zuerst als widerlegbare Behauptung aussprechen,
dann gegen die Quelle prüfen. Vorheriges Modell: eine Store-Fassade über
austauschbaren Backends; ein Fähigkeitssystem, weil die Backends sich wirklich
unterscheiden; Absage an Verhalten nach dem kleinsten gemeinsamen Nenner;
gespiegelte synchrone und asynchrone Oberflächen; Konformität parametrisiert über
alle Backends, mit Dafny und TLA+ als unabhängigen Orakeln. Dieses Modell war aus
`CLAUDE.md`, Verzeichnislisten und Trace-Dateinamen im Verlauf des Schreibens
entstanden, ohne eine Spec oder ein Quellmodul zu lesen. Geprüft wurde es dann
gegen [`sdd/DESIGN.md`](../DESIGN.md), die Specs
[003](../specs/003-backend-adapter-contract.md),
[004](../specs/004-path-model.md) und
[010](../specs/010-native-path-resolution.md), die `_GATING`-Tabelle am Kopf von
`src/remote_store/_store.py` sowie Listen von `src/remote_store/` und
`sdd/specs/`.

Das Skelett hielt. Drei Punkte hielten nicht, und alle drei waren _Warum_-Fragen
und keine _Was_-Fragen:

- **Capabilities sind zweierlei, nicht einerlei.** CAP-007 trennt Gates, die
  `CapabilityNotSupported` auslösen und eine Methode sperren, von Qualitätsflags
  (`ATOMIC_MOVE`, `SEEKABLE_READ`, `LAZY_READ`), die eine Eigenschaft einer
  bestehenden Methode beschreiben und nichts sperren. Das vorherige Modell hätte
  einen aktiven Fehler erzeugt: dass ein Backend `SEEKABLE_READ` deklarieren
  müsse, um `read_seekable()` zu bedienen, während diese Methode überall
  verfügbar ist und das Flag nur berichtet, was sie kostet.
- **Die Pfadauflösung fehlte vollständig** — `_resolution.py`, `_proxy.py`, die
  Specs 010 und 043 — samt ihrer motivierenden Invariante, der
  Rundlauf-Sicherheit: Was eine Store-Methode zurückgibt, muss ohne manuelles
  Abschneiden als Eingabe einer anderen verwendbar sein, nachdem `FileInfo.path`
  das `root_path`-Präfix durchgereicht hatte und Aufrufende es doppelt
  voranstellten.
- **Das leitende Prinzip war falsch benannt.** Nicht „Verhalten nach dem
  kleinsten gemeinsamen Nenner ablehnen", sondern etwas Schärferes: die
  Schnittstelle hart normalisieren, also Pfadvalidierung und eine
  Fehlerhierarchie, und sich zugleich weigern, die Garantien zu normalisieren,
  die als vom Aufrufenden prüfbare Deklarationen sichtbar bleiben. Diese Regel
  erklärt CAP-007, statt es als Eigenheit zu behandeln.

**Der Befund schränkt sowohl § 5 als auch die obige Naur-Lesart ein.** Er
bestätigt das Amnesie-Argument: Dieser Eintrag wurde ausführlich über ein System
geschrieben, dessen Theorie sein Verfasser nicht hielt. Er zeigt aber auch, dass
die Lücke sich schneller schließt, als Naurs Compiler-Beispiel erwarten lässt.
Gruppe B hatte vollständigen Code und vollständige Dokumentation und konnte das
System dennoch nicht erweitern; vier Lesevorgänge stellten hier die strittige
Argumentation wieder her, weil diese Specs das _Warum_ an den Stellen festhalten,
an denen das Warum umstritten war. Spec 010 beginnt mit einem Abschnitt „The
Problem" und einem scheiternden Beispiel, und CAP-007 argumentiert für
Qualitätsflags, statt sie nur aufzuzählen. **Dokumentation, die Begründung trägt,
ist nicht die Dokumentation, die Naur ausgeschlossen hat.** Sie hebt die
Notwendigkeit der Beteiligung nicht auf, und sie überlebt die Sitzung nicht; sie
macht die Beteiligung billig genug, dass es sich lohnt, sie zu verlangen.

Zwei Grenzen des Versuchs. Sein Subjekt ist ein Agent, er misst also Transfer auf
der Intent-Schicht und nicht menschliche cognitive debt. Und ein selbst
abgenommener Verständnistest wird von derselben Partei bewertet, die ihn
geschrieben hat: Die drei Fehlstellen sind jene, die die Prüfung zutage
förderte, und sie sind eine Untergrenze dessen, was fehlte.

**Die Lücken.** Gemessen an § 6 haben zwei Vorschläge hier keinen Mechanismus.
(1) Offenlegung: Commit-Nachrichten tragen Backlog-IDs, aber keinen
`Assisted-by:`-Trailer, sodass die KI-Herkunft nicht in `git log` überlebt.
(7) Die Ausbildungskette: Ein Projekt mit einer einzigen wartenden Person hat
keinen Juniorpfad zu verteidigen, was bedeutet, dass das Repository den
schwersten Vorschlag nicht vorführen kann, und nicht, dass es an ihm scheitert.

Die Verständnismessung aus Vorschlag 8 ist bewusst nicht als dritte Lücke
aufgeführt. Die obigen präventiven Kontrollen adressieren dasselbe Versagen auf
anderem Weg, und nach dem Argument zur Nichtrückzahlbarkeit in § 2.3 adressieren
sie es an der einzigen Stelle, an der es adressierbar ist. Eine Messung würde
nachträglich über ein Fenster berichten, das bereits geschlossen ist.

**Die offene Frage ist betrieblich, nicht strukturell.** Die Kontrollen
garantieren, dass die vorgeschriebene Beteiligung stattfindet; was sie von sich
aus nicht festlegen, ist, wessen Theorie dabei entsteht, denn das Reproduzieren,
das Lesen der Ripple-Menge und das Ausführen können vom Agenten, von der
wartenden Person oder von beiden geleistet werden. Im Prozess fehlt hier nichts.
Das ist eine Frage danach, wie der Prozess betrieben wird, und der Grund, warum
„diese Schulden zu vermeiden versuchen" das richtige Register für die Behauptung
ist und nicht „beseitigen". Es ist zugleich die Frage, die eine zweite wartende
Person umsonst beantworten würde, indem sie die Lücke der einen für die andere
sichtbar macht.

Dies sind Beobachtungen, keine Handlungsempfehlungen. Gemäß
[`CLAUDE.md` § Audits](../../CLAUDE.md) liegt die Entscheidung bei der
Nutzerin oder dem Nutzer.

## Quellen

Die Quellenliste steht ungekürzt in der englischen Fassung unter
[§ Sources](research-code-abundance-goals-and-values.md). Sie wird hier nicht
wiederholt: Eine zweite Kopie von 47 URLs wäre eine zweite Stelle, die veraltet,
und der einzige Ort, an dem sie gepflegt wird, ist die englische Datei.
