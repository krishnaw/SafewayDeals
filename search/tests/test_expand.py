"""Unit and integration tests for query expansion (search/expand.py)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from search.expand import expand_query, _cached_expand, _get_api_key


# Real Groq responses captured 2026-02-12 — used as mock fixtures.
REAL_EXPANSIONS = {
    "bbq essentials": "charcoal, BBQ sauce, ketchup, mustard, hot dogs, hamburger buns, ribs, corn, baked beans",
    "healthy snacks": "almonds, granola bars, hummus, rice cakes, dried fruit, trail mix, yogurt, apples",
    "protein rich": "chicken breast, beef, steak, eggs, Greek yogurt, protein bars, salmon, tuna, turkey, cottage cheese",
    "breakfast items": "cereal, oatmeal, pancake mix, syrup, eggs, milk, butter, yogurt, toast, English muffin",
    "party supplies": "chips, salsa, soda, beer, ice cream, frozen pizza",
    "italian dinner": "spaghetti, marinara sauce, lasagna, meatballs, ravioli, Italian bread, garlic bread, parmesan cheese, sausage, pepperoni",
    "kids lunch ideas": "tuna, turkey, chicken, peanut butter, jelly, bread, tortillas, cheese, ham, crackers, grapes, carrot sticks, yogurt, mac & cheese",
    "craft beer": "IPA, craft lager, pale ale, porter, stout, amber ale, wheat beer, brown ale",
    "cocktail mixers": "triple sec, lemon-lime soda, 7-up, tonic water, cola, cranberry juice, pineapple juice, grenadine, simple syrup, rum, tequila.",
    "cleaning supplies": "dish soap, trash bags, paper towels, laundry detergent, glass cleaner, air freshener, window cleaner, all-purpose cleaner, dishwashing liquid, disinfectant spray, bleach, broom, dustpan",
    "baby essentials": "diapers, baby wipes, formula, baby food, baby bath wash, baby lotion, baby oil, baby shampoo, baby cream, baby toothpaste, pacifiers",
    "pet food": "dog food, cat food, salmon oil for pets, Purina, Iams, Royal Canin, Greenies for cats and dogs",
    "pain relief": "Advil, ibuprofen, acetaminophen, Aleve, Bayer Aspirin, pain relieving cream, Motrin, Excedrin, Tylenol",
    "allergy medicine": "Benadryl, Advil, Claritin, Zyrtec, Allegra, Tums, acid reducer, vitamin C, saline drops, children's ibuprofen, acetaminophen",
}

# Queries where the LLM should return PASS (already specific)
PASS_QUERIES = {
    "coca cola zero": "PASS",
    "chicken breast": "PASS",
    "milk": "PASS",
}


def _mock_groq_response(text: str):
    """Build a mock Groq chat completion response."""
    msg = MagicMock()
    msg.content = text
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


def _make_mock_client():
    """Create a mock Groq client that returns real cached expansions."""
    mock_client = MagicMock()

    def _side_effect(**kwargs):
        user_msg = kwargs["messages"][1]["content"]
        if user_msg in PASS_QUERIES:
            return _mock_groq_response(PASS_QUERIES[user_msg])
        if user_msg in REAL_EXPANSIONS:
            return _mock_groq_response(REAL_EXPANSIONS[user_msg])
        return _mock_groq_response("PASS")

    mock_client.chat.completions.create.side_effect = _side_effect
    return mock_client


@pytest.fixture(autouse=True)
def clear_lru_cache():
    """Clear the LRU cache before each test so results aren't stale."""
    _cached_expand.cache_clear()
    yield
    _cached_expand.cache_clear()


@pytest.fixture
def mock_groq():
    """Fixture that patches the Groq client with real cached responses."""
    client = _make_mock_client()
    with patch("search.expand._get_client", return_value=client):
        yield client


# ---------------------------------------------------------------------------
# Unit tests — short-circuit logic (no LLM needed)
# ---------------------------------------------------------------------------

