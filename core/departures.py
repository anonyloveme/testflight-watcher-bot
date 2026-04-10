"""Scraping helpers for departures.to app discovery."""

import logging
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://departures.to"
LISTING_URL = f"{BASE_URL}/apps"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

# In-memory caches
_open_cache: dict = {"data": [], "expires_at": datetime.min}
_search_cache: dict[str, dict] = {}


# -------------------------------------------------
# 1. FETCH HELPERS
# -------------------------------------------------

def _fetch_url(url: str, timeout: int = 10) -> Optional[str]:
    """Fetch HTML với retry 3 lần, timeout tuỳ chỉnh."""
    for attempt in range(3):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=timeout)
            if resp.status_code == 200:
                return resp.text
            logger.warning("HTTP %s for %s", resp.status_code, url)
            return None
        except requests.RequestException as exc:
            if attempt == 2:
                logger.warning("Request failed for %s: %s", url, exc)
                return None
            time.sleep(1.5)
    return None


# -------------------------------------------------
# 2. RSS FEED (CACH ON DINH NHAT)
#    findbeta.no dang dung chinh RSS nay
# -------------------------------------------------

RSS_CANDIDATES = [
    f"{BASE_URL}/rss.xml",
    f"{BASE_URL}/feed.xml",
    f"{BASE_URL}/apps.rss",
    f"{BASE_URL}/feed/rss",
]
_rss_url_cache: Optional[str] = None  # luu URL RSS hoat dong duoc


def _find_working_rss_url() -> Optional[str]:
    """Tim URL RSS hoat dong trong danh sach candidates."""
    global _rss_url_cache
    if _rss_url_cache:
        return _rss_url_cache

    for url in RSS_CANDIDATES:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=8)
            if resp.status_code == 200 and (
                "<rss" in resp.text or "<feed" in resp.text or "<urlset" in resp.text
            ):
                logger.info("Found working RSS/feed at: %s", url)
                _rss_url_cache = url
                return url
        except Exception:
            continue
    return None


def _parse_rss_apps(limit: int = 30) -> list[dict]:
    """
    Parse RSS feed của departures.to để lấy danh sách app mới nhất.
    Trả về list dict với keys: departures_id, app_name, status, source.
    """
    rss_url = _find_working_rss_url()
    if not rss_url:
        logger.warning("Khong tim thay RSS feed hoat dong tu departures.to")
        return []

    html = _fetch_url(rss_url)
    if not html:
        return []

    apps = []
    try:
        root = ET.fromstring(html)
        # Hỗ trợ cả RSS 2.0 và Atom feed
        ns_map = {
            "atom": "http://www.w3.org/2005/Atom",
        }
        # RSS 2.0 items
        items = root.findall(".//item")
        # Atom entries fallback
        if not items:
            items = root.findall(".//atom:entry", ns_map)

        for item in items[:limit]:
            link_tag = item.find("link")
            title_tag = item.find("title")
            if link_tag is None or title_tag is None:
                continue

            link = (link_tag.text or "").strip()
            title = (title_tag.text or "").strip()

            id_match = re.search(r"/apps/(\d+)", link)
            if not id_match:
                continue

            departures_id = int(id_match.group(1))
            apps.append({
                "departures_id": departures_id,
                "app_name": title,
                "app_id": None,
                "status": "OPEN",
                "source": "departures.to/rss",
                "categories": [],
                "description": "",
            })

        logger.info("RSS: parsed %d apps", len(apps))
    except ET.ParseError as exc:
        logger.warning("RSS parse error: %s", exc)

    return apps


# -------------------------------------------------
# 3. SITEMAP - lay toan bo ID (dung de sync)
# -------------------------------------------------

def get_all_app_ids_from_sitemap() -> list[int]:
    """
    Parse sitemap.xml để lấy tất cả departures ID.
    Sitemap của departures.to chứa hàng nghìn entry /apps/{id}.
    """
    sitemap_url = f"{BASE_URL}/sitemap.xml"
    html = _fetch_url(sitemap_url, timeout=15)
    if not html:
        return []

    try:
        root = ET.fromstring(html)
        ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        ids = []
        for loc in root.findall("sm:url/sm:loc", ns):
            text = (loc.text or "").strip()
            match = re.search(r"/apps/(\d+)$", text)
            if match:
                ids.append(int(match.group(1)))
        logger.info("Sitemap: found %d app IDs", len(ids))
        return sorted(ids)
    except ET.ParseError as exc:
        logger.warning("Sitemap parse error: %s", exc)
        return []


# -------------------------------------------------
# 4. HTML LISTING SCRAPER (fallback)
# -------------------------------------------------

