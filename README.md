# SafewayDeals

Search, browse, and explore Safeway grocery deals with intelligent search, AI chat, and a modern web interface.

## Features

- **401 deals** with **4,057 qualifying products** from Safeway store #1197
- **Intelligent search** combining keyword, fuzzy, and semantic matching
- **Natural language queries** — ask "something for a headache" and find Tylenol, Advil, etc.
- **NLQ expansion** via Groq Llama 3.1 for multi-word query interpretation
- **AI Chat** — conversational deal finder with streaming responses and deal cards
- **10 card designs** — Coupon, Minimal, Split, Badge, Compact, Glass, Magazine, Dark, Price, List
- **5 filters** — Category, Offer Type, Deal Type, Expiry, Has Products
- **SSE streaming** — results appear progressively as they're found
- **Deal-centric results** — searches across both deal and product fields, groups by offer

## Prerequisites

- **Python 3.11+**
- **Groq API key** (optional — enables NLQ query expansion and AI chat; free at https://console.groq.com/)

## Quick Start

```bash
# Clone the repo
git clone https://github.com/krishnaw/SafewayDeals.git
cd SafewayDeals

# Install dependencies
pip install -r requirements.txt

# (Optional) Set up NLQ expansion + AI chat
cp .env.example .env
# Edit .env and add your Groq API key (free at console.groq.com)

# Start the web server
powershell -ExecutionPolicy Bypass -File web/server.ps1 start

# Open in browser
# http://localhost:8001
```

To stop the server:
```bash
powershell -ExecutionPolicy Bypass -File web/server.ps1 stop
```

### CLI Search

You can also search from the command line:
```bash
python -m search
```

## Project Structure

```
SafewayDeals/
├── deals.json                  # 401 deals from Safeway
├── qualifying-products.json    # 4,057 products across 359 deals
├── requirements.txt            # Python dependencies
├── pytest.ini                  # Test configuration
├── .env.example                # API key template
│
├── search/                     # Search engine
│   ├── index.py                # Data loading, embedding computation & caching
│   ├── search.py               # Keyword, fuzzy, semantic search + composite ranking
│   ├── expand.py               # NLQ query expansion via Groq Llama 3.1
│   ├── chat.py                 # AI chat with Groq Llama 3.1 (tool use, streaming)
│   ├── cli.py                  # Interactive CLI interface
│   └── tests/                  # 188 search tests
│       ├── test_keyword.py     # 17 field-weighted keyword scoring tests
│       ├── test_fuzzy.py       # 8 fuzzy matching & typo correction tests
│       ├── test_semantic.py    # 6 semantic similarity tests
│       ├── test_search_unified.py  # 23 composite search logic tests
│       ├── test_integration.py # 8 real-data integration tests
│       ├── test_ranking.py     # 40 ranking quality assertions
│       ├── test_expand.py      # 45 NLQ expansion tests (mock + live)
│       └── test_chat.py        # 54 AI chat tests (guardrails, streaming, tool use)
│
└── web/                        # Web portal
    ├── server.py               # FastAPI backend (6 endpoints, SSE streaming)
    ├── server.ps1              # PowerShell start/stop script
    ├── templates/index.html    # HTML shell
    ├── static/
    │   ├── styles.css          # 10 card designs, responsive grid
    │   └── app.js              # SPA logic, SSE streaming, filters, chat
    └── tests/                  # 51 web tests
        ├── test_server.py      # 36 API tests (deals, SSE, NLQ, chat)
        └── test_e2e.py         # 15 Playwright E2E tests (browse, search, chat)
```

## Search Architecture

The search engine builds **4,099 searchable records** (one per product + one per offer without products) and runs three strategies concurrently using a thread pool:

| Strategy | Weight | How it works |
|----------|--------|-------------|
| **Keyword** | 50% | Field-weighted term matching. All query words must appear in the record. Scores by where each word matches: offer name (3x), product name (2x), description (1x), other fields like category/department (0.5x). Whole-word matches get a 1.5x bonus over substring matches. |
| **Fuzzy** | 25% | RapidFuzz `partial_ratio` against offer names and product names (threshold: 60). Handles typos like "choclate" → chocolate, "cofee" → coffee, "yougrt" → yogurt. |
| **Semantic** | 25% | Sentence-transformer embeddings (all-MiniLM-L6-v2, 384-dim). Encodes the query and finds closest records by cosine similarity. Handles conceptual queries like "something to drink with breakfast". |

### Composite Scoring

Each record's final score is a weighted combination:

```
composite = 0.50 * keyword + 0.25 * fuzzy + 0.25 * semantic
```

### Ranking Signals

Six additional signals adjust the composite score:

1. **Multi-source bonus** — +0.1 per extra search mode that found the record (max +0.2). A record found by all three modes gets +0.2.

2. **Fuzzy cap** — When a record has both keyword and fuzzy scores, fuzzy is capped to the keyword score. This prevents fuzzy from inflating results that already have exact substring matches. Fuzzy is meant for typo recovery (when keyword finds nothing), not score inflation.

3. **Semantic-only discount** — Records found only by semantic search (no keyword or fuzzy confirmation) get a 0.5x multiplier. This prevents vaguely-related conceptual matches from outranking exact keyword hits.

4. **Match density** — Penalizes deals where only a small fraction of products matched. Formula: `score *= 0.3 + 0.7 * (matched_products / total_products)`. A deal with 2/2 products matching "chocolate" ranks above a deal with 1/20 matching. Uses keyword-matched product counts primarily, falling back to fuzzy counts for typo queries where keyword finds nothing.

5. **Offer-name boost** — 1.2x when query words appear in the deal's offer name (via exact substring OR fuzzy match with `partial_ratio >= 80`). Ensures "Milk Sale" ranks above a deal that only has milk buried in its product list. The fuzzy path handles typos: "choclate" still boosts "Chocolate Treats".

6. **Adaptive cutoff** — Trims low-scoring tail noise. The cutoff threshold adapts to result confidence:
   - High-confidence (top score >= 0.5): keeps results above 40% of top score
   - Low-confidence (top score < 0.5): keeps results above 70% of top score

   This trims noise from weak queries (e.g., "wine" from 36 results down to ~4) without losing good results from strong queries.

### Gibberish Gate

Before scoring, the engine checks if the query is meaningful. A query is rejected (returns 0 results) when **all three** conditions are true:
- No keyword matches found
- No strong fuzzy matches (score >= 80)
- No query word exists in the precomputed corpus word set (all words from all records)

This blocks nonsense like "abcd", "qwerty", "zzzzz" while still allowing typos ("choclate" passes because fuzzy finds strong matches) and real words ("milk" passes because it's in the corpus).

### Deal Grouping

Search operates at the record level (one record per product), then groups results by `offer_id` into `DealResult` objects. Each `DealResult` contains only the products that actually matched the query — not all products in the deal. A deal surfaces if its name/description matches OR if any of its qualifying products match.

## Search Examples

These examples are derived from the [ranking test suite](search/tests/test_ranking.py) which validates search quality against the full 401-deal dataset.

### Exact keyword matching

| Query | Behavior |
|-------|----------|
| `"chocolate"` | Top result has "chocolate" in offer name. Score > 0.8. |
| `"milk"` | Deals with "milk" in offer name rank above deals where milk only appears in product names. |
| `"bread"` | Returns 1–5 precise results, all with "bread" in offer name. |
| `"gift card"` | Every returned result is a gift card deal (high precision). |
| `"coffee"` | Top result has "coffee" in offer name. |

### Typo recovery

| Query | Finds | How |
|-------|-------|-----|
| `"choclate"` | Chocolate deals (Ferrero, etc.) | Fuzzy match corrects the typo |
| `"cofee"` | Coffee deals | Fuzzy `partial_ratio` catches single-letter typo |
| `"yougrt"` | Yogurt deals (Chobani, Yoplait) | Fuzzy recovers transposed/missing letters |
| `"logion"` | Lotion deals | Fuzzy matches despite letter substitution |
| `"mlk"` | Milk deals | Fuzzy catches abbreviated/missing vowels |

Correct spelling always returns more results and higher scores than the typo version.

### Brand search

| Query | Result |
|-------|--------|
| `"pepsi"` | All results are Pepsi deals |
| `"coca cola"` | Finds Coca-Cola deals |
| `"huggies"` | Finds Huggies diaper deals |
| `"ferrero"` | Finds Ferrero chocolate deals |
| `"starbucks"` | Finds Starbucks coffee deals |

### Natural language & semantic

| Query | Behavior |
|-------|----------|
| `"healthy snacks"` | Finds snack deals via semantic similarity |
| `"baby products"` | Finds baby care deals |
| `"pet food"` | Finds cat/dog food deals (Purina, etc.) |
| `"cleaning supplies"` | Finds household cleaning deals |
| `"something to drink with breakfast"` | Semantic search finds milk, juice, and coffee deals |

### Gibberish rejection

| Query | Result |
|-------|--------|
| `"abcd"`, `"asdf"`, `"qwerty"` | 0 results (blocked by gibberish gate) |
| `"xyz"` | Finds XYZAL allergy deals (real substring match, not blocked) |
| `"milk"`, `"bread"`, `"soap"` | Results returned (real corpus words pass the gate) |

### Ranking quality properties

- **Scores are differentiated** — common queries like "milk", "chocolate", "cheese" produce a clear score range (not flat)
- **Results are always sorted** by score descending
- **No duplicate deals** — each `offer_id` appears at most once
- **Products belong to their deal** — every `matching_product`'s `offer_id` matches its parent deal
- **Density matters** — a deal with 2/2 chocolate products ranks above a deal with 1/4 chocolate products

## NLQ Query Expansion

For multi-word queries, the NLQ expander sends the query to **Groq Llama 3.1 8B Instant** to extract concrete product keywords. The system prompt constrains suggestions to the store's 19 categories (Beverages, Dairy, Meat & Seafood, etc.).

- **Single-word queries skip the LLM** — the existing search pipeline handles them well
- **LLM returns "PASS"** for queries that are already specific (e.g., "coca cola")
- Each expanded term is searched individually, and results are merged by best score per deal with multi-term boosting (up to 1.3x) and 45% adaptive cutoff
- **LRU cache** (128 entries) avoids redundant LLM calls
- **3-second timeout** with graceful fallback to direct search
- UI shows "Interpreted as: ..." when expansion occurs

Example: `"something for breakfast"` → LLM expands to `"cereal, oatmeal, pancake mix, eggs, yogurt, orange juice, coffee, milk, bread, bacon"` → each term searched → results merged.

## AI Chat

A conversational deal finder accessible via the chat panel in the web UI.

- **Groq Llama 3.1 8B** with OpenAI-style function calling (`search_deals` tool)
- Two-phase LLM call: Phase 1 checks for tool calls, Phase 2 streams the response
- **Pre-check guardrail** rejects off-topic queries (politics, coding, etc.)
- **System prompt guardrail** constrains responses to grocery/deals/meal planning
- SSE streaming with mini deal cards rendered after the text response
- Follow-up suggestion chips after every response (LLM-generated or default suggestions)
- **Summarize visible deals** button — shows mini cards for deals currently in the browser viewport
- Stateless: client sends conversation history with each request (truncated to last 10 turns)
- Expiry filtering via `search_deals(query='*', expiry='week')` for expiring deal queries
- Robust frontend: text always shows, deal cards always render when available, SUGGESTIONS never leak
- Requires `GROQ_API_KEY` in `.env`

## Configuration

Create a `.env` file (or copy `.env.example`):

```env
# Enables NLQ query expansion + AI chat (optional — search works without it)
# Free key at https://console.groq.com/
GROQ_API_KEY=gsk_...
```

## Running Tests

```bash
# All tests (search + server: 274)
python -m pytest search/tests/ web/tests/test_server.py -v

# Search tests only (189)
python -m pytest search/tests/ -v

# Web API tests only (36)
python -m pytest web/tests/test_server.py -v

# E2E browser tests (15, 4 LLM-dependent skipped by default)
python -m pytest web/tests/test_e2e.py -v
```

## Tech Stack

- **Python 3.11** — core language
- **FastAPI** + **Uvicorn** — async web server with SSE streaming
- **sentence-transformers** — semantic embeddings (all-MiniLM-L6-v2)
- **RapidFuzz** — fuzzy string matching
- **NumPy** — vector operations
- **Groq SDK** — NLQ query expansion + AI chat via Llama 3.1 8B Instant (free tier)
- **Vanilla HTML/CSS/JS** — zero frontend framework dependencies
- **Playwright** — E2E testing
- **pytest** — test framework

## License

MIT
