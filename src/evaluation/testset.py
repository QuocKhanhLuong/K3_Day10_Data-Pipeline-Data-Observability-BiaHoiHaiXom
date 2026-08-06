from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from core.utils import first_sentence, normalize_whitespace, write_json


MIN_TEST_DOCUMENTS = 3
MAX_TEST_DOCUMENTS = 4


def _quoted_lookup_value(row: pd.Series) -> str:
    title = normalize_whitespace(str(row["title"]))
    if "'" not in title:
        return title
    return normalize_whitespace(str(row["paper_id"]))


def build_test_set(df: pd.DataFrame, output_path: Path) -> list[dict[str, Any]]:
    """Build a deterministic multi-type evaluation set from the cleaned corpus."""
    required_columns = {
        "paper_id",
        "title",
        "summary",
        "authors_joined",
        "categories_joined",
        "published",
        "summary_chars",
    }
    missing = sorted(required_columns - set(df.columns))
    if missing:
        raise ValueError(f"Cleaned dataframe is missing required columns: {missing}")
    if len(df) < MIN_TEST_DOCUMENTS:
        raise ValueError(
            f"At least {MIN_TEST_DOCUMENTS} cleaned documents are required to build the evaluation set; got {len(df)}."
        )

    selected = (
        df.sort_values(["summary_chars", "published"], ascending=[False, False])
        .head(MAX_TEST_DOCUMENTS)
        .reset_index(drop=True)
    )
    test_set: list[dict[str, Any]] = []

    def add_sample(
        row: pd.Series,
        question_type: str,
        question: str,
        ground_truth: str,
    ) -> None:
        normalized_truth = normalize_whitespace(ground_truth)
        if not normalized_truth:
            return
        sample_number = len(test_set) + 1
        test_set.append(
            {
                "id": f"eval-{sample_number:03d}",
                "question_type": question_type,
                "question": question,
                "ground_truth": normalized_truth,
                "ground_truth_doc_ids": [str(row["paper_id"])],
            }
        )

    for _, row in selected.iterrows():
        lookup_value = _quoted_lookup_value(row)
        add_sample(
            row,
            "summary",
            f"What is the main contribution described in '{lookup_value}'?",
            first_sentence(str(row["summary"])),
        )
        add_sample(
            row,
            "authors",
            f"Who authored the paper '{lookup_value}'?",
            str(row["authors_joined"]),
        )
        add_sample(
            row,
            "date",
            f"When was the paper '{lookup_value}' published?",
            str(row["published"]),
        )
        add_sample(
            row,
            "categories",
            f"What categories are associated with the paper '{lookup_value}'?",
            str(row["categories_joined"]),
        )

    if not test_set:
        raise ValueError("Could not create any valid evaluation samples from the cleaned dataframe.")

    write_json(output_path, test_set)
    return test_set
