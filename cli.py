from __future__ import annotations

import argparse
import json
import logging
import os
import random
import re
import signal
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlencode, parse_qs, urlparse

from scraper import BrowserSession, HtmlCache, ScrapeError, enrich_from_browser, parse_product
from scraper.cache import atomic_write
from scraper.search import search_amazon

log = logging.getLogger("scraper")

_interrupted = False


def _handle_interrupt(signum: int, frame) -> None:
    """Set interrupt flag for graceful shutdown.  Call twice to force exit."""
    global _interrupted
    if _interrupted:
        sys.exit(1)
    _interrupted = True
    log.warning("Interrupt received — finishing current request, then saving partial results...")

AMAZON_TRACKING_PARAMS = {
    "sbo", "tag", "ref", "ref_", "pf_rd_r", "pf_rd_p", "pf_rd_m",
    "pf_rd_s", "pf_rd_t", "pf_rd_i", "linkCode", "linkId", "language",
    "th", "psc", "smid", "coliid", "colid", "ie",
    "sr", "s", "qid", "crid", "sprefix", "dchild", "rh", "pf", "keywords",
}


def _get_amazon_domain(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    if "amazon" in host:
        return host
    return "amazon.com"


def _clean_amazon_url(url: str) -> str:
    """Remove tracking query params that can trigger CAPTCHA."""
    parsed = urlparse(url)
    if "amazon" not in parsed.netloc:
        return url
    qs = parse_qs(parsed.query, keep_blank_values=True)
    clean_qs = {k: v for k, v in qs.items() if k not in AMAZON_TRACKING_PARAMS}
    if clean_qs:
        clean = parsed._replace(query=urlencode(clean_qs, doseq=True))
    else:
        clean = parsed._replace(query="")
    return clean.geturl()


def _interruptible_sleep(seconds: float) -> None:
    """Sleep in short intervals, checking _interrupted flag."""
    for _ in range(int(seconds * 10)):
        if _interrupted:
            return
        time.sleep(0.1)


def main() -> None:
    signal.signal(signal.SIGINT, _handle_interrupt)
    signal.signal(signal.SIGTERM, _handle_interrupt)

    parser = argparse.ArgumentParser(
        description="Scrape Amazon product details via CloakBrowser"
    )
    parser.add_argument("url", help="Amazon product URL (e.g. https://www.amazon.com/dp/B09XS7JWHH) or search term (with -s/--search)")
    parser.add_argument("-o", "--output", help="Output JSON file path")
    parser.add_argument("--headed", action="store_true", help="Show browser UI")
    parser.add_argument("--proxy", help="Proxy URL (e.g. http://user:pass@host:port)")
    parser.add_argument("--geoip", action="store_true", help="Auto-detect timezone/locale from proxy IP")
    parser.add_argument("--humanize", action="store_true", help="Enable human-like mouse/keyboard/scroll")
    parser.add_argument("--fingerprint", help="Fixed fingerprint seed for consistent identity")
    parser.add_argument("--persistent", metavar="NAME", help="Use persistent profile (name for profile dir)")
    parser.add_argument("--user-agent", help="Custom user agent string")
    parser.add_argument("--retries", type=int, default=2, help="Max retries on failure")
    parser.add_argument("--timeout", type=int, default=15000, help="Navigation timeout in ms")
    parser.add_argument("--wait", type=int, default=0, help="Extra wait time after page load (ms)")
    parser.add_argument("--zip", default="90035", help="Set delivery zip code (default: 90035)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")
    parser.add_argument("-s", "--search", action="store_true", help="Treat URL as a search term instead of product URL")
    parser.add_argument("-n", "--max-results", type=int, default=5, help="Maximum number of search results to scrape (default: 5)")
    parser.add_argument("--cache", action="store_true", help="Enable HTML caching (reuse previously fetched pages)")
    parser.add_argument("--cache-dir", default="cache", help="Cache directory (default: cache/)")
    parser.add_argument("--cache-ttl", type=int, default=3600, help="Cache TTL in seconds (default: 3600)")
    parser.add_argument("--profile-dir", default="profiles", help="Directory for persistent profiles (default: profiles/)")
    parser.add_argument("--domain", help="Amazon domain (e.g. amazon.co.uk). Overrides auto-detection from URL.")
    args = parser.parse_args()

    logging.basicConfig(
        format="%(levelname)s %(name)s: %(message)s",
        level=logging.DEBUG if args.verbose else logging.WARNING,
        stream=sys.stderr,
    )

    domain = args.domain if args.domain else _get_amazon_domain(args.url)
    session = BrowserSession(
        headless=not args.headed,
        humanize=args.humanize,
        proxy=args.proxy,
        geoip=args.geoip,
        fingerprint=args.fingerprint,
        user_agent=args.user_agent,
        persistent=args.persistent,
        profile_dir=Path(args.profile_dir),
        domain=domain,
    )

    cache = HtmlCache(args.cache_dir, args.cache_ttl) if args.cache else None

    page = None
    product = None
    results = []
    all_products: list = []

    try:
        session.start()

        clean_url = _clean_amazon_url(args.url)
        if clean_url != args.url and args.verbose:
            log.info("Cleaned URL: %s", clean_url)

        if args.search:
            # Search mode
            results = search_amazon(
                session=session,
                query=args.url,
                max_results=args.max_results,
                timeout=args.timeout,
                wait=args.wait,
                verbose=args.verbose,
            )

            # Note: zip code is set on individual product pages below but not on the
            # search results page itself. Amazon may show region-specific results.

            if args.verbose:
                log.info("Found %d search results", len(results))

            # Process each result
            for i, url in enumerate(results):
                if _interrupted:
                    break
                if args.verbose:
                    log.info("Processing result %d/%d: %s", i + 1, len(results), url)

                try:
                    # Check cache before navigation
                    if cache:
                        cached_html = cache.get(url)
                        if cached_html is not None:
                            cached_product = parse_product(cached_html, url=url)
                            if cached_product.price and cached_product.asin:
                                if args.verbose:
                                    log.info("Using cached HTML for %s", url)
                                all_products.append(cached_product)
                                if _interrupted:
                                    break
                                continue

                    for attempt in range(args.retries):
                        if page:
                            page.close()

                        page = session.navigate_with_retry(
                            url,
                            retries=1,
                            timeout=args.timeout,
                            wait=args.wait,
                            verbose=args.verbose,
                        )

                        session.set_zip_code(page, zip_code=args.zip, verbose=args.verbose)

                        page.wait_for_timeout(1500)

                        html = page.content()
                        product = parse_product(html, url=url)
                        product = enrich_from_browser(product, page)

                        if product.price and product.asin:
                            if cache:
                                cache.put(url, html)
                            break

                        missing = []
                        if not product.price:
                            missing.append("price")
                        if not product.asin:
                            missing.append("asin")
                        if args.verbose and attempt < args.retries - 1:
                            log.warning("Attempt %d/%d: missing %s, retrying...", attempt + 1, args.retries, ", ".join(missing))

                        if attempt < args.retries - 1:
                            _interruptible_sleep(2**attempt + random.uniform(0, 1))
                    else:
                        missing = []
                        if not product.price:
                            missing.append("price")
                        if not product.asin:
                            missing.append("asin")
                        log.warning("Skipping result %d due to missing %s", i + 1, ", ".join(missing))
                        continue

                    if args.verbose:
                        log.info("Result %d: %s - %s", i + 1, product.title or "No title", product.price or "No price")

                    all_products.append(product)

                    if _interrupted:
                        break

                except Exception as e:
                    if args.verbose:
                        log.warning("Error processing result %d: %s", i + 1, e)
                    continue

            # Output results
            output_data = [p.to_dict() for p in all_products]
            json_output = json.dumps(output_data, indent=2, ensure_ascii=False)

            if args.output:
                out_path = Path(args.output)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                atomic_write(out_path, json_output)
            else:
                print(json_output)

        else:
            # Product mode (original behavior)

            # Check cache before hitting Amazon
            if cache:
                cached_html = cache.get(clean_url)
                if cached_html is not None:
                    cached_product = parse_product(cached_html, url=args.url)
                    if cached_product.price and cached_product.asin:
                        product = cached_product
                        if args.verbose:
                            log.info("Using cached HTML for %s", clean_url)

            if product is None:
                for attempt in range(args.retries):
                    if page:
                        page.close()

                    page = session.navigate_with_retry(
                        clean_url,
                        retries=1,
                        timeout=args.timeout,
                        wait=args.wait,
                        verbose=args.verbose,
                    )

                    session.set_zip_code(page, zip_code=args.zip, verbose=args.verbose)

                    page.wait_for_timeout(1500)

                    html = page.content()
                    product = parse_product(html, url=args.url)
                    product = enrich_from_browser(product, page)

                    if product.price and product.asin:
                        if cache:
                            cache.put(clean_url, html)
                        break

                    missing = []
                    if not product.price:
                        missing.append("price")
                    if not product.asin:
                        missing.append("asin")
                    if args.verbose:
                        log.warning("Attempt %d/%d: missing %s, retrying...", attempt + 1, args.retries, ", ".join(missing))

                    if attempt < args.retries - 1:
                        _interruptible_sleep(2**attempt + random.uniform(0, 1))
                else:
                    missing = []
                    if not product.price:
                        missing.append("price")
                    if not product.asin:
                        missing.append("asin")
                    raise ScrapeError(clean_url, f"missing {', '.join(missing)} after {args.retries} attempts", "parse")

            if args.verbose:
                log.info("URL: %s", args.url)
                log.info("Title: %s", product.title)
                log.info("Price: %s", product.price)
                log.info("Rating: %s", product.rating)
                log.info("Reviews: %s", product.review_count)
                log.info("ASIN: %s", product.asin)
                log.info("Availability: %s", product.availability)
                log.info("Images: %d", len(product.images))
                log.info("Bullet points: %d", len(product.bullets))

            output_dir = Path("output")
            output_dir.mkdir(parents=True, exist_ok=True)

            if args.output:
                out_path = Path(args.output)
                out_path.parent.mkdir(parents=True, exist_ok=True)
            else:
                asin = "product"
                m = re.search(r"/dp/([A-Z0-9]{10})", args.url)
                if m:
                    asin = m.group(1)
                else:
                    m = re.search(r"/gp/product/([A-Z0-9]{10})", args.url)
                    if m:
                        asin = m.group(1)
                out_path = output_dir / f"{asin}.json"

            json_output = product.to_json()
            atomic_write(out_path, json_output)
            print(json_output)

    except ScrapeError as e:
        log.error("%s", e)
        sys.exit(1)

    except Exception as e:
        log.error("Unexpected error: %s", e, exc_info=True)
        sys.exit(1)

    finally:
        if _interrupted and (all_products or product):
            if not all_products:
                all_products = [product]
            partial = [p.to_dict() for p in all_products]
            partial_path = (
                Path(args.output).with_suffix(".partial.json")
                if args.output
                else Path("output") / "partial.json"
            )
            partial_path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write(partial_path, json.dumps(partial, indent=2, ensure_ascii=False))
            log.warning("Saved %d partial result(s) to %s", len(all_products), partial_path)
        if page:
            try:
                page.close()
            except Exception:
                pass
        session.stop()


if __name__ == "__main__":
    main()
