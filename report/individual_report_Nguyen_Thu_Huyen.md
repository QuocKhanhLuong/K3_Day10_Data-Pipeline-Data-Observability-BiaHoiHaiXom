# Member Role Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
|---|---|
| Họ và tên | Nguyễn Thu Huyền |
| MSSV | 2A202601027 |
| Khóa/Lớp | K3 |
| Tên nhóm | BiaHoiHaiXom |
| Vai trò chính | Role 1 — Source Ingestion Owner |
| Repository | `K3_Day10_Data-Pipeline-Data-Observability` |
| Ngày hoàn thành | 2026-08-06 |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
|---|---|---|---|---|
| Gọi và lưu nguồn Crossref | `src/ingestion/crossref.py`, `fetch_source_records()` | `Settings`: API URL, query, filter, số rows | `data/raw/crossref_response.json` | Hoàn thành |
| Parse raw payload thành record schema | `parse_crossref_payload()`, `PaperRecord` | Crossref response `message.items` | `data/raw/crossref_records.json` | Hoàn thành |
| Load raw snapshot cho baseline/reuse | `load_raw_records()` | `data/raw/crossref_records.json` | List `PaperRecord` cho Role 2 và Phase 1 | Hoàn thành |

Role 1 không sở hữu cleaning, retrieval, evaluation metrics hoặc corruption. Raw contract được bàn giao cho Hoàng Đức Anh để thực hiện cleaning và tạo evaluation set.

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
|---|---|---|---|
| Gọi nguồn Crossref với query/filter từ Settings | `fetch_source_records()` | Raw response được lưu trong `data/raw/crossref_response.json` | Artifact tồn tại, được Phase 1 đọc lại |
| Chuẩn hóa raw record | `parse_crossref_payload()` | 240 parsed records với `PaperRecord` schema ổn định | `data/raw/crossref_records.json` |
| Loại record raw không dùng được | `parse_crossref_payload()` | Bỏ item thiếu DOI/URL, title hoặc abstract; de-duplicate ID canonical | Kiểm tra parser và số lượng raw records |
| Bàn giao raw snapshot cho Role 2 | `load_raw_records()` | Role 2 tạo được 239 clean records | `data/clean/papers_clean.json` và baseline report |

Các artifact do phần ingestion cung cấp:

```text
data/raw/crossref_response.json
data/raw/crossref_records.json
```

Baseline hiện ghi nhận 240 raw records và sử dụng `cached raw snapshot`, giúp các bước sau không phụ thuộc việc Crossref thay đổi dữ liệu giữa các lần chạy.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Pipeline cần một nguồn raw có schema ổn định trước khi cleaning, embedding và evaluation. Crossref trả về payload lồng trong `message.items`, ngày ở dạng `date-parts`, title/abstract có thể là list hoặc chứa markup, authors là list dictionary và các link PDF nằm trong mảng `link`. Nếu chuyển thẳng payload sang các module sau, các trường sẽ không nhất quán.

### Cách triển khai

`crossref.py` thực hiện các bước:

1. Gửi request tới `https://api.crossref.org/works` với query, filter, sort publication và số rows từ `Settings`.
2. Retry tối đa 5 lần cho lỗi request hoặc status retryable như 429, 500, 502, 503, 504; dùng backoff theo attempt và tôn trọng `Retry-After` nếu có.
3. Lưu response JSON nguyên gốc trước khi parse để có snapshot audit.
4. Duyệt `message.items`, bỏ item không phải dictionary hoặc thiếu trường tối thiểu.
5. Tạo `paper_id` từ DOI, fallback sang URL; lấy title/abstract, authors, subject/type, publication date, update date và các URL.
6. De-duplicate theo ID canonical viết thường.
7. Lưu các record đã parse bằng `asdict(PaperRecord)` vào raw records JSON.

Parser giữ raw record ở mức đủ thông tin cho cleaning. Việc strip markup, flatten authors/categories và tạo `text_for_embedding` được giao cho Role 2 để tránh trộn trách nhiệm giữa ingestion và data modeling.

### Input, output và contract

