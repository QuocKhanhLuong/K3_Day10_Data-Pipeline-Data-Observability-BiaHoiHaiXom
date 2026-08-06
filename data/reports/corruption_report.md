# Corruption and Repair Comparison

## RAG metric comparison

| Metric | Baseline | Corrupted | Repaired |
|---|---|---|---|
| retrieval_hit_rate | 1.0000 | 0.4500 | 0.6000 |
| mean_token_f1 | 1.0000 | 0.2622 | 0.5642 |
| judge_accuracy | 1.0000 | 0.2500 | 0.5000 |
| mean_judge_score | 5 | 2.0500 | 3.1000 |

### Missing metric warnings

- None.

## Metric deltas

- `retrieval_hit_rate`: corruption delta -0.5500; repair delta vs corrupted +0.1500; remaining gap vs baseline -0.4000.
- `mean_token_f1`: corruption delta -0.7378; repair delta vs corrupted +0.3020; remaining gap vs baseline -0.4358.
- `judge_accuracy`: corruption delta -0.7500; repair delta vs corrupted +0.2500; remaining gap vs baseline -0.5000.
- `mean_judge_score`: corruption delta -2.9500; repair delta vs corrupted +1.0500; remaining gap vs baseline -1.9000.

## Repaired metric gaps versus baseline

- `retrieval_hit_rate`: repaired minus baseline -0.4000.
- `mean_token_f1`: repaired minus baseline -0.4358.
- `judge_accuracy`: repaired minus baseline -0.5000.
- `mean_judge_score`: repaired minus baseline -1.9000.

## Baseline data quality

- Overall status: **UNKNOWN**
- Total rows: n/a
- Checks: n/a

### Failed checks

- None.

## Baseline freshness

- Status: **UNKNOWN**
- Latest publication: n/a
- Oldest publication: n/a
- Latest age (days): n/a
- Future rows: n/a
- Invalid publication rows: n/a
- Stale rows: n/a
- Stale ratio: n/a
- Total rows: n/a

## Corrupted data quality

- Overall status: **FAIL**
- Total rows: 287
- `dataset_not_empty`: PASS (observed: 287; expectation: Dataset must contain at least one row.)
- `required_columns`: PASS (observed: []; expectation: All required cleaned-data columns must be present; extra columns are allowed.)
- `paper_id_completeness`: PASS (observed: 0; expectation: paper_id must be non-empty for every row.)
- `paper_id_uniqueness`: FAIL (observed: 48; expectation: paper_id must be unique.)
- `title_completeness`: PASS (observed: 0; expectation: title must be non-empty for every row.)
- `summary_completeness`: FAIL (observed: 48; expectation: summary must be non-empty for every row.)
- `summary_min_length`: FAIL (observed: 48; expectation: Every summary must contain at least 100 characters.)
- `published_date_parseable`: PASS (observed: 0; expectation: published must be a parseable date for every row.)
- `future_published_dates`: PASS (observed: 0; expectation: published must not be later than the current UTC date.)
- `age_days_numeric`: PASS (observed: 0; expectation: age_days must be numeric for every row.)
- `age_days_non_negative`: PASS (observed: 0; expectation: age_days must be greater than or equal to zero.)
- `authors_joined_completeness`: PASS (observed: 0; expectation: authors_joined must be non-empty for every row.)
- `categories_joined_completeness`: PASS (observed: 0; expectation: categories_joined must be non-empty for every row.)
- `embedding_text_completeness`: PASS (observed: 0; expectation: text_for_embedding must be non-empty for every row.)
- `embedding_text_canonical_format`: FAIL (observed: 97; expectation: text_for_embedding must equal 'Title: {title} | Authors: {authors_joined} | Summary: {summary}'.)
- `freshness_ratio`: PASS (observed: 0.1672; expectation: At most 20% of records may be stale or have invalid dates.)

### Failed checks

- `paper_id_uniqueness`
- `summary_completeness`
- `summary_min_length`
- `embedding_text_canonical_format`

## Corrupted freshness

- Status: **FRESH**
- Latest publication: 2026-08-05
- Oldest publication: 2000-01-01
- Latest age (days): 1
- Future rows: 0
- Invalid publication rows: 0
- Stale rows: 48
- Stale ratio: 0.1672
- Total rows: 287

## Repaired data quality

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

## Repaired freshness

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

Data quality and freshness recovered, but RAG performance recovery is not fully demonstrated; review the remaining metric gaps above.

<!-- C4_THREE_STATE_SUMMARY_START -->
## Checkpoint C4 - Three-state comparison

All three states were evaluated with the same frozen test set.
Frozen test set SHA-256: `3807187b60127dc5b331a3d7d2313fd6cec1a67b78abdab71cfde5aac8791ee3`.

### RAG metrics

| Metric | Baseline | Corrupted | Repaired |
|---|---:|---:|---:|
| `retrieval_hit_rate` | 1.0000 | 0.4500 | 0.6000 |
| `mean_token_f1` | 1.0000 | 0.2622 | 0.5642 |
| `judge_accuracy` | 1.0000 | 0.2500 | 0.5000 |
| `mean_judge_score` | 5.0000 | 2.0500 | 3.1000 |

### Data observability

| Signal | Baseline | Corrupted | Repaired |
|---|---|---|---|
| `status` | pass | fail | pass |
| `completeness` | N/A | N/A | N/A |
| `uniqueness` | N/A | N/A | N/A |
| `freshness` | N/A | N/A | N/A |

<!-- C4_THREE_STATE_SUMMARY_END -->
