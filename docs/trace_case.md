# Trace case: từ trace tới quyết định sai đầu tiên

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-002@11`, run ID `E-seeded_regression-20261117-35a9` (`R-seeded_regression-C-002-s11`) |
| Triệu chứng | Lab 8 grader FAIL: `status resolved != denied`. Ledger ghi 20.000đ, 1 dòng; nhãn là 0đ, `denied`. Reply "LogiX đã hoàn 20.000đ cho đơn O-202" khớp với ledger nên `reply_matches_ledger` không bắt được ca này. |
| Bước sai đầu tiên | Event 3 `model_override {"delay_days": 5}`: agent ghi đè số ngày trễ của đơn O-202 bằng số 5 trong ticket, trong khi DB ghi 2 ngày. |
| Vì sao là bước *đầu tiên* | Event 1 `handoff` và event 2 `investigator` (`lookup_order` thấy đơn, `visible: true`) đều đúng. Từ event 3 trở đi mọi thứ là hệ quả: event 4 `quote` ra 20.000đ theo 5 ngày, event 6 `reply` báo 20.000đ, host ghi ledger 20.000đ. |
| Failure mode | FM-03 `ticket_trust` (tin ticket hơn DB) |
| Đối chứng | `fixed` chạy 70/70 trial `pass_rate = 1.0` và `db_fact_kept = 1.0` (không có event `model_override` nào trong cả lần chạy), nên C-002@11 không có bước ghi đè và PASS. |
| Regression test | `tests/test_lab9_trace_regression.py` (`test_ticket_trust_is_caught`, `test_clean_trial_passes`): dựng lại trial C-002@11; `DbFactKept` và `RefundAmountCorrect` fail trên bản lỗi, pass trên bản đúng. Chạy: `python -m pytest -q -m student -o addopts= -k trace_regression`. Cổng `eval-gate` cũng chặn `seeded_regression` ở `pass_rate` Δ −0.271, CI [−0.500, −0.057]. |
| Chưa chắc chắn | Trace chỉ cho thấy agent dùng số ngày của ticket, không cho biết vì sao (MockLLM đặt cố định `seed % 5 == 0` hoặc bật cờ `ticket_trust`). Không biết LLM thật có lỗi theo cùng cách hay không. |
