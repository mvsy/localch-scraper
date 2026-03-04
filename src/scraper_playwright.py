import logging
import time
import re
import urllib.parse
from typing import List, Optional
from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext

logger = logging.getLogger(__name__)


class PlaywrightScraper:
    """Scrapt Google Maps direkt via Headless-Browser (kein API-Key nötig)."""

    def __init__(self, config: dict):
        self.language = config["search"].get("language", "de")
        self._pw = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._cookies_accepted = False

    def _ensure_browser(self):
        """Browser starten falls nötig (wiederverwendet über alle Queries)."""
        if self._page is not None:
            return

        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        self._context = self._browser.new_context(
            locale="de-CH",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
        )
        self._page = self._context.new_page()

    def close(self):
        if self._browser:
            self._browser.close()
            self._browser = None
        if self._pw:
            self._pw.stop()
            self._pw = None
        self._page = None
        self._context = None

    def scrape_all_pages(self, query: str, ll: str) -> List[dict]:
        """Sucht auf Google Maps und gibt Ergebnisse mit Website-Info zurück.

        ll format: @lat,lon,zoom (z.B. @47.3769,8.5417,13z)
        """
        match = re.match(r"@([\d.-]+),([\d.-]+),([\d]+)z", ll)
        if not match:
            logger.error(f"Ungültiges ll-Format: {ll}")
            return []

        lat, lon, zoom = match.group(1), match.group(2), match.group(3)
        encoded_query = urllib.parse.quote(query)

        url = (
            f"https://www.google.com/maps/search/{encoded_query}/"
            f"@{lat},{lon},{zoom}z?hl={self.language}"
        )

        try:
            self._ensure_browser()
            page = self._page

            page.goto(url, wait_until="domcontentloaded", timeout=30000)

            if not self._cookies_accepted:
                self._accept_cookies()
                self._cookies_accepted = True

            # Warten auf Ergebnisliste
            try:
                page.wait_for_selector('div[role="feed"]', timeout=8000)
            except Exception:
                logger.info(f"'{query}' @ {lat},{lon}: Keine Ergebnisse (kein Feed)")
                return []

            time.sleep(2)

            # Ergebnis-Feed scrollen
            self._scroll_feed()

            # Alle Ergebnis-Links sammeln
            links = page.query_selector_all(
                'div[role="feed"] a[href*="/maps/place/"]'
            )

            results = []
            for i, link in enumerate(links):
                try:
                    data = self._click_and_extract(link, i)
                    if data and data.get("title"):
                        results.append(data)
                except Exception as e:
                    logger.debug(f"Fehler bei Ergebnis {i}: {e}")
                    continue

            logger.info(f"'{query}' @ {lat},{lon}: {len(results)} Ergebnisse")
            return results

        except Exception as e:
            logger.error(f"Fehler bei '{query}' @ {lat},{lon}: {e}")
            # Browser-Reset bei schweren Fehlern
            self.close()
            self._cookies_accepted = False
            return []

    def _accept_cookies(self):
        """Google Cookie-Consent akzeptieren."""
        page = self._page
        try:
            for selector in [
                'button:has-text("Alle akzeptieren")',
                'button:has-text("Accept all")',
                'button:has-text("Alles akzeptieren")',
            ]:
                btn = page.query_selector(selector)
                if btn and btn.is_visible():
                    btn.click()
                    time.sleep(1.5)
                    return
        except Exception:
            pass

    def _scroll_feed(self):
        """Scrollt den Ergebnis-Feed um alle Treffer zu laden."""
        page = self._page
        feed = page.query_selector('div[role="feed"]')
        if not feed:
            return

        prev_count = 0
        for _ in range(3):
            feed.evaluate("el => el.scrollTop = el.scrollHeight")
            time.sleep(1.5)
            items = page.query_selector_all('div[role="feed"] a[href*="/maps/place/"]')
            if len(items) == prev_count:
                break
            prev_count = len(items)

    def _click_and_extract(self, link, index: int) -> dict:
        """Klickt auf ein Ergebnis, extrahiert Details inkl. Website-Check."""
        page = self._page
        result = {}

        # Name aus aria-label
        aria = link.get_attribute("aria-label") or ""
        result["title"] = aria.strip()

        if not result["title"]:
            return result

        # Klick auf das Ergebnis um Detail-Panel zu öffnen
        link.click()
        time.sleep(2)

        # --- Detail-Panel auslesen ---

        # Website-Link suchen
        website = None
        website_link = page.query_selector('a[data-item-id="authority"]')
        if website_link:
            website = website_link.get_attribute("href") or ""

        result["website"] = website if website else None

        # Adresse
        addr_el = page.query_selector('[data-item-id="address"] .fontBodyMedium')
        if addr_el:
            result["address"] = addr_el.inner_text().strip()

        # Telefon
        phone_el = page.query_selector('[data-item-id^="phone"] .fontBodyMedium')
        if phone_el:
            result["phone"] = phone_el.inner_text().strip()

        # Kategorie
        cat_btn = page.query_selector('button[jsaction*="category"]')
        if cat_btn:
            result["type"] = cat_btn.inner_text().strip()

        # Rating
        rating_el = page.query_selector('div.fontDisplayLarge')
        if rating_el:
            try:
                result["rating"] = float(rating_el.inner_text().strip().replace(",", "."))
            except ValueError:
                pass

        # Bewertungsanzahl
        review_el = page.query_selector('span[aria-label*="Rezension"], span[aria-label*="review"]')
        if review_el:
            review_text = review_el.get_attribute("aria-label") or ""
            review_match = re.search(r"([\d.]+)", review_text.replace(".", ""))
            if review_match:
                result["reviews"] = int(review_match.group(1))

        # GPS aus URL
        current_url = page.url
        gps_match = re.search(r"@([\d.-]+),([\d.-]+)", current_url)
        if gps_match:
            result["gps_coordinates"] = {
                "latitude": float(gps_match.group(1)),
                "longitude": float(gps_match.group(2)),
            }

        # Place-ID aus URL
        place_match = re.search(r"/place/[^/]+/([^/]+)", current_url)
        if place_match:
            result["place_id"] = place_match.group(1)

        # Zurück zur Liste
        back_btn = page.query_selector('button[aria-label="Zurück"], button[aria-label="Back"]')
        if back_btn:
            back_btn.click()
            time.sleep(1)
        else:
            page.go_back()
            time.sleep(1.5)

        # Warten dass Feed wieder da ist
        try:
            page.wait_for_selector('div[role="feed"]', timeout=5000)
        except Exception:
            pass

        return result
