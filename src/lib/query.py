"""The query engine: filter, invert, search, sort and total over records.

Pure functions over the list of package dicts from ``cache.load_packages``.
Nothing here prints, reads argv, or touches the filesystem. This is the one
place filter semantics live; ``aptq`` and ``aptfz`` both go through it.

Model (identical to pacfz): "precondition" conditions are always AND'd
together; an optional second group is AND'd internally and negated as a unit
(``-v FILTER -v FILTER2`` means NOT(A AND B), not NOT(A) AND NOT(B)).
"""
from __future__ import annotations

from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from schema import (FIELD_ORDER, REASON_AUTO, REASON_MANUAL, resolve_field_name)

Record = Dict
Predicate = Callable[[Record], bool]

SIZE_FIELD = 'Installed_Size'
NAME_FIELD = 'Name'

# Canned filters.
FILTERS: Dict[str, Predicate] = {
    'explicit': lambda r: r['Install_Reason'] == REASON_MANUAL,
    'deps': lambda r: r['Install_Reason'] == REASON_AUTO,
    'notadep': lambda r: not r['Required_By'],
    'notoptdep': lambda r: not r['Recommended_By'] and not r['Suggested_By'],
}

# Every short letter / long spelling -> FILTERS key, for -v/--invert FILTER.
CANNED_FILTER_ALIASES = {
    'e': 'explicit', 'explicit': 'explicit',
    'd': 'deps', 'deps': 'deps',
    'n': 'notadep', 'notadep': 'notadep',
    'k': 'notoptdep', 'notoptdep': 'notoptdep',
}

# Phrase per canned filter, for the sentence -t prints in aptfz.
FILTER_PHRASES = {
    'explicit': 'manually installed',
    'deps': 'automatically installed',
    'notadep': 'that nothing requires',
    'notoptdep': 'that nothing recommends or suggests',
}


def resolve_canned_filter_name(name: str) -> str:
    """Resolve a -v/--invert FILTER argument to its FILTERS key.

    Raises:
        ValueError: if the name doesn't match any canned filter.
    """
    key = CANNED_FILTER_ALIASES.get(name.strip().lower())
    if key is None:
        valid = ', '.join(sorted(set(CANNED_FILTER_ALIASES.values())))
        raise ValueError(
            f"Unknown filter '{name}' for -v/--invert. Valid filters: {valid}"
        )
    return key


def _field_predicate(col: str, value: str, exact: bool) -> Predicate:
    if exact:
        return lambda r: str(r[col]) == value
    needle = value.casefold()
    return lambda r: needle in str(r[col]).casefold()


def _any_field_predicate(value: str, exact: bool) -> Predicate:
    if exact:
        return lambda r: any(str(r[c]) == value for c in FIELD_ORDER)
    needle = value.casefold()
    return lambda r: any(needle in str(r[c]).casefold() for c in FIELD_ORDER)


def _negate(pred: Predicate) -> Predicate:
    return lambda r: not pred(r)


