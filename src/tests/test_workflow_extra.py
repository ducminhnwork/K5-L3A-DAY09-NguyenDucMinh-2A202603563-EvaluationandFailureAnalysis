from __future__ import annotations

import json
from pathlib import Path

from lab8.shapes.workflow import run_claim


def test_workflow_unknown_claim_returns_failed_with_valid_trace(public_db: Path) -> None:
    result = run_claim("UNKNOWN-999", seed=11, store_path=str(public_db))
    assert result.status == "failed"
    assert result.proposal_amount == 0
    assert result.refund_effects == []
    assert result.committed_audit_count == 0
    assert result.error_reason == "unknown_claim"

    trace_data = json.loads(Path(result.trace_path).read_text(encoding="utf-8"))
    assert trace_data["run_id"] == result.run_id
    assert isinstance(trace_data["events"], list)
    assert len(trace_data["events"]) >= 1


def test_workflow_deterministic_and_zero_model_calls(public_db: Path) -> None:
    res_11 = run_claim("C-001", seed=11, store_path=str(public_db))
    res_55 = run_claim("C-001", seed=55, store_path=str(public_db))

    assert res_11.status == "resolved"
    assert res_11.status == res_55.status
    assert res_11.proposal_amount == res_55.proposal_amount
    assert res_11.model_calls == 0
    assert res_55.model_calls == 0
    assert res_11.committed_audit_count == 1

    trace_text = Path(res_11.trace_path).read_text(encoding="utf-8")
    assert "CANARY_SECRET" not in trace_text
