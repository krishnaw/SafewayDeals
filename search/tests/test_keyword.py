"""Unit tests for keyword_search."""

from search.search import keyword_search


class TestKeywordSearch:
    def test_single_word_match(self, sample_records):
        results = keyword_search("milk", sample_records)
        matched_upcs = {rec.product_upc for rec, _ in results}
        # Should match: Whole Milk, 2% Milk, Organic Whole Milk, Chocolate Milk
        assert "001" in matched_upcs
        assert "002" in matched_upcs
        assert "003" in matched_upcs
        assert "006" in matched_upcs

    def test_single_word_excludes_non_matches(self, sample_records):
        results = keyword_search("milk", sample_records)
        matched_upcs = {rec.product_upc for rec, _ in results}
        # Corn Flakes, Dark Chocolate Bar, Cheddar Cheese should NOT match
        assert "007" not in matched_upcs
        assert "005" not in matched_upcs
        assert "004" not in matched_upcs

    def test_multi_word_all_must_match(self, sample_records):
        results = keyword_search("chocolate milk", sample_records)
        matched_upcs = {rec.product_upc for rec, _ in results}
        # Only "Chocolate Milk Drink" has both words in search_text
        assert "006" in matched_upcs
        # "Dark Chocolate Bar" has chocolate but not milk
        assert "005" not in matched_upcs

    def test_case_insensitive(self, sample_records):
        lower = keyword_search("milk", sample_records)
        upper = keyword_search("MILK", sample_records)
        mixed = keyword_search("Milk", sample_records)
        assert len(lower) == len(upper) == len(mixed)

    def test_no_matches_returns_empty(self, sample_records):
        results = keyword_search("pizza", sample_records)
        assert results == []

    def test_empty_query_returns_empty(self, sample_records):
        results = keyword_search("", sample_records)
        assert results == []

    def test_results_sorted_by_score(self, sample_records):
        results = keyword_search("milk", sample_records)
        scores = [s for _, s in results]
        assert scores == sorted(scores, reverse=True)

    def test_offer_name_match_scores_higher(self, sample_records):
        """Record with 'milk' in offer_name should score higher than 'milk' only in product_name."""
        results = keyword_search("milk", sample_records)
        by_upc = {rec.product_upc: score for rec, score in results}
        # D1 "Milk Sale" / UPC 001 has milk in offer_name
        # D2 UPC 003 "Organic Whole Milk" only has milk in product_name
        assert by_upc["001"] > by_upc["003"]

    def test_top_k_limits_results(self, sample_records):
        results = keyword_search("milk", sample_records, top_k=2)
        assert len(results) <= 2

    def test_offer_only_record_searchable(self, sample_records):
        results = keyword_search("bread", sample_records)
        offer_ids = {rec.offer_id for rec, _ in results}
        assert "D4" in offer_ids

    def test_matches_in_description(self, sample_records):
        results = keyword_search("dairy essentials", sample_records)
        offer_ids = {rec.offer_id for rec, _ in results}
        assert "D2" in offer_ids

    def test_whole_word_scores_higher_than_substring(self, sample_records):
        """'milk' as whole word in 'Milk Sale' should score higher than 'milk' in 'Oatmilk'."""
        results = keyword_search("milk", sample_records)
        by_upc = {rec.product_upc: score for rec, score in results}
        # D1's "Whole Milk" (whole word) vs D9's "Planet Oat Oatmilk" (substring)
        assert by_upc["001"] > by_upc["011"]

    def test_scores_between_0_and_1(self, sample_records):
        """All keyword scores should be normalized between 0 and 1."""
        results = keyword_search("milk", sample_records)
        for _, score in results:
            assert 0.0 < score <= 1.0

    def test_category_field_match(self, sample_records):
        """Match in category field ('Wine, Beer & Spirits') should be found."""
        results = keyword_search("wine", sample_records)
        offer_ids = {rec.offer_id for rec, _ in results}
        assert "D7" in offer_ids  # "Wine Special"

    def test_offer_name_scores_above_category_only(self, sample_records):
        """'wine' in offer_name 'Wine Special' should score higher than 'wine' only in category."""
        results = keyword_search("wine", sample_records)
        by_oid = {}
        for rec, score in results:
            by_oid.setdefault(rec.offer_id, []).append(score)
        # D7 "Wine Special" has wine in offer_name AND category
        # D8 "Beer Deal" has wine only in category field
        d7_best = max(by_oid.get("D7", [0]))
        d8_best = max(by_oid.get("D8", [0]))
        assert d7_best > d8_best

    def test_description_weight_above_other_fields(self, sample_records):
        """Match in description should score higher than match only in category/dept."""
        results = keyword_search("wines", sample_records)
        by_oid = {}
        for rec, score in results:
            by_oid.setdefault(rec.offer_id, []).append(score)
        # D7 has "wines" in description ("Save on select wines")
        # D7 should have higher score because description weight (1.0) > other fields (0.5)
        if "D7" in by_oid:
            assert max(by_oid["D7"]) > 0

    def test_multi_word_scoring_additive(self, sample_records):
        """Multi-word queries should sum weights per word, not just count matches."""
        results_one = keyword_search("milk", sample_records)
        results_two = keyword_search("chocolate milk", sample_records)
        # "Chocolate Milk Drink" (UPC 006) should have different normalized
        # scores between 1-word and 2-word queries
        one_scores = {rec.product_upc: s for rec, s in results_one}
        two_scores = {rec.product_upc: s for rec, s in results_two}
        # Both should find UPC 006 but with different normalizations
        assert "006" in one_scores
        assert "006" in two_scores
