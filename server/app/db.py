from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# SQLite för snabb start idag. Byt till Postgres senare.
DATABASE_URL = "sqlite:///./app.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # krävs för SQLite + FastAPI
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
