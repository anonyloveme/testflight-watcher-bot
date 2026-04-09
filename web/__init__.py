"""Flask application factory for web dashboard."""

import os

from flask import Flask

from web.routes import register_routes


def create_flask_app() -> Flask:
	"""Create Flask app instance and register all routes."""
	app = Flask(__name__)
	register_routes(app)
	return app
