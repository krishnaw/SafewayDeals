# SafewayDeals

Search, browse, and explore Safeway grocery deals with intelligent search and a modern web interface.

## Features

- **401 deals** with **4,057 qualifying products** from Safeway store #1197
- **Intelligent search** combining keyword, fuzzy, and semantic matching
- **Natural language queries** — ask "something for a headache" and find Tylenol, Advil, etc.
- **NLQ expansion** via Claude Haiku for multi-word query interpretation
- **10 card designs** — Coupon, Minimal, Split, Badge, Compact, Glass, Magazine, Dark, Price, List
- **5 filters** — Category, Offer Type, Deal Type, Expiry, Has Products
- **SSE streaming** — results appear progressively as they're found
- **Deal-centric results** — searches across both deal and product fields, groups by offer

## Prerequisites

- **Python 3.11+**
- **Anthropic API key** (optional — enables NLQ query expansion for natural language searches)

## Quick Start

```bash
# Clone the repo
git clone https://github.com/krishnaw/SafewayDeals.git
cd SafewayDeals

# Install dependencies
pip install -r requirements.txt

# (Optional) Set up NLQ expansion
cp .env.example .env
# Edit .env and add your Anthropic API key

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
│   ├── expand.py               # NLQ query expansion via Claude Haiku
│   ├── cli.py                  # Interactive CLI interface
│   └── tests/                  # 103 search tests
│       ├── test_keyword.py     # Field-weighted keyword scoring
│       ├── test_fuzzy.py       # Fuzzy matching & typo correction
│       ├── test_semantic.py    # Semantic similarity search
│       ├── test_search_unified.py  # Composite search logic
│       ├── test_integration.py # Real-data integration tests
│       └── test_ranking.py     # Ranking quality assertions
│
└── web/                        # Web portal
    ├── server.py               # FastAPI backend (5 endpoints, SSE streaming)
    ├── server.ps1              # PowerShell start/stop script
    ├── templates/index.html    # HTML shell
    ├── static/
    │   ├── styles.css          # 10 card designs, responsive grid
    │   └── app.js              # SPA logic, SSE streaming, filters
    └── tests/                  # 29 web tests
        ├── test_server.py      # 21 API tests
        └── test_e2e.py         # 8 Playwright E2E tests
```

## Search Architecture

The search engine runs three strategies in parallel and combines their scores:

| Strategy | Weight | How it works |
|----------|--------|-------------|
| **Keyword** | 50% | Field-weighted term matching (offer name 3x, product name 2x, description 1x) with whole-word bonus |
| **Fuzzy** | 25% | RapidFuzz token matching for typo tolerance (e.g., "choclate" finds "chocolate") |
| **Semantic** | 25% | Sentence-transformer embeddings (all-MiniLM-L6-v2) for conceptual similarity |

Additional ranking signals:
- **Multi-source bonus** — results found by multiple strategies get a boost
- **Match density** — deals where more products match rank higher
- **Offer-name boost** — 1.2x when query terms appear in the deal name
- **Adaptive cutoff** — automatically trims low-confidence noise
- **Gibberish gate** — rejects nonsense queries (e.g., "asdf")

For multi-word natural language queries (e.g., "something for breakfast"), the NLQ expander sends the query to Claude Haiku to extract concrete product keywords before searching.

## Configuration

Create a `.env` file (or copy `.env.example`):

```env
# Required for NLQ query expansion (optional — search works without it)
ANTHROPIC_API_KEY=sk-ant-...
```

## Running Tests

```bash
# All tests (124+)
python -m pytest search/tests/ web/tests/ -v

# Search tests only (103)
python -m pytest search/tests/ -v

# Web API tests only (21)
python -m pytest web/tests/test_server.py -v

# E2E browser tests (8) — requires playwright install
python -m pytest web/tests/test_e2e.py -v
```

## Tech Stack

- **Python 3.11** — core language
- **FastAPI** + **Uvicorn** — async web server with SSE streaming
- **sentence-transformers** — semantic embeddings (all-MiniLM-L6-v2)
- **RapidFuzz** — fuzzy string matching
- **NumPy** — vector operations
- **Anthropic SDK** — NLQ query expansion via Claude Haiku
- **Vanilla HTML/CSS/JS** — zero frontend framework dependencies
- **Playwright** — E2E testing
- **pytest** — test framework

## License

MIT
