"""Database engine and session helpers."""
from __future__ import annotations

from sqlmodel import Session, SQLModel, create_engine

from .config import settings

connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(settings.DATABASE_URL, connect_args=connect_args, echo=False)


def init_db() -> None:
    Path = __import__("pathlib").Path
    if settings.DATABASE_URL.startswith("sqlite"):
        # Ensure parent directory exists for file-based sqlite.
        url = settings.DATABASE_URL.split("///", 1)[-1]
        if url and url != ":memory:":
            Path(url).parent.mkdir(parents=True, exist_ok=True)
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session
