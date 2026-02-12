"""Multi-turn conversational deal finder with Groq Llama streaming + tool use."""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Generator

import numpy as np

from .expand import _get_api_key
from .index import SearchRecord
from .search import DealResult, search

logger = logging.getLogger(__name__)


def _days_until_expiry(end_date_str: str) -> int | None:
    """Return days until deal expires, or None if no date."""
    if not end_date_str:
        return None
    try:
        end_ms = int(end_date_str)
        now_ms = int(time.time() * 1000)
        diff_days = (end_ms - now_ms) / (1000 * 60 * 60 * 24)
        return max(0, int(diff_days))
    except (ValueError, TypeError):
        return None


def _filter_by_expiry(deals: list[DealResult], expiry: str, deals_data: list[dict]) -> list[DealResult]:
    """Filter DealResults by expiry window using raw deals_data for endDate."""
    max_days = {"today": 0, "week": 7, "month": 30}.get(expiry)
    if max_days is None:
        return deals
    # Build offer_id -> endDate lookup
    end_dates = {d.get("offerId", ""): d.get("endDate", "") for d in deals_data}
    filtered = []
    for deal in deals:
        end_date = end_dates.get(deal.offer_id, "")
        days = _days_until_expiry(end_date)
        if days is not None and days <= max_days:
            filtered.append(deal)
    return filtered

_MODEL = "llama-3.1-8b-instant"

SYSTEM_PROMPT = (
    "You are a helpful Safeway grocery deals assistant. Your ONLY purpose is to help "
    "customers find grocery deals, coupons, products, and plan meals or shopping trips.\n\n"
    "STRICT RULES:\n"
    "1. ONLY answer questions about grocery products, deals, coupons, shopping, meal planning, "
    "recipes, and food preparation.\n"
    "2. REFUSE any question about politics, news, coding, math, science, history, celebrities, "
    "sports scores, medical/legal advice, or general knowledge. Respond with: "
    '"I\'m your Safeway deals assistant — I can only help with grocery shopping, deals, and meal ideas!"\n'
    "3. You do NOT know current deals from memory. ALWAYS use the search_deals tool to look up "
    "deals before answering about available products or prices.\n"
    "4. When a user refines their request (e.g. 'healthier ones', 'under $5', 'something else'), "
    "infer what they mean from conversation history and search accordingly.\n"
    "5. Present deals in a friendly, concise way. Mention the deal name, price, and category.\n"
    "6. Keep responses SHORT — 2-4 sentences max, plus deal listings.\n\n"
    "Available store categories: Beverages, Bread & Bakery, Breakfast & Cereal, "
    "Canned Goods & Soups, Condiments Spices & Bake, Cookies Snacks & Candy, "
    "Dairy Eggs & Cheese, Deli, Frozen Foods, Fruits & Vegetables, "
    "Grains Pasta & Sides, International Cuisine, Meat & Seafood, "
    "Paper Cleaning & Home, Personal Care & Health, Pet Care, Baby Care, "
    "Wine Beer & Spirits.\n\n"
    "CRITICAL — How to use search_deals:\n"
    "- ALWAYS search for SPECIFIC PRODUCT NAMES, never abstract concepts.\n"
    "- WRONG: search_deals('healthy dinner') or search_deals('something for breakfast')\n"
    "- RIGHT: search_deals('chicken'), search_deals('salmon'), search_deals('salad')\n"
    "- For broad/thematic queries like 'plan a dinner' or 'healthy meal', make MULTIPLE "
    "search_deals calls with specific product terms. Example: for 'healthy dinner' call "
    "search_deals('chicken'), search_deals('salmon'), search_deals('salad'), search_deals('vegetables').\n"
    "- Keep queries to 1-2 words — product names or brands work best.\n"
    "- For EXPIRING deals: use query='*' with the expiry filter. Example: "
    "search_deals(query='*', expiry='week') for deals expiring this week, "
    "search_deals(query='*', expiry='today') for deals expiring today.\n"
    "- When the user specifies a price limit (e.g. 'under $3', 'less than $5'), search for the "
    "products first, then ONLY include deals where the product price is at or below that limit. "
    "The product prices are shown next to product names in the search results.\n\n"
    "After EVERY response, add a line starting with 'SUGGESTIONS:' followed by 2-3 short "
    "follow-up questions the user might ask, separated by '|'. These help guide the conversation.\n"
    "Example: SUGGESTIONS: Show me healthier options|Any deals under $3?|What about drinks?\n"
    "IMPORTANT: Always include the SUGGESTIONS line as the very last line of your response."
)

