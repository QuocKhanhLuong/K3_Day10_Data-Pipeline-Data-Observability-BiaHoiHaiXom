# Group Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin bài nộp

| Thông tin | Nội dung |
|---|---|
| Khóa/Lớp | K3 |
| Tên nhóm | BiaHoiHaiXom |
| Repository | `K3_Day10_Data-Pipeline-Data-Observability` |
| Ngày báo cáo | 2026-08-06 |
| Tiến độ | Đã hoàn thành Baseline Phase 1; chưa chạy Corruption/Repair |

### Thành viên và phân công

| STT | Họ và tên | Mã sinh viên | Vai trò | Module/deliverable sở hữu | Artifact đầu vào | Người nhận đầu ra |
|---:|---|---|---|---|---|---|
| 1 | Lương Quốc Khánh | 2A202601713 | Role 3 — Data Observability Owner | `src/observability/quality.py`, `src/observability/reporting.py`; quality/freshness reports | Clean dataset và evaluation/metrics artifacts | Thành viên 3 — Role 4 |
| 2 | Hoàng Đức Anh | 2A202601223 | Role 2 — Data Model & Eval Set Owner | `src/ingestion/cleaning.py`, `src/evaluation/testset.py`; clean dataset và frozen test set | Raw Crossref records từ Role 1 | Role 3 và Role 4 |
| 3 | Trần Nguyễn Mỹ Anh | 2A202601019 | Role 4 — Corruption & Integration Owner | `src/ingestion/corruption.py`, `src/pipelines/phase1.py`, `src/pipelines/corruption_flow.py` | Clean dataset, frozen test set và observability contract | Cả nhóm |
| 4 | Nguyễn Thu Huyền | 2A202601027 | Role 1 — Source Ingestion Owner | `src/ingestion/crossref.py`; raw response và parsed raw records | `Settings`, query/filter và Crossref API | Role 2 |

### Contract bàn giao

- Role 1 tạo `data/raw/crossref_response.json` và `data/raw/crossref_records.json`.
- Role 2 đọc raw records, tạo `data/clean/papers_clean.csv`, `data/clean/papers_clean.json` và `data/eval/test_set.json`.
- Role 3 dùng clean schema và metrics JSON để chạy quality/freshness checks, sinh report cho baseline và chuẩn bị contract dùng chung cho corrupted/repaired.
- Role 4 nhận các module/artifact trên để tích hợp pipeline và thực hiện corruption/repair. Phần này chưa chạy trong phiên bản báo cáo hiện tại.

## 2. Tóm tắt kết quả

Nhóm BiaHoiHaiXom đã hoàn thành luồng Baseline Phase 1 từ raw snapshot của Crossref đến cleaned dataset, frozen evaluation set, embedding manifest, ChromaDB index, evaluation metrics và quality/freshness reports. Snapshot đầu vào có 240 raw records; sau cleaning còn 239 records hợp lệ. Clean schema đã chuẩn hóa title, summary, authors, categories, ngày publication, `age_days` và `text_for_embedding`. Bộ evaluation hiện có 20 câu factual, trong đó các câu hỏi được đối chiếu với `ground_truth_doc_ids` trong clean dataset.

Baseline ghi nhận `retrieval_hit_rate = 0.6000`, `mean_token_f1 = 0.5642`, `judge_accuracy = 0.5000` và `mean_judge_score = 3.1000`. Data quality đạt PASS với toàn bộ checks thành công; freshness đạt FRESH, không có stale record và tỷ lệ stale là 0.0. Ragas chưa chạy vì đang được cấu hình skip mặc định. Nhóm chưa thực hiện corruption flow, repair từ raw snapshot hoặc comparison report, nên chưa có kết luận nhân quả về tác động của dữ liệu lỗi và mức phục hồi của agent. Giới hạn chính hiện tại là phần LLM phụ thuộc network/provider, còn kết quả corruption và repaired vẫn là công việc tiếp theo.

## 3. Kiến trúc và luồng dữ liệu

### Luồng đã hoàn thành

```text
Crossref raw snapshot
    -> cleaning và data modeling
    -> papers_clean.csv/json
    -> SentenceTransformer embeddings
    -> ChromaDB baseline collection
    -> frozen evaluation set
    -> baseline answers/metrics
    -> data quality và freshness reports
```

### Luồng chưa thực hiện

```text
clean baseline
    -> corruption
    -> corrupted re-index/evaluation
    -> repair từ data/raw/crossref_records.json
    -> repaired re-index/evaluation
    -> comparison report
```

