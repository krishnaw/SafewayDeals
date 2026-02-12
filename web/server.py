"""FastAPI backend for Safeway Deals web portal."""

from __future__ import annotations

import asyncio
import json
import re
import time
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

WEB_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = WEB_DIR.parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    _startup()
    yield


app = FastAPI(title="Safeway Deals Portal", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")
templates = Jinja2Templates(directory=WEB_DIR / "templates")


@app.middleware("http")
async def no_cache_static(request: Request, call_next):
    """Disable browser caching for static assets during development."""
    response = await call_next(request)
    if request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

# --- Global state populated at startup ---
_records: list = []
_embeddings = None
_model = None
_deals_lookup: dict[str, dict] = {}  # offerId -> full deal dict from deals.json
_all_deals: list[dict] = []  # ordered list of deals (enriched)
_categories: list[str] = []
_offer_types: list[str] = []
_deal_types: list[str] = []

_SEASONAL_KEYWORDS = ["valentine", "easter", "christmas", "holiday", "halloween",
                      "thanksgiving", "super bowl", "game day", "4th of july"]


def _classify_deal_type(offer_price: str) -> str:
    """Parse offerPrice string to determine deal type."""
    p = offer_price.lower().strip()
    if "rebate" in p:
        return "Rebate"
    if "free" in p:
        return "Free"
    if "per lb" in p:
        return "Per Pound"
    if "points" in p:
        return "Points"
    if "off" in p or p.startswith("save"):
        return "Dollar Off"
    if "each" in p or "for " in p:
        return "Fixed Price"
    if re.match(r"^\$[\d.]+$", p):
        return "Fixed Price"
    return "Other"


def _detect_seasonal(name: str) -> str:
    """Return seasonal tag if deal name matches a seasonal keyword."""
    name_lower = name.lower()
    for kw in _SEASONAL_KEYWORDS:
        if kw in name_lower:
            return kw.title().replace("4Th", "4th")
    return ""


def _enrich_deal_dict(deal: dict) -> dict:
    """Add image fields, deal type, product count, and seasonal tag."""
    offer_id = deal["offerId"]
    result = {
        "offerId": deal.get("offerId", ""),
        "name": deal.get("name", ""),
        "description": deal.get("description", ""),
        "offerPrice": deal.get("offerPrice", ""),
        "category": deal.get("category", ""),
        "offerPgm": deal.get("offerPgm", ""),
        "dealImageUrl": deal.get("image", ""),
        "productImageUrl": "",
        "startDate": deal.get("startDate", ""),
        "endDate": deal.get("endDate", ""),
        "dealType": _classify_deal_type(deal.get("offerPrice", "")),
        "seasonal": _detect_seasonal(deal.get("name", "")),
    }

    # Product count and first product data
    products_entry = _products_lookup.get(offer_id)
    if products_entry and products_entry.get("products"):
        prods = products_entry["products"]
        result["productCount"] = len(prods)
        first_prod = prods[0]
        result["productImageUrl"] = first_prod.get("imageUrl", "")
        result["productPrice"] = first_prod.get("price")
        result["productBasePrice"] = first_prod.get("basePrice")
    else:
        result["productCount"] = 0

    return result


def _deal_result_to_dict(deal_result) -> dict:
    """Convert a search DealResult to a JSON-serializable dict with image enrichment."""
    d = asdict(deal_result)
    offer_id = d["offer_id"]

    # Get image URLs from deals.json lookup
    raw_deal = _deals_lookup.get(offer_id, {})
    d["dealImageUrl"] = raw_deal.get("image", "")
    d["productImageUrl"] = ""

    # First matching product image, or fallback to products data
    if d["matching_products"]:
        for mp in d["matching_products"]:
            if mp.get("product_image_url"):
                d["productImageUrl"] = mp["product_image_url"]
                break

    products_entry = _products_lookup.get(offer_id)
    if not d["productImageUrl"]:
        if products_entry and products_entry.get("products"):
            d["productImageUrl"] = products_entry["products"][0].get("imageUrl", "")

    # Add product pricing from first qualifying product
    if products_entry and products_entry.get("products"):
        first_prod = products_entry["products"][0]
        d["productPrice"] = first_prod.get("price")
        d["productBasePrice"] = first_prod.get("basePrice")

    # Add dates from deal lookup
    d["startDate"] = raw_deal.get("startDate", "")
    d["endDate"] = raw_deal.get("endDate", "")

    # Add deal type, product count, seasonal
    d["dealType"] = _classify_deal_type(d.get("offer_price", ""))
    d["seasonal"] = _detect_seasonal(d.get("offer_name", ""))
    if products_entry and products_entry.get("products"):
        d["productCount"] = len(products_entry["products"])
    else:
        d["productCount"] = 0

    return d


# Products lookup: offerId -> offer entry from qualifying-products.json
_products_lookup: dict[str, dict] = {}


def _startup():
    global _records, _embeddings, _model, _deals_lookup, _all_deals
    global _categories, _offer_types, _deal_types, _products_lookup

    # Load deals.json for image enrichment
    deals_path = PROJECT_ROOT / "deals.json"
    with open(deals_path, "r", encoding="utf-8") as f:
        deals_data = json.load(f)
    for deal in deals_data["deals"]:
        _deals_lookup[deal["offerId"]] = deal

    # Load qualifying-products.json for product images
    products_path = PROJECT_ROOT / "qualifying-products.json"
    with open(products_path, "r", encoding="utf-8") as f:
        products_data = json.load(f)
    for offer in products_data["offers"]:
        _products_lookup[offer["offerId"]] = offer

    # Build enriched deals list
    _all_deals = [_enrich_deal_dict(deal) for deal in deals_data["deals"]]

    # Extract unique categories, offer types, and deal types
    cats = sorted({d["category"] for d in _all_deals if d["category"]})
    types = sorted({d["offerPgm"] for d in _all_deals if d["offerPgm"]})
    dtypes = sorted({d["dealType"] for d in _all_deals if d["dealType"]})
    _categories = cats
    _offer_types = types
    _deal_types = dtypes

    # Build search index
    from search.index import build_index
    _records, _embeddings, _model = build_index(show_progress=True)
    print(f"Server ready: {len(_all_deals)} deals, {len(_records)} search records")


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse(request, "index.html")


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


@app.get("/api/deals")
async def get_deals(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    category: str = Query("", description="Filter by category"),
    offer_pgm: str = Query("", description="Filter by offer program type"),
    deal_type: str = Query("", description="Filter by deal type"),
    expiry: str = Query("", description="Filter by expiry: today, week, month"),
    has_products: str = Query("", description="Filter to deals with products: yes"),
):
    filtered = _all_deals
    if category:
        filtered = [d for d in filtered if d["category"] == category]
    if offer_pgm:
        filtered = [d for d in filtered if d["offerPgm"] == offer_pgm]
    if deal_type:
        filtered = [d for d in filtered if d["dealType"] == deal_type]
    if has_products == "yes":
        filtered = [d for d in filtered if d["productCount"] > 0]
    if expiry:
        max_days = {"today": 0, "week": 7, "month": 30}.get(expiry)
        if max_days is not None:
            filtered = [
                d for d in filtered
                if (days := _days_until_expiry(d.get("endDate", ""))) is not None
                and days <= max_days
            ]

    total = len(filtered)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, total_pages)
    start = (page - 1) * per_page
    end = start + per_page

    return {
        "deals": filtered[start:end],
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages,
    }


