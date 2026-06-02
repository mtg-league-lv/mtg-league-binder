"""
Integration tests — require live internet access.
Run with: pytest scraper/test_integration.py -v
"""
import pytest
from main import scrape_binder, extract_binder_id


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
