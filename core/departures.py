"""Scraper utilities for departures.to discovery and TestFlight status checks."""

import logging
import re
import time
from datetime import datetime
from typing import Any, Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://departures.to"
TESTFLIGHT_BASE = "https://testflight.apple.com/join/"

# RSS candidates. departures.to does not publish one canonical feed URL.
RSS_CANDIDATES = [
    "https://departures.to/rss",
    "https://departures.to/feed",
    "https://departures.to/rss.xml",
    "https://departures.to/feed.xml",
    "https://departures.to/apps.rss",
    "https://departures.to/feed/apps",
]

LISTING_PAGES = [
    f"{BASE_URL}/apps",
    f"{BASE_URL}/live",
    f"{BASE_URL}",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Cache-Control": "no-cache",
}

# Simple in-memory cache
_cache: dict[str, dict[str, Any]] = {}
CACHE_TTL = 300  # 5 minutes


def _is_cache_valid(key: str) -> bool:
    if key not in _cache:
        return False
    return (datetime.now() - _cache[key]["time"]).seconds < CACHE_TTL


def _set_cache(key: str, value: Any) -> None:
    _cache[key] = {"data": value, "time": datetime.now()}


def _get_cache(key: str) -> Any:
    return _cache.get(key, {}).get("data")


# ---------------------------------------------
# STEP 1: Try RSS feed first
# ---------------------------------------------
def _try_rss_feed() -> list[dict]:
    """Try RSS candidates and return parsed app rows if available."""
    for rss_url in RSS_CANDIDATES:
        try:
            response = requests.get(
                rss_url,
                headers=HEADERS,
                timeout=10,
                allow_redirects=True,
            )
            content_type = response.headers.get("Content-Type", "")

            if response.status_code == 200 and (
                "xml" in content_type
                or "rss" in content_type
                or response.text.strip().startswith("<?xml")
            ):
                logger.info("Found RSS feed at %s", rss_url)
                return _parse_rss(response.text)

            logger.debug("Not RSS: %s (status=%s)", rss_url, response.status_code)
        except Exception as exc:
            logger.debug("RSS candidate failed %s: %s", rss_url, exc)

    logger.warning("No working RSS feed found, fallback to HTML scraping")
    return []


def _parse_rss(xml_text: str) -> list[dict]:
    """Parse RSS XML into app rows with name/departures_id/departures_url."""
    apps = []
    soup = BeautifulSoup(xml_text, "xml")

    for item in soup.find_all("item"):
        try:
            title = item.find("title")
            link = item.find("link")
            if not title or not link:
                continue

            name = title.get_text(strip=True)
            url = link.get_text(strip=True)

            match = re.search(r"/apps/(\d+)", url)
            if not match:
                continue

            departures_id = match.group(1)
            apps.append(
                {
                    "name": name,
                    "departures_id": departures_id,
                    "departures_url": url,
                }
            )
        except Exception as exc:
            logger.debug("RSS item parse error: %s", exc)

    logger.info("RSS returned %d apps", len(apps))
    return apps


# ---------------------------------------------
# STEP 2: Scrape listing pages
# ---------------------------------------------
def _scrape_listing_page(url: str) -> list[dict]:
    """Scrape listing page and extract departures_id + name rows."""
    apps = []
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code != 200:
            logger.warning("Listing page %s returned %s", url, response.status_code)
            return []

        soup = BeautifulSoup(response.text, "html.parser")

        for anchor in soup.find_all("a", href=re.compile(r"^/apps/\d+")):
            href = str(anchor.get("href", ""))
            match = re.search(r"/apps/(\d+)", href)
            if not match:
                continue

            departures_id = match.group(1)
            name = ""
            heading = anchor.find(["h2", "h3", "h4", "strong"])
            if heading:
                name = heading.get_text(strip=True)
            if not name:
                name = anchor.get_text(strip=True)[:100]

            if name and departures_id:
                apps.append(
                    {
                        "name": name,
                        "departures_id": departures_id,
                        "departures_url": f"{BASE_URL}/apps/{departures_id}",
                    }
                )

        seen_ids = set()
        unique_apps = []
        for app in apps:
            if app["departures_id"] not in seen_ids:
                seen_ids.add(app["departures_id"])
                unique_apps.append(app)

        logger.info("Listing %s: found %d apps", url, len(unique_apps))
        return unique_apps
    except Exception as exc:
        logger.error("Listing scrape failed for %s: %s", url, exc)
        return []


