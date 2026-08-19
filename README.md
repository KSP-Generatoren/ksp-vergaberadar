# KSP Vergaberadar

Ausschreibungs-Radar für Netzersatzanlagen. Findet, bewertet und überwacht
öffentliche Ausschreibungen — zugeschnitten auf das KSP-Portfolio.

Gebaut als Gegenentwurf zu Vergabepilot: schmaler im Umfang, tiefer in der
Fachlichkeit. Das Tool kennt das KSP-50Y-Datenblatt.

---

## Betrieb

Vollautomatisch über GitHub Actions (siehe `DEPLOY.md`): 3× täglich Sync,
Änderungswächter, Site-Build, Deploy auf GitHub Pages. RSS-Feed und
ICS-Kalender inklusive. Die Oberfläche läuft identisch als lokale Datei.

## Was drin ist

| Modul | Zweck |
|---|---|
| `sources/ted.py` | TED Search API v3, EU-weit, ohne Authentifizierung |
| `sources/doe.py` | Datenservice Öffentlicher Einkauf — ober- **und unterschwellig** |
| `sources/nrw.py` | Vergabe.NRW Open-Data-REST, Vorlage für weitere Länder |
| `sources/cosinex.py` | **Ein** Adapter für DTVP, eVergabe-Online und alle Länder-VMPs |
| `score.py` | Dreischichtige Bewertung, jede Zeile begründet |
| `documents.py` | Vergabeunterlagen über eForms BT-15 ziehen und Text extrahieren |
| `monitor.py` | Änderungsmonitor — der Baustein, den Vergabepilot nicht hat |
| `dossier.py` | Go/No-Go-Dossier im KSP-Format, per Claude API |
| `db.py` | SQLite, `tenant_id` von Anfang an |
| `summarize.py` | Deutsche Zusammenfassungen + Assistent-Antworten ohne API-Zwang |
| `export.py` | Site-Build: HTML mit Inline-Daten, RSS, ICS-Kalender |
| `web/template.html` | Oberfläche: Leitstand, Radar mit Suchprofilen, Wächter, Kanban-Pipeline (Drag & Drop), Profil-Editor |
| `.github/workflows/sync.yml` | Zeitplan, Sync, Build, Pages-Deploy |
| `tests/` | 19 pytest-Checks + 25 Browser-E2E-Checks (Playwright) |

## Loslegen

```bash
pip install -r requirements.txt
cp .env.example .env          # ANTHROPIC_API_KEY eintragen
python -m ksp_radar.cli sync  # alle Quellen abrufen und bewerten
python -m ksp_radar.cli list  # Treffer ansehen
python -m ksp_radar.cli watch # Änderungsmonitor
```

Täglich per Cron:

```
0 6,12,18 * * *  cd /pfad/ksp-vergaberadar && python -m ksp_radar.cli sync
15 6 * * *       cd /pfad/ksp-vergaberadar && python -m ksp_radar.cli watch
```

## Die Bewertung

Drei Schichten, in dieser Reihenfolge:

1. **Harte Ausschlüsse** — Negativliste (BHKW, PV, Wind), Zubehör das wir nicht
   liefern (Lastbank, Prüfstand), bereits vergebene Verfahren
2. **Deterministische Merkmale** — CPV-Kerncode +35, Kernbegriff im Volltext +30,
   Leistungsklasse im Portfolio +20, Auftraggebertyp bis +12, Lieferleistung +8,
   reiner Wartungsauftrag −25
3. **Deckel** — was außerhalb 20–200 kVA liegt, wird nie automatisch „Go"

Schwellen: ab 70 Go, ab 45 prüfen, darunter Ablage.

Jeder Punkt trägt seine Begründung mit. Im Dossier steht unter „Warum dieser
Treffer" die vollständige Rechnung. Wer eine Regel ändert, sieht sofort, welche
Treffer sich verschieben.

Alles Fachliche steht in `config.py` — CPV-Codes, Keywords, Produktprofil,
Schwellen. Der übrige Code ist generisch.

## Warum die Datenbeschaffung funktioniert

**Bekanntmachungen:** TED liefert EU-weit ohne Authentifizierung. Der
Datenservice Öffentlicher Einkauf liefert seit 2024 als einzige zentrale Stelle
auch unterschwellige Verfahren strukturiert — genau dort liegt das KSP-Geschäft.

**Vergabeunterlagen:** § 41 Abs. 1 VgV und § 29 UVgO verlangen wortgleich, dass
die Unterlagen „unentgeltlich, uneingeschränkt, vollständig und direkt"
abrufbar sind. „Direkt" ist als *ohne Registrierung* ausgelegt. Die Adresse
steht als Feld BT-15 in der Bekanntmachung. Deshalb ist der Weg von der
Bekanntmachung zum Volltext durchgängig automatisierbar.

**Portale:** Rund 800 Vergabequellen laufen auf einer Handvoll Softwareprodukte.
Ein cosinex-Adapter deckt DTVP, eVergabe-Online und die meisten Länder-Portale
ab. Aus 800 Scrapern werden 8–12.

## Der Änderungsmonitor

Wer die Unterlagen registrierungsfrei zieht, ist der Vergabestelle unbekannt und
bekommt **keine Benachrichtigung über Änderungen**. Das ist das bekannte
Praxisproblem der direkten Bereitstellung — Bieter reichen auf veralteten
Unterlagen ein und werden formal ausgeschlossen.

Der Monitor zieht die Dokument-URLs täglich neu, vergleicht Hashes, erzeugt ein
Diff und stuft es ein. Kritisch wird markiert, was Fristen, Mindestanforderungen,
Eignung oder Wertung berührt.

Bad Oldesloe (11.81.01.0020) ist der Beleg: drei Bieterinformationen in sieben
Tagen, jede mit materieller Wirkung auf das Angebot. Der Test in `test_e2e.py`
bildet genau diesen Fall ab.

## Tests

```bash
python3 test_scoring.py   # trennt der Scorer die echten Bekanntmachungen?
python3 test_e2e.py       # laden, bewerten, speichern, Änderungen erkennen
```

## Grenzen

- **Beschränkte Ausschreibungen ohne Teilnahmewettbewerb werden nicht
  veröffentlicht.** Bad Oldesloe hätte kein Portal gefunden, auch Vergabepilot
  nicht. Das Tool erweitert den öffentlichen Kanal, es ersetzt nicht den, über
  den KSP heute gewinnt.
- Ein Teil der Vergabestellen setzt § 41 VgV falsch um und verlangt trotzdem eine
  Anmeldung. Diese Fälle bleiben manuell.
- Die Basis-URL des Datenservice ist über `DOE_API_BASE` konfigurierbar, weil der
  Dienst noch im Ausbau ist.

## Kosten

Hetzner CX22 oder Supabase 5–25 €, Claude API 10–40 €, Embeddings unter 5 €.
Zusammen 25–90 € im Monat gegenüber 60 € für Vergabepilot Professional oder
125 € für Ultimate.

Es rechnet sich nicht über den Preis. Es rechnet sich über Passgenauigkeit —
und über die Datenbasis, die entsteht: jede geprüfte Ausschreibung, jede
Entscheidung, jeder Ausgang.
