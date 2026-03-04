import argparse
import logging
import sys
import os
from datetime import datetime, timezone

from tqdm import tqdm

# src/ als Modul-Pfad
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config_loader import load_config
from search_strategy import generate_grid
from scraper_serpapi import SerpApiScraper
from deduplicator import Deduplicator
from filter import filter_no_website
from exporter import export_results
from progress import ProgressTracker
from models import Business

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(
        description="Google Maps Scraper - Businesses ohne Website im Raum Zürich"
    )
    parser.add_argument(
        "--config", default="config.yaml", help="Pfad zur config.yaml"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Zeigt den Suchplan ohne API-Calls"
    )
    parser.add_argument(
        "--reset", action="store_true",
        help="Setzt den Fortschritt zurück (Neustart)"
    )
    parser.add_argument(
        "--terms", nargs="*",
        help="Nur bestimmte Suchbegriffe verwenden (für Tests)"
    )
    args = parser.parse_args()

    config = load_config(args.config)
    grid_points = generate_grid(config["search_area"])
    search_terms = args.terms if args.terms else config["search_terms"]

    total_combinations = len(search_terms) * len(grid_points)

    logger.info(f"Suchgebiet: {config['search_area']['name']}")
    logger.info(f"Grid-Punkte: {len(grid_points)}")
    logger.info(f"Suchbegriffe: {len(search_terms)}")
    logger.info(f"Kombinationen total: {total_combinations}")

    if args.dry_run:
        logger.info("--- Dry-Run: Keine API-Calls ---")
        logger.info(f"Suchbegriffe: {search_terms}")
        logger.info(f"Erster Grid-Punkt: {grid_points[0].to_ll_param()}")
        logger.info(f"Letzter Grid-Punkt: {grid_points[-1].to_ll_param()}")
        estimated_calls = total_combinations * 2  # ~2 Seiten im Schnitt
        logger.info(f"Geschätzte API-Calls: ~{estimated_calls}")
        return

    # Progress-Tracker
    progress_conf = config["progress"]
    progress = ProgressTracker(progress_conf["directory"], progress_conf["enabled"])

    if args.reset:
        progress.reset()
        logger.info("Fortschritt zurückgesetzt.")

    # Scraper
    scraper = SerpApiScraper(config)
    deduplicator = Deduplicator()
    all_businesses: list[Business] = []

    skipped = progress.completed_count
    if skipped > 0:
        logger.info(f"Fortsetzen: {skipped} Kombinationen bereits erledigt")

    # Haupt-Scraping-Loop
    with tqdm(total=total_combinations, initial=skipped, desc="Scraping") as pbar:
        for term in search_terms:
            for point in grid_points:
                if progress.is_completed(term, point.latitude, point.longitude):
                    continue

                try:
                    results = scraper.scrape_all_pages(term, point.to_ll_param())

                    for raw in results:
                        biz = Business.from_serpapi_result(raw, term)
                        biz.scraped_at = datetime.now(timezone.utc).isoformat()

                        if not deduplicator.is_duplicate(biz):
                            all_businesses.append(biz)

                    progress.mark_completed(term, point.latitude, point.longitude)
                    pbar.update(1)

                    # Regelmässig speichern
                    checkpoint_interval = progress_conf["checkpoint_every_n_queries"]
                    if progress.completed_count % checkpoint_interval == 0:
                        progress.save()

                except KeyboardInterrupt:
                    logger.info("Unterbrochen! Speichere Fortschritt...")
                    progress.save()
                    _export_partial(config, all_businesses)
                    sys.exit(0)

                except Exception as e:
                    logger.error(f"Fehler bei '{term}' @ ({point.latitude}, {point.longitude}): {e}")
                    continue

    progress.save()

    # Filtern und Exportieren
    logger.info(f"Unique Businesses gefunden: {len(all_businesses)}")

    filtering = config["filtering"]
    if filtering["keep_only_no_website"]:
        filtered = filter_no_website(
            all_businesses,
            treat_social_as_no_website=filtering["treat_social_media_as_no_website"],
            social_domains=filtering.get("social_media_domains"),
        )
    else:
        filtered = all_businesses

    logger.info(f"Davon ohne Website: {len(filtered)}")

    output_conf = config["output"]
    files = export_results(
        filtered,
        output_dir=output_conf["directory"],
        fmt=output_conf["format"],
        prefix=output_conf["filename_prefix"],
    )
    for f in files:
        logger.info(f"Exportiert: {f}")

    logger.info("Fertig!")


def _export_partial(config: dict, businesses: list):
    """Exportiert Teilergebnisse bei Unterbrechung."""
    if not businesses:
        return

    filtering = config["filtering"]
    if filtering["keep_only_no_website"]:
        filtered = filter_no_website(
            businesses,
            treat_social_as_no_website=filtering["treat_social_media_as_no_website"],
            social_domains=filtering.get("social_media_domains"),
        )
    else:
        filtered = businesses

    output_conf = config["output"]
    files = export_results(
        filtered,
        output_dir=output_conf["directory"],
        fmt=output_conf["format"],
        prefix=output_conf["filename_prefix"] + "_partial",
    )
    for f in files:
        logger.info(f"Teilergebnis exportiert: {f}")


if __name__ == "__main__":
    main()
