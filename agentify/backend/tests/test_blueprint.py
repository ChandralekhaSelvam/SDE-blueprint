"""Tests for the parts that break demos: ingest, policy, and the DoD contract."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("POLICY_DIR", os.path.join(os.path.dirname(__file__), "..", "policy"))

from app.config import Settings  # noqa: E402
from app.agents.pipeline import Pipeline  # noqa: E402
from app.ingest import IngestError, parse_inventory  # noqa: E402
from app.pii import mask  # noqa: E402
from app.policy import load_pack  # noqa: E402
from app.schemas import Band, Blueprint, Task  # noqa: E402
from app.scoring import score_task  # noqa: E402

MOCK = os.path.join(os.path.dirname(__file__), "..", "..", "mock-data")
SAMPLES = ["unilever-legal.csv", "honeywell-p2p.csv", "csl-quality.csv", "charter-care.csv"]


def read(name: str) -> bytes:
    with open(os.path.join(MOCK, name), "rb") as fh:
        return fh.read()


# ------------------------------------------------------------------- ingest

@pytest.mark.parametrize("name", SAMPLES)
def test_every_sample_parses(name):
    tasks, _ = parse_inventory(read(name), name)
    assert len(tasks) > 10
    assert all(t.l4_name for t in tasks)


def test_title_block_and_aliased_columns():
    """charter-care.csv has two title rows and non-standard headers."""
    tasks, _ = parse_inventory(read("charter-care.csv"), "charter-care.csv")
    assert len(tasks) == 18
    assert any("subscriber" in t.l4_name.lower() for t in tasks)
    assert any(t.volume_per_month for t in tasks)


def test_semicolon_delimiter():
    body = b"L1 Code;L1 Name;L4 Code;L4 Name\n9.0;Finance;9.1.1;Post journal entry\n"
    tasks, _ = parse_inventory(body, "euro.csv")
    assert tasks[0].l4_name == "Post journal entry"


def test_missing_optional_columns_still_parses():
    body = b"L4 Code,L4 Name\n1.1.1,Validate an invoice\n1.1.2,Approve a payment\n"
    tasks, warnings = parse_inventory(body, "thin.csv")
    assert len(tasks) == 2
    assert any("volume" in w.lower() or "code" in w.lower() for w in warnings)


def test_empty_file_raises():
    with pytest.raises(IngestError):
        parse_inventory(b"", "empty.csv")


def test_headerless_junk_raises():
    with pytest.raises(IngestError):
        parse_inventory(b"a,b,c\n1,2,3\n", "junk.csv")


# ---------------------------------------------------------------------- pii

def test_masking_catches_common_identifiers():
    result = mask("Email payroll@acme.com about CASE-99812 for Mr John Smith")
    assert "payroll@acme.com" not in result.text
    assert "CASE-99812" not in result.text
    assert "[NAME]" in result.text
    assert result.total >= 3


# ------------------------------------------------------------------ scoring

def make_task(**kw) -> Task:
    base = dict(
        id="T1", l1_code="9.0", l1_name="Finance", l2_code="9.2", l2_name="Accounts Payable",
        l3_code="9.2.1", l3_name="Invoice Capture", l4_code="9.2.1.1", l4_name="Post journal entry",
        volume_per_month=8000, avg_handle_minutes=5, rule_based=95, systems="SAP API", exception_rate=0.03,
    )
    base.update(kw)
    return Task(**base)


def test_high_volume_rule_bound_task_is_autonomous():
    scored = score_task(make_task(), load_pack("industrial"))
    assert scored.band is Band.FULL_AGENT
    assert scored.score >= 75


def test_judgement_work_is_human_only_however_often_it_runs():
    """Volume must never make judgement work automatable."""
    scored = score_task(
        make_task(l4_name="Negotiate settlement with counterparty", rule_based=12,
                  exception_rate=0.5, volume_per_month=9000),
        load_pack("consumer_products"),
    )
    assert scored.band is Band.HUMAN_ONLY
    assert any(o.rule == "judgement_dominant" for o in scored.overrides)


def test_pii_flag_caps_the_score():
    scored = score_task(make_task(pii=True), load_pack("industrial"))
    assert scored.score <= 60
    assert any(o.rule == "pii" for o in scored.overrides)
    assert any(e.kind == "policy" for e in scored.evidence)


def test_keyword_rules_do_not_match_the_process_group_name():
    """A group called 'Contract Management' must not cap every activity in it."""
    scored = score_task(
        make_task(l2_name="Contract Management", l3_name="Contract Review",
                  l4_name="File executed document in the repository"),
        load_pack("consumer_products"),
    )
    assert not any(o.rule == "contract_commitment" for o in scored.overrides)


def test_every_score_carries_evidence_and_a_rationale():
    scored = score_task(make_task(), load_pack("industrial"))
    assert scored.evidence and scored.rationale
    assert abs(sum(d.weight for d in scored.dimensions) - 1.0) < 1e-9


# ----------------------------------------------------------- definition of done

@pytest.fixture(scope="module")
def blueprint() -> Blueprint:
    os.environ.update(RUN_MODE="demo", LLM_PROVIDER="mock", DATA_DIR="/tmp/agentify-test")
    tasks, warnings = parse_inventory(read("unilever-legal.csv"), "unilever-legal.csv")
    result = None
    for item in Pipeline(Settings()).run(tasks, "consumer_products", "Legal", warnings):
        if isinstance(item, Blueprint):
            result = item
    assert result is not None
    return result


def test_dod_agent_catalog(blueprint):
    assert blueprint.agents
    for agent in blueprint.agents:
        assert agent.name and agent.purpose and agent.tools and agent.guardrails


def test_dod_dependencies(blueprint):
    ids = {a.id for a in blueprint.agents}
    assert blueprint.dependencies
    for dep in blueprint.dependencies:
        assert dep.source in ids and dep.target in ids
        assert dep.payload and dep.schema_ref


def test_dod_human_gates(blueprint):
    assert blueprint.gates
    for gate in blueprint.gates:
        assert gate.reason and gate.triggers and gate.reviewer_role


def test_dod_automation_estimate_per_agent(blueprint):
    for agent in blueprint.agents:
        est = agent.estimate
        assert est.source_task_count > 0
        assert est.annual_hours_after <= est.annual_hours_today
        assert 0 <= est.automation_pct <= 100


def test_dod_every_row_traces_to_its_source_task(blueprint):
    task_ids = {t.task.id for t in blueprint.scored_tasks}
    assert len(blueprint.traceability) == blueprint.task_count
    for row in blueprint.traceability:
        assert row.task_id in task_ids
        assert row.agent_id != "unassigned"
        assert row.evidence, f"{row.task_id} has no evidence"


def test_all_three_bands_are_represented(blueprint):
    """A run where everything lands in one band means the policy is misconfigured."""
    assert all(blueprint.band_totals[b.value] > 0 for b in Band)


def test_demo_mode_reports_avoided_calls(blueprint):
    assert blueprint.cost.llm_calls_avoided > blueprint.cost.llm_calls
    assert blueprint.cost.naive_cost_usd > blueprint.cost.total_cost_usd


def test_bridge_arithmetic_is_consistent(blueprint):
    bridge = blueprint.bridge
    assert bridge.fte_after < bridge.fte_today
    assert abs(bridge.steps[-1]["to"] - bridge.fte_after) < 0.2
    assert abs(sum(s["share_of_hours"] for s in bridge.steps) - 100) < 1.0


def test_provider_failure_still_produces_a_blueprint():
    """The whole point of the deterministic path: a dead provider is a warning."""
    os.environ.update(RUN_MODE="live", LLM_PROVIDER="anthropic", ANTHROPIC_API_KEY="sk-ant-invalid")
    tasks, warnings = parse_inventory(read("csl-quality.csv"), "csl-quality.csv")
    result = None
    for item in Pipeline(Settings()).run(tasks, "life_sciences", "Quality", warnings):
        if isinstance(item, Blueprint):
            result = item
    os.environ.update(RUN_MODE="demo", LLM_PROVIDER="mock")
    assert result is not None
    assert result.agents and result.traceability
    assert any("unavailable" in w for w in result.warnings)
