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
# Trang listing mặc định chỉ show "Now Boarding" (OPEN) apps
LISTING_URL = f"{BASE_URL}/apps"
HEADERS = {
    # Dùng browser UA thật để tránh block
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# In-memory caches
_open_cache: dict = {"data": [], "expires_at": datetime.min}
_search_cache: dict[str, dict] = {}


def _fetch_url(url: str) -> Optional[str]:
    """Fetch HTML with retry, timeout 8s."""
    for attempt in range(3):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=8)
            if resp.status_code == 200:
                return resp.text
            logger.warning("HTTP %s for %s", resp.status_code, url)
            return None
        except requests.RequestException as exc:
            if attempt == 2:
                logger.warning("Request failed for %s: %s", url, exc)
                return None
            time.sleep(1)
    return None


def _parse_listing_page(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    apps = []
    seen: set[int] = set()

    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href", ""))
        # Match /apps/12345 — dùng fullmatch thay vì search với ^ $
        id_match = re.fullmatch(r"/apps/(\d+)", href)
        if not id_match:
            continue

        departures_id = int(id_match.group(1))
        if departures_id in seen:
            continue
        seen.add(departures_id)

        # Lấy tên — text của toàn anchor, lọc bỏ "· Xh ago"
        full_text = anchor.get_text(" ", strip=True)
        # Tên app nằm trước " · "
        app_name = full_text.split("·")[0].strip()
        if not app_name or len(app_name) < 2:
            continue

        apps.append({
            "departures_id": departures_id,
            "app_name": app_name,
            "app_id": None,   # cần scrape detail
            "status": "OPEN",
            "source": "departures.to",
            "categories": [],
            "description": "",
        })

    return apps


def _scrape_detail_for_app_id(departures_id: int) -> Optional[str]:
    """
    Scrape detail page chỉ để lấy TestFlight app_id.
    Trả về app_id string hoặc None.
    """
    url = f"{BASE_URL}/apps/{departures_id}"
    html = _fetch_url(url)
    if not html:
        return None

    soup = BeautifulSoup(html, "html.parser")
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        if "testflight.apple.com/join/" not in href:
            continue
        if not href.startswith("http"):
            href = urljoin(BASE_URL, href)
        tf_match = re.search(
            r"testflight\.apple\.com/join/([A-Za-z0-9]{8})",
            href,
        )
        if tf_match:
            return tf_match.group(1)  # giữ nguyên case, KHÔNG upper()
    return None


def scrape_open_apps(max_pages: int = 2) -> list[dict]:
    raw_apps: list[dict] = []
    seen_ids: set[int] = set()

    for page in range(1, max_pages + 1):
        url = f"{BASE_URL}/apps" if page == 1 else f"{BASE_URL}/apps?page={page}"
        html = _fetch_url(url)
        if not html:
            break
        page_apps = _parse_listing_page(html)
        new_apps = [a for a in page_apps if a["departures_id"] not in seen_ids]
        if not new_apps:
            break
        for a in new_apps:
            seen_ids.add(a["departures_id"])
            raw_apps.append(a)
        if page < max_pages:
            time.sleep(0.5)

    logger.info("Listing: %s apps parsed", len(raw_apps))

    # Chỉ scrape detail cho 15 app đầu để tránh timeout
    result: list[dict] = []
    for app in raw_apps[:15]:
        app_id = _scrape_detail_for_app_id(app["departures_id"])
        if app_id:
            app["app_id"] = app_id
            result.append(app)
        time.sleep(0.3)

    logger.info("Final with app_id: %s apps", len(result))
    return result


def get_open_apps_cached() -> list[dict]:
    """Return cached open apps, refresh mỗi 30 phút."""
    now = datetime.utcnow()
    if _open_cache["data"] and _open_cache["expires_at"] > now:
        logger.info("Returning cached open apps (%s items)", len(_open_cache["data"]))
        return _open_cache["data"]

    data = scrape_open_apps()
    _open_cache["data"] = data
    _open_cache["expires_at"] = now + timedelta(minutes=30)
    return data


def find_app_on_departures(app_id: str) -> Optional[dict]:
    """
    Tìm app theo TestFlight app_id trên departures.to.
    Dùng search endpoint, cache 30 phút.
    KHÔNG gọi upper() — app_id case-sensitive.
    """
    cache_key = app_id
    now = datetime.utcnow()
    cached = _search_cache.get(cache_key)
    if cached and cached["expires_at"] > now:
        return cached["data"]

    result = None
    try:
        search_url = f"{BASE_URL}/search?q={app_id}"
        html = _fetch_url(search_url)
        if html:
            soup = BeautifulSoup(html, "html.parser")
            for anchor in soup.find_all("a", href=True):
                id_match = re.search(r"^/apps/(\d+)$", anchor["href"])
                if not id_match:
                    continue
                departures_id = int(id_match.group(1))
                found_id = _scrape_detail_for_app_id(departures_id)
                if found_id == app_id:
                    heading = anchor.find(["h3", "h2", "h4"])
                    app_name = ""
                    if heading:
                        app_name = re.sub(r"\s*·\s*.+ago.*$", "", heading.get_text(" ", strip=True)).strip()
                    result = {
                        "app_id": app_id,
                        "app_name": app_name or f"App {app_id}",
                        "status": "OPEN",
                        "source": "departures.to",
                        "categories": [],
                        "description": "",
                        "departures_id": departures_id,
                    }
                    break
    except Exception as exc:
        logger.warning("find_app_on_departures error for %s: %s", app_id, exc)

    _search_cache[cache_key] = {"data": result, "expires_at": now + timedelta(minutes=30)}
    return result


def get_popular_apps_from_departures(limit: int = 20) -> list[dict]:
    """Alias của get_open_apps_cached dùng cho scheduler sync."""
    return get_open_apps_cached()[:limit]
