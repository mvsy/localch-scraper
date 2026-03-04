import httpx
import math
from typing import Optional


NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"


def geocode(place: str) -> Optional[tuple[float, float, str]]:
    """Löst einen Ortsnamen in GPS-Koordinaten auf via Nominatim (OpenStreetMap).

    Returns (latitude, longitude, display_name) oder None falls nicht gefunden.
    """
    resp = httpx.get(
        NOMINATIM_URL,
        params={
            "q": place,
            "format": "json",
            "limit": 1,
            "countrycodes": "ch",  # Schweiz priorisieren
        },
        headers={"User-Agent": "googlemaps-scraper/1.0"},
        timeout=10,
    )
    resp.raise_for_status()
    results = resp.json()

    if not results:
        return None

    hit = results[0]
    return (
        float(hit["lat"]),
        float(hit["lon"]),
        hit.get("display_name", place),
    )


def make_search_area(lat: float, lon: float, radius_km: float = 5.0) -> dict:
    """Erstellt eine search_area-Config um einen Punkt mit gegebenem Radius.

    Für kleine Radien (≤5km) wird nur 1 Punkt verwendet — Google Maps
    deckt bei Zoom 13 schon ~10km ab, ein Grid ist unnötig.
    Für grössere Radien wird ein sparsames Grid erstellt.
    """
    lat_offset = radius_km / 111.0
    lon_offset = radius_km / (111.0 * math.cos(math.radians(lat)))

    if radius_km <= 5:
        # Kleiner Radius: 1 Punkt reicht, Zoom 13 deckt ~10km ab
        return {
            "name": f"{lat:.4f}, {lon:.4f}",
            "center_lat": lat,
            "center_lon": lon,
            "lat_min": round(lat, 6),
            "lat_max": round(lat, 6),
            "lon_min": round(lon, 6),
            "lon_max": round(lon, 6),
            "lat_step": 1.0,  # irrelevant bei 1 Punkt
            "lon_step": 1.0,
            "zoom": "13z",
        }
    elif radius_km <= 10:
        # Mittlerer Radius: 2×2 = 4 Punkte
        step_km = radius_km  # grob: halber Durchmesser
        lat_step = step_km / 111.0
        lon_step = step_km / (111.0 * math.cos(math.radians(lat)))
        zoom = "13z"
    else:
        # Grosser Radius: feineres Grid
        step_km = 8.0
        lat_step = step_km / 111.0
        lon_step = step_km / (111.0 * math.cos(math.radians(lat)))
        zoom = "13z"

    return {
        "name": f"{lat:.4f}, {lon:.4f}",
        "center_lat": lat,
        "center_lon": lon,
        "lat_min": round(lat - lat_offset, 6),
        "lat_max": round(lat + lat_offset, 6),
        "lon_min": round(lon - lon_offset, 6),
        "lon_max": round(lon + lon_offset, 6),
        "lat_step": round(lat_step, 6),
        "lon_step": round(lon_step, 6),
        "zoom": zoom,
    }
