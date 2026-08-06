from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from core.utils import first_sentence, normalize_whitespace, write_json


TEST_SET_SIZE = 10


def _quoted_lookup_value(row: pd.Series) -> str:
    title = normalize_whitespace(str(row["title"]))
    if "'" not in title:
        return title
    return normalize_whitespace(str(row["paper_id"]))


def build_test_set(df: pd.DataFrame, output_path: Path) -> list[dict[str, Any]]:
    """Build and freeze 10 deterministic factual questions from clean data."""
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
    if len(df) < TEST_SET_SIZE:
        raise ValueError(
            f"At least {TEST_SET_SIZE} cleaned documents are required to build the evaluation set; got {len(df)}."
        )

    selected = (
        df.assign(_paper_id_key=df["paper_id"].astype(str).str.casefold())
        .sort_values(["published", "_paper_id_key"], ascending=[False, True])
        .head(TEST_SET_SIZE)
        .reset_index(drop=True)
    )
    test_set: list[dict[str, Any]] = []

    question_builders = (
        (
            lambda lookup_value, row: f"Who authored the paper '{lookup_value}'?",
            lambda row: row["authors_joined"],
        ),
        (
            lambda lookup_value, row: f"When was the paper '{lookup_value}' published?",
            lambda row: row["published"],
        ),
        (
            lambda lookup_value, row: f"What categories are associated with the paper '{lookup_value}'?",
            lambda row: row["categories_joined"],
        ),
        (
            lambda lookup_value, row: f"What is the main contribution described in '{lookup_value}'?",
            lambda row: first_sentence(str(row["summary"])),
        ),
    )

    for index, (_, row) in enumerate(selected.iterrows()):
        lookup_value = _quoted_lookup_value(row)
        build_question, build_truth = question_builders[index % len(question_builders)]
        question = build_question(lookup_value, row)
        ground_truth = normalize_whitespace(str(build_truth(row)))
        if not ground_truth:
            raise ValueError(f"Could not create ground truth for paper {row['paper_id']}.")
        test_set.append(
            {
                "id": f"q{index + 1}",
                "question_type": "factual",
                "question": question,
                "ground_truth": ground_truth,
                "ground_truth_doc_ids": [str(row["paper_id"])],
            }
        )

    if len(test_set) != TEST_SET_SIZE:
        raise ValueError(f"Expected exactly {TEST_SET_SIZE} evaluation samples; got {len(test_set)}.")

    write_json(output_path, test_set)
    return test_set
