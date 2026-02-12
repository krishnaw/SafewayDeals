"""Unit tests for the chat module (search/chat.py)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from search.chat import (
    SYSTEM_PROMPT,
    _extract_raw_tool_call,
    _parse_suggestions,
    chat_stream,
    format_deals_for_context,
    is_on_topic,
    truncate_history,
)
from search.search import DealResult


# ---------------------------------------------------------------------------
# Guardrail tests
# ---------------------------------------------------------------------------

class TestGuardrailCheck:
    """Tests for the is_on_topic pre-check."""

    @pytest.mark.parametrize("msg", [
        "show me snacks",
        "what chicken deals are there",
        "I need milk",
        "help me plan dinner",
        "any coupons for yogurt",
        "healthy breakfast ideas",
        "what's on sale for pet food",
    ])
    def test_grocery_queries_allowed(self, msg):
        assert is_on_topic(msg) is True

    @pytest.mark.parametrize("msg", [
        "who is the president",
        "write me python code",
        "explain the election results",
        "what religion is best",
        "help me with my homework",
        "tell me about bitcoin investing",
        "debug my javascript",
    ])
    def test_off_topic_blocked(self, msg):
        assert is_on_topic(msg) is False

    def test_ambiguous_allowed(self):
        """Messages without clear off-topic keywords are allowed (LLM decides)."""
        assert is_on_topic("tell me something interesting") is True

    def test_mixed_grocery_and_offtopic_allowed(self):
        """If grocery keywords are present, don't block even with off-topic words."""
        assert is_on_topic("is there a deal on election day food") is True

    def test_empty_message_allowed(self):
        assert is_on_topic("") is True

    def test_recipe_queries_allowed(self):
        assert is_on_topic("recipe for chicken soup") is True


# ---------------------------------------------------------------------------
# Format deals tests
# ---------------------------------------------------------------------------

class TestFormatDeals:
    """Tests for format_deals_for_context."""

    def _make_deal(self, name="Test Deal", price="$2.99", category="Snacks") -> DealResult:
        return DealResult(
            offer_id="123",
            offer_name=name,
            offer_price=price,
            offer_description="desc",
            offer_category=category,
            offer_pgm="MF",
            score=0.8,
            sources=["keyword"],
        )

    def test_formats_single_deal(self):
        deals = [self._make_deal()]
        result = format_deals_for_context(deals)
        assert "Test Deal" in result
        assert "$2.99" in result
        assert "Snacks" in result

    def test_formats_multiple_deals(self):
        deals = [
            self._make_deal("Deal A", "$1.99"),
            self._make_deal("Deal B", "$3.49"),
        ]
        result = format_deals_for_context(deals)
        assert "1. Deal A" in result
        assert "2. Deal B" in result

    def test_empty_deals(self):
        assert format_deals_for_context([]) == "No deals found."

    def test_limits_to_max_deals(self):
        deals = [self._make_deal(f"Deal {i}") for i in range(15)]
        result = format_deals_for_context(deals, max_deals=10)
        lines = [l for l in result.split("\n") if l.strip()]
        assert len(lines) == 10

    def test_includes_matching_products(self):
        deal = self._make_deal()
        prod = MagicMock()
        prod.product_name = "Organic Almonds"
        prod.product_price = 0.0
        deal.matching_products = [prod]
        result = format_deals_for_context([deal])
        assert "Organic Almonds" in result

    def test_includes_product_prices(self):
        deal = self._make_deal()
        prod = MagicMock()
        prod.product_name = "Greek Yogurt"
        prod.product_price = 2.49
        deal.matching_products = [prod]
        result = format_deals_for_context([deal])
        assert "Greek Yogurt $2.49" in result


# ---------------------------------------------------------------------------
# Truncate history tests
# ---------------------------------------------------------------------------

class TestTruncateHistory:
    """Tests for truncate_history."""

    def test_preserves_system_message(self):
        messages = [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "msg 1"},
            {"role": "assistant", "content": "resp 1"},
            {"role": "user", "content": "msg 2"},
            {"role": "assistant", "content": "resp 2"},
        ]
        result = truncate_history(messages, max_turns=1)
        assert result[0]["role"] == "system"
        assert result[-1]["content"] == "resp 2"

    def test_keeps_last_n_turns(self):
        messages = [{"role": "system", "content": "sys"}]
        for i in range(10):
            messages.append({"role": "user", "content": f"u{i}"})
            messages.append({"role": "assistant", "content": f"a{i}"})
        result = truncate_history(messages, max_turns=3)
        # system + 6 messages (3 turns)
        assert len(result) == 7
        assert result[0]["role"] == "system"

    def test_short_history_unchanged(self):
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]
        result = truncate_history(messages, max_turns=5)
        assert len(result) == 3

    def test_no_system_message(self):
        messages = [
            {"role": "user", "content": "u1"},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "u2"},
            {"role": "assistant", "content": "a2"},
        ]
        result = truncate_history(messages, max_turns=1)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# Chat stream tests (mocked Groq)