_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "search_deals",
        "description": "Search current Safeway deals and coupons. Returns matching deals with names, prices, and categories. Can also filter by expiry window.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query — use short, specific terms like 'chicken', 'yogurt', 'laundry detergent'. Use '*' to match all deals (useful with expiry filter).",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Max results to return (default 8)",
                    "default": 8,
                },
                "expiry": {
                    "type": "string",
                    "enum": ["today", "week", "month"],
                    "description": "Filter deals expiring within this window: 'today', 'week' (7 days), or 'month' (30 days). Only use when user asks about expiring/ending deals.",
                },
            },
            "required": ["query"],
        },
    },
}

# Off-topic keyword lists for pre-check guardrail
_OFF_TOPIC_KEYWORDS = {
    "president", "election", "democrat", "republican", "trump", "biden",
    "congress", "senate", "politics", "political",
    "python", "javascript", "code", "programming", "algorithm", "debug",
    "religion", "god", "church", "bible", "quran",
    "stock", "crypto", "bitcoin", "invest",
    "homework", "essay", "calculus", "physics",
    "celebrity", "kardashian", "movie", "netflix",
    "weather forecast",
}

_GROCERY_KEYWORDS = {
    "grocery", "food", "meal", "recipe", "cook", "bake", "eat", "drink",
    "snack", "breakfast", "lunch", "dinner", "deal", "coupon", "save",
    "price", "buy", "shop", "safeway", "produce", "meat", "dairy", "expiring", "expire", "expiry",
    "bread", "cereal", "frozen", "canned", "organic", "healthy",
    "chicken", "beef", "pork", "fish", "salmon", "shrimp",
    "milk", "cheese", "yogurt", "egg", "butter",
    "fruit", "vegetable", "salad", "juice", "soda", "water", "coffee", "tea",
    "beer", "wine", "spirits", "pet", "baby", "diaper", "formula",
    "cleaning", "detergent", "paper towel", "soap",
    "vitamin", "medicine", "shampoo", "toothpaste",
    "chocolate", "candy", "chips", "crackers", "cookies",
    "pasta", "rice", "soup", "sauce", "condiment", "spice",
    "ice cream", "pizza", "waffles",
}


def is_on_topic(message: str) -> bool:
    """Quick pre-check: reject obviously off-topic messages.

    Returns True if the message seems grocery-related or ambiguous (let LLM handle).
    Returns False only for clearly off-topic messages.
    """
    words = set(message.lower().split())
    has_off_topic = bool(words & _OFF_TOPIC_KEYWORDS)
    has_grocery = bool(words & _GROCERY_KEYWORDS)

    # Only reject when off-topic is clear AND no grocery context
    if has_off_topic and not has_grocery:
        return False
    return True


def _get_groq_client():
    """Create a Groq client, or return None if key is missing."""
    api_key = _get_api_key()
    if not api_key:
        return None
    try:
        from groq import Groq
        return Groq(api_key=api_key)
    except Exception:
        logger.debug("Failed to create Groq client", exc_info=True)
        return None


def format_deals_for_context(deals: list[DealResult], max_deals: int = 10) -> str:
    """Format deal results into compact text for LLM context."""
    if not deals:
        return "No deals found."

    lines = []
    for i, deal in enumerate(deals[:max_deals]):
        products_str = ""
        if deal.matching_products:
            parts = []
            for p in deal.matching_products[:3]:
                if p.product_name:
                    price_str = f" ${p.product_price:.2f}" if p.product_price else ""
                    parts.append(f"{p.product_name}{price_str}")
            if parts:
                products_str = f" | Products: {', '.join(parts)}"
        lines.append(
            f"{i+1}. {deal.offer_name} — {deal.offer_price} "
            f"[{deal.offer_category}]{products_str}"
        )
    return "\n".join(lines)


def truncate_history(messages: list[dict], max_turns: int = 10) -> list[dict]:
    """Keep system message + last N user/assistant turn pairs."""
    if len(messages) <= 1 + max_turns * 2:
        return messages

    system = [m for m in messages if m["role"] == "system"]
    non_system = [m for m in messages if m["role"] != "system"]
    kept = non_system[-(max_turns * 2):]
    return system + kept


def _make_done_event(full_response: str) -> dict:
    """Create a done event, extracting suggestions if present."""
    clean, suggestions = _parse_suggestions(full_response)
    event = {"type": "done", "full_response": clean}
    if suggestions:
        event["suggestions"] = suggestions
    return event


def _parse_suggestions(text: str) -> tuple[str, list[str]]:
    """Split response text into (main_response, suggestions_list).

    Finds 'SUGGESTIONS:' anywhere in the text (may be inline or on its own line)
    and extracts pipe-separated suggestions after it.
    """
    idx = text.upper().rfind("SUGGESTIONS:")
    if idx >= 0:
        before = text[:idx].strip()
        after = text[idx + len("SUGGESTIONS:"):].strip()
        suggestions = [s.strip() for s in after.split("|") if s.strip()]
        return before, suggestions
    return text.strip(), []


