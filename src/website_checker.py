import logging
import re
import time
import urllib.parse
from typing import Optional, TYPE_CHECKING
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page

if TYPE_CHECKING:
    from models import Business

logger = logging.getLogger(__name__)

# Regex für E-Mail-Adressen
EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')

# E-Mail-Domains die ignoriert werden (keine echten Kontakt-Mails)
IGNORED_EMAIL_DOMAINS = {
    "example.com", "example.org", "test.com",
    "sentry.io", "google.com", "googlemail.com",
    "facebook.com", "apple.com", "microsoft.com",
    "wixpress.com", "squarespace.com", "wordpress.com",
    "placeholder.com", "email.com", "domain.com",
}

# Kostenlose / ISP E-Mail-Provider → kein Hinweis auf eigene Website
FREE_EMAIL_PROVIDERS = {
    # Webmail international
    "gmail.com", "googlemail.com",
    "yahoo.com", "yahoo.de", "yahoo.ch", "yahoo.fr",
    "hotmail.com", "hotmail.ch", "hotmail.de",
    "outlook.com", "outlook.ch", "outlook.de",
    "live.com", "live.ch", "live.de",
    "msn.com", "icloud.com", "me.com", "mac.com",
    "aol.com", "aol.de",
    # Schweizer ISPs
    "bluewin.ch", "bluemail.ch",
    "sunrise.ch", "sunrisemail.ch",
    "hispeed.ch", "tele2.ch",
    "swisscom.ch", "swisscom.net",
    "quickline.ch", "vtxnet.ch",
    # Deutsche ISPs / Webmail
    "gmx.ch", "gmx.net", "gmx.de", "gmx.at", "gmx.com",
    "web.de", "freenet.de", "t-online.de", "arcor.de",
    "1und1.de", "versatel.de",
    # Datenschutz-Webmail
    "protonmail.com", "protonmail.ch", "pm.me",
    "tutanota.com", "tutanota.de",
    "mailbox.org", "posteo.de", "posteo.ch",
}


def is_free_email_provider(domain: str) -> bool:
    """Prüft ob eine E-Mail-Domain ein kostenloser/ISP-Anbieter ist."""
    return domain.lower() in FREE_EMAIL_PROVIDERS


def check_domain_has_website(domain: str) -> Optional[str]:
    """Prüft per HTTP-Request ob eine Domain eine Website hat.

    Viel schneller als Playwright — kein Browser nötig.
    Returns die finale URL wenn erreichbar, sonst None.
    """
    import httpx
    for scheme in ("https", "http"):
        url = f"{scheme}://{domain}"
        try:
            resp = httpx.get(
                url,
                timeout=6,
                follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0.0.0"},
            )
            if resp.status_code < 400:
                final = str(resp.url)
                # Sicherstellen dass es nicht zu local.ch oder ähnlichem umgeleitet wurde
                if "local.ch" not in final and "google." not in final:
                    return final
        except Exception:
            continue
    return None

# Domains die NICHT als echte Website zählen (Verzeichnisse, Social Media, etc.)
DIRECTORY_DOMAINS = {
    "facebook.com", "instagram.com", "twitter.com", "x.com",
    "tiktok.com", "linkedin.com", "youtube.com", "xing.com",
    "pinterest.com", "pinterest.ch", "whatsapp.com", "telegram.org",
    "local.ch", "search.ch", "localsearch.ch",
    "yelp.com", "yelp.ch", "tripadvisor.com", "tripadvisor.ch",
    "google.com", "google.ch", "maps.google.com",
    "yellow.pages", "gelbeseiten.ch", "comparis.ch",
    "kununu.com", "glassdoor.com",
    "wikipedia.org", "wikidata.org",
    "apple.com",  # Apple Maps
    "trustpilot.com",
    "handwerkerregion.ch", "renovero.ch",
    "meinbezirk.at",
    "branchenindex.ch",
    # Neu hinzugefügt:
    "trivago.ch", "trivago.com",
    "booking.com",
    "zoominfo.com",
    "tel.search.ch",
    "yellowpages.com",
    "firmen.ch",
    "moneyhouse.ch",
    "zefix.ch",
    "dastelefonbuch.de",
}


