# Multi-Platform Scraper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the scraper into a plugin architecture supporting both Moxfield and Deckstats.net binders, without changing the public interface of `main.py`.

**Architecture:** Platform-specific logic moves into `scraper/scrapers/moxfield.py` and `scraper/scrapers/deckstats.py`. A `get_scraper(url)` dispatcher in `scraper/scrapers/__init__.py` selects the right module. `scraper/scrapers/base.py` holds the shared patchright browser launch helper. `main.py` replaces its direct `scrape_binder` call with `get_scraper(url)(url)`.

**Tech Stack:** Python 3.11+, patchright (headless Chromium), pytest, supabase-py

---

## File Map

| File | Change |
|------|--------|
| `scraper/scrapers/__init__.py` | **Create** — `get_scraper(url)` dispatcher |
| `scraper/scrapers/base.py` | **Create** — `launch_browser(playwright)` context manager |
| `scraper/scrapers/moxfield.py` | **Create** — `scrape(url)`, `parse_cards()`, `extract_binder_id()` (moved from `main.py`) |
| `scraper/scrapers/deckstats.py` | **Create** — `scrape(url)` for Deckstats collections |
| `scraper/main.py` | **Modify** — remove old scraping functions, call `get_scraper(url)(url)` |
| `scraper/test_scraper.py` | **Modify** — update imports to `scrapers.moxfield` |
| `scraper/test_integration.py` | **Modify** — update imports; add Deckstats integration tests |
| `scraper/test_dispatcher.py` | **Create** — unit tests for `get_scraper()` |
| `supabase/functions/telegram-bot/index.ts` | **Modify** — extend URL regex to accept deckstats URLs |

---

### Task 1: Create `scrapers/` package with dispatcher

**Files:**
- Create: `scraper/scrapers/__init__.py`
- Create: `scraper/test_dispatcher.py`

- [ ] **Step 1: Write the failing tests**

Create `scraper/test_dispatcher.py`:

```python
# scraper/test_dispatcher.py
import pytest
from scrapers import get_scraper


def test_get_scraper_moxfield():
    from scrapers.moxfield import scrape
    assert get_scraper("https://moxfield.com/binders/ABC123") is scrape


def test_get_scraper_deckstats():
    from scrapers.deckstats import scrape
    assert get_scraper("https://deckstats.net/collection/45416") is scrape


def test_get_scraper_unknown_raises():
    with pytest.raises(ValueError, match="Unsupported binder URL"):
        get_scraper("https://unknown-site.com/binder/1")


def test_get_scraper_moxfield_with_trailing_path():
    from scrapers.moxfield import scrape
    assert get_scraper("https://moxfield.com/binders/ABC123?tab=cards") is scrape
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd scraper
python -m pytest test_dispatcher.py -v
```

Expected: `ModuleNotFoundError: No module named 'scrapers'`

- [ ] **Step 3: Create the `scrapers` package directory and stub files**

Create `scraper/scrapers/__init__.py`:

```python
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
```

Create stub `scraper/scrapers/moxfield.py` (just enough to satisfy the import):

```python
def scrape(url: str) -> list[dict]:
    raise NotImplementedError("moxfield scraper not yet implemented")
```

Create stub `scraper/scrapers/deckstats.py`:

```python
def scrape(url: str) -> list[dict]:
    raise NotImplementedError("deckstats scraper not yet implemented")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd scraper
python -m pytest test_dispatcher.py -v
```

Expected: all 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add scraper/scrapers/__init__.py scraper/scrapers/moxfield.py scraper/scrapers/deckstats.py scraper/test_dispatcher.py
git commit -m "feat: add scrapers package with get_scraper() dispatcher"
```

---

### Task 2: Create shared browser base helper

**Files:**
- Create: `scraper/scrapers/base.py`

No dedicated unit test — this is a thin wrapper around patchright; tested indirectly via the moxfield tests in Task 3.

- [ ] **Step 1: Create `scraper/scrapers/base.py`**

```python
# scraper/scrapers/base.py
from contextlib import contextmanager
from patchright.sync_api import Browser, BrowserContext


