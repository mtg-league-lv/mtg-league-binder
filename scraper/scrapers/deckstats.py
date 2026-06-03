# scraper/scrapers/deckstats.py
import re
import logging
import urllib.parse
from patchright.sync_api import sync_playwright
from .base import launch_browser

log = logging.getLogger(__name__)

PAGE_SIZE = 100  # DataTables page size used by deckstats


def extract_collection_id(url: str) -> str:
    match = re.search(r"/collection/(\d+)", url)
    if not match:
        raise ValueError(f"Cannot extract collection ID from URL: {url}")
    return match.group(1)


def parse_deckstats_response(api_response: dict) -> list[dict]:
    """Parse cards from a Deckstats api_cards.php DataTables response.

    Response shape:
      {"iTotalRecords": N, "aaData": [{"name": "...", "amount": "N"}, ...]}
    """
    result = []
    rows = api_response.get("aaData", [])
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


def scrape(url: str) -> list[dict]:
    """Load a Deckstats collection page and fetch all cards via the DataTables API."""
    collection_id = extract_collection_id(url)
    all_cards: list[dict] = []
    total_records = None
    first_api_url = None

    with sync_playwright() as p:
        with launch_browser(p) as (browser, context):
            page = context.new_page()

            def handle_response(response):
                nonlocal total_records, first_api_url
                if (
                    "api_cards.php" in response.url
                    and response.status == 200
                    and collection_id in response.url
                ):
                    try:
                        data = response.json()
                        if total_records is None:
                            total_records = int(data.get("iTotalRecords", 0))
                            first_api_url = response.url
                            log.info(
                                "Deckstats collection %s: %s total records, api url: %s",
                                collection_id,
                                total_records,
                                first_api_url[:120],
                            )
                        cards = parse_deckstats_response(data)
                        if cards:
                            all_cards.extend(cards)
                            log.info(
                                "Parsed %s cards from %s",
                                len(cards),
                                response.url[:100],
                            )
                    except Exception as exc:
                        log.warning("Failed to parse deckstats response: %s", exc)

            page.on("response", handle_response)

            log.info("Navigating to %s", url)
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(10000)

            # Fetch remaining pages via page.request (uses session cookies)
            if total_records and total_records > PAGE_SIZE and first_api_url:
                # Derive base URL by stripping iDisplayStart from the intercepted URL
                parsed = urllib.parse.urlparse(first_api_url)
                params = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
                # Remove iDisplayStart so we can set it ourselves
                params.pop("iDisplayStart", None)
                # Flatten single-value lists
                flat_params = {k: v[0] for k, v in params.items()}

                for start in range(PAGE_SIZE, total_records, PAGE_SIZE):
                    flat_params["iDisplayStart"] = str(start)
                    api_url = urllib.parse.urlunparse(
                        parsed._replace(query=urllib.parse.urlencode(flat_params))
                    )
                    log.info(
                        "Fetching page starting at %s/%s", start, total_records
                    )
                    resp = page.request.get(api_url)
                    if resp.status != 200:
                        log.warning("Non-200 response %s for offset %s", resp.status, start)
                        continue
                    result = resp.json()
                    cards = parse_deckstats_response(result)
                    all_cards.extend(cards)
                    log.info("Fetched %s cards (offset %s)", len(cards), start)

    if all_cards:
        log.info("Total cards scraped from deckstats collection %s: %s", collection_id, len(all_cards))
    else:
        log.warning("No cards found for deckstats collection %s", collection_id)

    return all_cards
