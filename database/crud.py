"""CRUD helpers for users, apps, watches, and status history."""

from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from .models import App, StatusHistory, User, Watch


def get_or_create_user(
	db: Session,
	chat_id: int,
	username: str,
	first_name: str,
	language_code: str,
) -> User:
	"""Get a user by chat_id or create a new one."""
	user = db.query(User).filter(User.chat_id == chat_id).first()
	if user:
		return user

	user = User(
		chat_id=chat_id,
		username=username,
		first_name=first_name,
		language_code=language_code or "en",
	)
	db.add(user)
	db.commit()
	db.refresh(user)
	return user


def get_user_by_chat_id(db: Session, chat_id: int) -> User | None:
	"""Return a user by chat_id or None if not found."""
	return db.query(User).filter(User.chat_id == chat_id).first()


def ban_user(db: Session, chat_id: int) -> bool:
	"""Ban a user by setting is_banned=True."""
	user = get_user_by_chat_id(db, chat_id)
	if not user:
		return False

	user.is_banned = True
	db.commit()
	db.refresh(user)
	return True


def get_all_users(db: Session) -> list[User]:
	"""Return all active and non-banned users."""
	return (
		db.query(User)
		.filter(User.is_active.is_(True), User.is_banned.is_(False))
		.all()
	)


def get_or_create_app(
	db: Session,
	app_id: str,
	app_name: str,
	bundle_id: str,
	status: str,
) -> App:
	"""Get an app by app_id or create a new app record."""
	app = get_app_by_app_id(db, app_id)
	if app:
		# Backfill app_name when legacy rows were created without it.
		if not app.app_name and app_name:
			app.app_name = app_name
			db.commit()
			db.refresh(app)
		return app

	app = App(
		app_id=app_id,
		app_name=app_name,
		bundle_id=bundle_id,
		# Always start with UNKNOWN so the first scheduler check can detect
		# the real status transition and notify watchers.
		current_status="UNKNOWN",
		last_checked=datetime.now(),
	)
	db.add(app)
	db.commit()
	db.refresh(app)
	return app


def get_app_by_app_id(db: Session, app_id: str) -> App | None:
	"""Return an app by app_id or None if not found."""
	return db.query(App).filter(App.app_id == app_id).first()


def update_app_status(db: Session, app_id: str, new_status: str) -> App | None:
	"""Update app status, history, and watcher_count."""
	app = get_app_by_app_id(db, app_id)
	if not app:
		return None

	old_status = app.current_status
	app.current_status = new_status
	app.last_checked = datetime.now()

	if old_status != new_status:
		history = StatusHistory(
			app_id_fk=app.id,
			old_status=old_status,
			new_status=new_status,
			changed_at=datetime.now(),
		)
		db.add(history)

	app.watcher_count = (
		db.query(func.count(Watch.id)).filter(Watch.app_id_fk == app.id).scalar() or 0
	)
	db.commit()
	db.refresh(app)
	return app


def get_top_watched_apps(db: Session, limit: int = 10) -> list[App]:
	"""Return apps ordered by watcher_count descending."""
	return db.query(App).order_by(App.watcher_count.desc()).limit(limit).all()


def get_all_apps(db: Session) -> list[App]:
	"""Return all apps in the database."""
	return db.query(App).all()


def get_open_apps(db: Session) -> list[App]:
	"""Return apps that currently have OPEN status."""
	return db.query(App).filter(App.current_status == "OPEN").all()


def add_watch(
	db: Session,
	chat_id: int,
	app_id: str,
	auto_unwatch: bool = True,
) -> tuple[Watch, bool]:
	"""Create a watch record for user and app, if not existing."""
	user = get_user_by_chat_id(db, chat_id)
	if not user:
		user = User(chat_id=chat_id, language_code="en")
		db.add(user)
		db.commit()
		db.refresh(user)

	app = get_app_by_app_id(db, app_id)
	if not app:
		app = App(app_id=app_id, current_status="UNKNOWN")
		db.add(app)
		db.commit()
		db.refresh(app)

	watch = (
		db.query(Watch)
		.filter(Watch.user_id == user.id, Watch.app_id_fk == app.id)
		.first()
	)
	if watch:
		return watch, False

	watch = Watch(user_id=user.id, app_id_fk=app.id, auto_unwatch=auto_unwatch)
	db.add(watch)
	db.commit()
	db.refresh(watch)

	app.watcher_count = (
		db.query(func.count(Watch.id)).filter(Watch.app_id_fk == app.id).scalar() or 0
	)
	db.commit()
	db.refresh(app)
	return watch, True


def remove_watch(db: Session, chat_id: int, app_id: str) -> bool:
	"""Remove a watch record and update app watcher_count."""
	user = get_user_by_chat_id(db, chat_id)
	app = get_app_by_app_id(db, app_id)
	if not user or not app:
		return False

	watch = (
		db.query(Watch)
		.filter(Watch.user_id == user.id, Watch.app_id_fk == app.id)
		.first()
	)
	if not watch:
		return False

	db.delete(watch)
	db.commit()

	app.watcher_count = (
		db.query(func.count(Watch.id)).filter(Watch.app_id_fk == app.id).scalar() or 0
	)
	db.commit()
	db.refresh(app)
	return True


def get_user_watches(db: Session, chat_id: int) -> list[Watch]:
	"""Return all watches of a user with eager-loaded app."""
	user = get_user_by_chat_id(db, chat_id)
	if not user:
		return []

	return (
		db.query(Watch)
		.options(joinedload(Watch.app))
		.filter(Watch.user_id == user.id)
		.all()
	)


def get_watchers_of_app(db: Session, app_id: str) -> list[User]:
	"""Return all users watching the given app_id."""
	app = get_app_by_app_id(db, app_id)
	if not app:
		return []

	return (
		db.query(User)
		.join(Watch, Watch.user_id == User.id)
		.filter(Watch.app_id_fk == app.id)
		.all()
	)


def count_user_watches(db: Session, chat_id: int) -> int:
	"""Count total watches of a user by chat_id."""
	user = get_user_by_chat_id(db, chat_id)
	if not user:
		return 0

	return db.query(func.count(Watch.id)).filter(Watch.user_id == user.id).scalar() or 0


def remove_all_watches_for_app(db: Session, app_id: str) -> None:
	"""Remove all watch records for a given app_id."""
	app = get_app_by_app_id(db, app_id)
	if not app:
		return

	db.query(Watch).filter(Watch.app_id_fk == app.id).delete(synchronize_session=False)
	app.watcher_count = 0
	db.commit()
	db.refresh(app)


def get_stats(db: Session) -> dict:
	"""Return aggregate statistics for dashboard and admin usage."""
	total_users = db.query(func.count(User.id)).scalar() or 0
	total_apps = db.query(func.count(App.id)).scalar() or 0
	total_watches = db.query(func.count(Watch.id)).scalar() or 0
	open_apps = db.query(func.count(App.id)).filter(App.current_status == "OPEN").scalar() or 0

	top_apps_models = get_top_watched_apps(db, limit=10)
	top_apps = [
		{
			"app_id": app.app_id,
			"app_name": app.app_name,
			"watcher_count": app.watcher_count,
		}
		for app in top_apps_models
	]

	return {
		"total_users": total_users,
		"total_apps": total_apps,
		"total_watches": total_watches,
		"open_apps": open_apps,
		"top_apps": top_apps,
	}
