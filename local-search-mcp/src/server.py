"""MCP server for searching files inside explicitly authorized folders."""

from __future__ import annotations

import json
import os
from pathlib import Path
from threading import Lock
from typing import Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from indexer import (
    FileAccessError,
    IndexedFile,
    build_folder_tree,
    build_index,
    compare_index,
    file_metadata,
    resolve_authorized_directory,
    resolve_authorized_file,
)
from search import TEXT_SUFFIXES, filter_index, search_index
from semantic_search import SemanticSearchError, search_semantic


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MAX_READ_CHARACTERS = 50_000
INDEX_LOCK = Lock()


def _configured_roots() -> tuple[Path, ...]:
    configured = os.environ.get("LOCAL_SEARCH_ROOTS")
    root_values = (
        [value.strip() for value in configured.split(os.pathsep) if value.strip()]
        if configured
        else [str(PROJECT_ROOT / "data")]
    )
    roots: list[Path] = []
    for value in root_values:
        root = Path(value).expanduser().resolve(strict=bool(configured))
        if not root.is_dir() and (configured or root.exists()):
            raise RuntimeError(f"Authorized search path is not a directory: {root}")
        if root not in roots:
            roots.append(root)
    if not roots:
        raise RuntimeError("Configure at least one authorized folder in LOCAL_SEARCH_ROOTS.")
    return tuple(roots)


AUTHORIZED_ROOTS = _configured_roots()
POSTGRES_DSN = os.environ.get("LOCAL_SEARCH_POSTGRES_DSN")

if POSTGRES_DSN:
    from postgres_index import PostgresIndex, PostgresIndexError

    postgres_index = PostgresIndex(POSTGRES_DSN, AUTHORIZED_ROOTS)
    postgres_index.refresh()
    INDEXED_FILES: tuple[IndexedFile, ...] = ()
else:
    postgres_index = None
    INDEXED_FILES = build_index(AUTHORIZED_ROOTS)


def _current_index() -> tuple[IndexedFile, ...]:
    if postgres_index is None:
        return INDEXED_FILES

    try:
        return postgres_index.load()
    except PostgresIndexError as error:
        raise ToolError(str(error)) from error


def _resolve_file(path: str) -> Path:
    try:
        return resolve_authorized_file(path, AUTHORIZED_ROOTS)
    except FileAccessError as error:
        raise ToolError(str(error)) from error


mcp = MCPServer(
    name="local-search",
    instructions=(
        "Search and read files only inside the authorized folders. "
        "Use list_indexed_roots for authorized roots and get_folder_tree for their layout. "
        "Use search_files to find matches, get_file_path for an exact path, get_file_info for metadata, "
        "and read_file only when the user asks for file contents."
    ),
)


@mcp.tool()
def search_files(
    query: str = "",
    limit: int = 10,
    mode: Literal["text", "semantic"] = "text",
    extension: str | None = None,
    modified_from: str | None = None,
    modified_to: str | None = None,
) -> str:
    """Search indexed files by keyword or by similarity in meaning.

    Args:
        query: Keywords or a natural-language description. May be omitted for filter-only text searches.
        limit: Maximum number of results to return, from 1 to 50.
        mode: Text matches names, paths, and text contents. Semantic compares supported UTF-8 document
            passages using OpenAI embeddings and sends the query and candidate passages to OpenAI.
        extension: Optional extension with or without the leading dot, such as pdf or .pdf.
        modified_from: Optional first UTC modification date, inclusive, in YYYY-MM-DD format.
        modified_to: Optional last UTC modification date, inclusive, in YYYY-MM-DD format.
    """
    try:
        files = filter_index(_current_index(), extension, modified_from, modified_to)
        if mode == "semantic":
            results = search_semantic(files, query, limit)
        else:
            filters_given = any(value is not None for value in (extension, modified_from, modified_to))
            results = search_index(files, query, limit, allow_empty=filters_given)
    except (ValueError, SemanticSearchError) as error:
        raise ToolError(str(error)) from error
    return json.dumps(results, ensure_ascii=False)


@mcp.tool()
def get_file_info(path: str) -> str:
    """Get metadata for one file inside an authorized folder.

    Args:
        path: Absolute path or path relative to an authorized folder.
    """
    resolved = _resolve_file(path)
    return json.dumps(file_metadata(resolved), ensure_ascii=False)


