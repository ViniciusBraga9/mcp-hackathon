"""Build an index of files and resolve paths within authorized folders."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from stat import S_ISDIR, S_ISREG
from typing import TypedDict


class FileAccessError(ValueError):
    """The requested path cannot be accessed within the authorized folders."""


@dataclass(frozen=True, slots=True)
class IndexedFile:
    path: str
    name: str
    extension: str
    size_bytes: int
    modified_at: str
    root: str


class IndexChanges(TypedDict):
    new: list[str]
    modified: list[str]
    removed: list[str]


def compare_index(
    previous: dict[str, IndexedFile], current: dict[str, IndexedFile]
) -> IndexChanges:
    """Identify changes by absolute path and recorded metadata."""
    return {
        "new": sorted(current.keys() - previous.keys()),
        "modified": sorted(
            path for path in current.keys() & previous.keys() if current[path] != previous[path]
        ),
        "removed": sorted(previous.keys() - current.keys()),
    }


def is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _on_scan_error(error: OSError) -> None:
    # An inaccessible subtree is not evidence that its files were removed.
    if not isinstance(error, FileNotFoundError):
        raise error


def _path_is_direct(path: Path) -> bool:
    try:
        return not path.is_symlink() and path.resolve(strict=True) == path
    except FileNotFoundError:
        return False


def build_index(roots: tuple[Path, ...]) -> tuple[IndexedFile, ...]:
    """Scan authorized roots and return a complete snapshot of file metadata."""
    indexed: dict[Path, IndexedFile] = {}
    for root in roots:
        if not _path_is_direct(root):
            if root.exists():
                raise OSError(f"Authorized folder no longer resolves to its original path: {root}")
            continue
        for directory, subdirectories, filenames in os.walk(root, onerror=_on_scan_error):
            folder = Path(directory)
            subdirectories[:] = [
                name for name in subdirectories if _path_is_direct(folder / name)
            ]
            for name in filenames:
                path = folder / name
                try:
                    resolved = path.resolve(strict=True)
                    if not is_within(resolved, root):
                        continue
                    stat = resolved.stat()
                except FileNotFoundError:
                    continue
                if not S_ISREG(stat.st_mode):
                    continue

                indexed[resolved] = IndexedFile(
                    path=str(resolved),
                    name=resolved.name,
                    extension=resolved.suffix.lower(),
                    size_bytes=stat.st_size,
                    modified_at=datetime.fromtimestamp(
                        stat.st_mtime, tz=timezone.utc
                    ).isoformat(),
                    root=str(root),
                )
    return tuple(
        sorted(indexed.values(), key=lambda item: (item.root.casefold(), item.path.casefold()))
    )


def resolve_authorized_file(path: str, roots: tuple[Path, ...]) -> Path:
    """Resolve a file path and reject paths outside the authorized roots."""
    return _resolve_authorized_path(path, roots, directory=False)


def resolve_authorized_directory(path: str, roots: tuple[Path, ...]) -> Path:
    """Resolve a folder path and reject paths outside the authorized roots."""
    return _resolve_authorized_path(path, roots, directory=True)


def _resolve_authorized_path(path: str, roots: tuple[Path, ...], *, directory: bool) -> Path:
    kind = "directory" if directory else "file"
    if not path.strip() or "\x00" in path:
        raise FileAccessError(f"Provide a valid {kind} path.")
    try:
        requested = Path(path).expanduser()
    except RuntimeError as error:
        raise FileAccessError(f"Unable to expand the requested path: {error}") from error
    candidates = (
        [(requested, roots)]
        if requested.is_absolute()
        else [(root / requested, (root,)) for root in roots]
    )

    matches: list[Path] = []
    inside = False
    wrong_type = False
    for candidate, allowed_roots in candidates:
        try:
            resolved = candidate.resolve(strict=False)
        except (OSError, RuntimeError, ValueError) as error:
            raise FileAccessError(f"Unable to resolve the requested path: {error}") from error
        if not any(is_within(resolved, root) for root in allowed_roots):
            continue

        inside = True
        try:
            resolved = candidate.resolve(strict=True)
            if not any(is_within(resolved, root) for root in allowed_roots):
                raise FileAccessError(f"The requested {kind} is outside the authorized folders.")
            mode = resolved.stat().st_mode
        except FileNotFoundError:
            continue
        except (OSError, RuntimeError) as error:
            raise FileAccessError(f"Unable to access the requested {kind}: {error}") from error

        matches_type = S_ISDIR(mode) if directory else S_ISREG(mode)
        if matches_type:
            matches.append(resolved)
        else:
            wrong_type = True

    unique_matches = list(dict.fromkeys(matches))
    if not inside:
        raise FileAccessError(f"The requested {kind} is outside the authorized folders.")
    if not unique_matches:
        if wrong_type:
            raise FileAccessError(f"The requested path is not a {kind}.")
        raise FileAccessError(f"{kind.capitalize()} not found in the authorized folders.")
    if len(unique_matches) > 1:
        plural = "directories" if directory else "files"
        raise FileAccessError(f"The relative path matches {plural} in multiple authorized folders.")
    return unique_matches[0]


def build_folder_tree(
    folders: tuple[Path, ...], max_depth: int, max_entries: int
) -> dict[str, object]:
    """List current directory contents without following links."""
    remaining = max_entries
    truncated = False

    def walk(folder: Path, depth: int) -> dict[str, object]:
        nonlocal remaining, truncated
        children = []
        if depth < max_depth and _path_is_direct(folder):
            for child in sorted(folder.iterdir(), key=lambda item: (item.name.casefold(), item.name)):
                try:
                    if not _path_is_direct(child):
                        continue
                    mode = child.stat().st_mode
                except FileNotFoundError:
                    continue
                if not (S_ISDIR(mode) or S_ISREG(mode)):
                    continue
                if remaining == 0:
                    truncated = True
                    break
                remaining -= 1
                if S_ISDIR(mode):
                    children.append(walk(child, depth + 1))
                else:
                    children.append({"name": child.name, "path": str(child), "type": "file"})
        return {
            "name": folder.name or folder.anchor,
            "path": str(folder),
            "type": "directory",
            "children": children,
        }

    trees = [
        walk(folder, 0) for folder in folders if _path_is_direct(folder) and folder.is_dir()
    ]
    return {"roots": trees, "truncated": truncated}


def file_metadata(path: Path) -> dict[str, str | int]:
    stat = path.stat()
    return {
        "path": str(path),
        "name": path.name,
        "extension": path.suffix.lower(),
        "size_bytes": stat.st_size,
        "modified_at": datetime.fromtimestamp(
            stat.st_mtime, tz=timezone.utc
        ).isoformat(),
    }
