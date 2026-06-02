# scraper/test_scraper.py
import pytest
from unittest.mock import patch, MagicMock
from main import extract_binder_id, parse_cards, scrape_binder


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


def test_scrape_binder_passes_user_agent():
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "boards": {
            "mainboard": {
                "cards": {
                    "c1": {"quantity": 1, "card": {"name": "Lightning Bolt"}}
                }
            }
        }
    }
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.get", return_value=mock_response) as mock_get:
        result = scrape_binder("https://moxfield.com/binders/ABC123")

    call_kwargs = mock_get.call_args
    assert call_kwargs.kwargs["headers"]["User-Agent"] == "LeagueBinderBot/1.0"
    mock_response.raise_for_status.assert_called_once()
    assert result == [{"card_name": "lightning bolt", "quantity": 1}]


def test_scrape_binder_raises_on_http_error():
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = Exception("HTTP 404")

    with patch("httpx.get", return_value=mock_response):
        with pytest.raises(Exception, match="HTTP 404"):
            scrape_binder("https://moxfield.com/binders/ABC123")
