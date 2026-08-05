# Amazon Scraper

Scrapes Amazon product details, search results, prices, ratings, reviews,
sellers and deals using Playwright with CloakBrowser for anti-detection and
BeautifulSoup for HTML parsing. Runs both as a CLI tool and as an Apify actor.

## Features

- **Product pages** — title, price, rating, review count, images, bullet
  points, availability, ASIN, brand, technical details, category, variants,
  seller / buy-box ownership, price-deal tracking and reviews.
- **Search mode** — walks search result pages and scrapes every result.
- **Anti-detection** — CloakBrowser fingerprinting, per-domain
  locale/timezone, randomized viewports, CAPTCHA detection and click-through
  with retries and backoff.
- **HTML caching** with TTL for fast repeat runs.
- **Persistent browser profiles** and optional proxy support (including the
  Apify proxy).
- **Apify actor support** with resume/persist state and graceful shutdown.

## Installation

Requires Python 3.11+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .

# Install the CloakBrowser Chromium binary (once, ~150 MB):
python -c "from cloakbrowser.download import ensure_binary; ensure_binary()"
```

## CLI usage

Scrape a single product:

```bash
amazon-scraper "https://www.amazon.com/dp/B09XS7JWHH" -o product.json
```

Scrape a search term and every resulting product:

```bash
amazon-scraper "noise cancelling headphones" --search -n 10 -o results.json
```

Common options:

| Option | Description |
| --- | --- |
| `--search` / `-s` | Treat the positional argument as a search term |
| `-n, --max-results` | Max products scraped from search (default 5) |
| `--max-pages` | Max search result pages walked (default 3) |
| `--max-reviews` | Reviews scraped per product; `0` disables (default 10) |
| `--retries` | Max attempts per product, including the first (default 2) |
| `--timeout` | Navigation timeout in ms (default 15000) |
| `--wait` | Extra wait after page load in ms |
| `--zip` | Delivery zip code (default 90035) |
| `--cache` / `--no-cache` | Enable / disable HTML caching |
| `--cache-dir`, `--cache-ttl` | Cache location and TTL in seconds (default 3600) |
| `--proxy` | Proxy URL, e.g. `http://user:pass@host:port` |
| `--persistent NAME` | Use a persistent browser profile |
| `--headed` | Show the browser UI |
| `--verbose` / `-v` | Debug logging |
| `--config PATH` | YAML config file with default option values |

## Configuration

Defaults can be seeded from a YAML file (see `config.yaml.example`):

```yaml
retries: 2
timeout: 15000
wait: 0
headless: true
zip: "90035"
max_results: 5
max_pages: 3
max_reviews: 10
cache: true
cache_dir: cache
cache_ttl: 3600
```

## Apify actor

Deploy the `src/` package as an Apify actor (see `.actor/actor.json`). Input
fields (`.actor/INPUT_SCHEMA.json`):

- `searchTerm` — run in search mode.
- `productUrls` — run in URL mode (list of product URLs).
- `domain` — Amazon domain (default `amazon.com`).
- `maxResults`, `maxPages`, `maxReviews`, `retries`, `timeout`, `wait` —
  run limits (clamped to safe maximums).
- `zip` — delivery zip code.
- `proxy` — Apify proxy configuration.
- `session` — proxy session id for sticky sessions.
- `freshRun` — ignore previously persisted resume state.

The actor persists processed URLs to its key-value store and resumes
interrupted runs unless `freshRun` is set. On `ABORTING` / `MIGRATING` /
`EXIT` events it saves state and stops the scraping thread gracefully.

## Output

Each product is emitted as JSON, for example:

```json
{
  "url": "https://www.amazon.com/dp/B09XS7JWHH",
  "title": "Sony WH-1000XM5",
  "price": "$329.99",
  "rating": "4.6 out of 5 stars",
  "review_count": "12345",
  "asin": "B09XS7JWHH",
  "seller_name": "Sony",
  "buybox_owner": true,
  "from_cache": false,
  "scraped_at": "2026-07-23T12:34:56+00:00"
}
```

## Development

```bash
pip install -e .
pytest
ruff check .
```

## Docker

Build the actor image (used by Apify, or run locally):

```bash
docker build -t amazon-scraper .
docker run --rm amazon-scraper
```

The image installs pinned dependencies and runs as the non-root `myuser`.