# ---------------------------------------------------------------------------

def _make_mock_tool_response(query: str):
    """Mock a Groq response that includes a tool call."""
    tc = MagicMock()
    tc.id = "call_123"
    tc.function.name = "search_deals"
    tc.function.arguments = json.dumps({"query": query, "top_k": 8})

    choice = MagicMock()
    choice.message.tool_calls = [tc]
    choice.message.content = None
    choice.message.model_dump.return_value = {
        "role": "assistant",
        "content": None,
        "tool_calls": [{"id": "call_123", "function": {"name": "search_deals", "arguments": json.dumps({"query": query})}}],
    }

    resp = MagicMock()
    resp.choices = [choice]
    return resp


def _make_mock_stream_chunks(text: str):
    """Mock streaming chunks that yield text word by word."""
    words = text.split()
    chunks = []
    for i, word in enumerate(words):
        chunk = MagicMock()
        chunk.choices = [MagicMock()]
        chunk.choices[0].delta.content = word if i == 0 else " " + word
        chunks.append(chunk)
    return chunks


def _make_mock_direct_response(text: str):
    """Mock a Groq response with no tool call (direct text)."""
    choice = MagicMock()
    choice.message.tool_calls = None
    choice.message.content = text

    resp = MagicMock()
    resp.choices = [choice]
    return resp


