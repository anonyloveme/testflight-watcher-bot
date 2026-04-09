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
    """
    Parse listing page HTML — mỗi app card có dạng:
    <a href="/apps/12345">
      <h3>App Name</h3>
      <span>Category</span>
    </a>
    Tất cả app trên listing mặc định đều là OPEN (Now Boarding).
    """
    soup = BeautifulSoup(html, "html.parser")
    apps = []
    seen_ids: set[int] = set()

    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        match = re.search(r"^/apps/(\d+)$", href)
        if not match:
            continue

        departures_id = int(match.group(1))
        if departures_id in seen_ids:
            continue
        seen_ids.add(departures_id)

        # Lấy tên app từ thẻ h3 hoặc h2 bên trong anchor
        heading = anchor.find(["h3", "h2", "h4"])
        app_name = heading.get_text(" ", strip=True) if heading else ""
        # Bỏ phần " · Xh ago" ở cuối tên nếu có
        app_name = re.sub(r"\s*·\s*\d+\w?\s*ago.*$", "", app_name).strip()

        if not app_name:
            continue

        apps.append(
            {
                "departures_id": departures_id,
                "app_name": app_name,
                "status": "OPEN",  # listing mặc định = Now Boarding = OPEN
                "source": "departures.to",
                "app_id": None,  # chưa có, cần scrape detail nếu cần
            }
        )

    return apps


def _scrape_app_detail(departures_id: int) -> Optional[dict]:
    """
    Scrape detail page để lấy TestFlight app_id, categories, description.
    Chỉ gọi khi cần app_id cụ thể.
    """
    url = f"{BASE_URL}/apps/{departures_id}"
    html = _fetch_url(url)
    if not html:
        return None

    soup = BeautifulSoup(html, "html.parser")

    # Lấy TestFlight URL → extract app_id
    testflight_url = ""
    app_id = None
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        if "testflight.apple.com/join/" in href:
            testflight_url = href if href.startswith("http") else urljoin(BASE_URL, href)
            tf_match = re.search(
                r"testflight\.apple\.com/join/([A-Za-z0-9]{8})",
                testflight_url,
            )
            if tf_match:
                app_id = tf_match.group(1)  # giữ nguyên case, KHÔNG upper()
            break

    if not app_id:
        return None

    # Lấy description từ thẻ <p> đầu tiên
    description = ""
    para = soup.find("p")
    if para:
        description = para.get_text(" ", strip=True)
        if len(description) > 200:
            description = description[:200].rstrip() + "..."

    # Lấy categories từ emoji text (departures.to dùng emoji + text)
    categories: list[str] = []
    page_text = soup.get_text(" ", strip=True)
    cat_match = re.findall(r"[🎳🌐🎬🍿🏠🔦🛍🏦🪙🏃‍♀️⚽️🎨🔊🎧📢🤖💊🏋️📱🎮🗺️✈️🍔📸🎵🔬💰🎓]\s*[\w &/]+", page_text)
    for cat in cat_match[:5]:
        cat_clean = cat.strip()
        if cat_clean and cat_clean not in categories:
            categories.append(cat_clean)

    return {
        "app_id": app_id,
        "testflight_url": testflight_url,
        "description": description,
        "categories": categories,
        "departures_id": departures_id,
    }


def scrape_open_apps(max_pages: int = 5) -> list[dict]:
    """
    Scrape danh sách app OPEN từ listing pages.
    KHÔNG cần vào detail page — listing mặc định đã là Now Boarding.
    Nhanh hơn rất nhiều so với cách cũ.
    """
    all_apps: list[dict] = []
    seen_ids: set[int] = set()

    for page in range(1, max_pages + 1):
        url = LISTING_URL if page == 1 else f"{LISTING_URL}?page={page}"
        html = _fetch_url(url)
        if not html:
            break

        page_apps = _parse_listing_page(html)
        new_apps = [a for a in page_apps if a["departures_id"] not in seen_ids]

        if not new_apps:
            break  # hết trang

        for app in new_apps:
            seen_ids.add(app["departures_id"])
            all_apps.append(app)

        logger.info("departures.to page %s: found %s apps", page, len(new_apps))

        if page < max_pages:
            time.sleep(0.5)  # polite delay, ngắn vì chỉ scrape listing

    logger.info("Total open apps from departures.to: %s", len(all_apps))
    return all_apps


def get_open_apps_cached() -> list[dict]:
    """Return cached open apps, refresh mỗi 30 phút."""
    now = datetime.utcnow()
    if _open_cache["data"] and _open_cache["expires_at"] > now:
        return _open_cache["data"]

    data = scrape_open_apps()
    _open_cache["data"] = data
    _open_cache["expires_at"] = now + timedelta(minutes=30)
    return data


def find_app_on_departures(app_id: str) -> Optional[dict]:
    """
    Tìm app trên departures.to theo TestFlight app_id.
    Dùng search endpoint, chỉ scrape 1 detail page nếu tìm thấy.
    Cache 30 phút.
    """
    cache_key = app_id  # giữ nguyên case
    now = datetime.utcnow()
    cached = _search_cache.get(cache_key)
    if cached and cached["expires_at"] > now:
        return cached["data"]

    result = None
    try:
        # Bước 1: search bằng app_id
        search_url = f"{BASE_URL}/search?q={app_id}"
        html = _fetch_url(search_url)
        if html:
            soup = BeautifulSoup(html, "html.parser")
            for anchor in soup.find_all("a", href=True):
                m = re.search(r"^/apps/(\d+)$", anchor["href"])
                if not m:
                    continue
                detail = _scrape_app_detail(int(m.group(1)))
                if detail and detail.get("app_id") == app_id:
                    # Lấy tên app từ anchor text
                    heading = anchor.find(["h3", "h2", "h4"])
                    app_name = heading.get_text(" ", strip=True) if heading else ""
                    app_name = re.sub(r"\s*·\s*\d+\w?\s*ago.*$", "", app_name).strip()
                    result = {
                        **detail,
                        "app_name": app_name or f"App {app_id}",
                        "status": "OPEN",
                        "source": "departures.to",
                    }
                    break
    except Exception as exc:
        logger.warning("find_app_on_departures failed for %s: %s", app_id, exc)

    _search_cache[cache_key] = {"data": result, "expires_at": now + timedelta(minutes=30)}
    return result


def get_popular_apps_from_departures(limit: int = 20) -> list[dict]:
    """
    Lấy danh sách app phổ biến đang OPEN từ departures.to.
    Với mỗi app cần scrape detail để lấy app_id (TestFlight ID).
    Chỉ dùng cho scheduler sync — không dùng trong Telegram handler.
    """
    open_apps = scrape_open_apps(max_pages=3)
    result: list[dict] = []

    for app in open_apps:
        if len(result) >= limit:
            break
        try:
            detail = _scrape_app_detail(app["departures_id"])
            if detail and detail.get("app_id"):
                result.append(
                    {
                        **app,
                        **detail,
                        "status": "OPEN",
                    }
                )
            time.sleep(0.5)
        except Exception as exc:
            logger.warning("Failed detail for departures_id %s: %s", app["departures_id"], exc)

    return result
