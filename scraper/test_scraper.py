# scraper/test_scraper.py
import pytest
from unittest.mock import patch, MagicMock, call
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


def test_parse_cards_trade_binder_response():
    """trade-binders /v1/search response format."""
    api_response = {
        "data": [
            {"quantity": 2, "card": {"name": "Black Lotus"}},
            {"quantity": 1, "card": {"name": "Mox Pearl"}},
        ]
    }
    cards = parse_cards(api_response)
    assert sorted(cards, key=lambda c: c["card_name"]) == [
        {"card_name": "black lotus", "quantity": 2},
        {"card_name": "mox pearl", "quantity": 1},
    ]


def test_parse_cards_legacy_boards_response():
    """Legacy /v2/binders response format."""
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


def test_parse_cards_empty_data():
    assert parse_cards({"data": []}) == []


def test_parse_cards_missing_keys():
    assert parse_cards({}) == []


def _make_mock_response(url: str, status: int, json_data: dict):
    resp = MagicMock()
    resp.url = url
    resp.status = status
    resp.json.return_value = json_data
    return resp


def test_scrape_binder_intercepts_trade_binder_api():
    """scrape_binder should capture cards from the intercepted trade-binders response."""
    captured_handler = {}

    mock_page = MagicMock()

    def capture_on(event, handler):
        captured_handler[event] = handler

    mock_page.on.side_effect = capture_on
    mock_page.goto = MagicMock()

    mock_context = MagicMock()
    mock_context.new_page.return_value = mock_page

    mock_browser = MagicMock()
    mock_browser.new_context.return_value = mock_context

    mock_pw = MagicMock()
    mock_pw.__enter__ = MagicMock(return_value=mock_pw)
    mock_pw.__exit__ = MagicMock(return_value=False)
    mock_pw.chromium.launch.return_value = mock_browser

    with patch("main.sync_playwright", return_value=mock_pw):
        from main import scrape_binder

        def run_scrape():
            # Simulate the page load firing the intercepted API response
            original_goto = mock_page.goto.side_effect

            def goto_and_fire(*args, **kwargs):
                handler = captured_handler.get("response")
                if handler:
                    mock_resp = _make_mock_response(
                        "https://api2.moxfield.com/v1/trade-binders/ABC123/search?q=+",
                        200,
                        {
                            "data": [
                                {"quantity": 3, "card": {"name": "Lightning Bolt"}},
                                {"quantity": 1, "card": {"name": "Black Lotus"}},
                            ]
                        },
                    )
                    handler(mock_resp)

            mock_page.goto.side_effect = goto_and_fire
            return scrape_binder("https://moxfield.com/binders/ABC123")

        result = run_scrape()

    assert {"card_name": "lightning bolt", "quantity": 3} in result
    assert {"card_name": "black lotus", "quantity": 1} in result