class TestExpandQueryShortCircuit:
    """Tests for expand_query logic that never touches the LLM."""

    def test_single_word_returns_none(self):
        assert expand_query("milk") is None

    def test_single_word_with_whitespace_returns_none(self):
        assert expand_query("  milk  ") is None

    def test_empty_string_returns_none(self):
        assert expand_query("") is None

    @pytest.mark.parametrize("word", ["chicken", "yogurt", "beer", "detergent", "salmon"])
    def test_single_word_various(self, word):
        assert expand_query(word) is None


# ---------------------------------------------------------------------------
# Unit tests — mocked LLM with real cached responses
# ---------------------------------------------------------------------------

class TestExpandWithMockLLM:
    """Tests using mock Groq client seeded with real response data."""

    def test_multi_word_returns_expansion(self, mock_groq):
        result = expand_query("protein rich")
        assert result is not None
        assert "chicken breast" in result
        assert "salmon" in result

    def test_bbq_expansion_has_grilling_terms(self, mock_groq):
        result = expand_query("BBQ essentials")
        assert result is not None
        terms = [t.strip().lower() for t in result.split(",")]
        assert "charcoal" in terms
        assert "bbq sauce" in terms

    def test_cleaning_supplies_expansion(self, mock_groq):
        result = expand_query("cleaning supplies")
        assert result is not None
        terms = [t.strip().lower() for t in result.split(",")]
        assert any("detergent" in t for t in terms)
        assert any("paper towel" in t for t in terms)

    def test_italian_dinner_expansion(self, mock_groq):
        result = expand_query("Italian dinner")
        assert result is not None
        terms = [t.strip().lower() for t in result.split(",")]
        assert "spaghetti" in terms
        assert any("marinara" in t for t in terms)

    def test_party_supplies_no_non_grocery(self, mock_groq):
        result = expand_query("party supplies")
        assert result is not None
        terms = [t.strip().lower() for t in result.split(",")]
        non_grocery = {"balloons", "streamers", "party hats", "confetti", "decorations"}
        bad = [t for t in terms if any(w in t for w in non_grocery)]
        assert len(bad) == 0, f"Non-grocery terms found: {bad}"

    def test_pass_response_returns_none(self, mock_groq):
        result = expand_query("coca cola zero")
        assert result is None

    def test_pass_case_insensitive(self, mock_groq):
        # Mock always returns "PASS" for chicken breast
        result = expand_query("chicken breast")
        assert result is None

    def test_expansion_is_comma_separated(self, mock_groq):
        result = expand_query("BBQ essentials")
        terms = [t.strip() for t in result.split(",")]
        assert len(terms) >= 3

    @pytest.mark.parametrize("query,min_terms", [
        ("BBQ essentials", 5),
        ("healthy snacks", 5),
        ("protein rich", 5),
        ("breakfast items", 5),
        ("party supplies", 3),
        ("Italian dinner", 5),
        ("craft beer", 5),
        ("cleaning supplies", 5),
        ("pain relief", 5),
        ("allergy medicine", 5),
        ("pet food", 3),
        ("baby essentials", 5),
    ])
    def test_expansion_term_count(self, mock_groq, query, min_terms):
        result = expand_query(query)
        assert result is not None
        terms = [t.strip() for t in result.split(",") if t.strip()]
        assert len(terms) >= min_terms, f"'{query}' only got {len(terms)} terms: {terms}"


