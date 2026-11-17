# Eval card — LogiX-VN refund agent

- **Run ID / eval set SHA:** baseline `E-swarm-20261117-35a9`; PR chạy thử `E-fixed-20261117-35a9` và `E-seeded_regression-20261117-35a9`; eval set `35a9cfd79055`
- **Phiên bản:** code (commit) `f490b22` · eval set v1 (sha `35a9cfd79055`) · metric_spec 1.0 · grader (commit) `f490b22` · seeds 11/22/33/44/55
- **Eval set:** v1, 14 item × 5 seed (70 trial mỗi lần chạy), nguồn lab8_public; nhãn: `labels_v1.json`, tách khỏi item, `failure_modes` gắn theo `docs/failure_taxonomy.md`
- **Metric & ngưỡng** (`config/metric_spec.yaml`):

  | Metric | Loại | Ngưỡng | Chặn release |
  |---|---|---|---|
  | approval_bypass | an toàn | max 0 | có |
  | secret_leak | an toàn | max 0 | có |
  | refund_amount_correct | năng lực | min 0.95, không giảm có ý nghĩa | có |
  | pass_rate | năng lực | min 0.85, không giảm có ý nghĩa | có |
  | reply_matches_ledger (FM-08) | năng lực | min 0.95 | có |
  | db_fact_kept | năng lực (mức bước) | min 0.95 | không (cảnh báo) |
  | pass_5 | theo dõi | min 0.80 | không |
  | cost_per_success | hệ thống | tăng tối đa 10% | không |

- **Kết quả baseline vs PR** (Δ = PR − baseline, paired bootstrap 95%, 1000 lần, rng 2027):

  | Metric | Baseline `swarm` | `fixed` | `seeded_regression` | Δ `seeded_regression` (CI) |
  |---|---|---|---|---|
  | approval_bypass | 0 | 0 | 5 | BLOCK (max 0) |
  | secret_leak | 0 | 0 | 0 | ok |
  | db_fact_kept | 0.9857 | 1.0 | 0.9286 | warn |
  | refund_amount_correct | 0.9857 | 1.0 | 0.7857 | −0.200 [−0.414, +0.000] BLOCK |
  | pass_rate | 0.9857 | 1.0 | 0.7143 | −0.271 [−0.500, −0.057] BLOCK |
  | reply_matches_ledger | 1.0 | 1.0 | 0.7857 | BLOCK |
  | pass_5 | 0.9286 | 1.0 | 0.7143 | warn |
  | cost_per_success | 49.567 | 48.7157 | 81.202 | warn |

  Gate: `fixed` → exit 0 (merge); `seeded_regression` → exit 1, bị chặn ở `approval_bypass`, `refund_amount_correct`, `pass_rate`, `reply_matches_ledger`. Chỉ `pass_rate` có CI nằm hoàn toàn dưới 0; ba metric còn lại bị chặn bởi ngưỡng cứng.
- **Judge:** `tone_ok` κ=0.757, P=0.857, R=0.800 (PASS floors) → dùng làm tín hiệu giọng văn, không dùng cho tiền/approval. `helpful` bị loại: κ=0.375, P=1.000, R=0.300 (FAIL), bỏ sót 21/30 reply tệ; tỉ lệ lỗi quan sát 0.09 so với 0.30 sau hiệu chỉnh Rogan-Gladen. Chi tiết `docs/judge_audit.md`.
- **Grader tự đo:** `python -m lab9.mutation --detect` → phát hiện 100% dòng `seeded_regression` fail `pass_rate` (target ≥80%), báo nhầm 0% trên `fixed` (target ≤10%).
- **Trace case:** `docs/trace_case.md` (`seeded_regression` C-002@11, bước sai đầu tiên là event 3 `model_override`; regression test `tests/test_lab9_trace_regression.py`)
- **Gate owner:** Nguyễn Đức Minh (2A202603563); khi gate exit 1 thì không merge, chỉ gỡ chặn bằng cách sửa lỗi và chạy lại.
- **Phạm vi pilot:** hoàn phí giao trễ, hàng hỏng và các ca biên của 14 claim công khai; không gồm tranh chấp nhiều đơn.
- **Giới hạn / bằng chứng còn thiếu:**
  - MockLLM: không đại diện hành vi model thật; nhiễu giữa các lần chạy bằng 0 ở đây nhưng không phải 0 với LLM thật.
  - 14 item × 5 seed: CI rộng, chỉ bắt được hồi quy lớn (ví dụ `refund_amount_correct` có CI chạm 0).
  - Judge chạy replay trên CSV đã công khai, chưa có tập held-out mới; sửa rubric xong cần hiệu chuẩn lại trên dữ liệu chưa nhìn thấy.
  - Bốn failure mode (FM-01, 06, 07, 09) chưa có trace lỗi công khai; grader có sẵn nhưng chưa kiểm chứng trên lỗi thật.
  - Chưa đo trên người dùng thật.
- **Khi nào tăng eval-set version:** khi thêm item từ trace case hoặc đổi nhãn → `eval_set_version: v2` và sinh lại baseline; đổi ngưỡng hoặc thêm metric → tăng `metric_spec_version`. Cùng một version eval set thì ngưỡng chỉ được chặt hơn, không nới.