| Khối | Input | Xử lý chính | Output/artifact | Owner |
|---|---|---|---|---|
| Ingestion | Crossref API hoặc raw snapshot | Fetch, retry, parse record schema | `data/raw/crossref_response.json`, `data/raw/crossref_records.json` | Nguyễn Thu Huyền |
| Cleaning | Raw records | Loại record lỗi, chuẩn hóa text/list/date | `data/clean/papers_clean.csv/json` | Hoàng Đức Anh |
| Embedding/index | Clean dataframe | `all-MiniLM-L6-v2`, vector 384 chiều, ChromaDB | `data/embeddings/papers_embeddings.json`, `data/chroma/` | Trần Nguyễn Mỹ Anh |
| Evaluation | Clean corpus và frozen set | Retrieval, QA, token F1, judge | `data/results/baseline_answers.json`, `baseline_metrics.json` | Hoàng Đức Anh / Trần Nguyễn Mỹ Anh |
| Observability | Clean data và metrics | Quality checks, freshness, Markdown reports | `data/quality/`, `data/reports/phase1_report.md` | Lương Quốc Khánh |
| Corruption/repair | Clean baseline và raw snapshot | Chưa chạy | Chưa có corrupted/repaired artifacts | Trần Nguyễn Mỹ Anh |

## 4. Cách tái hiện kết quả

### Cấu hình không chứa secret

| Biến/cấu hình | Giá trị sử dụng |
|---|---|
| `LLM_PROVIDER` | `gemini` |
| `LLM_MODEL` | `gemini-2.5-flash` |
| Embedding model | `sentence-transformers/all-MiniLM-L6-v2` |
| Raw records | 240 |
| Clean records | 239 |
| Retrieval `top_k` | 4 |
| Freshness threshold | 180 ngày |
| Frozen evaluation samples | 20 |
| Random seed | Chưa áp dụng cho baseline |

Không ghi API key hoặc nội dung `.env` vào báo cáo.

### Lệnh cài đặt

```bash
uv sync
```

### Lệnh chạy baseline

```bash
uv run python script/run_phase1.py
```

Nếu model embedding đã có cache local nhưng môi trường không cho phép gọi Hugging Face:

```powershell
$env:HF_HUB_OFFLINE="1"
$env:TRANSFORMERS_OFFLINE="1"
uv run python script/run_phase1.py
```

### Kết quả tái hiện

| Lệnh | Trạng thái | Bằng chứng |
|---|---|---|
| Baseline pipeline | Thành công | `data/results/baseline_metrics.json`, `data/quality/baseline_quality.json`, `data/reports/phase1_report.md` |
| Corruption flow | Chưa thực hiện | Chưa có `data/results/corruption_log.json` |

## 5. Ingestion, cleaning và data contract

### Nguồn dữ liệu

| Thuộc tính | Giá trị |
|---|---|
| Source | Crossref REST API — `https://api.crossref.org/works` |
| Query | `agentic retrieval augmented generation large language model` |
| Filter | `from-pub-date:2026-02-07,has-abstract:true` |
| Source mode của baseline | Cached raw snapshot |
| Số record nhận được | 240 |
| Cơ chế retry/backoff | Retry tối đa 5 lần cho request retryable; exponential backoff |

### Clean schema chính

| Trường | Kiểu | Bắt buộc | Ý nghĩa | Xử lý khi thiếu/sai |
|---|---|---:|---|---|
| `paper_id` | string | Có | DOI/ID tài liệu | Loại record nếu rỗng; loại duplicate |
| `title` | string | Có | Tiêu đề paper | Strip markup/whitespace; loại nếu rỗng |
| `summary` | string | Có | Abstract/summary | Strip markup; loại nếu dưới 100 ký tự |
| `authors` | list | Không | Danh sách tác giả | Flatten dict nested và chuẩn hóa |
| `authors_joined` | string | Có | Tác giả nối bằng `, ` | Tạo từ `authors` |
| `categories` | list | Không | Category/type | Flatten và de-duplicate |
| `categories_joined` | string | Có | Category nối bằng `, ` | Tạo từ `categories` |
| `published` | `YYYY-MM-DD` | Có | Ngày publication | Parse date; loại nếu không hợp lệ |
| `age_days` | integer | Có | Số ngày từ publication đến run date | Tính từ timestamp chạy pipeline |
| `text_for_embedding` | string | Có | Văn bản đưa vào embedding | `Title: ... \| Authors: ... \| Summary: ...` |

### Quy tắc cleaning