class TestExpandErrorHandling:
    """Tests for graceful error handling."""

    def test_no_api_key_returns_none(self):
        with patch("search.expand._get_client", return_value=None):
            assert expand_query("healthy snacks") is None

    def test_api_timeout_returns_none(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("Request timed out")
        with patch("search.expand._get_client", return_value=mock_client):
            assert expand_query("BBQ essentials") is None

    def test_api_rate_limit_returns_none(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("Rate limit exceeded")
        with patch("search.expand._get_client", return_value=mock_client):
            assert expand_query("party supplies") is None

    def test_malformed_response_returns_none(self):
        mock_client = MagicMock()
        resp = MagicMock()
        resp.choices = []  # Empty choices
        mock_client.chat.completions.create.return_value = resp
        with patch("search.expand._get_client", return_value=mock_client):
            assert expand_query("cleaning supplies") is None


class TestExpandCaching:
    """Tests for LRU cache behavior."""

    def test_cache_deduplicates_calls(self, mock_groq):
        r1 = expand_query("party supplies")
        r2 = expand_query("party supplies")
        assert r1 == r2
        assert mock_groq.chat.completions.create.call_count == 1

    def test_normalizes_query_case(self, mock_groq):
        r1 = expand_query("Party Supplies")
        r2 = expand_query("party supplies")
        assert r1 == r2
        assert mock_groq.chat.completions.create.call_count == 1

    def test_different_queries_separate_cache_entries(self, mock_groq):
        r1 = expand_query("healthy snacks")
        r2 = expand_query("pain relief")
        assert r1 != r2
        assert mock_groq.chat.completions.create.call_count == 2


class TestExpandModelParams:
    """Tests that the Groq API is called with correct parameters."""

    def test_uses_correct_model(self, mock_groq):
        expand_query("breakfast items")
        call_kwargs = mock_groq.chat.completions.create.call_args.kwargs
        assert call_kwargs["model"] == "llama-3.1-8b-instant"

    def test_max_tokens_set(self, mock_groq):
        expand_query("breakfast items")
        call_kwargs = mock_groq.chat.completions.create.call_args.kwargs
        assert call_kwargs["max_tokens"] == 200

    def test_timeout_set(self, mock_groq):
        expand_query("breakfast items")
        call_kwargs = mock_groq.chat.completions.create.call_args.kwargs
        assert call_kwargs["timeout"] == 3.0

    def test_system_prompt_includes_categories(self, mock_groq):
        expand_query("breakfast items")
        messages = mock_groq.chat.completions.create.call_args.kwargs["messages"]
        system_msg = messages[0]["content"]
        assert "Beverages" in system_msg
        assert "Meat & Seafood" in system_msg
        assert "Pet Care" in system_msg
        assert "Baby Care" in system_msg

    def test_user_message_is_lowered_query(self, mock_groq):
        expand_query("Breakfast Items")
        messages = mock_groq.chat.completions.create.call_args.kwargs["messages"]
        assert messages[1]["content"] == "breakfast items"


# ---------------------------------------------------------------------------
# Integration tests — real Groq API (skipped if no key)
# ---------------------------------------------------------------------------

def _has_groq_key() -> bool:
    return _get_api_key() is not None


@pytest.mark.skipif(not _has_groq_key(), reason="GROQ_API_KEY not set")
class TestExpandIntegration:
    """Hit the real Groq API. Verify end-to-end behavior."""

    def test_bbq_essentials_returns_food_terms(self):
        result = expand_query("BBQ essentials")
        assert result is not None
        terms = [t.strip().lower() for t in result.split(",")]
        assert len(terms) >= 3
        bbq_words = {"charcoal", "bbq", "sauce", "ketchup", "mustard", "hot dogs",
                     "ribs", "buns", "hamburger", "corn", "baked beans"}
        matched = sum(1 for t in terms if any(w in t for w in bbq_words))
        assert matched >= 2, f"Expected BBQ terms, got: {terms}"

    def test_healthy_snacks_returns_food_terms(self):
        result = expand_query("healthy snacks")
        assert result is not None
        terms = [t.strip().lower() for t in result.split(",")]
        assert len(terms) >= 3

    def test_specific_product_short_expansion(self):
        """Specific product names should get PASS or a very short expansion."""
        result = expand_query("coca cola zero")
        if result is not None:
            # LLM may sometimes expand instead of PASS — but should be very few terms
            terms = [t.strip() for t in result.split(",") if t.strip()]
            assert len(terms) <= 5, f"Expected PASS or short expansion, got: {terms}"

    def test_expansion_stays_within_grocery_categories(self):
        result = expand_query("party supplies")
        assert result is not None
        terms = [t.strip().lower() for t in result.split(",")]
        non_grocery = {"balloons", "streamers", "party hats", "confetti", "decorations"}
        bad_terms = [t for t in terms if any(w in t for w in non_grocery)]
        assert len(bad_terms) == 0, f"Non-grocery terms found: {bad_terms}"

    def test_expansion_term_count_within_range(self):
        result = expand_query("cleaning supplies")
        assert result is not None
        terms = [t.strip() for t in result.split(",") if t.strip()]
        assert 3 <= len(terms) <= 20, f"Got {len(terms)} terms: {terms}"
