import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from deduplicator import Deduplicator
from filter import categorize_leads
from website_checker import WebsiteChecker
from scraper_localch import LocalChScraper
from models import Business

logger = logging.getLogger(__name__)


@dataclass
class JobStatus:
    job_id: str
    status: str = "pending"  # pending, running, verifying, completed, error
    location: str = ""
    location_display: str = ""
    total_categories: int = 0
    completed_categories: int = 0
    current_term: str = ""
    total_found: int = 0
    no_website_count: int = 0
    has_website_count: int = 0
    verified_count: int = 0
    verify_total: int = 0
    email_found_count: int = 0
    error_message: str = ""
    all_businesses: list = field(default_factory=list)
    filtered_businesses: list = field(default_factory=list)

    @property
    def progress_pct(self) -> float:
        if self.status == "verifying":
            if self.verify_total == 0:
                return 95.0
            return round(95.0 + (self.verified_count / self.verify_total * 5.0), 1)
        if self.total_categories == 0:
            return 0.0
        return round(self.completed_categories / self.total_categories * 95.0, 1)


class ScraperService:
    """Verwaltet Scraping-Jobs als Background-Threads."""

    def __init__(self, config: dict):
        self.config = config
        self.jobs: dict[str, JobStatus] = {}

    def start_job(
        self,
        categories: list[str],
        location_name: str,
        location_display: str,
    ) -> str:
        job_id = str(uuid.uuid4())[:8]
        job = JobStatus(
            job_id=job_id,
            location=location_name,
            location_display=location_display,
        )
        self.jobs[job_id] = job

        thread = threading.Thread(
            target=self._run_job,
            args=(job, categories),
            daemon=True,
        )
        thread.start()
        return job_id

    def get_job(self, job_id: str) -> Optional[JobStatus]:
        return self.jobs.get(job_id)

    def _run_job(self, job: JobStatus, categories: list[str]):
        job.status = "running"
        scraper = None
        checker = None

        try:
            job.total_categories = len(categories)

            scraper = LocalChScraper(self.config)
            deduplicator = Deduplicator()
            all_businesses: list[Business] = []

            # --- Phase 1: local.ch Scraping ---
            for term in categories:
                job.current_term = term
                try:
                    results = scraper.scrape(term, job.location)

                    for raw in results:
                        biz = Business.from_serpapi_result(raw, term)
                        biz.scraped_at = datetime.now(timezone.utc).isoformat()
                        if not deduplicator.is_duplicate(biz):
                            all_businesses.append(biz)
                            # E-Mail direkt von local.ch zählen
                            if biz.email:
                                job.email_found_count += 1

                    job.completed_categories += 1
                    job.total_found = len(all_businesses)

                except Exception as e:
                    logger.error(f"Fehler bei '{term}' in {job.location}: {e}")
                    job.completed_categories += 1
                    continue

            # Scraper schliessen bevor Checker startet
            if scraper:
                scraper.close()
                scraper = None

            # --- Phase 2: Kategorisierung ---
            filtering = self.config.get("filtering", {})
            candidates = categorize_leads(
                all_businesses,
                treat_social_as_no_website=filtering.get("treat_social_media_as_no_website", True),
                social_domains=filtering.get("social_media_domains"),
            )

            no_website_candidates = [b for b in candidates if b.lead_type == "Keine Website"]
            has_website_candidates = [b for b in candidates if b.lead_type == "Website vorhanden"]

            logger.info(
                f"Job {job.job_id}: {len(all_businesses)} gefunden, "
                f"{len(no_website_candidates)} ohne Website, "
                f"{len(has_website_candidates)} mit Website → Verifizierung"
            )

            # --- Phase 3: Google-Verifizierung (nur für "Keine Website") ---
            job.status = "verifying"
            job.current_term = "Google-Verifizierung..."
            job.verify_total = len(no_website_candidates)
            job.verified_count = 0

            checker = WebsiteChecker()

            for biz in no_website_candidates:
                try:
                    found_url = checker.has_website(biz, job.location)
                    if found_url:
                        # Google hat eine Website gefunden → umkategorisieren
                        biz.website = found_url
                        biz.has_website = True
                        biz.lead_type = "Website vorhanden"
                        logger.info(f"  Website gefunden: {biz.name} → {found_url}")

                    # Falls noch keine E-Mail, via Google suchen
                    if not biz.email:
                        try:
                            found_email = checker.find_email(biz, job.location)
                            if found_email:
                                biz.email = found_email
                                job.email_found_count += 1
                                logger.info(f"  E-Mail gefunden: {biz.name} → {found_email}")
                        except Exception as e:
                            logger.debug(f"  E-Mail-Suche Fehler bei {biz.name}: {e}")

                except Exception as e:
                    logger.debug(f"  Check-Fehler bei {biz.name}: {e}")

                job.verified_count += 1
                job.no_website_count = sum(1 for b in candidates if b.lead_type == "Keine Website")
                job.has_website_count = sum(1 for b in candidates if b.lead_type == "Website vorhanden")

            # Sortieren: "Keine Website" zuerst, dann "Website vorhanden"
            lead_order = {"Keine Website": 0, "Website vorhanden": 1}
            candidates.sort(key=lambda b: lead_order.get(b.lead_type, 2))

            job.all_businesses = all_businesses
            job.filtered_businesses = candidates
            job.no_website_count = sum(1 for b in candidates if b.lead_type == "Keine Website")
            job.has_website_count = sum(1 for b in candidates if b.lead_type == "Website vorhanden")
            job.current_term = ""
            job.status = "completed"

            logger.info(
                f"Job {job.job_id} fertig: {len(all_businesses)} total, "
                f"{job.no_website_count} ohne Website, "
                f"{job.has_website_count} mit Website, "
                f"{job.email_found_count} E-Mails gefunden"
            )

        except Exception as e:
            job.status = "error"
            job.error_message = str(e)
            logger.error(f"Job {job.job_id} fehlgeschlagen: {e}")
        finally:
            if scraper:
                scraper.close()
            if checker:
                checker.close()
