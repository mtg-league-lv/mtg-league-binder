"""
Integration tests — require live internet access.
Run with: pytest scraper/test_integration.py -v
"""
import pytest
from scrapers.moxfield import scrape as scrape_binder, extract_binder_id


BINDER_URL = "https://moxfield.com/binders/FI4YNpJD40aTDf2_8vUExg"


def test_real_binder_returns_multiple_cards():
    cards = scrape_binder(BINDER_URL)
    assert len(cards) > 1, f"Expected more than 1 card, got {len(cards)}"


def test_real_binder_card_structure():
    cards = scrape_binder(BINDER_URL)
    assert len(cards) > 0
    for card in cards:
        assert "card_name" in card, f"Missing card_name in {card}"
        assert "quantity" in card, f"Missing quantity in {card}"
        assert isinstance(card["card_name"], str)
        assert card["card_name"] == card["card_name"].lower(), "card_name should be lowercase"
        assert isinstance(card["quantity"], int)
        assert card["quantity"] >= 1


def test_real_binder_has_more_than_4_pages():
    """Binder should span more than 4 pages (50 cards/page) resulting in 200+ cards."""
    cards = scrape_binder(BINDER_URL)
    assert len(cards) > 200, (
        f"Expected more than 200 cards (4+ pages at 50 cards/page), got {len(cards)}"
    )


from scrapers.deckstats import scrape as scrape_deckstats

DECKSTATS_URL = "https://deckstats.net/collection/45416"


def test_deckstats_binder_returns_cards():
    cards = scrape_deckstats(DECKSTATS_URL)
    assert len(cards) > 0, f"Expected at least 1 card from deckstats binder, got 0"


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
