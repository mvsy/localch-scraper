# local.ch Scraper — Lead Generator für Schweizer KMU

Ein Web-Scraper der **local.ch** nach Schweizer Kleinbetrieben ohne Website durchsucht und qualifizierte Leads exportiert.

## Was es macht

1. **Scraping** — Durchsucht local.ch nach Betrieben in einer gewählten Stadt und Branche
2. **Kategorisierung** — Trennt Betriebe mit und ohne Website
3. **Verifizierung** — Googelt jeden Betrieb ohne Website nochmals um sicherzugehen
4. **E-Mail-Suche** — Findet E-Mail-Adressen via Google + Firmen-Website
5. **Export** — Lädt Ergebnisse als CSV herunter

---

## Voraussetzungen

- Python 3.9+
- [Docker](https://www.docker.com/) (empfohlen) **oder** lokale Python-Umgebung

---

## Schnellstart mit Docker (empfohlen)

```bash
# Repository klonen
git clone https://github.com/mvsy/localch-scraper.git
cd localch-scraper

# Starten
docker-compose up --build

# Browser öffnen
open http://localhost:8000
```

---

## Lokale Installation (ohne Docker)

```bash
# Repository klonen
git clone https://github.com/mvsy/localch-scraper.git
cd localch-scraper

# Virtuelle Umgebung erstellen
python -m venv venv

# Aktivieren
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# Abhängigkeiten installieren
pip install -r requirements.txt

# Playwright-Browser installieren (Chromium)
playwright install chromium
playwright install-deps chromium

# Server starten
cd src
uvicorn app:app --reload --port 8000

# Browser öffnen
open http://localhost:8000
```

---

## Benutzung (Web-UI)

1. **Ort eingeben** — z.B. `Uster`, `Zürich`, `Winterthur`
2. **Branchen auswählen** — Handwerk, Gastronomie, Gesundheit etc.
3. **Suche starten** — Fortschritt wird live angezeigt
4. **CSV herunterladen** — Alle Leads mit Name, Adresse, Telefon, E-Mail

### Fortschritts-Phasen

| Phase | Beschreibung |
|-------|-------------|
| Läuft... | Scraping auf local.ch |
| Verifizierung | Google-Check pro Betrieb |
| Fertig | Ergebnisse bereit |

---

## CSV-Felder

| Feld | Beschreibung |
|------|-------------|
| `lead_type` | `Keine Website` oder `Website vorhanden` |
| `name` | Firmenname |
| `address` | Vollständige Adresse |
| `phone` | Telefonnummer (formatiert) |
| `email` | E-Mail-Adresse (falls gefunden) |
| `website` | Website (falls vorhanden) |
| `category` | Branche |
| `rating` | Bewertung auf local.ch |
| `review_count` | Anzahl Bewertungen |
| `description` | Firmenbeschreibung |
| `hours` | Öffnungszeiten |
| `latitude` / `longitude` | GPS-Koordinaten |

---

## Konfiguration (`config.yaml`)

```yaml
search:
  max_pages_per_query: 3    # Seiten pro Kategorie (je mehr, desto langsamer)

filtering:
  treat_social_media_as_no_website: true   # Facebook = keine Website
  social_media_domains:
    - facebook.com
    - instagram.com
    - twitter.com

output:
  format: "csv"    # "csv", "excel" oder "both"
```

---

## Architektur

```
local.ch Scraper
├── src/
│   ├── app.py               # FastAPI Web-Server (API + UI)
│   ├── scraper_localch.py   # Playwright-Scraper für local.ch
│   ├── scraper_service.py   # Job-Verwaltung (Background-Threads)
│   ├── website_checker.py   # Google-Verifizierung + E-Mail-Suche
│   ├── filter.py            # Lead-Kategorisierung
│   ├── deduplicator.py      # Duplikat-Erkennung
│   ├── exporter.py          # CSV/Excel-Export
│   └── models.py            # Datenmodelle
├── static/
│   └── index.html           # Web-UI (Vanilla JS + Tailwind)
├── config.yaml              # Konfiguration
├── Dockerfile
└── docker-compose.yml
```

---

## Tipps für gute Leads

- **Kleinere Orte** liefern bessere Ergebnisse (weniger Konkurrenz um lokale Kunden)
- **Handwerk-Kategorien** haben die höchste Rate an Betrieben ohne Website
- `max_pages_per_query: 1` für schnellen Überblick, `3` für vollständige Suche
- Leads mit E-Mail sind am wertvollsten → direkt anschreibbar

---

## Hinweise

- Der Scraper respektiert lokale Verzögerungen um Server nicht zu überlasten
- Für den persönlichen/kommerziellen Einsatz: Nutzungsbedingungen von local.ch beachten
- Google-Verifizierung kann bei sehr grossen Resultatsmengen langsam sein
