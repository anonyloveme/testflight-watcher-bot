"""Telegram bot handlers for commands, callbacks, and watch flow."""

import asyncio
from html import escape
import os
import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from bot.keyboards import *
from bot.messages import *
from bot.messages import (
    check_all_loading_message,
    check_all_result_message,
    recheck_message,
)
from core.departures import get_open_apps_cached
from core.testflight import fetch_app_info, validate_app_id
from database import get_db
from database.crud import *

WAITING_APP_ID = 1

WATCH_PROMPT = (
    "🔗 <b>Gửi link TestFlight để theo dõi!</b>\n\n"
    "Ví dụ:\n"
    "<code>https://testflight.apple.com/join/m2kxP5cw</code>\n\n"
    "💡 Copy link từ App Store hoặc trang web của app rồi paste vào đây."
)


def _with_db_session():
    """Create a DB session generator and concrete session object."""
    db_gen = get_db()
    db = next(db_gen)
    return db_gen, db


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command and ensure user exists in DB."""
    try:
        user = update.effective_user
        if not user or not update.effective_message:
            return

        db_gen, db = _with_db_session()
        try:
            get_or_create_user(
                db=db,
                chat_id=user.id,
                username=user.username or "",
                first_name=user.first_name or "",
                language_code=user.language_code or "en",
            )
        finally:
            db_gen.close()

        await update.effective_message.reply_text(
            "👇 Menu luôn hiển thị bên dưới để thao tác nhanh!",
            reply_markup=persistent_menu_keyboard(),
        )

        await update.effective_message.reply_text(
            welcome_message(user.first_name or "bạn"),
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(),
        )
    except Exception as exc:
        print(f"[start_handler] Error: {exc}")


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command."""
    try:
        if not update.effective_message:
            return

        help_text = (
            "🆘 <b>Hướng dẫn sử dụng</b>\n\n"
            "• /start - Bắt đầu bot\n"
            "• /watch - Nhập App ID để theo dõi\n"
            "• /help - Xem hướng dẫn\n\n"
            "Bạn cũng có thể dùng các nút menu để thao tác nhanh."
        )
        await update.effective_message.reply_text(
            help_text,
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(),
        )
    except Exception as exc:
        print(f"[help_handler] Error: {exc}")


async def discover_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Discover apps that are currently open on TestFlight."""
    try:
        query = update.callback_query
        message = update.effective_message

        if query:
            await query.answer()
            await query.edit_message_text(
                "🌐 Đang tải danh sách app từ departures.to...\n⏳ Vui lòng chờ 10-20 giây",
                parse_mode="HTML",
            )
        elif message:
            await message.reply_text(
                "🌐 Đang tải danh sách app từ departures.to...\n⏳ Vui lòng chờ 10-20 giây",
                parse_mode="HTML",
            )

        open_apps = await asyncio.to_thread(get_open_apps_cached)
        if not open_apps:
            no_results_text = (
                "😔 Hiện không tìm thấy app nào đang mở slot.\n"
                "Thử lại sau vài phút hoặc vào thẳng "
                "<a href='https://departures.to'>departures.to</a> để xem."
            )
            if query:
                await query.edit_message_text(
                    no_results_text,
                    parse_mode="HTML",
                    reply_markup=main_menu_keyboard(),
                )
            elif message:
                await message.reply_text(
                    no_results_text,
                    parse_mode="HTML",
                    reply_markup=main_menu_keyboard(),
                )
            return

        display_apps = [
            {
                "name": app.get("app_name") or app.get("name") or "Unknown App",
                "app_id": app.get("app_id", ""),
                "status": app.get("status", "OPEN"),
            }
            for app in open_apps[:10]
            if app.get("app_id")
        ]

        if not display_apps:
            no_results_text = "😔 Không lấy được TestFlight link từ departures.to. Thử lại sau."
            if query:
                await query.edit_message_text(
                    no_results_text,
                    parse_mode="HTML",
                    reply_markup=main_menu_keyboard(),
                )
            elif message:
                await message.reply_text(
                    no_results_text,
                    parse_mode="HTML",
                    reply_markup=main_menu_keyboard(),
                )
            return

        text = discover_message(len(open_apps))
        keyboard = popular_apps_keyboard(display_apps)
        if query:
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)
        elif message:
            await message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)
    except Exception as exc:
        print(f"[discover_handler] Error: {exc}")


async def watch_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start watch flow and ask user for app id."""
    try:
        query = update.callback_query
        if query:
            await query.answer()
            await query.edit_message_text(
                WATCH_PROMPT,
                parse_mode="HTML",
                reply_markup=cancel_keyboard(),
            )
            return WAITING_APP_ID

        message = update.effective_message
        if not message:
            return ConversationHandler.END

        await message.reply_text(
            WATCH_PROMPT,
            parse_mode="HTML",
            reply_markup=cancel_keyboard(),
        )
        return WAITING_APP_ID
    except Exception as exc:
        print(f"[watch_start] Error: {exc}")
        return ConversationHandler.END


