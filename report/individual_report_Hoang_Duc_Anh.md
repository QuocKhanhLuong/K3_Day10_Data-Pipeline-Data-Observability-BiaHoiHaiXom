# Member Role Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
|---|---|
| Họ và tên | Hoàng Đức Anh |
| MSSV | 2A202601223 |
| Khóa/Lớp | K3 |
| Tên nhóm | BiaHoiHaiXom |
| Vai trò chính | Role 2 — Data Model & Evaluation Set Owner |
| Repository | `K3_Day10_Data-Pipeline-Data-Observability` |
| Ngày hoàn thành | 2026-08-06 |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
|---|---|---|---|---|
| Làm sạch dữ liệu cho retrieval | `src/ingestion/cleaning.py`, đặc biệt `build_clean_dataframe()` | `data/raw/crossref_records.json` và `PaperRecord` | `data/clean/papers_clean.csv`, `data/clean/papers_clean.json` | Hoàn thành |
| Đóng băng evaluation set | `src/evaluation/testset.py`, `build_test_set()` | Clean dataframe / `papers_clean.json` | `data/eval/test_set.json` | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
|---|---|---|
| Kiểm tra clean schema và document IDs | Role 3 — Observability, Role 4 — Integration | Quality checks và pipeline có thể dùng chung clean contract |
| Chạy embedding và tạo vector index | `src/retrieval/embeddings.py`, `src/retrieval/index.py` | Model `all-MiniLM-L6-v2` tạo vector 384 chiều; ChromaDB baseline có 239 documents và metadata `paper_id` |
| Kiểm tra retrieval với frozen questions | `src/retrieval/index.py`, `src/retrieval/qa.py` | Xác nhận `ground_truth_doc_ids` tồn tại trong clean corpus và QA đọc được metadata authors/date/category |

Role 2 không sở hữu retrieval, metrics hoặc corruption. Corruption/repaired do Role 4 thực hiện và đã có artifact; Role 2 kiểm tra rằng các trạng thái vẫn dùng cùng clean contract và frozen evaluation set.

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
|---|---|---|---|
| Chuẩn hóa text và loại record không hợp lệ | `cleaning.py`, `build_clean_dataframe()` | 240 raw records tạo thành 239 clean records | Kiểm tra `papers_clean.json` và `baseline_quality.json` |
| Xử lý authors/categories nested | `_append_normalized()`, `_normalize_list()` | Có `authors_joined`, `categories_joined` dạng chuỗi, không giữ dict lồng trong joined fields | Kiểm tra clean schema và quality checks |
| Tạo freshness fields | `_parse_date()`, `published`, `age_days` | `published` dạng `YYYY-MM-DD`, `age_days` là số nguyên | `data/quality/freshness_report.json` |
| Tạo semantic text | `text_for_embedding` | Format canonical `Title: ... \| Authors: ... \| Summary: ...` | `baseline_quality.json` — `embedding_text_canonical_format: PASS` |
| Tạo frozen evaluation set | `testset.py`, `build_test_set()` | 20 samples `q1`–`q20`, factual, ground truth trực tiếp từ clean data | Schema validation và `data/eval/test_set.json` |
| Chạy thử embedding/index/retrieval | `src/retrieval/embeddings.py`, `src/retrieval/index.py`, `src/retrieval/qa.py` | Collection `papers-baseline`, 239 documents, vector 384 chiều; retrieval trả về top-k kèm `paper_id` | `data/chroma/`, `data/embeddings/papers_embeddings.json`, QA smoke test |

Output quan trọng nhất là cặp clean artifact:

```text
data/clean/papers_clean.csv
data/clean/papers_clean.json
```

Clean dataset có 239 rows, đủ các field cần cho retrieval, evaluation và observability. Frozen set hiện có 20 câu; `ground_truth_doc_ids` của các câu đều tồn tại trong clean dataset.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Dữ liệu Crossref có thể chứa XML/HTML trong title và abstract, authors có thể là list các dictionary `given/family/name`, categories có thể có nhiều dạng list/dict, còn ngày publication cần được chuẩn hóa trước khi đưa vào retrieval. Nếu giữ nguyên các dạng này, embedding text sẽ chứa markup hoặc chuỗi biểu diễn dict, làm giảm khả năng truy hồi và khiến metadata không nhất quán.

Ngoài ra, baseline/corrupted/repaired phải dùng cùng evaluation set. Nếu mỗi trạng thái tạo câu hỏi khác nhau, thay đổi metrics không còn chỉ phản ánh thay đổi dữ liệu.

### Cách triển khai

`cleaning.py` thực hiện các bước chính:

