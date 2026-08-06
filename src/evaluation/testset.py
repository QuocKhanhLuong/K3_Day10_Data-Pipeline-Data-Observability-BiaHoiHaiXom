from __future__ import annotations

from pathlib import Path
import re
from typing import Any

import pandas as pd

from core.utils import first_sentence, normalize_whitespace, write_json


TEST_SET_SIZE = 20
KEEP_EXISTING_SAMPLES = 6
TOPIC_ONLY_SAMPLES = 15
TOPIC_STOPWORDS = {
    "a",
    "an",
    "and",
    "for",
    "from",
    "in",
    "of",
    "on",
    "the",
    "to",
    "with",
}


def _topic_from_title(title: str) -> str:
    """Create a short topic cue without copying the paper's full title."""
    normalized = normalize_whitespace(title)
    tokens = re.findall(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)?", normalized)
    topic_tokens = [
        token
        for token in tokens
        if token.casefold() not in TOPIC_STOPWORDS and not token.isdigit()
    ][:4]
    if not topic_tokens:
        topic_tokens = tokens[:4]
    topic = normalize_whitespace(" ".join(topic_tokens))
    if not topic:
        raise ValueError("Could not derive a topic cue from a paper title.")
    return topic


def build_test_set(df: pd.DataFrame, output_path: Path) -> list[dict[str, Any]]:
    """Build and freeze 20 factual questions with 15 topic-only and 5 title lookups."""
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

    ordered = (
        df.assign(_paper_id_key=df["paper_id"].astype(str).str.casefold())
        .sort_values(["published", "_paper_id_key"], ascending=[False, True])
        .reset_index(drop=True)
    )
    topic_selected = ordered.head(TOPIC_ONLY_SAMPLES)
    title_candidates = ordered.iloc[TOPIC_ONLY_SAMPLES:]
    title_selected = title_candidates[
        ~title_candidates["title"].astype(str).str.contains("'", regex=False)
    ].head(TEST_SET_SIZE - TOPIC_ONLY_SAMPLES)
    if len(topic_selected) < TOPIC_ONLY_SAMPLES or len(title_selected) < TEST_SET_SIZE - TOPIC_ONLY_SAMPLES:
        raise ValueError("Not enough clean documents to build the requested frozen evaluation set.")
    selected = pd.concat([topic_selected, title_selected], ignore_index=True)
    test_set: list[dict[str, Any]] = []

    question_builders = (
        (
            lambda topic, row: f"Who authored research about {topic}?",
            lambda row: row["authors_joined"],
        ),
        (
            lambda topic, row: f"When was the study about {topic} published?",
            lambda row: row["published"],
        ),
        (
            lambda topic, row: f"What categories are associated with research about {topic}?",
            lambda row: row["categories_joined"],
        ),
        (
            lambda topic, row: f"What is the main contribution described in research about {topic}?",
            lambda row: first_sentence(str(row["summary"])),
        ),
    )
    rewritten_question_builders = (
        (
            lambda topic, row: f"Who authored research investigating {topic}?",
            lambda row: row["authors_joined"],
        ),
        (
            lambda topic, row: f"When was research examining {topic} published?",
            lambda row: row["published"],
        ),
        (
            lambda topic, row: f"What categories are associated with studies focused on {topic}?",
            lambda row: row["categories_joined"],
        ),
        (
            lambda topic, row: f"What is the main contribution of research investigating {topic}?",
            lambda row: first_sentence(str(row["summary"])),
        ),
    )
    full_title_question_builders = (
        (
            lambda title, row: f"Who authored the paper '{title}'?",
            lambda row: row["authors_joined"],
        ),
        (
            lambda title, row: f"When was the paper '{title}' published?",
            lambda row: row["published"],
        ),
        (
            lambda title, row: f"What categories are associated with the paper '{title}'?",
            lambda row: row["categories_joined"],
        ),
        (
            lambda title, row: f"What is the main contribution described in '{title}'?",
            lambda row: first_sentence(str(row["summary"])),
        ),
    )

    for index, (_, row) in enumerate(selected.iterrows()):
        if index < TOPIC_ONLY_SAMPLES:
            topic = _topic_from_title(str(row["title"]))
            builders = question_builders if index < KEEP_EXISTING_SAMPLES else rewritten_question_builders
            build_question, build_truth = builders[index % len(builders)]
            question = build_question(topic, row)
        else:
            title = normalize_whitespace(str(row["title"]))
            build_question, build_truth = full_title_question_builders[
                (index - TOPIC_ONLY_SAMPLES) % len(full_title_question_builders)
            ]
            question = build_question(title, row)
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
