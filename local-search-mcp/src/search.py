"""Rank indexed files by keywords in their paths and UTF-8 contents."""

from __future__ import annotations

import logging
import re
from dataclasses import asdict
from datetime import date
from pathlib import Path

from indexer import IndexedFile, is_within


logger = logging.getLogger(__name__)


TEXT_SUFFIXES = frozenset(
    {
        ".cfg",
        ".csv",
        ".html",
        ".htm",
        ".ini",
        ".json",
        ".log",
        ".md",
        ".py",
        ".rst",
        ".sql",
        ".toml",
        ".txt",
        ".xml",
        ".yaml",
        ".yml",
    }
)
MAX_SEARCH_FILE_BYTES = 1_000_000
SearchHit = tuple[float, IndexedFile, str]


def read_searchable_text(item: IndexedFile) -> str:
    path = Path(item.path)
    if path.suffix.lower() not in TEXT_SUFFIXES:
        return ""
    try:
        path = path.resolve(strict=True)
        if not is_within(path, Path(item.root)) or not path.is_file():
            return ""
        with path.open("rb") as file:
            data = file.read(MAX_SEARCH_FILE_BYTES + 1)
        if len(data) > MAX_SEARCH_FILE_BYTES:
            return ""
        return data.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    except (OSError, UnicodeError) as error:
        logger.warning("Unable to search file contents in %s: %s", path, error)
        return ""


def _parse_date(value: str | None, argument: str) -> str | None:
    if value is None:
        return None
    try:
        if date.fromisoformat(value).isoformat() == value:
            return value
    except ValueError:
        pass
    raise ValueError(f"{argument} must be a valid date in YYYY-MM-DD format.")


def filter_index(
    indexed_files: tuple[IndexedFile, ...],
    extension: str | None = None,
    modified_from: str | None = None,
    modified_to: str | None = None,
) -> tuple[IndexedFile, ...]:
    """Filter by extension and an inclusive UTC modification date range."""
    start = _parse_date(modified_from, "modified_from")
    end = _parse_date(modified_to, "modified_to")
    if start and end and start > end:
        raise ValueError("modified_from must be on or before modified_to.")
    if extension is not None:
        suffix = extension.strip().lower().removeprefix(".")
        if not suffix or any(character in suffix for character in "./\\*?"):
            raise ValueError("Provide a single file extension, such as txt or .txt.")
        extension = f".{suffix}"
    return tuple(
        item
        for item in indexed_files
        if (extension is None or item.extension == extension)
        and (start is None or item.modified_at[:10] >= start)
        and (end is None or item.modified_at[:10] <= end)
    )


def _make_snippet(content: str, terms: list[str], maximum: int = 280) -> str:
    lowered = content.casefold()
    positions = [lowered.find(term) for term in terms if lowered.find(term) >= 0]
    if not positions:
        return ""
    start = max(0, min(positions) - maximum // 3)
    snippet = content[start : start + maximum].strip()
    if start:
        snippet = f"...{snippet}"
    if start + maximum < len(content):
        snippet = f"{snippet}..."
    return snippet


def search_index(
    indexed_files: tuple[IndexedFile, ...], query: str, limit: int = 10, *, allow_empty: bool = False
) -> dict[str, object]:
    """Return ranked matches with metadata and text excerpts."""
    if not query.strip() and not allow_empty:
        raise ValueError("The search query cannot be empty.")
    validate_limit(limit)
    if not query.strip():
        return format_results(query, [(0, item, "") for item in indexed_files], limit)

    terms = list(dict.fromkeys(re.findall(r"\w+", query.casefold())))
    if not terms:
        raise ValueError("The search query must contain at least one searchable word.")

    results: list[SearchHit] = []
    for indexed_file in indexed_files:
        name_and_path = f"{indexed_file.name} {indexed_file.path}".casefold()
        content = read_searchable_text(indexed_file)
        content_lower = content.casefold()
        score = sum(3 for term in terms if term in name_and_path)
        score += sum(1 for term in terms if term in content_lower)
        if score:
            results.append((score, indexed_file, _make_snippet(content, terms)))
    return format_results(query, results, limit)


def validate_limit(limit: int) -> None:
    if not 1 <= limit <= 50:
        raise ValueError("The result limit must be between 1 and 50.")


def format_results(
    query: str, results: list[SearchHit], limit: int, *, semantic: bool = False
) -> dict[str, object]:
    results.sort(key=lambda result: (result[0], result[1].modified_at), reverse=True)
    return {
        "query": query,
        "count": min(len(results), limit),
        "results": [
            {
                **asdict(indexed_file),
                "snippet": snippet,
                **({"similarity": round(score, 6)} if semantic else {}),
            }
            for score, indexed_file, snippet in results[:limit]
        ],
    }
