"""Background scheduler for periodic TestFlight status checks."""

import logging
import os

import requests

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from telegram import Bot

from core.departures import get_popular_apps_from_departures
from core.notifier import notify_admin, notify_slot_closed, notify_slot_opened
from core.testflight import check_app_status
from database import get_db
from database.crud import (
    get_all_apps,
    get_or_create_app,
    get_user_watches,
    get_watchers_of_app,
    remove_watch,
    update_app_status,
)

logger = logging.getLogger(__name__)


def _with_db_session():
    """Create a db generator and session object."""
    db_gen = get_db()
    db = next(db_gen)
    return db_gen, db


async def check_all_apps(bot: Bot):
    """Periodic job: check tracked apps and notify on status transitions."""
    db_gen, db = _with_db_session()
    try:
        apps = get_all_apps(db)
        if not apps:
            logger.info("No apps to check")
            return

        logger.info("Checking %d apps...", len(apps))

        for app in apps:
            try:
                old_status = app.current_status
                new_status = check_app_status(app.app_id)

                logger.debug(
                    "App %s (%s): old=%s new=%s",
                    app.app_name,
                    app.app_id,
                    old_status,
                    new_status,
                )

                if new_status not in {"OPEN", "CLOSED"}:
                    logger.debug("App %s: status UNKNOWN, skip", app.app_id)
                    continue

                if new_status == old_status:
                    # Touch last_checked even when status does not change.
                    update_app_status(db, app.app_id, new_status)
                    continue

                updated_app = update_app_status(db, app.app_id, new_status)
                if not updated_app:
                    logger.warning("update_app_status returned None for %s", app.app_id)
                    continue

                app_name = updated_app.app_name or updated_app.app_id
                logger.info(
                    "Status changed: %s (%s): %s -> %s",
                    app_name,
                    app.app_id,
                    old_status,
                    new_status,
                )

                watchers = get_watchers_of_app(db, updated_app.app_id)
                logger.info("App %s has %d watchers", app.app_id, len(watchers))

                if new_status == "OPEN" and old_status != "OPEN":
                    # Notify on UNKNOWN->OPEN and CLOSED->OPEN.
                    if watchers:
                        result = await notify_slot_opened(
                            bot,
                            watchers,
                            app_name=app_name,
                            app_id=updated_app.app_id,
                        )

                        # Auto-unwatch users that opted in for this app.
                        for user in watchers:
                            user_watches = get_user_watches(db, user.chat_id)
                            for watch in user_watches:
                                if (
                                    watch.app
                                    and watch.app.app_id == updated_app.app_id
                                    and watch.auto_unwatch
                                ):
                                    remove_watch(db, user.chat_id, updated_app.app_id)
                                    logger.debug(
                                        "Auto-unwatched user %s from app %s",
                                        user.chat_id,
                                        app.app_id,
                                    )

                        logger.info(
                            "[OPEN] %s -> sent=%d failed=%d",
                            app_name,
                            result["sent"],
                            result["failed"],
                        )
                        await notify_admin(
                            bot,
                            f"🟢 <b>OPEN</b>: {app_name} (<code>{updated_app.app_id}</code>)\n"
                            f"📤 Sent: {result['sent']} | ❌ Failed: {result['failed']}",
                        )
                    else:
                        logger.info("[OPEN] %s -> no watchers, skip notify", app_name)

                elif new_status == "CLOSED" and old_status == "OPEN":
                    # Notify close only for OPEN->CLOSED.
                    close_watchers = []
                    for user in watchers:
                        user_watches = get_user_watches(db, user.chat_id)
                        for watch in user_watches:
                            if (
                                watch.app
                                and watch.app.app_id == updated_app.app_id
                                and watch.notify_on_close
                            ):
                                close_watchers.append(user)
                                break

                    if close_watchers:
                        result = await notify_slot_closed(
                            bot,
                            close_watchers,
                            app_name=app_name,
                            app_id=updated_app.app_id,
                        )
                        logger.info(
                            "[CLOSED] %s -> sent=%d failed=%d",
                            app_name,
                            result["sent"],
                            result["failed"],
                        )
                        await notify_admin(
                            bot,
                            f"🔴 <b>CLOSED</b>: {app_name} (<code>{updated_app.app_id}</code>)\n"
                            f"📤 Sent: {result['sent']} | ❌ Failed: {result['failed']}",
                        )
                    else:
                        logger.info("[CLOSED] %s -> no watchers with notify_on_close", app_name)
            except Exception as exc:
                logger.exception("Error checking app %s: %s", app.app_id, exc)

        logger.info("Done checking %d apps", len(apps))
    finally:
        db_gen.close()


async def sync_popular_apps(bot: Bot):
    """Sync popular apps from departures.to into the local database."""
    db_gen, db = _with_db_session()
    try:
        popular_apps = get_popular_apps_from_departures(limit=20)
        count = 0
        for app in popular_apps:
            try:
                get_or_create_app(
                    db,
                    app_id=app.get("app_id", ""),
                    app_name=app.get("app_name", ""),
                    bundle_id="",
                    status=app.get("status", "UNKNOWN"),
                )
                count += 1
                logger.info("Synced popular app: %s", app.get("app_name", app.get("app_id", "unknown")))
            except Exception as exc:
                logger.warning("Failed to sync popular app %s: %s", app.get("app_id"), exc)

        logger.info("Synced %s popular apps from departures.to", count)
    except Exception as exc:
        logger.warning("Popular apps sync failed: %s", exc)
    finally:
        db_gen.close()


def self_ping():
    """Ping own /health endpoint to prevent Render free tier sleep."""
    try:
        render_url = os.getenv("RENDER_EXTERNAL_URL", "").strip()
        if render_url:
            response = requests.get(f"{render_url}/health", timeout=10)
            logger.info("Self-ping OK: %s", response.status_code)
        else:
            logger.debug("RENDER_EXTERNAL_URL not set, skip self-ping")
    except Exception as exc:
        logger.warning("Self-ping failed: %s", exc)


def create_scheduler(bot: Bot) -> AsyncIOScheduler:
    """Create and configure periodic scheduler without starting it."""
    poll_interval = int(os.environ.get("POLL_INTERVAL", "60"))
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        check_all_apps,
        trigger=IntervalTrigger(seconds=poll_interval),
        args=[bot],
        id="check_all_apps",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        self_ping,
        "interval",
        minutes=5,
        id="self_ping",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        sync_popular_apps,
        trigger=IntervalTrigger(hours=6),
        args=[bot],
        id="sync_popular_apps",
        max_instances=1,
        coalesce=True,
    )
    return scheduler
