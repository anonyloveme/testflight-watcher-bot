"""Telegram bot handlers for commands, callbacks, and watch flow."""

import os

from telegram import Update
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
from core.testflight import fetch_app_info, validate_app_id
from database import get_db
from database.crud import *

WAITING_APP_ID = 1


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


async def watch_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start watch flow and ask user for app id."""
    try:
        query = update.callback_query
        if query:
            await query.answer()
            await query.edit_message_text(
                "Nhập App ID (8 ký tự chữ và số) để theo dõi:",
                parse_mode="HTML",
                reply_markup=cancel_keyboard(),
            )
            return WAITING_APP_ID

        message = update.effective_message
        if not message:
            return ConversationHandler.END

        await message.reply_text(
            "Nhập App ID (8 ký tự chữ và số) để theo dõi:",
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

        app_id = message.text.strip().upper()
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
            app_info = fetch_app_info(app_id)
        except ValueError:
            await message.reply_text(
                error_app_not_found_message(app_id),
                parse_mode="HTML",
                reply_markup=main_menu_keyboard(),
            )
            return ConversationHandler.END
        except Exception:
            await message.reply_text(
                "❌ Không thể kết nối TestFlight API. Vui lòng thử lại sau.",
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

        if data == "popular":
            await show_popular_apps(update, context)
            return

        if data == "watch":
            await watch_start(update, context)
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


async def show_popular_apps(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show popular apps list from core.popular_apps."""
    try:
        query = update.callback_query
        if not query:
            return

        try:
            from core.popular_apps import POPULAR_APPS
        except Exception:
            POPULAR_APPS = []

        if not POPULAR_APPS:
            await query.edit_message_text(
                "📋 Chưa có danh sách app phổ biến.",
                parse_mode="HTML",
                reply_markup=main_menu_keyboard(),
            )
            return

        await query.edit_message_text(
            "📋 <b>App phổ biến</b>\nChọn app để theo dõi nhanh:",
            parse_mode="HTML",
            reply_markup=popular_apps_keyboard(POPULAR_APPS),
        )
    except Exception as exc:
        print(f"[show_popular_apps] Error: {exc}")


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


def setup_handlers(app: Application):
    """Register all bot handlers to the Telegram application."""
    watch_conversation = ConversationHandler(
        entry_points=[
            CommandHandler("watch", watch_start),
            CallbackQueryHandler(watch_start, pattern="^watch$"),
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
    app.add_handler(watch_conversation)
    app.add_handler(CallbackQueryHandler(callback_handler))
