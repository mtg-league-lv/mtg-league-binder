# scraper/main.py
import os
import logging
from datetime import datetime, timezone
from supabase import create_client, Client
from scrapers import get_scraper

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def sync_binder(client: Client, binder_id: str, url: str) -> None:
    log.info("Scraping binder %s (%s)", binder_id, url)
    try:
        scrape = get_scraper(url)
        cards = scrape(url)
    except ValueError as exc:
        log.warning("Skipping binder %s: %s", binder_id, exc)
        return
    except Exception as exc:
        log.warning("Skipping binder %s: %s", binder_id, exc)
        return

    client.from_("binders").update(
        {"last_scraped_at": datetime.now(timezone.utc).isoformat()}
    ).eq("id", binder_id).execute()

    if not cards:
        log.warning(
            "Binder %s returned 0 cards — skipping card update to preserve existing data",
            binder_id,
        )
        return

    # Deduplicate by card_name, summing quantities for multiple printings
    merged: dict[str, int] = {}
    for c in cards:
        merged[c["card_name"]] = merged.get(c["card_name"], 0) + c["quantity"]

    client.from_("binder_cards").delete().eq("binder_id", binder_id).execute()
    rows = [
        {"binder_id": binder_id, "card_name": name, "quantity": qty}
        for name, qty in merged.items()
    ]
    client.from_("binder_cards").insert(rows).execute()
    log.info("  Done: %s unique cards upserted", len(rows))


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
