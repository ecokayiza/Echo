from __future__ import annotations

from pathlib import Path
from typing import Any

from langchain_core.tools import tool

from ..config import Config

MAX_LIST_RESULTS = 200
MAX_READ_CHARS = 50_000
MAX_WRITE_CHARS = 500_000


@tool
def workspace_list_files(path: str = ".", recursive: bool = False, max_results: int = 100) -> dict[str, Any]:
    """List files under the bounded workspace root."""
    try:
        root = _workspace_root()
        target = _resolve_workspace_path(path or ".")
        limit = max(1, min(int(max_results or 100), MAX_LIST_RESULTS))
        if not target.exists():
            return _context("workspace_list_files", [], error=f"Workspace path does not exist: {_relative_path(target, root)}")

        paths = [target] if target.is_file() else _iter_children(target, recursive=bool(recursive), limit=limit)
        items = [_file_item(item, root) for item in paths[:limit]]
        return _context("workspace_list_files", items)
    except Exception as exc:
        return _context("workspace_list_files", [], error=str(exc))


@tool
def workspace_read_file(file_path: str, max_chars: int = 20_000) -> dict[str, Any]:
    """Read one UTF-8 text file from the bounded workspace root."""
    try:
        path = _resolve_workspace_path(file_path)
        root = _workspace_root()
        if not path.exists():
            return _context("workspace_read_file", [], error=f"Workspace file does not exist: {_relative_path(path, root)}")
        if not path.is_file():
            return _context("workspace_read_file", [], error=f"Workspace path is not a file: {_relative_path(path, root)}")

        limit = max(1, min(int(max_chars or 20_000), MAX_READ_CHARS))
        content = _read_text(path)
        truncated = len(content) > limit
        return _context(
            "workspace_read_file",
            [
                {
                    "title": _relative_path(path, root),
                    "content": content[:limit],
                    "file_path": _relative_path(path, root),
                    "size": path.stat().st_size,
                    "truncated": truncated,
                }
            ],
        )
    except UnicodeDecodeError:
        return _context("workspace_read_file", [], error="Workspace file is not valid UTF-8 text.")
    except Exception as exc:
        return _context("workspace_read_file", [], error=str(exc))


@tool
def workspace_write_file(file_path: str, content: str, overwrite: bool = False) -> dict[str, Any]:
    """Create or overwrite one UTF-8 text file in the bounded workspace root."""
    try:
        path = _resolve_workspace_path(file_path)
        root = _workspace_root()
        text = str(content)
        if len(text) > MAX_WRITE_CHARS:
            return _context("workspace_write_file", [], error=f"Content exceeds {MAX_WRITE_CHARS} characters.")
        if path.exists() and not path.is_file():
            return _context("workspace_write_file", [], error=f"Workspace path is not a file: {_relative_path(path, root)}")
        if path.exists() and not overwrite:
            return _context(
                "workspace_write_file",
                [],
                error=f"Workspace file already exists: {_relative_path(path, root)}. Pass overwrite=True to replace it.",
            )

        path.parent.mkdir(parents=True, exist_ok=True)
        _write_text(path, text)
        return _context(
            "workspace_write_file",
            [
                {
                    "title": _relative_path(path, root),
                    "content": f"Wrote {len(text)} characters.",
                    "file_path": _relative_path(path, root),
                    "size": path.stat().st_size,
                }
            ],
        )
    except Exception as exc:
        return _context("workspace_write_file", [], error=str(exc))


@tool
def workspace_edit_file(file_path: str, old_text: str, new_text: str, expected_replacements: int = 1) -> dict[str, Any]:
    """Edit one UTF-8 workspace file by replacing exact text."""
    try:
        path = _resolve_workspace_path(file_path)
        root = _workspace_root()
        if not path.exists():
            return _context("workspace_edit_file", [], error=f"Workspace file does not exist: {_relative_path(path, root)}")
        if not path.is_file():
            return _context("workspace_edit_file", [], error=f"Workspace path is not a file: {_relative_path(path, root)}")

        old = str(old_text)
        new = str(new_text)
        if not old:
            return _context("workspace_edit_file", [], error="old_text cannot be empty.")
        expected = max(1, int(expected_replacements or 1))
        content = _read_text(path)
        replacements = content.count(old)
        if replacements != expected:
            return _context(
                "workspace_edit_file",
                [],
                error=f"Expected {expected} replacement(s), found {replacements}. Read the file and use a more exact old_text.",
            )
        next_content = content.replace(old, new, expected)
        if len(next_content) > MAX_WRITE_CHARS:
            return _context("workspace_edit_file", [], error=f"Edited content exceeds {MAX_WRITE_CHARS} characters.")

        _write_text(path, next_content)
        return _context(
            "workspace_edit_file",
            [
                {
                    "title": _relative_path(path, root),
                    "content": f"Applied {expected} replacement(s).",
                    "file_path": _relative_path(path, root),
                    "size": path.stat().st_size,
                }
            ],
        )
    except UnicodeDecodeError:
        return _context("workspace_edit_file", [], error="Workspace file is not valid UTF-8 text.")
    except Exception as exc:
        return _context("workspace_edit_file", [], error=str(exc))


def _workspace_root() -> Path:
    root = Config.WORKSPACE_DIR.resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _resolve_workspace_path(value: str) -> Path:
    raw = str(value or "").strip().replace("\\", "/")
    if not raw:
        raise ValueError("Workspace path cannot be empty.")
    raw_path = Path(raw)
    if raw_path.is_absolute() or raw_path.drive or raw_path.anchor:
        raise ValueError("Workspace path must be relative to the workspace root.")

    root = _workspace_root()
    resolved = (root / raw_path).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError("Workspace path must stay inside the workspace root.") from exc
    return resolved


def _iter_children(path: Path, *, recursive: bool, limit: int) -> list[Path]:
    iterator = path.rglob("*") if recursive else path.iterdir()
    return sorted(iterator, key=lambda item: (not item.is_dir(), str(item).lower()))[:limit]


def _file_item(path: Path, root: Path) -> dict[str, Any]:
    relative = _relative_path(path, root)
    if path.is_dir():
        return {
            "title": relative,
            "content": "Directory",
            "file_path": relative,
            "is_dir": True,
        }
    return {
        "title": relative,
        "content": f"File, {path.stat().st_size} bytes",
        "file_path": relative,
        "is_dir": False,
        "size": path.stat().st_size,
    }


def _relative_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root).as_posix() or "."
    except ValueError:
        return path.name


def _read_text(path: Path) -> str:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return handle.read()


def _write_text(path: Path, content: str):
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(content)


def _context(skill_name: str, items: list[dict[str, Any]], *, error: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": "context",
        "skill_name": skill_name,
        "items": items,
    }
    if error:
        payload["error"] = error
    return payload
