from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class GridPoint:
    latitude: float
    longitude: float
    zoom: str

    def to_ll_param(self) -> str:
        """Format als SerpAPI ll-Parameter: @lat,lon,zoom"""
        return f"@{self.latitude},{self.longitude},{self.zoom}"


@dataclass
class Business:
    place_id: Optional[str] = None
    name: str = ""
    address: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    has_website: bool = False
    lead_type: str = ""  # "Keine Website" | "Website vorhanden"
    email: Optional[str] = None
    fax: Optional[str] = None

    category: Optional[str] = None
    categories: List[str] = field(default_factory=list)
    search_term_used: str = ""

    rating: Optional[float] = None
    review_count: Optional[int] = None

    latitude: Optional[float] = None
    longitude: Optional[float] = None

    open_state: Optional[str] = None
    hours: Optional[str] = None
    price_level: Optional[str] = None
    description: Optional[str] = None

    scraped_at: Optional[str] = None

    @classmethod
    def from_serpapi_result(cls, result: dict, search_term: str) -> "Business":
        gps = result.get("gps_coordinates", {})
        website = result.get("website")

        return cls(
            place_id=result.get("place_id"),
            name=result.get("title", ""),
            address=result.get("address"),
            phone=result.get("phone"),
            website=website,
            has_website=bool(website),
            email=result.get("email"),
            fax=result.get("fax"),
            category=result.get("type"),
            categories=result.get("types", []),
            search_term_used=search_term,
            rating=result.get("rating"),
            review_count=result.get("reviews"),
            latitude=gps.get("latitude"),
            longitude=gps.get("longitude"),
            open_state=result.get("open_state"),
            hours=result.get("hours"),
            price_level=result.get("price"),
            description=result.get("description"),
            scraped_at=None,
        )
