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
