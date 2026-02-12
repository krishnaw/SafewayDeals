"""Integration tests against real deals.json + qualifying-products.json data."""

import pytest

from search.index import build_index, load_records, SearchRecord
from search.search import search, DealResult


@pytest.fixture(scope="module")
def index():
    """Build full index once for all integration tests."""
    records, embeddings, model = build_index(show_progress=False)
    return records, embeddings, model


class TestDataLoading:
    def test_record_count(self, index):
        records, _, _ = index
        # 4057 products + 42 offer-only = 4099
        assert len(records) == 4099

    def test_records_have_search_text(self, index):
        records, _, _ = index
        for rec in records:
            assert rec.search_text, f"Record {rec.offer_id}/{rec.product_upc} has empty search_text"

    def test_embeddings_shape(self, index):
        records, embeddings, _ = index
        assert embeddings.shape[0] == len(records)
        assert embeddings.shape[1] == 384  # all-MiniLM-L6-v2 dim

    def test_all_records_have_offer_id(self, index):
        records, _, _ = index
        for rec in records:
            assert rec.offer_id


class TestSearchIntegration:
    def test_search_returns_deals(self, index):
        records, embeddings, model = index
        results = search("lotion", records, embeddings, model)
        assert len(results) > 0
        assert all(isinstance(r, DealResult) for r in results)

    def test_deals_are_unique(self, index):
        records, embeddings, model = index
        results = search("lotion", records, embeddings, model)
        offer_ids = [r.offer_id for r in results]
        assert len(offer_ids) == len(set(offer_ids))

    def test_product_match_surfaces_deal(self, index):
        """Searching for a product name should surface its parent deal."""
        records, embeddings, model = index
        results = search("Gold Bond", records, embeddings, model)
        offer_names = {r.offer_name for r in results}
        assert "Gold Bond Lotion" in offer_names

    def test_deal_has_matching_products(self, index):
        records, embeddings, model = index
        results = search("lotion", records, embeddings, model)
        # Gold Bond Lotion deal should have matching products
        gold_bond = next((r for r in results if r.offer_name == "Gold Bond Lotion"), None)
        assert gold_bond is not None
        assert len(gold_bond.matching_products) > 0

    def test_typo_finds_results(self, index):
        records, embeddings, model = index
        results = search("logion", records, embeddings, model)
        offer_names = {r.offer_name for r in results}
        # Fuzzy should catch typo and find lotion deals
        assert "Gold Bond Lotion" in offer_names

    def test_semantic_natural_language(self, index):
        records, embeddings, model = index
        results = search("healthy snacks", records, embeddings, model)
        assert len(results) > 0

    def test_deal_fields_populated(self, index):
        records, embeddings, model = index
        results = search("milk", records, embeddings, model)
        for deal in results:
            assert deal.offer_id
            assert deal.offer_name
            assert deal.offer_price

    def test_matching_products_belong_to_deal(self, index):
        """Every matching product's offer_id should match the deal's offer_id."""
        records, embeddings, model = index
        results = search("milk", records, embeddings, model)
        for deal in results:
            for prod in deal.matching_products:
                assert prod.offer_id == deal.offer_id
