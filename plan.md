# Analysis and Improvement Plan for Amazon Scraper

## Project Overview
The Amazon scraper is a Python package that extracts product information from Amazon product pages using Playwright with CloakBrowser for anti-detection, BeautifulSoup for HTML parsing, and a dataclass model for structured output.

## Current State Assessment

### Strengths Already Present (No Changes Needed):
- **URL Tracking Parameter Removal**: `_clean_amazon_url()` removes tracking params that can trigger CAPTCHA (`AMAZON_TRACKING_PARAMS` at line 19-23 in scraper.py)
- **Domain-Specific Locale/Timezone**: `DOMAIN_LOCALE` dictionary (lines 33-53 in browser.py) handles 18 Amazon country domains with correct timezone/locale
- **Viewport Randomization**: Random viewport selection from `VIEWPORTS` list (lines 18-24 in browser.py)
- **Humanization**: Configured via cloakbrowser with careful preset and detailed mouse/typing config (lines 88-99 in browser.py)
- **Persistent Profile Support**: Full implementation with profile path creation (lines 118-122 in browser.py)
- **Retry Logic with Backoff**: Exponential backoff with jitter in both scraper.py (lines 104-143) and browser.py (lines 237-280)
- **Intelligent Wait for Content**: Uses `wait_for_selector("#productTitle, #dp, #centerCol")` instead of flat timeouts (lines 258-264 in browser.py)
- **Price Extraction**: Uses layered approach correctly - HTML first (`_extract_price_from_soup`), browser fallback (`_extract_price_from_browser`)
- **Image Deduplication**: Smart image extraction with size normalization and dedup (lines 123-154 in parser.py)
- **Bullet Point Deduplication**: Case-insensitive dedup already implemented (lines 157-170 in parser.py)
- **Atomic File Write**: Safe write via temp file + rename (lines 50-53 in scraper.py)
- **Proper Resource Cleanup**: `finally` block in main() closes page and stops session (lines 180-183 in scraper.py)
- **Test Coverage**: Good parser tests with realistic fixtures for sony_xm5 and lenovo_legion products
- **Multi-Domain Support**: Domain detection and URL cleaning for amazon.com, .co.uk, .de, etc.

### Bug Still Present (Needs Fix):
1. **`_extract_availability` returns empty string**: Line 173-180 in parser.py - returns `el.get_text(strip=True)` without checking if result is empty

### What Was Wrong in Original Analysis:
- **"COUPON_PATTERNS dead code"** - This was removed in a prior edit
- **"Replace hardcoded waits"** - Core navigation already uses `wait_for_selector()`, only `set_zip_code()` uses `wait_for_timeout()`
- **"Improve output filename"** - Already uses ASIN when available, `product.json` fallback is reasonable
- **"Price extraction path inconsistent"** - The code is actually correct - `enrich_from_browser` intentionally only fills price (not the full `extract_price` function) to avoid redundant work

## Identified Issues, Improvements, and New Features

### Priority 1: Bug Fixes
1. **Fix `_extract_availability` in `parser.py`** (line 173-180)
   - Currently returns empty string when `#availability span` is present but empty
   - Fix: Check if stripped text is non-empty before returning

### Priority 2: Browser Session Improvements
1. **Fix persistent browser context leak** (line 132 in browser.py)
   - `stop()` method only closes context for non-persistent sessions
   - Fix: Close persistent context as well, or provide explicit cleanup method for persistent mode

2. **Replace hardcoded waits in `set_zip_code()`**
   - `wait_for_timeout()` calls at lines 164, 189, 199, 208, 220 should use explicit waits
   - Example: wait for zip input to appear instead of 300ms sleep

3. **Improve CAPTCHA handling**
   - Only detects `button[alt='Continue shopping']`
   - Add detection for other CAPTCHA variants (image selection, checkbox puzzles)
   - Add logging for all CAPTCHA encounters

### Priority 3: Parser Enhancements (No Rush - Foundation is Solid)
1. **Extract additional product fields**
   - Brand/manufacturer
   - Product dimensions/weight
   - Best Seller Rank (BSR)
   - Date first available
   - Color/size/variant options
   - Discount/savings amount
   - Seller information
   - Warranty information
   - Return policy
   - Customer questions/answers count

2. **Enhance `enrich_from_browser`**
   - Currently only fills missing price
   - Could extract rating, review count, availability, brand via JS when not in HTML

3. **Improve title extraction**
   - Current fallback strips `: Amazon\..*` from title tag - could be overly aggressive

### Priority 4: Model Improvements
1. **Add field validation to `Product` model**
   - Validate ASIN format (10 alphanumeric characters)
   - Validate price format (currency symbol + number)
   - Validate rating format (X out of 5)
   - Add URL validation for image URLs (optional)

2. **Enhance `to_json()` method**
   - Add schema version field
   - Add timestamp field for when scrape occurred
   - Consider adding metadata about scrape source (domain, locale, etc.)

### Priority 5: CLI Improvements
1. **Enhance verbose output**
   - Add images count, bullets count, availability, ASIN to verbose logs
   - Currently only logs: URL, title, price, rating, reviews

2. **Add configuration file support**
   - Allow YAML/JSON config file with defaults
   - Support environment variable overrides
   - Example: default retries, timeout, wait, humanize settings

3. **Add signal handling**
   - Handle SIGINT/SIGTERM for graceful shutdown
   - Save partial results on interrupt

4. **Improve error handling**
   - Classify errors (retryable vs fatal)
   - Circuit breaker for repeated failures
   - Log partial results when possible

