import json
import logging
import re
import time
import urllib.parse
from typing import List, Optional
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page

logger = logging.getLogger(__name__)

# Bekannte Verzeichnis-Domains (nicht als Website des Unternehmens werten)
from website_checker import DIRECTORY_DOMAINS


def _fix_mojibake(text: str) -> str:
    """Repariert doppelt-encoded UTF-8 (Mojibake).

    z.B. 'Geschäft' (Ã¤ statt ä) → 'Geschäft'
    """
    if not text:
        return text
    try:
        return text.encode("latin-1").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return text


def _format_swiss_phone(phone: str) -> str:
    """Formatiert Schweizer Telefonnummern einheitlich.

    +41449412816 → +41 44 941 28 16
    0449412816   → 044 941 28 16
    """
    cleaned = re.sub(r"[^\d+]", "", phone)
    # Internationales Format: +41 + 9 Ziffern
    if cleaned.startswith("+41") and len(cleaned) == 12:
        d = cleaned[3:]
        return f"+41 {d[0]} {d[1:3]} {d[3:6]} {d[6:9]}"
    # Nationales Format: 0 + 9 Ziffern
    if cleaned.startswith("0") and len(cleaned) == 10:
        return f"{cleaned[0:3]} {cleaned[3:6]} {cleaned[6:8]} {cleaned[8:10]}"
    return phone


def _format_hours(spec) -> Optional[str]:
    """Formatiert openingHoursSpecification aus JSON-LD als lesbaren String.

    Erwartet eine Liste von Dicts mit dayOfWeek, opens, closes.
    """
    if not spec:
        return None
    try:
        if isinstance(spec, dict):
            spec = [spec]
        parts = []
        for entry in spec:
            days = entry.get("dayOfWeek", [])
            if isinstance(days, str):
                days = [days]
            opens = entry.get("opens", "")
            closes = entry.get("closes", "")
            day_names = [d.split("/")[-1] for d in days]  # URL → Tagname
            if day_names and opens and closes:
                parts.append(f"{', '.join(day_names)}: {opens}–{closes}")
        return " | ".join(parts) if parts else None
    except Exception:
        return None


