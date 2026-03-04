from typing import List
from models import GridPoint


def generate_grid(search_area: dict) -> List[GridPoint]:
    """Generiert ein GPS-Raster über das Suchgebiet."""
    points = []
    zoom = search_area["zoom"]

    lat = search_area["lat_min"]
    while lat <= search_area["lat_max"]:
        lon = search_area["lon_min"]
        while lon <= search_area["lon_max"]:
            points.append(GridPoint(
                latitude=round(lat, 6),
                longitude=round(lon, 6),
                zoom=zoom,
            ))
            lon += search_area["lon_step"]
        lat += search_area["lat_step"]

    return points
