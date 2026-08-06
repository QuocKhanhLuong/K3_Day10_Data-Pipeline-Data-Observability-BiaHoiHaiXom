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


def _append_unique(values: list[str], value: str) -> None:
    if value and value not in values:
        values.append(value)


def _classify_question(question: str) -> str:
    """Map the factual questions in test_set.json to the field they evaluate."""
    normalized = normalize_whitespace(question).casefold()
    if "who authored" in normalized or "author of" in normalized:
        return "authors"
    if "when was" in normalized and "published" in normalized:
        return "published"
    if "categor" in normalized:
        return "categories"
    if "main contribution" in normalized or "main finding" in normalized:
        return "summary"
    return "other"


def _load_frozen_targets(
    test_set_path: Path,
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    if not test_set_path.exists():
        raise FileNotFoundError(f"Frozen test set not found: {test_set_path}")

    with test_set_path.open("r", encoding="utf-8") as stream:
        samples = _extract_test_samples(json.load(stream))

    targets = {
        "all": [],
        "authors": [],
        "published": [],
        "categories": [],
        "summary": [],
        "other": [],
    }
    doc_to_question_ids: dict[str, list[str]] = {}

    for position, sample in enumerate(samples):
        question_id = str(sample.get("id", f"sample_{position}")).strip()
        question = str(sample.get("question", "")).strip()
        if not question:
            raise ValueError(f"Frozen test sample {question_id} has an empty question.")
        target_field = _classify_question(question)

        doc_ids = sample.get("ground_truth_doc_ids", [])
        if isinstance(doc_ids, (str, int)):
            doc_ids = [doc_ids]
        if not isinstance(doc_ids, list):
            raise ValueError("ground_truth_doc_ids must be a list in every frozen test sample.")
        if not doc_ids:
            raise ValueError(
                f"Frozen test sample {question_id} has no ground_truth_doc_ids."
            )
        for doc_id in doc_ids:
            normalized_id = str(doc_id).strip().casefold()
            if not normalized_id:
                raise ValueError(
                    f"Frozen test sample {question_id} contains an empty document ID."
                )
            _append_unique(targets["all"], normalized_id)
            _append_unique(targets[target_field], normalized_id)
            doc_to_question_ids.setdefault(normalized_id, [])
            _append_unique(doc_to_question_ids[normalized_id], question_id)

    if not targets["all"]:
        raise ValueError("Frozen test set contains no ground_truth_doc_ids.")
    return targets, doc_to_question_ids


def _load_frozen_doc_ids(test_set_path: Path) -> list[str]:
    """Backward-compatible helper used by existing tests or integrations."""
    targets, _ = _load_frozen_targets(test_set_path)
    return targets["all"]


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
    forced_ids: list[str] | None = None,
) -> list[str]:
    """Choose targets while always retaining semantically matched frozen IDs."""
    ordered_id_set = set(ordered_ids)
    selected = [
        paper_id
        for paper_id in (forced_ids or [])
        if paper_id in ordered_id_set
    ]
    effective_count = max(count, len(selected))

    for paper_id in ordered_ids:
        if len(selected) >= effective_count:
            break
        if paper_id not in selected and paper_id not in used_ids:
            selected.append(paper_id)

    if len(selected) < effective_count:
        for paper_id in ordered_ids:
            if len(selected) >= effective_count:
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


