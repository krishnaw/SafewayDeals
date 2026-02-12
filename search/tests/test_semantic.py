"""Unit tests for semantic_search."""

import numpy as np
import pytest

from search.search import semantic_search


@pytest.fixture(scope="module")
def model():
    """Load the sentence transformer model once for all semantic tests."""
    from search.index import load_model
    return load_model()


@pytest.fixture
def sample_embeddings(sample_records, model):
    """Compute embeddings for sample records."""
    texts = [r.search_text for r in sample_records]
    return model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)


class TestSemanticSearch:
    def test_returns_results(self, sample_records, sample_embeddings, model):
        results = semantic_search("milk", sample_records, sample_embeddings, model)
        assert len(results) > 0

    def test_scores_sorted_descending(self, sample_records, sample_embeddings, model):
        results = semantic_search("milk", sample_records, sample_embeddings, model)
        scores = [s for _, s in results]
        assert scores == sorted(scores, reverse=True)

    def test_relevant_results_rank_higher(self, sample_records, sample_embeddings, model):
        results = semantic_search("milk", sample_records, sample_embeddings, model)
        top_5_ids = {rec.offer_id for rec, _ in results[:5]}
        # Milk Sale and Dairy Savings should be in top results
        assert "D1" in top_5_ids or "D2" in top_5_ids

    def test_top_k_limits_results(self, sample_records, sample_embeddings, model):
        results = semantic_search("milk", sample_records, sample_embeddings, model, top_k=3)
        assert len(results) <= 3

    def test_scores_between_negative1_and_1(self, sample_records, sample_embeddings, model):
        results = semantic_search("milk", sample_records, sample_embeddings, model)
        for _, score in results:
            assert -1.0 <= score <= 1.0

    def test_natural_language_query(self, sample_records, sample_embeddings, model):
        """Semantic search should handle natural language queries."""
        results = semantic_search(
            "something to drink with breakfast",
            sample_records, sample_embeddings, model
        )
        assert len(results) > 0