class WebsiteChecker:
    """Verifiziert via Google-Suche ob ein Business wirklich keine Website hat."""

    def __init__(self):
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

    def find_email(self, business: "Business", location: str) -> Optional[str]:
        """Sucht per Google nach einer E-Mail-Adresse für das Business.

        Returns die gefundene E-Mail oder None.
        """
        name = business.name
        if not name:
            return None

        # Strategie 1: Google-Suche nach E-Mail (mit Anführungszeichen für exakten Namen)
        query = f'"{name}" {location} email OR kontakt OR impressum'
        email = self._google_search_email(query)
        if email:
            return email

        # Strategie 2: Falls Website bekannt, dort nach E-Mail suchen
        website = business.website
        if website:
            email = self._scrape_email_from_website(website)
            if email:
                return email

        return None

    def _google_search_email(self, query: str) -> Optional[str]:
        """Google-Suche durchführen und E-Mail-Adressen aus Snippets extrahieren."""
        try:
            self._ensure_browser()
            page = self._page

            encoded = urllib.parse.quote(query)
            url = f"https://www.google.com/search?q={encoded}&hl=de&gl=ch"

            page.goto(url, wait_until="domcontentloaded", timeout=15000)
            self._accept_cookies_if_needed()

            # Auf Suchergebnisse warten statt blind schlafen
            try:
                page.wait_for_selector("#search", timeout=5000)
            except Exception:
                time.sleep(1)

            # Gesamten sichtbaren Text der Suchergebnisse holen
            search_div = page.query_selector("#search")
            if not search_div:
                return None

            text = search_div.inner_text()
            emails = EMAIL_RE.findall(text)

            for email in emails:
                email = email.lower()
                domain = email.split("@")[1]
                if domain not in IGNORED_EMAIL_DOMAINS:
                    logger.debug(f"E-Mail gefunden für '{query}': {email}")
                    return email

            return None

        except Exception as e:
            logger.debug(f"E-Mail-Suche Fehler für '{query}': {e}")
            return None

    def _scrape_email_from_website(self, url: str) -> Optional[str]:
        """Besucht eine Website und sucht nach E-Mail-Adressen."""
        try:
            self._ensure_browser()
            page = self._page

            page.goto(url, wait_until="domcontentloaded", timeout=10000)
            try:
                page.wait_for_load_state("networkidle", timeout=4000)
            except Exception:
                pass

            # mailto: Links suchen
            mailto_links = page.query_selector_all('a[href^="mailto:"]')
            for link in mailto_links:
                href = link.get_attribute("href") or ""
                email = href.replace("mailto:", "").split("?")[0].strip().lower()
                if email and "@" in email:
                    domain = email.split("@")[1]
                    if domain not in IGNORED_EMAIL_DOMAINS:
                        logger.debug(f"E-Mail auf Website gefunden: {email}")
                        return email

            # Fallback: Seitentext nach E-Mail durchsuchen
            text = page.inner_text("body")
            emails = EMAIL_RE.findall(text)
            for email in emails:
                email = email.lower()
                domain = email.split("@")[1]
                if domain not in IGNORED_EMAIL_DOMAINS:
                    logger.debug(f"E-Mail im Text gefunden: {email}")
                    return email

            # Kontakt-/Impressum-Seite versuchen
            for keyword in ["kontakt", "contact", "impressum", "about"]:
                contact_link = page.query_selector(f'a[href*="{keyword}"]')
                if contact_link:
                    try:
                        contact_link.click()
                        try:
                            page.wait_for_load_state("networkidle", timeout=4000)
                        except Exception:
                            time.sleep(1)

                        mailto_links = page.query_selector_all('a[href^="mailto:"]')
                        for link in mailto_links:
                            href = link.get_attribute("href") or ""
                            email = href.replace("mailto:", "").split("?")[0].strip().lower()
                            if email and "@" in email:
                                domain = email.split("@")[1]
                                if domain not in IGNORED_EMAIL_DOMAINS:
                                    logger.debug(f"E-Mail auf Kontaktseite gefunden: {email}")
                                    return email

                        text = page.inner_text("body")
                        emails = EMAIL_RE.findall(text)
                        for email in emails:
                            email = email.lower()
                            domain = email.split("@")[1]
                            if domain not in IGNORED_EMAIL_DOMAINS:
                                return email
                    except Exception:
                        pass
                    break  # Nur eine Kontaktseite versuchen

            return None

        except Exception as e:
            logger.debug(f"Website-Scrape Fehler für '{url}': {e}")
            return None

    def has_website(self, business: "Business", location: str) -> Optional[str]:
        """Googelt ein Business und prüft ob eine echte Website existiert.

        Returns die gefundene Website-URL oder None.
        """
        name = business.name
        if not name:
            return None

        query = f'"{name}" {location}'
        return self._google_search(query)

    def _google_search(self, query: str) -> Optional[str]:
        """Führt eine Google-Suche durch und prüft die Ergebnisse."""
        try:
            self._ensure_browser()
            page = self._page

            encoded = urllib.parse.quote(query)
            url = f"https://www.google.com/search?q={encoded}&hl=de&gl=ch"

            page.goto(url, wait_until="domcontentloaded", timeout=15000)
            self._accept_cookies_if_needed()

            # Auf Suchergebnisse warten statt blind schlafen
            try:
                page.wait_for_selector("#search", timeout=5000)
            except Exception:
                time.sleep(1)

            # Suchergebnisse parsen - die ersten 8 Links prüfen
            links = page.query_selector_all("#search a[href]")

            for link in links[:8]:
                href = link.get_attribute("href") or ""

                # Nur echte URLs
                if not href.startswith("http"):
                    continue

                # Domain extrahieren
                domain = self._extract_domain(href)
                if not domain:
                    continue

                # Verzeichnisse und Social Media ignorieren
                if self._is_directory(domain):
                    continue

                # Echte Website gefunden!
                logger.debug(f"Website gefunden für '{query}': {href}")
                return href

            return None

        except Exception as e:
            logger.debug(f"Google-Check Fehler für '{query}': {e}")
            return None

    def _accept_cookies_if_needed(self):
        """Akzeptiert Cookie-Banner falls einer sichtbar ist."""
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
                    try:
                        page.wait_for_load_state("networkidle", timeout=3000)
                    except Exception:
                        time.sleep(0.5)
                    return
        except Exception:
            pass

    @staticmethod
    def _extract_domain(url: str) -> Optional[str]:
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain = parsed.hostname or ""
            # www. entfernen
            if domain.startswith("www."):
                domain = domain[4:]
            return domain.lower()
        except Exception:
            return None

    @staticmethod
    def _is_directory(domain: str) -> bool:
        """Prüft ob eine Domain ein Verzeichnis/Social Media ist."""
        for blocked in DIRECTORY_DOMAINS:
            if domain == blocked or domain.endswith("." + blocked):
                return True
        return False
