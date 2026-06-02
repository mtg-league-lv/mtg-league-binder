import os
import re
import logging
from datetime import datetime, timezone
import httpx
from supabase import create_client, Client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

MOXFIELD_API = "https://api2.moxfield.com/v2/binders/{}"


def extract_binder_id(url: str) -> str:
    match = re.search(r"/binders/([^/?#]+)", url)
    if not match:
        raise ValueError(f"Cannot extract binder ID from URL: {url}")
    return match.group(1)


def parse_cards(api_response: dict) -> list[dict]:
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
    binder_id = extract_binder_id(url)
    api_url = MOXFIELD_API.format(binder_id)
    headers = {"User-Agent": "LeagueBinderBot/1.0"}
    response = httpx.get(api_url, headers=headers, timeout=30, follow_redirects=True)
    response.raise_for_status()
    return parse_cards(response.json())


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
