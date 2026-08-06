# Báo cáo nhóm — Day 10: Data Pipeline & Data Observability

## 1. Thông tin nhóm

| Trường | Nội dung |
|---|---|
| Team | BiaHoiHaiXom |
| Số thành viên | 4 |
| Repository | `K3_Day10_Data-Pipeline-Data-Observability` |
| Ngày cập nhật | 2026-08-06 |
| Tiến độ | Baseline Phase 1 và corruption/repaired flow đã hoàn thành |

### Thành viên và phân công

| STT | Họ và tên | MSSV | Vai trò | Module chính | Đầu vào | Đầu ra/người nhận |
|---:|---|---|---|---|---|---|
| 1 | Lương Quốc Khánh | 2A202601713 | Role 3 — Data Observability Owner | `quality.py`, `reporting.py` | Clean data, metrics | Quality/freshness reports cho Role 4 và cả nhóm |
| 2 | Hoàng Đức Anh | 2A202601223 | Role 2 — Data Model & Eval Set Owner | `cleaning.py`, `testset.py` | Raw Crossref records | Clean dataset và frozen test set cho Role 3/4 |
| 3 | Trần Nguyễn Mỹ Anh | 2A202601019 | Role 4 — Corruption & Integration Owner | `corruption.py`, `phase1.py`, `corruption_flow.py` | Clean data, raw snapshot, frozen set | Corrupted/repaired artifacts và metrics |
| 4 | Nguyễn Thu Huyền | 2A202601027 | Role 1 — Source Ingestion Owner | `crossref.py` | Crossref API/settings | Raw response và parsed records cho Role 2 |

## 2. Tóm tắt tiến độ hiện tại

Nhóm đã hoàn thành chuỗi xử lý từ raw Crossref snapshot đến clean dataset, frozen evaluation set, local embedding, ChromaDB, retrieval/QA, observability và corruption/repaired flow. Baseline có 240 raw records và 239 clean records. Bộ đánh giá cố định có 20 câu factual, dùng chung cho baseline, corrupted và repaired.

Corruption flow đã chạy thành công với seed 42 và corruption ratio 0.2. Corrupted data bị quality FAIL và metrics RAG giảm; repaired data được dựng lại từ raw snapshot, quality trở lại PASS và metrics hiện tại khôi phục về baseline. Ragas chưa chạy vì `RUN_RAGAS=1` chưa được bật; Gemini judge vẫn phụ thuộc provider/network.

## 3. Luồng dữ liệu đã hoàn thành

```text
Crossref API/raw snapshot
    -> parsed raw records
    -> cleaning và data contract
    -> papers_clean.csv/json
    -> frozen evaluation set
    -> SentenceTransformer embeddings 384 chiều
    -> ChromaDB + metadata paper_id
    -> baseline retrieval/QA metrics
    -> quality/freshness baseline
    -> corruption + log
    -> corrupted index/evaluation/observability
    -> repair từ raw snapshot
    -> repaired index/evaluation/observability
    -> comparison report
```

### Contract bàn giao

- Role 1 bàn giao `data/raw/crossref_response.json` và `data/raw/crossref_records.json`.
- Role 2 bàn giao `data/clean/papers_clean.csv`, `data/clean/papers_clean.json` và `data/eval/test_set.json`.
- Role 3 áp dụng cùng quality/freshness checks cho ba trạng thái.
- Role 4 tạo corruption, re-index, repair và tổng hợp kết quả.

## 4. Artifact đã có

| Nhóm artifact | Đường dẫn | Trạng thái |
|---|---|---|
| Raw source | `data/raw/crossref_response.json`, `data/raw/crossref_records.json` | Có; 240 records |
| Clean data | `data/clean/papers_clean.csv`, `data/clean/papers_clean.json` | Có; 239 records |
| Frozen evaluation | `data/eval/test_set.json` | Có; 20 câu, `q1`–`q20` |
| Embedding/index | `data/embeddings/papers_embeddings.json`, `data/chroma/` | Có; vector 384 chiều, metadata có `paper_id` |
| Baseline | `data/results/baseline_metrics.json`, `data/quality/baseline_quality.json` | Có |
| Corruption | `data/results/corruption_log.json`, corrupted clean/index/results | Có |
| Repaired | `data/results/repaired_metrics.json`, repaired quality/freshness/results | Có |
| Reports | `data/reports/phase1_report.md`, `data/reports/corruption_report.md` | Có |

## 5. Kết quả baseline

| Metric | Giá trị |
|---|---:|
| `retrieval_hit_rate` | 0.6000 |
| `mean_token_f1` | 0.5642 |
| `judge_accuracy` | 0.5000 |
| `mean_judge_score` | 3.10 |
| Quality | PASS |
| Freshness | FRESH |
| Ragas | Skipped |

