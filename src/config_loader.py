import os
import yaml


def load_config(config_path: str = "config.yaml") -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # Umgebungsvariable überschreibt config.yaml
    env_key = os.environ.get("SERPAPI_KEY")
    if env_key:
        config["api_keys"]["serpapi"] = env_key

    _validate(config)
    return config


def _validate(config: dict):
    key = config.get("api_keys", {}).get("serpapi", "")
    if not key:
        import logging
        logging.getLogger(__name__).info(
            "Kein SerpAPI Key gesetzt → Playwright-Modus (kostenlos, kein API-Key nötig)"
        )

    if not config.get("search_terms"):
        raise ValueError("Keine Suchbegriffe in config.yaml definiert.")

    area = config.get("search_area", {})
    for field in ("lat_min", "lat_max", "lon_min", "lon_max", "lat_step", "lon_step", "zoom"):
        if field not in area:
            raise ValueError(f"search_area.{field} fehlt in config.yaml.")
