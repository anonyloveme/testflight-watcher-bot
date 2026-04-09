"""Main entrypoint for running Telegram bot and Flask dashboard."""

import os
import asyncio
import logging
import threading

from dotenv import load_dotenv
from telegram import Bot
from telegram.ext import Application

load_dotenv()

# Setup logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

from database import init_db
from bot.handlers import setup_handlers
from core.scheduler import create_scheduler
from web import create_flask_app


async def run_bot():
    """Start Telegram bot and scheduler runtime."""
    token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    if not token:
        raise ValueError("TELEGRAM_TOKEN is missing. Please set TELEGRAM_TOKEN in .env")

    # Clean old webhook before polling to avoid getUpdates conflict on restart.
    async with Bot(token=token) as bot:
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("✅ Đã xóa webhook cũ, sẵn sàng polling...")

    application = Application.builder().token(token).build()
    setup_handlers(application)

    scheduler = create_scheduler(application.bot)
    try:
        await application.initialize()
        await application.start()
        scheduler.start()
        logger.info("✅ Bot đang chạy...")

        if application.updater:
            await application.updater.start_polling(drop_pending_updates=True)

        await asyncio.Event().wait()
    finally:
        try:
            if scheduler.running:
                scheduler.shutdown(wait=False)
        except Exception as exc:
            logger.error("Error shutting down scheduler: %s", exc)

        try:
            if application.updater:
                await application.updater.stop()
        except Exception as exc:
            logger.error("Error stopping updater: %s", exc)

        try:
            await application.stop()
            await application.shutdown()
        except Exception as exc:
            logger.error("Error shutting down application: %s", exc)


def run_flask():
    """Run Flask dashboard in a separate daemon thread."""
    flask_app = create_flask_app()
    port = int(os.environ.get("PORT", 5000))
    logger.info("🌐 Web dashboard chạy tại port %s", port)
    flask_app.run(host="0.0.0.0", port=port, use_reloader=False)


if __name__ == "__main__":
    logger.info("🚀 Khởi động TestFlight Watcher Bot...")

    init_db()
    logger.info("✅ Database đã khởi tạo")

    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    asyncio.run(run_bot())
