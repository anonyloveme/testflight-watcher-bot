"""Popular TestFlight apps list maintained manually."""

# Danh sach nay se duoc cap nhat thu cong theo thoi gian.
POPULAR_APPS = [
    {"name": "Telegram Beta", "app_id": "W38CV8MJ", "category": "Social"},
    {"name": "Swiftgram", "app_id": "3TUwXHbH", "category": "Social"},
    {"name": "Flighty", "app_id": "r9STGYAU", "category": "Travel"},
    {"name": "Noir", "app_id": "43YWjVTy", "category": "Utility"},
    {"name": "Reeder", "app_id": "82TEZR37", "category": "News"},
    {"name": "Toolbox for Word", "app_id": "W2S7xNMB", "category": "Productivity"},
    {"name": "Mango 5Star", "app_id": "xwKKHp73", "category": "Productivity"},
    {"name": "Tempi", "app_id": "RXjNTyLb", "category": "Music"},
    {"name": "Keewordz", "app_id": "5mVR42xR", "category": "Productivity"},
    {"name": "Pricetag", "app_id": "JAbnQB3e", "category": "Utility"},
]


def get_popular_apps() -> list[dict]:
    """Tra ve danh sach app pho bien."""
    return POPULAR_APPS


def get_popular_app_by_id(app_id: str) -> dict | None:
    """Tim app trong danh sach pho bien theo app_id."""
    return next((a for a in POPULAR_APPS if a["app_id"] == app_id), None)
