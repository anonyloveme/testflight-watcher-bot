"""Inline keyboard builders for bot interactions."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu_keyboard() -> InlineKeyboardMarkup:
    """Return the main menu keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("📋 App phổ biến", callback_data="popular"),
            InlineKeyboardButton("➕ Theo dõi app", callback_data="watch"),
        ],
        [
            InlineKeyboardButton("🔍 Khám phá OPEN", callback_data="discover"),
            InlineKeyboardButton("📱 App đang theo dõi", callback_data="mylist"),
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
        ]
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
                "🗑 Bỏ theo dõi app này", callback_data=f"unwatch:{app_id}"
            )
        ],
        [InlineKeyboardButton("🔙 Quay lại danh sách", callback_data="back_mylist")],
    ]
    return InlineKeyboardMarkup(keyboard)


def popular_apps_keyboard(popular_apps: list) -> InlineKeyboardMarkup:
    """Return keyboard with popular apps quick-watch buttons."""
    rows: list[list[InlineKeyboardButton]] = []
    for app in popular_apps:
        status = str(app.get("status", "UNKNOWN")).upper()
        icon = "⚫"
        if status == "OPEN":
            icon = "🟢"
        elif status == "CLOSED":
            icon = "🔴"

        app_name = app.get("name") or app.get("app_name") or "Unknown App"

        rows.append(
            [
                InlineKeyboardButton(
                    f"{icon} {app_name}",
                    callback_data=f"quick_watch:{app.get('app_id', '')}",
                )
            ]
        )

    rows.append([InlineKeyboardButton("🔙 Quay lại", callback_data="back_main")])
    return InlineKeyboardMarkup(rows)


def cancel_keyboard() -> InlineKeyboardMarkup:
    """Return one-button cancel keyboard."""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("❌ Huỷ", callback_data="cancel")]]
    )
