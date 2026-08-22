import sys
from pathlib import Path

import pytest
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rig.migrate import admin_engine, run_migrations  # noqa: E402
from rig.seed import seed_demo  # noqa: E402


@pytest.fixture(scope="session")
def database():
    """Fresh schema per test session: drop everything, re-run migrations.

    Schema ops run on the ADMIN engine; the application engine (rig.db) is a
    non-superuser role so RLS is actually enforced in every test below.
    """
    with admin_engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    run_migrations()
    yield


@pytest.fixture(scope="session")
def seeded(database):
    """Seed demo tenants once; returns the id map."""
    return seed_demo()
