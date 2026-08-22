"""Data-quality checks, freshness suppression of usage signals, CSV import."""

from datetime import date, timedelta

from sqlalchemy import text

from rig.data_quality import run_checks, usage_is_fresh
from rig.db import tenant_session
from rig.signals.engine import evaluate_account
from rig.usage_import import import_usage_csv

TODAY = date.today()


def test_missing_field_issue_lifecycle(seeded):
    tid = seeded["nsc_tenant"]
    with tenant_session(tid) as s:
        account_id = s.execute(text(
            "INSERT INTO account (tenant_id, name) VALUES (:tid, 'NoRenewalCo') RETURNING id"
        ), {"tid": tid}).scalar_one()
        run_checks(s, tid, today=TODAY)
        issues = s.execute(text(
            "SELECT dedupe_key FROM data_quality_issue WHERE state = 'open'"
            " AND dedupe_key LIKE :k"
        ), {"k": f"missing_field:account:{account_id}:%"}).scalars().all()
        assert len(issues) == 2  # renewal_date + arr_cents

        s.execute(text(
            "UPDATE account SET renewal_date = :d, arr_cents = 100000 WHERE id = :id"
        ), {"d": TODAY + timedelta(days=90), "id": str(account_id)})
        summary = run_checks(s, tid, today=TODAY)
        assert summary["resolved"] >= 2
        still_open = s.execute(text(
            "SELECT count(*) FROM data_quality_issue WHERE state = 'open'"
            " AND dedupe_key LIKE :k"
        ), {"k": f"missing_field:account:{account_id}:%"}).scalar_one()
    assert still_open == 0


def test_stale_usage_creates_issue_and_suppresses_signal(seeded):
    tid = seeded["nsc_tenant"]
    with tenant_session(tid) as s:
        # age Acme's usage data beyond the SLA (two-step shift: the unique
        # constraint on (account, metric, date) is not deferrable, so a direct
        # +/-10 collides with not-yet-shifted rows)
        s.execute(text(
            "UPDATE usage_metric_daily SET date = date - 1000 WHERE account_id = :aid"
        ), {"aid": seeded["acme_account"]})
        s.execute(text(
            "UPDATE usage_metric_daily SET date = date + 990 WHERE account_id = :aid"
        ), {"aid": seeded["acme_account"]})
        assert not usage_is_fresh(s, seeded["acme_account"], TODAY)

        run_checks(s, tid, today=TODAY)
        issue = s.execute(text(
            "SELECT severity FROM data_quality_issue WHERE state = 'open'"
            " AND dedupe_key = :k"
        ), {"k": f"freshness:usage:{seeded['acme_account']}"}).scalar_one()
        assert issue == "high"

        # usage signal must NOT fire on a stale feed (docs/07 U1 FP prevention)
        evaluate_account(s, tid, seeded["acme_account"], today=TODAY)
        state = s.execute(text(
            "SELECT state FROM signal WHERE account_id = :aid"
            " AND signal_type = 'usage_drop_vs_baseline'"
        ), {"aid": seeded["acme_account"]}).scalar_one_or_none()
        assert state in (None, "resolved")

        # restore fixture and confirm recovery (same two-step shift)
        s.execute(text(
            "UPDATE usage_metric_daily SET date = date + 1000 WHERE account_id = :aid"
        ), {"aid": seeded["acme_account"]})
        s.execute(text(
            "UPDATE usage_metric_daily SET date = date - 990 WHERE account_id = :aid"
        ), {"aid": seeded["acme_account"]})
        summary = run_checks(s, tid, today=TODAY)
        assert summary["resolved"] >= 1
        evaluate_account(s, tid, seeded["acme_account"], today=TODAY)
        state = s.execute(text(
            "SELECT state FROM signal WHERE account_id = :aid"
            " AND signal_type = 'usage_drop_vs_baseline'"
        ), {"aid": seeded["acme_account"]}).scalar_one()
    assert state == "active"


def test_csv_import_validation_report(seeded):
    tid = seeded["nsc_tenant"]
    csv_content = "\n".join([
        "account_ref,date,metric,value,user_count",
        f"acme.com,{TODAY.isoformat()},api_calls,1500,12",          # domain match
        f"CSV NameMatch Co,{TODAY.isoformat()},api_calls,300,",     # name match
        f"nonexistent.example,{TODAY.isoformat()},api_calls,10,1",  # unmatched
        f"acme.com,not-a-date,api_calls,10,1",                      # malformed
    ])
    with tenant_session(tid) as s:
        s.execute(text(
            "INSERT INTO account (tenant_id, name, arr_cents, renewal_date)"
            " VALUES (:tid, 'CSV NameMatch Co', 2000000, :renewal)"
        ), {"tid": tid, "renewal": TODAY})
        report = import_usage_csv(s, tid, csv_content)
        assert report["status"] == "partial"
        assert report["imported"] == 2 and report["error_count"] == 2
        assert any("unmatched" in e["error"] for e in report["errors"])
        assert any("malformed" in e["error"] for e in report["errors"])
        value = s.execute(text(
            "SELECT value FROM usage_metric_daily WHERE account_id = :aid"
            " AND metric = 'api_calls' AND date = :d"
        ), {"aid": seeded["acme_account"], "d": TODAY}).scalar_one()
    assert float(value) == 1500.0


def test_csv_import_rejects_missing_columns(seeded):
    with tenant_session(seeded["nsc_tenant"]) as s:
        report = import_usage_csv(s, seeded["nsc_tenant"], "foo,bar\n1,2")
    assert report["status"] == "rejected" and "missing required columns" in report["error"]
