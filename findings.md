# Amazon Scraper — Full Code Review Findings

> Generated 2026-07-23 via 4-agent workflow (Safety, Logic, Architecture, CLI).  
> 49 findings total: 4 critical, 14 high, 17 medium, 14 low.

---

## Critical

### 1. Path traversal in persistent profile directory name
- **File:** `scraper/browser.py:120`
- **Category:** security

The `persistent_name` parameter (from CLI `--persistent` flag) is used unsanitized as a directory name via `self.profile_dir / self.persistent_name` and then `profile_path.mkdir(parents=True, exist_ok=True)`. An attacker or malicious input like `--persistent ../../etc/cron/evil` would traverse upward from the intended profiles directory. Because `mkdir(parents=True)` creates intermediate directories, this can create directories anywhere the process has write access, and the subsequent `launch_persistent_context(str(profile_path), **kwargs)` will write Playwright profile data (cookies, localStorage, extensions) into attacker-controlled locations.

---

### 2. Review dedup set reset inside pagination loop
- **File:** `scraper/review.py:61`
- **Category:** correctness

`seen_reviews = set()` is declared inside `while len(reviews) < max_reviews:`, so it is re-initialized to empty on every pagination iteration. Reviews from different pages are never deduplicated against each other. If pagination fails silently and the same page content is re-read, every review on the page is duplicated in the output. The dedup set must be moved outside the while loop to cover all pages.

---

### 3. Namespace collision between scraper.py and scraper/ package
- **File:** `scraper.py:17`
- **Category:** design

The file `scraper.py` and the directory `scraper/` (containing `__init__.py`) share the Python import name `scraper`. When `scraper.py` executes `from scraper import BrowserSession, HtmlCache, ...`, it relies on Python resolving `scraper` to the package directory rather than to itself. This is fragile: import order, tooling (IDEs, linters, type checkers), and future Python versions may resolve this differently. Rename the CLI entry point to `cli.py` or `__main__.py` to eliminate the conflict.

---

### 4. Product mode interrupt loses all data
- **File:** `scraper.py:283`
- **Category:** correctness

The `finally` block at line 330 checks `if _interrupted and all_products:`, but in product mode (non-search) `all_products` is always the empty list `[]` initialized at line 121. It is only ever populated in search mode (line 213). If a user hits Ctrl+C during product mode scraping, `all_products` evaluates to falsy and the partial-results block is skipped entirely, discarding the single product being scraped. The `product` variable at line 119 holds the in-progress result and should be saved instead.

---

## High

### 5. CAPTCHA handling only matches one narrow selector
- **File:** `scraper/browser.py:247`
- **Category:** robustness
- **Status:** BY DESIGN — The scraper targets the specific "Continue shopping" automated-access gate. More sophisticated CAPTCHA variants require human intervention and are outside the scope of automated handling. Failures are handled by the retry/navigation logic.

---

### 6. Search-mode CAPTCHA handling silently ignores all but one variant
- **File:** `scraper/search.py:56`
- **Category:** robustness

The same single-selector CAPTCHA detection from browser.py is duplicated in search.py. Worse, the exception from `page.wait_for_selector('[data-component-type="s-search-result"]', timeout=10000)` is caught and silently passed via bare `except Exception: pass`. If any non-button CAPTCHA variant is encountered, the code silently proceeds to parse the CAPTCHA page as a search results page, producing zero results with no warning logged.

---

### 7. Proxy credentials leak risk
- **File:** `scraper/browser.py:111`
- **Category:** security

The `proxy` parameter is stored as `self.proxy` (a raw URL like `http://user:pass@host:port`) and forwarded to CloakBrowser's `launch()` and `launch_persistent_context()` functions. If CloakBrowser raises an exception that includes the proxy URL in its message (e.g., connection errors, auth failures), the credentials will appear in logs and crash output. The `ScrapeError` at line 296 also includes `str(last_exc)` which could transitively include proxy auth credentials. No redaction or masking is applied anywhere in the chain.

---

### 8. Browser price extraction only matches $ currency
- **File:** `scraper/parser.py:60`
- **Category:** correctness

The JavaScript regex in `_extract_price_from_browser` is `/\\$\\d+(?:,\\d{3})*(?:\\.\\d{2})?/`, which only matches the `$` currency symbol. The soup-based extraction supports $, £, €, ¥, and ₹, but when soup extraction fails and falls back to the browser, non-USD prices silently return None. The JS regex should match the same set of currency symbols.

---

### 9. Savings amount hardcodes $ currency symbol
- **File:** `scraper/price_tracker.py:67`
- **Category:** correctness

The formatted savings string `f"${savings:.2f}"` always uses the dollar sign, regardless of the product's actual currency. The `current_price` and `original_price` strings could contain £, €, ¥, ₹, or other symbols. The `savings_amount` should either inherit the currency symbol from the original prices or store the amount as a numeric value without any symbol.