def build_predicate(where_clauses: Optional[Sequence[str]] = None,
                    invert_clauses: Optional[Sequence[str]] = None,
                    invert_all: bool = False,
                    field_searches: Optional[Sequence[Tuple[str, str]]] = None,
                    any_field_searches: Optional[Sequence[str]] = None,
                    exact_match: bool = False,
                    invert_each: Optional[Sequence[str]] = None) -> Predicate:
    """Combine the active conditions into one predicate.

    Args:
        where_clauses: FILTERS keys applied as preconditions.
        invert_clauses: FILTERS keys AND'd then negated as ONE group.
        invert_each: FILTERS keys each negated independently, AND'd with the rest.
        invert_all: bare ``-v``: where_clauses, field_searches and
            any_field_searches are AND'd together and negated as a whole.
        field_searches: (field, value) pairs from -f.
        any_field_searches: values from -a, each OR'd across all columns.
        exact_match: equality instead of case-insensitive substring for -f/-a.

    Raises:
        ValueError: on unknown field names, or invert_all with nothing to invert.
    """
    conditions: List[Predicate] = [FILTERS[k] for k in (where_clauses or [])]
    for field, value in (field_searches or []):
        conditions.append(_field_predicate(resolve_field_name(field), value, exact_match))
    for value in (any_field_searches or []):
        conditions.append(_any_field_predicate(value, exact_match))

    invert_group: List[Predicate] = []
    base: List[Predicate]
    if invert_all:
        if not conditions:
            raise ValueError(
                "--invert has nothing to invert - combine it with at least one "
                "filter (-e/-d/-n/-k/-f/-a), or use -v FILTER to invert just one "
                "specific filter"
            )
        invert_group, base = conditions, []
    else:
        base = conditions
        invert_group = [FILTERS[k] for k in (invert_clauses or [])]

    for key in (invert_each or []):
        base.append(_negate(FILTERS[key]))
    if invert_group:
        group = list(invert_group)
        base.append(lambda r: not all(p(r) for p in group))

    return lambda r: all(p(r) for p in base)


def select(records: Iterable[Record], *, notes_filter: Optional[str] = None,
           noted: Optional[set] = None, sort_field: Optional[str] = None,
           sort_direction: Optional[str] = None, **predicate_kwargs) -> List[Record]:
    """Filter, then sort. The notes filter is applied outside the inversion
    (as in pacfz, ``-v`` never flips ``--has-note``/``--no-note``).

    ``sort_direction`` is 'ASC', 'DESC' or None (size defaults to DESC,
    everything else to ASC).
    """
    predicate = build_predicate(**predicate_kwargs)
    sort_col = resolve_field_name(sort_field) if sort_field else NAME_FIELD

    rows = [r for r in records if predicate(r)]
    if notes_filter == 'has_note':
        rows = [r for r in rows if r['Name'] in (noted or ())]
    elif notes_filter == 'no_note':
        rows = [r for r in rows if r['Name'] not in (noted or ())]

    descending = (sort_direction or ('DESC' if sort_col == SIZE_FIELD else 'ASC')) == 'DESC'
    if sort_col == SIZE_FIELD:
        key = lambda r: (r[SIZE_FIELD] or 0, r['Name'])
    else:
        key = lambda r: (str(r[sort_col]).casefold(), r['Name'])
    rows.sort(key=key, reverse=descending)
    return rows


def total_size(rows: Iterable[Record]) -> int:
    return sum(r[SIZE_FIELD] or 0 for r in rows)


def describe_filters(*, explicit=False, deps=False, notadep=False, notoptdep=False,
                     has_note=False, no_note=False, field_searches=None,
                     any_field_searches=None, bare_invert=False) -> str:
    """Build the sentence aptfz prints above ``-t``'s number.

    Every active filter contributes its own phrase, so the sentence composes
    for any combination without hand-written cases.
    """
    adjectives = [FILTER_PHRASES[key] for key, on in (
        ('explicit', explicit), ('deps', deps)) if on]

    # Relational filters read as trailing clauses, not adjectives.
    qualifiers = [FILTER_PHRASES[key] for key, on in (
        ('notadep', notadep), ('notoptdep', notoptdep)) if on]
    if has_note:
        qualifiers.append('with a note')
    elif no_note:
        qualifiers.append('without a note')
    for field, value in (field_searches or []):
        qualifiers.append(f'where {field} matches "{value}"')
    for value in (any_field_searches or []):
        qualifiers.append(f'where any field matches "{value}"')

    if not adjectives and not qualifiers and not bare_invert:
        return 'total package size'

    descriptor = ', '.join(adjectives)
    if bare_invert:
        sentence = f"total size of packages NOT matching: {descriptor or 'the above'}"
    else:
        sentence = f"total size of {descriptor} packages" if descriptor else 'total package size'
    if qualifiers:
        sentence += ' ' + ' and '.join(qualifiers)
    return sentence
