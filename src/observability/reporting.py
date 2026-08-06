from __future__ import annotations

from pathlib import Path
from typing import Any

from core.utils import write_text


CORE_METRICS = (
    "retrieval_hit_rate",
    "mean_token_f1",
    "judge_accuracy",
    "mean_judge_score",
)


def _format_value(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.4f}"
    if value is None:
        return "n/a"
    return str(value)


def _metric_table(metrics_by_state: dict[str, dict[str, Any]]) -> list[str]:
    headers = ["Metric", *metrics_by_state.keys()]
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join(["---"] * len(headers)) + "|",
    ]
    for metric in CORE_METRICS:
        lines.append(
            "| "
            + " | ".join(
                [metric]
                + [_format_value(metrics.get(metric)) for metrics in metrics_by_state.values()]
            )
            + " |"
        )
    return lines


def _quality_lines(quality: dict[str, Any]) -> list[str]:
    checks = quality.get("checks") or []
    lines = [
        f"- Overall status: **{str(quality.get('status', 'unknown')).upper()}**",
        f"- Total rows: {_format_value(quality.get('total_rows'))}",
    ]
    if checks:
        lines.extend(
            f"- `{check.get('name')}`: {'PASS' if check.get('passed') else 'FAIL'} "
            f"(observed: {_format_value(check.get('observed'))})"
            for check in checks
        )
    return lines


def _freshness_lines(freshness: dict[str, Any]) -> list[str]:
    return [
        f"- Status: **{'FRESH' if freshness.get('is_fresh') else 'STALE'}**",
        f"- Latest publication: {_format_value(freshness.get('latest_published'))}",
        f"- Oldest publication: {_format_value(freshness.get('oldest_published'))}",
        f"- Stale rows: {_format_value(freshness.get('stale_rows'))}/{_format_value(freshness.get('total_rows'))}",
        f"- Stale ratio: {_format_value(freshness.get('stale_ratio'))}",
    ]


def generate_phase1_report(
    report_path: Path,
    source_summary: dict[str, Any],
    metrics: dict[str, Any],
    quality: dict[str, Any],
    freshness: dict[str, Any],
) -> None:
    """Write a reproducible baseline pipeline report."""
    source_rows = [
        f"- Source: {_format_value(source_summary.get('source'))}",
        f"- Query: `{_format_value(source_summary.get('query'))}`",
        f"- Filter: `{_format_value(source_summary.get('filter'))}`",
        f"- Raw records: {_format_value(source_summary.get('raw_records'))}",
        f"- Clean records: {_format_value(source_summary.get('clean_records'))}",
        f"- Evaluation samples: {_format_value(metrics.get('samples'))}",
    ]

    lines = [
        "# Phase 1 — Baseline Data Pipeline Report",
        "",
        "## Source and artifacts",
        "",
        *source_rows,
        "",
        "## RAG evaluation",
        "",
        *_metric_table({"Baseline": metrics}),
        "",
        f"- Ragas: `{_format_value(metrics.get('ragas'))}`",
        "",
        "## Data quality",
        "",
        *_quality_lines(quality),
        "",
        "## Freshness",
        "",
        *_freshness_lines(freshness),
        "",
        "## Interpretation",
        "",
        (
            "The baseline is ready for corruption testing."
            if quality.get("status") == "pass" and freshness.get("is_fresh")
            else "The baseline has failed checks; resolve them before using it as the comparison reference."
        ),
        "",
    ]
    write_text(report_path, "\n".join(lines))


def generate_corruption_report(
    report_path: Path,
    baseline_metrics: dict[str, Any],
    corrupted_metrics: dict[str, Any],
    repaired_metrics: dict[str, Any],
    corrupted_quality: dict[str, Any],
    repaired_quality: dict[str, Any],
    corrupted_freshness: dict[str, Any],
    repaired_freshness: dict[str, Any],
) -> None:
    """Write the baseline/corrupted/repaired comparison report."""
    delta_lines: list[str] = []
    for metric in CORE_METRICS:
        baseline = baseline_metrics.get(metric)
        corrupted = corrupted_metrics.get(metric)
        repaired = repaired_metrics.get(metric)
        if all(isinstance(value, (int, float)) for value in (baseline, corrupted, repaired)):
            delta_lines.append(
                f"- `{metric}`: corruption delta {corrupted - baseline:+.4f}; "
                f"repair delta vs corrupted {repaired - corrupted:+.4f}; "
                f"remaining gap vs baseline {repaired - baseline:+.4f}."
            )

    lines = [
        "# Corruption and Repair Comparison",
        "",
        "## Metric comparison",
        "",
        *_metric_table(
            {
                "Baseline": baseline_metrics,
                "Corrupted": corrupted_metrics,
                "Repaired": repaired_metrics,
            }
        ),
        "",
        "## Metric deltas",
        "",
        *(delta_lines or ["- Numeric deltas were unavailable."]),
        "",
        "## Corrupted data quality",
        "",
        *_quality_lines(corrupted_quality),
        "",
        "## Corrupted freshness",
        "",
        *_freshness_lines(corrupted_freshness),
        "",
        "## Repaired data quality",
        "",
        *_quality_lines(repaired_quality),
        "",
        "## Repaired freshness",
        "",
        *_freshness_lines(repaired_freshness),
        "",
        "## Conclusion",
        "",
        (
            "The observability checks detected the corrupted state, and rebuilding from the raw snapshot "
            "restored the dataset and evaluation pipeline."
            if corrupted_quality.get("status") == "fail"
            and repaired_quality.get("status") == "pass"
            else "Review the failed checks and metric deltas before claiming successful recovery."
        ),
        "",
    ]
    write_text(report_path, "\n".join(lines))