class TestChatStream:
    """Tests for chat_stream with mocked Groq."""

    def test_guardrail_blocks_offtopic(self):
        """Off-topic messages get blocked without hitting LLM."""
        events = list(chat_stream(
            "who is the president",
            [],
            [], None, None,  # records/embeddings/model not needed
        ))
        types = [e["type"] for e in events]
        assert "guardrail" in types
        assert "done" in types
        assert events[0]["type"] == "guardrail"

    def test_no_client_returns_unavailable(self):
        with patch("search.chat._get_groq_client", return_value=None):
            events = list(chat_stream(
                "show me snacks",
                [],
                [], None, None,
            ))
        types = [e["type"] for e in events]
        assert "token" in types
        assert "done" in types
        assert "unavailable" in events[-1]["full_response"].lower()

    def test_tool_call_triggers_search_and_deals(self):
        mock_client = MagicMock()
        # Phase 1: return tool call
        mock_client.chat.completions.create.side_effect = [
            _make_mock_tool_response("snacks"),
            _make_mock_stream_chunks("Here are some snack deals!"),
        ]

        mock_deal = DealResult(
            offer_id="abc",
            offer_name="Chips Deal",
            offer_price="$2.99",
            offer_description="",
            offer_category="Snacks",
            offer_pgm="MF",
            score=0.9,
            sources=["keyword"],
        )

        with patch("search.chat._get_groq_client", return_value=mock_client), \
             patch("search.chat.search", return_value=[mock_deal]):
            events = list(chat_stream(
                "show me snacks",
                [],
                [], None, None,
            ))

        types = [e["type"] for e in events]
        assert "thinking" in types
        assert "deals" in types
        assert "token" in types
        assert "done" in types

    def test_direct_response_no_tool_call(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_mock_direct_response(
            "I can help with grocery shopping!"
        )

        with patch("search.chat._get_groq_client", return_value=mock_client):
            events = list(chat_stream(
                "hello",
                [],
                [], None, None,
            ))

        types = [e["type"] for e in events]
        assert "token" in types
        assert "done" in types
        full = events[-1]["full_response"]
        assert "grocery" in full.lower()

    def test_error_handling(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("API error")

        with patch("search.chat._get_groq_client", return_value=mock_client):
            events = list(chat_stream(
                "show me deals",
                [],
                [], None, None,
            ))

        types = [e["type"] for e in events]
        assert "done" in types
        assert "wrong" in events[-1]["full_response"].lower()

    def test_system_prompt_injected_when_missing(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_mock_direct_response("Hello!")

        with patch("search.chat._get_groq_client", return_value=mock_client):
            list(chat_stream("hi", [], [], None, None))

        # Check that system prompt was in the messages
        call_args = mock_client.chat.completions.create.call_args
        messages = call_args.kwargs["messages"]
        assert messages[0]["role"] == "system"
        assert "Safeway" in messages[0]["content"]

    def test_multi_tool_calls_deduplicates(self):
        """When LLM makes multiple tool calls, results should be deduplicated."""
        # Mock two tool calls (like real "healthy dinner" response: salmon, chicken)
        tc1 = MagicMock()
        tc1.id = "call_1"
        tc1.function.name = "search_deals"
        tc1.function.arguments = json.dumps({"query": "salmon"})

        tc2 = MagicMock()
        tc2.id = "call_2"
        tc2.function.name = "search_deals"
        tc2.function.arguments = json.dumps({"query": "chicken"})

        choice = MagicMock()
        choice.message.tool_calls = [tc1, tc2]
        choice.message.content = None

        phase1_resp = MagicMock()
        phase1_resp.choices = [choice]

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            phase1_resp,
            _make_mock_stream_chunks("Here are salmon and chicken deals!"),
        ]

        deal_salmon = DealResult(
            offer_id="s1", offer_name="Salmon Deal", offer_price="$9.99",
            offer_description="", offer_category="Meat & Seafood",
            offer_pgm="MF", score=0.8, sources=["keyword"],
        )
        deal_chicken = DealResult(
            offer_id="c1", offer_name="Chicken Deal", offer_price="$5.99",
            offer_description="", offer_category="Meat & Seafood",
            offer_pgm="MF", score=0.7, sources=["keyword"],
        )
        # Same deal found by both searches (should be deduped)
        deal_dup = DealResult(
            offer_id="s1", offer_name="Salmon Deal", offer_price="$9.99",
            offer_description="", offer_category="Meat & Seafood",
            offer_pgm="MF", score=0.6, sources=["fuzzy"],
        )

        search_results = [[deal_salmon], [deal_chicken, deal_dup]]

        with patch("search.chat._get_groq_client", return_value=mock_client), \
             patch("search.chat.search", side_effect=search_results):
            events = list(chat_stream("healthy dinner", [], [], None, None))

        deal_events = [e for e in events if e["type"] == "deals"]
        assert len(deal_events) == 1
        # Should have 2 unique deals (not 3)
        assert len(deal_events[0]["deals"]) == 2

    def test_tool_use_failed_fallback(self):
        """When Groq returns tool_use_failed, parse and execute the search."""
        mock_client = MagicMock()

        # Phase 1 fails with tool_use_failed (real Groq error pattern)
        error = Exception("tool_use_failed")
        error.body = {
            "error": {
                "message": "Failed to call a function.",
                "type": "invalid_request_error",
                "code": "tool_use_failed",
                "failed_generation": '<function=search_deals>query=snacks</function>',
            }
        }
        mock_client.chat.completions.create.side_effect = [
            error,
            _make_mock_stream_chunks("Here are some snack deals!"),
        ]

        mock_deal = DealResult(
            offer_id="snk1", offer_name="Pringles", offer_price="$4.99",
            offer_description="", offer_category="Snacks",
            offer_pgm="MF", score=0.9, sources=["keyword"],
        )

        with patch("search.chat._get_groq_client", return_value=mock_client), \
             patch("search.chat.search", return_value=[mock_deal]):
            events = list(chat_stream("what snacks", [], [], None, None))

        types = [e["type"] for e in events]
        assert "thinking" in types
        assert "deals" in types
        assert "done" in types
        # Should NOT have "wrong" error
        done_event = next(e for e in events if e["type"] == "done")
        assert "wrong" not in done_event["full_response"].lower()

    def test_raw_tool_call_in_content_fallback(self):
        """When LLM outputs raw function call as content, parse and execute."""
        mock_client = MagicMock()

        # Phase 1 returns content with raw function call (no tool_calls)
        choice = MagicMock()
        choice.message.tool_calls = None
        choice.message.content = '<function=search_deals>{"query": "yogurt"}</function>'
        phase1_resp = MagicMock()
        phase1_resp.choices = [choice]

        mock_client.chat.completions.create.side_effect = [
            phase1_resp,
            _make_mock_stream_chunks("Here are yogurt deals!"),
        ]

        mock_deal = DealResult(
            offer_id="y1", offer_name="Greek Yogurt", offer_price="$3.99",
            offer_description="", offer_category="Dairy",
            offer_pgm="MF", score=0.85, sources=["keyword"],
        )

        with patch("search.chat._get_groq_client", return_value=mock_client), \
             patch("search.chat.search", return_value=[mock_deal]):
            events = list(chat_stream("yogurt deals", [], [], None, None))

        types = [e["type"] for e in events]
        assert "thinking" in types
        assert "deals" in types
        assert "done" in types

    def test_streaming_tokens_collected(self):
        """Verify streaming tokens are yielded individually."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            _make_mock_tool_response("milk"),
            _make_mock_stream_chunks("Found three milk deals for you"),
        ]

        mock_deal = DealResult(
            offer_id="m1", offer_name="Milk Deal", offer_price="$2.99",
            offer_description="", offer_category="Dairy",
            offer_pgm="MF", score=0.9, sources=["keyword"],
        )

        with patch("search.chat._get_groq_client", return_value=mock_client), \
             patch("search.chat.search", return_value=[mock_deal]):
            events = list(chat_stream("milk deals", [], [], None, None))

        tokens = [e for e in events if e["type"] == "token"]
        assert len(tokens) >= 5  # "Found three milk deals for you" = 6 words
        done_event = next(e for e in events if e["type"] == "done")
        assert "Found three milk deals" in done_event["full_response"]

    def test_history_passed_to_groq(self):
        """Verify conversation history is passed to the Groq API call."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_mock_direct_response(
            "I can help you find deals!"
        )

        history = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "show me snacks"},
            {"role": "assistant", "content": "Here are some snacks!"},
        ]

        with patch("search.chat._get_groq_client", return_value=mock_client):
            list(chat_stream("healthier ones", history, [], None, None))

        call_args = mock_client.chat.completions.create.call_args
        messages = call_args.kwargs["messages"]
        # Should have system + 2 history + 1 current = 4 messages
        assert len(messages) == 4
        assert messages[-1]["content"] == "healthier ones"
        assert messages[-2]["content"] == "Here are some snacks!"


