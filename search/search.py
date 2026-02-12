"""Three search modes: keyword, fuzzy, and semantic — plus unified deal-centric search."""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import numpy as np
from rapidfuzz import fuzz, process

from .index import SearchRecord

# Field weights for keyword scoring — higher = more relevant match location
_OFFER_NAME_WEIGHT = 3.0
_PRODUCT_NAME_WEIGHT = 2.0
_DESCRIPTION_WEIGHT = 1.0
_OTHER_FIELD_WEIGHT = 0.5
_WHOLE_WORD_BONUS = 1.5

# ---------------------------------------------------------------------------
# Module-level caches — populated once per record set, reused across queries
# ---------------------------------------------------------------------------
_cached_records_id: int | None = None
_offer_names_list: list[str] = []
_product_names_list: list[str] = []
_offer_names_lower: list[str] = []
_product_names_lower: list[str] = []
_offer_product_counts: dict[str, int] = {}
_rec_to_idx: dict[int, int] = {}
_corpus_words: set[str] = set()


def _ensure_caches(records: list[SearchRecord]) -> None:
    """Build or reuse module-level caches for the given record set."""
    global _cached_records_id, _offer_names_list, _product_names_list
    global _offer_names_lower, _product_names_lower
    global _offer_product_counts, _rec_to_idx, _corpus_words

    rid = id(records)
    if _cached_records_id == rid:
        return
    _cached_records_id = rid
    _offer_names_list = [rec.offer_name for rec in records]
    _product_names_list = [rec.product_name for rec in records]
    _offer_names_lower = [n.lower() for n in _offer_names_list]
    _product_names_lower = [n.lower() for n in _product_names_list]
    _rec_to_idx = {id(rec): i for i, rec in enumerate(records)}
    counts: dict[str, int] = {}
    for rec in records:
        if rec.product_name:
            counts[rec.offer_id] = counts.get(rec.offer_id, 0) + 1
    _offer_product_counts = counts
    words = set()
    for rec in records:
        words.update(rec.search_text.lower().split())
    _corpus_words = words


def keyword_search(
    query: str, records: list[SearchRecord], top_k: int = 20
) -> list[tuple[SearchRecord, float]]:
    """Case-insensitive keyword search with field-weighted scoring.

    All query words must appear in search_text. Score is based on WHERE each
    word matches (offer_name > product_name > description > other) with a
    bonus for whole-word matches vs substring matches.
    Returns (record, score) sorted by score descending, normalized 0–1.

    Expects records to have pre-lowered fields (_stl, _onl, _pnl, etc.)
    set by index._prepare_records_for_search().
    """
    words = query.lower().split()
    if not words:
        return []

    max_possible = len(words) * _OFFER_NAME_WEIGHT * _WHOLE_WORD_BONUS

    # Pre-compile regex patterns once per word (not per record)
    patterns = [re.compile(r"\b" + re.escape(w) + r"\b") for w in words]

    results: list[tuple[SearchRecord, float]] = []
    for rec in records:
        # Use pre-lowered search_text (falls back to .lower() if not prepared)
        text = getattr(rec, "_stl", None) or rec.search_text.lower()
        if not all(w in text for w in words):
            continue

        total_score = 0.0
        for w, pattern in zip(words, patterns):
            best = 0.0

            # Weighted fields — use pre-lowered attributes
            for field_text, weight in (
                (getattr(rec, "_onl", None) or rec.offer_name.lower(), _OFFER_NAME_WEIGHT),
                (getattr(rec, "_pnl", None) or rec.product_name.lower(), _PRODUCT_NAME_WEIGHT),
                (getattr(rec, "_odl", None) or rec.offer_description.lower(), _DESCRIPTION_WEIGHT),
            ):
                if w in field_text:
                    bonus = _WHOLE_WORD_BONUS if pattern.search(field_text) else 1.0
                    best = max(best, weight * bonus)

            # Other fields (category, department, shelf)
            for field_text in (
                getattr(rec, "_ocl", None) or rec.offer_category.lower(),
                getattr(rec, "_pdl", None) or rec.product_department.lower(),
                getattr(rec, "_psl", None) or rec.product_shelf.lower(),
            ):
                if w in field_text:
                    bonus = _WHOLE_WORD_BONUS if pattern.search(field_text) else 1.0
                    best = max(best, _OTHER_FIELD_WEIGHT * bonus)

            total_score += best

        results.append((rec, total_score / max_possible))

    results.sort(key=lambda x: x[1], reverse=True)
    return results[:top_k]


