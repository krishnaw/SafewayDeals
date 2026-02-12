"""Unit tests for fuzzy_search."""

from search.search import fuzzy_search


class TestFuzzySearch:
    def test_typo_correction(self, sample_records):
        """'mlk' (typo for milk) should still find milk-related records."""
        results = fuzzy_search("mlk", sample_records, threshold=50)
        offer_ids = {rec.offer_id for rec, _ in results}
        assert "D1" in offer_ids  # "Milk Sale"

    def test_exact_match_scores_high(self, sample_records):
        results = fuzzy_search("Milk Sale", sample_records)
        # Best match should be records under "Milk Sale" deal
        if results:
            best_rec, best_score = results[0]
            assert best_rec.offer_id == "D1"
            assert best_score > 90

    def test_scores_sorted_descending(self, sample_records):
        results = fuzzy_search("milk", sample_records)
        scores = [s for _, s in results]
        assert scores == sorted(scores, reverse=True)

    def test_threshold_filters_low_scores(self, sample_records):
        high_threshold = fuzzy_search("milk", sample_records, threshold=90)
        low_threshold = fuzzy_search("milk", sample_records, threshold=50)
        assert len(low_threshold) >= len(high_threshold)

    def test_no_matches_above_threshold(self, sample_records):
        results = fuzzy_search("xyzzyplugh", sample_records, threshold=90)
        assert results == []

    def test_top_k_limits_results(self, sample_records):
        results = fuzzy_search("milk", sample_records, top_k=2)
        assert len(results) <= 2

    def test_matches_product_name(self, sample_records):
        """Should match against product names, not just offer names."""
        results = fuzzy_search("Corn Flakes", sample_records, threshold=70)
        matched_upcs = {rec.product_upc for rec, _ in results}
        assert "007" in matched_upcs

    def test_matches_offer_name(self, sample_records):
        results = fuzzy_search("Lotion Special", sample_records, threshold=70)
        offer_ids = {rec.offer_id for rec, _ in results}
        assert "D6" in offer_ids
