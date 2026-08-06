from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from typing import Iterable

import pandas as pd

from core.utils import compact_join, normalize_whitespace
from ingestion.crossref import PaperRecord


MIN_SUMMARY_CHARS = 80


def _normalize_list(values: Iterable[str]) -> list[str]:
    normalized: list[str] = []
    for value in values:
        item = normalize_whitespace(str(value))
        if item and item not in normalized:
            normalized.append(item)
    return normalized


def _parse_date(value: str) -> pd.Timestamp | None:
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
        paper_id = normalize_whitespace(row["paper_id"])
        title = normalize_whitespace(row["title"])
        summary = normalize_whitespace(row["summary"])
        authors = _normalize_list(row["authors"])
        categories = _normalize_list(row["categories"])
        primary_category = normalize_whitespace(row["primary_category"])
        if primary_category and primary_category not in categories:
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
                "abs_url": normalize_whitespace(row["abs_url"]),
                "pdf_url": normalize_whitespace(row["pdf_url"]),
                "comment": normalize_whitespace(row["comment"]),
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
    df["_paper_id_key"] = df["paper_id"].str.lower()
    df["_title_key"] = df["title"].str.lower()
    df = (
        df.sort_values(["published", "paper_id"], ascending=[False, True])
        .drop_duplicates(subset=["_paper_id_key"], keep="first")
        .drop_duplicates(subset=["_title_key"], keep="first")
        .drop(columns=["_paper_id_key", "_title_key"])
        .reset_index(drop=True)
    )
    return df
