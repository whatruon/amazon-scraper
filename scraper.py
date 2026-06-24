from __future__ import annotations

import argparse
import json
import logging
import os
import random
import re
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlencode, parse_qs, urlparse

from scraper import BrowserSession, ScrapeError, enrich_from_browser, parse_product

log = logging.getLogger("scraper")

AMAZON_TRACKING_PARAMS = {
    "sbo", "tag", "ref", "ref_", "pf_rd_r", "pf_rd_p", "pf_rd_m",
    "pf_rd_s", "pf_rd_t", "pf_rd_i", "linkCode", "linkId", "language",
    "th", "psc", "smid", "coliid", "colid", "ie",
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


def atomic_write(path: Path, content: str) -> None:
    tmp = path.with_suffix(f".tmp.{os.getpid()}")
    tmp.write_text(content, encoding="utf-8")
    tmp.rename(path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scrape Amazon product details via CloakBrowser"
    )
    parser.add_argument("url", help="Amazon product URL (e.g. https://www.amazon.com/dp/B09XS7JWHH)")
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
    args = parser.parse_args()

    logging.basicConfig(
        format="%(levelname)s %(name)s: %(message)s",
        level=logging.DEBUG if args.verbose else logging.WARNING,
        stream=sys.stderr,
    )

    domain = _get_amazon_domain(args.url)
    session = BrowserSession(
        headless=not args.headed,
        humanize=args.humanize,
        proxy=args.proxy,
        geoip=args.geoip,
        fingerprint=args.fingerprint,
        user_agent=args.user_agent,
        persistent=args.persistent,
        domain=domain,
    )

    page = None
    product = None

    try:
        session.start()

        clean_url = _clean_amazon_url(args.url)
        if clean_url != args.url and args.verbose:
            log.info("Cleaned URL: %s", clean_url)

        for attempt in range(args.retries):
            if page:
                page.close()

            page = session.navigate_with_retry(
                clean_url,
                retries=args.retries,
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
                break

            missing = []
            if not product.price:
                missing.append("price")
            if not product.asin:
                missing.append("asin")
            if args.verbose:
                log.warning("Attempt %d/%d: missing %s, retrying...", attempt + 1, args.retries, ", ".join(missing))

            if attempt < args.retries - 1:
                time.sleep(2**attempt + random.uniform(0, 1))
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

        output_dir = Path("output")
        output_dir.mkdir(parents=True, exist_ok=True)

        if args.output:
            out_path = Path(args.output)
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
        log.error("Unexpected error: %s", e)
        sys.exit(1)

    finally:
        if page:
            page.close()
        session.stop()


if __name__ == "__main__":
    main()
