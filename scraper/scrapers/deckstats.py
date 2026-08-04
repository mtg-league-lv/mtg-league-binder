# scraper/scrapers/deckstats.py
import re
import math
import logging
import urllib.parse
from patchright.sync_api import sync_playwright
from .base import launch_real_browser

log = logging.getLogger(__name__)

# Deckstats only honours a whitelist of page sizes on /api/collection/list and
# silently falls back to 50 for anything else. 500 is the largest accepted value.
PAGE_SIZE = 500

API_PATH = "/api/collection/list"

# Deckstats moved binders from /collection/<id> to /binders/<id>. The numeric ID
# is unchanged, so both forms are accepted for binders registered under the old
# URL.
BINDER_ID_RE = re.compile(r"/(?:binders|collection)/(\d+)")


def extract_collection_id(url: str) -> str:
    match = BINDER_ID_RE.search(url)
    if not match:
        raise ValueError(f"Cannot extract collection ID from URL: {url}")
    return match.group(1)


def binder_url(collection_id: str) -> str:
    return f"https://deckstats.net/binders/{collection_id}"


def api_url(collection_id: str, page: int, per_page: int = PAGE_SIZE) -> str:
    query = urllib.parse.urlencode(
        {
            "public_binder": collection_id,
            "sort": "name",
            "dir": "asc",
            "page": page,
            "per_page": per_page,
        }
    )
    return f"https://deckstats.net{API_PATH}?{query}"


# CloudFlare fingerprints Playwright's out-of-band HTTP client and answers it
# with 403, so the API has to be called from inside the loaded page instead.
_FETCH_JS = """
async (url) => {
  const res = await fetch(url, { credentials: 'include' });
  if (!res.ok) return { status: res.status, data: null };
  return { status: res.status, data: await res.json() };
}
"""


def parse_deckstats_response(api_response: dict) -> list[dict]:
    """Parse cards from a Deckstats /api/collection/list response.

    Response shape:
      {"total": N, "page": N, "per_page": N,
       "items": [{"name": "...", "amount": N, ...}, ...]}
    """
    result = []
    rows = api_response.get("items", [])
    if not isinstance(rows, list):
        return result
    for entry in rows:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name", "")
        amount = entry.get("amount", 1)
        try:
            qty = int(amount)
        except (ValueError, TypeError):
            qty = 1
        if name:
            result.append({"card_name": name.lower().strip(), "quantity": qty})
    return result


def total_pages(total: int, per_page: int) -> int:
    """Number of pages needed to cover `total` entries."""
    if total <= 0 or per_page <= 0:
        return 0
    return math.ceil(total / per_page)


def scrape(url: str) -> list[dict]:
    """Load a Deckstats binder page and fetch all cards via the JSON API."""
    collection_id = extract_collection_id(url)
    all_cards: list[dict] = []

    with sync_playwright() as p:
        with launch_real_browser(p) as context:
            page = context.new_page()

            # Load the binder page first so the browser picks up the CloudFlare
            # clearance cookies the API requires.
            target = binder_url(collection_id)
            log.info("Navigating to %s", target)
            page.goto(target, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(5000)

            page_number = 1
            pages = None
            while pages is None or page_number <= pages:
                resp = page.evaluate(_FETCH_JS, api_url(collection_id, page_number))
                if resp.get("status") != 200 or not resp.get("data"):
                    log.warning(
                        "Non-200 response %s for page %s of collection %s",
                        resp.get("status"),
                        page_number,
                        collection_id,
                    )
                    break
                data = resp["data"]

                if pages is None:
                    total = int(data.get("total", 0))
                    # The API clamps per_page to a whitelist; trust what it returns.
                    per_page = int(data.get("per_page") or PAGE_SIZE)
                    pages = total_pages(total, per_page)
                    log.info(
                        "Deckstats collection %s: %s entries, %s per page, %s pages",
                        collection_id,
                        total,
                        per_page,
                        pages,
                    )
                    if pages == 0:
                        break

                cards = parse_deckstats_response(data)
                if not cards:
                    log.warning("Page %s returned no cards, stopping", page_number)
                    break
                all_cards.extend(cards)
                log.info("Parsed %s cards from page %s/%s", len(cards), page_number, pages)
                page_number += 1

    if all_cards:
        log.info(
            "Total cards scraped from deckstats collection %s: %s",
            collection_id,
            len(all_cards),
        )
    else:
        log.warning("No cards found for deckstats collection %s", collection_id)

    return all_cards
