import shutil
import tempfile
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


@contextmanager
def launch_real_browser(playwright):
    """Launch a real, non-headless Chrome with a throwaway profile.

    Deckstats sits behind CloudFlare, which returns 403 for XHRs issued by a
    headless browser. A genuine windowed Chrome session is served normally.
    CI runs this under xvfb, so there is no visible window there.

    Usage:
        with sync_playwright() as p:
            with launch_real_browser(p) as context:
                page = context.new_page()
                ...
    """
    profile_dir = tempfile.mkdtemp(prefix="scraper-profile-")
    context: BrowserContext = playwright.chromium.launch_persistent_context(
        user_data_dir=profile_dir,
        channel="chrome",
        headless=False,
        no_viewport=True,
        locale="en-US",
        timezone_id="America/New_York",
    )
    try:
        yield context
    finally:
        context.close()
        shutil.rmtree(profile_dir, ignore_errors=True)
