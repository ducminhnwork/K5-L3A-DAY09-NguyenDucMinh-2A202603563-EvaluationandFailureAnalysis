# Judge audit

Hai judge replay, 100 reply mỗi judge, nhãn người làm chuẩn. FAIL là lớp dương (judge phải tìm ra reply tệ). Số liệu: `python -m lab9.judge --csv ... --audit 6`.

## Kết quả hiệu chuẩn

| Judge | n | Precision | Recall | κ | Confusion (tp/fp/fn/tn) | Tỉ lệ FAIL quan sát → hiệu chỉnh (Rogan-Gladen) | Floors (κ≥0.6, P≥0.8, R≥0.7) |
|---|---|---|---|---|---|---|---|
| tone (`judge_tone_public.csv`) | 100 | 0.857 | 0.800 | 0.757 | 24 / 4 / 6 / 66 | 0.28 → 0.30 | PASS |
| helpful (`judge_helpful_public.csv`) | 100 | 1.000 | 0.300 | 0.375 | 9 / 0 / 21 / 70 | 0.09 → 0.30 | FAIL (κ, recall) |

## Kết luận

- **Judge `tone` dùng được** làm tín hiệu chất lượng giọng văn: cả ba ngưỡng đạt, tỉ lệ lỗi hiệu chỉnh (0.30) sát tỉ lệ quan sát (0.28). Vẫn không dùng để chấm tiền hay approval (việc đó là của code).
- **Judge `helpful` không được dùng làm cổng chặn.** Recall 0.3: nó bỏ sót 21 trong 30 reply người đã chấm FAIL. Precision 1.0 không cứu được vì một cổng phải bắt được lỗi, không chỉ đúng khi nó kêu. Nếu tin judge này, ta sẽ báo tỉ lệ lỗi 9% trong khi thực tế khoảng 30%, tức là đánh giá thấp gấp ba lần, và release một agent có 1/3 reply không hữu ích.
- Các ca bỏ sót của `helpful` có chung một kiểu: reply lịch sự nhưng rỗng (xin lỗi dài không có thông tin, hoặc chỉ báo đã hoàn một số tiền). Judge thưởng cho sự lịch sự và độ dài, không kiểm tra ích lợi thực.

## Bảng audit bất đồng (judge `tone`)

| # | Item | Người | Judge | Reply | Ai đúng | Lý do | Sửa rubric |
|---|---|---|---|---|---|---|---|
| 1 | H-008 | FAIL | PASS | "Em đã hoàn tiền cho anh rồi nha, anh check giúp em." | Người | Thiếu "Dạ", dùng "nha" thân mật và ra lệnh nhẹ "anh check giúp em" với khách; không đúng giọng chăm sóc khách hàng. | Liệt kê trợ từ cuối câu thân mật ("nha", "nhé", "á") là lỗi khi trả lời khách; yêu cầu mở đầu bằng "Dạ". |
| 2 | H-017 | FAIL | PASS | "Dạ, bạn ơi LogiX đã hoàn 25.000đ cho đơn O-606 rồi nha." | Người | Gọi khách là "bạn ơi" và dùng "rồi nha": xưng hô ngang hàng, thân mật quá mức. | Quy định xưng hô bắt buộc "anh/chị"; "bạn" kèm trợ từ thân mật là FAIL. |
| 3 | H-029 | FAIL | PASS | "Dạ, vui lòng chờ. Hệ thống đang xử lý, không cần nhắn thêm." | Người | Lịch sự bề mặt ("Dạ", "vui lòng") nhưng câu cuối cụt và gạt khách ("không cần nhắn thêm"), không xin lỗi hay nêu thời gian. | Thêm tiêu chí: không câu mệnh lệnh cụt hoặc từ chối nhận phản hồi; phải có lời xin lỗi hoặc mốc thời gian khi bắt khách chờ. |
| 4 | H-042 | PASS | FAIL | "Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ." | Người | Giọng văn lịch sự, rõ ràng, có thời gian cụ thể. Judge có vẻ trừ điểm vì ngắn hoặc vì số tiền, nhưng số tiền thuộc về code (`ReplyMatchesLedger`), không thuộc judge giọng văn. | Ghi rõ trong rubric: judge này chỉ chấm giọng văn, không chấm số liệu; ngắn gọn mà đủ lễ phép thì PASS. |
| 5 | H-051 | PASS | FAIL | "Dạ, LogiX đã refund 90.000đ cho đơn O-202 ạ." | Người (có tranh luận) | "refund" là từ mượn phổ biến trong chăm sóc khách hàng, câu vẫn có "Dạ" và "ạ". Judge quá cứng với từ mượn. Ghi chú: đây là ca biên; một số đội ngũ sẽ muốn tiếng Việt thuần. | Cho phép từ mượn quen thuộc ("refund", "ok"); chỉ FAIL khi cả câu trộn ngôn ngữ làm khó hiểu. |
| 6 | H-063 | FAIL | PASS | "Dạ, LogiX đã hoàn 20.000đ và sẽ hoàn thêm cho anh/chị ạ." | Người | Giọng văn ổn, nhưng người chấm FAIL vì hứa "sẽ hoàn thêm" khi chưa có căn cứ. Đó là lỗi cam kết (cùng họ với FM-08), không phải giọng văn, nên judge giọng văn bỏ sót là hợp lý. | Không sửa judge `tone`. Thêm kiểm tra riêng cho cam kết ngoài phạm vi (code hoặc judge khác đã hiệu chuẩn) và ghi vào taxonomy nếu xuất hiện trên trace thật. |

Kết quả audit: 5/6 ca người đúng rõ ràng; ca 5 có tranh luận; ca 6 là bất đồng về tiêu chí chứ không phải judge sai về giọng văn. Sửa rubric theo cột cuối rồi hiệu chuẩn lại trên một tập held-out mới trước khi tin con số mới (CSV công khai này đã bị nhìn thấy khi sửa rubric, nên κ sau sửa sẽ bị lạc quan).

## Bất đồng tiêu biểu (judge `helpful`, lý do không dùng làm cổng)

| Item | Người | Judge | Reply (rút gọn) | Nhận xét |
|---|---|---|---|---|
| HL-015 | FAIL | PASS | "Dạ, LogiX đã hoàn 55.000đ cho đơn O-112 ạ." | Lịch sự, nhưng không nói khi nào tiền về hay bước tiếp theo; judge coi là đủ. |
| HL-016, HL-028 | FAIL | PASS | "Dạ, LogiX thành thật xin lỗi anh/chị vì sự bất tiện này và rất trân trọng sự kiên nhẫn của…" | Xin lỗi dài, không có thông tin hay hành động; judge thưởng cho độ lịch sự và độ dài. |
| HL-035, HL-041 | FAIL | PASS | "Dạ, Một lần nữa LogiX xin lỗi vì trải nghiệm chưa tốt, mong anh/chị thông cảm và tiếp tục…" | Lặp lại lời xin lỗi, vẫn không giải quyết gì. |
