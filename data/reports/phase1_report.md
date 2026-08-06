# Phase 1 — Baseline Data Pipeline Report

## Source and artifacts

- Source: Crossref REST API
- Source mode: cached raw snapshot
- Query: `agentic retrieval augmented generation large language model`
- Filter: `from-pub-date:2026-02-07,has-abstract:true`
- Raw records: 240
- Clean records: 239
- Evaluation samples: 20
- Raw response artifact: D:\GIT\K3_Day10_Data-Pipeline-Data-Observability\data\raw\crossref_response.json
- Raw records artifact: D:\GIT\K3_Day10_Data-Pipeline-Data-Observability\data\raw\crossref_records.json
- Clean CSV artifact: D:\GIT\K3_Day10_Data-Pipeline-Data-Observability\data\clean\papers_clean.csv
- Clean JSON artifact: D:\GIT\K3_Day10_Data-Pipeline-Data-Observability\data\clean\papers_clean.json

## Baseline RAG metrics

| Metric | Baseline |
|---|---|
| retrieval_hit_rate | 0.6000 |
| mean_token_f1 | 0.5642 |
| judge_accuracy | 0.5000 |
| mean_judge_score | 3.1000 |

### Missing metric warnings

- None.

- Ragas: `{'skipped': 'Set RUN_RAGAS=1 to enable the slower Ragas pass.'}`

## Baseline data quality

- Overall status: **PASS**
- Total rows: 239
- `dataset_not_empty`: PASS (observed: 239; expectation: Dataset must contain at least one row.)
- `required_columns`: PASS (observed: []; expectation: All required cleaned-data columns must be present; extra columns are allowed.)
- `paper_id_completeness`: PASS (observed: 0; expectation: paper_id must be non-empty for every row.)
- `paper_id_uniqueness`: PASS (observed: 0; expectation: paper_id must be unique.)
- `title_completeness`: PASS (observed: 0; expectation: title must be non-empty for every row.)
- `summary_completeness`: PASS (observed: 0; expectation: summary must be non-empty for every row.)
- `summary_min_length`: PASS (observed: 0; expectation: Every summary must contain at least 100 characters.)
- `published_date_parseable`: PASS (observed: 0; expectation: published must be a parseable date for every row.)
- `future_published_dates`: PASS (observed: 0; expectation: published must not be later than the current UTC date.)
- `age_days_numeric`: PASS (observed: 0; expectation: age_days must be numeric for every row.)
- `age_days_non_negative`: PASS (observed: 0; expectation: age_days must be greater than or equal to zero.)
- `authors_joined_completeness`: PASS (observed: 0; expectation: authors_joined must be non-empty for every row.)
- `categories_joined_completeness`: PASS (observed: 0; expectation: categories_joined must be non-empty for every row.)
- `embedding_text_completeness`: PASS (observed: 0; expectation: text_for_embedding must be non-empty for every row.)
- `embedding_text_canonical_format`: PASS (observed: 0; expectation: text_for_embedding must equal 'Title: {title} | Authors: {authors_joined} | Summary: {summary}'.)
- `freshness_ratio`: PASS (observed: 0.0000; expectation: At most 20% of records may be stale or have invalid dates.)

### Failed checks

- None.

## Baseline freshness

- Status: **FRESH**
- Latest publication: 2026-08-05
- Oldest publication: 2026-02-11
- Latest age (days): 1
- Future rows: 0
- Invalid publication rows: 0
- Stale rows: 0
- Stale ratio: 0.0000
- Total rows: 239

## Conclusion

The baseline quality and freshness artifacts pass, so it is ready for corruption testing.
