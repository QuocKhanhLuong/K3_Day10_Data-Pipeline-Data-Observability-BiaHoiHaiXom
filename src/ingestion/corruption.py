from __future__ import annotations

import json
import random
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from core.utils import normalize_whitespace, write_json


DEFAULT_TEST_SET_PATH = Path("data/eval/test_set.json")
DEFAULT_OUTPUT_CSV_PATH = Path("data/clean/papers_corrupted.csv")
NOISE_TEXT = "telemetry_error checksum_mismatch malformed_payload"
NOISE_REPETITIONS = 16
REQUIRED_COLUMNS = {
    "paper_id",
    "title",
    "summary",
    "published",
    "age_days",
    "text_for_embedding",
}


def _json_value(value: Any) -> Any:
    """Convert pandas/numpy scalar values to JSON-safe Python values."""
    if value is None:
        return None
    if isinstance(value, (pd.Timestamp, date)):
        return value.isoformat()
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        return value.item()
    return value


def _validate_clean_dataframe(df: pd.DataFrame) -> None:
    missing = sorted(REQUIRED_COLUMNS - set(df.columns))
    if missing:
        raise ValueError(f"Clean dataframe is missing required columns: {missing}")
    if len(df) < 4:
        raise ValueError("At least 4 clean rows are required to run four corruption scenarios.")
    if df["paper_id"].isna().any():
        raise ValueError("Clean dataframe contains null paper_id values.")
    if df["paper_id"].astype(str).duplicated().any():
        raise ValueError(
            "Input data is already duplicated; the clean baseline must have "
            "unique paper_id values."
        )


