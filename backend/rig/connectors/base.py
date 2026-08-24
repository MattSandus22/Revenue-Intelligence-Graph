"""Connector framework (docs/11 §11.0).

A Connector exposes ordered `streams`; for each stream it fetches records
after an incremental cursor and applies each record to canonical tables.
The SyncRunner owns everything cross-cutting:

- sync_run bookkeeping (mode, stats, status, error capture)
- raw payload landing (raw_record — replay without re-fetch)
- per-stream cursor/watermark persistence on data_source.cursors
- idempotent upserts (connectors key on (tenant, source_system, source_record_id))

Auth secrets never live in data_source.config; clients receive credentials
from the environment/secrets layer and are injected, which is also what makes
connectors testable against fixture clients.
"""

import json
from dataclasses import dataclass, field
from typing import Iterable, Protocol
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


@dataclass
class SourceRecord:
    stream: str
    source_record_id: str
    payload: dict
    cursor_value: str | None = None   # contributes to the stream watermark


@dataclass
class ApplyResult:
    outcome: str                      # created | updated | linked | queued | deferred | skipped
    detail: dict = field(default_factory=dict)


class Connector(Protocol):
    source_system: str
    streams: list[str]

    def fetch(self, stream: str, cursor: str | None) -> Iterable[SourceRecord]: ...
    def apply(self, session: Session, tenant_id: str, record: SourceRecord) -> ApplyResult: ...


class SyncRunner:
    def run(self, session: Session, tenant_id: UUID | str, data_source_id: UUID | str,
            connector: Connector, source_row=None) -> dict:
        tenant_id, data_source_id = str(tenant_id), str(data_source_id)
        source = source_row if source_row is not None else session.execute(
            text("SELECT * FROM data_source WHERE id = :id"), {"id": data_source_id}
        ).mappings().one()
        cursors: dict = dict(source["cursors"] or {})
        mode = "incremental" if cursors else "backfill"

        run_id = session.execute(text(
            "INSERT INTO sync_run (tenant_id, data_source_id, mode) VALUES (:tid, :sid, :mode)"
            " RETURNING id"
        ), {"tid": tenant_id, "sid": data_source_id, "mode": mode}).scalar_one()

        stats: dict[str, dict[str, int]] = {}
        try:
            for stream in connector.streams:
                stream_stats: dict[str, int] = {}
                watermark = cursors.get(stream)
                for record in connector.fetch(stream, watermark):
                    self._land_raw(session, tenant_id, data_source_id, record)
                    result = connector.apply(session, tenant_id, record)
                    stream_stats[result.outcome] = stream_stats.get(result.outcome, 0) + 1
                    if record.cursor_value and (watermark is None or record.cursor_value > watermark):
                        watermark = record.cursor_value
                if watermark is not None:
                    cursors[stream] = watermark
                stats[stream] = stream_stats

            session.execute(text(
                "UPDATE data_source SET cursors = CAST(:cursors AS jsonb) WHERE id = :id"
            ), {"cursors": json.dumps(cursors), "id": data_source_id})
            session.execute(text(
                "UPDATE sync_run SET status = 'succeeded', stats = CAST(:stats AS jsonb),"
                " finished_at = now() WHERE id = :id"
            ), {"stats": json.dumps(stats), "id": str(run_id)})
            return {"sync_run_id": str(run_id), "mode": mode, "status": "succeeded", "stats": stats}
        except Exception as exc:
            # Record the failure on the run row; the caller's transaction manager
            # decides whether partial progress commits (Temporal handles retries
            # in production — docs/13).
            session.execute(text(
                "UPDATE sync_run SET status = 'failed', error = :err,"
                " stats = CAST(:stats AS jsonb), finished_at = now() WHERE id = :id"
            ), {"err": str(exc)[:2000], "stats": json.dumps(stats), "id": str(run_id)})
            session.execute(text(
                "UPDATE data_source SET status = 'action_required' WHERE id = :id"
            ), {"id": data_source_id})
            return {"sync_run_id": str(run_id), "mode": mode, "status": "failed", "error": str(exc)}

    @staticmethod
    def _land_raw(session: Session, tenant_id: str, data_source_id: str,
                  record: SourceRecord) -> None:
        session.execute(text(
            "INSERT INTO raw_record (tenant_id, data_source_id, stream, source_record_id, payload)"
            " VALUES (:tid, :sid, :stream, :rec, CAST(:payload AS jsonb))"
            " ON CONFLICT (tenant_id, data_source_id, stream, source_record_id)"
            " DO UPDATE SET payload = EXCLUDED.payload, fetched_at = now()"
        ), {"tid": tenant_id, "sid": data_source_id, "stream": record.stream,
            "rec": record.source_record_id, "payload": json.dumps(record.payload)})