@app.get("/api/search/stream")
async def search_stream(
    q: str = Query(..., min_length=1, description="Search query"),
    top_k: int = Query(40, ge=1, le=100),
):
    from search.expand import expand_query
    from search.search import search

    async def event_generator():
        loop = asyncio.get_event_loop()

        # Try query expansion for natural language queries
        expanded = await loop.run_in_executor(None, lambda: expand_query(q))

        if expanded:
            yield f"data: {json.dumps({'type': 'expanded', 'original': q, 'expanded': expanded})}\n\n"

            # Search each expanded term individually, then merge best scores
            terms = [t.strip() for t in expanded.split(",") if t.strip()]

            def _multi_search():
                from search.search import DealResult
                merged: dict[str, DealResult] = {}
                # Track how many terms matched each deal (multi-term hit = more relevant)
                term_hits: dict[str, int] = {}
                for term in terms:
                    hits = search(term, _records, _embeddings, _model, top_k=top_k)
                    for deal in hits:
                        term_hits[deal.offer_id] = term_hits.get(deal.offer_id, 0) + 1
                        if deal.offer_id not in merged or deal.score > merged[deal.offer_id].score:
                            merged[deal.offer_id] = deal
                # Boost deals matched by multiple expanded terms (more relevant to theme)
                for oid, deal in merged.items():
                    hits_count = term_hits.get(oid, 1)
                    if hits_count >= 2:
                        deal.score *= 1.0 + 0.1 * min(hits_count - 1, 3)  # up to 1.3x
                ranked = sorted(merged.values(), key=lambda d: d.score, reverse=True)
                ranked = ranked[:top_k]
                # Apply adaptive cutoff to merged results (removes noisy tail)
                if ranked:
                    top_score = ranked[0].score
                    cutoff = top_score * 0.45
                    ranked = [d for d in ranked if d.score >= cutoff]
                return ranked

            results = await loop.run_in_executor(None, _multi_search)
        else:
            # Single/direct query — search as-is
            results = await loop.run_in_executor(
                None, lambda: search(q, _records, _embeddings, _model, top_k=top_k)
            )

        # Stream in batches of 4 (one row)
        batch = []
        for deal_result in results:
            batch.append(_deal_result_to_dict(deal_result))
            if len(batch) == 4:
                yield f"data: {json.dumps(batch)}\n\n"
                batch = []
                await asyncio.sleep(0.05)

        # Send remaining
        if batch:
            yield f"data: {json.dumps(batch)}\n\n"

        yield "data: [END]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/categories")
async def get_categories():
    return {
        "categories": _categories,
        "offerTypes": _offer_types,
        "dealTypes": _deal_types,
    }
