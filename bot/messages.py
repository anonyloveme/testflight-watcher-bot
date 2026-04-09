"""Message template builders for Telegram bot responses."""

from html import escape


def welcome_message(first_name: str) -> str:
	"""Build welcome message for a new or returning user."""
	name = escape(first_name or "bạn")
	return (
		f"Xin chào {name}! 👋\n\n"
		"🔍 <b>TestFlight Watcher Bot</b>\n\n"
		"Bot giúp bạn theo dõi slot beta TestFlight theo thời gian thực.\n"
		"Nhập App ID để theo dõi và nhận thông báo ngay khi slot mở.\n\n"
		"Bắt đầu bằng cách chọn <b>➕ Theo dõi app</b> hoặc dùng lệnh /watch."
	)


def app_info_message(app_info: dict) -> str:
	"""Build formatted app information message before watch confirm."""
	app_name = escape(str(app_info.get("app_name", "Unknown App")))
	app_id_raw = str(app_info.get("app_id", ""))
	app_id = escape(app_id_raw)
	status = str(app_info.get("status", "UNKNOWN")).upper()
	status_label = {
		"OPEN": "🟢 OPEN — Còn slot!",
		"CLOSED": "🔴 CLOSED — Hết slot",
	}.get(status, "⚫ UNKNOWN")
	join_url = f"https://testflight.apple.com/join/{escape(app_id_raw)}"

	return (
		f"📱 <b>{app_name}</b>\n"
		f"🆔 App ID: <code>{app_id}</code>\n"
		f"🔗 <a href='{join_url}'>Xem trên TestFlight</a>\n"
		f"{status_label}\n\n"
		"Bạn có muốn theo dõi app này không?"
	)


def app_info_message_rich(app_info: dict) -> str:
	"""Build a richer app information message for departures.to results."""
	if str(app_info.get("source", "")).lower() == "testflight":
		return app_info_message(app_info)

	app_name = escape(str(app_info.get("app_name", "Unknown App")))
	app_id = escape(str(app_info.get("app_id", "")))
	categories = app_info.get("categories", []) or []
	description = str(app_info.get("description", "")).strip()
	if len(description) > 150:
		description = description[:150].rstrip() + "..."
	description = escape(description) if description else "Chưa có mô tả."
	status = str(app_info.get("status", "UNKNOWN")).upper()
	status_emoji = "⚫"
	if status == "OPEN":
		status_emoji = "🟢"
	elif status == "CLOSED":
		status_emoji = "🔴"
	categories_text = ", ".join(escape(str(category)) for category in categories) if categories else "N/A"

	return (
		f"📱 <b>{app_name}</b>\n"
		f"🆔 App ID: <code>{app_id}</code>\n"
		f"🏷 Category: {categories_text}\n"
		f"📝 {description}\n"
		f"{status_emoji} Trạng thái: {status}\n"
		"🔗 Source: departures.to\n\n"
		"Bạn có muốn theo dõi app này không?"
	)


def watch_success_message(app_name: str, app_id: str) -> str:
	"""Build success message after creating watch."""
	return (
		"✅ <b>Theo dõi thành công!</b>\n\n"
		f"Bạn đang theo dõi: <b>{escape(app_name)}</b>\n"
		f"App ID: <code>{escape(app_id)}</code>"
	)


def unwatch_success_message(app_name: str) -> str:
	"""Build success message after removing watch."""
	return f"🗑 Đã bỏ theo dõi <b>{escape(app_name)}</b> thành công."


def slot_open_notification(app_name: str, app_id: str) -> str:
	"""Build high-priority notification when slots open."""
	join_url = f"https://testflight.apple.com/join/{escape(app_id)}"
	return (
		"🚨 <b>SLOT ĐÃ MỞ!</b> 🚨\n\n"
		f"📱 <b>{escape(app_name)}</b> vừa mở đăng ký TestFlight!\n\n"
		f"⚡ <a href='{join_url}'>Nhấn vào đây để tham gia ngay!</a>\n\n"
		"⏰ Slot có thể đóng bất cứ lúc nào!"
	)


