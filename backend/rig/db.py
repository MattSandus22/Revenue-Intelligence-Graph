"""Database access with mandatory tenant context.

Every unit of work runs inside a transaction whose `app.tenant_id` GUC is set
via `set_config(..., is_local => true)`. Row-level security policies (see
migrations/0001_init.sql) key on that setting, so a session without tenant
context sees no tenant rows at all. There is deliberately no code path that
opens a tenant-data session without a tenant id.
"""

from contextlib import contextmanager
from uuid import UUID

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from .config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)


@contextmanager
def tenant_session(tenant_id: UUID | str):
    """Yield a Session bound to one tenant. Commits on success, rolls back on error."""
    with Session(engine) as session, session.begin():
        session.execute(
            text("SELECT set_config('app.tenant_id', :tid, true)"),
            {"tid": str(tenant_id)},
        )
        yield session


@contextmanager
def untenanted_session():
    """A session with NO tenant context — RLS hides all tenant rows.

    Exists only for schema-level operations (migrations bookkeeping) and for
    isolation tests proving that no-context means no data.
    """
    with Session(engine) as session, session.begin():
        yield session
