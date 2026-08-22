"""Identity resolution: match ladder, confidence bands, review queue."""

import pytest
from sqlalchemy import text

from rig.db import tenant_session
from rig.resolution import (accept_candidate, normalize_name, reject_candidate,
                            resolve_account)


def test_normalize_name():
    assert normalize_name("Acme Corporation") == "acme"
    assert normalize_name("Acme, Inc.") == "acme"
    assert normalize_name("BetaWorks Ltd") == "betaworks"
    assert normalize_name("Globex GmbH") == "globex"


def test_domain_match_auto_links(seeded):
    with tenant_session(seeded["nsc_tenant"]) as s:
        result = resolve_account(
            s, seeded["nsc_tenant"], source_system="testsrc", source_record_id="c-1",
            name="Acme Corporation", domain="acme.com", primary=False,
        )
        assert result.outcome == "linked" and result.method == "domain"
        assert str(result.account_id) == seeded["acme_account"]
        # second call: already linked, idempotent
        again = resolve_account(
            s, seeded["nsc_tenant"], source_system="testsrc", source_record_id="c-1",
            name="Acme Corporation", domain="acme.com",
        )
        assert again.outcome == "already_linked"


def test_high_fuzzy_match_without_domain_queues_for_review(seeded):
    """Name-only matches never silently auto-link at <0.95 confidence."""
    with tenant_session(seeded["nsc_tenant"]) as s:
        result = resolve_account(
            s, seeded["nsc_tenant"], source_system="testsrc", source_record_id="c-2",
            name="BetaWorx Ltd",  # near-miss of seeded 'BetaWorks Ltd', no domain
            primary=False,
        )
        assert result.outcome == "queued" and result.method == "fuzzy_name"
        assert result.confidence and 0.70 <= result.confidence < 0.95
        suggestion = s.execute(text(
            "SELECT a.name FROM identity_candidate ic JOIN account a"
            " ON a.id = ic.suggested_entity_id WHERE ic.source_record_id = 'c-2'"
        )).scalar_one()
    assert suggestion == "BetaWorks Ltd"


def test_primary_source_creates_account_when_no_match(seeded):
    with tenant_session(seeded["nsc_tenant"]) as s:
        result = resolve_account(
            s, seeded["nsc_tenant"], source_system="testsrc", source_record_id="c-3",
            name="Wildly Different Name Co", domain="wdn.example", primary=True,
        )
        assert result.outcome == "created"
        name = s.execute(text("SELECT name FROM account WHERE id = :id"),
                         {"id": str(result.account_id)}).scalar_one()
    assert name == "Wildly Different Name Co"


def test_secondary_source_queues_instead_of_creating(seeded):
    with tenant_session(seeded["nsc_tenant"]) as s:
        result = resolve_account(
            s, seeded["nsc_tenant"], source_system="testsrc", source_record_id="c-4",
            name="Totally Unknown Org", primary=False,
        )
        assert result.outcome == "queued"
        pending = s.execute(text(
            "SELECT count(*) FROM identity_candidate WHERE source_record_id = 'c-4'"
            " AND status = 'pending'"
        )).scalar_one()
    assert pending == 1


def test_accept_candidate_links_and_audits(seeded):
    with tenant_session(seeded["nsc_tenant"]) as s:
        resolve_account(s, seeded["nsc_tenant"], source_system="testsrc",
                        source_record_id="c-5", name="Acmee", primary=False)
        candidate_id = s.execute(text(
            "SELECT id FROM identity_candidate WHERE source_record_id = 'c-5'"
        )).scalar_one()
        account_id = accept_candidate(
            s, seeded["nsc_tenant"], candidate_id, resolved_by="u_reviewer",
            target_account_id=seeded["acme_account"],
        )
        assert str(account_id) == seeded["acme_account"]
        link = s.execute(text(
            "SELECT match_method, confidence, linked_by FROM source_link"
            " WHERE source_record_id = 'c-5'"
        )).one()
    assert link[0] == "human" and float(link[1]) == 1.0 and link[2] == "u_reviewer"


def test_reject_candidate(seeded):
    with tenant_session(seeded["nsc_tenant"]) as s:
        resolve_account(s, seeded["nsc_tenant"], source_system="testsrc",
                        source_record_id="c-6", name="Zzz Unknown", primary=False)
        candidate_id = s.execute(text(
            "SELECT id FROM identity_candidate WHERE source_record_id = 'c-6'"
        )).scalar_one()
        reject_candidate(s, seeded["nsc_tenant"], candidate_id, resolved_by="u_reviewer")
        with pytest.raises(ValueError):
            reject_candidate(s, seeded["nsc_tenant"], candidate_id, resolved_by="u_reviewer")
