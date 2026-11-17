import pytest

from lab8.db import connect
from lab8.durability import InjectedCrash, committed_audit_count, get_refund, issue_refund


@pytest.mark.parametrize(
    "point",
    ["before_effect", "after_effect_before_checkpoint", "after_checkpoint"],
)
def test_crash_then_resume_gives_one_refund(public_db, point):
    conn = connect(public_db)
    with pytest.raises(InjectedCrash):
        issue_refund(conn, "C-001", 35000, crash_at=point)
    issue_refund(conn, "C-001", 35000)
    effect = get_refund(conn, "C-001")
    audits = committed_audit_count(conn, "C-001")
    rows = conn.execute(
        "SELECT COUNT(*) AS n FROM refund_ledger WHERE claim_id = 'C-001'"
    ).fetchone()["n"]
    conn.close()
    assert int(effect["amount_vnd"]) == 35000
    assert audits == 1
    assert rows == 1