@mcp.tool()
def get_file_path(name: str) -> str:
    """Return the absolute path of an authorized file.

    Args:
        name: Exact indexed filename, absolute path, or path relative to an authorized folder.
              Use a relative or absolute path to disambiguate duplicate filenames.
    """
    requested = Path(name)
    if name and name == requested.name and "\x00" not in name:
        matches: set[Path] = set()
        for item in _current_index():
            if Path(item.name) != requested:
                continue
            try:
                matches.add(resolve_authorized_file(item.path, AUTHORIZED_ROOTS))
            except FileAccessError:
                # An indexed file can disappear before the next refresh.
                continue
        if len(matches) > 1:
            raise ToolError("Multiple files have that name. Use search_files to find their paths.")
        if matches:
            return json.dumps({"path": str(matches.pop())}, ensure_ascii=False)
    return json.dumps({"path": str(_resolve_file(name))}, ensure_ascii=False)


@mcp.tool()
def get_folder_tree(path: str | None = None, max_depth: int = 2, max_entries: int = 200) -> str:
    """List the current folders and files within authorized roots.

    Args:
        path: Absolute or root-relative folder path. Omit it to start at all authorized roots.
        max_depth: Number of levels below each starting folder, from 0 to 10.
        max_entries: Maximum combined number of child files and folders, from 1 to 1000.
    """
    if not 0 <= max_depth <= 10:
        raise ToolError("The tree depth must be between 0 and 10.")
    if not 1 <= max_entries <= 1000:
        raise ToolError("The tree entry limit must be between 1 and 1000.")
    try:
        folders = AUTHORIZED_ROOTS if path is None else (
            resolve_authorized_directory(path, AUTHORIZED_ROOTS),
        )
        tree = build_folder_tree(folders, max_depth, max_entries)
    except FileAccessError as error:
        raise ToolError(str(error)) from error
    except (OSError, RuntimeError) as error:
        raise ToolError(f"Unable to list the authorized folders: {error}") from error
    return json.dumps(tree, ensure_ascii=False)


@mcp.tool()
def read_file(path: str, max_characters: int = 10_000) -> str:
    """Read a UTF-8 text file inside an authorized folder.

    Args:
        path: Absolute path or path relative to an authorized folder.
        max_characters: Maximum file-content characters to return, from 1 to 50000.
    """
    if not 1 <= max_characters <= MAX_READ_CHARACTERS:
        raise ToolError(
            f"The character limit must be between 1 and {MAX_READ_CHARACTERS}."
        )

    resolved = _resolve_file(path)
    if resolved.suffix.lower() not in TEXT_SUFFIXES:
        raise ToolError("This file type is not supported for text reading.")
    try:
        with resolved.open("r", encoding="utf-8-sig") as file:
            content = file.read(max_characters + 1)
    except (OSError, UnicodeError) as error:
        raise ToolError(f"Unable to read the requested text file: {error}") from error

    truncated = len(content) > max_characters
    if truncated:
        content = content[:max_characters]
        return f"{content}\n\n[Content truncated at {max_characters} characters.]"
    return content


@mcp.tool()
def refresh_index() -> str:
    """Rescan authorized folders and report absolute paths added, modified, and removed."""
    global INDEXED_FILES
    try:
        if postgres_index is None:
            with INDEX_LOCK:
                files = build_index(AUTHORIZED_ROOTS)
                changes = compare_index(
                    {item.path: item for item in INDEXED_FILES},
                    {item.path: item for item in files},
                )
                INDEXED_FILES = files
                count = len(files)
        else:
            try:
                count, changes = postgres_index.refresh()
            except PostgresIndexError as error:
                raise ToolError(str(error)) from error
    except OSError as error:
        raise ToolError(f"Unable to scan the authorized folders: {error}") from error
    return json.dumps(
        {
            "indexed_files": count,
            "folders": [str(root) for root in AUTHORIZED_ROOTS],
            "changes": changes,
        },
        ensure_ascii=False,
    )


def _indexed_roots() -> list[dict[str, str | int]]:
    files = _current_index()
    folder_counts = {
        str(root): sum(1 for item in files if item.root == str(root))
        for root in AUTHORIZED_ROOTS
    }
    return [{"path": root, "indexed_files": count} for root, count in folder_counts.items()]


@mcp.tool()
def list_indexed_roots() -> str:
    """List the authorized root directories and the number of indexed files in each."""
    return json.dumps({"roots": _indexed_roots()}, ensure_ascii=False)


@mcp.tool()
def list_indexed_folders() -> str:
    """List the authorized folders and indexed file counts for existing clients."""
    return json.dumps({"folders": _indexed_roots()}, ensure_ascii=False)


if __name__ == "__main__":
    mcp.run(transport="stdio")
