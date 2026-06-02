# scraper/test_scraper.py
import pytest
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
