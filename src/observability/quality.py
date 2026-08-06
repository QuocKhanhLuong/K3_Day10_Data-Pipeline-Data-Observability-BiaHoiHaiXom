from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from core.config import Settings
from core.utils import write_json


def _check(name: str, passed: bool, observed: Any, expectation: str) -> dict[str, Any]:
    return {
        "name": name,
        "passed": bool(passed),
        "observed": observed,
        "expectation": expectation,
    }


def run_data_quality_checks(df: pd.DataFrame, settings: Settings, report_name: str) -> dict[str, Any]:
    """Run deterministic schema, completeness, uniqueness, and freshness checks."""
    required_columns = {
        "paper_id",
        "title",
        "summary",
        "published",
        "age_days",
        "text_for_embedding",
    }
    missing_columns = sorted(required_columns - set(df.columns))
    total_rows = int(len(df))
    minimum_rows = min(10, max(3, settings.max_results // 2))

    if missing_columns:
        checks = [
            _check(
                "required_columns",
                False,
                missing_columns,
                "All required cleaned-data columns must be present.",
            )
        ]
    else:
        paper_ids = df["paper_id"].fillna("").astype(str).str.strip()
        titles = df["title"].fillna("").astype(str).str.strip()
        summaries = df["summary"].fillna("").astype(str).str.strip()
        embedding_text = df["text_for_embedding"].fillna("").astype(str).str.strip()
        age_days = pd.to_numeric(df["age_days"], errors="coerce")

        duplicate_ids = int(paper_ids[paper_ids != ""].duplicated().sum())
        short_summaries = int((summaries.str.len() < 80).sum())
        stale_mask = age_days.isna() | (age_days > settings.freshness_threshold_days)
        stale_rows = int(stale_mask.sum())
        stale_ratio = stale_rows / total_rows if total_rows else 1.0

        checks = [
            _check(
                "row_count",
                total_rows >= minimum_rows,
                total_rows,
                f"At least {minimum_rows} cleaned records are required.",
            ),
            _check(
                "paper_id_completeness",
                bool((paper_ids != "").all()),
                int((paper_ids == "").sum()),
                "paper_id must be non-empty for every row.",
            ),
            _check(
                "paper_id_uniqueness",
                duplicate_ids == 0,
                duplicate_ids,
                "paper_id must be unique.",
            ),
            _check(
                "title_completeness",
                bool((titles != "").all()),
                int((titles == "").sum()),
                "title must be non-empty for every row.",
            ),
            _check(
                "summary_min_length",
                short_summaries == 0,
                short_summaries,
                "Every summary must contain at least 80 characters.",
            ),
            _check(
                "embedding_text_completeness",
                bool((embedding_text != "").all()),
                int((embedding_text == "").sum()),
                "text_for_embedding must be non-empty for every row.",
            ),
            _check(
                "freshness_ratio",
                stale_ratio <= 0.20,
                round(stale_ratio, 4),
                "At most 20% of records may exceed the freshness threshold.",
            ),
        ]

    failed_checks = [item["name"] for item in checks if not item["passed"]]
    report = {
        "report_name": report_name,
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "pass" if not failed_checks else "fail",
        "total_rows": total_rows,
        "freshness_threshold_days": settings.freshness_threshold_days,
        "checks": checks,
        "failed_checks": failed_checks,
    }

    report_path = settings.paths.quality_dir / report_name
    if report_path.suffix.lower() != ".json":
        report_path = report_path.with_suffix(".json")
    write_json(report_path, report)
    return report


def build_freshness_report(df: pd.DataFrame, settings: Settings, report_path: Path) -> dict[str, Any]:
    """Summarize publication recency and stale-row distribution."""
    published = pd.to_datetime(df.get("published"), errors="coerce", utc=True)
    if "age_days" in df.columns:
        age_days = pd.to_numeric(df["age_days"], errors="coerce")
    else:
        now = pd.Timestamp.now(tz="UTC").normalize()
        age_days = (now - published.dt.normalize()).dt.days

    total_rows = int(len(df))
    valid_published = published.dropna()
    stale_mask = age_days.isna() | (age_days > settings.freshness_threshold_days)
    stale_rows = int(stale_mask.sum()) if total_rows else 0
    stale_ratio = stale_rows / total_rows if total_rows else 1.0
    latest_age_days = int(age_days.min()) if total_rows and age_days.notna().any() else None

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "latest_published": (
            valid_published.max().date().isoformat() if not valid_published.empty else None
        ),
        "oldest_published": (
            valid_published.min().date().isoformat() if not valid_published.empty else None
        ),
        "latest_age_days": latest_age_days,
        "stale_rows": stale_rows,
        "stale_ratio": round(stale_ratio, 4),
        "total_rows": total_rows,
        "freshness_threshold_days": settings.freshness_threshold_days,
        "is_fresh": bool(
            total_rows
            and latest_age_days is not None
            and latest_age_days <= settings.freshness_threshold_days
            and stale_ratio <= 0.20
        ),
    }
    write_json(report_path, report)
    return report