1. Đọc từng `PaperRecord` và chuyển về row chuẩn.
2. Dùng `_normalize_text()` để `unescape`, loại XML/HTML bằng regex và chuẩn hóa whitespace.
3. Dùng `_append_normalized()` để flatten scalar/list/dict; dictionary authors được ghép `given + family`, còn `name`, `label`, `term`, `value` được xử lý như text. Giá trị trùng được loại theo `casefold()`.
4. Loại record thiếu `paper_id`, title, publication date hoặc summary ngắn hơn 100 ký tự.
5. Chuẩn hóa `published` về `YYYY-MM-DD`, giữ `updated` ở dạng ISO và tính `age_days` từ `run_timestamp`.
6. Tạo `authors_joined`, `categories_joined` và `text_for_embedding`.
7. Loại duplicate theo `paper_id` và title không phân biệt hoa thường.
8. Lưu clean dataframe thành CSV/JSON bằng `save_clean_data()`.

`testset.py` sắp xếp dữ liệu deterministic theo publication date và `paper_id`, sau đó tạo bộ câu hỏi có ID ổn định. Bộ hiện tại có 15 câu hỏi theo topic rút gọn và 5 câu có full title trong dấu nháy để kiểm tra exact-title lookup; tất cả đều có `question_type: factual`, `ground_truth` và `ground_truth_doc_ids`.

Ngoài ownership chính, tôi đã chạy thử local embedding và retrieval trên clean dataset mới. `all-MiniLM-L6-v2` tạo vector 384 chiều; `LocalEmbeddingIndex` tạo collection `papers-baseline` trong `data/chroma/`, lưu manifest tại `data/embeddings/papers_embeddings.json` và giữ `paper_id` trong metadata. `qa.py` sau đó truy vấn top-k và trả lời factual từ metadata/context. Phần này là kiểm thử hỗ trợ cho Role 4, không thay đổi các file shared trong `src/retrieval/`.

### Input, output và contract

| Thành phần | Mô tả |
|---|---|
| Input | `data/raw/crossref_records.json`, list các record Crossref đã parse |
| Clean output | `data/clean/papers_clean.csv`, `data/clean/papers_clean.json` |
| Evaluation input | Clean dataframe hoặc `papers_clean.json` |
| Evaluation output | `data/eval/test_set.json`, 20 samples `q1`–`q20` |
| Module phụ thuộc | `core.utils`, `ingestion.crossref.PaperRecord`, pandas |
| Module sử dụng output | `retrieval.index`, `evaluation.metrics`, `observability.quality`, `pipelines.phase1` |
| Điều kiện lỗi | Missing required fields, invalid publication date, summary <100, duplicate IDs/title |

### Cách xác minh

```bash
uv run python script/run_phase1.py
```

Kiểm tra bổ sung đã thực hiện trên clean/test artifacts:

```text
raw records: 240
clean records: 239
evaluation samples: 20
all ground_truth_doc_ids exist in clean: True
```

- **Kết quả mong đợi:** Clean schema hợp lệ, test set có ID duy nhất và ground-truth document IDs tồn tại.
- **Kết quả thực tế:** Đạt; quality baseline `PASS`, clean dataset có 239 rows.
- **Artifact/log:** `data/clean/`, `data/eval/test_set.json`, `data/quality/baseline_quality.json`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Authors trong raw data có thể là dictionary nested; nếu gọi `str()` trực tiếp sẽ tạo text dạng `{'given': ..., 'family': ...}` và không phù hợp cho retrieval.
- **Các phương án đã cân nhắc:** Giữ nguyên dictionary và serialize JSON; hoặc flatten về tên người đọc được rồi tạo chuỗi joined.
- **Phương án đã chọn:** Flatten theo thứ tự `given`, `family`, fallback sang `name/label/term/value`, loại duplicate và tạo `authors_joined` cách nhau bởi `, `.
- **Lý do:** Schema ổn định hơn, embedding text dễ đọc hơn, metadata truy xuất được trực tiếp và không phụ thuộc thứ tự key của dictionary.
- **Bằng chứng:** Các clean rows có `authors_joined`/`categories_joined` hợp lệ; quality check `authors_joined_completeness` và `categories_joined_completeness` đều PASS.

Một quyết định khác là giữ frozen evaluation set thay vì tạo lại trong mỗi lần chạy. Phase 1 tái sử dụng `data/eval/test_set.json` khi `refresh_test_set` không bật và validate các document IDs với clean dataframe hiện tại.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng:** Clean data có thể chứa markup như `<jats:p>`/`<b>` và authors nested dict; nếu đưa trực tiếp vào embedding sẽ làm bẩn nội dung và joined fields.
- **Lệnh hoặc bước tái hiện:** Chạy cleaning từ `data/raw/crossref_records.json`, sau đó kiểm tra title/summary, joined fields và `text_for_embedding` trong clean JSON.
- **Nguyên nhân gốc:** Raw Crossref payload không có một dạng thống nhất cho text markup và các trường list/dict.
- **Cách xử lý:** Thêm `_normalize_text()` và `_append_normalized()` trong `cleaning.py`, áp dụng summary threshold 100 ký tự, parse date và deduplicate.
- **Cách xác minh sau khi sửa:** Baseline quality report có toàn bộ checks PASS; `embedding_text_canonical_format` PASS và không có summary ngắn.
- **Điều học được:** Data contract phải được chuẩn hóa trước embedding; nếu không, lỗi schema sẽ lan sang vector index và evaluation.