def _parse_listing_page(html: str) -> list[dict]:
    """
    Parse trang listing HTML.
    FIX: dùng re.search thay vì re.fullmatch để bắt được href
         có query string như /apps/12345?ref=homepage
    """
    soup = BeautifulSoup(html, "html.parser")
    apps = []
    seen: set[int] = set()

    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href", ""))

        # FIX CHINH: dùng re.search với ^ thay vì fullmatch
        # để bắt /apps/12345 và /apps/12345?ref=homepage
        id_match = re.search(r"^/apps/(\d+)", href)
        if not id_match:
            continue

        departures_id = int(id_match.group(1))
        if departures_id in seen:
            continue
        seen.add(departures_id)

        # Lấy tên app - text của anchor, lọc bỏ "· Xh ago"
        full_text = anchor.get_text(" ", strip=True)
        app_name = full_text.split("·")[0].strip()

        # Lấy categories từ các thẻ con
        categories = []
        for tag in anchor.find_all(class_=re.compile(r"tag|category|badge", re.I)):
            cat_text = tag.get_text(strip=True)
            if cat_text:
                categories.append(cat_text)

        if not app_name or len(app_name) < 2:
            continue

        apps.append({
            "departures_id": departures_id,
            "app_name": app_name,
            "app_id": None,
            "status": "OPEN",
            "source": "departures.to/listing",
            "categories": categories,
            "description": "",
        })

    return apps


def scrape_open_apps_from_listing(max_pages: int = 3) -> list[dict]:
    """Scrape từ trang listing HTML, nhiều page hơn."""
    raw_apps: list[dict] = []
    seen_ids: set[int] = set()

    for page in range(1, max_pages + 1):
        url = LISTING_URL if page == 1 else f"{LISTING_URL}?page={page}"
        html = _fetch_url(url)
        if not html:
            break
        page_apps = _parse_listing_page(html)
        new_apps = [app for app in page_apps if app["departures_id"] not in seen_ids]
        if not new_apps:
            break
        for app in new_apps:
            seen_ids.add(app["departures_id"])
            raw_apps.append(app)
        if page < max_pages:
            time.sleep(0.8)

    logger.info("Listing scraper: %d apps raw", len(raw_apps))
    return raw_apps


# -------------------------------------------------
# 5. DETAIL PAGE - lay TestFlight app_id
# -------------------------------------------------

def _scrape_detail_for_app_id(departures_id: int) -> Optional[str]:
    """
    Scrape trang detail để lấy TestFlight app_id (8 ký tự).
    Trả về app_id string hoặc None.
    Case-sensitive - KHÔNG gọi .upper() hay .lower().
    """
    url = f"{BASE_URL}/apps/{departures_id}"
    html = _fetch_url(url)
    if not html:
        return None

    soup = BeautifulSoup(html, "html.parser")

    # Cách 1: Tìm link testflight.apple.com/join/...
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href", ""))
        if "testflight.apple.com/join/" not in href:
            continue
        if not href.startswith("http"):
            href = urljoin(BASE_URL, href)
        tf_match = re.search(
            r"testflight\.apple\.com/join/([A-Za-z0-9]{8})",
            href,
        )
        if tf_match:
            return tf_match.group(1)

    # Cách 2: Tìm trong toàn bộ text của trang (phòng khi link bị ẩn)
    page_text = soup.get_text()
    tf_match = re.search(
        r"testflight\.apple\.com/join/([A-Za-z0-9]{8})",
        page_text,
    )
    if tf_match:
        return tf_match.group(1)

    # Cách 3: Tìm trong các thẻ script/meta
    for script in soup.find_all(["script", "meta"]):
        content = script.get("content", "") or script.string or ""
        tf_match = re.search(
            r"testflight\.apple\.com/join/([A-Za-z0-9]{8})",
            str(content),
        )
        if tf_match:
            return tf_match.group(1)

    logger.debug("No TestFlight link found for departures_id=%d", departures_id)
    return None


def _scrape_detail_batch(
    apps: list[dict],
    max_items: int = 20,
    delay: float = 0.4,
) -> list[dict]:
    """
    Scrape detail page cho batch app để lấy TestFlight app_id.
    Trả về list chỉ gồm các app có app_id.
    """
    result = []
    for app in apps[:max_items]:
        app_id = _scrape_detail_for_app_id(app["departures_id"])
        if app_id:
            app["app_id"] = app_id
            result.append(app)
            logger.debug(
                "Detail OK: departures_id=%d -> app_id=%s name=%s",
                app["departures_id"], app_id, app["app_name"],
            )
        time.sleep(delay)
    logger.info("Detail batch: %d/%d apps có app_id", len(result), len(apps[:max_items]))
    return result


# -------------------------------------------------
# 6. MAIN SCRAPE FUNCTION - co fallback chain
# -------------------------------------------------

def scrape_open_apps(max_pages: int = 3) -> list[dict]:
    """
    Kéo danh sách app đang OPEN từ departures.to.
    Thứ tự ưu tiên:
      1. RSS feed  (nhanh, ổn định nhất)
      2. HTML listing scraper (fallback)
    Sau đó scrape detail từng app để lấy TestFlight app_id.
    """
    # Bước 1: Thử RSS feed trước
    raw_apps = _parse_rss_apps(limit=30)

    # Bước 2: Fallback sang HTML listing nếu RSS không hoạt động
    if not raw_apps:
        logger.info("RSS khong co ket qua, fallback sang HTML listing scraper...")
        raw_apps = scrape_open_apps_from_listing(max_pages=max_pages)

    if not raw_apps:
        logger.warning("Khong lay duoc app nao tu departures.to")
        return []

    # Bước 3: Scrape detail để lấy TestFlight app_id
    result = _scrape_detail_batch(raw_apps, max_items=20, delay=0.4)

    logger.info("scrape_open_apps: %d apps cuối cùng có đủ thông tin", len(result))
    return result


