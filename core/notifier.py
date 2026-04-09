"""Telegram notification helpers for app status changes."""

import asyncio
import logging
import os

from telegram import Bot
from telegram.error import BadRequest, Forbidden, TelegramError

from bot.messages import slot_closed_notification, slot_open_notification

logger = logging.getLogger(__name__)


async def send_message_to_user(bot: Bot, chat_id: int, text: str) -> bool:
    """Send a message to one user and return whether it succeeds."""
    try:
        await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
        return True
    except Forbidden:
        logger.warning("Cannot send to %s: user blocked bot", chat_id)
        return False
    except BadRequest as exc:
        if "chat not found" in str(exc).lower():
            logger.warning("Cannot send to %s: chat not found", chat_id)
            return False
        logger.error("BadRequest when sending to %s: %s", chat_id, exc)
        return False
    except TelegramError as exc:
        logger.error("TelegramError when sending to %s: %s", chat_id, exc)
        return False


async def notify_slot_opened(bot: Bot, watchers: list, app_name: str, app_id: str) -> dict:
    """Notify all watchers that an app slot is OPEN."""
    payload = slot_open_notification(app_name, app_id)
    sent = 0
    failed = 0

    for watcher in watchers:
        ok = await send_message_to_user(bot, int(watcher.chat_id), payload)
        if ok:
            sent += 1
        else:
            failed += 1
        await asyncio.sleep(0.05)

    return {"sent": sent, "failed": failed}


async def notify_slot_closed(bot: Bot, watchers: list, app_name: str, app_id: str) -> dict:
    """Notify selected watchers that an app slot is CLOSED."""
    payload = slot_closed_notification(app_name, app_id)
    sent = 0
    failed = 0

    for watcher in watchers:
        ok = await send_message_to_user(bot, int(watcher.chat_id), payload)
        if ok:
            sent += 1
        else:
            failed += 1
        await asyncio.sleep(0.05)

    return {"sent": sent, "failed": failed}


async def notify_admin(bot: Bot, message: str):
    """Send important operational notifications to admin chat."""
    admin_chat_id = os.environ.get("TELEGRAM_ADMIN_CHAT_ID", "").strip()
    if not admin_chat_id:
        logger.warning("TELEGRAM_ADMIN_CHAT_ID is not set")
        return

    try:
        await bot.send_message(chat_id=int(admin_chat_id), text=message, parse_mode="HTML")
    except TelegramError as exc:
        logger.error("Failed to notify admin: %s", exc)
