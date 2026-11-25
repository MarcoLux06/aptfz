"""Reverse-dependency computation.

dpkg only stores *forward* dependencies. "Required By" and friends are
computed here by inverting Depends/Pre-Depends/Recommends/Suggests across the
installed set. This module is pure: records in, records mutated, no I/O.

Resolution rules (deliberately conservative: when in doubt, draw the edge, so
a package is never wrongly reported as "required by nothing"):

* ``a | b`` alternatives: every alternative that is installed gets an edge.
* Virtual packages: a dependency on a name nobody installs under that name is
  resolved through installed packages' ``Provides``.
* Version constraints (``>= 1.2``) are ignored.
* Multiarch: an unqualified dependency prefers candidates of the depender's
  own architecture (or ``all``); ``:any`` matches every architecture; an
  explicit ``:amd64`` restricts to that architecture (or ``all``).
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from schema import bare_name

Alternative = Tuple[str, Optional[str]]  # (package name, arch qualifier or None)

_STRIP_RE = re.compile(r'\([^)]*\)|\[[^\]]*\]|<[^>]*>')
_ALT_RE = re.compile(r'^([A-Za-z0-9][A-Za-z0-9+.\-]*)(?::([A-Za-z0-9\-]+))?')


def parse_dependency_field(value: str) -> List[List[Alternative]]:
    """Parse a Depends-style field into clauses of alternatives.

    "libc6 (>= 2.34), a | b:any" -> [[('libc6', None)], [('a', None), ('b', 'any')]]
    """
    clauses: List[List[Alternative]] = []
    if not value:
        return clauses
    for clause in value.split(','):
        alternatives: List[Alternative] = []
        for alt in clause.split('|'):
            alt = _STRIP_RE.sub('', alt).strip()
            match = _ALT_RE.match(alt)
            if match:
                alternatives.append((match.group(1), match.group(2)))
        if alternatives:
            clauses.append(alternatives)
    return clauses


def _resolve(name: str, qualifier: Optional[str], depender: dict,
             by_name: Dict[str, List[dict]], provided: Dict[str, List[dict]]) -> List[dict]:
    """Installed packages that could satisfy ``name`` for ``depender``."""
    candidates: List[dict] = []
    seen = set()
    for pkg in list(by_name.get(name, ())) + list(provided.get(name, ())):
        if id(pkg) not in seen:
            seen.add(id(pkg))
            candidates.append(pkg)
    if not candidates:
        return candidates

    if qualifier == 'any' or qualifier == 'native':
        return candidates
    if qualifier:
        return [c for c in candidates if c['Architecture'] in (qualifier, 'all')]

    arch = depender['Architecture']
    if len(candidates) > 1 and arch != 'all':
        same = [c for c in candidates if c['Architecture'] in (arch, 'all')]
        if same:
            return same
    return candidates


# (record field, which reverse map it feeds)
_SOURCES = (
    ('Depends_On', 'required'),
    ('Pre_Depends', 'required'),
    ('Recommends', 'recommended'),
    ('Suggests', 'suggested'),
)


def compute_reverse_dependencies(records: List[dict]) -> None:
    """Fill Required_By, Recommended_By and Suggested_By on every record."""
    by_name: Dict[str, List[dict]] = {}
    provided: Dict[str, List[dict]] = {}
    for rec in records:
        by_name.setdefault(bare_name(rec['Name']), []).append(rec)
    for rec in records:
        for clause in parse_dependency_field(rec['Provides']):
            for name, _qualifier in clause:
                provided.setdefault(name, []).append(rec)

    reverse: Dict[str, Dict[str, set]] = {
        'required': {}, 'recommended': {}, 'suggested': {},
    }
    for rec in records:
        for field, kind in _SOURCES:
            for clause in parse_dependency_field(rec[field]):
                for name, qualifier in clause:
                    for target in _resolve(name, qualifier, rec, by_name, provided):
                        if target is not rec:
                            reverse[kind].setdefault(target['Name'], set()).add(rec['Name'])

    for rec in records:
        key = rec['Name']
        rec['Required_By'] = ', '.join(sorted(reverse['required'].get(key, ())))
        rec['Recommended_By'] = ', '.join(sorted(reverse['recommended'].get(key, ())))
        rec['Suggested_By'] = ', '.join(sorted(reverse['suggested'].get(key, ())))
