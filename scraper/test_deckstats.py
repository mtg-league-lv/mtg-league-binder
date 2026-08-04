# scraper/test_deckstats.py
import pytest
from unittest.mock import patch, MagicMock

from scrapers.deckstats import (
    extract_collection_id,
    parse_deckstats_response,
    total_pages,
    api_url,
    binder_url,
    scrape,
)


def test_extract_collection_id_new_binders_url():
    assert extract_collection_id("https://deckstats.net/binders/58989") == "58989"


def test_extract_collection_id_legacy_collection_url():
    """Binders registered before the /binders/ rename must keep working."""
    assert extract_collection_id("https://deckstats.net/collection/45416") == "45416"


def test_extract_collection_id_trailing_path():
    assert extract_collection_id("https://deckstats.net/binders/58989/for-trade") == "58989"


def test_extract_collection_id_invalid():
    with pytest.raises(ValueError, match="Cannot extract collection ID"):
        extract_collection_id("https://deckstats.net/deck/12345")


def test_binder_url_uses_new_path():
    assert binder_url("58989") == "https://deckstats.net/binders/58989"


def test_api_url_shape():
    url = api_url("58989", 2, per_page=500)
    assert url.startswith("https://deckstats.net/api/collection/list?")
    assert "public_binder=58989" in url
    assert "page=2" in url
    assert "per_page=500" in url


def test_parse_deckstats_response_items():
    response = {
        "total": 2,
        "page": 1,
        "per_page": 500,
        "items": [
            {"name": "Black Lotus", "amount": 1, "set_abbr": "LEA"},
            {"name": "Lightning Bolt", "amount": 3, "set_abbr": "M10"},
        ],
    }
    assert parse_deckstats_response(response) == [
        {"card_name": "black lotus", "quantity": 1},
        {"card_name": "lightning bolt", "quantity": 3},
    ]


def test_parse_deckstats_response_separate_printings_kept_separate():
    """The same card in two sets is two entries; main.py merges quantities."""
    response = {
        "items": [
            {"name": "Abigale, Eloquent First-Year", "amount": 2, "set_abbr": "ECL"},
            {"name": "Abigale, Eloquent First-Year", "amount": 1, "set_abbr": "PECL"},
        ]
    }
    assert parse_deckstats_response(response) == [
        {"card_name": "abigale, eloquent first-year", "quantity": 2},
        {"card_name": "abigale, eloquent first-year", "quantity": 1},
    ]


def test_parse_deckstats_response_bad_amount_defaults_to_one():
    assert parse_deckstats_response({"items": [{"name": "Island", "amount": None}]}) == [
        {"card_name": "island", "quantity": 1}
    ]


def test_parse_deckstats_response_skips_nameless_and_non_dict_rows():
    response = {"items": [{"name": "", "amount": 2}, "junk", {"name": "Forest", "amount": 1}]}
    assert parse_deckstats_response(response) == [{"card_name": "forest", "quantity": 1}]


def test_parse_deckstats_response_empty():
    assert parse_deckstats_response({"items": []}) == []
    assert parse_deckstats_response({}) == []
    assert parse_deckstats_response({"items": "nope"}) == []


@pytest.mark.parametrize(
    "total,per_page,expected",
    [(0, 500, 0), (1, 500, 1), (500, 500, 1), (501, 500, 2), (1451, 500, 3), (10, 0, 0)],
)
def test_total_pages(total, per_page, expected):
    assert total_pages(total, per_page) == expected


def _mock_playwright(page):
    context = MagicMock()
    context.new_page.return_value = page
    pw = MagicMock()
    pw.__enter__ = MagicMock(return_value=pw)
    pw.__exit__ = MagicMock(return_value=False)
    pw.chromium.launch_persistent_context.return_value = context
    return pw


def _api_response(status, payload):
    return {"status": status, "data": payload if status == 200 else None}


def test_scrape_walks_every_page():
    """1451 entries at 500/page must produce 3 requests and all cards."""
    pages = {
        1: {"total": 1451, "page": 1, "per_page": 500,
            "items": [{"name": f"Card {i}", "amount": 1} for i in range(500)]},
        2: {"total": 1451, "page": 2, "per_page": 500,
            "items": [{"name": f"Card {i}", "amount": 1} for i in range(500, 1000)]},
        3: {"total": 1451, "page": 3, "per_page": 500,
            "items": [{"name": f"Card {i}", "amount": 1} for i in range(1000, 1451)]},
    }
    requested = []

    def get(_js, url):
        page_num = int(url.split("page=")[1].split("&")[0])
        requested.append(page_num)
        return _api_response(200, pages[page_num])

    page = MagicMock()
    page.evaluate.side_effect = get

    with patch("scrapers.deckstats.sync_playwright", return_value=_mock_playwright(page)):
        cards = scrape("https://deckstats.net/binders/58989")

    assert requested == [1, 2, 3]
    assert len(cards) == 1451
    assert {"card_name": "card 0", "quantity": 1} in cards
    assert {"card_name": "card 1450", "quantity": 1} in cards
    page.goto.assert_called_once()
    assert page.goto.call_args[0][0] == "https://deckstats.net/binders/58989"


def test_scrape_honours_server_clamped_per_page():
    """If the API ignores per_page and returns 50, paginate by 50."""
    payload = lambda p: {
        "total": 120, "page": p, "per_page": 50,
        "items": [{"name": f"Card {i}", "amount": 1} for i in range(50 if p < 3 else 20)],
    }
    requested = []

    def get(_js, url):
        p = int(url.split("page=")[1].split("&")[0])
        requested.append(p)
        return _api_response(200, payload(p))

    page = MagicMock()
    page.evaluate.side_effect = get

    with patch("scrapers.deckstats.sync_playwright", return_value=_mock_playwright(page)):
        cards = scrape("https://deckstats.net/binders/58989")

    assert requested == [1, 2, 3]
    assert len(cards) == 120


def test_scrape_returns_empty_on_error_status():
    page = MagicMock()
    page.evaluate.return_value = _api_response(403, {})

    with patch("scrapers.deckstats.sync_playwright", return_value=_mock_playwright(page)):
        assert scrape("https://deckstats.net/binders/58989") == []


def test_scrape_handles_empty_binder():
    page = MagicMock()
    page.evaluate.return_value = _api_response(
        200, {"total": 0, "page": 1, "per_page": 500, "items": []}
    )

    with patch("scrapers.deckstats.sync_playwright", return_value=_mock_playwright(page)):
        assert scrape("https://deckstats.net/binders/58989") == []
    assert page.evaluate.call_count == 1
