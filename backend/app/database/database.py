from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

from app import config  # noqa: F401 - imported for its .env side effect

DATABASE_URL = config.DATABASE_URL

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


# Columns added after the first release. create_all() only creates missing
# tables, never missing columns, so an existing glassbox.db would otherwise
# fail with "no such column" instead of picking these up.
_ADDED_COLUMNS = {
    "runs": {
        "cost_known": "BOOLEAN DEFAULT 1",
    },
    "trace_steps": {
        "cost_known": "BOOLEAN DEFAULT 1",
    },
}


def ensure_schema() -> None:
    """Create tables, then add any columns missing from an older database."""
    Base.metadata.create_all(bind=engine)

    if not DATABASE_URL.startswith("sqlite"):
        # ALTER TABLE syntax differs per backend; only SQLite is auto-migrated.
        return

    inspector = inspect(engine)
    with engine.begin() as connection:
        for table, columns in _ADDED_COLUMNS.items():
            if table not in inspector.get_table_names():
                continue
            existing = {col["name"] for col in inspector.get_columns(table)}
            for name, ddl in columns.items():
                if name not in existing:
                    connection.execute(text("ALTER TABLE " + table + " ADD COLUMN " + name + " " + ddl))
                    print("[db] added column " + table + "." + name)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
