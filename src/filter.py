from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from models import Business


def filter_no_website(
    businesses: List["Business"],
    treat_social_as_no_website: bool = True,
    social_domains: Optional[List[str]] = None,
) -> List["Business"]:
    """Filtert Businesses die KEINE echte Website haben."""
    if social_domains is None:
        social_domains = [
            "facebook.com", "instagram.com", "twitter.com",
            "x.com", "tiktok.com", "linkedin.com",
            "xing.com", "pinterest.ch", "pinterest.com",
            "whatsapp.com", "telegram.org",
        ]

    result = []
    for biz in businesses:
        website = (biz.website or "").strip()

        if not website:
            result.append(biz)
            continue

        if treat_social_as_no_website:
            is_social = any(domain in website.lower() for domain in social_domains)
            if is_social:
                biz.has_website = False
                result.append(biz)

    return result


def categorize_leads(
    businesses: List["Business"],
    treat_social_as_no_website: bool = True,
    social_domains: Optional[List[str]] = None,
) -> List["Business"]:
    """Kategorisiert alle Businesses nach Lead-Typ.

    Setzt lead_type auf:
    - "Keine Website" → kein Website-Feld oder nur Social Media
    - "Website vorhanden" → hat eine echte Website
    """
    if social_domains is None:
        social_domains = [
            "facebook.com", "instagram.com", "twitter.com",
            "x.com", "tiktok.com", "linkedin.com",
            "xing.com", "pinterest.ch", "pinterest.com",
            "whatsapp.com", "telegram.org",
        ]

    for biz in businesses:
        website = (biz.website or "").strip()

        if not website:
            biz.lead_type = "Keine Website"
            continue

        if treat_social_as_no_website:
            is_social = any(domain in website.lower() for domain in social_domains)
            if is_social:
                biz.has_website = False
                biz.lead_type = "Keine Website"
                continue

        biz.lead_type = "Website vorhanden"

    return businesses