---

### 10. Invalid CSS selector in FBA detection
- **File:** `scraper/seller.py:126`
- **Category:** correctness

The selector `#usp fulfullment-message` has two issues: (1) "fulfullment" is misspelled, and (2) `fulfullment-message` has no CSS class prefix (`.` or `#`), so it is interpreted as an element tag name selector matching a custom HTML element that will never exist on an Amazon page. This FBA detection path is effectively dead code.

---

### 11. PRICE_SELECTORS list duplicated in JS string
- **File:** `scraper/parser.py:13`
- **Category:** maintainability

The CSS container selectors `PRICE_SELECTORS` (lines 13-23) are hardcoded as a Python list. The same selectors (a subset) are hardcoded again inside a JS template string in `_extract_price_from_browser` (lines 47-55). Any change to one must be manually mirrored in the other. Define the list once (e.g., as a module constant) and reference it when building the JS expression.

---

### 12. enrich_from_browser mutates its Product argument in-place
- **File:** `scraper/parser.py:280`
- **Category:** design

`enrich_from_browser` takes a `Product` object and may set `product.price` as a side effect, then returns the same object. Callers depend on the return value but may not realize the input object was mutated. Either make it a pure function that returns a new Product, or make it a method on the Product class.

---

### 13. f-string logging defeats lazy evaluation
- **File:** `scraper/price_tracker.py:73`, `review.py:100`, `review.py:159`, `seller.py:71`
- **Category:** performance

Multiple modules use f-string formatting in logging calls (e.g., `log.warning(f"...{e}")`). This defeats lazy evaluation — the string is formatted even when the log level is below WARNING, wasting CPU cycles. Use `log.warning("...%s", e)` style with `%s` placeholders throughout.

---

### 14. Broad except Exception across multiple modules
- **File:** `scraper/browser.py:229`, `review.py:99`, `seller.py:70`, `price_tracker.py:72`
- **Category:** robustness

`set_zip_code` (line 229) and `navigate_with_retry` (line 287) both wrap large blocks in `except Exception`, swallowing all errors. `set_zip_code` never signals failure to the caller (returns None in all paths). Catch specific exception types and propagate or surface failures appropriately.

---

### 15. Unnecessary lazy imports
- **File:** `scraper/search.py:34`, `price_tracker.py:80`
- **Category:** maintainability

Both modules use function-level lazy imports (`from .parser import ...`) to avoid circular dependencies. However, the import graph is acyclic, so top-level imports would work. Lazy imports mislead readers about module dependencies and defeat static analysis.

---

### 16. Double retry loop causes quadratic navigation attempts
- **File:** `scraper.py:165`
- **Category:** correctness

The outer `for attempt in range(args.retries)` loop wraps a call to `session.navigate_with_retry(url, retries=args.retries, ...)`, which itself retries navigation up to `args.retries` times. With the default `--retries=2`, each URL may be navigated up to 4 times (2×2). With `--retries=3`, up to 9 times. Use `retries=1` inside the loop or separate the retry budgets.

---

### 17. Search mode cannot target a non-.com Amazon domain
- **File:** `scraper.py:104`
- **Category:** design

When `--search` is used, `args.url` is a plain search term. The domain is derived via `_get_amazon_domain(args.url)`, which calls `urlparse` on the search term. Since a plain search term has no netloc, `_get_amazon_domain` always falls back to `"amazon.com"`. There is no `--domain` CLI argument, so users cannot search on other regional domains.

---

### 18. Important missing-field warnings hidden behind --verbose
- **File:** `scraper.py:195`
- **Category:** design

Warnings about missing price/ASIN that cause a search result to be skipped are gated behind `if args.verbose`. A user running at the default WARNING level sees no output when a result is silently dropped. The skip message explaining why fewer results were returned should be unconditional at WARNING level.

---

## Medium

### 19. Overly broad exception catch in search silently swallows all errors
- **File:** `scraper/search.py:101`
- **Category:** robustness

Lines 101-103 catch `Exception` broadly: the exception is only logged at `verbose` level via a generic warning. All errors produce the same non-diagnostic message. The caller receives an empty results list and cannot distinguish between "no products found" and "the entire request failed."

---

### 20. atomic_write temp files leak on crash
- **File:** `scraper/cache.py:192`
- **Category:** robustness

The `atomic_write` function creates a temp file at `path.with_suffix(f'{path.suffix}.tmp.{os.getpid()}')`. If the process crashes between `write_text` and `rename`, the `.tmp.<PID>` file is left behind permanently with no cleanup mechanism. Orphaned temp files can accumulate in the cache directory, potentially containing cached HTML content with product URLs and ASINs.

---

