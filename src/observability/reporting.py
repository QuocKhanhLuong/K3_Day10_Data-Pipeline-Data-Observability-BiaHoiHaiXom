from __future__ import annotations

from numbers import Real
from pathlib import Path
from typing import Any

from core.utils import write_text


CORE_METRICS = (
    "retrieval_hit_rate",
    "mean_token_f1",
    "judge_accuracy",
    "mean_judge_score",
)
OBSERVABILITY_STATES = ("Baseline", "Corrupted", "Repaired")


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


def _missing_metric_lines(metrics_by_state: dict[str, dict[str, Any]]) -> list[str]:
    warnings = []
    for state, metrics in metrics_by_state.items():
        missing = [metric for metric in CORE_METRICS if metrics.get(metric) is None]
        if missing:
            warnings.append(f"- {state}: {', '.join(f'`{metric}`' for metric in missing)}")
    return warnings or ["- None."]


def _quality_lines(quality: dict[str, Any]) -> list[str]:
    checks = quality.get("checks") or []
    lines = [
        f"- Overall status: **{str(quality.get('status', 'unknown')).upper()}**",
        f"- Total rows: {_format_value(quality.get('total_rows'))}",
    ]
    if checks:
        lines.extend(
            f"- `{check.get('name')}`: {'PASS' if check.get('passed') is True else 'FAIL'} "
            f"(observed: {_format_value(check.get('observed'))}; "
            f"expectation: {_format_value(check.get('expectation'))})"
            for check in checks
        )
    else:
        lines.append("- Checks: n/a")
    return lines


def _failed_check_lines(quality: dict[str, Any]) -> list[str]:
    failed = quality.get("failed_checks")
    if failed is None:
        failed = [
            check.get("name", "unnamed_check")
            for check in quality.get("checks") or []
            if check.get("passed") is False
        ]
    return [f"- `{name}`" for name in failed] or ["- None."]


def _freshness_status(freshness: dict[str, Any]) -> str:
    is_fresh = freshness.get("is_fresh")
    if is_fresh is True:
        return "FRESH"
    if is_fresh is False:
        return "STALE"
    return "UNKNOWN"


def _freshness_lines(freshness: dict[str, Any]) -> list[str]:
    return [
        f"- Status: **{_freshness_status(freshness)}**",
        f"- Latest publication: {_format_value(freshness.get('latest_published'))}",
        f"- Oldest publication: {_format_value(freshness.get('oldest_published'))}",
        f"- Latest age (days): {_format_value(freshness.get('latest_age_days'))}",
        f"- Future rows: {_format_value(freshness.get('future_rows'))}",
        f"- Invalid publication rows: {_format_value(freshness.get('invalid_published_rows'))}",
        f"- Stale rows: {_format_value(freshness.get('stale_rows'))}",
        f"- Stale ratio: {_format_value(freshness.get('stale_ratio'))}",
        f"- Total rows: {_format_value(freshness.get('total_rows'))}",
    ]


def generate_phase1_report(
    report_path: Path,
    source_summary: dict[str, Any],
    metrics: dict[str, Any],
    quality: dict[str, Any],
    freshness: dict[str, Any],
) -> None:
    """Write a baseline report whose conclusion follows the supplied artifacts."""
    source_rows = [
        f"- Source: {_format_value(source_summary.get('source'))}",
        f"- Source mode: {_format_value(source_summary.get('source_mode'))}",
        f"- Query: `{_format_value(source_summary.get('query'))}`",
        f"- Filter: `{_format_value(source_summary.get('filter'))}`",
        f"- Raw records: {_format_value(source_summary.get('raw_records'))}",
        f"- Clean records: {_format_value(source_summary.get('clean_records'))}",
        f"- Evaluation samples: {_format_value(metrics.get('samples'))}",
        f"- Raw response artifact: {_format_value(source_summary.get('raw_response_path'))}",
        f"- Raw records artifact: {_format_value(source_summary.get('raw_records_path'))}",
        f"- Clean CSV artifact: {_format_value(source_summary.get('clean_csv_path'))}",
        f"- Clean JSON artifact: {_format_value(source_summary.get('clean_json_path'))}",
    ]
    metrics_by_state = {"Baseline": metrics}
    baseline_ready = quality.get("status") == "pass" and freshness.get("is_fresh") is True

    lines = [
        "# Phase 1 — Baseline Data Pipeline Report",
        "",
        "## Source and artifacts",
        "",
        *source_rows,
        "",
        "## Baseline RAG metrics",
        "",
        *_metric_table(metrics_by_state),
        "",
        "### Missing metric warnings",
        "",
        *_missing_metric_lines(metrics_by_state),
        "",
        f"- Ragas: `{_format_value(metrics.get('ragas'))}`",
        "",
        "## Baseline data quality",
        "",
        *_quality_lines(quality),
        "",
        "### Failed checks",
        "",
        *_failed_check_lines(quality),
        "",
        "## Baseline freshness",
        "",
        *_freshness_lines(freshness),
        "",
        "## Conclusion",
        "",
        (
            "The baseline quality and freshness artifacts pass, so it is ready for corruption testing."
            if baseline_ready
            else "The baseline is not ready for corruption testing because quality or freshness requirements are not satisfied."
        ),
        "",
    ]
    write_text(report_path, "\n".join(lines))


