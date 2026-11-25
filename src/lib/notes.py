"""Per-package notes, stored as one small JSON object {package: note}.

Deliberately separate from the package cache: the cache is disposable and
rebuilt constantly, notes are the user's own data and must never be at risk
from a cache rebuild. Writes are atomic (temp file + os.replace). A notes file
that exists but cannot be parsed is never overwritten: writes refuse with an
error instead, so one bad edit cannot silently destroy every note.

Nothing in this module prints; the CLI layer owns user-facing messages.
"""
from __future__ import annotations

import json
import os
import tempfile
from typing import Dict, List, Optional, Set, Tuple

import config


def _path(path: Optional[str]) -> str:
    return path if path is not None else config.notes_path()


def _load(path: str, strict: bool) -> Dict[str, str]:
    """Load the notes dict. Missing file -> {}. Unreadable/corrupt -> {} when
    not strict (read paths), RuntimeError when strict (write paths)."""
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        if strict:
            raise RuntimeError(
                f"Notes file {path} is unreadable ({e}); refusing to overwrite it. "
                f"Fix or move it aside first."
            )
        return {}
    if not isinstance(data, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in data.items()):
        if strict:
            raise RuntimeError(f"Notes file {path} has an unexpected format; refusing to overwrite it.")
        return {}
    return data


def _save(path: str, notes: Dict[str, str]) -> None:
    directory = os.path.dirname(path) or '.'
    try:
        os.makedirs(directory, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix='.notes-', suffix='.tmp', dir=directory)
    except OSError as e:
        raise RuntimeError(f"Cannot write notes in {directory}: {e}")
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as fh:
            json.dump(notes, fh, indent=2, sort_keys=True, ensure_ascii=False)
            fh.write('\n')
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def get_note(name: str, path: Optional[str] = None) -> Optional[str]:
    """The note for ``name``, or None. Never creates the file."""
    return _load(_path(path), strict=False).get(name) or None


def set_note(name: str, note: str, path: Optional[str] = None) -> None:
    if not note.strip():
        raise RuntimeError("Note is empty; use -d to delete a note.")
    path = _path(path)
    notes = _load(path, strict=True)
    notes[name] = note
    _save(path, notes)


def delete_note(name: str, path: Optional[str] = None) -> bool:
    """Delete a note; returns False if there was none."""
    path = _path(path)
    notes = _load(path, strict=True)
    if name not in notes:
        return False
    del notes[name]
    _save(path, notes)
    return True


def list_notes(path: Optional[str] = None) -> List[Tuple[str, str]]:
    return sorted(_load(_path(path), strict=False).items())


def packages_with_notes(path: Optional[str] = None) -> Set[str]:
    return set(_load(_path(path), strict=False))
