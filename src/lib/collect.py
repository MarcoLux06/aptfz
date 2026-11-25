"""Read the installed-package set from dpkg and apt.

Sources:
  * ``dpkg-query -W -f ...``    metadata, one machine-readable record per package
  * ``apt-mark showmanual``     install reason: explicitly installed
  * ``apt-mark showauto``       install reason: installed as a dependency

The parsing functions are pure (text in, records out) so they can be unit
tested with crafted input; only ``collect_packages`` touches subprocesses.

Package identity ("Name") is the name apt itself accepts and prints: the bare
package name for native-architecture and ``all`` packages, ``name:arch`` for
packages of a foreign architecture (multiarch). Note this is *not* dpkg-query's
``${binary:Package}``, which also qualifies native Multi-Arch: same packages.
"""
from __future__ import annotations

import logging
import subprocess
from typing import Dict, List, Optional, Set

import depgraph
from schema import (FIELD_ORDER, REASON_AUTO, REASON_MANUAL, REASON_UNKNOWN,
                    bare_name)

CMD_TIMEOUT = 60  # seconds
logger = logging.getLogger(__name__)

# Real control characters, passed straight to dpkg-query (it does not
# understand \x1f-style escapes). Unlikely to occur inside field values.
_FIELD_SEP = '\x1f'
_RECORD_SEP = '\x1e'

# (dpkg-query field, record key)
_DPKG_FIELDS = [
    ('Package', '_package'),
    ('Architecture', 'Architecture'),
    ('Version', 'Version'),
    ('Installed-Size', 'Installed_Size'),
    ('Depends', 'Depends_On'),
    ('Pre-Depends', 'Pre_Depends'),
    ('Recommends', 'Recommends'),
    ('Suggests', 'Suggests'),
    ('Conflicts', 'Conflicts'),
    ('Breaks', 'Breaks'),
    ('Provides', 'Provides'),
    ('Replaces', 'Replaces'),
    ('Section', 'Section'),
    ('Priority', 'Priority'),
    ('Maintainer', 'Maintainer'),
    ('Homepage', 'Homepage'),
    ('Source', 'Source'),
    ('Essential', 'Essential'),
    ('Multi-Arch', 'Multi_Arch'),
    ('db:Status-Abbrev', '_status'),
    ('binary:Synopsis', 'Description'),
]

DPKG_QUERY_FORMAT = _FIELD_SEP.join(f'${{{f}}}' for f, _ in _DPKG_FIELDS) + _RECORD_SEP


def _squash(value: str) -> str:
    """Collapse all whitespace (dpkg may fold long fields over lines)."""
    return ' '.join(value.split())


def package_key(name: str, arch: str, native_arch: str) -> str:
    """The identity apt uses: bare for native/all, name:arch otherwise."""
    if arch in (native_arch, 'all') or not arch:
        return name
    return f'{name}:{arch}'


def parse_dpkg_query(output: str, native_arch: str) -> List[Dict]:
    """Parse the output of ``dpkg-query -W -f DPKG_QUERY_FORMAT``.

    Packages that are not actually installed (removed-with-config-left ``rc``,
    never-installed ``un`` placeholders) are skipped. Malformed records are
    skipped with a warning rather than aborting the whole listing.
    """
    records: List[Dict] = []
    for chunk in output.split(_RECORD_SEP):
        if not chunk.strip():
            continue
        fields = chunk.split(_FIELD_SEP)
        if len(fields) != len(_DPKG_FIELDS):
            logger.warning("Skipping malformed dpkg-query record (%d fields)", len(fields))
            continue
        raw = {key: value for (_, key), value in zip(_DPKG_FIELDS, fields)}

        status = raw['_status'].strip()[1:2]  # want, STATUS, error-flag
        if status in ('n', 'c'):  # not-installed, config-files
            continue

        name = _squash(raw['_package'])
        if not name:
            continue
        arch = _squash(raw['Architecture'])

        rec: Dict = {col: '' for col in FIELD_ORDER}
        for _, key in _DPKG_FIELDS:
            if key in rec:
                rec[key] = _squash(raw[key])
        rec['Name'] = package_key(name, arch, native_arch)
        try:
            # dpkg's Installed-Size is an integer number of KiB.
            rec['Installed_Size'] = int(rec['Installed_Size'] or 0) * 1024
        except ValueError:
            rec['Installed_Size'] = 0
        rec['Install_Reason'] = REASON_UNKNOWN
        records.append(rec)
    return records


def parse_name_list(text: str) -> Set[str]:
    """Parse ``apt-mark showmanual/showauto`` output (one name per line)."""
    return {line.strip() for line in text.splitlines() if line.strip()}


def assign_install_reasons(records: List[Dict], manual: Set[str], auto: Set[str]) -> None:
    """Set Install_Reason on every record from the two apt-mark sets."""
    for rec in records:
        key = rec['Name']
        candidates = {key, f"{bare_name(key)}:{rec['Architecture']}"}
        if candidates & manual:
            rec['Install_Reason'] = REASON_MANUAL
        elif candidates & auto:
            rec['Install_Reason'] = REASON_AUTO
        else:
            rec['Install_Reason'] = REASON_UNKNOWN


# ---------------------------------------------------------------------------
# subprocess I/O
# ---------------------------------------------------------------------------
def _run(cmd: List[str], timeout: int = CMD_TIMEOUT) -> str:
    env = {'LC_ALL': 'C', 'PATH': '/usr/sbin:/usr/bin:/sbin:/bin'}
    try:
        result = subprocess.run(
            cmd, capture_output=True, timeout=timeout, check=False, env=env,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"{cmd[0]} timed out after {timeout}s")
    except FileNotFoundError:
        raise RuntimeError(
            f"'{cmd[0]}' not found. aptfz needs a Debian-based system (dpkg and apt)."
        )
    if result.returncode != 0:
        stderr = result.stderr.decode('utf-8', 'replace').strip()
        raise RuntimeError(f"{' '.join(cmd[:2])} failed with code {result.returncode}: {stderr}")
    return result.stdout.decode('utf-8', 'replace')


def native_architecture() -> str:
    return _run(['dpkg', '--print-architecture']).strip()


def collect_packages(native_arch: Optional[str] = None) -> List[Dict]:
    """Collect every installed package as a normalized record.

    Raises:
        RuntimeError: if dpkg/apt are missing or a command fails.
    """
    native = native_arch or native_architecture()
    records = parse_dpkg_query(_run(['dpkg-query', '-W', '-f', DPKG_QUERY_FORMAT]), native)
    if not records:
        raise RuntimeError("dpkg-query reported no installed packages")
    manual = parse_name_list(_run(['apt-mark', 'showmanual']))
    auto = parse_name_list(_run(['apt-mark', 'showauto']))
    assign_install_reasons(records, manual, auto)
    depgraph.compute_reverse_dependencies(records)
    return records