async def watch_receive_app_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive app id from user, validate, and prepare confirmation step."""
    try:
        message = update.effective_message
        user = update.effective_user
        if not message or not user or not message.text:
            return ConversationHandler.END

        user_input = message.text.strip()

        # Tự động parse nếu user gửi link đầy đủ
        # Hỗ trợ các dạng:
        # https://testflight.apple.com/join/ABCDEFGH
        # testflight.apple.com/join/ABCDEFGH
        # ABCDEFGH (App ID trực tiếp)
        patterns = [
            r"testflight\.apple\.com/join/([A-Za-z0-9]{8})",  # link dạng URL
            r"^([A-Za-z0-9]{8})$",  # App ID trực tiếp
        ]
        app_id = None
        for pattern in patterns:
            match = re.search(pattern, user_input)
            if match:
                app_id = match.group(1)
                break

        if not app_id:
            await message.reply_text(
                "❌ <b>Không nhận ra link này!</b>\n\n"
                "Vui lòng gửi đúng link TestFlight, ví dụ:\n"
                "<code>https://testflight.apple.com/join/m2kxP5cw</code>\n\n"
                "💡 Link TestFlight luôn có dạng <b>testflight.apple.com/join/...</b>",
                parse_mode="HTML",
                reply_markup=cancel_keyboard(),
            )
            return WAITING_APP_ID

        if not validate_app_id(app_id):
            await message.reply_text(
                error_invalid_app_id_message(),
                parse_mode="HTML",
                reply_markup=cancel_keyboard(),
            )
            return WAITING_APP_ID

        max_watches = int(os.getenv("MAX_WATCHES_PER_USER", "5"))
        db_gen, db = _with_db_session()
        try:
            current_count = count_user_watches(db, user.id)
        finally:
            db_gen.close()

        if current_count >= max_watches:
            await message.reply_text(
                error_max_watches_message(max_watches),
                parse_mode="HTML",
                reply_markup=main_menu_keyboard(),
            )
            return ConversationHandler.END

        try:
            # Wrap sync fetch trong thread để không block event loop
            app_info = await asyncio.to_thread(fetch_app_info, app_id)
            app_info["source"] = "testflight"
        except ValueError:
            await message.reply_text(
                error_app_not_found_message(app_id),
                parse_mode="HTML",
                reply_markup=main_menu_keyboard(),
            )
            return ConversationHandler.END
        except Exception:
            await message.reply_text(
                "❌ Không thể kết nối TestFlight. Vui lòng thử lại sau.",
                parse_mode="HTML",
                reply_markup=main_menu_keyboard(),
            )
            return ConversationHandler.END

        context.user_data["pending_app"] = app_info
        await message.reply_text(
            app_info_message(app_info),
            parse_mode="HTML",
            reply_markup=confirm_watch_keyboard(app_id),
        )
        return ConversationHandler.END
    except Exception as exc:
        print(f"[watch_receive_app_id] Error: {exc}")
        return ConversationHandler.END


async def watch_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel watch conversation and return to main menu."""
    try:
        query = update.callback_query
        if query:
            await query.answer()
            await query.edit_message_text(
                "Đã huỷ thao tác. Quay về menu chính.",
                parse_mode="HTML",
                reply_markup=main_menu_keyboard(),
            )
            return ConversationHandler.END

        message = update.effective_message
        if not message:
            return ConversationHandler.END

        await message.reply_text(
            "Đã huỷ thao tác. Quay về menu chính.",
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(),
        )
    except Exception as exc:
        print(f"[watch_cancel] Error: {exc}")
    return ConversationHandler.END


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Route all callback query actions from inline keyboards."""
    try:
        query = update.callback_query
        user = update.effective_user
        if not query or not user:
            return

        await query.answer()
        data = query.data or ""

        if data == "check_all":
            await check_all_handler(update, context)
            return

        if data == "watch":
            await watch_start(update, context)
            return

        if data == "discover":
            await discover_handler(update, context)
            return

        if data == "stats":
            await show_stats(update, context)
            return

        if data == "mylist":
            await show_my_list(update, context)
            return

        if data == "back_main":
            await query.edit_message_text(
                "🏠 <b>Menu chính</b>",
                parse_mode="HTML",
                reply_markup=main_menu_keyboard(),
            )
            return

        if data == "back_mylist":
            await show_my_list(update, context)
            return

        if data == "cancel":
            context.user_data.pop("pending_app", None)
            await query.edit_message_text(
                "Đã huỷ thao tác.",
                parse_mode="HTML",
                reply_markup=main_menu_keyboard(),
            )
            return

        if data.startswith("confirm_watch:"):
            app_id = data.split(":", 1)[1]
            app_info = context.user_data.get("pending_app")
            if not app_info:
                await query.edit_message_text(
                    "Không tìm thấy dữ liệu app đang chờ xác nhận.",
                    parse_mode="HTML",
                    reply_markup=main_menu_keyboard(),
                )
                return

            db_gen, db = _with_db_session()
            try:
                app = get_or_create_app(
                    db,
                    app_id=app_info.get("app_id", app_id),
                    app_name=app_info.get("app_name", "Unknown App"),
                    bundle_id=app_info.get("bundle_id", ""),
                    status=app_info.get("status", "UNKNOWN"),
                )
                watch, is_new = add_watch(db, chat_id=user.id, app_id=app.app_id)
            finally:
                db_gen.close()

            context.user_data.pop("pending_app", None)
            if not is_new:
                await query.edit_message_text(
                    error_already_watching_message(app.app_name or app.app_id),
                    parse_mode="HTML",
                    reply_markup=main_menu_keyboard(),
                )
                return

            await query.edit_message_text(
                watch_success_message(app.app_name or app.app_id, app.app_id),
                parse_mode="HTML",
                reply_markup=main_menu_keyboard(),
            )
            return

        if data.startswith("detail:"):
            app_id = data.split(":", 1)[1]
            db_gen, db = _with_db_session()
            try:
                app = get_app_by_app_id(db, app_id)
            finally:
                db_gen.close()

            if not app:
                await query.edit_message_text(
                    error_app_not_found_message(app_id),
                    parse_mode="HTML",
                    reply_markup=main_menu_keyboard(),
                )
                return

            await query.edit_message_text(
                app_info_message(
                    {
                        "app_name": app.app_name or "Unknown App",
                        "app_id": app.app_id,
                        "status": app.current_status,
                        "bundle_id": app.bundle_id or "N/A",
                    }
                ),
                parse_mode="HTML",
                reply_markup=app_detail_keyboard(app_id),
            )
            return

        if data.startswith("recheck:"):
            app_id = data.split(":", 1)[1]
            db_gen, db = _with_db_session()
            try:
                app = get_app_by_app_id(db, app_id)
            finally:
                db_gen.close()

            if not app:
                await query.edit_message_text(
                    error_app_not_found_message(app_id),
                    parse_mode="HTML",
                    reply_markup=main_menu_keyboard(),
                )
                return

            app_name = app.app_name or app_id
            current_status = app.current_status

            await query.edit_message_text(
                f"⏳ Đang kiểm tra slot cho <b>{escape(app_name)}</b>...",
                parse_mode="HTML",
            )

            try:
                fresh_info = await asyncio.to_thread(fetch_app_info, app_id)
                new_status = fresh_info["status"]
            except Exception:
                new_status = "UNKNOWN"

            if new_status != "UNKNOWN" and new_status != current_status:
                db_gen, db = _with_db_session()
                try:
                    update_app_status(db, app_id, new_status)
                finally:
                    db_gen.close()

            await query.edit_message_text(
                recheck_message(app_name, app_id, new_status),
                parse_mode="HTML",
                reply_markup=app_detail_keyboard(app_id),
            )
            return

        if data.startswith("unwatch:"):
            app_id = data.split(":", 1)[1]
            db_gen, db = _with_db_session()
            try:
                app = get_app_by_app_id(db, app_id)
                removed = remove_watch(db, chat_id=user.id, app_id=app_id)
            finally:
                db_gen.close()

            if removed and app:
                await query.edit_message_text(
                    unwatch_success_message(app.app_name or app.app_id),
                    parse_mode="HTML",
                )
            else:
                await query.edit_message_text(
                    "Không tìm thấy theo dõi để xoá.",
                    parse_mode="HTML",
                )
            await show_my_list(update, context)
            return

        if data.startswith("quick_watch:"):
            app_id = data.split(":", 1)[1]
            db_gen, db = _with_db_session()
            try:
                app = get_app_by_app_id(db, app_id)
                if not app:
                    app_info = fetch_app_info(app_id)
                    app = get_or_create_app(
                        db,
                        app_id=app_info.get("app_id", app_id),
                        app_name=app_info.get("app_name", "Unknown App"),
                        bundle_id=app_info.get("bundle_id", ""),
                        status=app_info.get("status", "UNKNOWN"),
                    )
                watch, is_new = add_watch(db, chat_id=user.id, app_id=app.app_id)
            except ValueError:
                await query.edit_message_text(
                    error_app_not_found_message(app_id),
                    parse_mode="HTML",
                    reply_markup=main_menu_keyboard(),
                )
                return
            except Exception:
                await query.edit_message_text(
                    "❌ Không thể theo dõi app lúc này. Vui lòng thử lại.",
                    parse_mode="HTML",
                    reply_markup=main_menu_keyboard(),
                )
                return
            finally:
                db_gen.close()

            if not is_new:
                await query.edit_message_text(
                    error_already_watching_message(app.app_name or app.app_id),
                    parse_mode="HTML",
                    reply_markup=main_menu_keyboard(),
                )
                return

            await query.edit_message_text(
                watch_success_message(app.app_name or app.app_id, app.app_id),
                parse_mode="HTML",
                reply_markup=main_menu_keyboard(),
            )
            return
    except Exception as exc:
        print(f"[callback_handler] Error: {exc}")


async def check_all_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check live status for all apps currently watched by the user."""
    try:
        query = update.callback_query
        message = update.effective_message
        user = update.effective_user
        if not user:
            return

        db_gen, db = _with_db_session()
        try:
            watches = get_user_watches(db, user.id)
        finally:
            db_gen.close()

        if not watches:
            no_watch_text = (
                "📭 Bạn chưa theo dõi app nào.\n"
                "Dùng <b>➕ Theo dõi app</b> để bắt đầu!"
            )
            if query:
                await query.edit_message_text(
                    no_watch_text,
                    parse_mode="HTML",
                    reply_markup=main_menu_keyboard(),
                )
            elif message:
                await message.reply_text(
                    no_watch_text,
                    parse_mode="HTML",
                    reply_markup=main_menu_keyboard(),
                )
            return

        loading_text = check_all_loading_message(len(watches))
        if query:
            await query.edit_message_text(loading_text, parse_mode="HTML")
        elif message:
            await message.reply_text(loading_text, parse_mode="HTML")
        else:
            return

        results: list[dict] = []
        for watch in watches:
            app = watch.app
            app_id = app.app_id
            app_name = app.app_name or app_id
            old_status = app.current_status or "UNKNOWN"

            try:
                fresh_info = await asyncio.to_thread(fetch_app_info, app_id)
                new_status = fresh_info.get("status", "UNKNOWN")
            except Exception:
                new_status = "UNKNOWN"

            if new_status != "UNKNOWN" and new_status != old_status:
                db_gen, db = _with_db_session()
                try:
                    update_app_status(db, app_id, new_status)
                finally:
                    db_gen.close()

            results.append(
                {
                    "app_name": app_name,
                    "app_id": app_id,
                    "old_status": old_status,
                    "new_status": new_status,
                }
            )

            await asyncio.sleep(0.5)

        result_text = check_all_result_message(results)
        result_keyboard = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("📱 Xem danh sách", callback_data="mylist")],
                [InlineKeyboardButton("🏠 Menu chính", callback_data="back_main")],
            ]
        )

        if query:
            await query.edit_message_text(
                result_text,
                parse_mode="HTML",
                reply_markup=result_keyboard,
                disable_web_page_preview=True,
            )
        elif message:
            await message.reply_text(
                result_text,
                parse_mode="HTML",
                reply_markup=result_keyboard,
                disable_web_page_preview=True,
            )
    except Exception as exc:
        print(f"[check_all_handler] Error: {exc}")


