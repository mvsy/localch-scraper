import os
from datetime import datetime
from typing import List, TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from models import Business

CSV_COLUMNS = [
    "lead_type",
    "name",
    "address",
    "phone",
    "email",
    "category",
    "categories",
    "rating",
    "review_count",
    "latitude",
    "longitude",
    "open_state",
    "price_level",
    "description",
    "website",
    "place_id",
    "search_term_used",
    "scraped_at",
]


def export_results(
    businesses: List["Business"],
    output_dir: str,
    fmt: str = "csv",
    prefix: str = "zuerich_ohne_website",
) -> List[str]:
    """Exportiert Ergebnisse als CSV und/oder Excel."""
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    records = []
    for biz in businesses:
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

    output_files = []

    if fmt in ("csv", "both"):
        csv_path = os.path.join(output_dir, f"{prefix}_{timestamp}.csv")
        df.to_csv(csv_path, index=False, encoding="utf-8-sig")  # BOM für Excel
        output_files.append(csv_path)

    if fmt in ("excel", "both"):
        xlsx_path = os.path.join(output_dir, f"{prefix}_{timestamp}.xlsx")
        df.to_excel(xlsx_path, index=False, sheet_name="Businesses")
        output_files.append(xlsx_path)

    return output_files