# Kategorien-Slugs für local.ch (lowercase, keine Umlaute in URL nötig)
CATEGORY_SLUGS = {
    "Handwerker": "handwerker",
    "Elektriker": "elektriker",
    "Sanitär": "sanitaer",
    "Maler": "maler",
    "Schreiner": "schreiner",
    "Zimmermann": "zimmermann",
    "Dachdecker": "dachdecker",
    "Bodenleger": "bodenleger",
    "Gipser": "gipser",
    "Spengler": "spengler",
    "Schlosser": "schlosser",
    "Heizungsinstallateur": "heizungsinstallateur",
    "Klempner": "klempner",
    "Maurer": "maurer",
    "Fliesenleger": "fliesenleger",
    "Gartenbau": "gartenbau",
    "Landschaftsgärtner": "landschaftsgaertner",
    "Reinigungsfirma": "reinigung",
    "Umzugsfirma": "umzug",
    "Kaminfeger": "kaminfeger",
    "Restaurant": "restaurant",
    "Café": "cafe",
    "Bar": "bar",
    "Imbiss": "imbiss",
    "Bäckerei": "baeckerei",
    "Metzgerei": "metzgerei",
    "Konditorei": "konditorei",
    "Pizzeria": "pizzeria",
    "Kebab": "kebab",
    "Takeaway": "takeaway",
    "Catering": "catering",
    "Arzt": "arzt",
    "Zahnarzt": "zahnarzt",
    "Hausarzt": "hausarzt",
    "Tierarzt": "tierarzt",
    "Physiotherapie": "physiotherapie",
    "Chiropraktiker": "chiropraktiker",
    "Heilpraktiker": "heilpraktiker",
    "Psychologe": "psychologe",
    "Augenarzt": "augenarzt",
    "Kinderarzt": "kinderarzt",
    "Frauenarzt": "frauenarzt",
    "Apotheke": "apotheke",
    "Optiker": "optiker",
    "Hörgeräte": "hoergeraete",
    "Blumenladen": "blumen",
    "Buchhandlung": "buchhandlung",
    "Elektronikladen": "elektronik",
    "Möbelladen": "moebel",
    "Bekleidungsgeschäft": "bekleidung",
    "Schuhgeschäft": "schuhe",
    "Juwelier": "juwelier",
    "Spielwarenladen": "spielwaren",
    "Geschenkladen": "geschenke",
    "Papeterie": "papeterie",
    "Sportgeschäft": "sport",
    "Velogeschäft": "velo",
    "Weinhandlung": "wein",
    "Lebensmittelladen": "lebensmittel",
    "Biomarkt": "bio",
    "Kiosk": "kiosk",
    "Coiffeur": "coiffeur",
    "Friseur": "coiffeur",
    "Kosmetikstudio": "kosmetik",
    "Nagelstudio": "nagelstudio",
    "Tattoo Studio": "tattoo",
    "Schneider": "schneider",
    "Schuhmacher": "schuhmacher",
    "Schlüsseldienst": "schluesseldienst",
    "Druckerei": "druckerei",
    "Copyshop": "copyshop",
    "Fotograf": "fotograf",
    "Fahrschule": "fahrschule",
    "Nachhilfe": "nachhilfe",
    "Übersetzungsbüro": "uebersetzung",
    "Rechtsanwalt": "rechtsanwalt",
    "Notar": "notar",
    "Steuerberater": "steuerberater",
    "Treuhand": "treuhand",
    "Versicherungsberater": "versicherung",
    "Immobilienmakler": "immobilien",
    "Autowerkstatt": "autowerkstatt",
    "Autogarage": "garage",
    "Reifenservice": "reifen",
    "Autowaschanlage": "autowaschanlage",
    "Fahrradwerkstatt": "fahrrad",
    "Taxiunternehmen": "taxi",
    "Schädlingsbekämpfung": "schaedlingsbekaempfung",
    "Gebäudereinigung": "gebaeudereinigung",
    "Fensterreinigung": "fensterreinigung",
    "Gartenservice": "gartenpflege",
    "Hauswartung": "hauswartung",
    "Musikschule": "musikschule",
    "Tanzschule": "tanzschule",
    "Yogastudio": "yoga",
    "Fitnessstudio": "fitness",
    "Kampfsport": "kampfsport",
    "Sprachschule": "sprachschule",
    "Kindertagesstätte": "kinderkrippe",
}


