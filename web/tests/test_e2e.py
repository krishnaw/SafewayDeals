"""Playwright E2E tests for the Safeway Deals web portal.

Run with: python -m pytest web/tests/test_e2e.py -v
Headless by default (via pytest.ini). Optimized for speed with minimal page navigations.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

BASE_URL = "http://localhost:8787"


@pytest.fixture(scope="module")
def shared_page(e2e_server, browser):
    """Single shared page for all tests — avoids server overload from many page creations."""
    ctx = browser.new_context()
    p = ctx.new_page()
    yield p
    p.close()
    ctx.close()


def load_home(page: Page):
    """Navigate to home and wait for deals to load."""
    page.goto(BASE_URL, wait_until="domcontentloaded")
    page.wait_for_selector(".deal-card", timeout=30000)


class TestBrowseMode:
    """Tests for the initial browse view: page load, card designs, filters, pagination."""

    def test_page_loads_with_deals(self, shared_page: Page):
        load_home(shared_page)
        expect(shared_page).to_have_title("Safeway Deals")
        expect(shared_page.locator(".brand-title")).to_be_visible()
        expect(shared_page.locator("#search-input")).to_be_visible()
        cards = shared_page.locator(".deal-card")
        assert cards.count() == 20, f"Expected 20 deals on page 1, got {cards.count()}"

    def test_design_picker_present(self, shared_page: Page):
        """Design picker should be visible with 10 style buttons."""
        picker = shared_page.locator(".design-picker")
        expect(picker).to_be_visible()
        buttons = shared_page.locator(".picker-btn")
        assert buttons.count() == 10, f"Expected 10 picker buttons, got {buttons.count()}"

    def test_all_cards_same_design(self, shared_page: Page):
        """All cards should use the same design (default style 1)."""
        cards = shared_page.locator('.deal-card[data-card-style="1"]')
        assert cards.count() == 20, f"Expected all 20 cards to be style 1, got {cards.count()}"

    def test_dropdowns_populated(self, shared_page: Page):
        cat_count = shared_page.evaluate("document.querySelectorAll('#filter-category option').length")
        type_count = shared_page.evaluate("document.querySelectorAll('#filter-type option').length")
        assert cat_count > 3, f"Expected >3 category options, got {cat_count}"
        assert type_count > 2, f"Expected >2 offer type options, got {type_count}"

    def test_pagination(self, shared_page: Page):
        expect(shared_page.locator("#pagination")).to_be_visible()
        expect(shared_page.locator("#page-info")).to_contain_text("Page 1 of")
        expect(shared_page.locator("#prev-btn")).to_be_disabled()
        # Navigate to page 2
        shared_page.click("#next-btn")
        shared_page.wait_for_timeout(2000)
        expect(shared_page.locator("#page-info")).to_contain_text("Page 2 of")
        cards = shared_page.locator(".deal-card")
        assert cards.count() == 20
        # Go back to page 1
        shared_page.click("#prev-btn")
        shared_page.wait_for_timeout(2000)
        expect(shared_page.locator("#page-info")).to_contain_text("Page 1 of")

    def test_category_filter(self, shared_page: Page):
        shared_page.select_option("#filter-category", "Pet Care")
        shared_page.wait_for_timeout(1500)
        cards = shared_page.locator(".deal-card")
        count = cards.count()
        assert 0 < count < 20, f"Expected filtered count between 1 and 19, got {count}"
        # Reset filter
        shared_page.select_option("#filter-category", "")
        shared_page.wait_for_timeout(1500)


class TestSearchMode:
    """Tests for search: SSE streaming, source tags, fuzzy search, clear."""

    def test_search_and_clear(self, shared_page: Page):
        load_home(shared_page)

        # Search for "lotion"
        shared_page.fill("#search-input", "lotion")
        shared_page.wait_for_timeout(5000)

        cards = shared_page.locator(".deal-card")
        assert cards.count() > 0, "Search for 'lotion' should return results"

        # Pagination should be hidden in search mode
        has_hidden = shared_page.evaluate(
            "document.getElementById('pagination').classList.contains('hidden')"
        )
        assert has_hidden, "Pagination should be hidden during search"

        # Results info should update
        text = shared_page.locator("#results-info").text_content()
        assert "result" in text.lower()

        # Clear search and return to browse
        shared_page.click("#search-clear")
        shared_page.wait_for_timeout(2000)
        has_hidden = shared_page.evaluate(
            "document.getElementById('pagination').classList.contains('hidden')"
        )
        assert not has_hidden, "Pagination should be visible after clearing search"
        cards = shared_page.locator(".deal-card")
        assert cards.count() == 20

    def test_fuzzy_search_typo(self, shared_page: Page):
        """Fuzzy search should handle typos (e.g., 'logion' -> 'lotion')."""
        shared_page.fill("#search-input", "logion")
        shared_page.wait_for_timeout(5000)
        cards = shared_page.locator(".deal-card")
        assert cards.count() > 0, "Fuzzy search should find results for 'logion'"
        # Clear for next tests
        shared_page.click("#search-clear")
        shared_page.wait_for_timeout(2000)
