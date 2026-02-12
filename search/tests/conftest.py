"""Shared fixtures for search tests."""

import pytest
import numpy as np

from search.index import SearchRecord


def _make_record(
    offer_id: str,
    offer_name: str,
    offer_price: str = "$1.00 OFF",
    offer_description: str = "",
    offer_category: str = "General",
    offer_pgm: str = "MF",
    product_name: str = "",
    product_upc: str = "",
    product_price: float = 0.0,
    product_department: str = "",
    product_shelf: str = "",
    product_aisle: str = "",
    product_size: str = "",
    product_rating: str = "",
) -> SearchRecord:
    rec = SearchRecord(
        offer_id=offer_id,
        offer_name=offer_name,
        offer_price=offer_price,
        offer_description=offer_description,
        offer_category=offer_category,
        offer_pgm=offer_pgm,
        product_name=product_name,
        product_upc=product_upc,
        product_price=product_price,
        product_department=product_department,
        product_shelf=product_shelf,
        product_aisle=product_aisle,
        product_size=product_size,
        product_rating=product_rating,
    )
    parts = [offer_name, product_name, offer_description, product_department, product_shelf, offer_category]
    rec.search_text = " ".join(p for p in parts if p)
    return rec


@pytest.fixture
def sample_records() -> list[SearchRecord]:
    """A small set of records covering various search scenarios."""
    return [
        # Deal "Milk Sale" with 2 milk products
        _make_record("D1", "Milk Sale", product_name="Whole Milk 1 Gallon",
                      product_upc="001", product_price=3.99,
                      product_department="Dairy", product_shelf="Milk", product_aisle="Aisle 1"),
        _make_record("D1", "Milk Sale", product_name="2% Reduced Fat Milk",
                      product_upc="002", product_price=4.29,
                      product_department="Dairy", product_shelf="Milk", product_aisle="Aisle 1"),
        # Deal "Dairy Savings" — name doesn't say milk, but has a milk product
        _make_record("D2", "Dairy Savings", offer_description="Save on dairy essentials",
                      product_name="Organic Whole Milk Half Gallon",
                      product_upc="003", product_price=5.49,
                      product_department="Dairy", product_shelf="Milk", product_aisle="Aisle 1"),
        _make_record("D2", "Dairy Savings", offer_description="Save on dairy essentials",
                      product_name="Cheddar Cheese Block",
                      product_upc="004", product_price=6.99,
                      product_department="Dairy", product_shelf="Cheese", product_aisle="Aisle 2"),
        # Deal "Chocolate Treats" — has chocolate milk product
        _make_record("D3", "Chocolate Treats", offer_price="$2.00 OFF",
                      product_name="Dark Chocolate Bar",
                      product_upc="005", product_price=2.99,
                      product_department="Cookies, Snacks & Candy", product_shelf="Chocolate"),
        _make_record("D3", "Chocolate Treats", offer_price="$2.00 OFF",
                      product_name="Chocolate Milk Drink 16oz",
                      product_upc="006", product_price=1.99,
                      product_department="Dairy", product_shelf="Flavored Milk"),
        # Deal with no products (offer only)
        _make_record("D4", "Fresh Bread", offer_description="Save on bakery bread",
                      offer_category="Bakery"),
        # Deal "Cereal Deals" — no milk relation
        _make_record("D5", "Cereal Deals", product_name="Corn Flakes 18oz",
                      product_upc="007", product_price=4.49,
                      product_department="Breakfast & Cereal", product_shelf="Cereal"),
        # Deal "Lotion Special"
        _make_record("D6", "Lotion Special", product_name="Hand Lotion 8oz",
                      product_upc="008", product_price=7.99,
                      product_department="Personal Care", product_shelf="Lotion", product_aisle="Aisle 7"),
        # Deal "Wine Special" — category is "Wine, Beer & Spirits"
        _make_record("D7", "Wine Special", offer_price="$3.00 OFF",
                      offer_description="Save on select wines",
                      offer_category="Wine, Beer & Spirits",
                      product_name="Chardonnay 750ml",
                      product_upc="009", product_price=12.99,
                      product_department="Wine, Beer & Spirits", product_shelf="White Wine"),
        # Deal "Beer Deal" — same category but different product
        _make_record("D8", "Beer Deal", offer_price="$5.00 REBATE",
                      offer_category="Wine, Beer & Spirits",
                      product_name="Craft IPA 6-Pack",
                      product_upc="010", product_price=9.99,
                      product_department="Wine, Beer & Spirits", product_shelf="Craft Beer"),
        # Deal "Oatmilk Offer" — "milk" as substring in "oatmilk"
        _make_record("D9", "Oatmilk Offer", offer_price="$1.50 OFF",
                      product_name="Planet Oat Oatmilk 64oz",
                      product_upc="011", product_price=4.49,
                      product_department="Dairy", product_shelf="Milk Alternatives"),
        # Deal "Candy Bonanza" — many products, only some match chocolate
        _make_record("D10", "Candy Bonanza", offer_price="$2.00 OFF",
                      product_name="Milk Chocolate Truffles",
                      product_upc="012", product_price=5.99,
                      product_department="Cookies, Snacks & Candy", product_shelf="Chocolate"),
        _make_record("D10", "Candy Bonanza", offer_price="$2.00 OFF",
                      product_name="Gummy Bears",
                      product_upc="013", product_price=3.49,
                      product_department="Cookies, Snacks & Candy", product_shelf="Candy"),
        _make_record("D10", "Candy Bonanza", offer_price="$2.00 OFF",
                      product_name="Sour Patch Kids",
                      product_upc="014", product_price=3.99,
                      product_department="Cookies, Snacks & Candy", product_shelf="Candy"),
        _make_record("D10", "Candy Bonanza", offer_price="$2.00 OFF",
                      product_name="Jelly Beans",
                      product_upc="015", product_price=2.99,
                      product_department="Cookies, Snacks & Candy", product_shelf="Candy"),
    ]