Phần LLM/network không thuộc ownership chính của Role 2. Việc gọi Gemini có thể phụ thuộc network, nhưng clean artifact và frozen test set không phụ thuộc API key.

## 7. Hiểu biết về luồng end-to-end

1. Raw records từ Crossref được Role 1 lưu vào `data/raw/`. Role 2 làm sạch và tạo `text_for_embedding`; retrieval dùng trường này để tạo vector và lưu document/metadata vào ChromaDB.
2. Mỗi evaluation sample có câu hỏi, ground truth và `ground_truth_doc_ids`. Evaluation chạy QA, so sánh retrieved IDs với ground-truth IDs để tính retrieval hit, sau đó so sánh answer với ground truth bằng token F1 và judge.
3. Quality checks kiểm tra schema, completeness, uniqueness, summary length và embedding text. Freshness monitoring tập trung vào publication date, `age_days`, stale rows và freshness ratio.
4. Cùng một test set là điều kiện cần để baseline, corrupted và repaired có cùng câu hỏi, ground truth và target documents. Khi đó thay đổi metrics mới có thể quy về thay đổi dataset/index.
5. Repair thành công khi repaired dataset đạt quality PASS, freshness đạt FRESH, các artifact repaired được tạo từ `data/raw/crossref_records.json`, và metrics agent phục hồi so với corrupted/baseline. Kết quả hiện tại cho thấy repaired data có 239 rows, quality PASS, freshness FRESH và metrics trở lại baseline.

## 8. Phân tích kết quả

### Metrics chính

| Metric/signal | Baseline | Corrupted | Repaired | Nhận xét cá nhân |
|---|---:|---:|---:|---|
| `retrieval_hit_rate` | 0.6000 | 0.4500 | 0.6000 | Corruption giảm 0.15; repaired trở lại baseline |
| `mean_token_f1` | 0.5642 | 0.2622 | 0.5642 | Corruption làm giảm answer overlap; repair khôi phục |
| `judge_accuracy` | 0.5000 | 0.2500 | 0.5000 | Phụ thuộc chất lượng answer và LLM/fallback judge |
| `mean_judge_score` | 3.1000 | 2.0500 | 3.1000 | Repaired trở lại điểm baseline hiện tại |
| Quality checks | PASS | FAIL | PASS | Corrupted có duplicate/summary/embedding-format failures |
| Freshness status | FRESH | FRESH theo threshold | FRESH | Corrupted có 48 stale rows, ratio 0.1672 |

### Kết luận từ số liệu

Hiện chỉ có thể kết luận được chuỗi baseline:

```text
Raw/Clean data contract hợp lệ -> quality PASS và freshness FRESH
    -> baseline retrieval_hit_rate 0.6000, mean_token_f1 0.5642
```

Corruption flow đã có `corruption_log.json`, corrupted metrics và repaired metrics. Corrupted data làm giảm retrieval hit rate từ 0.6000 xuống 0.4500 và mean token F1 từ 0.5642 xuống 0.2622; repaired metrics hiện tại trở lại baseline. Vai trò của Role 2 là xác nhận input/contract mà flow dùng vẫn đúng.

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. Clean schema cần được chốt trước khi embedding; markup và nested dict nếu không xử lý sẽ làm sai nội dung semantic.
2. Evaluation set là một artifact độc lập, cần deterministic và có `ground_truth_doc_ids` tồn tại trong clean corpus.
3. Chất lượng dữ liệu và freshness là điều kiện đầu vào của RAG; quality PASS không đồng nghĩa retrieval/answer metrics đã cao, nhưng giúp phân biệt lỗi dữ liệu với lỗi retrieval/LLM.

### Nếu có thêm thời gian

Đã chạy Phase 2 với cùng `data/eval/test_set.json`; Role 2 cần tiếp tục kiểm tra thêm rằng repair từ raw snapshot tái tạo đúng clean schema và không làm thay đổi frozen test set.

## 10. Cam kết của thành viên

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [x] Tôi phân biệt rõ phần Role 2 sở hữu với artifact corruption/repaired do Role 4 bàn giao.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này tập trung vào Role 2, không sao chép nguyên văn báo cáo nhóm.

**Họ và tên:** Hoàng Đức Anh

**Ngày xác nhận:** 2026-08-06