def _extract_raw_tool_call(content: str) -> str | None:
    """Detect if LLM output a raw function call as text and extract the query.

    Llama 3.1 8B sometimes outputs function calls as text instead of using
    the tool mechanism. Catches patterns like:
    - <function=search_deals>{"query": "snacks"}</function>
    - <function=search_deals>query=snacks</function>
    - search_deals(query="snacks")
    """
    import re

    # Pattern: <function=search_deals>{"query": "..."}</function>
    m = re.search(r'search_deals[>\(]\s*\{?["\']?query["\']?\s*[:=]\s*["\']([^"\']+)["\']', content)
    if m:
        return m.group(1)

    # Pattern: <function=search_deals>query=VALUE</function> (no quotes, may have spaces)
    m = re.search(r'search_deals>.*?query\s*=\s*(.+?)(?:</function>|$)', content)
    if m:
        return m.group(1).strip("\"' ")

    # Pattern: {"query": "..."} anywhere in content that looks like a function call
    if "search_deals" in content:
        m = re.search(r'"query"\s*:\s*"([^"]+)"', content)
        if m:
            return m.group(1)

    return None


def chat_stream(
    message: str,
    history: list[dict],
    records: list[SearchRecord],
    embeddings: np.ndarray,
    model,
    deals_data: list[dict] | None = None,
) -> Generator[dict, None, None]:
    """Stream chat response as SSE-ready event dicts.

    Yields dicts with 'type' key:
    - {"type": "guardrail", "message": "..."} — off-topic rejection
    - {"type": "thinking"} — searching deals indicator
    - {"type": "deals", "deals": [...]} — deal results (as DealResult dicts)
    - {"type": "token", "content": "..."} — streaming text token
    - {"type": "done", "full_response": "..."} — final complete response
    """
    # Pre-check guardrail
    if not is_on_topic(message):
        refusal = "I'm your Safeway deals assistant — I can only help with grocery shopping, deals, and meal ideas!"
        yield {"type": "guardrail", "message": refusal}
        yield {"type": "done", "full_response": refusal}
        return

    client = _get_groq_client()
    if client is None:
        error_msg = "Chat is currently unavailable — please try again later."
        yield {"type": "token", "content": error_msg}
        yield {"type": "done", "full_response": error_msg}
        return

    # Build messages: ensure system prompt + truncated history + current message
    messages = truncate_history(history)
    if not messages or messages[0].get("role") != "system":
        messages.insert(0, {"role": "system", "content": SYSTEM_PROMPT})
    messages.append({"role": "user", "content": message})

    try:
        # Phase 1: Non-streaming call to check for tool use
        try:
            response = client.chat.completions.create(
                model=_MODEL,
                max_tokens=500,
                messages=messages,
                tools=[_SEARCH_TOOL],
                tool_choice="auto",
                timeout=8.0,
            )
            choice = response.choices[0]
            tool_calls = choice.message.tool_calls
        except Exception as tool_err:
            # Groq returns 400 tool_use_failed when Llama outputs a malformed tool call.
            # Extract the query from the failed_generation and execute manually.
            tool_calls = None
            choice = None
            failed_gen = getattr(tool_err, 'body', {})
            if isinstance(failed_gen, dict):
                failed_gen = failed_gen.get('error', {}).get('failed_generation', '')
            else:
                failed_gen = str(tool_err)
            raw_query = _extract_raw_tool_call(str(failed_gen))
            if raw_query:
                yield {"type": "thinking"}
                hits = search(raw_query, records, embeddings, model, top_k=8)
                if hits:
                    yield {"type": "deals", "deals": hits}
                deal_context = format_deals_for_context(hits)
                count = len(hits)
                messages.append({"role": "assistant", "content": f"I found {count} deal(s) for '{raw_query}'."})
                messages.append({"role": "user", "content": (
                    f"The customer can see the {count} deal card(s) above. "
                    "Write a 1-sentence summary ONLY. "
                    "Do NOT repeat deal names, prices, or product details — the cards show that. "
                    "Do NOT invent or hallucinate any products or prices. "
                    "End with SUGGESTIONS: line."
                )})
                stream = client.chat.completions.create(
                    model=_MODEL,
                    max_tokens=500,
                    messages=messages,
                    stream=True,
                    timeout=8.0,
                )
                full_response = []
                for chunk in stream:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        full_response.append(delta.content)
                        yield {"type": "token", "content": delta.content}
                yield _make_done_event("".join(full_response))
                return
            else:
                raise  # Re-raise if we can't parse

        if tool_calls:
            # Execute search tool calls
            all_deals: list[DealResult] = []
            expiry_filter = None
            for tc in tool_calls:
                if tc.function.name == "search_deals":
                    args = json.loads(tc.function.arguments)
                    query = args.get("query", "")
                    top_k = args.get("top_k", 8)
                    expiry_filter = args.get("expiry")

                    yield {"type": "thinking"}

                    if query == "*":
                        # Wildcard: return all deals (for expiry-only queries)
                        from .index import load_records as _lr
                        all_offer_ids = {rec.offer_id for rec in records}
                        for oid in list(all_offer_ids)[:200]:
                            rec = next(r for r in records if r.offer_id == oid)
                            all_deals.append(DealResult(
                                offer_id=oid,
                                offer_name=rec.offer_name,
                                offer_price=rec.offer_price,
                                offer_description=rec.offer_description,
                                offer_category=rec.offer_category,
                                offer_pgm=rec.offer_pgm,
                                score=1.0,
                                sources=["filter"],
                            ))
                    else:
                        hits = search(query, records, embeddings, model, top_k=top_k)
                        all_deals.extend(hits)

            # Deduplicate by offer_id, keep best score
            seen: dict[str, DealResult] = {}
            for deal in all_deals:
                if deal.offer_id not in seen or deal.score > seen[deal.offer_id].score:
                    seen[deal.offer_id] = deal
            unique_deals = sorted(seen.values(), key=lambda d: d.score, reverse=True)

            # Apply expiry filter if requested
            if expiry_filter and deals_data:
                unique_deals = _filter_by_expiry(unique_deals, expiry_filter, deals_data)

            # Yield deal results for frontend rendering
            if unique_deals:
                yield {
                    "type": "deals",
                    "deals": unique_deals,  # server.py will enrich these
                }

            # Phase 2a: Stream response with deal context
            deal_context = format_deals_for_context(unique_deals)

            # Add tool call and result to messages for context
            # Manually construct the assistant message (model_dump() may not round-trip)
            assistant_msg = {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in tool_calls
                ],
            }
            messages.append(assistant_msg)
            for tc in tool_calls:
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": deal_context,
                })
            # Instruct LLM to keep it brief — deal cards are shown visually
            count = len(unique_deals)
            messages.append({
                "role": "user",
                "content": (
                    f"The customer can see the {count} deal card(s) above. "
                    "Write a 1-sentence summary ONLY (e.g. 'Here are {count} dairy deals!'). "
                    "Do NOT repeat deal names, prices, or product details — the cards show that. "
                    "Do NOT invent or hallucinate any products or prices. "
                    "End with SUGGESTIONS: line."
                ),
            })

            # Stream the final response
            stream = client.chat.completions.create(
                model=_MODEL,
                max_tokens=500,
                messages=messages,
                stream=True,
                timeout=8.0,
            )

            full_response = []
            for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    full_response.append(delta.content)
                    yield {"type": "token", "content": delta.content}

            yield _make_done_event("".join(full_response))

        else:
            # Phase 2b: No tool call — check if LLM output a raw function call as text
            # (Llama 3.1 8B sometimes does this instead of using the tool mechanism)
            content = choice.message.content or ""

            raw_query = _extract_raw_tool_call(content)
            if raw_query:
                # LLM tried to call search_deals as text — execute it properly
                yield {"type": "thinking"}
                hits = search(raw_query, records, embeddings, model, top_k=8)

                if hits:
                    yield {"type": "deals", "deals": hits}

                deal_context = format_deals_for_context(hits)
                count = len(hits)
                messages.append({"role": "assistant", "content": f"I found {count} deal(s) for '{raw_query}'."})
                messages.append({"role": "user", "content": (
                    f"The customer can see the {count} deal card(s) above. "
                    "Write a 1-sentence summary ONLY. "
                    "Do NOT repeat deal names, prices, or product details — the cards show that. "
                    "Do NOT invent or hallucinate any products or prices. "
                    "End with SUGGESTIONS: line."
                )})

                stream = client.chat.completions.create(
                    model=_MODEL,
                    max_tokens=500,
                    messages=messages,
                    stream=True,
                    timeout=8.0,
                )
                full_response = []
                for chunk in stream:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        full_response.append(delta.content)
                        yield {"type": "token", "content": delta.content}
                yield _make_done_event("".join(full_response))

            elif content:
                # Direct text response — stream it token-by-token
                words = content.split(" ")
                full_response = []
                for i, word in enumerate(words):
                    token = word if i == 0 else " " + word
                    full_response.append(token)
                    yield {"type": "token", "content": token}

                yield _make_done_event("".join(full_response))
            else:
                fallback = "I'm not sure how to help with that. Try asking about grocery deals or meal ideas!"
                yield {"type": "token", "content": fallback}
                yield {"type": "done", "full_response": fallback}

    except Exception:
        logger.debug("Chat stream error", exc_info=True)
        error = "Something went wrong — please try again."
        yield {"type": "token", "content": error}
        yield {"type": "done", "full_response": error}
