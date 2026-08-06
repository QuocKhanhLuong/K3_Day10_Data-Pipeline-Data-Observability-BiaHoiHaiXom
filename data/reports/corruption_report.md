# Corruption and Repair Comparison

All three states were evaluated with the same frozen test set.

- Frozen test set: `data/eval/test_set.json`
- Frozen test set SHA-256: `9DAFDE0C18D2411A6986207E3D79572DC75F414404586E7EC45E092F02354CDC`
- Samples: 20
- Corruption seed: 42
- Corruption ratio: 0.2

## RAG metric comparison

| Metric | Baseline | Corrupted | Repaired |
|---|---:|---:|---:|
| `retrieval_hit_rate` | 0.6000 | 0.4500 | 0.6000 |
| `mean_token_f1` | 0.5642 | 0.2622 | 0.5642 |
| `judge_accuracy` | 0.5000 | 0.2500 | 0.5000 |
| `mean_judge_score` | 3.1000 | 2.0500 | 3.1000 |

### Metric deltas

| Metric | Corrupted - baseline | Repaired - corrupted | Repaired - baseline |
|---|---:|---:|---:|
| `retrieval_hit_rate` | -0.1500 | +0.1500 | 0.0000 |
| `mean_token_f1` | -0.3020 | +0.3020 | 0.0000 |
| `judge_accuracy` | -0.2500 | +0.2500 | 0.0000 |
| `mean_judge_score` | -1.0500 | +1.0500 | 0.0000 |

Ragas was skipped because `RUN_RAGAS=1` was not enabled.

## Data quality comparison

| Signal | Baseline | Corrupted | Repaired |
|---|---|---|---|
| Rows | 239 | 287 | 239 |
| Overall status | PASS | FAIL | PASS |
| `paper_id` uniqueness failures | 0 | 48 | 0 |
| Summary completeness failures | 0 | 48 | 0 |
| Summary minimum-length failures | 0 | 48 | 0 |
| Canonical embedding-text failures | 0 | 97 | 0 |

The corrupted quality report also records 48 stale rows with stale ratio `0.1672`. The freshness status remains FRESH because the configured threshold allows up to 20% stale/invalid rows; the stale count is still exposed for observability.

## Freshness comparison

| Signal | Baseline | Corrupted | Repaired |
|---|---:|---:|---:|
| Status | FRESH | FRESH (threshold) | FRESH |
| Latest publication | 2026-08-05 | 2026-08-05 | 2026-08-05 |
| Oldest publication | 2026-02-11 | 2000-01-01 | 2026-02-11 |
| Latest age (days) | 1 | 1 | 1 |
| Stale rows | 0 | 48 | 0 |
| Stale ratio | 0.0000 | 0.1672 | 0.0000 |

## Interpretation

Corruption reduced both retrieval and answer quality while producing concrete quality violations. Repair was performed from `data/raw/crossref_records.json`, without requiring a new Crossref request. The repaired dataset returned to 239 rows, quality PASS, freshness FRESH and the current baseline metrics.

## Source artifacts

- `data/results/baseline_metrics.json`
- `data/results/corrupted_metrics.json`
- `data/results/repaired_metrics.json`
- `data/quality/baseline_quality.json`
- `data/quality/corrupted_quality.json`
- `data/quality/repaired_quality.json`
- `data/quality/freshness_baseline.json`
- `data/quality/freshness_corrupted.json`
- `data/quality/freshness_repaired.json`
- `data/results/corruption_log.json`
