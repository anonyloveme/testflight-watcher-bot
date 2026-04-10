"""Inline keyboard builders for bot interactions."""

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)


def main_menu_keyboard() -> InlineKeyboardMarkup:
    """Return the main menu keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("➕ Theo dõi app", callback_data="watch"),
            InlineKeyboardButton("📱 App đang theo dõi", callback_data="mylist"),
        ],
        [
            InlineKeyboardButton("🌐 Khám phá departures.to", callback_data="discover"),
            InlineKeyboardButton("📋 App phổ biến", callback_data="popular"),
        ],
        [InlineKeyboardButton("📊 Thống kê", callback_data="stats")],
    ]
    return InlineKeyboardMarkup(keyboard)


def confirm_watch_keyboard(app_id: str) -> InlineKeyboardMarkup:
    """Return confirmation keyboard for watching an app."""
    keyboard = [
        [
            InlineKeyboardButton(
                "✅ Xác nhận theo dõi", callback_data=f"confirm_watch:{app_id}"
            ),
            InlineKeyboardButton("❌ Huỷ", callback_data="cancel"),
        ],
        [
            InlineKeyboardButton(
                "🔗 Mở TestFlight xem thử",
                url=f"https://testflight.apple.com/join/{app_id}",
            ),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def my_list_keyboard(watches: list) -> InlineKeyboardMarkup:
    """Return keyboard listing user watches."""
    rows: list[list[InlineKeyboardButton]] = []

    for watch in watches:
        app = watch.app
        status = (app.current_status or "UNKNOWN").upper()
        icon = "⚫"
        if status == "OPEN":
            icon = "🟢"
        elif status == "CLOSED":
            icon = "🔴"

        app_name = app.app_name or "Unknown App"
        rows.append(
            [
                InlineKeyboardButton(
                    f"{icon} {app_name} ({app.app_id})",
                    callback_data=f"detail:{app.app_id}",
                )
            ]
        )

    rows.append([InlineKeyboardButton("🔙 Quay lại", callback_data="back_main")])
    return InlineKeyboardMarkup(rows)


def app_detail_keyboard(app_id: str) -> InlineKeyboardMarkup:
    """Return keyboard for app detail actions."""
    keyboard = [
        [
            InlineKeyboardButton(
                "🔄 Kiểm tra slot ngay", callback_data=f"recheck:{app_id}"
            ),
        ],
        [
            InlineKeyboardButton(
                "🔗 Mở TestFlight", url=f"https://testflight.apple.com/join/{app_id}"
            ),
        ],
        [
            InlineKeyboardButton(
                "🗑 Bỏ theo dõi", callback_data=f"unwatch:{app_id}"
            ),
            InlineKeyboardButton("🔙 Danh sách", callback_data="back_mylist"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def popular_apps_keyboard(popular_apps: list) -> InlineKeyboardMarkup:
    """Return keyboard with popular apps quick-watch buttons."""
    rows: list[list[InlineKeyboardButton]] = []
    for app in popular_apps:
        status = str(app.get("status", "UNKNOWN")).upper()
        icon = "⚫" if status == "UNKNOWN" else ("🟢" if status == "OPEN" else "🔴")

        app_name = app.get("name") or app.get("app_name") or "Unknown App"
        app_id = app.get("app_id", "")

        rows.append(
            [
                InlineKeyboardButton(
                    f"{icon} {app_name}",
                    callback_data=f"quick_watch:{app_id}",
                ),
                InlineKeyboardButton(
                    "🔗",
                    url=f"https://testflight.apple.com/join/{app_id}",
                ),
            ]
        )

    rows.append([InlineKeyboardButton("🔙 Quay lại", callback_data="back_main")])
    return InlineKeyboardMarkup(rows)


def cancel_keyboard() -> InlineKeyboardMarkup:
    """Return one-button cancel keyboard."""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("❌ Huỷ", callback_data="cancel")]]
    )


def persistent_menu_keyboard() -> ReplyKeyboardMarkup:
    """Return a persistent reply keyboard for quick actions."""
    keyboard = [
        [
            KeyboardButton("➕ Theo dõi app"),
            KeyboardButton("📱 App đang theo dõi"),
        ],
        [
            KeyboardButton("🌐 Khám phá OPEN"),
            KeyboardButton("📋 App phổ biến"),
        ],
        [
            KeyboardButton("📊 Thống kê"),
            KeyboardButton("❓ Hướng dẫn"),
        ],
    ]
    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        is_persistent=True,
    )
