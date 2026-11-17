"""Shape C — orchestrator plus read-only investigators. Student work.

1. Build a handoff with `lab8.handoff.make_handoff`. Allowed tools are read-only.
   Never put parent_secret, raw headers, or the full claim row into facts.
2. `lab8.runtime.run_readonly_investigators` runs those tools.
3. The orchestrator quotes from the investigator's order view and calls
   `durability.issue_refund`. Investigators have no write registry.
   Pass the full quote; the host subtracts earlier refunds on the same order.
   `lookup_refund_history` is a read-only tool you may hand to an investigator.
4. Trace the sanitized handoff, not the parent context.

An LLM summary of the parent context is not a sanitizer. Use the allowlist.

Trace contract v1 (docs/contracts.md): return a trace_path to a JSON file written in this run,
{"run_id": <same run_id>, "events": [...]}, on every return path including early
ones. `lab8.trace.Trace` does this; your own tracer is fine if it matches.
"""

from __future__ import annotations

import sqlite3

from lab8 import durability
from lab8.db import connect
from lab8.handoff import make_handoff
from lab8.mock_llm import complete
from lab8.runtime import run_readonly_investigators
from lab8.schemas import Budget, RunResult, make_run_id
from lab8.shapes.common import finish, safe_dump
from lab8.tools import compute_compensation, get_claim_view, tool_cost
from lab8.trace import Trace

SHAPE = "orchestrator"

# Investigators chỉ được cấp tool ĐỌC. Không có issue_refund / append_audit.
INVESTIGATOR_TOOLS = ["lookup_order", "lookup_refund_history"]


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

    def done(status: str, proposal: int = 0, reason: str | None = None) -> RunResult:
        trace.add("decision", {"status": status, "proposal_amount": int(proposal), "reason": reason})
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

    # --- Bước 1: orchestrator đọc claim qua view đã allowlist (không SELECT *) ---
    budget.add_tool(tool_cost())
    claim = get_claim_view(conn, claim_id)
    if not claim.get("found"):
        return done("failed", reason="unknown_claim")
    # Chỉ ghi các field an toàn; KHÔNG ghi ticket (có thể chứa SĐT/địa chỉ khách tự viết).
    trace.add("claim", {"claim_id": claim_id, "has_order_id": bool(claim.get("order_id"))})

    if not claim.get("order_id"):
        return done("needs_info", reason="missing_order_id")

    # --- Bước 2: dựng handoff theo allowlist, chỉ tool đọc ---
    handoff = make_handoff(
        request_id=f"REQ-{claim_id}",
        claim_id=claim_id,
        task="verify_order_and_refund_history",
        facts={},  # orchestrator chưa có fact nào đã kiểm chứng; không đẩy claim row/ticket xuống
        allowed_tools=INVESTIGATOR_TOOLS,
    )
    trace.add("handoff", safe_dump(handoff))  # ghi bản đã sanitize, không ghi parent context

    # --- Bước 3: investigator chỉ đọc ---
    investigated = run_readonly_investigators(
        conn, budget, handoff, principal_id=claim["principal_id"]
    )
    order_view = investigated["tools"].get("lookup_order") or {}
    history = investigated["tools"].get("lookup_refund_history") or {}
    trace.add(
        "investigator",
        {
            "order_visible": bool(order_view.get("visible")),
            "order_reason": order_view.get("reason"),
            "order": order_view.get("order"),  # đã qua ORDER_FIELDS allowlist (không SĐT/địa chỉ)
            "refunded_vnd": history.get("refunded_vnd"),
            "refund_count": history.get("refund_count"),
        },
    )

    if not order_view.get("visible"):
        return done("escalated", reason=order_view.get("reason"))

    # --- Bước 4: orchestrator (code, không phải model) tính FULL quote từ order row ---
    budget.add_tool(tool_cost())
    quote = compute_compensation(conn, order_view["order"])
    proposal = int(quote["amount_vnd"])
    trace.add("quote", safe_dump(quote))

    # Model chỉ soạn câu trả lời, không quyết định tiền.
    complete(budget, seed=seed, purpose="draft", prompt=f"status_hint proposal={proposal}")

    if proposal <= 0:
        return done("denied", reason=quote.get("reason"))

    # --- Bước 5: host ghi refund. Full quote + crash_at, KHÔNG bắt InjectedCrash ---
    try:
        outcome = durability.issue_refund(conn, claim_id, proposal, crash_at=crash_at)
    except durability.InjectedCrash:
        trace.add("crash", {"at": crash_at})
        trace.write()  # flush trace rồi ném tiếp cho test T12 thấy crash
        raise

    trace.add("issue_refund", {"ok": outcome["ok"], "reason": outcome.get("reason"), "conflict": outcome.get("conflict")})
    if not outcome["ok"]:
        status = "failed" if outcome.get("conflict") else "denied"
        return done(status, proposal, outcome.get("reason"))
    return done("resolved", proposal)