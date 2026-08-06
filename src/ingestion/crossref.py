from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from html import unescape
from pathlib import Path
import re
import time
from typing import Any

import requests

from core.config import Settings, load_settings
from core.utils import normalize_whitespace, read_json, write_json


CROSSREF_API_URL = "https://api.crossref.org/works"
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


@dataclass(frozen=True)
class PaperRecord:
    paper_id: str
    title: str
    summary: str
    authors: list[str]
    categories: list[str]
    primary_category: str
    published: str
    updated: str
    abs_url: str
    pdf_url: str
    comment: str


def _clean_markup(value: Any) -> str:
    if not value:
        return ""
    text = re.sub(r"<[^>]+>", " ", str(value))
    return normalize_whitespace(unescape(text))


def _first_text(value: Any) -> str:
    if isinstance(value, list):
        return _clean_markup(value[0]) if value else ""
    return _clean_markup(value)


def _date_from_parts(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    date_parts = value.get("date-parts")
    if not date_parts or not isinstance(date_parts, list) or not date_parts[0]:
        return ""
    parts = [int(part) for part in date_parts[0][:3]]
    while len(parts) < 3:
        parts.append(1)
    try:
        return date(parts[0], parts[1], parts[2]).isoformat()
    except (TypeError, ValueError):
        return ""


def _published_date(item: dict[str, Any]) -> str:
    today_str = date.today().isoformat()
    for key in ("published-print", "published-online", "published", "issued", "created"):
        parsed = _date_from_parts(item.get(key))
        if parsed and parsed <= today_str:
            return parsed
    for key in ("created", "issued", "deposited"):
        parsed = _date_from_parts(item.get(key))
        if parsed:
            return min(parsed, today_str)
    return ""



def _updated_date(item: dict[str, Any]) -> str:
    indexed = item.get("indexed") or {}
    if isinstance(indexed, dict) and indexed.get("date-time"):
        return str(indexed["date-time"])
    for key in ("deposited", "created"):
        parsed = _date_from_parts(item.get(key))
        if parsed:
            return parsed
    return ""


def _author_names(item: dict[str, Any]) -> list[str]:
    authors: list[str] = []
    for author in item.get("author") or []:
        if not isinstance(author, dict):
            continue
        name = normalize_whitespace(
            " ".join(
                part
                for part in (
                    str(author.get("given") or "").strip(),
                    str(author.get("family") or "").strip(),
                )
                if part
            )
        )
        if not name:
            name = normalize_whitespace(str(author.get("name") or ""))
        if name and name not in authors:
            authors.append(name)
    return authors


def _pdf_url(item: dict[str, Any]) -> str:
    for link in item.get("link") or []:
        if not isinstance(link, dict):
            continue
        content_type = str(link.get("content-type") or "").lower()
        url = str(link.get("URL") or "")
        if url and ("pdf" in content_type or url.lower().endswith(".pdf")):
            return url
    return ""


def parse_crossref_payload(payload: dict) -> list[PaperRecord]:
    """Parse a Crossref API payload into a stable paper schema."""
    message = payload.get("message") if isinstance(payload, dict) else None
    items = message.get("items", []) if isinstance(message, dict) else []
    records: list[PaperRecord] = []
    seen_ids: set[str] = set()
    today_str = date.today().isoformat()

    for item in items:
        if not isinstance(item, dict):
            continue

        paper_id = normalize_whitespace(str(item.get("DOI") or item.get("URL") or ""))
        title = _first_text(item.get("title"))
        summary = _clean_markup(item.get("abstract"))
        if not paper_id or not title or not summary:
            continue

        canonical_id = paper_id.lower()
        if canonical_id in seen_ids:
            continue

        published = _published_date(item)
        if published and published > today_str:
            continue

        seen_ids.add(canonical_id)

        categories = [
            normalized
            for subject in item.get("subject") or []
            if (normalized := normalize_whitespace(str(subject)))
        ]
        primary_category = categories[0] if categories else normalize_whitespace(str(item.get("type") or ""))
        container_title = _first_text(item.get("container-title"))
        subtitle = _first_text(item.get("subtitle"))
        comment = " | ".join(part for part in (container_title, subtitle) if part)

        records.append(
            PaperRecord(
                paper_id=paper_id,
                title=title,
                summary=summary,
                authors=_author_names(item),
                categories=categories,
                primary_category=primary_category,
                published=published,
                updated=_updated_date(item),
                abs_url=str(item.get("URL") or ""),
                pdf_url=_pdf_url(item),
                comment=comment,
            )
        )

    return records


def fetch_source_records(settings: Settings) -> list[PaperRecord]:
    """Fetch Crossref records, persist the raw response, and persist parsed records."""
    today_str = date.today().isoformat()
    filter_str = settings.source_filter
    if "until-pub-date" not in filter_str:
        filter_str = f"{filter_str},until-pub-date:{today_str}"

    headers = {
        "Accept": "application/json",
        "User-Agent": "day10-data-observability-lab/0.1 (educational use)",
    }

    target_count = settings.max_results
    all_records: list[PaperRecord] = []
    seen_ids: set[str] = set()
    raw_payloads: list[dict] = []
    all_raw_items: list[dict] = []

    batch_size = max(50, target_count)
    offset = 0
    max_pages = 10

    for page in range(max_pages):
        if len(all_records) >= target_count:
            break

        params = {
            "query": settings.source_query,
            "filter": filter_str,
            "rows": batch_size,
            "offset": offset,
            "sort": "score",
            "order": "desc",
        }

        response: requests.Response | None = None
        last_error: Exception | None = None
        for attempt in range(5):
            try:
                response = requests.get(
                    CROSSREF_API_URL,
                    params=params,
                    headers=headers,
                    timeout=30,
                )
                if response.status_code not in RETRYABLE_STATUS_CODES:
                    response.raise_for_status()
                    break
                last_error = RuntimeError(
                    f"Crossref returned retryable status {response.status_code}: {response.text[:200]}"
                )
            except requests.RequestException as exc:
                last_error = exc

            if attempt < 4:
                retry_after = 0
                if response is not None:
                    try:
                        retry_after = int(response.headers.get("Retry-After", "0"))
                    except ValueError:
                        retry_after = 0
                time.sleep(max(retry_after, 2**attempt))
        else:
            if not all_records:
                raise RuntimeError(f"Crossref request failed after retries: {last_error}") from last_error
            break

        if response is None:
            break

        payload = response.json()
        raw_payloads.append(payload)
        items = payload.get("message", {}).get("items", []) if isinstance(payload, dict) else []
        if not items:
            break

        all_raw_items.extend(items)
        batch_records = parse_crossref_payload(payload)

        for rec in batch_records:
            if rec.paper_id.lower() not in seen_ids:
                seen_ids.add(rec.paper_id.lower())
                all_records.append(rec)

        offset += batch_size

    if not all_records:
        raise RuntimeError(
            "Crossref returned no usable records. Check SOURCE query/filter or inspect the raw response artifact."
        )

    records = all_records[:target_count]

    composite_payload = {
        "status": "ok",
        "message-type": "work-list",
        "message": {
            "total-results": len(all_raw_items),
            "items": all_raw_items,
        },
    }
    write_json(settings.paths.raw_api_response, composite_payload)
    write_json(settings.paths.raw_records_json, [asdict(record) for record in records])
    return records



def load_raw_records(path: Path) -> list[PaperRecord]:
    """Load a persisted raw-record snapshot."""
    payload = read_json(path)
    if not isinstance(payload, list):
        raise ValueError(f"Expected a JSON list in {path}, got {type(payload).__name__}.")

    records: list[PaperRecord] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        records.append(
            PaperRecord(
                paper_id=str(item.get("paper_id") or ""),
                title=str(item.get("title") or ""),
                summary=str(item.get("summary") or ""),
                authors=[str(value) for value in item.get("authors") or []],
                categories=[str(value) for value in item.get("categories") or []],
                primary_category=str(item.get("primary_category") or ""),
                published=str(item.get("published") or ""),
                updated=str(item.get("updated") or ""),
                abs_url=str(item.get("abs_url") or ""),
                pdf_url=str(item.get("pdf_url") or ""),
                comment=str(item.get("comment") or ""),
            )
        )
    return records


if __name__ == "__main__":
    settings = load_settings()
    print("Fetching papers from Crossref API...")
    print(f"Query: {settings.source_query}")
    print(f"Filter: {settings.source_filter}")
    records = fetch_source_records(settings)
    print(f"Successfully fetched and parsed {len(records)} records.")
    print(f"Raw API response saved to: {settings.paths.raw_api_response}")
    print(f"Raw records saved to: {settings.paths.raw_records_json}")

