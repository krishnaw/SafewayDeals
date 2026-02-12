"""Query expansion via Claude Haiku for natural language grocery searches."""

from __future__ import annotations

import logging
import os
from functools import lru_cache

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a grocery search query expander. Given a natural language "
    "search query, output a comma-separated list of specific grocery product "
    "names, brands, or categories that match. Keep to 10-15 terms max. "
    "If the query is already specific product names (e.g. 'milk', 'Coca Cola', "
    "'chicken breast'), respond with just PASS — no expansion needed.\n\n"
    "Examples:\n"
    '- "protein rich" → "chicken breast, beef, steak, eggs, Greek yogurt, '
    'protein bars, salmon, tuna, turkey, pork chops, whey protein, cottage cheese"\n'
    '- "BBQ essentials" → "hot dogs, hamburger buns, ketchup, mustard, charcoal, '
    'BBQ sauce, corn on cob, ribs, coleslaw, paper plates"\n'
    '- "healthy snacks" → "almonds, granola bars, hummus, baby carrots, '
    'rice cakes, dried fruit, trail mix, yogurt, apple slices, celery"\n'
    '- "milk" → "PASS"\n'
    '- "coca cola" → "PASS"'
)


def _get_client():
    """Create an Anthropic client, or return None if key is missing."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        # Try loading from .env file
        try:
            from pathlib import Path

            env_path = Path(__file__).resolve().parent.parent / ".env"
            if env_path.exists():
                for line in env_path.read_text().splitlines():
                    line = line.strip()
                    if line.startswith("ANTHROPIC_API_KEY=") and not line.startswith("#"):
                        api_key = line.split("=", 1)[1].strip().strip("\"'")
                        break
        except Exception:
            pass

    if not api_key:
        return None

    try:
        import anthropic

        return anthropic.Anthropic(api_key=api_key)
    except Exception:
        logger.debug("Failed to create Anthropic client", exc_info=True)
        return None


@lru_cache(maxsize=128)
def _cached_expand(query: str) -> str | None:
    """Call Claude Haiku to expand the query. Returns expanded terms or None."""
    client = _get_client()
    if client is None:
        return None

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": query}],
            timeout=3.0,
        )
        text = response.content[0].text.strip()
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
    - Claude returns PASS (query is already specific)
    - Any error occurs (graceful fallback)
    """
    # Short-circuit: single-word queries don't need expansion
    if len(query.split()) <= 1:
        return None

    return _cached_expand(query.strip().lower())
