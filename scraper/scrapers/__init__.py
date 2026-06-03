from __future__ import annotations
from typing import Callable


def get_scraper(url: str) -> Callable[[str], list[dict]]:
    """Return the scrape(url) function for the given binder URL."""
    if "moxfield.com" in url:
        from .moxfield import scrape
        return scrape
    if "deckstats.net" in url:
        from .deckstats import scrape
        return scrape
    raise ValueError(f"Unsupported binder URL: {url}")