Baseline quality có 239 rows và không có lỗi required columns, completeness, uniqueness, summary length, date, age, joined fields hoặc canonical embedding text. Freshness có publication mới nhất `2026-08-05`, cũ nhất `2026-02-11`, latest age 1 ngày và stale ratio 0.

## 6. Corruption và repair

### Corruption log

`data/results/corruption_log.json` ghi `input_rows=239`, `output_rows=287`, `seed=42`, `corruption_ratio=0.2`, reference date `2026-08-06`; toàn bộ frozen question IDs được bao phủ và yêu cầu overlap ground-truth được kiểm tra.

### Observability kết quả

| Trạng thái | Rows | Quality | Freshness | Tín hiệu chính |
|---|---:|---|---|---|
| Baseline | 239 | PASS | FRESH | Không lỗi quality, stale ratio 0 |
| Corrupted | 287 | FAIL | FRESH theo threshold hiện tại | 48 duplicate IDs, 48 summary rỗng/ngắn, 97 embedding text sai format; 48 stale rows |
| Repaired | 239 | PASS | FRESH | Các quality checks và stale ratio trở lại bình thường |

Corrupted data làm observability phát hiện lỗi cụ thể thay vì chỉ ghi nhận metric RAG giảm. Freshness corrupted vẫn có status FRESH vì stale ratio 48/287 khoảng 16.7%, thấp hơn ngưỡng 20%; tuy nhiên stale rows vẫn được ghi trong artifact để theo dõi.

### So sánh metrics hiện tại

| Metric | Baseline | Corrupted | Repaired | Thay đổi corrupted so với baseline |
|---|---:|---:|---:|---:|
| `retrieval_hit_rate` | 0.6000 | 0.4500 | 0.6000 | -0.1500 |
| `mean_token_f1` | 0.5642 | 0.2622 | 0.5642 | -0.3020 |
| `judge_accuracy` | 0.5000 | 0.2500 | 0.5000 | -0.2500 |
| `mean_judge_score` | 3.10 | 2.05 | 3.10 | -1.05 |

Kết luận: corruption tác động rõ ràng đến cả retrieval và answer quality; repair khôi phục các metrics hiện tại về baseline. Việc so sánh dùng cùng `data/eval/test_set.json`, nên không bị nhiễu bởi thay đổi câu hỏi hoặc ground truth.

## 7. Embedding, ChromaDB và retrieval

Embedding dùng local model `sentence-transformers/all-MiniLM-L6-v2`, vector 384 chiều; không cần API key cho bước chunking/embedding khi model đã được cache. ChromaDB được tạo trong `data/chroma/`, manifest nằm tại `data/embeddings/papers_embeddings.json`, và metadata mỗi document giữ `paper_id` để tính retrieval hit rate.

LLM wrapper đọc provider/model từ `.env`, nhưng gọi Gemini có thể bị chặn bởi network (`WinError 10013`). Vì vậy local embedding, ChromaDB, retrieval và các metric fallback vẫn có thể chạy; Ragas được skip khi provider không sẵn sàng.

## 8. Đồng bộ artifact

`data/reports/corruption_report.md` đã được cập nhật theo ba file metrics JSON hiện tại và frozen test set hash hiện tại. Các bảng trong báo cáo nhóm dùng cùng một bộ số liệu: baseline hit rate `0.6`, corrupted `0.45`, repaired `0.6`.

## 9. Cách tái hiện

```bash
uv run python script/run_phase1.py
uv run python script/run_corruption_flow.py
```

Khi embedding model đã có cache local và môi trường chặn Hugging Face, có thể chạy offline:

```powershell
$env:HF_HUB_OFFLINE="1"
$env:TRANSFORMERS_OFFLINE="1"
uv run python script/run_phase1.py
```

Không ghi API key, token hoặc nội dung `.env` vào báo cáo.

## 10. Checklist bàn giao

- [x] Đã điền bảng thành viên và phân công để tránh xung đột interface.
- [x] Raw response/records tồn tại.
- [x] Cleaned CSV/JSON tồn tại.
- [x] Frozen evaluation set tồn tại và document IDs hợp lệ.
- [x] Embedding manifest và ChromaDB tồn tại.
- [x] Baseline metrics, quality và freshness đã có.
- [x] Corruption log và corrupted artifacts đã có.
- [x] Repaired artifacts, quality và metrics đã có.
- [x] So sánh baseline/corrupted/repaired đã được tổng hợp.
- [x] Đồng bộ `data/reports/corruption_report.md` với metrics JSON và frozen test set hiện tại.
- [x] Không đưa secret vào báo cáo.
