# In 5 Minuten live

Das Repository ist vollständig vorbereitet: Datenpipeline, Weboberfläche,
Zeitplan und Deployment liegen fertig drin. Es fehlt nur der Push auf euren
GitHub-Account — den kann nur jemand mit euren Zugangsdaten machen.

## Schritt 1 — Repository anlegen

Auf github.com mit dem KSP-Account (github@ksp-generatoren.de) anmelden:

- **New repository** → Name `ksp-vergaberadar`
- Sichtbarkeit: **Public** empfohlen (GitHub Pages ist im Free-Plan nur für
  öffentliche Repos verfügbar; die Daten sind ohnehin öffentliche
  Bekanntmachungen). Private geht auch, braucht aber GitHub Pro/Team.
- Keine Haken bei README/License (das Repo bringt alles mit)

## Schritt 2 — Pushen

Im entpackten Projektordner:

```bash
git remote add origin https://github.com/<KSP-ACCOUNT>/ksp-vergaberadar.git
git push -u origin main
```

## Schritt 3 — Pages einschalten

Im neuen Repo: **Settings → Pages → Source: "GitHub Actions"** wählen. Fertig.

Der Push löst den ersten Workflow-Lauf automatisch aus. Danach:

- **Die App:** `https://<KSP-ACCOUNT>.github.io/ksp-vergaberadar/`
- **RSS-Feed:** `…/feed.xml` (in Outlook abonnieren)
- **Kalender:** `…/fristen.ics` (alle Angebotsfristen mit 3-Tage-Erinnerung)

## Was dann automatisch passiert

3× täglich (ca. 06:20 / 12:20 / 17:20) läuft der Sync auf GitHub-Servern:
alle Quellen abrufen, bewerten, Vergabeunterlagen auf Änderungen prüfen,
Site neu bauen und veröffentlichen. Kostenlos — öffentliche Repos haben
unbegrenzte Actions-Minuten.

**Wichtig für den ersten Lauf:** Aus der Claude-Sandbox war `api.ted.europa.eu`
netzwerkseitig gesperrt; die Adapter sind gegen die offiziellen API-Doku
geschrieben, aber noch nie gegen die Live-API gelaufen. Auf GitHub-Runnern
ist die API erreichbar. Schlägt eine Quelle fehl, zeigt die Kopfleiste der
App eine rote Lampe mit der Fehlermeldung, und der Rest läuft weiter —
im Actions-Tab steht unter "Summary" das Ergebnis jedes Laufs. Erfahrungsgemäß
braucht es nach dem ersten Live-Lauf ein, zwei kleine Feldnamen-Korrekturen.

## Optional: KI-Dossiers

**Settings → Secrets and variables → Actions → New repository secret**
`ANTHROPIC_API_KEY` mit einem Claude-API-Schlüssel anlegen. Ab dem nächsten
Lauf erzeugt die Pipeline für die Top-Treffer automatisch vollständige
Dossiers (Ausschlussrisiken, Wertungshebel, Widersprüche) aus den
Vergabeunterlagen. Ohne Schlüssel laufen regelbasierte Zusammenfassungen —
die App funktioniert vollständig auch ohne.

## Optional: Suchprofil ändern

In der App unter **Profil** anpassen → **Exportieren** →
die Datei als `data/profile_override.json` ins Repo legen (Add file →
Upload). Ab dem nächsten Sync bewertet die Pipeline mit dem neuen Profil.