def _question_ids_for_papers(
    paper_ids: list[str],
    doc_to_question_ids: dict[str, list[str]],
) -> list[str]:
    question_ids: list[str] = []
    for paper_id in paper_ids:
        for question_id in doc_to_question_ids.get(paper_id.casefold(), []):
            _append_unique(question_ids, question_id)
    return question_ids


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

    Frozen documents are assigned to corruption scenarios according to the
    fields evaluated by their questions: summary, publication date, authors,
    or categories. The function is deterministic for a fixed input, seed,
    ratio, and reference date.
    """
    _validate_clean_dataframe(df)
    if not 0 < corruption_ratio <= 1:
        raise ValueError("corruption_ratio must be in the interval (0, 1].")

    output_log_path = Path(output_log_path)
    test_set_path = Path(test_set_path)
    output_csv_path = Path(output_csv_path) if output_csv_path is not None else None

    corrupted = df.copy(deep=True).reset_index(drop=True)
    corrupted["paper_id"] = corrupted["paper_id"].astype(str).str.strip()

    frozen_targets, doc_to_question_ids = _load_frozen_targets(test_set_path)
    available_ids = corrupted["paper_id"].drop_duplicates().tolist()
    available_id_lookup = {
        paper_id.casefold(): paper_id
        for paper_id in available_ids
    }
    missing_frozen_ids = sorted(
        set(frozen_targets["all"]) - set(available_id_lookup)
    )
    if missing_frozen_ids:
        raise ValueError(
            "Frozen test set references documents missing from the clean dataframe: "
            f"{missing_frozen_ids}"
        )
    frozen_available_by_field = {
        field: [available_id_lookup[paper_id] for paper_id in paper_ids]
        for field, paper_ids in frozen_targets.items()
    }
    frozen_available_ids = frozen_available_by_field["all"]
    frozen_available_id_set = set(frozen_available_ids)

    rng = random.Random(seed)
    shuffled_ids = available_ids.copy()
    rng.shuffle(shuffled_ids)
    filler_first_ids = [
        paper_id
        for paper_id in shuffled_ids
        if paper_id not in frozen_available_id_set
    ] + shuffled_ids
    count = max(1, round(len(available_ids) * corruption_ratio))
    used_ids: set[str] = set()
    operations: list[dict[str, Any]] = []

    # 1. Blank Summary: target q4/q8-style main-contribution questions.
    blank_target_ids = (
        frozen_available_by_field["summary"]
        or [frozen_available_ids[0]]
    )
    blank_ids = _select_ids(
        filler_first_ids,
        count,
        used_ids,
        forced_ids=blank_target_ids,
    )
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
            "semantic_target": "summary",
            "frozen_question_ids": _question_ids_for_papers(
                blank_ids,
                doc_to_question_ids,
            ),
            "changes": blank_changes,
        }
    )

    # 2. Add Noise: target author/category/other questions through retrieval text.
    noise_target_ids: list[str] = []
    for field in ("authors", "categories", "other"):
        for paper_id in frozen_available_by_field[field]:
            _append_unique(noise_target_ids, paper_id)
    if not noise_target_ids:
        noise_target_ids = [frozen_available_ids[0]]
    noise_ids = _select_ids(
        filler_first_ids,
        count,
        used_ids,
        forced_ids=noise_target_ids,
    )
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
            "semantic_target": "authors/categories/retrieval",
            "frozen_question_ids": _question_ids_for_papers(
                noise_ids,
                doc_to_question_ids,
            ),
            "changes": noise_changes,
        }
    )

    # 3. Stale Date: target q2/q6/q10-style publication-date questions.
    newest_ids = (
        corrupted.assign(_published_sort=pd.to_datetime(corrupted["published"], errors="coerce"))
        .sort_values("_published_sort", ascending=False, na_position="last")["paper_id"]
        .drop_duplicates()
        .tolist()
    )
    newest_filler_first_ids = [
        paper_id
        for paper_id in newest_ids
        if paper_id not in frozen_available_id_set
    ] + newest_ids
    stale_ids = _select_ids(
        newest_filler_first_ids,
        count,
        used_ids,
        forced_ids=frozen_available_by_field["published"],
    )
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
            "semantic_target": "published",
            "frozen_question_ids": _question_ids_for_papers(
                stale_ids,
                doc_to_question_ids,
            ),
            "changes": stale_changes,
        }
    )

    # 4. Duplicates: append complete rows while preserving their paper_id values.
    duplicate_ids = _select_ids(
        filler_first_ids,
        count,
        used_ids,
        forced_ids=[frozen_available_ids[-1]],
    )
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
            "semantic_target": "paper_id uniqueness",
            "frozen_question_ids": _question_ids_for_papers(
                duplicate_ids,
                doc_to_question_ids,
            ),
            "changes": duplicate_changes,
        }
    )

    corrupted_frozen_ids = sorted(
        {
            paper_id
            for operation in operations
            for paper_id in operation["paper_ids"]
            if paper_id in frozen_available_id_set
        }
    )
    if not corrupted_frozen_ids:
        raise RuntimeError("Corruption did not overlap any document in the frozen test set.")

    expected_question_ids: list[str] = []
    for question_ids in doc_to_question_ids.values():
        for question_id in question_ids:
            _append_unique(expected_question_ids, question_id)
    covered_question_id_set = {
        question_id
        for operation in operations
        for question_id in operation["frozen_question_ids"]
    }
    covered_question_ids = [
        question_id
        for question_id in expected_question_ids
        if question_id in covered_question_id_set
    ]
    uncovered_question_ids = [
        question_id
        for question_id in expected_question_ids
        if question_id not in covered_question_id_set
    ]
    if uncovered_question_ids:
        raise RuntimeError(
            "Some frozen questions were not targeted by corruption: "
            f"{uncovered_question_ids}"
        )

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
        "frozen_question_ids": expected_question_ids,
        "covered_frozen_question_ids": covered_question_ids,
        "all_frozen_questions_covered": True,
        "semantic_frozen_targets": {
            field: paper_ids
            for field, paper_ids in frozen_available_by_field.items()
            if field != "all"
        },
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
