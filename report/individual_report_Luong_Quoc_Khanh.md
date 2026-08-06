# Báo cáo cá nhân — Lương Quốc Khánh

## 1. Thông tin cá nhân

| Trường | Nội dung |
|---|---|
| Họ và tên | Lương Quốc Khánh |
| MSSV | 2A202601713 |
| Nhóm | BiaHoiHaiXom |
| Vai trò | Role 3 — Data Observability Owner |
| Ngày báo cáo | 2026-08-06 |

## 2. Phạm vi phụ trách

| Module | Trách nhiệm | Trạng thái |
|---|---|---|
| `src/observability/quality.py` | Kiểm tra schema, completeness, uniqueness, summary length, freshness fields và canonical embedding text | Hoàn thành |
| `src/observability/reporting.py` | Tổng hợp quality/freshness và sinh báo cáo Phase 1, corruption/repaired | Hoàn thành |

Role 3 nhận clean dataset và metrics từ Role 2/Role 4, sau đó trả về các tín hiệu observability để xác định dataset baseline có hợp lệ, corruption có bị phát hiện và repair có khôi phục được chất lượng hay không.

## 3. Artifact đã tạo

- `data/quality/baseline_quality.json`
- `data/quality/corrupted_quality.json`
- `data/quality/repaired_quality.json`
- `data/quality/freshness_report.json`
- `data/quality/freshness_corrupted.json`
- `data/quality/freshness_repaired.json`
- `data/reports/phase1_report.md`
- `data/reports/corruption_report.md`

Các report đọc metrics JSON và quality/freshness artifacts thay vì hard-code kết quả. Cùng một bộ check được áp dụng cho baseline, corrupted và repaired để so sánh có ý nghĩa.

## 4. Kết quả quality và freshness

| Trạng thái | Rows | Quality | Freshness | Chi tiết |
|---|---:|---|---|---|
| Baseline | 239 | PASS | FRESH | 0 lỗi completeness/uniqueness/format, stale ratio 0 |
| Corrupted | 287 | FAIL | FRESH theo threshold 20% | 48 duplicate IDs, 48 summary rỗng/ngắn, 97 canonical embedding text failures; 48 stale rows |
| Repaired | 239 | PASS | FRESH | Các check trở lại 0 lỗi, stale ratio 0 |

Freshness baseline có publication mới nhất `2026-08-05`, cũ nhất `2026-02-11`, `latest_age_days=1`, không có future row. Corrupted data có stale rows từ ngày `2000-01-01`; report vẫn ghi FRESH vì freshness threshold hiện tại cho phép stale ratio không vượt 20%. Đây là lý do quality vẫn là tín hiệu FAIL riêng biệt và không được suy ra chỉ từ freshness status.

## 5. So sánh metrics RAG

| Metric | Baseline | Corrupted | Repaired |
|---|---:|---:|---:|
| `retrieval_hit_rate` | 0.6000 | 0.4500 | 0.6000 |
| `mean_token_f1` | 0.5642 | 0.2622 | 0.5642 |
| `judge_accuracy` | 0.5000 | 0.2500 | 0.5000 |
| `mean_judge_score` | 3.10 | 2.05 | 3.10 |

Các số liệu trên được đọc từ `data/results/baseline_metrics.json`, `corrupted_metrics.json` và `repaired_metrics.json`. Kết quả cho thấy corruption làm giảm đồng thời retrieval và answer quality; khi repair đạt quality PASS, các metrics hiện tại trở về baseline. Ragas chưa chạy vì `RUN_RAGAS=1` chưa được bật.

## 6. Quyết định kỹ thuật và cách xác minh

Quality checks được tách theo các dimension: required columns, ID completeness/uniqueness, title/summary completeness, summary minimum length, date parsing, age validity, joined authors/categories, canonical `text_for_embedding` và freshness ratio. Cách tách này giúp xác định lỗi thuộc data contract hay thuộc retrieval/LLM.

Corrupted artifact chứng minh observability hoạt động: các lỗi duplicate, summary và embedding format đều xuất hiện trong `corrupted_quality.json`; repaired artifact chứng minh repair đã đưa dữ liệu về schema hợp lệ. Không dùng `max(0, age_days)` để che giấu ngày tương lai; giá trị freshness được tính từ timestamp chạy và được kiểm tra riêng.

## 7. Đồng bộ artifact

`data/reports/corruption_report.md` đã được cập nhật theo ba file metrics JSON hiện tại và frozen test set hash hiện tại, tránh tình trạng report Markdown và metrics JSON sử dụng hai bộ số liệu khác nhau.

## 8. Cam kết

- [x] Quality và freshness đã chạy cho baseline, corrupted và repaired.
- [x] Report được sinh từ artifact, không hard-code kết quả.
- [x] Corruption đã được phát hiện bằng các check cụ thể.
- [x] Repair được xác nhận bằng quality PASS và freshness FRESH.
- [x] Không ghi API key hoặc secret vào báo cáo.

**Người thực hiện:** Lương Quốc Khánh  
**Ngày:** 2026-08-06
