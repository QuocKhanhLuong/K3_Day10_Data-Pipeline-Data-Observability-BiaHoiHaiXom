# Phân công 4 Role — Day 10 Data Pipeline & Data Observability

## Role 1 — Source Ingestion

### File phụ trách

```text
src/ingestion/crossref.py
```

### Giới hạn

- Không sửa cleaning, retrieval hoặc pipeline.
- Dùng query, filter và artifact paths từ `Settings`.
- Đầu ra bắt buộc:
  - `data/raw/crossref_response.json`
  - `data/raw/crossref_records.json`

---

## Role 2 — Cleaning & Evaluation Set

### File phụ trách

```text
src/ingestion/cleaning.py
src/evaluation/testset.py
```

### Giới hạn

- Không sửa retrieval và `src/evaluation/metrics.py`.
- Giữ đúng clean schema đã thống nhất.
- Loại summary ngắn hơn 100 ký tự.
- Evaluation set gồm 5–10 câu, sinh deterministic.
- Không ghi đè test set sau khi đã freeze.

---

## Role 3 — Data Observability

### File phụ trách

```text
src/observability/quality.py
src/observability/reporting.py
```

### Giới hạn

- Không sửa cleaning hoặc corruption.
- Dùng cùng một quality-checking logic cho Baseline, Corrupted và Repaired.
- Báo cáo phải đọc số liệu thật từ JSON artifact.
- Không hard-code metrics hoặc kết quả PASS/FAIL.

---

## Role 4 — Corruption & Integration

### File phụ trách

```text
src/ingestion/corruption.py
src/pipelines/phase1.py
src/pipelines/corruption_flow.py
```

### File chỉ kiểm tra nhẹ khi cần

```text
script/run_phase1.py
script/run_corruption_flow.py
```

### Giới hạn

- Không rewrite retrieval.
- Corruption phải tác động ít nhất một `ground_truth_doc_id` trong frozen test set.
- Baseline, Corrupted và Repaired phải dùng chung một test set.
- Repair phải bắt đầu từ `data/raw/crossref_records.json`.
- Không repair trực tiếp từ corrupted dataset.
- Không fetch lại API trong bước repair.

---

## File shared — Không tự ý sửa

```text
src/core/config.py
src/core/utils.py
src/retrieval/*
src/evaluation/metrics.py
pyproject.toml
uv.lock
```

Chỉ sửa các file shared sau khi cả nhóm thống nhất contract và người tích hợp xác nhận.

---

## Thứ tự tích hợp đề xuất

```text
Role 1 — Ingestion
        ↓
Role 2 — Cleaning & Evaluation Set
        ↓
Role 3 — Observability
        ↓
Role 4 — Corruption & Integration
```