### Priority 6: NEW FEATURE - Search Functionality (User Requested)
1. **Add search command-line argument**
   - `--search` or `-s` for search terms instead of product URLs
   - Navigate to Amazon search results page
   - Parse results to extract product links

2. **Enhance parser for search results**
   - Parse Amazon search result pages
   - Extract product links, titles, prices, ratings, ASINs
   - Handle sponsored vs organic results
   - Implement pagination for multiple result pages

3. **Update CLI for search mode**
   - `--max-results` or `-n` to limit products scraped
   - `--pages` or `-p` for number of result pages
   - Output handling for multiple products (separate files or JSON array)

4. **Update BrowserSession for search**
   - Works with existing anti-detection
   - Handle search-specific CAPTCHAs
   - Support persistent profiles

### Priority 7: Advanced Features (Full-Fledged Scraper)
1. **Deep Review & Rating Analysis**
   - Individual review text, ratings, dates, verified badges
   - Review helpfulness votes, sentiment analysis
   - Review filtering by rating, date, verified purchase

2. **Questions & Answers (Q&A) Scraping**
   - Customer questions and seller responses
   - Q&A metadata (timestamps, helpful votes)
   - Pagination for extensive Q&A

3. **Price Intelligence & History**
   - Historical price tracking
   - Deal identification (Lightning Deals, coupons)
   - Restock alerts

4. **Seller & Marketplace Intelligence**
   - Buy box ownership tracking
   - All seller listings with prices/fulfillment
   - Seller performance metrics

5. **Media & Enhanced Content**
   - Complete image gallery in multiple resolutions
   - Product videos, 360° views
   - A+ Content extraction

6. **Category & Browse Navigation**
   - Bestseller lists by category
   - New releases, movers & shakers
   - Faceted navigation

7. **Product Relationship Intelligence**
   - "Also bought", "Frequently bought together"
   - Comparison tables
   - Related recommendations

8. **Advanced Anti-Bot & Stealth Features**
   - Intelligent rate limiting with adaptive delays
   - Proxy rotation with geo-targeting
   - User agent rotation
   - Browser fingerprint protection
   - CAPTCHA solving integration

9. **Data Management & Monitoring**
   - HTML caching to avoid re-scraping
   - Incremental scraping
   - Scheduling (cron-like)
   - Change detection and alerting
   - Database storage (SQLite, PostgreSQL)
   - Webhook/email/SMS notifications

10. **Flexible Export & Integration**
    - Multiple formats: CSV, Excel, JSONL, XML, Parquet
    - Configurable field selection
    - API endpoints
    - Data warehouse integrations

### Priority 8: Testing Improvements
1. **Add browser.py tests**
2. **Add models.py tests**
3. **Add integration tests**
4. **Add search functionality tests**
5. **Add edge case tests for new fields**

### Priority 9: Code Quality and Maintenance
1. **Add missing type hints**
2. **Improve documentation and docstrings**
3. **Better separation of concerns (modules for different page types)**

## Implementation Order (Revised Based on Current State)

1. **Bug fixes** (Priority 1) - 1 quick fix
2. **Browser session fixes** (Priority 2) - Persistent context leak + wait improvements
3. **NEW FEATURE: Search functionality** (Priority 6) - User requested
4. **CLI enhancements** (Priority 5) - Verbose output, config files, signal handling
5. **Parser enhancements** (Priority 3) - Additional fields
6. **Model improvements** (Priority 4) - Validation
7. **Advanced features** (Priority 7) - Professional-grade
8. **Testing** (Priority 8)
9. **Code quality** (Priority 9)

## Implementation Status

- [x] Priority 1: Bug Fix - Fix `_extract_availability` in parser.py
- [x] Priority 2: Browser Improvements - Context leak, wait_for_timeout, CAPTCHA
- [x] Priority 3: Parser Enhancements - Additional product fields (brand)
- [x] Priority 4: Model Improvements - Validation, schema version, brand field, scraped_at
- [x] Priority 5: CLI Enhancements - Verbose output, config, signals
- [x] Priority 6: Search Functionality - Search CLI args and parser
- [ ] Priority 7: Advanced Features - Professional-grade features
- [ ] Priority 8: Testing
- [ ] Priority 9: Code Quality

## Files to Modify

| File | Changes Needed |
|------|---------------|
| `scraper/parser.py` | Fix availability extraction, add search result parsing, additional fields |
| `scraper/browser.py` | Fix persistent context leak, replace wait_for_timeout with explicit waits, improve CAPTCHA |
| `scraper/models.py` | Add validation, schema version, metadata |
| `scraper.py` | Enhanced verbose output, config file support, signal handling, search CLI args |
| `tests/test_parser.py` | Search tests, new field tests |
| `tests/test_browser.py` (new) | Browser session tests |
| `tests/test_models.py` (new) | Model validation tests |
| `config.yaml.example` (new) | Configuration template |
| `README.md` (update) | Enhanced documentation |

## Expected Outcomes

After implementing these improvements, the scraper will:
1. Have fewer bugs (fix availability extraction, persistent context leak)
2. Properly clean up all browser resources
3. Extract more comprehensive product information
4. Provide better error handling and recovery
5. Be more configurable and user-friendly
6. Have comprehensive test coverage
7. Follow better coding practices
8. **NEW**: Support searching for products and scraping multiple results
9. **ENHANCED**: Professional-grade features matching user expectations from platforms like Apify