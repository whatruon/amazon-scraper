from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from pathlib import Path

from scraper import BrowserSession, ScrapeError, enrich_from_browser, parse_product

log = logging.getLogger("scraper")


def load_dotenv(path: Path = Path(".env")) -> None:
    """Load KEY=VALUE lines from .env into os.environ (no overwrite)."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


# Amazon marketplace domain -> manager profile name (each profile routes to the
# matching marketplace with the right locale/timezone).
DOMAIN_TO_PROFILE = {
    "amazon.ae": "Amazon UAE",
    "amazon.de": "Amazon DE",
    "amazon.co.uk": "Amazon UK",
    "amazon.com": "Amazon US",
}


def profile_for_url(url: str, profiles: list[dict]) -> tuple[str, str]:
    """Pick the manager profile whose marketplace matches the URL's domain.

    Returns (profile_id, profile_name); raises ValueError on an unknown domain
    or a missing profile so a mismatched marketplace never scrapes wrong prices.
    """
    import urllib.parse

    host = urllib.parse.urlparse(url).netloc.lower()
    # Longest suffix first so amazon.co.uk wins over a hypothetical amazon.co.
    for domain in sorted(DOMAIN_TO_PROFILE, key=len, reverse=True):
        if host == domain or host.endswith("." + domain):
            name = DOMAIN_TO_PROFILE[domain]
            for p in profiles:
                if p["name"] == name:
                    return p["id"], name
            raise ValueError(f"No manager profile named {name!r} for {domain}")
    raise ValueError(f"Unsupported Amazon domain in URL: {host or url!r}")


def list_profiles(base_url: str, api_key: str) -> list[dict]:
    import urllib.request

    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/profiles",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def launch_manager_profile(base_url: str, api_key: str, profile_id: str):
    """Launch a CloakBrowser-manager profile and return (cdp_url, headers)."""
    import urllib.request

    base = base_url.rstrip("/")
    headers = {"Authorization": f"Bearer {api_key}"}
    req = urllib.request.Request(
        f"{base}/api/profiles/{profile_id}/launch", method="POST", headers=headers
    )
    try:
        urllib.request.urlopen(req, timeout=60).read()
    except urllib.error.HTTPError as e:
        if e.code != 409:  # 409 = already running, which is fine
            raise
    return f"{base}/api/profiles/{profile_id}/cdp", headers


def atomic_write(path: Path, content: str) -> None:
    tmp = path.with_suffix(f".tmp.{os.getpid()}")
    tmp.write_text(content, encoding="utf-8")
    tmp.rename(path)


def main() -> None:
    load_dotenv(Path(__file__).parent / ".env")
    parser = argparse.ArgumentParser(
        description="Scrape Amazon product details via CloakBrowser"
    )
    parser.add_argument("url", help="Amazon product URL (e.g. https://www.amazon.com/dp/B09XS7JWHH)")
    parser.add_argument("-o", "--output", help="Output JSON file path")
    parser.add_argument("--retries", type=int, default=3, help="Max retries on failure")
    parser.add_argument("--timeout", type=int, default=30000, help="Navigation timeout in ms")
    parser.add_argument("--wait", type=int, default=5000, help="Extra wait time after page load (ms)")
    parser.add_argument("--zip", help="Set delivery zip code (e.g. 90035)")
    parser.add_argument("--manager", default=os.environ.get("CLOAK_MANAGER_URL"),
                        help="CloakBrowser manager base URL (env: CLOAK_MANAGER_URL)")
    parser.add_argument("--manager-key", default=os.environ.get("CLOAK_MANAGER_KEY"),
                        help="Manager API key / Bearer token (env: CLOAK_MANAGER_KEY)")
    parser.add_argument("--profile-id", default=os.environ.get("CLOAK_PROFILE_ID"),
                        help="Override profile ID (default: auto-routed from the URL's Amazon domain)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        format="%(levelname)s %(name)s: %(message)s",
        level=logging.DEBUG if args.verbose else logging.WARNING,
        stream=sys.stderr,
    )

    if not (args.manager and args.manager_key):
        parser.error("--manager and --manager-key are required "
                     "(or set CLOAK_MANAGER_URL / CLOAK_MANAGER_KEY)")

    profile_id = args.profile_id
    if not profile_id:
        try:
            profile_id, name = profile_for_url(
                args.url, list_profiles(args.manager, args.manager_key)
            )
        except ValueError as e:
            parser.error(str(e))
        if args.verbose:
            log.info("Routed %s -> profile %s (%s)", args.url, name, profile_id)

    cdp_url, cdp_headers = launch_manager_profile(
        args.manager, args.manager_key, profile_id
    )
    session = BrowserSession(cdp_url=cdp_url, cdp_headers=cdp_headers)

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