# -------------------------------------------------
# 7. CACHE LAYER
# -------------------------------------------------

def get_open_apps_cached(ttl_minutes: int = 30) -> list[dict]:
    """Return cached open apps, refresh sau mỗi ttl_minutes phút."""
    now = datetime.utcnow()
    if _open_cache["data"] and _open_cache["expires_at"] > now:
        logger.info(
            "Cache hit: trả về %d apps (còn %s)",
            len(_open_cache["data"]),
            _open_cache["expires_at"] - now,
        )
        return _open_cache["data"]

    logger.info("Cache miss, đang scrape departures.to...")
    data = scrape_open_apps()
    _open_cache["data"] = data
    _open_cache["expires_at"] = now + timedelta(minutes=ttl_minutes)
    return data


# -------------------------------------------------
# 8. SEARCH APP THEO TESTFLIGHT ID
# -------------------------------------------------

def find_app_on_departures(app_id: str) -> Optional[dict]:
    """
    Tìm app theo TestFlight app_id trên departures.to.

    Chiến lược:
      1. Tìm trong cache open apps hiện tại (không tốn request)
      2. Search trên departures.to/search?q={tên app hoặc id}
      3. Nếu vẫn không ra, brute-force qua ID gần đây từ sitemap (top 50 mới nhất)

    app_id là case-sensitive. KHÔNG gọi upper() hay lower().
    """
    cache_key = app_id
    now = datetime.utcnow()

    # Kiểm tra search cache
    cached = _search_cache.get(cache_key)
    if cached and cached["expires_at"] > now:
        return cached["data"]

    result = None

    # Bước 1: Tìm trong open apps cache trước (zero cost)
    cached_apps = _open_cache.get("data", [])
    for app in cached_apps:
        if app.get("app_id") == app_id:
            result = app
            logger.info("find_app: found in cache for app_id=%s", app_id)
            break

    # Bước 2: Search trên departures.to
    if not result:
        try:
            search_url = f"{BASE_URL}/search?q={app_id}"
            html = _fetch_url(search_url)
            if html:
                soup = BeautifulSoup(html, "html.parser")
                for anchor in soup.find_all("a", href=True):
                    id_match = re.search(r"^/apps/(\d+)", anchor["href"])
                    if not id_match:
                        continue
                    departures_id = int(id_match.group(1))
                    found_id = _scrape_detail_for_app_id(departures_id)
                    if found_id == app_id:
                        heading = anchor.find(["h3", "h2", "h4", "p", "span"])
                        app_name = ""
                        if heading:
                            app_name = re.sub(
                                r"\s*·\s*.+",
                                "",
                                heading.get_text(" ", strip=True),
                            ).strip()
                        result = {
                            "app_id": app_id,
                            "app_name": app_name or f"App {app_id}",
                            "status": "OPEN",
                            "source": "departures.to/search",
                            "categories": [],
                            "description": "",
                            "departures_id": departures_id,
                        }
                        logger.info(
                            "find_app: found via search for app_id=%s -> departures_id=%d",
                            app_id, departures_id,
                        )
                        break
        except Exception as exc:
            logger.warning("find_app search error for %s: %s", app_id, exc)

    # Bước 3: Brute-force qua 50 ID mới nhất từ sitemap (last resort)
    if not result:
        try:
            all_ids = get_all_app_ids_from_sitemap()
            recent_ids = sorted(all_ids, reverse=True)[:50]  # 50 ID cao nhất = mới nhất
            logger.info("find_app: brute-force %d recent IDs for app_id=%s", len(recent_ids), app_id)
            for dep_id in recent_ids:
                found_id = _scrape_detail_for_app_id(dep_id)
                if found_id == app_id:
                    result = {
                        "app_id": app_id,
                        "app_name": f"App {app_id}",
                        "status": "OPEN",
                        "source": "departures.to/brute-force",
                        "categories": [],
                        "description": "",
                        "departures_id": dep_id,
                    }
                    logger.info(
                        "find_app: brute-force found departures_id=%d for app_id=%s",
                        dep_id, app_id,
                    )
                    break
                time.sleep(0.3)
        except Exception as exc:
            logger.warning("find_app brute-force error: %s", exc)

    # Lưu vào search cache 30 phút
    _search_cache[cache_key] = {
        "data": result,
        "expires_at": now + timedelta(minutes=30),
    }
    return result


# -------------------------------------------------
# 9. ALIAS CHO SCHEDULER
# -------------------------------------------------

def get_popular_apps_from_departures(limit: int = 20) -> list[dict]:
    """Alias của get_open_apps_cached dùng cho scheduler sync."""
    return get_open_apps_cached()[:limit]
