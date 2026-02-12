"""Load Safeway deals/products JSON and build search index with cached embeddings."""

import hashlib
import json
import os
import pickle
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

MODEL_NAME = "all-MiniLM-L6-v2"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEALS_PATH = PROJECT_ROOT / "deals.json"
PRODUCTS_PATH = PROJECT_ROOT / "qualifying-products.json"
CACHE_DIR = Path(__file__).resolve().parent / "cache"


@dataclass
class SearchRecord:
    offer_id: str
    offer_name: str
    offer_price: str
    offer_description: str
    offer_category: str
    offer_pgm: str
    product_name: str = ""
    product_upc: str = ""
    product_price: float = 0.0
    product_image_url: str = ""
    product_department: str = ""
    product_shelf: str = ""
    product_aisle: str = ""
    product_size: str = ""
    product_rating: str = ""
    search_text: str = ""


def _build_search_text(rec: SearchRecord) -> str:
    parts = [
        rec.offer_name,
        rec.product_name,
        rec.offer_description,
        rec.product_department,
        rec.product_shelf,
        rec.offer_category,
    ]
    return " ".join(p for p in parts if p)


def _file_hash(*paths: Path) -> str:
    h = hashlib.md5()
    for p in paths:
        h.update(p.read_bytes())
    return h.hexdigest()


def load_records() -> list[SearchRecord]:
    """Load deals.json + qualifying-products.json and build SearchRecord list."""
    with open(DEALS_PATH, "r", encoding="utf-8") as f:
        deals_data = json.load(f)
    with open(PRODUCTS_PATH, "r", encoding="utf-8") as f:
        products_data = json.load(f)

    # Build a lookup from offerId -> offer-level product list
    product_lookup: dict[str, list[dict]] = {}
    for offer in products_data["offers"]:
        product_lookup[offer["offerId"]] = offer.get("products", [])

    records: list[SearchRecord] = []
    for deal in deals_data["deals"]:
        offer_id = deal["offerId"]
        offer_base = dict(
            offer_id=offer_id,
            offer_name=deal.get("name", ""),
            offer_price=deal.get("offerPrice", ""),
            offer_description=deal.get("description", ""),
            offer_category=deal.get("category", ""),
            offer_pgm=deal.get("offerPgm", ""),
        )

        products = product_lookup.get(offer_id, [])
        if products:
            for prod in products:
                size_parts = [
                    prod.get("dispItemSizeQty", ""),
                    prod.get("dispUnitOfMeasure", ""),
                ]
                size = " ".join(p for p in size_parts if p)
                rec = SearchRecord(
                    **offer_base,
                    product_name=prod.get("name", ""),
                    product_upc=prod.get("upc", ""),
                    product_price=prod.get("price", 0.0),
                    product_image_url=prod.get("imageUrl", ""),
                    product_department=prod.get("departmentName", ""),
                    product_shelf=prod.get("shelfName", ""),
                    product_aisle=prod.get("aisleLocation", ""),
                    product_size=size,
                    product_rating=prod.get("avgRating", ""),
                )
                rec.search_text = _build_search_text(rec)
                records.append(rec)
        else:
            rec = SearchRecord(**offer_base)
            rec.search_text = _build_search_text(rec)
            records.append(rec)

    return records


def build_embeddings(
    records: list[SearchRecord], show_progress: bool = True
) -> np.ndarray:
    """Compute or load cached embeddings for all records."""
    CACHE_DIR.mkdir(exist_ok=True)
    embeddings_path = CACHE_DIR / "embeddings.npy"
    records_path = CACHE_DIR / "records.pkl"
    hash_path = CACHE_DIR / "data_hash.txt"

    current_hash = _file_hash(DEALS_PATH, PRODUCTS_PATH)

    # Check cache validity
    if (
        embeddings_path.exists()
        and records_path.exists()
        and hash_path.exists()
        and hash_path.read_text().strip() == current_hash
    ):
        print(f"  Loading cached embeddings from {embeddings_path}")
        embeddings = np.load(embeddings_path)
        if embeddings.shape[0] == len(records):
            return embeddings
        print("  Cache size mismatch, recomputing...")

    # Compute embeddings
    from sentence_transformers import SentenceTransformer

    print(f"  Loading model '{MODEL_NAME}'...")
    model = SentenceTransformer(MODEL_NAME)

    texts = [r.search_text for r in records]
    print(f"  Computing embeddings for {len(texts)} records...")
    embeddings = model.encode(
        texts,
        show_progress_bar=show_progress,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )

    # Save cache
    np.save(embeddings_path, embeddings)
    with open(records_path, "wb") as f:
        pickle.dump(records, f)
    hash_path.write_text(current_hash)
    print(f"  Cached embeddings to {embeddings_path}")

    return embeddings


def load_model():
    """Load the sentence transformer model (for query encoding at search time)."""
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(MODEL_NAME)


def _prepare_records_for_search(records: list[SearchRecord]) -> None:
    """Pre-lowercase all text fields on records so search doesn't repeat this work."""
    for rec in records:
        rec._stl = rec.search_text.lower()
        rec._onl = rec.offer_name.lower()
        rec._pnl = rec.product_name.lower()
        rec._odl = rec.offer_description.lower()
        rec._ocl = rec.offer_category.lower()
        rec._pdl = rec.product_department.lower()
        rec._psl = rec.product_shelf.lower()


def build_index(show_progress: bool = True):
    """Full index build: load records, compute embeddings, load model. Returns (records, embeddings, model)."""
    print("Loading deal and product data...")
    records = load_records()
    print(f"  {len(records)} searchable records built")

    print("Building embeddings...")
    embeddings = build_embeddings(records, show_progress=show_progress)

    print("Loading search model...")
    model = load_model()

    # Pre-lowercase fields for fast keyword search
    _prepare_records_for_search(records)

    return records, embeddings, model
