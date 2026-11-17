"""Shape B — one ReAct agent. Student work.

Use `lab8.runtime.run_react` with max_steps=8. `decide` may pick a read tool.
It must not call `issue_refund`. After the loop, the host validates the quote
and is the only writer.

A decide() that trusts ticket text over the order row will fail hidden claims
where the customer overstates the delay or cites a superseded clause.

Per-order cap: an order may already have been refunded by an earlier claim.
The read tool `lookup_refund_history` shows how much. The host still enforces
the cap, so pass the full quote to `durability.issue_refund`, not a net amount.

Caps: stop at 8 steps. Count model calls in the Budget so cost stays comparable.

Trace contract v1 (docs/contracts.md): return a trace_path to a JSON file written in this run,
{"run_id": <same run_id>, "events": [...]}, on every return path including early
ones. `lab8.trace.Trace` does this; your own tracer is fine if it matches.

Implementation notes (Hoàng Lam Minh):

- Ranh giới code / model: `decide` (agent) chỉ chọn tool ĐỌC theo thứ tự
  lookup_order -> lookup_refund_history -> compute_compensation -> final.
  Mọi model call đi qua `mock_llm.complete` nên được đếm vào Budget.
- Số tiền không bao giờ lấy từ text của model hay ticket: shape chỉ dùng kết quả
  thật do `dispatch` trả về (ghi vào `memory`), và `compute_compensation` luôn
  nhận order row từ `lookup_order`, không nhận delay khách tự khai.
- Sau vòng lặp, chính code của shape quyết định nhánh (escalated / denied /
  refund) và gọi `durability.issue_refund` với quote đầy đủ + crash_at.
- Trace chỉ ghi field đã allowlist (order view, quote, outcome); không ghi
  ticket, claim row thô, parent_secret hay header.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from lab8.db import connect
from lab8.durability import InjectedCrash, issue_refund
from lab8.mock_llm import complete, parse_delay_days
from lab8.runtime import dispatch, run_react
from lab8.schemas import Budget, RunResult, make_run_id
from lab8.shapes.common import finish, safe_dump
from lab8.trace import Trace

SHAPE = "single"
MAX_STEPS = 8
# Tools the agent may request. All read-only; issue_refund is never offered.
AGENT_TOOLS = ("lookup_order", "lookup_refund_history", "compute_compensation")


def run_claim(
    claim_id: str,
    *,
    seed: int,
    store_path: str,
    crash_at: str | None = None,
) -> RunResult:
    conn = connect(store_path)
    try:
        return _run(conn, claim_id, seed=seed, crash_at=crash_at)
    finally:
        conn.close()


def _run(conn: sqlite3.Connection, claim_id: str, *, seed: int, crash_at: str | None) -> RunResult:
    budget = Budget()
    trace = Trace(make_run_id(SHAPE, claim_id, seed))

    memory: dict[str, Any] = {}

    def done(status: str, proposal: int, reason: str | None) -> RunResult:
        trace.add("decision", {
            "status": status,
            "proposal_amount": int(proposal),
            "error_reason": reason,
            "react_steps": memory.get("decide_calls", 0),
            "react_stopped": memory.get("stopped"),
        })
        return finish(
            conn,
            shape=SHAPE,
            claim_id=claim_id,
            seed=seed,
            status=status,
            proposal_amount=proposal,
            budget=budget,
            trace=trace,
            error_reason=reason,
        )

    try:
        claim = dispatch(conn, budget, "get_claim_view", {"claim_id": claim_id}, worker=False)
        if not claim.get("found"):
            return done("failed", 0, "unknown_claim")
        # Only non-sensitive facts about the claim go to the trace.
        trace.add("claim", {"claim_id": claim_id, "has_order_id": bool(claim.get("order_id"))})

        if not claim.get("order_id"):
            # Never recover an order id from ticket text.
            complete(budget, seed=seed, purpose="draft", prompt="needs_info")
            return done("needs_info", 0, "missing_order_id")

        decide = _make_decide(budget, seed=seed, claim=claim, memory=memory, trace=trace)
        loop = run_react(
            conn,
            budget,
            observation={"claim": {"claim_id": claim_id, "order_id": claim["order_id"]}},
            decide=decide,
            max_steps=MAX_STEPS,
        )
        memory["stopped"] = loop["stopped"]

        # From here on the shape's own code decides, using real tool results only.
        order_view = memory.get("lookup_order")
        if order_view is not None and not order_view.get("visible"):
            complete(budget, seed=seed, purpose="draft", prompt="escalated")
            return done("escalated", 0, order_view.get("reason"))
        if loop["stopped"] != "final" or "compute_compensation" not in memory:
            return done("failed", 0, loop["final"].get("error_reason") or "incomplete_react")

        quote_payload = memory["compute_compensation"]
        proposal = int(quote_payload["amount_vnd"])
        trace.add("quote", safe_dump(quote_payload))
        complete(budget, seed=seed, purpose="draft", prompt=f"proposal={proposal}")

        if proposal <= 0:
            return done("denied", 0, quote_payload.get("reason"))

        try:
            # Full quote: the host subtracts what other claims already got for this order.
            outcome = issue_refund(conn, claim_id, proposal, crash_at=crash_at)
        except InjectedCrash:
            trace.add("crash", {"at": crash_at})
            trace.write()
            raise
        trace.add("refund", {"ok": bool(outcome["ok"]), "reason": outcome.get("reason"),
                             "conflict": bool(outcome.get("conflict"))})
        if not outcome["ok"]:
            return done("failed" if outcome["conflict"] else "denied", proposal, outcome["reason"])
        return done("resolved", proposal, None)
    except InjectedCrash:
        raise
    except Exception as exc:  # run_claim must not raise; record the type only, never the message.
        return done("failed", 0, f"exception:{type(exc).__name__}")


def _make_decide(budget: Budget, *, seed: int, claim: dict[str, Any], memory: dict[str, Any], trace: Trace):
    """The agent policy. Picks the next read tool; never sees or requests a write tool."""
    principal_id = claim["principal_id"]
    order_id = claim["order_id"]
    ticket_delay = parse_delay_days(claim.get("ticket") or "")

    def decide(seen: dict[str, Any]) -> dict[str, Any]:
        memory["decide_calls"] = memory.get("decide_calls", 0) + 1
        # One trace event per ReAct step: what was observed, then what the agent chose.
        event: dict[str, Any] = {"step": memory["decide_calls"]}
        # Record the observation from the previous step (a real tool result from dispatch).
        last_tool = seen.get("last_tool")
        if last_tool in AGENT_TOOLS:
            memory[last_tool] = seen["last_result"]
            event["observed"] = {"tool": last_tool, "result": _trace_view(last_tool, seen["last_result"])}

        # One model call per ReAct step. The prompt is used for token accounting only.
        if last_tool is None:
            prompt = f"claim {claim['claim_id']} ticket: {claim.get('ticket') or ''}"
        else:
            prompt = f"observed {last_tool}"
        complete(budget, seed=seed, purpose="react", prompt=prompt)

        order_view = memory.get("lookup_order")
        if order_view is None:
            action: dict[str, Any] = {"tool": "lookup_order", "args": {"order_id": order_id, "principal_id": principal_id}}
        elif not order_view.get("visible"):
            action = {"final": {"status": "escalated", "error_reason": order_view.get("reason")}}
        elif "lookup_refund_history" not in memory:
            action = {"tool": "lookup_refund_history", "args": {"order_id": order_id, "principal_id": principal_id}}
        elif "compute_compensation" not in memory:
            order = dict(order_view["order"])  # the DB row is the source of truth
            if ticket_delay is not None and ticket_delay != int(order["delay_days"]):
                event["ticket_mismatch"] = {"field": "delay_days", "used": "order_row"}
            action = {"tool": "compute_compensation", "args": {"order": order}}
        else:
            action = {"final": {"status": "propose"}}

        event["action"] = action.get("tool") or "final"
        trace.add("react_step", event)
        return action

    return decide


def _trace_view(tool: str, result: dict[str, Any]) -> dict[str, Any]:
    """Allowlisted tool output only. lookup_order already strips PII to ORDER_FIELDS."""
    if tool == "lookup_order":
        view = {"visible": bool(result.get("visible")), "reason": result.get("reason")}
        if result.get("visible"):
            view["order"] = safe_dump(result["order"])
        return view
    if tool == "lookup_refund_history":
        keys = ("visible", "reason", "refund_count", "refunded_vnd")
        return {k: result[k] for k in keys if k in result}
    if tool == "compute_compensation":
        keys = ("amount_vnd", "reason", "clause_ids")
        return safe_dump({k: result[k] for k in keys if k in result})
    return {}