### 21. CAPTCHA click never verifies resolution
- **File:** `scraper/browser.py:248`
- **Category:** robustness

After clicking the CAPTCHA "Continue shopping" button, the code returns the current page immediately if the product-selector wait passes. It never verifies the CAPTCHA challenge was actually solved — the button could have been a dismissible overlay, or the click could have navigated to an Amazon error page.

---

### 22. parse_search_results discards non-/dp/ product paths
- **File:** `scraper/parser.py:233`
- **Category:** robustness

The guard `if href and "/dp/" in href` filters out all URLs that do not contain `/dp/` in their path. Amazon search result links can use `/gp/product/` or `/product/` paths for some items (especially categories like books, video games, or international listings). These valid product URLs are silently discarded.

---

### 23. Helpful votes regex does not capture number words
- **File:** `scraper/review.py:143`
- **Category:** robustness

The regex `(\\d+|One)` only captures digits or the literal word "One". Number words like "Two", "Three", etc. are not matched. Reviews with phrasing like "Two people found this helpful" produce `helpful_votes = None` even though the count is present.

---

### 24. Seller rating loop breaks prematurely
- **File:** `scraper/seller.py:182`
- **Category:** robustness

The inner loop breaks as soon as EITHER `rating_text` or `rating_count` is found from a single selector element. If the first matching selector contains a rating but no count, the loop stops without trying other selectors that may contain the count.

---

### 25. Substring match false positive in buybox owner detection
- **File:** `scraper/seller.py:229`
- **Category:** correctness

The check `if 'sold by' in seller_text.lower()` is a substring match that can trigger on any text containing "sold by", even in irrelevant contexts (e.g., "This product cannot be sold by unauthorized resellers"). Use regex with word boundaries for more precise matching.

---

### 26. ASIN extraction requires uppercase letters
- **File:** `scraper/parser.py:188`
- **Category:** robustness

The URL regex `/(?:dp|gp/product|product)/([A-Z0-9]{10})` only captures uppercase ASIN characters. While Amazon URLs conventionally use uppercase, a lowercase ASIN in the URL would silently return None. Uppercase the extracted candidate or use `[A-Za-z0-9]` and then normalize.

---

### 27. Image base normalization regex may produce false dedups
- **File:** `scraper/parser.py:133`
- **Category:** edge-case

The regex `\\._(AC|SX|SY|SL|SS|US|SR|FM|UX|V1|BG|PK)[^.]*_\\.` normalizes size markers in image URLs for deduplication. The greedy `[^.]*` could match across multiple size tokens, collapsing distinct image variants. The alternation tokens are short enough to appear coincidentally in unrelated URL path segments.

---

### 28. validate_price accepts 4+ consecutive digits without thousands separators
- **File:** `scraper/models.py:46`
- **Category:** edge-case

The regex branch `|\\d{4,}` allows prices like "$12345" (four or more consecutive digits without commas). While this could match valid large prices, it also accepts malformed scraping artifacts where commas were stripped, such as "$1234567" (which should be "$1,234,567").

---

### 29. Cache defeats browser-side price extraction
- **File:** `scraper.py:237`
- **Category:** performance

`enrich_from_browser()` fills `product.price` via JavaScript evaluation when the static HTML lacks it. However, the cache stores raw HTML only. When a cached entry is later read, `parse_product` only inspects static HTML and cannot recover the browser-side price. If the price is JS-only, the cache entry is rejected and the product is re-fetched. Cache the enriched Product alongside the HTML.

---

### 30. page.close() in finally block can prevent session.stop()
- **File:** `scraper.py:340`
- **Category:** robustness

If `page.close()` raises (e.g. because the page is from a closed context or the browser connection was interrupted), `session.stop()` is never reached, leaving the browser process and context open. Wrap in try/except.

---

### 31. Generic exception handler omits traceback
- **File:** `scraper.py:325`
- **Category:** maintainability

The `except Exception as e` handler calls `log.error('Unexpected error: %s', e)` without `exc_info=True`. Even with `--verbose`, no stack trace is printed. Add `exc_info=True`.

---

### 32. Explicit --output path fails when parent directory doesn't exist
- **File:** `scraper.py:228`
- **Category:** correctness

When `-o /some/deep/path/file.json` is specified, `atomic_write` calls `Path.write_text` without creating parent directories. The product mode default path creates `output/`, but explicit `-o` paths do not. Call `out_path.parent.mkdir(parents=True, exist_ok=True)` before writing.

---

### 33. Fragile importlib reimport of scraper.py CLI module
- **File:** `tests/test_browser.py:196`
- **Category:** test-coverage

Tests use `importlib.util.spec_from_file_location` to load `scraper.py` as a separate module to test `_clean_amazon_url` and `_get_amazon_domain`. This breaks if the file moves or import structure changes. Move URL-cleaning utilities to a shared module.

---