| Quy tắc | Dimension | Kết quả baseline | Bằng chứng |
|---|---|---:|---|
| Loại record thiếu title/summary không hợp lệ | Completeness/Validity | 1 record bị loại, còn 239 | `data/clean/papers_clean.json` |
| Summary tối thiểu 100 ký tự | Completeness | 0 record vi phạm | `baseline_quality.json` |
| Loại XML/HTML và chuẩn hóa whitespace | Validity | Không còn markup trong clean text | `cleaning.py` và clean artifacts |
| Flatten authors/categories nested dict | Schema consistency | 239 record có joined fields | `baseline_quality.json` |
| Chuẩn hóa ngày và tính `age_days` | Freshness | 239 record hợp lệ | `freshness_report.json` |

`text_for_embedding` được tạo theo format canonical:

```text
Title: {title} | Authors: {authors_joined} | Summary: {summary}
```

Document ID của ChromaDB có dạng `{paper_id}::{row_index}`; metadata giữ lại `paper_id`, title, publication date, authors, categories và summary.

## 6. Evaluation setup

| Thành phần | Cấu hình thực tế |
|---|---|
| Số câu hỏi | 20 (`q1`–`q20`) |
| `question_type` | `factual` |
| Ground truth document ID | Lấy từ clean record, lưu trong `ground_truth_doc_ids` |
| Embedding model | `sentence-transformers/all-MiniLM-L6-v2`, 384 chiều |
| Vector store | ChromaDB collection `papers-baseline`, lưu tại `data/chroma/` |
| Retrieval `top_k` | 4 |
| LLM provider/model | Gemini / `gemini-2.5-flash` |
| Frozen test set | `data/eval/test_set.json` |

Bộ test được đọc từ artifact JSON đã chốt và được kiểm tra rằng mọi `ground_truth_doc_ids` đều tồn tại trong clean corpus. Baseline, corrupted và repaired phải dùng cùng file này để thay đổi metrics phản ánh thay đổi dữ liệu, không phải thay đổi câu hỏi hoặc ground truth. SHA-256 hiện tại của test set là `9DAFDE0C18D2411A6986207E3D79572DC75F414404586E7EC45E092F02354CDC`.

## 7. Kết quả baseline

### Artifact checklist

| Artifact | Đường dẫn | Trạng thái | Ghi chú |
|---|---|---|---|
| Raw response/records | `data/raw/crossref_response.json`, `crossref_records.json` | Có | 240 raw records |
| Cleaned dataset | `data/clean/papers_clean.csv/json` | Có | 239 clean records |
| Embedding manifest/index | `data/embeddings/`, `data/chroma/` | Có | 239 documents, collection baseline |
| Evaluation set | `data/eval/test_set.json` | Có | 20 frozen factual questions |
| Baseline metrics | `data/results/baseline_metrics.json` | Có | Metrics đã ghi thực tế |
| Quality/freshness | `data/quality/` | Có | Quality PASS, freshness FRESH |
| Baseline report | `data/reports/phase1_report.md` | Có | Report baseline |

### Baseline metrics

| Metric | Giá trị | Diễn giải |
|---|---:|---|
| `retrieval_hit_rate` | 0.6000 | 12/20 sample có ground-truth document trong kết quả retrieval |
| `mean_token_f1` | 0.5642 | Mức trùng token trung bình giữa answer và ground truth |
| `judge_accuracy` | 0.5000 | 50% sample được judge đánh dấu đúng |
| `mean_judge_score` | 3.1000 | Điểm judge trung bình trên thang 1–5 |
| Ragas | Skipped | Chưa bật `RUN_RAGAS=1` |

## 8. Data quality và freshness

### Quality checks

Artifact `data/quality/baseline_quality.json` có status `pass`, failed checks rỗng và tổng cộng 239 rows.

| Check tiêu biểu | Ngưỡng/kỳ vọng | Kết quả baseline |
|---|---|---|
| Required columns | Đủ clean schema | PASS |
| `paper_id` completeness/uniqueness | Không rỗng, không duplicate | PASS; observed 0 |
| Title/summary completeness | Không rỗng | PASS; observed 0 |
| Summary minimum length | ≥100 ký tự | PASS; observed 0 vi phạm |
| Published date parseable | Tất cả parse được | PASS; observed 0 lỗi |
| Age numeric/non-negative | Số nguyên, ≥0 | PASS; observed 0 lỗi |
| Authors/categories joined | Không rỗng | PASS; observed 0 lỗi |
| Canonical embedding text | Đúng format Title/Authors/Summary | PASS; observed 0 lỗi |
| Freshness ratio | ≤20% stale/invalid | PASS; ratio 0.0 |

### Freshness