def fuzzy_search(
    query: str,
    records: list[SearchRecord],
    threshold: int = 60,
    top_k: int = 20,
) -> list[tuple[SearchRecord, float]]:
    """Fuzzy string match against offer_name and product_name. Handles typos.
    Matches against each field separately and takes the best score per record.
    Uses cached name lists for speed."""
    _ensure_caches(records)
    query_lower = query.lower()

    # partial_ratio is 2-3x faster than WRatio while retaining good typo recovery.
    # processor=None skips redundant lowercasing (we pre-lowered the lists and query).
    offer_matches = process.extract(
        query_lower, _offer_names_lower, scorer=fuzz.partial_ratio,
        limit=top_k * 2, score_cutoff=threshold, processor=None
    )
    product_matches = process.extract(
        query_lower, _product_names_lower, scorer=fuzz.partial_ratio,
        limit=top_k * 2, score_cutoff=threshold, processor=None
    )

    # Merge: best score per record index
    best_scores: dict[int, float] = {}
    for _, score, idx in offer_matches:
        best_scores[idx] = max(best_scores.get(idx, 0), score)
    for _, score, idx in product_matches:
        best_scores[idx] = max(best_scores.get(idx, 0), score)

    results = [(records[idx], score) for idx, score in best_scores.items()]
    results.sort(key=lambda x: x[1], reverse=True)
    return results[:top_k]


def semantic_search(
    query: str,
    records: list[SearchRecord],
    embeddings: np.ndarray,
    model,
    top_k: int = 20,
) -> list[tuple[SearchRecord, float]]:
    """Encode query and find closest records by cosine similarity.
    Returns (record, similarity_score) sorted by score descending.
    Uses argpartition for O(n) top-k instead of full sort."""
    query_embedding = model.encode(
        [query], convert_to_numpy=True, normalize_embeddings=True
    )

    # Cosine similarity (embeddings already normalized)
    similarities = (embeddings @ query_embedding.T).flatten()

    # argpartition is O(n) vs argsort O(n log n) — much faster for large n
    k = min(top_k, len(similarities))
    top_indices = np.argpartition(similarities, -k)[-k:]
    # Sort just the top-k by score (tiny sort)
    top_indices = top_indices[np.argsort(similarities[top_indices])[::-1]]

    return [(records[idx], float(similarities[idx])) for idx in top_indices]


@dataclass
class DealResult:
    """A deal surfaced by search, with the matching products that caused it to appear."""
    offer_id: str
    offer_name: str
    offer_price: str
    offer_description: str
    offer_category: str
    offer_pgm: str
    score: float
    sources: list[str]
    matching_products: list[SearchRecord] = field(default_factory=list)


# Thread pool reused across searches (avoids thread creation overhead)
_executor = ThreadPoolExecutor(max_workers=3)


