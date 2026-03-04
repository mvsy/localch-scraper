from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from models import Business


class Deduplicator:
    """Dedupliziert Businesses anhand der Google place_id."""

    def __init__(self):
        self._seen_place_ids: set[str] = set()
        self._seen_keys: set[str] = set()

    def is_duplicate(self, business: "Business") -> bool:
        # Primär: exakte place_id
        if business.place_id:
            if business.place_id in self._seen_place_ids:
                return True
            self._seen_place_ids.add(business.place_id)
            return False

        # Fallback: Name + Adresse normalisiert
        key = f"{business.name}|{business.address}".lower().strip()
        if key in self._seen_keys:
            return True
        self._seen_keys.add(key)
        return False

    @property
    def total_seen(self) -> int:
        return len(self._seen_place_ids) + len(self._seen_keys)
