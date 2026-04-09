"""SQLAlchemy ORM models for TestFlight Watcher Bot."""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all ORM models."""


class User(Base):
    """Telegram user who can watch TestFlight apps."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String, nullable=True)
    first_name: Mapped[str | None] = mapped_column(String, nullable=True)
    language_code: Mapped[str] = mapped_column(String, default="en")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    watches: Mapped[list["Watch"]] = relationship("Watch", back_populates="user")


class App(Base):
    """TestFlight app tracked by the system."""

    __tablename__ = "apps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    app_id: Mapped[str] = mapped_column(String(8), unique=True, nullable=False)
    app_name: Mapped[str | None] = mapped_column(String, nullable=True)
    bundle_id: Mapped[str | None] = mapped_column(String, nullable=True)
    current_status: Mapped[str] = mapped_column(String, default="UNKNOWN")
    last_checked: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    watcher_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    watches: Mapped[list["Watch"]] = relationship("Watch", back_populates="app")
    status_history: Mapped[list["StatusHistory"]] = relationship(
        "StatusHistory", back_populates="app"
    )


class Watch(Base):
    """Mapping between user and app watch preferences."""

    __tablename__ = "watches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    app_id_fk: Mapped[int] = mapped_column(ForeignKey("apps.id"), nullable=False)
    notify_on_open: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_on_close: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_unwatch: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship("User", back_populates="watches")
    app: Mapped["App"] = relationship("App", back_populates="watches")


class StatusHistory(Base):
    """Historical status transitions for tracked apps."""

    __tablename__ = "status_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    app_id_fk: Mapped[int] = mapped_column(ForeignKey("apps.id"), nullable=False)
    old_status: Mapped[str] = mapped_column(String, nullable=False)
    new_status: Mapped[str] = mapped_column(String, nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    app: Mapped["App"] = relationship("App", back_populates="status_history")
