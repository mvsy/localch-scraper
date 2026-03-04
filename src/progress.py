import json
import os


class ProgressTracker:
    """Speichert Fortschritt damit der Scraper fortgesetzt werden kann."""

    def __init__(self, progress_dir: str, enabled: bool = True):
        self.enabled = enabled
        self.progress_file = os.path.join(progress_dir, "progress.json")
        self._completed: set[str] = set()
        if enabled:
            self._load()

    def _load(self):
        if os.path.exists(self.progress_file):
            with open(self.progress_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                self._completed = set(data.get("completed", []))

    def save(self):
        if not self.enabled:
            return
        os.makedirs(os.path.dirname(self.progress_file), exist_ok=True)
        with open(self.progress_file, "w", encoding="utf-8") as f:
            json.dump({"completed": sorted(self._completed)}, f)

    @staticmethod
    def make_key(search_term: str, lat: float, lon: float) -> str:
        return f"{search_term}|{lat}|{lon}"

    def is_completed(self, search_term: str, lat: float, lon: float) -> bool:
        if not self.enabled:
            return False
        return self.make_key(search_term, lat, lon) in self._completed

    def mark_completed(self, search_term: str, lat: float, lon: float):
        if self.enabled:
            self._completed.add(self.make_key(search_term, lat, lon))

    @property
    def completed_count(self) -> int:
        return len(self._completed)

    def reset(self):
        self._completed.clear()
        if os.path.exists(self.progress_file):
            os.remove(self.progress_file)
