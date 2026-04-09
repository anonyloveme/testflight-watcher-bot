"""Database setup utilities.

Creates SQLAlchemy engine/session from DATABASE_URL and exposes init helpers.
"""

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .models import Base

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///database.db")

# SQLite needs check_same_thread disabled for multi-threaded app contexts.
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """Yield a database session and close it after use."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all database tables defined by ORM models."""
    Base.metadata.create_all(bind=engine)