class LocalChScraper:
    """Scrapt local.ch Branchenverzeichnis via Playwright."""

    def __init__(self, config: dict):
        self.config = config
        self.max_pages = config.get("search", {}).get("max_pages_per_query", 3)
        self._pw = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    def _ensure_browser(self):
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

    def scrape(self, category: str, location: str) -> List[dict]:
        """Sucht auf local.ch nach Businesses einer Kategorie in einem Ort.

        Returns Liste von dicts kompatibel mit Business.from_serpapi_result().
        """
        slug = CATEGORY_SLUGS.get(category, category.lower())
        location_slug = location.lower().strip()

        results = []
        for page_num in range(1, self.max_pages + 1):
            url = f"https://www.local.ch/de/q/{urllib.parse.quote(location_slug)}/{urllib.parse.quote(slug)}"
            if page_num > 1:
                url += f"?page={page_num}"

            detail_urls = self._scrape_search_page(url, slug)
            if not detail_urls:
                break

            for detail_url in detail_urls:
                try:
                    data = self._scrape_detail_page(detail_url)
                    if data and data.get("title"):
                        results.append(data)
                except Exception as e:
                    logger.debug(f"Fehler bei Detail-Seite {detail_url}: {e}")
                    continue

            logger.info(
                f"local.ch '{category}' in {location} Seite {page_num}: "
                f"{len(detail_urls)} Einträge, {len(results)} total"
            )

            # Kurze höfliche Pause zwischen Seiten
            time.sleep(0.5)

        return results

    def _scrape_search_page(self, url: str, slug: str = "") -> List[str]:
        """Extrahiert Detail-URLs von einer Suchergebnis-Seite."""
        try:
            self._ensure_browser()
            page = self._page

            page.goto(url, wait_until="domcontentloaded", timeout=15000)
            self._accept_cookies_if_needed()

            # Auf Ergebnisse warten statt blind schlafen
            try:
                page.wait_for_selector('a[href*="/de/d/"]', timeout=6000)
            except Exception:
                pass

            # Detail-Links sammeln (mit Retry bei Context-Fehler)
            detail_urls = []
            for attempt in range(2):
                try:
                    detail_urls = self._extract_detail_urls(page, slug)
                    break
                except Exception as e:
                    if attempt == 0 and "context" in str(e).lower():
                        logger.debug(f"Context destroyed, Seite neu laden: {url}")
                        page.goto(url, wait_until="domcontentloaded", timeout=15000)
                        try:
                            page.wait_for_selector('a[href*="/de/d/"]', timeout=5000)
                        except Exception:
                            time.sleep(2)
                    else:
                        raise

            return detail_urls

        except Exception as e:
            logger.error(f"Fehler bei Suchergebnis-Seite {url}: {e}")
            return []

    def _extract_detail_urls(self, page: Page, slug: str = "") -> List[str]:
        """Extrahiert Detail-URLs aus der aktuellen Seite.

        Filtert auf URLs die den Kategorie-Slug enthalten, um
        'ähnliche Businesses' und andere Sidebar-Links auszuschliessen.
        Verwendet flexible Regex-Prüfung statt striktem Substring-Match.
        """
        links = page.query_selector_all('a[href*="/de/d/"]')
        detail_urls = []
        seen = set()

        # Flexibles Regex-Pattern: /slug/ oder /slug- oder /slug am Ende
        slug_pattern = re.compile(
            r"/" + re.escape(slug) + r"(?:[/\-]|$)", re.IGNORECASE
        ) if slug else None

        for link in links:
            href = link.get_attribute("href") or ""
            if "/de/d/" not in href:
                continue
            if not href.startswith("http"):
                href = "https://www.local.ch" + href

            # Flexibler Slug-Filter
            if slug_pattern and not slug_pattern.search(href):
                continue

            if href not in seen:
                seen.add(href)
                detail_urls.append(href)

        return detail_urls

    def _scrape_detail_page(self, url: str) -> dict:
        """Besucht eine local.ch Detail-Seite und extrahiert alle Business-Daten."""
        self._ensure_browser()
        page = self._page
        result = {}

        page.goto(url, wait_until="domcontentloaded", timeout=15000)
        try:
            page.wait_for_load_state("networkidle", timeout=4000)
        except Exception:
            pass

        # Versuche JSON-LD zu parsen (zuverlässigste Methode)
        json_ld = self._extract_json_ld(page)

        if json_ld:
            result["title"] = json_ld.get("name", "")

            # Adresse
            addr = json_ld.get("address", {})
            if isinstance(addr, dict):
                parts = [
                    addr.get("streetAddress", ""),
                    addr.get("postalCode", ""),
                    addr.get("addressLocality", ""),
                ]
                result["address"] = ", ".join(p for p in parts if p)

            # Telefon
            if json_ld.get("telephone"):
                result["phone"] = json_ld.get("telephone")

            # GPS
            geo = json_ld.get("geo", {})
            if isinstance(geo, dict):
                lat = geo.get("latitude")
                lon = geo.get("longitude")
                if lat and lon:
                    try:
                        result["gps_coordinates"] = {
                            "latitude": float(lat),
                            "longitude": float(lon),
                        }
                    except (ValueError, TypeError):
                        pass

            # Rating
            agg_rating = json_ld.get("aggregateRating", {})
            if isinstance(agg_rating, dict):
                try:
                    result["rating"] = float(agg_rating.get("ratingValue", 0))
                    result["reviews"] = int(agg_rating.get("reviewCount", 0))
                except (ValueError, TypeError):
                    pass

            # Website aus JSON-LD url-Feld (zuverlässigster Weg)
            json_ld_url = json_ld.get("url", "")
            if json_ld_url and json_ld_url.startswith("http") and "local.ch" not in json_ld_url:
                result["website"] = json_ld_url
            elif not result.get("website"):
                # Fallback: sameAs Array prüfen
                same_as = json_ld.get("sameAs", [])
                if isinstance(same_as, str):
                    same_as = [same_as]
                for link in same_as:
                    if link.startswith("http") and "local.ch" not in link:
                        domain = self._extract_domain(link)
                        if domain and not self._is_directory_domain(domain):
                            result["website"] = link
                            break

            # Beschreibung
            description = json_ld.get("description", "")
            if description:
                result["description"] = description

            # Öffnungszeiten
            hours_spec = json_ld.get("openingHoursSpecification")
            hours_str = _format_hours(hours_spec)
            if hours_str:
                result["hours"] = hours_str

            # Place-ID aus URL
            result["place_id"] = self._extract_place_id(url)

        # Fallback: Name aus DOM
        if not result.get("title"):
            h1 = page.query_selector("h1")
            if h1:
                result["title"] = h1.inner_text().strip()

        # Telefon aus tel:-Link (oft zuverlässiger als JSON-LD)
        if not result.get("phone"):
            tel_links = page.query_selector_all('a[href^="tel:"]')
            for link in tel_links:
                href = link.get_attribute("href") or ""
                phone = href.replace("tel:", "").strip()
                if phone and len(phone) >= 8:
                    result["phone"] = phone
                    break

        # Telefon formatieren
        if result.get("phone"):
            result["phone"] = _format_swiss_phone(result["phone"])

        # E-Mail aus mailto-Link
        mailto_links = page.query_selector_all('a[href^="mailto:"]')
        for link in mailto_links:
            href = link.get_attribute("href") or ""
            email = href.replace("mailto:", "").split("?")[0].strip().lower()
            if email and "@" in email:
                result["email"] = email
                break

        # Website aus DOM (nur wenn noch keine gefunden)
        if not result.get("website"):
            website = self._extract_website(page)
            if website:
                result["website"] = website

        # Kategorie aus Seite
        result["type"] = self._extract_category(page, url)

        # Fax (schnelle Body-Text Methode)
        fax = self._extract_fax(page)
        if fax:
            result["fax"] = fax

        # Text bereinigen: Mojibake und escaped Unicode
        for key in ("title", "address", "description"):
            if result.get(key):
                result[key] = _fix_mojibake(result[key])
                result[key] = re.sub(
                    r"\\u([0-9a-fA-F]{4})",
                    lambda m: chr(int(m.group(1), 16)),
                    result[key],
                )

        return result

    def _extract_json_ld(self, page: Page) -> Optional[dict]:
        """Extrahiert JSON-LD Schema.org Daten aus der Seite.

        Parsing im Browser-JS-Context, damit Encoding korrekt bleibt.
        """
        try:
            result = page.evaluate("""() => {
                const scripts = document.querySelectorAll('script[type="application/ld+json"]');
                for (const script of scripts) {
                    try {
                        const data = JSON.parse(script.textContent);
                        if (Array.isArray(data)) {
                            for (const item of data) {
                                if (item['@type'] === 'LocalBusiness') return item;
                            }
                        } else if (data && data['@type'] === 'LocalBusiness') {
                            return data;
                        }
                    } catch (e) {}
                }
                return null;
            }""")
            return result
        except Exception:
            return None

    def _extract_website(self, page: Page) -> Optional[str]:
        """Extrahiert die Website-URL aus der Detail-Seite via DOM (Fallback).

        Priorität:
        1. Links mit Text 'website', 'webseite', 'homepage' (case-insensitive)
        2. Links deren Text wie eine Domain aussieht
        3. Externe nofollow-Links (strikt gefiltert)
        """
        try:
            links = page.query_selector_all("a[href]")
            for link in links:
                text = (link.inner_text() or "").strip().lower()
                href = link.get_attribute("href") or ""

                if not href.startswith("http") or "local.ch" in href:
                    continue

                # Expliziter Website-Link
                if text in ("website", "homepage", "webseite", "zur website", "webseite besuchen"):
                    domain = self._extract_domain(href)
                    if domain and not self._is_directory_domain(domain):
                        return href

                # Link-Text sieht wie eine Domain aus (z.B. "beispiel.ch")
                if re.match(r"^[a-z0-9\-]+\.[a-z]{2,}(/.*)?$", text):
                    domain = self._extract_domain(href)
                    if domain and not self._is_directory_domain(domain):
                        return href

            # Letzter Fallback: externe nofollow-Links
            external_links = page.query_selector_all('a[rel*="nofollow"][href^="http"]')
            for link in external_links:
                href = link.get_attribute("href") or ""
                domain = self._extract_domain(href)
                if domain and not self._is_directory_domain(domain):
                    return href

        except Exception:
            pass
        return None

    def _extract_category(self, page: Page, url: str) -> Optional[str]:
        """Kategorie aus der URL oder Seite extrahieren."""
        match = re.search(r"/de/d/[^/]+/\d+/([^/]+)/", url)
        if match:
            return match.group(1).replace("-", " ").title()
        return None

    def _extract_fax(self, page: Page) -> Optional[str]:
        """Extrahiert Fax-Nummer aus dem Seiten-Text (schnell via Body-Text)."""
        try:
            text = page.inner_text("body")
            match = re.search(r"[Ff]ax\s*:?\s*([\+\d\s\-]{7,20})", text)
            if match:
                fax = match.group(1).strip()
                # Mindestens 7 Ziffern
                if len(re.sub(r"\D", "", fax)) >= 7:
                    return fax
        except Exception:
            pass
        return None

    @staticmethod
    def _extract_place_id(url: str) -> str:
        """Extrahiert eine eindeutige ID aus der local.ch URL."""
        parts = url.rstrip("/").split("/")
        if parts:
            last = parts[-1]
            dash_idx = last.rfind("-")
            if dash_idx > 0 and len(last) - dash_idx > 5:
                return "localch_" + last[dash_idx + 1:]
            return "localch_" + last
        return "localch_unknown"

    @staticmethod
    def _extract_domain(url: str) -> Optional[str]:
        """Extrahiert die Domain aus einer URL."""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain = parsed.hostname or ""
            if domain.startswith("www."):
                domain = domain[4:]
            return domain.lower()
        except Exception:
            return None

    @staticmethod
    def _is_directory_domain(domain: str) -> bool:
        """Prüft ob eine Domain ein Verzeichnis/Social Media ist."""
        for blocked in DIRECTORY_DOMAINS:
            if domain == blocked or domain.endswith("." + blocked):
                return True
        return False

    def _accept_cookies_if_needed(self):
        """Akzeptiert Cookie-Banner falls einer sichtbar ist."""
        page = self._page
        try:
            for selector in [
                'button:has-text("Alle akzeptieren")',
                'button:has-text("Accept all")',
                'button:has-text("Alles akzeptieren")',
                'button:has-text("Akzeptieren")',
                '#onetrust-accept-btn-handler',
            ]:
                btn = page.query_selector(selector)
                if btn and btn.is_visible():
                    btn.click()
                    try:
                        page.wait_for_load_state("networkidle", timeout=3000)
                    except Exception:
                        time.sleep(0.5)
                    return
        except Exception:
            pass