async def menu_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle fixed text actions from persistent reply keyboard."""
    try:
        message = update.effective_message
        if not message:
            return

        text = (message.text or "").strip()
        if text == "➕ Theo dõi app":
            await watch_start(update, context)
        elif text == "📱 Danh sách của tôi":
            await show_my_list(update, context)
        elif text == "🔄 Kiểm tra tất cả":
            await check_all_handler(update, context)
        elif text == "🌐 Khám phá OPEN":
            await discover_handler(update, context)
        elif text == "📊 Thống kê":
            await show_stats(update, context)
        elif text == "❓ Hướng dẫn":
            await help_handler(update, context)
    except Exception as exc:
        print(f"[menu_text_handler] Error: {exc}")


async def show_my_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's current watch list."""
    try:
        user = update.effective_user
        if not user:
            return

        db_gen, db = _with_db_session()
        try:
            watches = get_user_watches(db, user.id)
        finally:
            db_gen.close()

        text = my_list_message(watches)
        keyboard = my_list_keyboard(watches)

        query = update.callback_query
        if query:
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)
        elif update.effective_message:
            await update.effective_message.reply_text(
                text,
                parse_mode="HTML",
                reply_markup=keyboard,
            )
    except Exception as exc:
        print(f"[show_my_list] Error: {exc}")