def search(
    query: str,
    records: list[SearchRecord],
    embeddings: np.ndarray,
    model,
    top_k: int = 20,
) -> list[DealResult]:
    """Run all three search modes concurrently, then group matched records by offer_id.

    Searches across both deal-level and product-level records, but returns
    unique deals. Each deal includes the products that matched the search.
    """
    _ensure_caches(records)

    # Run all three modes concurrently — large fetch_k to avoid missing matches
    fetch_k = max(top_k * 10, 500)
    kw_future = _executor.submit(keyword_search, query, records, fetch_k)
    fz_future = _executor.submit(fuzzy_search, query, records, 60, fetch_k)
    sm_future = _executor.submit(semantic_search, query, records, embeddings, model, fetch_k)

    kw_results = kw_future.result()
    fz_results = fz_future.result()
    sm_results = sm_future.result()

    # Track keyword-matched products per offer (for accurate density)
    kw_product_counts: dict[str, int] = {}
    for rec, _ in kw_results:
        if rec.product_name:
            kw_product_counts[rec.offer_id] = kw_product_counts.get(rec.offer_id, 0) + 1

    # Track fuzzy-matched products (score >= 80) for typo-query density
    fz_product_counts: dict[str, int] = {}
    for rec, score in fz_results:
        if rec.product_name and score >= 80:
            fz_product_counts[rec.offer_id] = fz_product_counts.get(rec.offer_id, 0) + 1

    # Gate: if no keyword matches, no strong fuzzy matches (score >= 80),
    # and no query word appears in the corpus, the query is gibberish.
    has_any_kw = bool(kw_results)
    has_strong_fuzzy = any(score >= 80 for _, score in fz_results)
    query_words_set = set(query.lower().split())
    has_corpus_word = bool(query_words_set & _corpus_words)
    if not has_any_kw and not has_strong_fuzzy and not has_corpus_word:
        return []

    # Collect per-mode scores for each record (use cached rec_to_idx)
    mode_scores: dict[int, dict[str, float]] = {}

    for rec, score in kw_results:
        idx = _rec_to_idx[id(rec)]
        ms = mode_scores.setdefault(idx, {})
        ms["keyword"] = max(ms.get("keyword", 0.0), score)

    for rec, score in fz_results:
        idx = _rec_to_idx[id(rec)]
        ms = mode_scores.setdefault(idx, {})
        ms["fuzzy"] = max(ms.get("fuzzy", 0.0), score / 100.0)

    for rec, score in sm_results:
        idx = _rec_to_idx[id(rec)]
        ms = mode_scores.setdefault(idx, {})
        ms["semantic"] = max(ms.get("semantic", 0.0), score)

    # Composite scoring: weighted combination + multi-source bonus
    record_hits: dict[int, tuple[float, set[str]]] = {}
    for idx, scores in mode_scores.items():
        kw = scores.get("keyword", 0.0)
        fz = scores.get("fuzzy", 0.0)
        sm = scores.get("semantic", 0.0)

        # Cap fuzzy to keyword score when both matched — fuzzy is for typos
        # (when keyword=0), not for inflating exact substring matches.
        if kw > 0 and fz > 0:
            fz = min(fz, kw)

        composite = 0.50 * kw + 0.25 * fz + 0.25 * sm
        # Bonus for being found by multiple modes (+0.1 per extra, cap +0.2)
        composite += min((len(scores) - 1) * 0.1, 0.2)
        # Semantic-only discount: reduce score when no keyword/fuzzy confirmation
        if "keyword" not in scores and "fuzzy" not in scores:
            composite *= 0.5
        record_hits[idx] = (composite, set(scores.keys()))

    # Group by offer_id -> DealResult
    deals: dict[str, DealResult] = {}
    for idx, (score, sources) in record_hits.items():
        rec = records[idx]
        oid = rec.offer_id

        if oid not in deals:
            deals[oid] = DealResult(
                offer_id=oid,
                offer_name=rec.offer_name,
                offer_price=rec.offer_price,
                offer_description=rec.offer_description,
                offer_category=rec.offer_category,
                offer_pgm=rec.offer_pgm,
                score=score,
                sources=list(sources),
            )
        else:
            deal = deals[oid]
            deal.score = max(deal.score, score)
            for s in sources:
                if s not in deal.sources:
                    deal.sources.append(s)

        # Add matching product (skip offer-only records with no product)
        if rec.product_name:
            deals[oid].matching_products.append(rec)

    # Match density factor based on KEYWORD matches only (semantic is too broad).
    # Penalizes deals where "chocolate" matches 2 products out of 20.
    # Skip entirely when keyword found nothing (typo queries) — density is
    # meaningless when zero keyword matches exist and would unfairly penalize
    # all deals that have products while leaving offer-only records unaffected.
    has_any_kw = bool(kw_product_counts)
    has_any_fz = bool(fz_product_counts)
    if has_any_kw:
        for deal in deals.values():
            total = _offer_product_counts.get(deal.offer_id, 0)
            if total > 0:
                kw_matched = kw_product_counts.get(deal.offer_id, 0)
                if kw_matched > 0:
                    density = kw_matched / total
                else:
                    density = 0.1
                deal.score *= 0.3 + 0.7 * density
    elif has_any_fz:
        # Typo queries: keyword finds nothing but fuzzy finds matches.
        # Use fuzzy-matched product density to penalize deals where only
        # a tiny fraction of products matched the fuzzy query.
        for deal in deals.values():
            total = _offer_product_counts.get(deal.offer_id, 0)
            if total > 0:
                fz_matched = fz_product_counts.get(deal.offer_id, 0)
                if fz_matched > 0:
                    density = fz_matched / total
                else:
                    density = 0.1
                deal.score *= 0.3 + 0.7 * density

    # Offer-name relevance boost: deals whose name matches the query are more
    # relevant than deals surfaced only through product-level matches.
    # Uses both exact substring AND fuzzy matching (handles typos like "choclate").
    query_lower = query.lower()
    query_words = query_lower.split()
    for deal in deals.values():
        name_lower = deal.offer_name.lower()
        if any(w in name_lower for w in query_words):
            deal.score *= 1.2
        elif fuzz.partial_ratio(query_lower, name_lower) >= 80:
            deal.score *= 1.2

    results = sorted(deals.values(), key=lambda d: d.score, reverse=True)
    results = results[:top_k]

    # Adaptive score cutoff: tighter when results are weak (low top score),
    # looser when results are strong (high top score with clear matches).
    # High-confidence results (top >= 0.5) use 40% cutoff to keep relevant tail.
    # Low-confidence results (top < 0.5) use 70% cutoff to trim noise aggressively.
    if results:
        top_score = results[0].score
        ratio = 0.4 if top_score >= 0.5 else 0.7
        cutoff = top_score * ratio
        results = [d for d in results if d.score >= cutoff]

    return results
