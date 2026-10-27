import uuid
from datetime import UTC, datetime

from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import DATABASE_URL

database_url = make_url(DATABASE_URL)
engine_options: dict[str, object] = {}
if database_url.drivername == "sqlite":
    if database_url.database not in (None, "", ":memory:"):
        from pathlib import Path

        Path(database_url.database).parent.mkdir(parents=True, exist_ok=True)
    engine_options["connect_args"] = {"check_same_thread": False}
    if database_url.database in (None, "", ":memory:"):
        engine_options["poolclass"] = StaticPool

engine = create_engine(database_url, **engine_options)
if database_url.drivername == "sqlite":
    @event.listens_for(engine, "connect")
    def _register_sqlite_functions(connection, _record) -> None:
        connection.create_function("gen_random_uuid", 0, lambda: uuid.uuid4().hex)
        connection.create_function(
            "now",
            0,
            lambda: datetime.now(UTC).isoformat(sep=" "),
        )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def initialize_database() -> None:
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    if engine.dialect.name == "sqlite":
        with engine.begin() as connection:
            connection.exec_driver_sql(
                """
                CREATE TRIGGER IF NOT EXISTS validate_asset_status_insert
                BEFORE INSERT ON assets
                WHEN NEW.status_source NOT IN ('user', 'workflow_adapter')
                  OR trim(NEW.status_actor) = ''
                  OR trim(NEW.status_reason) = ''
                  OR (NEW.operational_status = 'available'
                      AND NEW.status_stale_after IS NULL)
                BEGIN
                    SELECT RAISE(ABORT, 'Invalid operational status provenance');
                END
                """
            )
            connection.exec_driver_sql(
                """
                CREATE TRIGGER IF NOT EXISTS validate_asset_status_update
                BEFORE UPDATE OF operational_status, status_source, status_actor,
                                 status_reason, status_stale_after ON assets
                WHEN NEW.status_source NOT IN ('user', 'workflow_adapter')
                  OR trim(NEW.status_actor) = ''
                  OR trim(NEW.status_reason) = ''
                  OR (NEW.operational_status = 'available'
                      AND NEW.status_stale_after IS NULL)
                  OR (NEW.operational_status != OLD.operational_status
                      AND NEW.status_source = OLD.status_source
                      AND NEW.status_actor = OLD.status_actor
                      AND NEW.status_reason = OLD.status_reason)
                BEGIN
                    SELECT RAISE(ABORT, 'Operational status changes require valid provenance');
                END
                """
            )
