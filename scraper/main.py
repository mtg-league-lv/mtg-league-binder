import os
import re
import logging
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright
from supabase import create_client, Client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def extract_binder_id(url: str) -> str:
    match = re.search(r"/binders/([^/?#]+)", url)
    if not match:
        raise ValueError(f"Cannot extract binder ID from URL: {url}")
    return match.group(1)


def parse_cards(api_response: dict) -> list[dict]:
    """Parse cards from Moxfield API JSON response (boards.mainboard.cards structure)."""
    try:
        cards_map = api_response["boards"]["mainboard"]["cards"]
    except (KeyError, TypeError):
        return []
    result = []
    for entry in cards_map.values():
        name = entry.get("card", {}).get("name", "")
        qty = entry.get("quantity", 1)
        if name:
            result.append({"card_name": name.lower().strip(), "quantity": qty})
    return result


def scrape_binder(url: str) -> list[dict]:
    """Scrape a Moxfield binder page using Playwright and intercept the API response."""
    cards: list[dict] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        # Intercept the Moxfield API response as the page loads
        api_data: dict = {}

        def handle_response(response):
            if "/api/" in response.url or "moxfield.com/v" in response.url or "api2.moxfield" in response.url:
                binder_id = extract_binder_id(url)
                if binder_id in response.url and response.status == 200:
                    try:
                        api_data.update(response.json())
                        log.info("Intercepted API response from %s", response.url)
                    except Exception:
                        pass

        page.on("response", handle_response)

        log.info("Navigating to %s", url)
        page.goto(url, wait_until="networkidle", timeout=60000)

        # If we got API data via interception, use it
        if api_data:
            cards = parse_cards(api_data)
            log.info("Parsed %s cards from intercepted API response", len(cards))
        else:
            # Fall back to DOM scraping
            log.info("No API response intercepted, falling back to DOM scraping")
            cards = _scrape_dom(page)

        context.close()
        browser.close()

    return cards


def _scrape_dom(page) -> list[dict]:
    """Extract card names and quantities directly from the rendered DOM."""
    cards = []

    # Wait for card content to appear
    try:
        page.wait_for_selector("[class*='card']", timeout=15000)
    except Exception:
        log.warning("Timed out waiting for card elements")

    # Try multiple selector strategies Moxfield uses
    selectors = [
        ("[data-testid='cardQuantity']", "[data-testid='cardName']"),
    ]

    # Generic approach: find quantity + name pairs via JS evaluation
    results = page.evaluate("""
        () => {
            const cards = [];
            // Try to find card rows with quantity and name
            document.querySelectorAll('[class*="deckview"], [class*="card-row"], [class*="cardRow"]').forEach(row => {
                const nameEl = row.querySelector('[class*="name"], [class*="Name"]');
                const qtyEl = row.querySelector('[class*="qty"], [class*="Qty"], [class*="quantity"], [class*="Quantity"]');
                if (nameEl && nameEl.textContent.trim()) {
                    cards.push({
                        name: nameEl.textContent.trim(),
                        qty: qtyEl ? parseInt(qtyEl.textContent.trim()) || 1 : 1
                    });
                }
            });
            return cards;
        }
    """)

    for r in results:
        name = r.get("name", "").strip()
        qty = r.get("qty", 1)
        if name and not name.isdigit():
            cards.append({"card_name": name.lower(), "quantity": qty})

    if cards:
        log.info("DOM scraping found %s cards", len(cards))
    else:
        log.warning("DOM scraping found 0 cards — page may not have loaded correctly")

    return cards


def sync_binder(client: Client, binder_id: str, url: str) -> None:
    log.info("Scraping binder %s (%s)", binder_id, url)
    try:
        cards = scrape_binder(url)
    except Exception as exc:
        log.warning("Skipping binder %s: %s", binder_id, exc)
        return

    # Always update last_scraped_at so operators can see this binder was attempted
    client.from_("binders").update({"last_scraped_at": datetime.now(timezone.utc).isoformat()}).eq("id", binder_id).execute()

    if not cards:
        log.warning("Binder %s returned 0 cards — skipping card update to preserve existing data", binder_id)
        return

    # Full replace: delete then insert
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
