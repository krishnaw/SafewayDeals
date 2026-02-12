"""Query expansion via Groq (Llama) for natural language grocery searches."""

from __future__ import annotations

import logging
import os
from functools import lru_cache

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a grocery store search query expander for a Safeway deals/coupons database. "
    "Given a natural language search query, output ONLY a comma-separated list of specific "
    "product names or brands. Keep to 8-12 terms max. Output ONLY the list, nothing else.\n\n"
    "IMPORTANT: Only suggest products that fall within these store categories:\n"
    "- Beverages (juice, soda, water, coffee, tea, sports drinks)\n"
    "- Bread & Bakery (bread, rolls, tortillas, baked goods)\n"
    "- Breakfast & Cereal (cereal, oatmeal, pancake mix, syrup)\n"
    "- Canned Goods & Soups (canned vegetables, soup, broth, beans)\n"
    "- Condiments, Spices & Bake (sauces, ketchup, mustard, spices, baking)\n"
    "- Cookies, Snacks & Candy (chips, crackers, cookies, nuts, candy)\n"
    "- Dairy, Eggs & Cheese (milk, yogurt, cheese, eggs, butter)\n"
    "- Deli (deli meats, prepared meals, sandwiches)\n"
    "- Frozen Foods (frozen pizza, ice cream, frozen meals, waffles)\n"
    "- Fruits & Vegetables (fresh produce, salads)\n"
    "- Grains, Pasta & Sides (pasta, rice, mac & cheese)\n"
    "- International Cuisine (Asian sauces, Mexican foods, ethnic items)\n"
    "- Meat & Seafood (chicken, beef, pork, salmon, shrimp)\n"
    "- Paper, Cleaning & Home (paper towels, detergent, cleaning spray, trash bags)\n"
    "- Personal Care & Health (medicine, vitamins, shampoo, lotion, oral care)\n"
    "- Pet Care (dog food, cat food, treats, litter)\n"
    "- Baby Care (diapers, wipes, baby food, formula)\n"
    "- Wine, Beer & Spirits (beer, wine, vodka, whiskey, rum)\n\n"
    "Do NOT suggest items outside these categories (no balloons, decorations, electronics, "
    "clothing, toys, etc.).\n\n"
    "If the query is already a specific product name (e.g. 'milk', 'Coca Cola', "
    "'chicken breast'), respond with just PASS.\n\n"
    "Examples:\n"
    '- "protein rich" → chicken breast, beef, steak, eggs, Greek yogurt, '
    'protein bars, salmon, tuna, turkey, cottage cheese\n'
    '- "BBQ essentials" → charcoal, BBQ sauce, ketchup, mustard, hot dogs, '
    'hamburger buns, ribs, corn, baked beans, paper plates\n'
    '- "healthy snacks" → almonds, granola bars, hummus, rice cakes, '
    'dried fruit, trail mix, yogurt, celery\n'
    '- "party supplies" → chips, salsa, soda, beer, paper plates, '
    'cups, napkins, ice cream, frozen pizza\n'
    '- "milk" → PASS\n'
    '- "coca cola" → PASS'
)

_MODEL = "llama-3.1-8b-instant"


def _get_api_key() -> str | None:
    """Get Groq API key from env or .env file."""
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        try:
            from pathlib import Path

            env_path = Path(__file__).resolve().parent.parent / ".env"
            if env_path.exists():
                for line in env_path.read_text().splitlines():
                    line = line.strip()
                    if line.startswith("GROQ_API_KEY=") and not line.startswith("#"):
                        api_key = line.split("=", 1)[1].strip().strip("\"'")
                        break
        except Exception:
            pass

    return api_key or None


def _get_client():
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


@lru_cache(maxsize=128)
def _cached_expand(query: str) -> str | None:
    """Call Groq Llama to expand the query. Returns expanded terms or None."""
    client = _get_client()
    if client is None:
        return None

    try:
        response = client.chat.completions.create(
            model=_MODEL,
            max_tokens=200,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": query},
            ],
            timeout=3.0,
        )
        text = response.choices[0].message.content.strip()
        if text.upper() == "PASS":
            return None
        return text
    except Exception:
        logger.debug("Query expansion failed for %r", query, exc_info=True)
        return None


def expand_query(query: str) -> str | None:
    """Expand a natural language query into concrete grocery search terms.

    Returns comma-separated product keywords, or None if:
    - Query is a single word (existing pipeline handles it)
    - LLM returns PASS (query is already specific)
    - Any error occurs (graceful fallback)
    """
    # Short-circuit: single-word queries don't need expansion
    if len(query.split()) <= 1:
        return None

    return _cached_expand(query.strip().lower())
