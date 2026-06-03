# Multi-Platform Scraper Design

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extend the scraper to support both Moxfield and Deckstats.net binder URLs using a plugin pattern, keeping `main.py`'s public interface unchanged.

**Architecture:** Platform-specific scrape logic lives in isolated modules under `scraper/scrapers/`. A URL-based dispatcher selects the right scraper at runtime. Shared browser launch config lives in `base.py` to avoid duplication.

**Tech Stack:** Python, patchright (headless Chromium), supabase-py

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `scraper/scrapers/__init__.py` | Create | `get_scraper(url)` — URL-based dispatch |
| `scraper/scrapers/base.py` | Create | `launch_browser()` — shared patchright setup |
| `scraper/scrapers/moxfield.py` | Create | `scrape(url) -> list[dict]` — Moxfield logic (moved from `main.py`) |
| `scraper/scrapers/deckstats.py` | Create | `scrape(url) -> list[dict]` — Deckstats logic (new) |
| `scraper/main.py` | Modify | Replace `scrape_binder(url)` call with `get_scraper(url)(url)` |
| `scraper/test_integration.py` | Modify | Add deckstats integration test |

---

## Platform Detection

`scrapers/__init__.py` maps URL host to scraper module:

```python
def get_scraper(url: str):
    if "moxfield.com" in url:
        from .moxfield import scrape
    elif "deckstats.net" in url:
        from .deckstats import scrape
    else:
        raise ValueError(f"Unsupported binder URL: {url}")
    return scrape
```

---

## Shared Browser Base (`base.py`)

Extracts the current patchright launch config from `main.py` into a reusable helper:

```python
from patchright.sync_api import PlaywrightContextManager, Browser, BrowserContext, Page
from contextlib import contextmanager

@contextmanager
def launch_browser(playwright):
    browser = playwright.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-dev-shm-usage"],
    )
    context = browser.new_context(
        user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        locale="en-US",
        timezone_id="America/New_York",
    )
    try:
        yield browser, context
    finally:
        context.close()
        browser.close()
```

---

## Moxfield Scraper (`moxfield.py`)

Current `scrape_binder`, `parse_cards`, and `extract_binder_id` functions moved verbatim from `main.py`, with the public entry point renamed to `scrape(url) -> list[dict]`. Uses `base.launch_browser()`. Intercepts `trade-binders` XHR responses and paginates via `totalPages`.

---

## Deckstats Scraper (`deckstats.py`)

New `scrape(url) -> list[dict]` implementation:

- Extract collection ID from URL: `https://deckstats.net/collection/<id>`
- Launch browser via `base.launch_browser()`
- Navigate to the collection page
- Intercept XHR/fetch responses containing card data (URL pattern to be confirmed during implementation by logging all network responses)
- If no API endpoint is found, fall back to DOM parsing of the card table
- Paginate if the collection spans multiple pages
- Return cards in the same shape: `[{"card_name": str (lowercase), "quantity": int}]`

---

## `main.py` Change

Replace the direct `scrape_binder` import/call in `sync_binder`:

```python
# Before
from scraper import scrape_binder
cards = scrape_binder(url)

# After
from scrapers import get_scraper
cards = get_scraper(url)(url)
```

The `sync_binder` and `main` functions are otherwise unchanged.

---

## Bot URL Validation

The Telegram (and future Discord) bot validates registered URLs with a regex. Extend it to accept both platforms:

```typescript
// Before
const MOXFIELD_BINDER_RE = /^https:\/\/moxfield\.com\/binders\/[A-Za-z0-9_-]+/;

// After
const BINDER_URL_RE = /^https:\/\/(moxfield\.com\/binders\/[A-Za-z0-9_-]+|deckstats\.net\/collection\/\d+)/;
```

---

## Testing

### Existing tests
- `test_integration.py` Moxfield tests remain unchanged.

### New integration test
```python
DECKSTATS_URL = "https://deckstats.net/collection/45416"

def test_deckstats_binder_returns_cards():
    cards = scrape(DECKSTATS_URL)
    assert len(cards) > 0

def test_deckstats_card_structure():
    cards = scrape(DECKSTATS_URL)
    for card in cards:
        assert "card_name" in card
        assert "quantity" in card
        assert card["card_name"] == card["card_name"].lower()
        assert isinstance(card["quantity"], int)
```

### Unit test
```python
def test_get_scraper_moxfield():
    from scrapers import get_scraper
    from scrapers.moxfield import scrape
    assert get_scraper("https://moxfield.com/binders/ABC") is scrape

def test_get_scraper_deckstats():
    from scrapers import get_scraper
    from scrapers.deckstats import scrape
    assert get_scraper("https://deckstats.net/collection/123") is scrape

def test_get_scraper_unknown_raises():
    from scrapers import get_scraper
    with pytest.raises(ValueError):
        get_scraper("https://unknown.com/binder/1")
```