| Thuộc tính | Giá trị |
|---|---|
| Đo trên | Clean dataset baseline |
| Publication mới nhất | 2026-08-05 |
| Publication cũ nhất | 2026-02-11 |
| Freshness threshold | 180 ngày |
| Latest age | 1 ngày |
| Future/invalid rows | 0 / 0 |
| Stale rows/ratio | 0 / 0.0 |
| Trạng thái baseline | FRESH |

## 9. Corruption scenarios và repair

Chưa thực hiện trong tiến độ hiện tại.

| Hạng mục | Trạng thái | Bằng chứng |
|---|---|---|
| Tạo corrupted dataset | Chưa thực hiện | Chưa có `data/clean/papers_clean_corrupted.*` |
| Re-index/re-evaluate corrupted | Chưa thực hiện | Chưa có `corrupted_metrics.json` |
| Repair từ raw snapshot | Chưa thực hiện | Chưa có repaired artifacts |
| Corruption log | Chưa thực hiện | Chưa có `data/results/corruption_log.json` |

Do chưa chạy Phase 2, nhóm chưa kết luận corruption nào ảnh hưởng mạnh nhất hoặc repair đã phục hồi metric nào.

## 10. So sánh baseline, corrupted và repaired

Chưa có comparison report. Bảng dưới đây để dành cho lần chạy Phase 2 và không điền số liệu suy diễn.

| Metric/signal | Baseline | Corrupted | Repaired | Nhận xét hiện tại |
|---|---:|---:|---:|---|
| `retrieval_hit_rate` | 0.6000 | Chưa chạy | Chưa chạy | Chưa thể kết luận tác động |
| `mean_token_f1` | 0.5642 | Chưa chạy | Chưa chạy | Chưa thể kết luận phục hồi |
| `judge_accuracy` | 0.5000 | Chưa chạy | Chưa chạy | Chưa thể kết luận phục hồi |
| `mean_judge_score` | 3.1000 | Chưa chạy | Chưa chạy | Chưa thể kết luận phục hồi |
| Quality checks | PASS | Chưa chạy | Chưa chạy | Baseline đạt |
| Freshness | FRESH | Chưa chạy | Chưa chạy | Baseline đạt |

## 11. Vấn đề tích hợp quan trọng

- **Triệu chứng:** Model embedding có thể cố kiểm tra Hugging Face qua network dù model đã được cache local; Gemini cũng phụ thuộc kết nối API.
- **Nguyên nhân:** Môi trường chạy giới hạn outbound socket/network.
- **Cách xử lý:** Dùng model embedding cache local với `HF_HUB_OFFLINE=1` và `TRANSFORMERS_OFFLINE=1`; không ghi credential vào report. LLM judge có fallback khi provider không khả dụng; Ragas được skip mặc định.
- **Cách xác minh:** Baseline vẫn tạo được ChromaDB/manifest, 239 documents được index và các artifact Phase 1 được ghi đầy đủ.

## 12. Giới hạn và hướng cải thiện

| Giới hạn hiện tại | Ảnh hưởng | Hướng cải thiện có thể kiểm chứng |
|---|---|---|
| Chưa chạy corruption/repair | Chưa chứng minh được quan hệ data corruption → quality → RAG metrics | Chạy `script/run_corruption_flow.py`, kiểm tra log và comparison report |
| Ragas đang skip | Thiếu nhóm chỉ số context/faithfulness bổ sung | Chạy lại với `RUN_RAGAS=1` khi LLM provider hoạt động |
| Một phần test set có câu hỏi dùng full title để kiểm tra exact lookup | Retrieval hit rate có thể được hỗ trợ bởi exact-title lookup, không hoàn toàn phản ánh semantic search | Tách báo cáo semantic-only và exact-lookup benchmark |
| Judge phụ thuộc provider/network | `judge_accuracy` có thể dùng fallback heuristic khi API lỗi | Chạy lại với provider ổn định và lưu rõ judge mode |

## 13. Checklist trước khi nộp

- [x] Thông tin nhóm và phân công đã điền.
- [x] Raw response/records đã tồn tại.
- [x] Cleaned CSV/JSON đã tồn tại.
- [x] Frozen evaluation set đã tồn tại và khớp clean document IDs.
- [x] Embedding manifest và ChromaDB baseline đã tạo.
- [x] Baseline metrics, quality và freshness reports đã tạo.
- [x] Lệnh baseline đã chạy thành công.
- [ ] Corrupted và repaired dùng chung evaluation set — Chưa thực hiện Phase 2.
- [ ] Comparison report — Chưa thực hiện Phase 2.
- [x] Không đưa API key, token hoặc secret vào báo cáo.