async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show global statistics overview."""
    try:
        db_gen, db = _with_db_session()
        try:
            stats = get_stats(db)
        finally:
            db_gen.close()

        text = stats_message(stats)
        query = update.callback_query
        if query:
            await query.edit_message_text(
                text,
                parse_mode="HTML",
                reply_markup=main_menu_keyboard(),
            )
        elif update.effective_message:
            await update.effective_message.reply_text(
                text,
                parse_mode="HTML",
                reply_markup=main_menu_keyboard(),
            )
    except Exception as exc:
        print(f"[show_stats] Error: {exc}")


async def debug_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin-only command: compare DB status and live TestFlight status."""
    admin_id = int(os.getenv("TELEGRAM_ADMIN_CHAT_ID", "0"))
    user = update.effective_user
    message = update.effective_message
    if not user or not message or user.id != admin_id:
        return

    await message.reply_text("🔄 Đang force-check tất cả app...")

    db_gen, db = _with_db_session()
    try:
        apps = get_all_apps(db)
        if not apps:
            await message.reply_text("⚠️ Không có app nào trong DB!")
            return

        lines = [f"📊 Tổng: <b>{len(apps)}</b> apps\n"]
        for app in apps:
            real_status = check_app_status(app.app_id)
            db_status = app.current_status
            match = "✅" if real_status == db_status else "⚠️ MISMATCH"
            lines.append(
                f"{match} <code>{app.app_id}</code> {app.app_name or ''}\n"
                f"   DB: {db_status} | Real: {real_status}"
            )

        chunk = ""
        for line in lines:
            if len(chunk) + len(line) > 3500:
                await message.reply_text(chunk, parse_mode="HTML")
                chunk = ""
            chunk += line + "\n"
        if chunk:
            await message.reply_text(chunk, parse_mode="HTML")
    finally:
        db_gen.close()


def setup_handlers(app: Application):
    """Register all bot handlers to the Telegram application."""
    watch_conversation = ConversationHandler(
        entry_points=[
            CommandHandler("watch", watch_start),
            CallbackQueryHandler(watch_start, pattern="^watch$"),
            MessageHandler(filters.Text(["➕ Theo dõi app"]), watch_start),
        ],
        states={
            WAITING_APP_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, watch_receive_app_id)
            ]
        },
        fallbacks=[
            CommandHandler("cancel", watch_cancel),
            CallbackQueryHandler(watch_cancel, pattern="^cancel$"),
        ],
    )

    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("help", help_handler))
    app.add_handler(CommandHandler("discover", discover_handler))
    app.add_handler(CommandHandler("debug", debug_handler))

    menu_filter = filters.Text(
        [
            "📱 Danh sách của tôi",
            "🔄 Kiểm tra tất cả",
            "🌐 Khám phá OPEN",
            "📊 Thống kê",
            "❓ Hướng dẫn",
        ]
    )
    app.add_handler(MessageHandler(menu_filter, menu_text_handler))

    app.add_handler(watch_conversation)
    app.add_handler(CallbackQueryHandler(callback_handler))