def slot_closed_notification(app_name: str, app_id: str) -> str:
	"""Build notification when slots are closed."""
	return (
		"🔒 Slot TestFlight đã đóng.\n\n"
		f"📱 <b>{escape(app_name)}</b>\n"
		f"🆔 <code>{escape(app_id)}</code>"
	)


def my_list_message(watches: list) -> str:
	"""Build message header for watch list section."""
	if not watches:
		return "Bạn chưa theo dõi app nào. Hãy chọn ➕ Theo dõi app để bắt đầu."
	return f"📱 Danh sách <b>{len(watches)}</b> app đang theo dõi:"


def stats_message(stats: dict) -> str:
	"""Build formatted statistics summary message."""
	top_apps = stats.get("top_apps", []) or []
	top_lines: list[str] = []
	for idx, app in enumerate(top_apps[:5], start=1):
		top_lines.append(
			f"{idx}. {escape(str(app.get('app_name') or 'Unknown App'))} "
			f"(<code>{escape(str(app.get('app_id', '')))}</code>) - "
			f"{int(app.get('watcher_count', 0))} watchers"
		)

	top_text = "\n".join(top_lines) if top_lines else "Chưa có dữ liệu."
	return (
		"📊 <b>Thống kê hệ thống</b>\n\n"
		f"👥 Tổng users: <b>{int(stats.get('total_users', 0))}</b>\n"
		f"📱 Tổng apps: <b>{int(stats.get('total_apps', 0))}</b>\n"
		f"🔔 Tổng watches: <b>{int(stats.get('total_watches', 0))}</b>\n"
		f"🟢 Apps OPEN: <b>{int(stats.get('open_apps', 0))}</b>\n\n"
		"🏆 <b>Top app được theo dõi:</b>\n"
		f"{top_text}"
	)


def error_invalid_app_id_message() -> str:
	"""Build error message for invalid app id format."""
	return "❌ App ID không hợp lệ. Vui lòng nhập đúng 8 ký tự chữ và số."


def error_app_not_found_message(app_id: str) -> str:
	"""Build error message when app id does not exist on TestFlight."""
	return f"❌ Không tìm thấy app với App ID <code>{escape(app_id)}</code> trên TestFlight."


def error_max_watches_message(max_count: int) -> str:
	"""Build error message when user reaches watch limit."""
	return f"⚠️ Bạn đã đạt giới hạn theo dõi tối đa: <b>{max_count}</b> app."


def error_already_watching_message(app_name: str) -> str:
	"""Build error message for duplicate watch attempts."""
	return f"ℹ️ Bạn đã theo dõi <b>{escape(app_name)}</b> từ trước rồi."


def discover_message(count: int) -> str:
	"""Build message for discovered open TestFlight apps."""
	return (
		"🌐 <b>Khám phá qua departures.to</b>\n\n"
		f"Tìm thấy <b>{count}</b> app đang mở slot!\n"
		"📌 Nguồn: <a href='https://departures.to'>departures.to</a>\n\n"
		"Nhấn vào app để theo dõi ngay 👇"
	)


def recheck_message(app_name: str, app_id: str, status: str) -> str:
	"""Build message for manual slot recheck result."""
	status = status.upper()
	status_label = {
		"OPEN": "🟢 OPEN — Còn slot! Vào ngay!",
		"CLOSED": "🔴 CLOSED — Chưa có slot",
	}.get(status, "⚫ UNKNOWN — Không lấy được trạng thái")
	return (
		"🔄 <b>Kết quả kiểm tra</b>\n\n"
		f"📱 <b>{escape(app_name)}</b>\n"
		f"🆔 <code>{escape(app_id)}</code>\n"
		f"{status_label}\n\n"
		"🕐 Vừa kiểm tra xong"
	)
