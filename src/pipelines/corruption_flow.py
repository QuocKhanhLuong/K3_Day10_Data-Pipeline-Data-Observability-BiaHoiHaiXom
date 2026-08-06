from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

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


RAG_METRICS = (
    "retrieval_hit_rate",
    "mean_token_f1",
    "judge_accuracy",
    "mean_judge_score",
)
REQUIRED_RAG_METRICS = ("retrieval_hit_rate", "mean_token_f1")
REPORT_SECTION_START = "<!-- C4_THREE_STATE_SUMMARY_START -->"
REPORT_SECTION_END = "<!-- C4_THREE_STATE_SUMMARY_END -->"


def _dataframe_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    return json.loads(df.to_json(orient="records", date_format="iso"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _metric_payload(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    summary = payload.get("summary")
    return summary if isinstance(summary, Mapping) else payload


def _metric_value(payload: Mapping[str, Any], metric: str) -> float | None:
    value = _metric_payload(payload).get(metric)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_metric(payload: Mapping[str, Any], metric: str) -> str:
    value = _metric_value(payload, metric)
    return "N/A" if value is None else f"{value:.4f}"


def _find_named_value(payload: Any, target_key: str) -> Any:
    """Find a named observability signal in nested report dictionaries."""
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            if str(key).lower() == target_key.lower():
                return value
        for value in payload.values():
            found = _find_named_value(value, target_key)
            if found is not None:
                return found
    elif isinstance(payload, list):
        for value in payload:
            found = _find_named_value(value, target_key)
            if found is not None:
                return found
    return None


def _display_signal(payload: Mapping[str, Any], signal: str) -> str:
    value = _find_named_value(payload, signal)
    if isinstance(value, Mapping):
        for key in ("status", "result", "passed", "value", "score"):
            if key in value:
                return str(value[key])
        return json.dumps(dict(value), ensure_ascii=False)
    if value is None:
        return "N/A"
    return str(value)


def _status(payload: Mapping[str, Any]) -> str:
    value = _find_named_value(payload, "status")
    if value is None:
        return "UNKNOWN"
    return str(value).strip().upper()


def _ensure_baseline(settings: Any) -> None:
    required = (
        settings.paths.clean_json,
        settings.paths.raw_records_json,
        settings.paths.eval_testset,
        settings.paths.baseline_metrics,
    )
    if not all(path.exists() for path in required):
        print("Baseline artifacts are incomplete; running Phase 1 first.")
        run_phase1()

    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise RuntimeError(
            "Phase 1 did not create all required baseline artifacts: "
            + ", ".join(missing)
        )


def _append_three_state_summary(
    report_path: Path,
    *,
    baseline_metrics: Mapping[str, Any],
    corrupted_metrics: Mapping[str, Any],
    repaired_metrics: Mapping[str, Any],
    baseline_quality: Mapping[str, Any],
    corrupted_quality: Mapping[str, Any],
    repaired_quality: Mapping[str, Any],
    baseline_freshness: Mapping[str, Any],
    corrupted_freshness: Mapping[str, Any],
    repaired_freshness: Mapping[str, Any],
    frozen_test_set_sha256: str,
) -> None:
    """Guarantee that the report contains the C4 three-state comparison."""
    metric_rows = [
        (
            f"| `{metric}` | {_format_metric(baseline_metrics, metric)} "
            f"| {_format_metric(corrupted_metrics, metric)} "
            f"| {_format_metric(repaired_metrics, metric)} |"
        )
        for metric in RAG_METRICS
    ]

    observability_rows = []
    for signal in ("status", "completeness", "uniqueness"):
        observability_rows.append(
            f"| `{signal}` | {_display_signal(baseline_quality, signal)} "
            f"| {_display_signal(corrupted_quality, signal)} "
            f"| {_display_signal(repaired_quality, signal)} |"
        )
    observability_rows.append(
        f"| `freshness` | {_display_signal(baseline_freshness, 'status')} "
        f"| {_display_signal(corrupted_freshness, 'status')} "
        f"| {_display_signal(repaired_freshness, 'status')} |"
    )

    section_lines = [
        REPORT_SECTION_START,
        "## Checkpoint C4 - Three-state comparison",
        "",
        "All three states were evaluated with the same frozen test set.",
        f"Frozen test set SHA-256: `{frozen_test_set_sha256}`.",
        "",
        "### RAG metrics",
        "",
        "| Metric | Baseline | Corrupted | Repaired |",
        "|---|---:|---:|---:|",
        *metric_rows,
        "",
        "### Data observability",
        "",
        "| Signal | Baseline | Corrupted | Repaired |",
        "|---|---|---|---|",
        *observability_rows,
        "",
        REPORT_SECTION_END,
    ]
    section = "\n".join(section_lines)

    report_path.parent.mkdir(parents=True, exist_ok=True)
    existing = report_path.read_text(encoding="utf-8") if report_path.exists() else ""
    if REPORT_SECTION_START in existing:
        prefix = existing.split(REPORT_SECTION_START, maxsplit=1)[0].rstrip()
        suffix = ""
        if REPORT_SECTION_END in existing:
            suffix = existing.split(REPORT_SECTION_END, maxsplit=1)[1].strip()
        parts = [part for part in (prefix, section, suffix) if part]
        updated = "\n\n".join(parts) + "\n"
    else:
        updated = existing.rstrip() + "\n\n" + section + "\n"
    report_path.write_text(updated.lstrip(), encoding="utf-8")


def _validate_c4_results(
    *,
    baseline_metrics: Mapping[str, Any],
    corrupted_metrics: Mapping[str, Any],
    repaired_metrics: Mapping[str, Any],
    baseline_quality: Mapping[str, Any],
    corrupted_quality: Mapping[str, Any],
    repaired_quality: Mapping[str, Any],
) -> None:
    errors: list[str] = []

    if _status(baseline_quality) != "PASS":
        errors.append(
            f"baseline data quality must be PASS, got {_status(baseline_quality)}"
        )
    if _status(corrupted_quality) != "FAIL":
        errors.append(
            f"corrupted data quality must be FAIL, got {_status(corrupted_quality)}"
        )
    if _status(repaired_quality) != "PASS":
        errors.append(
            f"repaired data quality must be PASS, got {_status(repaired_quality)}"
        )

    comparable: list[tuple[str, float, float, float]] = []
    for metric in REQUIRED_RAG_METRICS:
        baseline = _metric_value(baseline_metrics, metric)
        corrupted = _metric_value(corrupted_metrics, metric)
        repaired = _metric_value(repaired_metrics, metric)
        if baseline is not None and corrupted is not None and repaired is not None:
            comparable.append((metric, baseline, corrupted, repaired))

    if not comparable:
        errors.append("no required RAG metrics were available for three-state comparison")
    else:
        if not any(corrupted < baseline for _, baseline, corrupted, _ in comparable):
            errors.append(
                "corruption did not reduce retrieval_hit_rate or mean_token_f1"
            )
        if not any(repaired > corrupted for _, _, corrupted, repaired in comparable):
            errors.append(
                "repair did not improve retrieval_hit_rate or mean_token_f1"
            )

    if errors:
        formatted = "\n- ".join(errors)
        raise RuntimeError(f"Checkpoint C4 validation failed:\n- {formatted}")


def _validate_output_artifacts(settings: Any) -> None:
    required = (
        settings.paths.corrupted_clean_csv,
        settings.paths.corrupted_clean_json,
        settings.paths.corruption_log,
        settings.paths.corrupted_metrics,
        settings.paths.corrupted_answers,
        settings.paths.repaired_clean_csv,
        settings.paths.repaired_clean_json,
        settings.paths.repaired_metrics,
        settings.paths.repaired_answers,
        settings.paths.comparison_report,
    )
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise RuntimeError("Corruption flow did not create: " + ", ".join(missing))


def main() -> None:
    """Run corruption, impact evaluation, raw-snapshot repair, and comparison."""
    settings = load_settings()
    _ensure_baseline(settings)

    frozen_test_set_sha256 = _sha256(settings.paths.eval_testset)
    baseline_metrics = read_json(settings.paths.baseline_metrics)
    clean_payload = read_json(settings.paths.clean_json)
    clean_df = pd.DataFrame(clean_payload)
    if clean_df.empty:
        raise RuntimeError("Baseline cleaned dataset is empty.")

    baseline_quality = run_data_quality_checks(
        clean_df,
        settings=settings,
        report_name="baseline_quality.json",
    )
    baseline_freshness = build_freshness_report(
        clean_df,
        settings=settings,
        report_path=settings.paths.quality_dir / "freshness_baseline.json",
    )

    corrupted_df = corrupt_clean_dataframe(
        clean_df,
        output_log_path=settings.paths.corruption_log,
        test_set_path=settings.paths.eval_testset,
        output_csv_path=None,
    )
    write_csv(corrupted_df, settings.paths.corrupted_clean_csv)
    write_json(settings.paths.corrupted_clean_json, _dataframe_records(corrupted_df))

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

    # Repair must use the C2 raw snapshot; do not fetch Crossref again here.
    raw_records = load_raw_records(settings.paths.raw_records_json)
    repaired_df = build_clean_dataframe(raw_records, run_date=now_utc())
    if repaired_df.empty:
        raise RuntimeError("Repair from raw records produced zero rows.")
    write_csv(repaired_df, settings.paths.repaired_clean_csv)
    write_json(settings.paths.repaired_clean_json, _dataframe_records(repaired_df))

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

    if _sha256(settings.paths.eval_testset) != frozen_test_set_sha256:
        raise RuntimeError("Frozen test set changed during the corruption flow.")

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
    _append_three_state_summary(
        settings.paths.comparison_report,
        baseline_metrics=baseline_metrics,
        corrupted_metrics=corrupted_evaluation.summary,
        repaired_metrics=repaired_evaluation.summary,
        baseline_quality=baseline_quality,
        corrupted_quality=corrupted_quality,
        repaired_quality=repaired_quality,
        baseline_freshness=baseline_freshness,
        corrupted_freshness=corrupted_freshness,
        repaired_freshness=repaired_freshness,
        frozen_test_set_sha256=frozen_test_set_sha256,
    )

    _validate_output_artifacts(settings)
    _validate_c4_results(
        baseline_metrics=baseline_metrics,
        corrupted_metrics=corrupted_evaluation.summary,
        repaired_metrics=repaired_evaluation.summary,
        baseline_quality=baseline_quality,
        corrupted_quality=corrupted_quality,
        repaired_quality=repaired_quality,
    )

    print("Corruption flow completed and passed Checkpoint C4 validation.")
    for metric in RAG_METRICS:
        print(
            f"{metric}: "
            f"baseline={_format_metric(baseline_metrics, metric)}, "
            f"corrupted={_format_metric(corrupted_evaluation.summary, metric)}, "
            f"repaired={_format_metric(repaired_evaluation.summary, metric)}"
        )
    print(f"Baseline quality: {_status(baseline_quality)}")
    print(f"Corrupted quality: {_status(corrupted_quality)}")
    print(f"Repaired quality: {_status(repaired_quality)}")
    print(f"Report: {settings.paths.comparison_report}")


if __name__ == "__main__":
    main()

