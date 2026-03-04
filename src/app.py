import os
import sys
import io
import logging

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

# src/ als Modul-Pfad
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config_loader import load_config
from scraper_service import ScraperService
from exporter import CSV_COLUMNS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)

app = FastAPI(title="local.ch Scraper")

# Config laden
config = load_config(os.path.join(os.path.dirname(__file__), "..", "config.yaml"))
service = ScraperService(config)

# Kategorien-Gruppen für das Frontend
CATEGORY_GROUPS = {
    "Handwerk": [
        "Handwerker", "Elektriker", "Sanitär", "Maler", "Schreiner",
        "Zimmermann", "Dachdecker", "Bodenleger", "Gipser", "Spengler",
        "Schlosser", "Heizungsinstallateur", "Klempner", "Maurer",
        "Fliesenleger", "Gartenbau", "Landschaftsgärtner",
        "Reinigungsfirma", "Umzugsfirma", "Kaminfeger",
    ],
    "Gastronomie": [
        "Restaurant", "Café", "Bar", "Imbiss", "Bäckerei", "Metzgerei",
        "Konditorei", "Pizzeria", "Kebab", "Takeaway", "Catering",
    ],
    "Gesundheit": [
        "Arzt", "Zahnarzt", "Hausarzt", "Tierarzt", "Physiotherapie",
        "Chiropraktiker", "Heilpraktiker", "Psychologe", "Augenarzt",
        "Kinderarzt", "Frauenarzt", "Apotheke", "Optiker", "Hörgeräte",
    ],
    "Detailhandel": [
        "Blumenladen", "Buchhandlung", "Elektronikladen", "Möbelladen",
        "Bekleidungsgeschäft", "Schuhgeschäft", "Juwelier",
        "Spielwarenladen", "Geschenkladen", "Papeterie", "Sportgeschäft",
        "Velogeschäft", "Weinhandlung", "Lebensmittelladen", "Biomarkt", "Kiosk",
    ],
    "Dienstleistungen": [
        "Coiffeur", "Friseur", "Kosmetikstudio", "Nagelstudio",
        "Tattoo Studio", "Schneider", "Schuhmacher", "Schlüsseldienst",
        "Druckerei", "Copyshop", "Fotograf", "Fahrschule", "Nachhilfe",
        "Übersetzungsbüro", "Rechtsanwalt", "Notar", "Steuerberater",
        "Treuhand", "Versicherungsberater", "Immobilienmakler",
    ],
    "Auto & Transport": [
        "Autowerkstatt", "Autogarage", "Reifenservice", "Autowaschanlage",
        "Fahrradwerkstatt", "Taxiunternehmen",
    ],
    "Haus & Wohnen": [
        "Schädlingsbekämpfung", "Gebäudereinigung", "Fensterreinigung",
        "Gartenservice", "Hauswartung",
    ],
    "Bildung & Freizeit": [
        "Musikschule", "Tanzschule", "Yogastudio", "Fitnessstudio",
        "Kampfsport", "Sprachschule", "Kindertagesstätte",
    ],
}


class ScrapeRequest(BaseModel):
    location: str
    categories: list[str] = []


# --- API Endpoints ---

@app.get("/api/categories")
def get_categories():
    return CATEGORY_GROUPS


@app.post("/api/scrape")
def start_scrape(req: ScrapeRequest):
    location = req.location.strip()
    if not location:
        raise HTTPException(status_code=400, detail="Bitte einen Ort eingeben")

    # Kategorien: wenn leer, alle verwenden
    categories = req.categories if req.categories else config["search_terms"]

    job_id = service.start_job(
        categories=categories,
        location_name=location,
        location_display=location,
    )

    return {
        "job_id": job_id,
        "location": location,
        "categories_count": len(categories),
    }


@app.get("/api/status/{job_id}")
def get_status(job_id: str):
    job = service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job nicht gefunden")

    return {
        "job_id": job.job_id,
        "status": job.status,
        "location": job.location_display,
        "progress_pct": job.progress_pct,
        "completed": job.completed_categories,
        "total": job.total_categories,
        "current_term": job.current_term,
        "total_found": job.total_found,
        "no_website_count": job.no_website_count,
        "has_website_count": job.has_website_count,
        "verified_count": job.verified_count,
        "verify_total": job.verify_total,
        "email_found_count": job.email_found_count,
        "error_message": job.error_message,
    }


@app.get("/api/results/{job_id}")
def get_results(job_id: str):
    job = service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job nicht gefunden")

    businesses = job.filtered_businesses if job.status == "completed" else []
    return {
        "job_id": job.job_id,
        "status": job.status,
        "count": len(businesses),
        "businesses": [
            {
                "name": b.name,
                "address": b.address,
                "phone": b.phone,
                "email": b.email,
                "category": b.category,
                "rating": b.rating,
                "review_count": b.review_count,
                "website": b.website,
                "lead_type": b.lead_type,
                "latitude": b.latitude,
                "longitude": b.longitude,
            }
            for b in businesses
        ],
    }


@app.get("/api/download/{job_id}")
def download_csv(job_id: str):
    job = service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job nicht gefunden")
    if job.status != "completed":
        raise HTTPException(status_code=400, detail="Job noch nicht fertig")

    import pandas as pd

    records = []
    for biz in job.filtered_businesses:
        records.append({
            "lead_type": biz.lead_type,
            "name": biz.name,
            "address": biz.address,
            "phone": biz.phone,
            "email": biz.email,
            "category": biz.category,
            "categories": "; ".join(biz.categories) if biz.categories else "",
            "rating": biz.rating,
            "review_count": biz.review_count,
            "latitude": biz.latitude,
            "longitude": biz.longitude,
            "open_state": biz.open_state,
            "price_level": biz.price_level,
            "description": biz.description,
            "website": biz.website,
            "place_id": biz.place_id,
            "search_term_used": biz.search_term_used,
            "scraped_at": biz.scraped_at,
        })

    df = pd.DataFrame(records, columns=CSV_COLUMNS)

    buffer = io.StringIO()
    df.to_csv(buffer, index=False, encoding="utf-8-sig")
    buffer.seek(0)

    filename = f"{job.location}_{job.job_id}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# --- Frontend ---

@app.get("/", response_class=HTMLResponse)
def index():
    html_path = os.path.join(os.path.dirname(__file__), "..", "static", "index.html")
    with open(html_path, "r", encoding="utf-8") as f:
        return f.read()
