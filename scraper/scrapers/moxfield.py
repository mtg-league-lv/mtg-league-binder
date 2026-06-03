# scraper/scrapers/moxfield.py
import re
import logging
from patchright.sync_api import sync_playwright
from .base import launch_browser

log = logging.getLogger(__name__)


def extract_binder_id(url: str) -> str:
    match = re.search(r"/binders/([^/?#]+)", url)
    if not match:
        raise ValueError(f"Cannot extract binder ID from URL: {url}")
    return match.group(1)


def parse_cards(api_response: dict) -> list[dict]:
    """Parse cards from Moxfield trade-binder search API response.

    The /v1/trade-binders/{id}/search endpoint returns:
      {"data": [{"quantity": N, "card": {"name": "..."}}, ...]}
    """
    result = []

    # /v1/trade-binders/{id}/search response shape
    items = api_response.get("data", [])
    if isinstance(items, list) and items:
        for entry in items:
            if not isinstance(entry, dict):
                continue
            name = entry.get("card", {}).get("name", "")
            qty = entry.get("quantity", 1)
            if name:
                result.append({"card_name": name.lower().strip(), "quantity": qty})
        if result:
            return result

    # Legacy /v2/binders response shape (boards.mainboard.cards)
    try:
        cards_map = api_response["boards"]["mainboard"]["cards"]
        for entry in cards_map.values():
            name = entry.get("card", {}).get("name", "")
            qty = entry.get("quantity", 1)
            if name:
                result.append({"card_name": name.lower().strip(), "quantity": qty})
    except (KeyError, TypeError):
        pass

    return result


def scrape(url: str) -> list[dict]:
    """Load a Moxfield binder page and intercept the trade-binders API response."""
    binder_id = extract_binder_id(url)
    all_cards: list[dict] = []

    with sync_playwright() as p:
        with launch_browser(p) as (browser, context):
            page = context.new_page()
            total_pages = 1  # updated when first API response arrives

            def handle_response(response):
                nonlocal total_pages
                if (
                    "trade-binders" in response.url
                    and binder_id in response.url
                    and response.status == 200
                ):
                    try:
                        data = response.json()
                        total_pages = data.get("totalPages", 1)
                        cards = parse_cards(data)
                        if cards:
                            all_cards.extend(cards)
                            log.info(
                                "Intercepted %s cards (page %s/%s) from %s",
                                len(cards),
                                data.get("pageNumber", "?"),
                                total_pages,
                                response.url[:80],
                            )
                        else:
                            log.warning(
                                "Intercepted response but parsed 0 cards. Keys: %s",
                                list(data.keys()) if isinstance(data, dict) else type(data),
                            )
                    except Exception as exc:
                        log.warning("Failed to parse intercepted response: %s", exc)

            page.on("response", handle_response)

            log.info("Navigating to %s", url)
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(8000)

            for page_num in range(2, total_pages + 1):
                next_btn = page.locator(
                    "div.d-flex.flex-wrap.align-items-center.row-gap-3.mt-3 "
                    "button.btn.ms-2.btn-secondary"
                ).last
                log.info("Clicking to page %s/%s", page_num, total_pages)
                next_btn.click()
                page.wait_for_timeout(3000)

    if all_cards:
        log.info("Total cards scraped: %s", len(all_cards))
    else:
        log.warning("No cards found for binder %s", binder_id)

    return all_cards
