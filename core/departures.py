"""Scraping helpers for departures.to app discovery."""

import logging
import re
import time
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://departures.to"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; TestFlightWatcherBot/1.0)",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}

_cache = {"data": [], "expires_at": datetime.min}
_search_cache: dict[str, dict] = {}
_popular_cache = {"data": [], "expires_at": datetime.min}


def _fetch_url(url: str) -> Optional[str]:
    """Fetch HTML from a URL with retries."""
    for attempt in range(3):
        try:
            response = requests.get(url, headers=HEADERS, timeout=8)
            if response.status_code != 200:
                raise requests.RequestException(f"Unexpected status code {response.status_code}")
            return response.text
        except requests.RequestException as exc:
            if attempt == 2:
                logger.warning("departures.to request failed for %s: %s", url, exc)
                return None
            time.sleep(2)
    return None


def _extract_departures_ids_from_listing(html: str) -> list[int]:
    """Extract departures app ids from listing HTML."""
    soup = BeautifulSoup(html, "html.parser")
    ids: list[int] = []
    seen: set[int] = set()
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        match = re.search(r"/apps/(\d+)", href)
        if match:
            departures_id = int(match.group(1))
            if departures_id not in seen:
                seen.add(departures_id)
                ids.append(departures_id)
    return ids


def _collect_departures_ids(max_pages: int = 3) -> list[int]:
    """Collect departures ids from a few listing pages."""
    all_ids: list[int] = []
    seen: set[int] = set()

    for page in range(1, max_pages + 1):
        url = f"{BASE_URL}/apps" if page == 1 else f"{BASE_URL}/apps?page={page}"
        html = _fetch_url(url)
        if not html:
            continue

        page_ids = _extract_departures_ids_from_listing(html)
        new_ids = [departures_id for departures_id in page_ids if departures_id not in seen]
        for departures_id in new_ids:
            seen.add(departures_id)
            all_ids.append(departures_id)

        if not new_ids:
            break

        if page < max_pages:
            time.sleep(1)

    return all_ids


def scrape_app_detail(departures_id: int) -> dict | None:
    """Scrape a departures.to app detail page and return structured metadata."""
    url = f"{BASE_URL}/apps/{departures_id}"
    html = _fetch_url(url)
    if not html:
        return None

    soup = BeautifulSoup(html, "html.parser")

    heading = soup.find(["h1", "h2"])
    app_name = heading.get_text(" ", strip=True) if heading else ""

    testflight_url = ""
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        if "testflight.apple.com/join/" in href:
            testflight_url = href if href.startswith("http") else urljoin(BASE_URL, href)
            break

    app_id = None
    if testflight_url:
        match = re.search(r"testflight\.apple\.com/join/([A-Za-z0-9]{8})", testflight_url, re.IGNORECASE)
        if match:
            app_id = match.group(1).upper()

    if not app_id:
        return None

    categories: list[str] = []
    seen_categories: set[str] = set()
    for node in soup.select('[class*="category"], a[href*="/categories/"], span, a'):
        text = node.get_text(" ", strip=True)
        href = node.get("href", "") if hasattr(node, "get") else ""
        if not text:
            continue
        lowered = text.lower()
        if len(text) > 40:
            continue
        if any(token in lowered for token in ["now boarding", "full", "closed", "testflight"]):
            continue
        if href and "/categories/" not in href and "category" not in str(node.get("class", [])).lower():
            continue
        if text not in seen_categories:
            seen_categories.add(text)
            categories.append(text)

    description = ""
    paragraph = soup.find("p")
    if paragraph:
        description = paragraph.get_text(" ", strip=True)

    page_text = soup.get_text(" ", strip=True).lower()
    status = "UNKNOWN"
    if "now boarding" in page_text:
        status = "OPEN"
    elif "full" in page_text or "closed" in page_text:
        status = "CLOSED"

    return {
        "app_name": app_name or f"Departure App {departures_id}",
        "app_id": app_id,
        "testflight_url": testflight_url,
        "categories": categories,
        "description": description,
        "status": status,
        "departures_id": departures_id,
        "source": "departures.to",
    }


def scrape_open_apps(max_pages: int = 3) -> list[dict]:
    """Scrape open apps from departures.to listing pages."""
    try:
        open_apps: list[dict] = []
        for departures_id in _collect_departures_ids(max_pages=max_pages):
            app = scrape_app_detail(departures_id)
            time.sleep(1)
            if app and app.get("status") == "OPEN":
                open_apps.append(app)
        return open_apps
    except Exception as exc:
        logger.warning("Failed to scrape open apps from departures.to: %s", exc)
        return []


def get_open_apps_cached() -> list[dict]:
    """Return cached open apps list, refreshing it once per hour."""
    now = datetime.utcnow()
    if _cache["data"] and _cache["expires_at"] > now:
        return _cache["data"]

    data = scrape_open_apps()
    _cache["data"] = data
    _cache["expires_at"] = now + timedelta(hours=1)
    return data


def find_app_on_departures(app_id: str) -> dict | None:
    """Find a departures.to app by TestFlight app id with 30 minute caching."""
    cache_key = app_id.upper()
    now = datetime.utcnow()
    cached = _search_cache.get(cache_key)
    if cached and cached["expires_at"] > now:
        return cached["data"]

    try:
        search_url = f"{BASE_URL}/search?q={cache_key}"
        html = _fetch_url(search_url)
        if not html:
            _search_cache[cache_key] = {"data": None, "expires_at": now + timedelta(minutes=30)}
            return None

        soup = BeautifulSoup(html, "html.parser")
        for anchor in soup.find_all("a", href=True):
            href = anchor["href"]
            match = re.search(r"/apps/(\d+)", href)
            if not match:
                continue

            departures_id = int(match.group(1))
            app = scrape_app_detail(departures_id)
            if app and app.get("app_id", "").upper() == cache_key:
                _search_cache[cache_key] = {"data": app, "expires_at": now + timedelta(minutes=30)}
                return app
    except Exception as exc:
        logger.warning("Failed to find app %s on departures.to: %s", app_id, exc)

    _search_cache[cache_key] = {"data": None, "expires_at": now + timedelta(minutes=30)}
    return None


def get_popular_apps_from_departures(limit: int = 20) -> list[dict]:
    """Return popular departures.to apps with OPEN apps prioritized."""
    now = datetime.utcnow()
    if _popular_cache["data"] and _popular_cache["expires_at"] > now:
        return _popular_cache["data"][:limit]

    try:
        apps: list[dict] = []
        for departures_id in _collect_departures_ids(max_pages=6):
            app = scrape_app_detail(departures_id)
            time.sleep(1)
            if app:
                apps.append(app)
            if len(apps) >= max(limit * 2, limit):
                break

        apps.sort(key=lambda item: (item.get("status") != "OPEN", item.get("app_name", "").lower()))
        _popular_cache["data"] = apps
        _popular_cache["expires_at"] = now + timedelta(hours=6)
        return apps[:limit]
    except Exception as exc:
        logger.warning("Failed to fetch popular apps from departures.to: %s", exc)
        return []
