# scraper/test_scraper.py
import pytest
from unittest.mock import patch, MagicMock
from main import extract_binder_id, parse_cards


def test_extract_binder_id_standard_url():
    url = "https://moxfield.com/binders/RUJ8XbZwAk2M1AQw640zQQ"
    assert extract_binder_id(url) == "RUJ8XbZwAk2M1AQw640zQQ"


def test_extract_binder_id_trailing_slash():
    url = "https://moxfield.com/binders/ABC123/"
    assert extract_binder_id(url) == "ABC123"


def test_extract_binder_id_invalid():
    with pytest.raises(ValueError, match="Cannot extract binder ID"):
        extract_binder_id("https://moxfield.com/decks/something")


def test_parse_cards_standard_response():
    api_response = {
        "boards": {
            "mainboard": {
                "cards": {
                    "card1": {"quantity": 2, "card": {"name": "Black Lotus"}},
                    "card2": {"quantity": 1, "card": {"name": "Mox Pearl"}},
                }
            }
        }
    }
    cards = parse_cards(api_response)
    assert sorted(cards, key=lambda c: c["card_name"]) == [
        {"card_name": "black lotus", "quantity": 2},
        {"card_name": "mox pearl", "quantity": 1},
    ]


def test_parse_cards_empty_binder():
    api_response = {"boards": {"mainboard": {"cards": {}}}}
    assert parse_cards(api_response) == []


def test_parse_cards_missing_boards():
    assert parse_cards({}) == []


def test_scrape_binder_uses_playwright():
    """Verify scrape_binder launches Playwright and returns parsed cards."""
    mock_page = MagicMock()
    mock_page.evaluate.return_value = [
        {"name": "Lightning Bolt", "qty": 3},
        {"name": "Black Lotus", "qty": 1},
    ]
    mock_page.goto = MagicMock()
    mock_page.wait_for_selector = MagicMock()

    mock_context = MagicMock()
    mock_context.new_page.return_value = mock_page

    mock_browser = MagicMock()
    mock_browser.new_context.return_value = mock_context

    mock_chromium = MagicMock()
    mock_chromium.launch.return_value = mock_browser

    mock_playwright = MagicMock()
    mock_playwright.__enter__ = MagicMock(return_value=mock_playwright)
    mock_playwright.__exit__ = MagicMock(return_value=False)
    mock_playwright.chromium = mock_chromium

    with patch("main.sync_playwright", return_value=mock_playwright):
        from main import scrape_binder
        result = scrape_binder("https://moxfield.com/binders/ABC123")

    assert {"card_name": "lightning bolt", "quantity": 3} in result
    assert {"card_name": "black lotus", "quantity": 1} in result
