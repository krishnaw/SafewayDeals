"""Ranking quality tests against real deals.json + qualifying-products.json data.

These tests verify that the search engine returns relevant, well-ranked results
for common queries, typos, brand names, and edge cases using the full dataset.
"""

import pytest

from search.index import build_index
from search.search import search, DealResult


@pytest.fixture(scope="module")
def index():
    """Build full index once for all ranking tests."""
    records, embeddings, model = build_index(show_progress=False)
    return records, embeddings, model


class TestGibberishGate:
    """Nonsense queries should return 0 results."""

    @pytest.mark.parametrize("query", ["abcd", "asdf", "qwerty", "blahblah", "zzzzz", "aaa"])
    def test_gibberish_returns_empty(self, index, query):
        records, embeddings, model = index
        results = search(query, records, embeddings, model)
        assert len(results) == 0, f"'{query}' is gibberish but returned {len(results)} results"

    def test_xyz_matches_xyzal_not_gibberish(self, index):
        """'xyz' is a substring of real product XYZAL — should NOT be blocked."""
        records, embeddings, model = index
        results = search("xyz", records, embeddings, model)
        assert len(results) >= 1
        assert any("XYZAL" in r.offer_name for r in results)

    def test_single_real_word_passes_gate(self, index):
        """A single real word that exists in the corpus should pass."""
        records, embeddings, model = index
        for word in ["milk", "bread", "soap", "juice"]:
            results = search(word, records, embeddings, model)
            assert len(results) > 0, f"'{word}' should pass the gibberish gate"


class TestExactMatchRanking:
    """Correct-spelling queries should return well-ranked results."""

    def test_chocolate_ferrero_ranks_first(self, index):
        records, embeddings, model = index
        results = search("chocolate", records, embeddings, model)
        assert len(results) > 0
        assert "chocolate" in results[0].offer_name.lower()

    def test_milk_offer_name_ranks_first(self, index):
        """Deals with 'milk' in offer name should rank above deals with milk only in products."""
        records, embeddings, model = index
        results = search("milk", records, embeddings, model)
        assert len(results) >= 3
        # Top result should have "milk" in offer name
        assert "milk" in results[0].offer_name.lower()

    def test_bread_results_precise(self, index):
        """'bread' should return only bread deals (few, precise results)."""
        records, embeddings, model = index
        results = search("bread", records, embeddings, model)
        assert 1 <= len(results) <= 5
        for r in results:
            assert "bread" in r.offer_name.lower()

    def test_gift_card_all_relevant(self, index):
        """Every result for 'gift card' should actually be a gift card deal."""
        records, embeddings, model = index
        results = search("gift card", records, embeddings, model)
        assert len(results) >= 5
        for r in results:
            assert "gift card" in r.offer_name.lower(), \
                f"'{r.offer_name}' is not a gift card deal"

    def test_coffee_all_relevant(self, index):
        records, embeddings, model = index
        results = search("coffee", records, embeddings, model)
        assert len(results) >= 2
        # Top result should have "coffee" in name
        assert "coffee" in results[0].offer_name.lower()

    def test_exact_match_scores_above_threshold(self, index):
        """Exact keyword matches should produce scores well above 0.5."""
        records, embeddings, model = index
        for query in ["milk", "bread", "cheese", "yogurt", "cereal"]:
            results = search(query, records, embeddings, model)
            assert results[0].score > 0.8, \
                f"'{query}' top score {results[0].score:.3f} is too low for exact match"


class TestTypoRecovery:
    """Typo queries should still find the right deals."""

    def test_choclate_finds_chocolate(self, index):
        records, embeddings, model = index
        results = search("choclate", records, embeddings, model)
        assert len(results) > 0
        # Ferrero or another chocolate deal should be #1
        assert "chocolate" in results[0].offer_name.lower() or \
               "ferrero" in results[0].offer_name.lower()

    def test_logion_finds_lotion(self, index):
        records, embeddings, model = index
        results = search("logion", records, embeddings, model)
        assert len(results) > 0
        offer_names = {r.offer_name for r in results}
        assert any("lotion" in n.lower() for n in offer_names)

    def test_cofee_finds_coffee(self, index):
        records, embeddings, model = index
        results = search("cofee", records, embeddings, model)
        assert len(results) > 0
        assert "coffee" in results[0].offer_name.lower()

    def test_yougrt_finds_yogurt(self, index):
        records, embeddings, model = index
        results = search("yougrt", records, embeddings, model)
        assert len(results) > 0
        offer_names = " ".join(r.offer_name.lower() for r in results)
        assert "yogurt" in offer_names or "chobani" in offer_names or "yoplait" in offer_names

    def test_correct_spelling_more_results_than_typo(self, index):
        """Correct spelling should always return at least as many results as the typo version."""
        records, embeddings, model = index
        pairs = [("chocolate", "choclate"), ("lotion", "logion"), ("coffee", "cofee")]
        for correct, typo in pairs:
            correct_results = search(correct, records, embeddings, model)
            typo_results = search(typo, records, embeddings, model)
            assert len(correct_results) >= len(typo_results), \
                f"'{correct}' ({len(correct_results)}) should have >= results than '{typo}' ({len(typo_results)})"

    def test_typo_scores_lower_than_correct(self, index):
        """Top score for typo query should be lower than correct spelling."""
        records, embeddings, model = index
        pairs = [("chocolate", "choclate"), ("lotion", "logion"), ("coffee", "cofee")]
        for correct, typo in pairs:
            correct_results = search(correct, records, embeddings, model)
            typo_results = search(typo, records, embeddings, model)
            assert correct_results[0].score > typo_results[0].score, \
                f"'{correct}' ({correct_results[0].score:.3f}) should score higher than '{typo}' ({typo_results[0].score:.3f})"


