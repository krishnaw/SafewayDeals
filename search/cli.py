"""Interactive CLI for searching Safeway deals and products."""

from __future__ import annotations

import time

from .index import SearchRecord, build_index
from .search import DealResult, search


def format_deal(deal: DealResult, rank: int) -> str:
    sources = ", ".join(deal.sources)
    lines = [
        f"  {rank}. {deal.offer_name}  [{deal.score:.3f} via {sources}]",
        f"     {deal.offer_price} | {deal.offer_category} | Offer ID: {deal.offer_id}",
        f"     {deal.offer_description}",
    ]

    if deal.matching_products:
        lines.append(f"     Matching products ({len(deal.matching_products)}):")
        for p in deal.matching_products:
            price = f"${p.product_price:.2f}" if p.product_price else "N/A"
            parts = [price]
            if p.product_size:
                parts.append(p.product_size)
            if p.product_aisle:
                parts.append(p.product_aisle)
            lines.append(f"       - {p.product_name}")
            lines.append(f"         {' | '.join(parts)}")

    return "\n".join(lines)


def main():
    print("=" * 60)
    print("  Safeway Deals Search")
    print("=" * 60)
    print()

    records, embeddings, model = build_index()
    print(f"\nReady! {len(records)} records indexed.\n")
    print("Type a search query (or 'quit' to exit):\n")

    while True:
        try:
            query = input("search> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if not query or query.lower() in ("quit", "exit", "q"):
            if query and query.lower() in ("quit", "exit", "q"):
                print("Bye!")
            break

        t0 = time.perf_counter()
        results = search(query, records, embeddings, model)
        elapsed = time.perf_counter() - t0

        print(f"\n{'='*60}")
        print(f"  {len(results)} deals found ({elapsed:.3f}s)")
        print(f"{'='*60}")

        if not results:
            print("  No deals found.")
        else:
            for i, deal in enumerate(results, 1):
                print(format_deal(deal, i))
                print()

        print()


if __name__ == "__main__":
    main()
