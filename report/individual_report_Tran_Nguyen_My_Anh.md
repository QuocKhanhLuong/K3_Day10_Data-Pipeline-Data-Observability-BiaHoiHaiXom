# Báo cáo cá nhân — Trần Nguyễn Mỹ Anh

## 1. Thông tin cá nhân

| Trường | Nội dung |
|---|---|
| Họ và tên | Trần Nguyễn Mỹ Anh |
| MSSV | 2A202601019 |
| Nhóm | BiaHoiHaiXom |
| Vai trò | Role 4 — Corruption & Integration Owner |
| Ngày báo cáo | 2026-08-06 |

## 2. Phạm vi phụ trách

| Module | Trách nhiệm | Trạng thái |
|---|---|---|
| `src/ingestion/corruption.py` | Tạo các biến thể dữ liệu lỗi có seed và corruption log | Hoàn thành |
| `src/pipelines/phase1.py` | Điều phối ingestion, cleaning, embedding, retrieval và evaluation baseline | Hoàn thành |
| `src/pipelines/corruption_flow.py` | Chạy chuỗi baseline → corrupted → repaired và so sánh kết quả | Hoàn thành |
| `script/run_phase1.py`, `script/run_corruption_flow.py` | Chạy và kiểm tra pipeline ở mức end-to-end | Hoàn thành |

Role 4 nhận clean dataset và frozen evaluation set từ Role 2, dùng contract observability của Role 3, đồng thời sử dụng raw snapshot của Role 1 để repair mà không cần gọi Crossref lại.

## 3. Công việc và artifact đã bàn giao

- Tạo corrupted dataset từ `data/clean/papers_clean.json` với `seed=42`, corruption ratio `0.2`, đầu vào 239 rows và đầu ra 287 rows.
- Lưu log tái lập tại `data/results/corruption_log.json`; log ghi seed, reference date, các question ID frozen và các thao tác corruption.
- Đảm bảo toàn bộ `q1`–`q20` trong `data/eval/test_set.json` vẫn được kiểm tra ở các trạng thái baseline, corrupted và repaired.
- Re-index và chạy evaluation cho corrupted data, sau đó repair từ `data/raw/crossref_records.json`.
- Tạo các artifact repaired: `data/clean/papers_clean_repaired.csv/json`, `data/quality/repaired_quality.json`, `data/results/repaired_metrics.json` và freshness report tương ứng.
- Tạo báo cáo so sánh tại `data/reports/corruption_report.md`.

## 4. Kết quả kiểm chứng

### Observability

| Trạng thái | Rows | Quality | Freshness | Phát hiện chính |
|---|---:|---|---|---|
| Baseline | 239 | PASS | FRESH | Không có lỗi quality, stale ratio 0 |
| Corrupted | 287 | FAIL | FRESH theo ngưỡng report | 48 duplicate `paper_id`, 48 summary rỗng/ngắn, 97 embedding text sai format; stale rows 48 |
| Repaired | 239 | PASS | FRESH | Các quality checks trở lại PASS, stale ratio 0 |

Corruption đã tạo ra lỗi observable thay vì chỉ làm thay đổi dữ liệu âm thầm. Repair được xác nhận bằng việc số dòng trở lại 239 và toàn bộ quality checks của repaired artifact đều PASS.

### Metrics evaluation hiện tại

| Metric | Baseline | Corrupted | Repaired |
|---|---:|---:|---:|
| `retrieval_hit_rate` | 0.6000 | 0.4500 | 0.6000 |
| `mean_token_f1` | 0.5642 | 0.2622 | 0.5642 |
| `judge_accuracy` | 0.5000 | 0.2500 | 0.5000 |
| `mean_judge_score` | 3.10 | 2.05 | 3.10 |

So với baseline, corrupted data làm retrieval hit rate giảm 0.15 và token F1 giảm khoảng 0.3020. Repaired data khôi phục về đúng các giá trị baseline trong các file metrics hiện tại. Ragas được skip vì cấu hình chạy chưa bật `RUN_RAGAS=1`.

## 5. Cách tích hợp end-to-end

```text
clean baseline
    -> inject corruption + corruption_log
    -> build embeddings/ChromaDB + evaluate
    -> quality/freshness checks
    -> repair from raw snapshot
    -> rebuild index + evaluate
    -> compare baseline/corrupted/repaired
```

Các trạng thái dùng chung `data/eval/test_set.json`, vì vậy thay đổi metrics được quy về thay đổi dữ liệu/index thay vì thay đổi bộ câu hỏi. Embedding dùng model local `sentence-transformers/all-MiniLM-L6-v2`; ChromaDB và metadata `paper_id` được tạo lại cho từng trạng thái.

## 6. Vấn đề tích hợp và bài học

`data/results/baseline_metrics.json`, `corrupted_metrics.json` và `repaired_metrics.json` là nguồn số liệu hiện tại cho bảng trên. `data/reports/corruption_report.md` đã được đồng bộ lại với các metrics JSON và frozen test set hash hiện tại.

Bài học chính là corruption flow phải có seed, log và frozen test set cố định. Repair từ raw snapshot giúp kiểm chứng pipeline có thể phục hồi mà không phụ thuộc network/API tại thời điểm đánh giá.

## 7. Cam kết

- [x] Corruption flow đã chạy đủ baseline, corrupted và repaired.
- [x] Có log corruption và các artifact quality/metrics/freshness.
- [x] Dùng chung frozen evaluation set cho ba trạng thái.
- [x] Không ghi API key hoặc nội dung `.env` vào báo cáo.
- [x] Đồng bộ report Markdown với metrics JSON hiện tại.

**Người thực hiện:** Trần Nguyễn Mỹ Anh  
**Ngày:** 2026-08-06
