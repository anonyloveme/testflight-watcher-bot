"""TestFlight status checking service."""

import time

import requests


def fetch_app_info(app_id: str) -> dict:
    """Fetch app metadata and current TestFlight status by app id."""
    url = f"https://testflight.apple.com/v3/app/{app_id}/details"
    headers = {"User-Agent": "Xcode", "Accept": "application/json"}

    for attempt in range(1, 4):
        try:
            response = requests.get(url, headers=headers, timeout=10)
        except requests.RequestException:
            if attempt == 3:
                raise ConnectionError("Không thể kết nối TestFlight API")
            time.sleep(2)
            continue

        if response.status_code == 404:
            raise ValueError(f"App ID {app_id} không tồn tại trên TestFlight")
        if response.status_code != 200:
            raise ConnectionError("Không thể kết nối TestFlight API")

        try:
            data = response.json()
            attributes = data["data"]["attributes"]
            app_name = attributes["name"]
            status = attributes["status"]
            bundle_id = attributes["bundleId"]
        except (ValueError, TypeError, KeyError):
            raise ConnectionError("Không thể kết nối TestFlight API")

        return {
            "app_name": app_name,
            "status": status,
            "bundle_id": bundle_id,
            "app_id": app_id,
        }

    raise ConnectionError("Không thể kết nối TestFlight API")


def check_app_status(app_id: str) -> str:
    """Return only OPEN/CLOSED status for the app, else UNKNOWN."""
    try:
        info = fetch_app_info(app_id)
        return str(info["status"])
    except Exception:
        return "UNKNOWN"


def validate_app_id(app_id: str) -> bool:
    """Validate app id format: exactly 8 alphanumeric characters."""
    return isinstance(app_id, str) and len(app_id) == 8 and app_id.isalnum()
