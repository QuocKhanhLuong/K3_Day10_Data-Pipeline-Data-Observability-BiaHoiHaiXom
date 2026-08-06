from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from core.config import Settings
from core.utils import write_json


MIN_SUMMARY_CHARS = 100
MAX_STALE_RATIO = 0.20
REQUIRED_COLUMNS = {
    "paper_id",
    "title",
    "summary",
    "published",
    "authors_joined",
    "categories_joined",
    "age_days",
    "text_for_embedding",
    "abs_url",
    "pdf_url",
}


def _check(name: str, passed: bool, observed: Any, expectation: str) -> dict[str, Any]:
    return {
        "name": name,
        "passed": bool(passed),
        "observed": observed,
        "expectation": expectation,
    }


def _text_column(df: pd.DataFrame, name: str) -> pd.Series:
    """Return a normalized text view without modifying the input dataframe."""
    if name not in df.columns:
        return pd.Series("", index=df.index, dtype="string")
    return df[name].fillna("").astype(str).str.strip()


def _published_dates(df: pd.DataFrame) -> pd.Series:
    if "published" not in df.columns:
        return pd.Series(pd.NaT, index=df.index, dtype="datetime64[ns, UTC]")
    return pd.to_datetime(df["published"], errors="coerce", utc=True)


def run_data_quality_checks(
    df: pd.DataFrame,
    settings: Settings,
    report_name: str,
) -> dict[str, Any]:
    """Run deterministic schema, completeness, validity, and freshness checks."""
    total_rows = int(len(df))
    missing_columns = sorted(REQUIRED_COLUMNS - set(df.columns))
    paper_ids = _text_column(df, "paper_id")
    titles = _text_column(df, "title")
    summaries = _text_column(df, "summary")
    authors = _text_column(df, "authors_joined")
    categories = _text_column(df, "categories_joined")
    embedding_text = _text_column(df, "text_for_embedding")
    published = _published_dates(df)
    today_utc = pd.Timestamp.now(tz="UTC").normalize()
    future_mask = published.notna() & (published.dt.normalize() > today_utc)

    if "age_days" in df.columns:
        age_days = pd.to_numeric(df["age_days"], errors="coerce")
    else:
        age_days = pd.Series(float("nan"), index=df.index, dtype="float64")

    duplicate_ids = int(paper_ids[paper_ids != ""].duplicated().sum())
    invalid_published = int(published.isna().sum())
    future_dates = int(future_mask.sum())
    non_numeric_age = int(age_days.isna().sum())
    negative_age = int((age_days.dropna() < 0).sum())
    expected_embedding = (
        "Title: " + titles + " | Authors: " + authors + " | Summary: " + summaries
    )
    malformed_embedding = int((embedding_text != expected_embedding).sum())
    stale_mask = (
        published.isna()
        | future_mask
        | age_days.isna()
        | (age_days > settings.freshness_threshold_days)
    )
    stale_rows = int(stale_mask.sum())
    stale_ratio = stale_rows / total_rows if total_rows else 1.0

    checks = [
        _check("dataset_not_empty", total_rows > 0, total_rows, "Dataset must contain at least one row."),
        _check(
            "required_columns",
            not missing_columns,
            missing_columns,
            "All required cleaned-data columns must be present; extra columns are allowed.",
        ),
        _check(
            "paper_id_completeness",
            total_rows > 0 and bool((paper_ids != "").all()),
            int((paper_ids == "").sum()),
            "paper_id must be non-empty for every row.",
        ),
        _check("paper_id_uniqueness", duplicate_ids == 0, duplicate_ids, "paper_id must be unique."),
        _check(
            "title_completeness",
            total_rows > 0 and bool((titles != "").all()),
            int((titles == "").sum()),
            "title must be non-empty for every row.",
        ),
        _check(
            "summary_completeness",
            total_rows > 0 and bool((summaries != "").all()),
            int((summaries == "").sum()),
            "summary must be non-empty for every row.",
        ),
        _check(
            "summary_min_length",
            total_rows > 0 and int((summaries.str.len() < MIN_SUMMARY_CHARS).sum()) == 0,
            int((summaries.str.len() < MIN_SUMMARY_CHARS).sum()),
            f"Every summary must contain at least {MIN_SUMMARY_CHARS} characters.",
        ),
        _check(
            "published_date_parseable",
            total_rows > 0 and invalid_published == 0,
            invalid_published,
            "published must be a parseable date for every row.",
        ),
        _check(
            "future_published_dates",
            future_dates == 0,
            future_dates,
            "published must not be later than the current UTC date.",
        ),
        _check(
            "age_days_numeric",
            total_rows > 0 and non_numeric_age == 0,
            non_numeric_age,
            "age_days must be numeric for every row.",
        ),
        _check(
            "age_days_non_negative",
            total_rows > 0 and negative_age == 0,
            negative_age,
            "age_days must be greater than or equal to zero.",
        ),
        _check(
            "authors_joined_completeness",
            total_rows > 0 and bool((authors != "").all()),
            int((authors == "").sum()),
            "authors_joined must be non-empty for every row.",
        ),
        _check(
            "categories_joined_completeness",
            total_rows > 0 and bool((categories != "").all()),
            int((categories == "").sum()),
            "categories_joined must be non-empty for every row.",
        ),
        _check(
            "embedding_text_completeness",
            total_rows > 0 and bool((embedding_text != "").all()),
            int((embedding_text == "").sum()),
            "text_for_embedding must be non-empty for every row.",
        ),
        _check(
            "embedding_text_canonical_format",
            total_rows > 0 and malformed_embedding == 0,
            malformed_embedding,
            "text_for_embedding must equal 'Title: {title} | Authors: {authors_joined} | Summary: {summary}'.",
        ),
        _check(
            "freshness_ratio",
            total_rows > 0 and stale_ratio <= MAX_STALE_RATIO,
            round(stale_ratio, 4),
            f"At most {MAX_STALE_RATIO:.0%} of records may be stale or have invalid dates.",
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


def build_freshness_report(
    df: pd.DataFrame,
    settings: Settings,
    report_path: Path,
) -> dict[str, Any]:
    """Summarize publication recency while treating invalid and future dates as stale."""
    published = _published_dates(df)
    total_rows = int(len(df))
    today_utc = pd.Timestamp.now(tz="UTC").normalize()
    valid_mask = published.notna()
    future_mask = valid_mask & (published.dt.normalize() > today_utc)
    invalid_published_rows = int((~valid_mask).sum())
    future_rows = int(future_mask.sum())
    valid_published = published[valid_mask]
    non_future_published = published[valid_mask & ~future_mask]
    derived_age_days = (today_utc - published.dt.normalize()).dt.days
    stale_mask = (
        ~valid_mask
        | future_mask
        | (derived_age_days > settings.freshness_threshold_days)
    )
    stale_rows = int(stale_mask.sum())
    stale_ratio = stale_rows / total_rows if total_rows else 1.0
    latest_age_days = (
        int((today_utc - non_future_published.max().normalize()).days)
        if not non_future_published.empty
        else None
    )

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "latest_published": (
            valid_published.max().date().isoformat() if not valid_published.empty else None
        ),
        "oldest_published": (
            valid_published.min().date().isoformat() if not valid_published.empty else None
        ),
        "latest_age_days": latest_age_days,
        "future_rows": future_rows,
        "invalid_published_rows": invalid_published_rows,
        "stale_rows": stale_rows,
        "stale_ratio": round(stale_ratio, 4),
        "total_rows": total_rows,
        "freshness_threshold_days": settings.freshness_threshold_days,
        "is_fresh": bool(
            total_rows > 0
            and invalid_published_rows == 0
            and future_rows == 0
            and latest_age_days is not None
            and latest_age_days <= settings.freshness_threshold_days
            and stale_ratio <= MAX_STALE_RATIO
        ),
    }
    write_json(report_path, report)
    return report
