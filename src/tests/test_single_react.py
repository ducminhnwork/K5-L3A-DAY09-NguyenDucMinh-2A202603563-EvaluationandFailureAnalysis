"""Shape B (single ReAct agent) boundary tests. Author: Hoàng Lam Minh (2A202603566).

These run in the default host gate (`python -m pytest -q`), so they must stay green.
They check what the public matrix does not check directly:

- the agent trusts the order row, not the delay the customer writes in the ticket;
- the ReAct loop only ever dispatches read tools (never issue_refund);
- model calls are counted in the Budget and the loop respects max_steps;
- a step-cap stop returns a valid failed RunResult with a trace, and writes no money;
- the trace never contains parent_secret, headers, PII, or the raw ticket.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import lab8.runtime as runtime
from lab8.db import connect, init_store
from lab8.durability import get_refund
from lab8.handoff import READONLY_TOOLS, WRITE_TOOLS
from lab8.shapes import single
from tests.conftest import BY_ID, CLAIMS, WORLD


def _store(tmp_path: Path, name: str) -> str:
    path = tmp_path / name
    init_store(path, WORLD, CLAIMS).close()
    return str(path)


def _trace(result) -> dict:
    return json.loads(Path(result.trace_path).read_text(encoding="utf-8"))


@pytest.mark.parametrize("seed", [11, 22, 33, 44, 55])
def test_single_ignores_overstated_ticket_delay(tmp_path, seed):
    # C-002: ticket says "trễ 5 ngày", order row says 2 days -> must deny on every seed
    # (the swarm reference pays on seed 55; the single agent must not).
    store = _store(tmp_path, f"c002-{seed}.sqlite")
    result = single.run_claim("C-002", seed=seed, store_path=store)
    assert result.status == "denied"
    assert result.proposal_amount == 0
    assert result.refund_effects == []
    conn = connect(store)
    try:
        assert get_refund(conn, "C-002") is None
    finally:
        conn.close()
    steps = [e["payload"] for e in _trace(result)["events"] if e["kind"] == "react_step"]
    assert any("ticket_mismatch" in step for step in steps)


def test_single_loop_dispatches_only_read_tools(tmp_path, monkeypatch):
    called: list[str] = []
    real_dispatch = runtime.dispatch

    def spy(conn, budget, name, args, *, worker):
        called.append(name)
        return real_dispatch(conn, budget, name, args, worker=worker)

    monkeypatch.setattr(runtime, "dispatch", spy)
    store = _store(tmp_path, "c001.sqlite")
    result = single.run_claim("C-001", seed=11, store_path=store)
    assert result.status == "resolved"
    assert called, "ReAct loop should call at least one read tool"
    assert not set(called) & WRITE_TOOLS
    assert set(called) <= READONLY_TOOLS
    # Expected plan for a payable claim: order -> refund history -> compensation.
    assert called == ["lookup_order", "lookup_refund_history", "compute_compensation"]


def test_single_counts_model_calls_and_respects_step_cap(tmp_path):
    store = _store(tmp_path, "c001-budget.sqlite")
    result = single.run_claim("C-001", seed=11, store_path=store)
    events = _trace(result)["events"]
    decide_calls = next(e["payload"]["react_steps"] for e in events if e["kind"] == "decision")
    assert decide_calls == sum(1 for e in events if e["kind"] == "react_step")
    assert 1 <= decide_calls <= single.MAX_STEPS == 8
    # One model call per ReAct step, plus one draft reply after the loop.
    assert result.model_calls == decide_calls + 1
    assert result.input_tokens > 0 and result.output_tokens > 0
    assert result.cost_estimate > 0


def test_single_step_cap_fails_closed_without_refund(tmp_path, monkeypatch):
    monkeypatch.setattr(single, "MAX_STEPS", 2)  # too few steps to reach a quote
    store = _store(tmp_path, "c001-cap.sqlite")
    result = single.run_claim("C-001", seed=11, store_path=store)
    assert result.status == "failed"
    assert result.error_reason == "step_cap"
    assert result.refund_effects == []
    assert _trace(result)["run_id"] == result.run_id
    conn = connect(store)
    try:
        assert get_refund(conn, "C-001") is None
    finally:
        conn.close()


@pytest.mark.parametrize("claim_id", ["C-001", "C-004", "C-005", "C-009", "C-010", "C-013"])
def test_single_trace_has_no_secret_pii_or_ticket(tmp_path, claim_id):
    store = _store(tmp_path, f"{claim_id}-leak.sqlite")
    result = single.run_claim(claim_id, seed=11, store_path=store)
    blob = Path(result.trace_path).read_text(encoding="utf-8") + json.dumps(result.as_dict(), ensure_ascii=False)
    row = BY_ID[claim_id]
    forbidden = list(row["expected"].get("forbid_substrings") or []) + ["CANARY_SECRET", "Bearer", row["ticket"]]
    for token in forbidden:
        assert token not in blob, f"trace leaked {token!r}"