def _get_all_listed_apps(limit: int = 50) -> list[dict]:
    """Scrape configured listing pages and return deduplicated recent rows."""
    all_apps = []
    seen_ids = set()

    for page_url in LISTING_PAGES:
        page_apps = _scrape_listing_page(page_url)
        for app in page_apps:
            if app["departures_id"] not in seen_ids:
                seen_ids.add(app["departures_id"])
                all_apps.append(app)

        if len(all_apps) >= limit:
            break

        time.sleep(0.5)

    return all_apps[:limit]


# ---------------------------------------------
# STEP 3: Direct TestFlight status check
# ---------------------------------------------
def check_testflight_status(app_id: str) -> str:
    """Return OPEN/CLOSED/UNKNOWN by checking the TestFlight join page."""
    if not app_id or len(app_id) < 5:
        return "UNKNOWN"

    url = f"{TESTFLIGHT_BASE}{app_id}"
    try:
        response = requests.get(
            url,
            headers={**HEADERS, "Accept": "text/html,application/xhtml+xml"},
            timeout=10,
            allow_redirects=True,
        )

        if response.status_code == 404:
            return "CLOSED"

        if response.status_code == 200:
            text = response.text
            if any(
                phrase in text
                for phrase in [
                    "This beta is full",
                    "beta is not accepting",
                    "no longer accepting",
                    "invite only",
                ]
            ):
                return "CLOSED"
            if any(
                phrase in text
                for phrase in [
                    "Start Testing",
                    "View in TestFlight",
                    "testflight://",
                    "JOIN THE BETA",
                ]
            ):
                return "OPEN"
            return "OPEN"

        return "UNKNOWN"
    except requests.exceptions.ConnectionError:
        return "UNKNOWN"
    except Exception as exc:
        logger.error("TestFlight status check failed for %s: %s", app_id, exc)
        return "UNKNOWN"


# ---------------------------------------------
# STEP 4: Resolve TestFlight app_id from detail
# ---------------------------------------------
def _resolve_testflight_id(departures_id: str) -> Optional[str]:
    """Try extracting a TestFlight app_id from departures detail page HTML."""
    url = f"{BASE_URL}/apps/{departures_id}"

    for user_agent in [
        HEADERS["User-Agent"],
        "Googlebot/2.1 (+http://www.google.com/bot.html)",
        "Mozilla/5.0 (compatible; bingbot/2.0)",
    ]:
        try:
            response = requests.get(
                url,
                headers={**HEADERS, "User-Agent": user_agent},
                timeout=10,
            )
            if response.status_code == 200:
                match = re.search(
                    r"testflight\.apple\.com/join/([A-Za-z0-9]{5,12})",
                    response.text,
                )
                if match:
                    tf_id = match.group(1)
                    logger.info(
                        "Resolved TestFlight app_id=%s for departures_id=%s",
                        tf_id,
                        departures_id,
                    )
                    return tf_id
        except Exception:
            pass
        time.sleep(0.3)

    logger.debug("Could not resolve TestFlight ID for departures_id=%s", departures_id)
    return None


# ---------------------------------------------
# PUBLIC API (used by handlers/scheduler)
# ---------------------------------------------
def get_open_apps_cached(limit: int = 30) -> list[dict]:
    """Return OPEN apps discovered from departures and verified via TestFlight."""
    cache_key = f"open_apps_{limit}"
    if _is_cache_valid(cache_key):
        return _get_cache(cache_key)

    result = []

    listed_apps = _try_rss_feed()
    if not listed_apps:
        listed_apps = _get_all_listed_apps(limit=limit)

    resolved_count = 0
    for app in listed_apps[:limit]:
        departures_id = app["departures_id"]
        name = app["name"]

        tf_id = _resolve_testflight_id(departures_id)
        if tf_id:
            status = check_testflight_status(tf_id)
            if status == "OPEN":
                result.append(
                    {
                        "app_id": tf_id,
                        "app_name": name,
                        "status": "OPEN",
                        "departures_id": departures_id,
                    }
                )
                resolved_count += 1

        time.sleep(0.3)
        if resolved_count >= limit:
            break

    logger.info(
        "get_open_apps_cached: %d OPEN apps from %d listed",
        len(result),
        len(listed_apps),
    )
    _set_cache(cache_key, result)
    return result


def find_app_on_departures(app_id: str) -> Optional[dict]:
    """Return minimal app info by checking TestFlight status directly."""
    cache_key = f"find_{app_id}"
    if _is_cache_valid(cache_key):
        return _get_cache(cache_key)

    status = check_testflight_status(app_id)
    result = {
        "app_id": app_id,
        "app_name": f"App {app_id}",
        "status": status,
        "departures_id": None,
    }

    _set_cache(cache_key, result)
    return result


def get_popular_apps_from_departures(limit: int = 20) -> list[dict]:
    """Compatibility alias used by scheduler sync."""
    return get_open_apps_cached(limit=limit)