class TestBrandSearch:
    """Brand name queries should find the right deals."""

    def test_pepsi_finds_pepsi_deals(self, index):
        records, embeddings, model = index
        results = search("pepsi", records, embeddings, model)
        assert len(results) >= 2
        for r in results:
            assert "pepsi" in r.offer_name.lower()

    def test_coca_cola_finds_coke(self, index):
        records, embeddings, model = index
        results = search("coca cola", records, embeddings, model)
        assert len(results) >= 1
        assert "coca-cola" in results[0].offer_name.lower() or \
               "coca cola" in results[0].offer_name.lower()

    def test_huggies_finds_huggies(self, index):
        records, embeddings, model = index
        results = search("huggies", records, embeddings, model)
        assert len(results) >= 1
        assert "huggies" in results[0].offer_name.lower()

    def test_ferrero_finds_ferrero(self, index):
        records, embeddings, model = index
        results = search("ferrero", records, embeddings, model)
        assert len(results) >= 1
        assert "ferrero" in results[0].offer_name.lower()

    def test_starbucks_finds_starbucks(self, index):
        records, embeddings, model = index
        results = search("starbucks", records, embeddings, model)
        assert len(results) >= 1
        assert "starbucks" in results[0].offer_name.lower()


class TestAdaptiveCutoff:
    """Verify the adaptive cutoff trims noise without losing good results."""

    def test_high_confidence_keeps_more(self, index):
        """Queries with strong matches (top score > 0.5) should keep results
        down to 40% of top score."""
        records, embeddings, model = index
        results = search("cheese", records, embeddings, model)
        assert results[0].score > 0.5
        cutoff = results[0].score * 0.4
        for r in results:
            assert r.score >= cutoff - 0.001  # small epsilon for float

    def test_low_confidence_trims_more(self, index):
        """Queries with weak matches (top score < 0.5) should trim results
        down to 70% of top score."""
        records, embeddings, model = index
        results = search("logion", records, embeddings, model)
        if results and results[0].score < 0.5:
            cutoff = results[0].score * 0.7
            for r in results:
                assert r.score >= cutoff - 0.001

    def test_wine_not_excessive(self, index):
        """'wine' should not return an excessive number of results (was 36 before fix)."""
        records, embeddings, model = index
        results = search("wine", records, embeddings, model)
        assert len(results) <= 15, f"'wine' returned {len(results)} results, expected <= 15"

    def test_choclate_typo_trimmed(self, index):
        """'choclate' typo should not return excessive tail noise."""
        records, embeddings, model = index
        results = search("choclate", records, embeddings, model)
        assert len(results) <= 15, f"'choclate' returned {len(results)} results, expected <= 15"


class TestScoreQuality:
    """Verify score differentiation and ranking properties."""

    def test_scores_not_flat(self, index):
        """For common queries, scores should show clear differentiation."""
        records, embeddings, model = index
        for query in ["milk", "chocolate", "cheese", "snacks"]:
            results = search(query, records, embeddings, model)
            if len(results) >= 3:
                scores = [r.score for r in results]
                score_range = max(scores) - min(scores)
                assert score_range > 0.1, \
                    f"'{query}' has flat scores (range={score_range:.3f})"

    def test_scores_sorted_descending(self, index):
        """Results should always be sorted by score descending."""
        records, embeddings, model = index
        for query in ["milk", "chocolate", "beer", "gift card", "lotion"]:
            results = search(query, records, embeddings, model)
            scores = [r.score for r in results]
            assert scores == sorted(scores, reverse=True), \
                f"'{query}' results not sorted by score"

    def test_all_results_are_deal_results(self, index):
        """Every result should be a proper DealResult with required fields."""
        records, embeddings, model = index
        for query in ["milk", "bread", "candy"]:
            results = search(query, records, embeddings, model)
            for r in results:
                assert isinstance(r, DealResult)
                assert r.offer_id
                assert r.offer_name
                assert r.score > 0
                assert len(r.sources) > 0

    def test_matching_products_belong_to_deal(self, index):
        """Every matching product's offer_id should match its parent deal."""
        records, embeddings, model = index
        for query in ["milk", "chocolate", "cheese", "coffee"]:
            results = search(query, records, embeddings, model)
            for deal in results:
                for prod in deal.matching_products:
                    assert prod.offer_id == deal.offer_id, \
                        f"Product {prod.product_name} has offer_id {prod.offer_id} but deal has {deal.offer_id}"

    def test_deals_are_unique(self, index):
        """No duplicate offer_ids in results."""
        records, embeddings, model = index
        for query in ["milk", "chocolate", "beer", "lotion", "cereal"]:
            results = search(query, records, embeddings, model)
            offer_ids = [r.offer_id for r in results]
            assert len(offer_ids) == len(set(offer_ids)), \
                f"'{query}' has duplicate offer_ids"


class TestNaturalLanguage:
    """Natural language queries should return reasonable results."""

    def test_healthy_snacks_returns_results(self, index):
        records, embeddings, model = index
        results = search("healthy snacks", records, embeddings, model)
        assert len(results) > 0

    def test_baby_products_returns_results(self, index):
        records, embeddings, model = index
        results = search("baby products", records, embeddings, model)
        assert len(results) > 0

    def test_pet_food_finds_pet_deals(self, index):
        records, embeddings, model = index
        results = search("pet food", records, embeddings, model)
        assert len(results) > 0
        # Should find cat/dog food deals
        names = " ".join(r.offer_name.lower() for r in results)
        assert "cat" in names or "purina" in names or "pet" in names

    def test_cleaning_supplies_returns_results(self, index):
        records, embeddings, model = index
        results = search("cleaning supplies", records, embeddings, model)
        assert len(results) > 0
