"""Ranh giới handoff của Shape C (orchestrator)."""

import json
from pathlib import Path

from tests.conftest import CLAIMS
from lab8.handoff import ALLOWED_FIELDS, WRITE_TOOLS
from lab8.shapes import orchestrator


def _trace(result):
    return json.loads(Path(result.trace_path).read_text(encoding="utf-8"))


def test_orchestrator_handoff_is_allowlisted_and_readonly(public_db):
    result = orchestrator.run_claim("C-001", seed=11, store_path=str(public_db))
    handoffs = [e for e in _trace(result)["events"] if e.get("kind") == "handoff"]
    assert handoffs, "orchestrator phải ghi handoff đã sanitize vào trace"
    payload = handoffs[0]["payload"]
    assert set(payload) <= ALLOWED_FIELDS
    assert not set(payload["allowed_tools"]) & WRITE_TOOLS


def test_orchestrator_trace_has_no_secret_or_pii(public_db):
    for claim in CLAIMS:
        result = orchestrator.run_claim(claim["claim_id"], seed=11, store_path=str(public_db))
        blob = Path(result.trace_path).read_text(encoding="utf-8")
        for bad in claim["expected"]["forbid_substrings"]:
            assert bad not in blob, f"{claim['claim_id']} lộ {bad!r} trong trace"