@contextmanager
def launch_browser(playwright):
    """Launch a patchright Chromium browser with anti-detection settings.

    Usage:
        with sync_playwright() as p:
            with launch_browser(p) as (browser, context):
                page = context.new_page()
                ...
    """
    browser: Browser = playwright.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-dev-shm-usage"],
    )
    context: BrowserContext = browser.new_context(
        user_agent=(
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        locale="en-US",
        timezone_id="America/New_York",
    )
    try:
        yield browser, context
    finally:
        context.close()
        browser.close()
```

- [ ] **Step 2: Commit**

```bash
git add scraper/scrapers/base.py
git commit -m "feat: add shared browser launch helper in scrapers/base.py"
```

---

### Task 3: Move Moxfield logic into `scrapers/moxfield.py`

**Files:**
- Modify: `scraper/scrapers/moxfield.py` (replace stub)
- Modify: `scraper/test_scraper.py` (update imports)
- Modify: `scraper/test_integration.py` (update import)

- [ ] **Step 1: Update `test_scraper.py` imports**

Open `scraper/test_scraper.py`. Change the import at the top from:

```python
from main import extract_binder_id, parse_cards
```

to:

```python
from scrapers.moxfield import extract_binder_id, parse_cards
```

Also update the mock patch target in `test_scrape_binder_intercepts_trade_binder_api` from:

```python
with patch("main.sync_playwright", return_value=mock_pw):
    from main import scrape_binder
```

to:

```python
with patch("scrapers.moxfield.sync_playwright", return_value=mock_pw):
    from scrapers.moxfield import scrape as scrape_binder
```

- [ ] **Step 2: Run existing tests to confirm they now fail (imports broken)**

```bash
cd scraper
python -m pytest test_scraper.py -v
```

Expected: `ImportError: cannot import name 'extract_binder_id' from 'scrapers.moxfield'`

- [ ] **Step 3: Replace the moxfield stub with the full implementation**

Replace `scraper/scrapers/moxfield.py` entirely:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd scraper
python -m pytest test_scraper.py -v
```

Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add scraper/scrapers/moxfield.py scraper/test_scraper.py
git commit -m "feat: move moxfield scraping logic to scrapers/moxfield.py"
```

---

### Task 4: Update `main.py` to use the dispatcher

**Files:**
- Modify: `scraper/main.py`
- Modify: `scraper/test_integration.py`

- [ ] **Step 1: Update `test_integration.py` imports**

Open `scraper/test_integration.py`. Change:

```python
from main import scrape_binder, extract_binder_id
```

to:

```python
from scrapers.moxfield import scrape as scrape_binder, extract_binder_id
```

- [ ] **Step 2: Run integration tests to confirm they still pass**

```bash
cd scraper
python -m pytest test_integration.py -v
```

Expected: all 3 tests PASS (live network required)

- [ ] **Step 3: Update `main.py`**

Replace `scraper/main.py` entirely:

```python
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
```

- [ ] **Step 4: Run all unit tests**

```bash
cd scraper
python -m pytest test_scraper.py test_dispatcher.py -v
```

Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add scraper/main.py scraper/test_integration.py
git commit -m "refactor: main.py uses get_scraper() dispatcher; remove inline scraping functions"
```

---

### Task 5: Discover Deckstats network API

This task produces information needed for Task 6. Run a spy script to capture the real API shape from `https://deckstats.net/collection/45416` before writing the scraper.

**Files:**
- Create (temporary): `scraper/scrapers/deckstats_spy.py`

- [ ] **Step 1: Create the spy script**

Create `scraper/scrapers/deckstats_spy.py`:

```python
"""
One-off discovery script — run this once to log all network responses from
deckstats.net/collection/45416, then delete the file.

Run: cd scraper && python scrapers/deckstats_spy.py
Output saved to: scraper/deckstats_responses.txt
"""
import json
from patchright.sync_api import sync_playwright
from base import launch_browser  # run from scraper/ directory

URL = "https://deckstats.net/collection/45416"
OUTPUT = "deckstats_responses.txt"

with sync_playwright() as p:
    with launch_browser(p) as (browser, context):
        page = context.new_page()
        responses = []

        def handle(response):
            if response.status == 200 and (
                "json" in response.headers.get("content-type", "")
                or "deckstats" in response.url
            ):
                try:
                    body = response.json()
                    responses.append({"url": response.url, "body": body})
                except Exception:
                    pass

        page.on("response", handle)
        page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(8000)

        with open(OUTPUT, "w") as f:
            json.dump(responses, f, indent=2)

        print(f"Saved {len(responses)} responses to {OUTPUT}")
        print("First 5 response URLs:")
        for r in responses[:5]:
            print(" ", r["url"])
```

- [ ] **Step 2: Run the spy script**

```bash
cd scraper
python scrapers/deckstats_spy.py
```

Expected: `deckstats_responses.txt` created with captured JSON responses.

- [ ] **Step 3: Inspect the output to find the card data endpoint**

```bash
cd scraper
python -c "
import json
data = json.load(open('deckstats_responses.txt'))
for r in data:
    body = r['body']
    # Look for responses that contain card-like data
    body_str = json.dumps(body)
    if 'name' in body_str and ('quantity' in body_str or 'amount' in body_str or 'count' in body_str):
        print('CANDIDATE:', r['url'])
        print(json.dumps(body)[:500])
        print('---')
"
```

Note the URL pattern and JSON shape of the candidate response. You will need this for Task 6.

- [ ] **Step 4: Delete the spy script and output**

```bash
rm scraper/scrapers/deckstats_spy.py scraper/deckstats_responses.txt
```

---

### Task 6: Implement Deckstats scraper

**Files:**
- Modify: `scraper/scrapers/deckstats.py` (replace stub)

**Context:** The deckstats collection URL is `https://deckstats.net/collection/{owner_id}`. From the spy output in Task 5, identify the API endpoint URL pattern and JSON response shape. The implementation below covers the two most likely formats found on deckstats — adjust `parse_deckstats_response()` to match what the spy actually found.

- [ ] **Step 1: Write the failing integration test first**

Add to `scraper/test_integration.py`:

```python
from scrapers.deckstats import scrape as scrape_deckstats

DECKSTATS_URL = "https://deckstats.net/collection/45416"


def test_deckstats_binder_returns_cards():
    cards = scrape_deckstats(DECKSTATS_URL)
    assert len(cards) > 0, "Expected at least 1 card from deckstats binder"


def test_deckstats_card_structure():
    cards = scrape_deckstats(DECKSTATS_URL)
    assert len(cards) > 0
    for card in cards:
        assert "card_name" in card, f"Missing card_name in {card}"
        assert "quantity" in card, f"Missing quantity in {card}"
        assert isinstance(card["card_name"], str)
        assert card["card_name"] == card["card_name"].lower(), "card_name must be lowercase"
        assert isinstance(card["quantity"], int)
        assert card["quantity"] >= 1
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
cd scraper
python -m pytest test_integration.py::test_deckstats_binder_returns_cards -v
```

Expected: FAIL with `NotImplementedError: deckstats scraper not yet implemented`

- [ ] **Step 3: Implement `scraper/scrapers/deckstats.py`**

Replace `scraper/scrapers/deckstats.py` with the full implementation. Use the API URL pattern and JSON shape discovered in Task 5. The structure below uses `parse_deckstats_response()` which you must fill in based on the actual response shape:

```python
# scraper/scrapers/deckstats.py
import re
import logging
from patchright.sync_api import sync_playwright
from .base import launch_browser

log = logging.getLogger(__name__)


def extract_collection_id(url: str) -> str:
    match = re.search(r"/collection/(\d+)", url)
    if not match:
        raise ValueError(f"Cannot extract collection ID from URL: {url}")
    return match.group(1)


def parse_deckstats_response(api_response: dict) -> list[dict]:
    """Parse cards from a Deckstats API response.

    Adjust the field names below to match what the spy script found in Task 5.

    Common Deckstats shapes:
      Shape A: {"cards": [{"name": "...", "amount": N}, ...]}
      Shape B: {"data": {"cards": [{"name": "...", "qty": N}, ...]}}
      Shape C: [{"name": "...", "quantity": N}, ...]  (bare list)
    """
    result = []

    # Shape A: top-level "cards" list
    cards_list = api_response.get("cards")
    if isinstance(cards_list, list) and cards_list:
        for entry in cards_list:
            if not isinstance(entry, dict):
                continue
            name = entry.get("name") or entry.get("card_name", "")
            qty = entry.get("amount") or entry.get("qty") or entry.get("quantity") or 1
            if name:
                result.append({"card_name": name.lower().strip(), "quantity": int(qty)})
        if result:
            return result

    # Shape B: nested data.cards
    try:
        cards_list = api_response["data"]["cards"]
        for entry in cards_list:
            name = entry.get("name") or entry.get("card_name", "")
            qty = entry.get("amount") or entry.get("qty") or entry.get("quantity") or 1
            if name:
                result.append({"card_name": name.lower().strip(), "quantity": int(qty)})
        if result:
            return result
    except (KeyError, TypeError):
        pass

    # Shape C: bare list at root
    if isinstance(api_response, list):
        for entry in api_response:
            if not isinstance(entry, dict):
                continue
            name = entry.get("name") or entry.get("card_name", "")
            qty = entry.get("amount") or entry.get("qty") or entry.get("quantity") or 1
            if name:
                result.append({"card_name": name.lower().strip(), "quantity": int(qty)})

    return result


def scrape(url: str) -> list[dict]:
    """Load a Deckstats collection page and intercept the card data API response."""
    collection_id = extract_collection_id(url)
    all_cards: list[dict] = []

    with sync_playwright() as p:
        with launch_browser(p) as (browser, context):
            page = context.new_page()

            def handle_response(response):
                if (
                    response.status == 200
                    and "deckstats.net" in response.url
                    and collection_id in response.url
                    and "json" in response.headers.get("content-type", "")
                ):
                    try:
                        data = response.json()
                        cards = parse_deckstats_response(data)
                        if cards:
                            all_cards.extend(cards)
                            log.info(
                                "Intercepted %s cards from %s",
                                len(cards),
                                response.url[:80],
                            )
                        else:
                            log.warning(
                                "Deckstats response at %s parsed 0 cards. Keys: %s",
                                response.url[:80],
                                list(data.keys()) if isinstance(data, dict) else type(data),
                            )
                    except Exception as exc:
                        log.warning("Failed to parse deckstats response: %s", exc)

            page.on("response", handle_response)

            log.info("Navigating to %s", url)
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(8000)

    if all_cards:
        log.info("Total cards scraped from deckstats: %s", len(all_cards))
    else:
        log.warning("No cards found for deckstats collection %s", collection_id)

    return all_cards
```

- [ ] **Step 4: Run the integration tests**

```bash
cd scraper
python -m pytest test_integration.py::test_deckstats_binder_returns_cards test_integration.py::test_deckstats_card_structure -v
```

Expected: both PASS.

If 0 cards are returned, the API shape doesn't match any of the three patterns in `parse_deckstats_response`. Debug by re-running the spy script from Task 5 and inspecting the response body, then update `parse_deckstats_response` accordingly.

- [ ] **Step 5: Run full test suite**

```bash
cd scraper
python -m pytest test_scraper.py test_dispatcher.py test_integration.py -v
```

Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
git add scraper/scrapers/deckstats.py scraper/test_integration.py
git commit -m "feat: add deckstats scraper with network interception"
```

---

### Task 7: Extend Telegram bot URL validation

**Files:**
- Modify: `supabase/functions/telegram-bot/index.ts`

- [ ] **Step 1: Update the URL regex**

Open `supabase/functions/telegram-bot/index.ts`. Find:

```typescript
const MOXFIELD_BINDER_RE = /^https:\/\/moxfield\.com\/binders\/[A-Za-z0-9_-]+/;
```

Replace with:

```typescript
const BINDER_URL_RE =
  /^https:\/\/(moxfield\.com\/binders\/[A-Za-z0-9_-]+|deckstats\.net\/collection\/\d+)/;
```

Then update all three references to `MOXFIELD_BINDER_RE` in the file to `BINDER_URL_RE`:
- In `/register` command handler (line ~36)
- In `/removebinder` command handler (line ~74)

- [ ] **Step 2: Verify the file compiles (no TypeScript errors)**

```bash
deno check supabase/functions/telegram-bot/index.ts
```

Expected: no errors

- [ ] **Step 3: Run the Deno unit tests**

```bash
deno test supabase/functions/telegram-bot/index.test.ts --allow-env
```

Expected: all 5 tests PASS (none of them test the regex directly, but confirm nothing broke)

- [ ] **Step 4: Commit and deploy**

```bash
git add supabase/functions/telegram-bot/index.ts
git commit -m "feat: extend bot URL validation to accept deckstats.net collection URLs"
```

Then deploy the updated Edge Function:

```bash
supabase functions deploy telegram-bot
```

---

## Final Verification

- [ ] Run all scraper tests:
  ```bash
  cd scraper && python -m pytest test_scraper.py test_dispatcher.py test_integration.py -v
  ```
- [ ] Confirm `get_scraper("https://moxfield.com/binders/X")` returns the moxfield scraper
- [ ] Confirm `get_scraper("https://deckstats.net/collection/45416")` returns the deckstats scraper
- [ ] Confirm `get_scraper("https://other.com/foo")` raises `ValueError`
- [ ] Confirm Telegram `/register https://deckstats.net/collection/45416` is accepted by the bot
