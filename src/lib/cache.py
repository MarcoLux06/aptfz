"""Self-validating package cache.

The cache is a single JSON file. It stores a *signature* (mtime, size and inode
of dpkg's status file and apt's extended_states) taken just before the data was
collected. Every run compares the stored signature with the current one: if
they match, the cache is served; otherwise the packages are re-collected and
the file is replaced atomically. There is therefore nothing to refresh by hand
and the cache cannot go stale: ``apt install``, ``dpkg -r`` and
``apt-mark manual`` all change one of the two files.

The signature is taken *before* collecting, so if the system changes while a
rebuild is running, the next run simply rebuilds again.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from typing import Callable, Dict, List, Optional

import collect
import config
from schema import FIELD_ORDER

CACHE_FORMAT = 1


def _stat_signature(path: str) -> Optional[List[int]]:
    try:
        st = os.stat(path)
    except OSError:
        return None
    return [st.st_mtime_ns, st.st_size, st.st_ino]


def current_signature() -> Dict[str, Optional[List[int]]]:
    return {
        'status': _stat_signature(config.status_path()),
        'states': _stat_signature(config.states_path()),
    }


def _read_cache(path: str) -> Optional[dict]:
    """Return {'signature', 'packages'} or None if missing/corrupt/foreign."""
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            data = json.load(fh)
        if (data['format'] != CACHE_FORMAT
                or data['version'] != config.__version__
                or data['columns'] != FIELD_ORDER):
            return None
        columns = data['columns']
        packages = [dict(zip(columns, row)) for row in data['rows']]
        return {'signature': data['signature'], 'packages': packages}
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _write_cache(path: str, signature: dict, packages: List[Dict]) -> None:
    """Atomically replace the cache file (readers never see a partial file)."""
    directory = os.path.dirname(path) or '.'
    os.makedirs(directory, exist_ok=True)
    payload = {
        'format': CACHE_FORMAT,
        'version': config.__version__,
        'signature': signature,
        'columns': FIELD_ORDER,
        'rows': [[pkg[col] for col in FIELD_ORDER] for pkg in packages],
    }
    fd, tmp_path = tempfile.mkstemp(prefix='.packages-', suffix='.tmp', dir=directory)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as fh:
            json.dump(payload, fh, separators=(',', ':'))
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


def load_packages(*, cache_file: Optional[str] = None,
                  collector: Optional[Callable[[], List[Dict]]] = None,
                  signature: Optional[dict] = None) -> List[Dict]:
    """Return all installed packages, rebuilding the cache if it is stale.

    A cache that cannot be written (read-only home, full disk) is not fatal:
    the freshly collected data is still returned, with a warning on stderr.

    Raises:
        RuntimeError: if collecting fails (e.g. not a Debian-based system).
    """
    cache_file = cache_file or config.cache_path()
    collector = collector or collect.collect_packages
    sig = signature if signature is not None else current_signature()

    cached = _read_cache(cache_file)
    if cached is not None and cached['signature'] == sig:
        return cached['packages']

    packages = collector()
    try:
        _write_cache(cache_file, sig, packages)
    except OSError as e:
        print(f"aptfz: warning: could not write cache {cache_file}: {e}", file=sys.stderr)
    return packages