# ---------------------------------------------------------------------------
# Raw tool call extractor tests
# ---------------------------------------------------------------------------

class TestExtractRawToolCall:
    """Tests for _extract_raw_tool_call helper."""

    @pytest.mark.parametrize("content,expected", [
        ('<function=search_deals>{"query": "snacks"}</function>', "snacks"),
        ('<function=search_deals>query=snacks</function>', "snacks"),
        ('<function=search_deals>query=cat food</function>', "cat food"),
        ('search_deals({"query": "yogurt"})', "yogurt"),
        ("Here are some great deals!", None),
        ("", None),
        ("I recommend searching for milk", None),
    ])
    def test_patterns(self, content, expected):
        assert _extract_raw_tool_call(content) == expected


# ---------------------------------------------------------------------------
# Parse suggestions tests
# ---------------------------------------------------------------------------

class TestParseSuggestions:
    """Tests for _parse_suggestions helper."""

    def test_extracts_suggestions(self):
        text = "Here are some deals!\nSUGGESTIONS: Show healthier options|Any under $3?|What about drinks?"
        main, suggestions = _parse_suggestions(text)
        assert main == "Here are some deals!"
        assert suggestions == ["Show healthier options", "Any under $3?", "What about drinks?"]

    def test_no_suggestions(self):
        text = "Here are some deals for you."
        main, suggestions = _parse_suggestions(text)
        assert main == "Here are some deals for you."
        assert suggestions == []

    def test_case_insensitive_prefix(self):
        text = "Great deals!\nsuggestions: Option A|Option B"
        main, suggestions = _parse_suggestions(text)
        assert main == "Great deals!"
        assert suggestions == ["Option A", "Option B"]

    def test_empty_text(self):
        main, suggestions = _parse_suggestions("")
        assert main == ""
        assert suggestions == []

    def test_suggestions_only(self):
        text = "SUGGESTIONS: A|B|C"
        main, suggestions = _parse_suggestions(text)
        assert main == ""
        assert suggestions == ["A", "B", "C"]

    def test_multiline_before_suggestions(self):
        text = "Line 1\nLine 2\nLine 3\nSUGGESTIONS: X|Y"
        main, suggestions = _parse_suggestions(text)
        assert "Line 1" in main
        assert "Line 2" in main
        assert "Line 3" in main
        assert suggestions == ["X", "Y"]

    def test_empty_pipe_segments_ignored(self):
        text = "Deals!\nSUGGESTIONS: A||B|  |C"
        main, suggestions = _parse_suggestions(text)
        assert suggestions == ["A", "B", "C"]

    def test_inline_suggestions_same_line(self):
        """SUGGESTIONS on same line as response text (no newline before it)."""
        text = "Here are 4 chicken deals to consider. SUGGESTIONS: Show me beef|Any deals under $5?|What about seafood?"
        main, suggestions = _parse_suggestions(text)
        assert main == "Here are 4 chicken deals to consider."
        assert len(suggestions) == 3
        assert "Show me beef" in suggestions