| Thành phần | Mô tả |
|---|---|
| Input | Crossref REST API response hoặc raw JSON snapshot |
| Record schema | `paper_id`, `title`, `summary`, `authors`, `categories`, `primary_category`, `published`, `updated`, `abs_url`, `pdf_url`, `comment` |
| Output 1 | `data/raw/crossref_response.json` — response nguyên gốc |
| Output 2 | `data/raw/crossref_records.json` — list các parsed records |
| Module sử dụng output | `src/ingestion/cleaning.py`, `src/pipelines/phase1.py`, `src/pipelines/corruption_flow.py` |
| Điều kiện lỗi | Request failure sau retry, response không có record dùng được, raw JSON không phải list |

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Crossref là nguồn sống; nếu mỗi lần chạy đều fetch lại API, raw input có thể thay đổi và làm baseline không tái lập.
- **Các phương án đã cân nhắc:** Luôn fetch mới ở mỗi pipeline run; hoặc fetch một lần, lưu raw response/records rồi dùng cached snapshot cho các lần chạy sau.
- **Phương án đã chọn:** Lưu cả raw response và parsed records, sau đó ưu tiên `data/raw/crossref_records.json` khi `refresh_source` không bật.
- **Lý do:** Giữ reproducibility, giúp Role 2/Role 4 dùng cùng input và hỗ trợ repair từ raw snapshot mà không cần fetch API lại.
- **Bằng chứng:** Phase 1 report ghi `Source mode: cached raw snapshot`; hai raw artifacts tồn tại và được pipeline đọc thành công.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi:** Nguồn Crossref có thể trả status 429 hoặc lỗi server/network tạm thời; payload cũng có thể thiếu trường hoặc có cấu trúc không đúng kỳ vọng.
- **Lệnh hoặc bước tái hiện:** Chạy baseline qua `uv run python script/run_phase1.py`; khi raw snapshot tồn tại, kiểm tra pipeline dùng cached mode.
- **Nguyên nhân gốc:** API bên ngoài có rate limit và dữ liệu metadata không đồng nhất giữa các publisher.
- **Cách xử lý:** Thêm retry/backoff cho status retryable, User-Agent, kiểm tra response, bỏ item invalid, parse fallback DOI/URL và lưu snapshot trước khi chuyển sang cleaning.
- **Cách xác minh sau khi sửa:** `data/raw/crossref_response.json` và `data/raw/crossref_records.json` tồn tại; Phase 1 tiếp tục tạo được 239 clean records.
- **Điều học được:** Ingestion cần lưu raw bất biến trước khi biến đổi để có thể audit, debug và repair từ nguồn đáng tin cậy.

## 7. Hiểu biết về luồng end-to-end

1. Crossref trả response; `crossref.py` lưu nguyên bản và parse thành `PaperRecord`. Role 2 đọc parsed records để clean, sau đó embedding/index tạo vector từ `text_for_embedding`.
2. Evaluation set chứa câu hỏi, ground truth và `ground_truth_doc_ids`. Metrics dùng các ID này để kiểm tra document đúng có xuất hiện trong retrieval result hay không.
3. Quality checks kiểm tra schema/completeness/uniqueness và nội dung clean. Freshness theo dõi publication date, `age_days` và tỷ lệ stale. Hai lớp này khác nhau nhưng cùng đọc clean artifact.
4. Baseline, corrupted và repaired phải dùng cùng test set để metric thay đổi do dữ liệu/index, không do câu hỏi hoặc ground truth khác nhau.
5. Repair thành công khi bắt đầu lại từ `data/raw/crossref_records.json`, tạo repaired dataset hợp lệ, quality/freshness trở lại đạt và metrics RAG phục hồi. Corruption flow hiện đã chạy; repaired artifact có 239 rows, quality PASS, freshness FRESH và metrics trở lại baseline.

## 8. Phân tích kết quả

| Metric/signal | Baseline | Corrupted | Repaired | Nhận xét cá nhân |
|---|---:|---:|---:|---|
| `retrieval_hit_rate` | 0.6000 | 0.4500 | 0.6000 | Corruption giảm hit rate; repair khôi phục |
| `mean_token_f1` | 0.5642 | 0.2622 | 0.5642 | Corruption làm giảm answer overlap; repair khôi phục |
| `judge_accuracy` | 0.5000 | 0.2500 | 0.5000 | Phụ thuộc LLM/fallback judge |
| `mean_judge_score` | 3.1000 | 2.0500 | 3.1000 | Repair khôi phục điểm baseline |
| Quality checks | PASS | FAIL | PASS | Corrupted bị phát hiện bởi observability |
| Freshness | FRESH | FRESH theo threshold | FRESH | Corrupted có 48 stale rows, ratio 0.1672 |

Corruption flow đã chạy và cho thấy lỗi dữ liệu làm giảm cả retrieval/answer quality; repair từ raw snapshot khôi phục các metrics hiện tại. Bằng chứng ingestion quan trọng nhất vẫn là raw contract đủ ổn định để Role 2/Role 4 tái sử dụng mà không fetch API lại.

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. Raw snapshot là nền tảng của reproducibility; không nên chỉ giữ dataframe sau cleaning mà bỏ response gốc.
2. Record schema phải ổn định trước khi giao cho cleaning; DOI/URL, dates, authors và categories cần fallback rõ ràng.
3. Data pipeline không chỉ là fetch API; retry, validation, artifact path và source mode đều ảnh hưởng đến khả năng debug và repair.

### Nếu có thêm thời gian

Bổ sung kiểm tra thống kê raw payload như tỷ lệ thiếu authors/categories/date và lưu số item bị loại trong ingestion log; các flow hiện tại đã dùng raw snapshot để repair mà không fetch API lại.

## 10. Cam kết của thành viên

- [x] Nội dung báo cáo phản ánh đúng phần ingestion tôi phụ trách.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ `crossref.py`.
- [x] Kết luận baseline có artifact hoặc metric đối chiếu.
- [x] Tôi ghi nhận corruption/repaired sau khi các artifact và metrics đã được tạo; Role 1 không nhận ownership thay cho Role 4.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này tập trung vào Role 1, không sao chép nguyên văn báo cáo nhóm.

**Họ và tên:** Nguyễn Thu Huyền

**Ngày xác nhận:** 2026-08-06
