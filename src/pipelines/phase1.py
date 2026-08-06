from __future__ import annotations

from dataclasses import asdict
import json

from core.config import load_settings
from core.utils import now_utc, read_json, write_csv, write_json
from evaluation.metrics import evaluate_pipeline
from evaluation.testset import build_test_set
from ingestion.cleaning import build_clean_dataframe
from ingestion.crossref import fetch_source_records, load_raw_records
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_phase1_report
from retrieval.index import LocalEmbeddingIndex
from retrieval.qa import answer_question


def _dataframe_records(df) -> list[dict]:
    return json.loads(df.to_json(orient="records"))


def main() -> None:
    """Run the clean baseline pipeline end-to-end."""
    settings = load_settings()
    run_date = now_utc()

    if settings.paths.raw_records_json.exists() and not settings.refresh_source:
        raw_records = load_raw_records(settings.paths.raw_records_json)
        source_mode = "cached raw snapshot"
    else:
        raw_records = fetch_source_records(settings)
        source_mode = "Crossref API"

    clean_df = build_clean_dataframe(raw_records, run_date=run_date)
    if clean_df.empty:
        raise RuntimeError("Cleaning produced zero records; inspect raw artifacts and filtering rules.")

    write_csv(clean_df, settings.paths.clean_csv)
    write_json(settings.paths.clean_json, _dataframe_records(clean_df))

    index = LocalEmbeddingIndex.build(
        clean_df,
        settings=settings,
        embeddings_output_path=settings.paths.embeddings_json,
    )

    if settings.paths.eval_testset.exists() and not settings.refresh_test_set:
        test_set = read_json(settings.paths.eval_testset)
    else:
        test_set = build_test_set(clean_df, settings.paths.eval_testset)

    evaluation = evaluate_pipeline(
        settings=settings,
        index=index,
        test_set_path=settings.paths.eval_testset,
        metrics_output_path=settings.paths.baseline_metrics,
        answers_output_path=settings.paths.baseline_answers,
    )

    quality = run_data_quality_checks(
        clean_df,
        settings=settings,
        report_name="baseline_quality.json",
    )
    freshness = build_freshness_report(
        clean_df,
        settings=settings,
        report_path=settings.paths.freshness_report,
    )

    source_summary = {
        "source": settings.source_api,
        "source_mode": source_mode,
        "query": settings.source_query,
        "filter": settings.source_filter,
        "raw_records": len(raw_records),
        "clean_records": len(clean_df),
        "raw_response_path": str(settings.paths.raw_api_response),
        "raw_records_path": str(settings.paths.raw_records_json),
        "clean_csv_path": str(settings.paths.clean_csv),
        "clean_json_path": str(settings.paths.clean_json),
    }
    generate_phase1_report(
        settings.paths.baseline_report,
        source_summary=source_summary,
        metrics=evaluation.summary,
        quality=quality,
        freshness=freshness,
    )

    demo_answers = []
    for item in test_set[: min(4, len(test_set))]:
        result = answer_question(item["question"], settings=settings, index=index)
        demo_answers.append(
            {
                **asdict(result),
                "ground_truth": item["ground_truth"],
                "ground_truth_doc_ids": item["ground_truth_doc_ids"],
            }
        )
    write_json(settings.paths.demo_answers, demo_answers)

    print("Phase 1 completed.")
    print(f"Raw records: {len(raw_records)}")
    print(f"Clean records: {len(clean_df)}")
    print(f"Evaluation samples: {evaluation.summary['samples']}")
    print(f"Retrieval hit rate: {evaluation.summary['retrieval_hit_rate']:.4f}")
    print(f"Mean token F1: {evaluation.summary['mean_token_f1']:.4f}")
    print(f"Quality status: {quality['status']}")
    print(f"Freshness status: {'fresh' if freshness['is_fresh'] else 'stale'}")
    print(f"Report: {settings.paths.baseline_report}")
