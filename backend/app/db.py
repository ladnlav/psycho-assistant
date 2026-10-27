from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def _make_engine(url: str):
    if url.startswith("sqlite") and ":memory:" in url:
        # Тесты: одна общая in-memory база на все соединения.
        return create_engine(url, connect_args={"check_same_thread": False}, poolclass=StaticPool)
    # Синхронные эндпоинты FastAPI работают в пуле из 40 потоков: столько же соединений с базой (20 + 20 сверх),
    # иначе при 100 пользователях запросы ждали свободное соединение (по умолчанию 5 + 10) и падали через 30 с.
    return create_engine(url, pool_pre_ping=True, pool_size=20, max_overflow=20)


engine = _make_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session
