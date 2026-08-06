from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any, Iterable

import pandas as pd

from core.utils import compact_join, normalize_whitespace
from ingestion.crossref import PaperRecord


MIN_SUMMARY_CHARS = 100


def _normalize_text(value: Any) -> str:
    """Convert a possibly missing scalar value into normalized text."""
    if value is None:
        return ""
    if not isinstance(value, (list, tuple, dict, set)) and pd.isna(value):
        return ""
    return normalize_whitespace(str(value))


def _normalize_list(values: Iterable[str] | str | None) -> list[str]:
    """Normalize list-like fields while preserving order and removing duplicates."""
    if values is None:
        return []
    if isinstance(values, str):
        values = [values]
    else:
        try:
            iter(values)
        except TypeError:
            values = [values]  # type: ignore[list-item]

    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = _normalize_text(value)
        item_key = item.casefold()
        if item and item_key not in seen:
            normalized.append(item)
            seen.add(item_key)
    return normalized


def _parse_date(value: Any) -> pd.Timestamp | None:
    parsed = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(parsed):
        return None
    return parsed


def build_clean_dataframe(records: list[PaperRecord], run_date: datetime) -> pd.DataFrame:
    """Clean raw records into a deterministic dataframe ready for embedding."""
    if run_date.tzinfo is None:
        run_date = run_date.replace(tzinfo=UTC)
    run_timestamp = pd.Timestamp(run_date).tz_convert("UTC")

    cleaned_rows: list[dict] = []
    for record in records:
        row = asdict(record)
        paper_id = _normalize_text(row.get("paper_id"))
        title = _normalize_text(row.get("title"))
        summary = _normalize_text(row.get("summary"))
        authors = _normalize_list(row.get("authors"))
        categories = _normalize_list(row.get("categories"))
        primary_category = _normalize_text(row.get("primary_category"))
        category_keys = {category.casefold() for category in categories}
        if primary_category and primary_category.casefold() not in category_keys:
            categories.insert(0, primary_category)

        published_ts = _parse_date(row["published"])
        updated_ts = _parse_date(row["updated"])
        if not paper_id or not title or len(summary) < MIN_SUMMARY_CHARS or published_ts is None:
            continue

        published_date = published_ts.date().isoformat()
        updated_value = updated_ts.isoformat() if updated_ts is not None else ""
        age_days = max(0, int((run_timestamp.normalize() - published_ts.normalize()).days))
        authors_joined = compact_join(authors)
        categories_joined = compact_join(categories)
        text_for_embedding = normalize_whitespace(
            "\n".join(
                part
                for part in (
                    f"Title: {title}",
                    f"Summary: {summary}",
                    f"Authors: {authors_joined}" if authors_joined else "",
                    f"Categories: {categories_joined}" if categories_joined else "",
                    f"Published: {published_date}",
                )
                if part
            )
        )

        cleaned_rows.append(
            {
                "paper_id": paper_id,
                "title": title,
                "summary": summary,
                "authors": authors,
                "categories": categories,
                "primary_category": primary_category,
                "published": published_date,
                "updated": updated_value,
                "abs_url": _normalize_text(row.get("abs_url")),
                "pdf_url": _normalize_text(row.get("pdf_url")),
                "comment": _normalize_text(row.get("comment")),
                "authors_joined": authors_joined,
                "categories_joined": categories_joined,
                "summary_chars": len(summary),
                "age_days": age_days,
                "text_for_embedding": text_for_embedding,
            }
        )

    columns = [
        "paper_id",
        "title",
        "summary",
        "authors",
        "categories",
        "primary_category",
        "published",
        "updated",
        "abs_url",
        "pdf_url",
        "comment",
        "authors_joined",
        "categories_joined",
        "summary_chars",
        "age_days",
        "text_for_embedding",
    ]
    if not cleaned_rows:
        return pd.DataFrame(columns=columns)

    df = pd.DataFrame(cleaned_rows, columns=columns)
    df["_paper_id_key"] = df["paper_id"].str.casefold()
    df["_title_key"] = df["title"].str.casefold()
    df = (
        df.sort_values(["published", "paper_id"], ascending=[False, True])
        .drop_duplicates(subset=["_paper_id_key"], keep="first")
        .drop_duplicates(subset=["_title_key"], keep="first")
        .drop(columns=["_paper_id_key", "_title_key"])
        .reset_index(drop=True)
    )
    return df