def _extract_test_samples(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        samples = payload
    elif isinstance(payload, dict):
        samples = next(
            (
                payload[key]
                for key in ("samples", "questions", "test_set", "items")
                if isinstance(payload.get(key), list)
            ),
            None,
        )
        if samples is None:
            raise ValueError("Frozen test set must be a list or contain a list of samples.")
    else:
        raise ValueError("Frozen test set has an unsupported JSON structure.")

    if not all(isinstance(sample, dict) for sample in samples):
        raise ValueError("Every frozen test sample must be a JSON object.")
    return samples


def _load_frozen_doc_ids(test_set_path: Path) -> list[str]:
    if not test_set_path.exists():
        raise FileNotFoundError(f"Frozen test set not found: {test_set_path}")

    with test_set_path.open("r", encoding="utf-8") as stream:
        samples = _extract_test_samples(json.load(stream))

    frozen_ids: list[str] = []
    for sample in samples:
        doc_ids = sample.get("ground_truth_doc_ids", [])
        if isinstance(doc_ids, (str, int)):
            doc_ids = [doc_ids]
        if not isinstance(doc_ids, list):
            raise ValueError("ground_truth_doc_ids must be a list in every frozen test sample.")
        for doc_id in doc_ids:
            normalized_id = str(doc_id).strip()
            if normalized_id and normalized_id not in frozen_ids:
                frozen_ids.append(normalized_id)

    if not frozen_ids:
        raise ValueError("Frozen test set contains no ground_truth_doc_ids.")
    return frozen_ids


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    if isinstance(value, list):
        value = ", ".join(str(item) for item in value)
    return normalize_whitespace(str(value))


def _build_embedding_text(row: pd.Series) -> str:
    """Rebuild the embedding text using the canonical Lab 10 format."""
    authors = row.get("authors_joined", row.get("authors", ""))
    return normalize_whitespace(
        " | ".join(
            (
                f"Title: {_clean_text(row.get('title', ''))}",
                f"Authors: {_clean_text(authors)}",
                f"Summary: {_clean_text(row.get('summary', ''))}",
            )
        )
    )


def _select_ids(
    ordered_ids: list[str],
    count: int,
    used_ids: set[str],
    forced_id: str | None = None,
) -> list[str]:
    """Choose deterministic targets, preferring unused rows and an optional frozen ID."""
    selected: list[str] = []
    if forced_id is not None and forced_id in ordered_ids:
        selected.append(forced_id)

    for paper_id in ordered_ids:
        if len(selected) >= count:
            break
        if paper_id not in selected and paper_id not in used_ids:
            selected.append(paper_id)

    if len(selected) < count:
        for paper_id in ordered_ids:
            if len(selected) >= count:
                break
            if paper_id not in selected:
                selected.append(paper_id)

    used_ids.update(selected)
    return selected


def _field_change(
    paper_id: str,
    field: str,
    before: Any,
    after: Any,
) -> dict[str, Any]:
    return {
        "paper_id": paper_id,
        "field": field,
        "before": _json_value(before),
        "after": _json_value(after),
    }


def corrupt_clean_dataframe(
    df: pd.DataFrame,
    output_log_path: Path,
    test_set_path: Path = DEFAULT_TEST_SET_PATH,
    output_csv_path: Path | None = DEFAULT_OUTPUT_CSV_PATH,
    *,
    corruption_ratio: float = 0.20,
    seed: int = 42,
    reference_date: str | date | pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Create the four controlled corruption scenarios required by Lab 10.

    At least the blank-summary and add-noise scenarios are forced to overlap
    documents referenced by the frozen evaluation set. The function is
    deterministic for a fixed input, seed, ratio, and reference date.
    """
    _validate_clean_dataframe(df)
    if not 0 < corruption_ratio <= 1:
        raise ValueError("corruption_ratio must be in the interval (0, 1].")

    output_log_path = Path(output_log_path)
    test_set_path = Path(test_set_path)
    output_csv_path = Path(output_csv_path) if output_csv_path is not None else None

    corrupted = df.copy(deep=True).reset_index(drop=True)
    corrupted["paper_id"] = corrupted["paper_id"].astype(str)

    frozen_ids = _load_frozen_doc_ids(test_set_path)
    available_ids = corrupted["paper_id"].drop_duplicates().tolist()
    available_id_set = set(available_ids)
    frozen_available_ids = [
        paper_id for paper_id in frozen_ids if paper_id in available_id_set
    ]
    if not frozen_available_ids:
        raise ValueError(
            "No ground_truth_doc_ids from the frozen test set exist in the clean dataframe."
        )

    rng = random.Random(seed)
    shuffled_ids = available_ids.copy()
    rng.shuffle(shuffled_ids)
    count = max(1, round(len(available_ids) * corruption_ratio))
    used_ids: set[str] = set()
    operations: list[dict[str, Any]] = []

    # 1. Blank Summary: force overlap with a document used by the frozen test set.
    blank_ids = _select_ids(shuffled_ids, count, used_ids, frozen_available_ids[0])
    blank_changes: list[dict[str, Any]] = []
    for paper_id in blank_ids:
        row_index = corrupted.index[corrupted["paper_id"] == paper_id][0]
        before_summary = corrupted.at[row_index, "summary"]
        before_embedding = corrupted.at[row_index, "text_for_embedding"]
        corrupted.at[row_index, "summary"] = ""
        if "summary_chars" in corrupted.columns:
            before_chars = corrupted.at[row_index, "summary_chars"]
            corrupted.at[row_index, "summary_chars"] = 0
            blank_changes.append(_field_change(paper_id, "summary_chars", before_chars, 0))
        corrupted.at[row_index, "text_for_embedding"] = _build_embedding_text(
            corrupted.loc[row_index]
        )
        blank_changes.extend(
            (
                _field_change(paper_id, "summary", before_summary, ""),
                _field_change(
                    paper_id,
                    "text_for_embedding",
                    before_embedding,
                    corrupted.at[row_index, "text_for_embedding"],
                ),
            )
        )
    operations.append(
        {
            "name": "blank_summary",
            "count": len(blank_ids),
            "paper_ids": blank_ids,
            "changes": blank_changes,
        }
    )

    # 2. Add Noise: modify text_for_embedding directly as required by the lab.
    noise_frozen_id = (
        frozen_available_ids[1]
        if len(frozen_available_ids) > 1
        else frozen_available_ids[0]
    )
    noise_ids = _select_ids(shuffled_ids, count, used_ids, noise_frozen_id)
    noise_changes: list[dict[str, Any]] = []
    noise_payload = " ".join([NOISE_TEXT] * NOISE_REPETITIONS)
    for paper_id in noise_ids:
        row_index = corrupted.index[corrupted["paper_id"] == paper_id][0]
        before = corrupted.at[row_index, "text_for_embedding"]
        # Prefix the noise so it is not silently truncated by short-context encoders.
        after = normalize_whitespace(f"{noise_payload} {_clean_text(before)}")
        corrupted.at[row_index, "text_for_embedding"] = after
        noise_changes.append(_field_change(paper_id, "text_for_embedding", before, after))
    operations.append(
        {
            "name": "add_noise",
            "count": len(noise_ids),
            "paper_ids": noise_ids,
            "changes": noise_changes,
        }
    )

    # 3. Stale Date: move the newest documents to 2000 and recompute age_days.
    newest_ids = (
        corrupted.assign(_published_sort=pd.to_datetime(corrupted["published"], errors="coerce"))
        .sort_values("_published_sort", ascending=False, na_position="last")["paper_id"]
        .drop_duplicates()
        .tolist()
    )
    stale_ids = _select_ids(newest_ids, count, used_ids)
    evaluation_date = pd.Timestamp(reference_date or date.today()).normalize().tz_localize(None)
    stale_date = pd.Timestamp("2000-01-01")
    stale_age_days = int((evaluation_date - stale_date).days)
    stale_changes: list[dict[str, Any]] = []
    for paper_id in stale_ids:
        row_index = corrupted.index[corrupted["paper_id"] == paper_id][0]
        before_published = corrupted.at[row_index, "published"]
        before_age = corrupted.at[row_index, "age_days"]
        corrupted.at[row_index, "published"] = stale_date.date().isoformat()
        corrupted.at[row_index, "age_days"] = stale_age_days
        stale_changes.extend(
            (
                _field_change(
                    paper_id,
                    "published",
                    before_published,
                    corrupted.at[row_index, "published"],
                ),
                _field_change(
                    paper_id,
                    "age_days",
                    before_age,
                    corrupted.at[row_index, "age_days"],
                ),
            )
        )
    operations.append(
        {
            "name": "stale_date",
            "count": len(stale_ids),
            "paper_ids": stale_ids,
            "changes": stale_changes,
        }
    )

    # 4. Duplicates: append complete rows while preserving their paper_id values.
    duplicate_frozen_id = (
        frozen_available_ids[2] if len(frozen_available_ids) > 2 else frozen_available_ids[-1]
    )
    duplicate_ids = _select_ids(shuffled_ids, count, used_ids, duplicate_frozen_id)
    duplicate_rows = corrupted[corrupted["paper_id"].isin(duplicate_ids)].copy(deep=True)
    duplicate_changes = [
        _field_change(paper_id, "row_count_for_paper_id", 1, 2)
        for paper_id in duplicate_ids
    ]
    corrupted = pd.concat([corrupted, duplicate_rows], ignore_index=True)
    operations.append(
        {
            "name": "duplicates",
            "count": len(duplicate_rows),
            "paper_ids": duplicate_ids,
            "changes": duplicate_changes,
        }
    )

    corrupted_frozen_ids = sorted(
        {
            paper_id
            for operation in operations
            for paper_id in operation["paper_ids"]
            if paper_id in set(frozen_available_ids)
        }
    )
    if not corrupted_frozen_ids:
        raise RuntimeError("Corruption did not overlap any document in the frozen test set.")

    log = {
        "input_rows": int(len(df)),
        "output_rows": int(len(corrupted)),
        "seed": seed,
        "corruption_ratio": corruption_ratio,
        "reference_date": evaluation_date.date().isoformat(),
        "frozen_test_set_path": str(test_set_path),
        "frozen_doc_ids_found_in_clean_data": frozen_available_ids,
        "corrupted_frozen_doc_ids": corrupted_frozen_ids,
        "overlap_requirement_passed": True,
        "operations": operations,
        "expected_effects": {
            "completeness": "FAIL because selected summaries are blank.",
            "uniqueness": "FAIL because duplicate paper_id rows are present.",
            "freshness": "FAIL because selected publications were moved to 2000-01-01.",
            "retrieval": (
                "Expected to decrease because frozen-test documents have blank "
                "or noisy embedding text."
            ),
        },
    }

    output_log_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(output_log_path, log)
    if output_csv_path is not None:
        output_csv_path.parent.mkdir(parents=True, exist_ok=True)
        corrupted.to_csv(output_csv_path, index=False)

    return corrupted.reset_index(drop=True)
