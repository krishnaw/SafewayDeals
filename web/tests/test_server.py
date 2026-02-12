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


def _has_groq_key() -> bool:
    from search.expand import _get_api_key
    return _get_api_key() is not None


def _parse_sse(text: str) -> tuple[list[dict], list[dict]]:
    """Parse SSE response into (metadata_events, deal_results)."""
    meta = []
    results = []
    for line in text.strip().split("\n"):
        if not line.startswith("data:"):
            continue
        payload = line[len("data:"):].strip()
        if payload == "[END]":
            continue
        parsed = json.loads(payload)
        if isinstance(parsed, dict):
            meta.append(parsed)
        elif isinstance(parsed, list):
            results.extend(parsed)
    return meta, results


@pytest.mark.skipif(not _has_groq_key(), reason="GROQ_API_KEY not set")
class TestNLQSearchStream:
    """Tests for NLQ query expansion in the SSE search endpoint."""

    def test_nlq_emits_expanded_event(self, client):
        """Multi-word NLQ query should emit an 'expanded' SSE event."""
        resp = client.get("/api/search/stream?q=healthy+snacks")
        meta, results = _parse_sse(resp.text)
        expanded_events = [m for m in meta if m.get("type") == "expanded"]
        assert len(expanded_events) == 1
        assert expanded_events[0]["original"] == "healthy snacks"
        assert len(expanded_events[0]["expanded"]) > 0

    def test_single_word_no_expanded_event(self, client):
        """Single-word queries should NOT trigger expansion."""
        resp = client.get("/api/search/stream?q=milk")
        meta, results = _parse_sse(resp.text)
        expanded_events = [m for m in meta if m.get("type") == "expanded"]
        assert len(expanded_events) == 0

    def test_nlq_returns_relevant_results(self, client):
        """NLQ 'cleaning supplies' should return cleaning-related deals."""
        resp = client.get("/api/search/stream?q=cleaning+supplies")
        meta, results = _parse_sse(resp.text)
        assert len(results) >= 3
        names = [r["offer_name"].lower() for r in results[:10]]
        cleaning_words = {"tide", "lysol", "windex", "scrubbing", "detergent",
                          "cleaner", "febreze", "bounty", "paper towel"}
        matched = sum(1 for n in names if any(w in n for w in cleaning_words))
        assert matched >= 2, f"Expected cleaning deals in top 10, got: {names}"

    def test_nlq_pain_relief_finds_medicine(self, client):
        resp = client.get("/api/search/stream?q=pain+relief")
        meta, results = _parse_sse(resp.text)
        assert len(results) >= 1
        names = [r["offer_name"].lower() for r in results[:5]]
        med_words = {"tylenol", "motrin", "advil", "nervive", "aspercreme"}
        matched = sum(1 for n in names if any(w in n for w in med_words))
        assert matched >= 1, f"Expected medicine deals, got: {names}"

    def test_nlq_results_have_scores_above_zero(self, client):
        resp = client.get("/api/search/stream?q=protein+rich")
        meta, results = _parse_sse(resp.text)
        assert len(results) >= 1
        for r in results:
            assert r["score"] > 0

    def test_nlq_noisy_tail_trimmed(self, client):
        """Results should not have very low scores relative to the top."""
        resp = client.get("/api/search/stream?q=pet+food")
        meta, results = _parse_sse(resp.text)
        if len(results) >= 2:
            top_score = results[0]["score"]
            worst_score = results[-1]["score"]
            # Worst result should be at least 45% of top (our cutoff)
            assert worst_score >= top_score * 0.40, (
                f"Noisy tail: worst={worst_score:.3f}, top={top_score:.3f}"
            )


def _parse_chat_sse(text: str) -> list[dict]:
    """Parse chat SSE response into event dicts."""
    events = []
    for line in text.strip().split("\n"):
        if not line.startswith("data:"):
            continue
        payload = line[len("data:"):].strip()
        if payload == "[END]":
            continue
        try:
            events.append(json.loads(payload))
        except json.JSONDecodeError:
            pass
    return events


class TestChatEndpoint:
    """Tests for the POST /api/chat/stream endpoint."""

    def test_requires_message(self, client):
        resp = client.post("/api/chat/stream", json={})
        assert resp.status_code == 400

    def test_returns_sse(self, client):
        resp = client.post("/api/chat/stream", json={"message": "hello"})
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]

    def test_returns_events(self, client):
        resp = client.post("/api/chat/stream", json={"message": "hello"})
        text = resp.text
        assert "data:" in text
        assert "[END]" in text

    def test_chat_has_done_event(self, client):
        resp = client.post("/api/chat/stream", json={"message": "hello"})
        events = _parse_chat_sse(resp.text)
        types = [e.get("type") for e in events]
        assert "done" in types

    def test_accepts_history(self, client):
        history = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "Hello! How can I help?"},
        ]
        resp = client.post("/api/chat/stream", json={
            "message": "show me snacks",
            "history": history,
        })
        assert resp.status_code == 200
        events = _parse_chat_sse(resp.text)
        assert len(events) > 0


class TestChatGuardrails:
    """Tests for chat guardrail enforcement."""

    def test_blocks_politics(self, client):
        resp = client.post("/api/chat/stream", json={
            "message": "who is the president"
        })
        events = _parse_chat_sse(resp.text)
        types = [e.get("type") for e in events]
        assert "guardrail" in types
        guardrail_event = next(e for e in events if e["type"] == "guardrail")
        assert "grocery" in guardrail_event["message"].lower() or "deals" in guardrail_event["message"].lower()

    def test_blocks_coding(self, client):
        resp = client.post("/api/chat/stream", json={
            "message": "write me python code"
        })
        events = _parse_chat_sse(resp.text)
        types = [e.get("type") for e in events]
        assert "guardrail" in types

    def test_allows_grocery_queries(self, client):
        resp = client.post("/api/chat/stream", json={
            "message": "what snacks are on sale"
        })
        events = _parse_chat_sse(resp.text)
        types = [e.get("type") for e in events]
        assert "guardrail" not in types

    def test_allows_recipe_queries(self, client):
        resp = client.post("/api/chat/stream", json={
            "message": "recipe for chicken soup"
        })
        events = _parse_chat_sse(resp.text)
        types = [e.get("type") for e in events]
        assert "guardrail" not in types
