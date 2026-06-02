import os
import re
import logging
from datetime import datetime, timezone
from patchright.sync_api import sync_playwright
from supabase import create_client, Client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
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


def scrape_binder(url: str) -> list[dict]:
    """Load a Moxfield binder page in a headless browser and intercept the API response."""
    binder_id = extract_binder_id(url)
    all_cards: list[dict] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="en-US",
            timezone_id="America/New_York",
        )
        page = context.new_page()

        def handle_response(response):
            if "moxfield" in response.url and response.status in (200, 403):
                log.info("RESPONSE %s %s", response.status, response.url[:120])
            if (
                "trade-binders" in response.url
                and binder_id in response.url
                and response.status == 200
            ):
                try:
                    data = response.json()
                    cards = parse_cards(data)
                    if cards:
                        all_cards.extend(cards)
                        log.info("Intercepted %s cards from %s", len(cards), response.url[:80])
                    else:
                        log.warning("Intercepted response but parsed 0 cards. Keys: %s", list(data.keys()) if isinstance(data, dict) else type(data))
                except Exception as exc:
                    log.warning("Failed to parse intercepted response: %s", exc)

        page.on("response", handle_response)

        log.info("Navigating to %s", url)
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(8000)

        context.close()
        browser.close()

    if all_cards:
        log.info("Total cards scraped: %s", len(all_cards))
    else:
        log.warning("No cards found for binder %s", binder_id)

    return all_cards


def sync_binder(client: Client, binder_id: str, url: str) -> None:
    log.info("Scraping binder %s (%s)", binder_id, url)
    try:
        cards = scrape_binder(url)
    except Exception as exc:
        log.warning("Skipping binder %s: %s", binder_id, exc)
        return

    client.from_("binders").update(
        {"last_scraped_at": datetime.now(timezone.utc).isoformat()}
    ).eq("id", binder_id).execute()

    if not cards:
        log.warning("Binder %s returned 0 cards — skipping card update to preserve existing data", binder_id)
        return

    client.from_("binder_cards").delete().eq("binder_id", binder_id).execute()
    rows = [{"binder_id": binder_id, **c} for c in cards]
    client.from_("binder_cards").insert(rows).execute()
    log.info("  Done: %s cards upserted", len(cards))


def main() -> None:
    supabase_url = os.environ["SUPABASE_URL"]
    supabase_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    client = create_client(supabase_url, supabase_key)

    response = client.from_("binders").select("id, url").execute()
    binders = response.data or []
    log.info("Found %s binders to scrape", len(binders))

    for binder in binders:
        sync_binder(client, binder["id"], binder["url"])

    log.info("Scrape complete")


if __name__ == "__main__":
    main()