### 34. max_pages hardcoded and not configurable
- **File:** `scraper/search.py:43`
- **Category:** maintainability

The pagination limit `max_pages = 3` is hardcoded inside the function. Should be a parameter with a default or drawn from configuration.

---

### 35. Missing test coverage for three modules
- **File:** Multiple
- **Category:** test-coverage

No test files exist for `price_tracker.py`, `review.py`, `seller.py`, or the `enrich_from_browser` function. These modules contain significant extraction logic with multiple fallback paths that need unit tests.

---

### 36. Duplicate atomic_write function
- **File:** `scraper.py:64`, `cache.py:192`
- **Category:** maintainability

`atomic_write` is defined identically in both files. Differs in temp-file naming (the cache version preserves the original suffix). `scraper.py` already imports `HtmlCache` from cache and could reuse it.

---

### 37. BrowserSession profile_dir not exposed as CLI argument
- **File:** `scraper.py:105`
- **Category:** design

`BrowserSession` accepts a `profile_dir` parameter (default `Path('profiles')`), but `scraper.py` hardcodes it. Users with `--persistent NAME` cannot choose where profiles are stored.

---

## Low

### 38. All locale overrides set en-US
- **File:** `scraper/browser.py:26`
- **Category:** robustness

The `DOMAIN_LOCALE` dictionary maps every Amazon domain to a `(timezone, 'en-US')` tuple. Visiting amazon.de with `en-US` locale is a detectable inconsistency that makes the session stand out to bot-detection systems.

---

### 39. Cache key truncated to 64 bits
- **File:** `scraper/cache.py:160`
- **Category:** correctness

Cache key uses `sha256(url)[:16]`, which is only the first 16 hex characters = 64 bits. Theoretically possible but not practical at this scale.

---

### 40. Search query not properly URL-encoded
- **File:** `scraper/search.py:37`
- **Category:** security

The search query is URL-encoded by only replacing spaces with plus signs. Special characters like `&`, `%`, `#`, or `=` are not percent-encoded, allowing partial URL manipulation through search input. Use `urllib.parse.quote_plus()`.

---

### 41. Duplicated regex alternation
- **File:** `scraper/seller.py:95`
- **Category:** maintainability

The alternation `Visit the|Visit the` contains "Visit the" twice — a copy-paste oversight.

---

### 42. Redundant re-extraction of seller name in buybox check
- **File:** `scraper/seller.py:233`
- **Category:** performance

`_is_buybox_owner` calls `_extract_seller_name(soup)`, but `scrape_seller_info` already called it. Accept the already-extracted name as a parameter.

---

### 43. Redundant condition for helpful votes
- **File:** `scraper/review.py:147`
- **Category:** maintainability

The second condition "'One person found this helpful' in helpful_text" is strictly redundant — any such text also contains "One person" which is checked first.

---

### 44. to_json() redundantly re-assigns schema_version
- **File:** `scraper/models.py:29`
- **Category:** maintainability

`data["schema_version"] = self.schema_version` is redundant because `to_dict()` calls `dataclasses.asdict(self)` which already includes `schema_version`.

---

### 45. Currency symbols limited to $£€¥₹
- **File:** `scraper/models.py:46`
- **Category:** edge-case

The currency character class `[$£€¥₹]` only supports five symbols. Amazon operates in dozens of countries (e.g., Brazil uses `R$`, Mexico uses `MX$`). Prices from these locales will fail validation.

---

### 46. pyproject.toml missing runtime dependencies
- **File:** `pyproject.toml:16`
- **Category:** maintainability

The `[project]` section has no `dependencies` list, yet the code requires playwright, beautifulsoup4, lxml, cloakbrowser, and other packages.

---

### 47. Overly broad DeprecationWarning suppression
- **File:** `pyproject.toml:21`
- **Category:** test-coverage

`filterwarnings = ["ignore::DeprecationWarning"]` hides ALL deprecation warnings, including those signaling upcoming breakage.

---

### 48. Search URL construction logic is duplicated
- **File:** `scraper/search.py:37`
- **Category:** maintainability

The search URL formula appears at line 37 for the first page and again at line 50 for paginated pages. Unify into a helper function.

---

### 49. time.sleep() during retry is not interrupt-safe
- **File:** `scraper.py:199`
- **Category:** edge-case

The signal handler for SIGINT/SIGTERM sets an `_interrupted` flag rather than raising `KeyboardInterrupt`. Since `time.sleep()` is not interrupted by a flag-based handler, Ctrl+C during a backoff sleep has no effect until the sleep completes.

---

### 50. Zip code not set on search results page
- **File:** `scraper.py:177`
- **Category:** edge-case

`session.set_zip_code()` is called on each individual product page but never on the search results page. Amazon search results may show different products or prices based on delivery location, so skipping this could produce inconsistent results.
