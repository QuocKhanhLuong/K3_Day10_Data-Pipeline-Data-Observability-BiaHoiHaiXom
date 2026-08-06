from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from core.utils import compact_join, normalize_whitespace, write_json


NOISE_TEXT = " telemetry_error checksum_mismatch malformed_payload "


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [normalize_whitespace(str(item)) for item in value if normalize_whitespace(str(item))]
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    text = normalize_whitespace(str(value))
    return [item.strip() for item in text.split(",") if item.strip()]


def _rebuild_embedding_fields(df: pd.DataFrame) -> pd.DataFrame:
    repaired = df.copy()
    repaired["authors"] = repaired["authors"].apply(_as_list)
    repaired["categories"] = repaired["categories"].apply(_as_list)
    repaired["authors_joined"] = repaired["authors"].apply(compact_join)
    repaired["categories_joined"] = repaired["categories"].apply(compact_join)
    repaired["summary"] = repaired["summary"].fillna("").astype(str).apply(normalize_whitespace)
    repaired["title"] = repaired["title"].fillna("").astype(str).apply(normalize_whitespace)
    repaired["summary_chars"] = repaired["summary"].str.len()

    def build_text(row: pd.Series) -> str:
        return normalize_whitespace(
            "\n".join(
                part
                for part in (
                    f"Title: {row['title']}",
                    f"Summary: {row['summary']}",
                    f"Authors: {row['authors_joined']}" if row["authors_joined"] else "",
                    f"Categories: {row['categories_joined']}" if row["categories_joined"] else "",
                    f"Published: {row['published']}",
                )
                if part
            )
        )

    repaired["text_for_embedding"] = repaired.apply(build_text, axis=1)
    return repaired


def corrupt_clean_dataframe(df: pd.DataFrame, output_log_path: Path) -> pd.DataFrame:
    """Create deterministic, traceable corruption across content and freshness dimensions."""
    if len(df) < 6:
        raise ValueError("At least 6 rows are required to simulate meaningful corruption.")

    corrupted = df.copy(deep=True).reset_index(drop=True)
    operations: list[dict[str, Any]] = []

    eval_like_ids = (
        corrupted.sort_values(["summary_chars", "published"], ascending=[False, False])["paper_id"]
        .astype(str)
        .head(4)
        .tolist()
    )
    latest_id = str(
        corrupted.sort_values("published", ascending=False).iloc[0]["paper_id"]
    )
    drop_ids = [latest_id]
    for paper_id in eval_like_ids:
        if paper_id not in drop_ids:
            drop_ids.append(paper_id)
            break
    corrupted = corrupted[~corrupted["paper_id"].astype(str).isin(drop_ids)].reset_index(drop=True)
    operations.append(
        {
            "name": "drop_records",
            "count": len(drop_ids),
            "paper_ids": drop_ids,
            "details": "Removed the latest record and one high-information evaluation-like record.",
        }
    )

    remaining_eval_ids = [
        paper_id
        for paper_id in eval_like_ids
        if paper_id not in drop_ids
        and paper_id in set(corrupted["paper_id"].astype(str))
    ]

    blank_count = max(1, len(corrupted) // 5)
    blank_ids = remaining_eval_ids[:1]
    for paper_id in corrupted["paper_id"].astype(str).head(blank_count):
        if paper_id not in blank_ids:
            blank_ids.append(paper_id)
        if len(blank_ids) >= blank_count:
            break
    blank_mask = corrupted["paper_id"].astype(str).isin(blank_ids)
    corrupted.loc[blank_mask, "summary"] = ""
    operations.append(
        {
            "name": "blank_summary",
            "count": int(blank_mask.sum()),
            "paper_ids": corrupted.loc[blank_mask, "paper_id"].astype(str).tolist(),
        }
    )

    noise_count = max(1, len(corrupted) // 5)
    noise_ids = remaining_eval_ids[1:2]
    for paper_id in corrupted["paper_id"].astype(str).iloc[blank_count : blank_count + noise_count]:
        if paper_id not in noise_ids and paper_id not in blank_ids:
            noise_ids.append(paper_id)
        if len(noise_ids) >= noise_count:
            break
    noise_mask = corrupted["paper_id"].astype(str).isin(noise_ids)
    corrupted.loc[noise_mask, "summary"] = (
        corrupted.loc[noise_mask, "summary"].astype(str) + NOISE_TEXT * 4
    )
    operations.append(
        {
            "name": "summary_noise",
            "count": int(noise_mask.sum()),
            "paper_ids": corrupted.loc[noise_mask, "paper_id"].astype(str).tolist(),
        }
    )

    truncate_count = max(1, len(corrupted) // 6)
    truncate_ids = remaining_eval_ids[2:3]
    for paper_id in corrupted["paper_id"].astype(str).iloc[-truncate_count:]:
        if paper_id not in truncate_ids:
            truncate_ids.append(paper_id)
        if len(truncate_ids) >= truncate_count:
            break
    truncate_mask = corrupted["paper_id"].astype(str).isin(truncate_ids)
    corrupted.loc[truncate_mask, "title"] = corrupted.loc[truncate_mask, "title"].astype(str).apply(
        lambda value: normalize_whitespace(value[: max(8, min(24, len(value) // 3))])
    )
    operations.append(
        {
            "name": "truncate_title",
            "count": int(truncate_mask.sum()),
            "paper_ids": corrupted.loc[truncate_mask, "paper_id"].astype(str).tolist(),
        }
    )

    stale_count = max(1, len(corrupted) // 4)
    stale_ids = []
    for paper_id in remaining_eval_ids[-1:] + corrupted["paper_id"].astype(str).tail(stale_count).tolist():
        if paper_id not in stale_ids:
            stale_ids.append(paper_id)
        if len(stale_ids) >= stale_count:
            break
    stale_mask = corrupted["paper_id"].astype(str).isin(stale_ids)
    stale_dates = pd.to_datetime(corrupted.loc[stale_mask, "published"], errors="coerce")
    corrupted.loc[stale_mask, "published"] = (
        stale_dates - pd.Timedelta(days=730)
    ).dt.date.astype(str)
    current_age = pd.to_numeric(corrupted.loc[stale_mask, "age_days"], errors="coerce").fillna(0)
    corrupted.loc[stale_mask, "age_days"] = (current_age + 730).astype(int)
    operations.append(
        {
            "name": "stale_publication_date",
            "count": int(stale_mask.sum()),
            "paper_ids": corrupted.loc[stale_mask, "paper_id"].astype(str).tolist(),
        }
    )

    duplicate_count = min(2, len(corrupted))
    duplicate_rows = corrupted.head(duplicate_count).copy(deep=True)
    corrupted = pd.concat([corrupted, duplicate_rows], ignore_index=True)
    operations.append(
        {
            "name": "duplicate_rows",
            "count": duplicate_count,
            "paper_ids": duplicate_rows["paper_id"].astype(str).tolist(),
        }
    )

    corrupted = _rebuild_embedding_fields(corrupted)
    log = {
        "input_rows": int(len(df)),
        "output_rows": int(len(corrupted)),
        "operations": operations,
        "expected_effects": {
            "quality": "Duplicate IDs, blank summaries, and stale rows should fail quality checks.",
            "evaluation": "Dropped and modified evaluation-like documents should reduce retrieval and answer metrics.",
        },
    }
    write_json(output_log_path, log)
    return corrupted.reset_index(drop=True)