def _metric_gap_lines(
    baseline_metrics: dict[str, Any],
    repaired_metrics: dict[str, Any],
) -> tuple[list[str], bool]:
    lines: list[str] = []
    fully_demonstrated = True
    for metric in CORE_METRICS:
        baseline = baseline_metrics.get(metric)
        repaired = repaired_metrics.get(metric)
        if not isinstance(baseline, Real) or isinstance(baseline, bool):
            lines.append(f"- `{metric}`: baseline or repaired value is missing; recovery cannot be compared.")
            fully_demonstrated = False
            continue
        if not isinstance(repaired, Real) or isinstance(repaired, bool):
            lines.append(f"- `{metric}`: baseline or repaired value is missing; recovery cannot be compared.")
            fully_demonstrated = False
            continue
        gap = float(repaired) - float(baseline)
        lines.append(f"- `{metric}`: repaired minus baseline {gap:+.4f}.")
        if gap < 0:
            fully_demonstrated = False
    return lines, fully_demonstrated


def generate_corruption_report(
    report_path: Path,
    baseline_metrics: dict[str, Any],
    corrupted_metrics: dict[str, Any],
    repaired_metrics: dict[str, Any],
    corrupted_quality: dict[str, Any],
    repaired_quality: dict[str, Any],
    corrupted_freshness: dict[str, Any],
    repaired_freshness: dict[str, Any],
    baseline_quality: dict[str, Any] | None = None,
    baseline_freshness: dict[str, Any] | None = None,
) -> None:
    """Write a backward-compatible three-state corruption and repair report."""
    metrics_by_state = {
        "Baseline": baseline_metrics,
        "Corrupted": corrupted_metrics,
        "Repaired": repaired_metrics,
    }
    quality_by_state = {
        "Baseline": baseline_quality or {},
        "Corrupted": corrupted_quality,
        "Repaired": repaired_quality,
    }
    freshness_by_state = {
        "Baseline": baseline_freshness or {},
        "Corrupted": corrupted_freshness,
        "Repaired": repaired_freshness,
    }

    delta_lines: list[str] = []
    for metric in CORE_METRICS:
        baseline = baseline_metrics.get(metric)
        corrupted = corrupted_metrics.get(metric)
        repaired = repaired_metrics.get(metric)
        if all(isinstance(value, Real) and not isinstance(value, bool) for value in (baseline, corrupted, repaired)):
            delta_lines.append(
                f"- `{metric}`: corruption delta {float(corrupted) - float(baseline):+.4f}; "
                f"repair delta vs corrupted {float(repaired) - float(corrupted):+.4f}; "
                f"remaining gap vs baseline {float(repaired) - float(baseline):+.4f}."
            )

    gap_lines, rag_recovery_demonstrated = _metric_gap_lines(baseline_metrics, repaired_metrics)
    data_recovered = (
        corrupted_quality.get("status") == "fail"
        and repaired_quality.get("status") == "pass"
        and repaired_freshness.get("is_fresh") is True
    )
    if data_recovered and rag_recovery_demonstrated:
        conclusion = "Data quality, freshness, and measured RAG performance recovered to the baseline level."
    elif data_recovered:
        conclusion = (
            "Data quality and freshness recovered, but RAG performance recovery is not fully demonstrated; "
            "review the remaining metric gaps above."
        )
    else:
        conclusion = "Successful recovery is not demonstrated because the corrupted/repaired quality and freshness conditions are not all satisfied."

    lines = [
        "# Corruption and Repair Comparison",
        "",
        "## RAG metric comparison",
        "",
        *_metric_table(metrics_by_state),
        "",
        "### Missing metric warnings",
        "",
        *_missing_metric_lines(metrics_by_state),
        "",
        "## Metric deltas",
        "",
        *(delta_lines or ["- Numeric deltas were unavailable."]),
        "",
        "## Repaired metric gaps versus baseline",
        "",
        *gap_lines,
        "",
    ]
    for state in OBSERVABILITY_STATES:
        lines.extend(
            [
                f"## {state} data quality",
                "",
                *_quality_lines(quality_by_state[state]),
                "",
                "### Failed checks",
                "",
                *_failed_check_lines(quality_by_state[state]),
                "",
                f"## {state} freshness",
                "",
                *_freshness_lines(freshness_by_state[state]),
                "",
            ]
        )
    lines.extend(["## Conclusion", "", conclusion, ""])
    write_text(report_path, "\n".join(lines))
