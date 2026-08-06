from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from core.config import load_settings
from core.utils import now_utc, read_json, write_csv, write_json
from evaluation.metrics import evaluate_pipeline
from evaluation.testset import build_test_set
from ingestion.cleaning import build_clean_dataframe
from ingestion.crossref import fetch_source_records, load_raw_records
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_phase1_report
from retrieval.index import LocalEmbeddingIndex


MIN_TEST_SAMPLES = 5
CLEAN_REQUIRED_COLUMNS = {
    "paper_id",
    "title",
    "summary",
    "authors_joined",
    "categories_joined",
    "published",
    "age_days",
    "text_for_embedding",
}
TEST_REQUIRED_FIELDS = {
    "id",
    "question_type",
    "question",
    "ground_truth",
    "ground_truth_doc_ids",
}
BASELINE_REQUIRED_METRICS = {
    "samples",
    "retrieval_hit_rate",
    "mean_token_f1",
}


def _dataframe_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Serialize dates consistently for Phase 2 to read back safely."""
    return json.loads(
        df.to_json(
            orient="records",
            date_format="iso",
        )
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_paths(paths: list[Path], stage: str) -> None:
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        raise RuntimeError(f"{stage} did not create required artifacts: {', '.join(missing)}")


def _validate_raw_records(raw_records: Any) -> None:
    if not isinstance(raw_records, list):
        raise ValueError("Raw Crossref records must be a list.")
    if not raw_records:
        raise ValueError("Raw Crossref snapshot contains zero records.")


def _validate_clean_dataframe(clean_df: pd.DataFrame) -> None:
    if clean_df.empty:
        raise RuntimeError(
            "Cleaning produced zero records; inspect raw artifacts and filtering rules."
        )

    missing_columns = sorted(CLEAN_REQUIRED_COLUMNS - set(clean_df.columns))
    if missing_columns:
        raise ValueError(
            f"Clean dataframe is missing required columns: {missing_columns}"
        )

    paper_ids = clean_df["paper_id"]
    if paper_ids.isna().any() or paper_ids.astype(str).str.strip().eq("").any():
        raise ValueError("Clean dataframe contains empty paper_id values.")
    if paper_ids.astype(str).duplicated().any():
        raise ValueError("Clean dataframe contains duplicate paper_id values.")

    titles = clean_df["title"].fillna("").astype(str).str.strip()
    if titles.eq("").any():
        raise ValueError("Clean dataframe contains empty titles.")

    summaries = clean_df["summary"].fillna("").astype(str).str.strip()
    if summaries.str.len().lt(100).any():
        raise ValueError("Clean dataframe contains summaries shorter than 100 characters.")

    embedding_text = clean_df["text_for_embedding"].fillna("").astype(str).str.strip()
    if embedding_text.eq("").any():
        raise ValueError("Clean dataframe contains empty text_for_embedding values.")


def _validate_test_set(
    test_set: Any,
    clean_df: pd.DataFrame,
) -> list[dict[str, Any]]:
    if not isinstance(test_set, list):
        raise ValueError("Frozen evaluation set must be a JSON list.")
    if len(test_set) < MIN_TEST_SAMPLES:
        raise ValueError(
            f"Frozen evaluation set must contain at least {MIN_TEST_SAMPLES} samples."
        )

    clean_doc_ids = set(clean_df["paper_id"].astype(str))
    seen_question_ids: set[str] = set()
    validated: list[dict[str, Any]] = []

    for position, sample in enumerate(test_set):
        if not isinstance(sample, dict):
            raise ValueError(f"Test sample at position {position} is not a JSON object.")

        missing_fields = sorted(TEST_REQUIRED_FIELDS - set(sample))
        if missing_fields:
            raise ValueError(
                f"Test sample at position {position} is missing: {missing_fields}"
            )

        question_id = str(sample["id"]).strip()
        if not question_id:
            raise ValueError(f"Test sample at position {position} has an empty id.")
        if question_id in seen_question_ids:
            raise ValueError(f"Duplicate test sample id: {question_id}")
        seen_question_ids.add(question_id)

        for field in ("question_type", "question", "ground_truth"):
            if not str(sample[field]).strip():
                raise ValueError(
                    f"Test sample {question_id} has an empty {field} value."
                )

        doc_ids = sample["ground_truth_doc_ids"]
        if not isinstance(doc_ids, list) or not doc_ids:
            raise ValueError(
                f"Test sample {question_id} must have non-empty ground_truth_doc_ids."
            )
        normalized_doc_ids = [str(doc_id).strip() for doc_id in doc_ids]
        if any(not doc_id for doc_id in normalized_doc_ids):
            raise ValueError(
                f"Test sample {question_id} contains an empty ground-truth document ID."
            )
        missing_doc_ids = sorted(set(normalized_doc_ids) - clean_doc_ids)
        if missing_doc_ids:
            raise ValueError(
                f"Test sample {question_id} references missing clean documents: "
                f"{missing_doc_ids}"
            )

        normalized_sample = dict(sample)
        normalized_sample["id"] = question_id
        normalized_sample["ground_truth_doc_ids"] = normalized_doc_ids
        validated.append(normalized_sample)

    return validated


def _validate_evaluation_summary(
    summary: Mapping[str, Any],
    expected_samples: int,
) -> None:
    missing_metrics = sorted(BASELINE_REQUIRED_METRICS - set(summary))
    if missing_metrics:
        raise ValueError(f"Baseline evaluation is missing metrics: {missing_metrics}")

    try:
        sample_count = int(summary["samples"])
        retrieval_hit_rate = float(summary["retrieval_hit_rate"])
        mean_token_f1 = float(summary["mean_token_f1"])
    except (TypeError, ValueError) as exc:
        raise ValueError("Baseline evaluation metrics must be numeric.") from exc

    if sample_count != expected_samples:
        raise ValueError(
            f"Evaluation processed {sample_count} samples; expected {expected_samples}."
        )
    for name, value in (
        ("retrieval_hit_rate", retrieval_hit_rate),
        ("mean_token_f1", mean_token_f1),
    ):
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"{name} must be in [0, 1], got {value}.")


def _quality_status(report: Mapping[str, Any]) -> str:
    return str(report.get("status", "UNKNOWN")).strip().upper()


def _freshness_passed(report: Mapping[str, Any]) -> bool:
    if "is_fresh" in report:
        return bool(report["is_fresh"])
    status = str(report.get("status", "UNKNOWN")).strip().upper()
    return status in {"PASS", "FRESH"}


def _extract_answer_records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        answers = payload
    elif isinstance(payload, dict) and isinstance(payload.get("answers"), list):
        answers = payload["answers"]
    elif isinstance(payload, dict) and isinstance(payload.get("results"), list):
        answers = payload["results"]
    else:
        raise ValueError("baseline_answers.json must contain a list of answers.")
    if not all(isinstance(answer, dict) for answer in answers):
        raise ValueError("Every baseline answer must be a JSON object.")
    return answers


def _build_demo_answers(
    test_set: list[dict[str, Any]],
    baseline_answers: list[dict[str, Any]],
    limit: int = 4,
) -> list[dict[str, Any]]:
    """Reuse evaluated answers instead of calling the LLM a second time."""
    demos: list[dict[str, Any]] = []
    for position, sample in enumerate(test_set[:limit]):
        answer = baseline_answers[position] if position < len(baseline_answers) else {}
        demos.append(
            {
                **answer,
                "id": sample["id"],
                "question": sample["question"],
                "ground_truth": sample["ground_truth"],
                "ground_truth_doc_ids": sample["ground_truth_doc_ids"],
            }
        )
    return demos


def _validate_output_artifacts(settings: Any) -> None:
    required = [
        settings.paths.raw_api_response,
        settings.paths.raw_records_json,
        settings.paths.clean_csv,
        settings.paths.clean_json,
        settings.paths.embeddings_json,
        settings.paths.eval_testset,
        settings.paths.baseline_metrics,
        settings.paths.baseline_answers,
        settings.paths.quality_dir / "baseline_quality.json",
        settings.paths.freshness_report,
        settings.paths.baseline_report,
        settings.paths.demo_answers,
    ]

    for optional_name in ("chroma_dir", "index_manifest"):
        optional_path = getattr(settings.paths, optional_name, None)
        if optional_path is not None:
            required.append(optional_path)

    _require_paths(required, "Phase 1")


def main() -> None:
    """Run and validate the clean baseline pipeline for Checkpoints C2 and C3."""
    settings = load_settings()
    run_date = now_utc()

    raw_artifacts = [
        settings.paths.raw_api_response,
        settings.paths.raw_records_json,
    ]
    use_cached_snapshot = (
        all(path.exists() for path in raw_artifacts)
        and not settings.refresh_source
    )
    if use_cached_snapshot:
        raw_records = load_raw_records(settings.paths.raw_records_json)
        source_mode = "cached raw snapshot"
    else:
        raw_records = fetch_source_records(settings)
        source_mode = "Crossref API"

    _validate_raw_records(raw_records)
    _require_paths(raw_artifacts, "Crossref ingestion")

    clean_df = build_clean_dataframe(raw_records, run_date=run_date)
    _validate_clean_dataframe(clean_df)
    write_csv(clean_df, settings.paths.clean_csv)
    write_json(settings.paths.clean_json, _dataframe_records(clean_df))

    index = LocalEmbeddingIndex.build(
        clean_df,
        settings=settings,
        embeddings_output_path=settings.paths.embeddings_json,
    )

    reuse_frozen_test_set = (
        settings.paths.eval_testset.exists()
        and not settings.refresh_test_set
    )
    if reuse_frozen_test_set:
        test_set_payload = read_json(settings.paths.eval_testset)
    else:
        test_set_payload = build_test_set(clean_df, settings.paths.eval_testset)

    _require_paths([settings.paths.eval_testset], "Frozen test-set generation")
    test_set = _validate_test_set(test_set_payload, clean_df)
    if not reuse_frozen_test_set:
        write_json(settings.paths.eval_testset, test_set)
    frozen_test_set_sha256 = _sha256(settings.paths.eval_testset)

    evaluation = evaluate_pipeline(
        settings=settings,
        index=index,
        test_set_path=settings.paths.eval_testset,
        metrics_output_path=settings.paths.baseline_metrics,
        answers_output_path=settings.paths.baseline_answers,
    )
    _validate_evaluation_summary(evaluation.summary, len(test_set))
    _require_paths(
        [settings.paths.baseline_metrics, settings.paths.baseline_answers],
        "Baseline evaluation",
    )

    if _sha256(settings.paths.eval_testset) != frozen_test_set_sha256:
        raise RuntimeError("Frozen test set changed during baseline evaluation.")

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
    if _quality_status(quality) != "PASS":
        raise RuntimeError(
            f"Baseline data quality must be PASS, got {_quality_status(quality)}."
        )
    if not _freshness_passed(freshness):
        raise RuntimeError("Baseline freshness check did not pass.")

    source_summary = {
        "source": settings.source_api,
        "source_mode": source_mode,
        "query": settings.source_query,
        "filter": settings.source_filter,
        "raw_records": len(raw_records),
        "clean_records": len(clean_df),
        "evaluation_samples": len(test_set),
        "frozen_test_set_sha256": frozen_test_set_sha256,
        "raw_response_path": str(settings.paths.raw_api_response),
        "raw_records_path": str(settings.paths.raw_records_json),
        "clean_csv_path": str(settings.paths.clean_csv),
        "clean_json_path": str(settings.paths.clean_json),
        "test_set_path": str(settings.paths.eval_testset),
    }
    generate_phase1_report(
        settings.paths.baseline_report,
        source_summary=source_summary,
        metrics=evaluation.summary,
        quality=quality,
        freshness=freshness,
    )

    baseline_answers = _extract_answer_records(
        read_json(settings.paths.baseline_answers)
    )
    if len(baseline_answers) != len(test_set):
        raise RuntimeError(
            f"Baseline answers contain {len(baseline_answers)} records; "
            f"expected {len(test_set)}."
        )
    demo_answers = _build_demo_answers(test_set, baseline_answers)
    write_json(settings.paths.demo_answers, demo_answers)

    if _sha256(settings.paths.eval_testset) != frozen_test_set_sha256:
        raise RuntimeError("Frozen test set changed after report generation.")
    _validate_output_artifacts(settings)

    print("Phase 1 completed and passed Checkpoints C2/C3 validation.")
    print(f"Raw records: {len(raw_records)}")
    print(f"Clean records: {len(clean_df)}")
    print(f"Evaluation samples: {evaluation.summary['samples']}")
    print(f"Retrieval hit rate: {evaluation.summary['retrieval_hit_rate']:.4f}")
    print(f"Mean token F1: {evaluation.summary['mean_token_f1']:.4f}")
    print(f"Quality status: {_quality_status(quality)}")
    print("Freshness status: PASS")
    print(f"Frozen test set SHA-256: {frozen_test_set_sha256}")
    print(f"Report: {settings.paths.baseline_report}")


if __name__ == "__main__":
    main()

