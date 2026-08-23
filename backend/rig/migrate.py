"""Minimal ordered SQL migration runner.

Applies backend/migrations/*.sql in filename order, recording applied files in
schema_migrations. Plain SQL keeps the schema (including RLS policies and
audit triggers) reviewable in one place.
"""

from pathlib import Path

from sqlalchemy import create_engine, text

from .config import settings

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"

admin_engine = create_engine(settings.admin_database_url, future=True)

import os

# The application role is created/granted on every migration run (idempotent).
# It is deliberately NOT the table owner and NOT a superuser: PostgreSQL RLS
# does not apply to superusers, so app traffic must never use one.
# Password from RIG_APP_DB_PASSWORD (dev default 'rig_app'; production must
# override — enforced by rig.boot's production config check).
_APP_DB_PASSWORD = os.environ.get("RIG_APP_DB_PASSWORD", "rig_app").replace("'", "''")
GRANTS_SQL = f"""
DO $$ BEGIN
  CREATE ROLE rig_app LOGIN PASSWORD '{_APP_DB_PASSWORD}';
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
ALTER ROLE rig_app PASSWORD '{_APP_DB_PASSWORD}';
GRANT USAGE ON SCHEMA public TO rig_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO rig_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO rig_app;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO rig_app;
-- audit log is append-only at the privilege layer too (trigger is backstop)
REVOKE UPDATE, DELETE ON audit_event FROM rig_app;
REVOKE ALL ON schema_migrations FROM rig_app;
"""


def run_migrations() -> list[str]:
    applied: list[str] = []
    with admin_engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            " filename TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        ))
        done = {r[0] for r in conn.execute(text("SELECT filename FROM schema_migrations"))}
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if path.name in done:
                continue
            # Raw DBAPI cursor: migration SQL must reach the server verbatim —
            # files legitimately contain ':' words (comments) and '%' (format()
            # in DO blocks) that client-side parameter parsing would mangle.
            with conn.connection.cursor() as cursor:
                cursor.execute(path.read_text())
            conn.execute(
                text("INSERT INTO schema_migrations (filename) VALUES (:f)"),
                {"f": path.name},
            )
            applied.append(path.name)
        conn.execute(text(GRANTS_SQL))
    return applied


if __name__ == "__main__":
    for name in run_migrations():
        print(f"applied {name}")
