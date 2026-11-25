"""Shared path configuration for the aptfz toolset.

Every path honors the XDG base-directory variables and can additionally be
overridden with an environment variable. Unlike pacfz, paths are resolved at
*call time*, not import time, so an override set after import is honored.

    APTFZ_CACHE_PATH   package cache (default: $XDG_CACHE_HOME/aptfz/packages.json)
    APTFZ_NOTES_PATH   per-package notes (default: $XDG_DATA_HOME/aptfz/notes.json)

Two more overrides exist mainly for the test suite: they change which files
are stat()ed to decide whether the cache is still fresh.

    APTFZ_STATUS_PATH  dpkg status file     (default: /var/lib/dpkg/status)
    APTFZ_STATES_PATH  apt extended states  (default: /var/lib/apt/extended_states)
"""
from __future__ import annotations

import os

# version tag (also used to invalidate caches written by other versions)
__version__ = "0.1.1"


def _xdg(env_var: str, default: str) -> str:
    """Return $env_var if set and non-empty, else the expanded default."""
    return os.environ.get(env_var) or os.path.expanduser(default)


def cache_path() -> str:
    """Path to the package cache file."""
    override = os.environ.get('APTFZ_CACHE_PATH')
    if override:
        return override
    return os.path.join(_xdg('XDG_CACHE_HOME', '~/.cache'), 'aptfz', 'packages.json')


def notes_path() -> str:
    """Path to the user-notes file."""
    override = os.environ.get('APTFZ_NOTES_PATH')
    if override:
        return override
    return os.path.join(_xdg('XDG_DATA_HOME', '~/.local/share'), 'aptfz', 'notes.json')


def status_path() -> str:
    """dpkg's status database; changes whenever a package is (un)installed."""
    return os.environ.get('APTFZ_STATUS_PATH') or '/var/lib/dpkg/status'


def states_path() -> str:
    """apt's extended_states; changes whenever manual/auto marks change."""
    return os.environ.get('APTFZ_STATES_PATH') or '/var/lib/apt/extended_states'
