from __future__ import annotations

import json

import pandas as pd

from core.config import load_settings
from core.utils import now_utc, read_json, write_csv, write_json
from evaluation.metrics import evaluate_pipeline
from ingestion.cleaning import build_clean_dataframe
from ingestion.corruption import corrupt_clean_dataframe
from ingestion.crossref import load_raw_records
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_corruption_report
from pipelines.phase1 import main as run_phase1
from retrieval.index import LocalEmbeddingIndex


def _dataframe_records(df: pd.DataFrame) -> list[dict]:
    return json.loads(df.to_json(orient="records"))


def _ensure_baseline() -> None:
    settings = load_settings()
    required = (
        settings.paths.clean_json,
        settings.paths.raw_records_json,
        settings.paths.eval_testset,
        settings.paths.baseline_metrics,
    )
    if not all(path.exists() for path in required):
        print("Baseline artifacts are incomplete; running Phase 1 first.")
        run_phase1()


def main() -> None:
    """Run corruption, impact evaluation, raw-snapshot repair, and comparison."""
    _ensure_baseline()
    settings = load_settings()

    baseline_metrics = read_json(settings.paths.baseline_metrics)
    clean_payload = read_json(settings.paths.clean_json)
    clean_df = pd.DataFrame(clean_payload)
    if clean_df.empty:
        raise RuntimeError("Baseline cleaned dataset is empty.")

    corrupted_df = corrupt_clean_dataframe(
        clean_df,
        output_log_path=settings.paths.corruption_log,
    )
    write_csv(corrupted_df, settings.paths.corrupted_clean_csv)
    write_json(settings.paths.corrupted_clean_json, _dataframe_records(corrupted_df))

    corrupted_index = LocalEmbeddingIndex.build(
        corrupted_df,
        settings=settings,
        embeddings_output_path=settings.paths.corrupted_embeddings_json,
    )
    corrupted_evaluation = evaluate_pipeline(
        settings=settings,
        index=corrupted_index,
        test_set_path=settings.paths.eval_testset,
        metrics_output_path=settings.paths.corrupted_metrics,
        answers_output_path=settings.paths.corrupted_answers,
    )
    corrupted_quality = run_data_quality_checks(
        corrupted_df,
        settings=settings,
        report_name="corrupted_quality.json",
    )
    corrupted_freshness = build_freshness_report(
        corrupted_df,
        settings=settings,
        report_path=settings.paths.quality_dir / "freshness_corrupted.json",
    )

    raw_records = load_raw_records(settings.paths.raw_records_json)
    repaired_df = build_clean_dataframe(raw_records, run_date=now_utc())
    if repaired_df.empty:
        raise RuntimeError("Repair from raw records produced zero rows.")
    write_csv(repaired_df, settings.paths.repaired_clean_csv)
    write_json(settings.paths.repaired_clean_json, _dataframe_records(repaired_df))

    repaired_index = LocalEmbeddingIndex.build(
        repaired_df,
        settings=settings,
        embeddings_output_path=settings.paths.repaired_embeddings_json,
    )
    repaired_evaluation = evaluate_pipeline(
        settings=settings,
        index=repaired_index,
        test_set_path=settings.paths.eval_testset,
        metrics_output_path=settings.paths.repaired_metrics,
        answers_output_path=settings.paths.repaired_answers,
    )
    repaired_quality = run_data_quality_checks(
        repaired_df,
        settings=settings,
        report_name="repaired_quality.json",
    )
    repaired_freshness = build_freshness_report(
        repaired_df,
        settings=settings,
        report_path=settings.paths.quality_dir / "freshness_repaired.json",
    )

    generate_corruption_report(
        settings.paths.comparison_report,
        baseline_metrics=baseline_metrics,
        corrupted_metrics=corrupted_evaluation.summary,
        repaired_metrics=repaired_evaluation.summary,
        corrupted_quality=corrupted_quality,
        repaired_quality=repaired_quality,
        corrupted_freshness=corrupted_freshness,
        repaired_freshness=repaired_freshness,
    )

    print("Corruption flow completed.")
    for metric in (
        "retrieval_hit_rate",
        "mean_token_f1",
        "judge_accuracy",
        "mean_judge_score",
    ):
        baseline = float(baseline_metrics.get(metric, 0.0))
        corrupted = float(corrupted_evaluation.summary.get(metric, 0.0))
        repaired = float(repaired_evaluation.summary.get(metric, 0.0))
        print(
            f"{metric}: baseline={baseline:.4f}, "
            f"corrupted={corrupted:.4f}, repaired={repaired:.4f}"
        )
    print(f"Corrupted quality: {corrupted_quality['status']}")
    print(f"Repaired quality: {repaired_quality['status']}")
    print(f"Report: {settings.paths.comparison_report}")
