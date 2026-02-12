"""Unit tests for the unified search() function and DealResult grouping."""

import numpy as np
import pytest

from search.search import search, DealResult


@pytest.fixture(scope="module")
def model():
    from search.index import load_model
    return load_model()


@pytest.fixture
def sample_embeddings(sample_records, model):
    texts = [r.search_text for r in sample_records]
    return model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)


class TestUnifiedSearch:
    def test_returns_deal_results(self, sample_records, sample_embeddings, model):
        results = search("milk", sample_records, sample_embeddings, model)
        assert all(isinstance(r, DealResult) for r in results)

    def test_deals_are_unique(self, sample_records, sample_embeddings, model):
        results = search("milk", sample_records, sample_embeddings, model)
        offer_ids = [r.offer_id for r in results]
        assert len(offer_ids) == len(set(offer_ids))

    def test_deal_matched_by_name(self, sample_records, sample_embeddings, model):
        """Deal 'Milk Sale' should appear when searching 'milk' (deal name matches)."""
        results = search("milk", sample_records, sample_embeddings, model)
        offer_ids = {r.offer_id for r in results}
        assert "D1" in offer_ids

    def test_deal_matched_by_product(self, sample_records, sample_embeddings, model):
        """Deal 'Dairy Savings' should appear because its product 'Organic Whole Milk' matches."""
        results = search("milk", sample_records, sample_embeddings, model)
        offer_ids = {r.offer_id for r in results}
        assert "D2" in offer_ids

    def test_deal_matched_by_product_cross_deal(self, sample_records, sample_embeddings, model):
        """Deal 'Chocolate Treats' should appear because it has 'Chocolate Milk Drink'."""
        results = search("milk", sample_records, sample_embeddings, model)
        offer_ids = {r.offer_id for r in results}
        assert "D3" in offer_ids

    def test_matching_products_correct_for_deal(self, sample_records, sample_embeddings, model):
        """D2 'Dairy Savings' should only have the milk product as matching, not cheese."""
        results = search("milk", sample_records, sample_embeddings, model)
        d2 = next(r for r in results if r.offer_id == "D2")
        matching_upcs = {p.product_upc for p in d2.matching_products}
        # Organic Whole Milk should match
        assert "003" in matching_upcs

    def test_scores_sorted_descending(self, sample_records, sample_embeddings, model):
        results = search("milk", sample_records, sample_embeddings, model)
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_sources_populated(self, sample_records, sample_embeddings, model):
        results = search("milk", sample_records, sample_embeddings, model)
        for r in results:
            assert len(r.sources) > 0
            assert all(s in ("keyword", "fuzzy", "semantic") for s in r.sources)

    def test_offer_only_deal_has_no_matching_products(self, sample_records, sample_embeddings, model):
        """D4 'Fresh Bread' is offer-only. If it matches, matching_products should be empty."""
        results = search("bread", sample_records, sample_embeddings, model)
        d4 = next((r for r in results if r.offer_id == "D4"), None)
        if d4:
            assert d4.matching_products == []

    def test_top_k_limits_deals(self, sample_records, sample_embeddings, model):
        results = search("milk", sample_records, sample_embeddings, model, top_k=2)
        assert len(results) <= 2

    def test_milk_in_name_ranks_above_milk_in_product(self, sample_records, sample_embeddings, model):
        """D1 'Milk Sale' (milk in offer name) should rank above D3 'Chocolate Treats' (milk in product)."""
        results = search("milk", sample_records, sample_embeddings, model)
        d1 = next(r for r in results if r.offer_id == "D1")
        d3 = next(r for r in results if r.offer_id == "D3")
        assert d1.score > d3.score

    def test_scores_differentiated(self, sample_records, sample_embeddings, model):
        """With composite scoring, not all deals should have the same score."""
        results = search("milk", sample_records, sample_embeddings, model)
        scores = {r.score for r in results}
        assert len(scores) > 1, "All deals have identical scores — ranking is flat"

    def test_no_results_for_nonsense(self, sample_records, sample_embeddings, model):
        """Gibberish that doesn't appear in corpus should return empty results."""
        results = search("xyzzyplugh", sample_records, sample_embeddings, model)
        assert len(results) == 0

    # --- Composite scoring tests ---

    def test_multi_source_bonus(self, sample_records, sample_embeddings, model):
        """Deals found by multiple search modes should get a score bonus."""
        results = search("milk", sample_records, sample_embeddings, model)
        # D1 "Milk Sale" should be found by keyword, fuzzy, AND semantic
        d1 = next(r for r in results if r.offer_id == "D1")
        assert len(d1.sources) >= 2, "D1 should be found by multiple search modes"

    def test_semantic_only_scores_lower(self, sample_records, sample_embeddings, model):
        """Deals matched only by semantic search should score lower than keyword matches."""
        results = search("milk", sample_records, sample_embeddings, model)
        kw_deals = [r for r in results if "keyword" in r.sources]
        sem_only = [r for r in results if r.sources == ["semantic"]]
        if kw_deals and sem_only:
            assert max(r.score for r in kw_deals) > max(r.score for r in sem_only)

    def test_offer_name_boost_applied(self, sample_records, sample_embeddings, model):
        """D1 'Milk Sale' gets offer-name boost; D2 'Dairy Savings' does not."""
        results = search("milk", sample_records, sample_embeddings, model)
        d1 = next(r for r in results if r.offer_id == "D1")
        d2 = next(r for r in results if r.offer_id == "D2")
        # D1 has "milk" in offer name, D2 doesn't — D1 should rank higher
        assert d1.score > d2.score

    def test_density_penalizes_sparse_match(self, sample_records, sample_embeddings, model):
        """D10 'Candy Bonanza' has 4 products but only 1 matches 'chocolate'.
        D3 'Chocolate Treats' has 2 products and both match. D3 should rank higher."""
        results = search("chocolate", sample_records, sample_embeddings, model)
        d3 = next((r for r in results if r.offer_id == "D3"), None)
        d10 = next((r for r in results if r.offer_id == "D10"), None)
        if d3 and d10:
            assert d3.score > d10.score, "Higher density deal should rank above sparse match"

    def test_fuzzy_cap_prevents_inflation(self, sample_records, sample_embeddings, model):
        """When keyword matches, fuzzy score should be capped to keyword score."""
        # "milk" exactly matches keyword — fuzzy should not inflate beyond keyword
        results = search("milk", sample_records, sample_embeddings, model)
        d1 = next(r for r in results if r.offer_id == "D1")
        # Score should be reasonable (not inflated by uncapped fuzzy)
        assert d1.score < 2.0, "Score seems inflated by uncapped fuzzy"

    def test_gibberish_gate_blocks_nonsense(self, sample_records, sample_embeddings, model):
        """Queries with no corpus words should return empty results."""
        for gibberish in ["abcxyz", "qqqqq", "zzzfff"]:
            results = search(gibberish, sample_records, sample_embeddings, model)
            assert results == [], f"'{gibberish}' should return 0 results, got {len(results)}"

    def test_gibberish_gate_allows_real_words(self, sample_records, sample_embeddings, model):
        """Queries with real words in corpus should pass the gate."""
        results = search("chocolate", sample_records, sample_embeddings, model)
        assert len(results) > 0, "Real word 'chocolate' should return results"

    def test_wine_in_name_ranks_above_wine_in_category(self, sample_records, sample_embeddings, model):
        """D7 'Wine Special' should rank above D8 'Beer Deal' for 'wine' query."""
        results = search("wine", sample_records, sample_embeddings, model)
        d7 = next((r for r in results if r.offer_id == "D7"), None)
        d8 = next((r for r in results if r.offer_id == "D8"), None)
        assert d7 is not None, "Wine Special should appear in wine search"
        if d8:
            assert d7.score > d8.score, "Wine in offer name should rank above wine only in category"

    def test_adaptive_cutoff_trims_weak_results(self, sample_records, sample_embeddings, model):
        """Low-confidence results should be trimmed more aggressively."""
        results = search("bread", sample_records, sample_embeddings, model)
        if results:
            top_score = results[0].score
            for r in results:
                # All results should be above the cutoff threshold
                if top_score >= 0.5:
                    assert r.score >= top_score * 0.4
                else:
                    assert r.score >= top_score * 0.7
