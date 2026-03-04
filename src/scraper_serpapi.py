import logging
from typing import List

from serpapi import GoogleSearch
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


class SerpApiScraper:
    def __init__(self, config: dict):
        self.api_key = config["api_keys"]["serpapi"]
        self.language = config["search"]["language"]
        self.max_pages = config["search"]["max_pages_per_query"]
        rate = config["rate_limiting"]["requests_per_second"]
        self.rate_limiter = RateLimiter(rate)

    def scrape_all_pages(self, query: str, ll: str) -> List[dict]:
        """Alle Seiten für eine Query+Location-Kombination abrufen."""
        all_results = []

        for page in range(self.max_pages):
            self.rate_limiter.wait()

            params = {
                "engine": "google_maps",
                "q": query,
                "ll": ll,
                "type": "search",
                "hl": self.language,
                "start": page * 20,
                "api_key": self.api_key,
            }

            result = self._execute_search(params)
            if result is None:
                break

            local_results = result.get("local_results", [])
            if not local_results:
                break

            all_results.extend(local_results)

            # Keine weitere Seite verfügbar
            if "next" not in result.get("serpapi_pagination", {}):
                break

        return all_results

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=4, max=60),
        retry=retry_if_exception_type((ConnectionError, TimeoutError, OSError)),
    )
    def _execute_search(self, params: dict) -> dict | None:
        try:
            search = GoogleSearch(params)
            result = search.get_dict()
        except Exception as e:
            logger.warning(f"SerpAPI Request fehlgeschlagen: {e}")
            raise

        if "error" in result:
            error_msg = result["error"]
            if "rate limit" in error_msg.lower():
                raise ConnectionError(f"Rate-Limit erreicht: {error_msg}")
            logger.error(f"SerpAPI Fehler: {error_msg}")
            return None

        return result
