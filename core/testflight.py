"""TestFlight status checking — scrapes join page HTML như source gốc jacopo-j/testflight-watcher."""

import re
import time

import requests
from lxml import html as lxml_html

TESTFLIGHT_URL = "https://testflight.apple.com/join/{}"
XPATH_STATUS = '//*[@class="beta-status"]/span/text()'
XPATH_TITLE = '/html/head/title/text()'
TITLE_REGEX = r'Join the (.+) beta - TestFlight - Apple'
FULL_TEXTS = [
    "This beta is full.",
    "This beta isn't accepting any new testers right now.",
]
HEADERS = {"Accept-Language": "en-us"}


def fetch_app_info(app_id: str) -> dict:
    """
    Scrape TestFlight join page to get app name and slot status.
    App ID is case-sensitive (e.g. 'm2kxP5cw' != 'M2KXP5CW').
    Returns dict with keys: app_id, app_name, status ('OPEN'|'CLOSED'), bundle_id.
    Raises ValueError if app not found (404 or title not matched).
    Raises ConnectionError on network failure after 3 retries.
    """
    url = TESTFLIGHT_URL.format(app_id)

    for attempt in range(1, 4):
        try:
            response = requests.get(url, headers=HEADERS, timeout=10)
        except requests.RequestException:
            if attempt == 3:
                raise ConnectionError("Không thể kết nối TestFlight")
            time.sleep(2)
            continue

        if response.status_code == 404:
            raise ValueError(f"App ID '{app_id}' không tồn tại trên TestFlight")

        if response.status_code != 200:
            if attempt == 3:
                raise ConnectionError("Không thể kết nối TestFlight")
            time.sleep(2)
            continue

        try:
            page = lxml_html.fromstring(response.text)

            # Lấy tên app từ <title>
            titles = page.xpath(XPATH_TITLE)
            if not titles:
                raise ValueError(f"App ID '{app_id}' không tồn tại trên TestFlight")
            title_match = re.findall(TITLE_REGEX, titles[0])
            if not title_match:
                raise ValueError(f"App ID '{app_id}' không tồn tại trên TestFlight")
            app_name = title_match[0]

            # Lấy trạng thái slot
            status_nodes = page.xpath(XPATH_STATUS)
            if status_nodes and status_nodes[0] in FULL_TEXTS:
                status = "CLOSED"
            else:
                status = "OPEN"

            return {
                "app_id": app_id,     # giữ nguyên case gốc, KHÔNG upper()
                "app_name": app_name,
                "status": status,
                "bundle_id": "",      # không có trong HTML, để trống
            }
        except ValueError:
            raise
        except Exception:
            if attempt == 3:
                raise ConnectionError("Không thể parse trang TestFlight")
            time.sleep(2)

    raise ConnectionError("Không thể kết nối TestFlight sau 3 lần thử")


def check_app_status(app_id: str) -> str:
    """Return 'OPEN', 'CLOSED', or 'UNKNOWN'. Never raises."""
    try:
        return fetch_app_info(app_id)["status"]
    except Exception:
        return "UNKNOWN"


def validate_app_id(app_id: str) -> bool:
    """
    App ID phải đúng 8 ký tự chữ và số, case-sensitive.
    KHÔNG gọi .upper() hay .lower() ở bất kỳ đâu.
    """
    return isinstance(app_id, str) and len(app_id) == 8 and app_id.isalnum()
