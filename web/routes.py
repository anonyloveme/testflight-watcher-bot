"""Flask routes for dashboard pages and JSON APIs."""

import os

from flask import Flask, jsonify, render_template

from database import get_db
from database.crud import (
    get_all_apps,
    get_app_by_app_id,
    get_open_apps,
    get_stats,
    get_top_watched_apps,
)


def _serialize_app_summary(app) -> dict:
    """Convert App model to summary JSON dictionary."""
    return {
        "app_id": app.app_id,
        "app_name": app.app_name,
        "status": app.current_status,
        "watcher_count": app.watcher_count,
        "last_checked": app.last_checked.isoformat() if app.last_checked else None,
    }


def _serialize_app_detail(app) -> dict:
    """Convert App model to detailed JSON dictionary."""
    return {
        "id": app.id,
        "app_id": app.app_id,
        "app_name": app.app_name,
        "bundle_id": app.bundle_id,
        "status": app.current_status,
        "watcher_count": app.watcher_count,
        "last_checked": app.last_checked.isoformat() if app.last_checked else None,
        "created_at": app.created_at.isoformat() if app.created_at else None,
    }


def register_routes(app: Flask):
    """Register page and API routes."""
    bot_username = os.environ.get("BOT_USERNAME", "your_bot_username_here")

    @app.context_processor
    def inject_global_template_context():
        """Inject shared values to all templates."""
        return {"BOT_USERNAME": bot_username}

    def _with_db_session():
        """Create db session generator and session object."""
        db_gen = get_db()
        db = next(db_gen)
        return db_gen, db

    @app.route("/")
    def index():
        """Render dashboard with stats, top apps, and open apps."""
        db_gen, db = _with_db_session()
        try:
            stats = get_stats(db)
            top_apps = get_top_watched_apps(db, limit=5)
            open_apps = get_open_apps(db)
            return render_template(
                "index.html",
                stats=stats,
                top_apps=top_apps,
                open_apps=open_apps,
                bot_username=os.environ.get("BOT_USERNAME", ""),
            )
        finally:
            db_gen.close()

    @app.route("/apps")
    def apps_list():
        """Render page with all tracked apps."""
        db_gen, db = _with_db_session()
        try:
            all_apps = get_all_apps(db)
            return render_template(
                "apps.html",
                apps=all_apps,
                bot_username=os.environ.get("BOT_USERNAME", ""),
            )
        finally:
            db_gen.close()

    @app.route("/api/stats")
    def api_stats():
        """Return dashboard stats as JSON."""
        db_gen, db = _with_db_session()
        try:
            stats = get_stats(db)
            return jsonify(stats)
        finally:
            db_gen.close()

    @app.route("/api/apps")
    def api_apps():
        """Return all tracked apps as JSON list."""
        db_gen, db = _with_db_session()
        try:
            all_apps = get_all_apps(db)
            return jsonify([_serialize_app_summary(app_item) for app_item in all_apps])
        finally:
            db_gen.close()

    @app.route("/api/apps/<app_id>")
    def api_app_detail(app_id: str):
        """Return details for one app by app_id."""
        db_gen, db = _with_db_session()
        try:
            app_item = get_app_by_app_id(db, app_id)
            if not app_item:
                return jsonify({"error": "App not found"}), 404
            return jsonify(_serialize_app_detail(app_item))
        finally:
            db_gen.close()

    @app.route("/health")
    def health():
        """Return health status response."""
        return jsonify({"status": "ok", "bot": "running"})

    @app.errorhandler(404)
    def not_found(e):
        """Return JSON for unknown routes."""
        return jsonify({"error": "Not found"}), 404
