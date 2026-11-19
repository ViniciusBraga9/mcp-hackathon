"""Find documents with passages similar in meaning to a query."""

from __future__ import annotations

import math
import os
from itertools import islice
from typing import Iterator

from openai import APIError, OpenAI

from indexer import IndexedFile
from search import SearchHit, format_results, read_searchable_text, validate_limit


EMBEDDING_MODEL = "text-embedding-3-small"
CHUNK_CHARACTERS = 1500
CHUNK_OVERLAP = 250
BATCH_SIZE = 32


class SemanticSearchError(RuntimeError):
    """The embedding service could not complete the search."""


def _passages(files: tuple[IndexedFile, ...]) -> Iterator[tuple[IndexedFile, str]]:
    for item in files:
        content = read_searchable_text(item)
        for start in range(0, len(content), CHUNK_CHARACTERS - CHUNK_OVERLAP):
            end = start + CHUNK_CHARACTERS
            passage = content[start:end].strip()
            if passage:
                yield item, passage
            if end >= len(content):
                break


def _embed(client: OpenAI, passages: list[str]) -> list[list[float]]:
    response = client.embeddings.create(model=EMBEDDING_MODEL, input=passages, encoding_format="float")
    data = sorted(response.data, key=lambda item: item.index)
    if [item.index for item in data] != list(range(len(passages))):
        raise SemanticSearchError("The embedding service returned incomplete results.")
    return [item.embedding for item in data]


def _unit_vector(vector: list[float]) -> list[float]:
    norm = math.hypot(*vector)
    if not norm or not math.isfinite(norm):
        raise SemanticSearchError("The embedding service returned an invalid vector.")
    return [component / norm for component in vector]


def search_semantic(
    files: tuple[IndexedFile, ...], query: str, limit: int = 10
) -> dict[str, object]:
    """Rank documents by cosine similarity to their best matching passage."""
    query_text = query.strip()
    if not query_text:
        raise ValueError("The search query cannot be empty.")
    if len(query_text.encode("utf-8")) > 6000:
        raise ValueError("The semantic search query must be at most 6000 UTF-8 bytes.")
    validate_limit(limit)

    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise SemanticSearchError("Set OPENAI_API_KEY to use semantic search.")

    passages = _passages(files)
    batch = list(islice(passages, BATCH_SIZE))
    if not batch:
        return format_results(query, [], limit, semantic=True)

    hits: dict[str, SearchHit] = {}
    try:
        with OpenAI(api_key=api_key, timeout=20, max_retries=1) as client:
            query_vector = _unit_vector(_embed(client, [query_text])[0])
            while batch:
                vectors = _embed(client, [passage for _, passage in batch])
                for (item, passage), embedding in zip(batch, vectors, strict=True):
                    if len(embedding) != len(query_vector):
                        raise SemanticSearchError("The embedding service returned incompatible vectors.")
                    score = sum(
                        left * right for left, right in zip(query_vector, _unit_vector(embedding))
                    )
                    best = hits.get(item.path)
                    if best is None or score > best[0]:
                        snippet = passage[:280].rstrip() + ("..." if len(passage) > 280 else "")
                        hits[item.path] = (score, item, snippet)
                batch = list(islice(passages, BATCH_SIZE))
    except APIError as error:
        status = getattr(error, "status_code", None)
        message = f"The OpenAI embedding service returned HTTP {status}." if status else (
            "Unable to connect to the OpenAI embedding service."
        )
        raise SemanticSearchError(message) from None
    return format_results(query, list(hits.values()), limit, semantic=True)
