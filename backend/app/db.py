from functools import lru_cache

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


@lru_cache
def engine():
    instance = create_engine(settings().database_url, pool_pre_ping=True, pool_size=5, max_overflow=5, connect_args={"timeout": 5})

    @event.listens_for(instance, "connect")
    def query_timeout(connection, _record):
        connection.timeout = 30

    return instance


def session_factory():
    return sessionmaker(bind=engine(), expire_on_commit=False)


def get_db():
    with session_factory()() as db:
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
