from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import tempfile
from pathlib import Path

from scraper import BrowserSession, ScrapeError, enrich_from_browser, parse_product

log = logging.getLogger("scraper")


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
    parser.add_argument("--retries", type=int, default=3, help="Max retries on failure")
    parser.add_argument("--timeout", type=int, default=30000, help="Navigation timeout in ms")
    parser.add_argument("--wait", type=int, default=5000, help="Extra wait time after page load (ms)")
    parser.add_argument("--zip", help="Set delivery zip code (e.g. 90035)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        format="%(levelname)s %(name)s: %(message)s",
        level=logging.DEBUG if args.verbose else logging.WARNING,
        stream=sys.stderr,
    )

    session = BrowserSession(
        headless=not args.headed,
        humanize=args.humanize,
        proxy=args.proxy,
        geoip=args.geoip,
        fingerprint=args.fingerprint,
        user_agent=args.user_agent,
        persistent=args.persistent,
    )

    page = None

    try:
        session.start()

        if args.zip:
            zip_page = session.set_zip_code(args.zip, verbose=args.verbose)
            if zip_page:
                zip_page.close()

        page = session.navigate_with_retry(
            args.url,
            retries=args.retries,
            timeout=args.timeout,
            wait=args.wait,
            verbose=args.verbose,
        )

        html = page.content()
        product = parse_product(html, url=args.url)
        product = enrich_from_browser(product, page)

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
