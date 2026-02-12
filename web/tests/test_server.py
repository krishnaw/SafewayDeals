"""Tests for the FastAPI web server."""

import json

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    """Create a test client. Startup event loads the search index."""
    from web.server import app
    with TestClient(app) as c:
        yield c


class TestRootEndpoint:
    def test_returns_html(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_contains_app_structure(self, client):
        resp = client.get("/")
        html = resp.text
        assert "Safeway Deals" in html
        assert "search-input" in html
        assert "deals-grid" in html


class TestCategoriesEndpoint:
    def test_returns_categories(self, client):
        resp = client.get("/api/categories")
        assert resp.status_code == 200
        data = resp.json()
        assert "categories" in data
        assert "offerTypes" in data
        assert isinstance(data["categories"], list)
        assert isinstance(data["offerTypes"], list)

    def test_categories_non_empty(self, client):
        data = client.get("/api/categories").json()
        assert len(data["categories"]) > 0
        assert len(data["offerTypes"]) > 0

    def test_known_category_present(self, client):
        data = client.get("/api/categories").json()
        # We know from the data that "Pet Care" exists
        assert "Pet Care" in data["categories"]

    def test_known_offer_types(self, client):
        data = client.get("/api/categories").json()
        for t in ["MF", "SC"]:
            assert t in data["offerTypes"]


class TestDealsEndpoint:
    def test_default_pagination(self, client):
        resp = client.get("/api/deals")
        assert resp.status_code == 200
        data = resp.json()
        assert "deals" in data
        assert "page" in data
        assert "total" in data
        assert "total_pages" in data
        assert data["page"] == 1
        assert data["per_page"] == 20
        assert len(data["deals"]) <= 20

    def test_total_is_401(self, client):
        data = client.get("/api/deals").json()
        assert data["total"] == 401

    def test_page_2(self, client):
        data = client.get("/api/deals?page=2").json()
        assert data["page"] == 2
        assert len(data["deals"]) == 20

    def test_custom_per_page(self, client):
        data = client.get("/api/deals?per_page=5").json()
        assert len(data["deals"]) == 5

    def test_filter_by_category(self, client):
        data = client.get("/api/deals?category=Pet Care").json()
        assert data["total"] > 0
        assert data["total"] < 401
        for deal in data["deals"]:
            assert deal["category"] == "Pet Care"

    def test_filter_by_offer_pgm(self, client):
        data = client.get("/api/deals?offer_pgm=MF").json()
        assert data["total"] > 0
        for deal in data["deals"]:
            assert deal["offerPgm"] == "MF"

    def test_deal_has_image_fields(self, client):
        data = client.get("/api/deals?per_page=1").json()
        deal = data["deals"][0]
        assert "dealImageUrl" in deal
        assert "productImageUrl" in deal
        assert "offerId" in deal
        assert "name" in deal
        assert "offerPrice" in deal

    def test_combined_filters(self, client):
        data = client.get("/api/deals?category=Pet Care&offer_pgm=MF").json()
        for deal in data["deals"]:
            assert deal["category"] == "Pet Care"
            assert deal["offerPgm"] == "MF"

    def test_page_beyond_max_clamps(self, client):
        data = client.get("/api/deals?page=9999").json()
        assert data["page"] == data["total_pages"]


class TestSearchStreamEndpoint:
    def test_stream_returns_sse(self, client):
        resp = client.get("/api/search/stream?q=lotion")
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]

    def test_stream_returns_results(self, client):
        # Use non-streaming to collect full response
        resp = client.get("/api/search/stream?q=lotion")
        assert resp.status_code == 200
        text = resp.text
        # Should contain data events and [END]
        assert "data:" in text
        assert "[END]" in text

    def test_stream_parseable_json_batches(self, client):
        resp = client.get("/api/search/stream?q=cat food")
        lines = [l for l in resp.text.strip().split("\n") if l.startswith("data:")]
        results = []
        for line in lines:
            payload = line[len("data:"):].strip()
            if payload == "[END]":
                continue
            batch = json.loads(payload)
            assert isinstance(batch, list)
            results.extend(batch)
        assert len(results) > 0

    def test_stream_results_have_fields(self, client):
        resp = client.get("/api/search/stream?q=lotion")
        lines = [l for l in resp.text.strip().split("\n") if l.startswith("data:")]
        for line in lines:
            payload = line[len("data:"):].strip()
            if payload == "[END]":
                continue
            batch = json.loads(payload)
            for deal in batch:
                assert "offer_id" in deal
                assert "offer_name" in deal
                assert "score" in deal
                assert "sources" in deal
                assert "dealImageUrl" in deal

    def test_stream_requires_query(self, client):
        resp = client.get("/api/search/stream")
        assert resp.status_code == 422  # validation error

    def test_fuzzy_search_handles_typo(self, client):
        resp = client.get("/api/search/stream?q=logion")
        lines = [l for l in resp.text.strip().split("\n") if l.startswith("data:")]
        results = []
        for line in lines:
            payload = line[len("data:"):].strip()
            if payload == "[END]":
                continue
            results.extend(json.loads(payload))
        # Should find lotion-related results via fuzzy matching
        assert len(results) > 0
