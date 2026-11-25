"""Everything aptfz and aptq share: flag definitions, the help text for those
flags, and the glue from parsed flags to ``query.select``.

Front-ends add only what is theirs (aptfz: the picker, notes editing; aptq:
nothing) and otherwise just call into here, so a filter fix lands in both.
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Callable, List

import cache
import notes
import query
from schema import FIELD_ORDER

# Printed by both front-ends' -h, so the wording lives in exactly one place.
SHARED_HELP = """\
Filter Options:
  -e, --explicit      Show only manually installed packages
                      (apt-mark showmanual)
  -d, --deps          Show only automatically installed packages
                      (apt-mark showauto)
  -n, --notadep       Not required by any installed package
                      (no Depends/Pre-Depends on it)
  -k, --notoptdep     Not recommended or suggested by any installed package
  --has-note          Only packages that have a user note
  --no-note           Only packages without a user note
  -f, --field F V     Only packages where field F matches value V
                      (repeatable, AND-combined; e.g. -f Name vim)
  -a, --any V         Only packages where any field matches value V
                      (repeatable, AND-combined with everything else)
  -x, --exact-match   Use exact equality (instead of case-insensitive
                      substring) for -f/-a
  -v, --invert [F]    Bare -v inverts the entire result, applied last.
                      -v FILTER (repeatable) inverts only that one canned
                      filter, leaving every other active filter untouched
                      (e.g. -e -v notadep -v notoptdep = manually installed
                      packages where NOT(notadep AND notoptdep)). FILTER is
                      one of: explicit/deps/notadep/notoptdep or their short
                      letters e/d/n/k

Sort Options:
  -s, --sort-by [F]   Sort by field F (default field: Name; bare -s means
                      Installed_Size; --size also still works)
  --asc               Sort ascending (applies to whichever field is sorted)
  --desc              Sort descending (applies to whichever field is sorted)

Size:
  -t, --totalsize     Show total size of the (filtered) packages

Fields (for -f and -s; case-insensitive, '-' '_' and ' ' are equivalent):
  """ + ', '.join(FIELD_ORDER)


class _Parser(argparse.ArgumentParser):
    """argparse that never prints its own usage (we print SHARED_HELP)."""


def new_parser(description: str) -> argparse.ArgumentParser:
    parser = _Parser(
        usage=argparse.SUPPRESS, description=description, add_help=False,
        allow_abbrev=False, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('-h', '--help', action='store_true', dest='help')
    parser.add_argument('--version', action='store_true', dest='version')

    parser.add_argument('-e', '--explicit', action='store_true')
    parser.add_argument('-d', '--deps', action='store_true')
    parser.add_argument('-n', '--notadep', action='store_true')
    parser.add_argument('-k', '--notoptdep', action='store_true')
    parser.add_argument('--has-note', action='store_true')
    parser.add_argument('--no-note', action='store_true')
    parser.add_argument('-f', '--field', nargs=2, metavar=('FIELD', 'VALUE'),
                        action='append', dest='field_searches')
    parser.add_argument('-a', '--any', metavar='VALUE', action='append',
                        dest='any_field_searches')
    parser.add_argument('-x', '--exact-match', action='store_true')
    parser.add_argument('-s', '--size', '--sort-by', nargs='?',
                        const=query.SIZE_FIELD, default=None, metavar='FIELD',
                        dest='sort_field')
    direction = parser.add_mutually_exclusive_group()
    direction.add_argument('--asc', action='store_true')
    direction.add_argument('--desc', action='store_true')
    parser.add_argument('-t', '--totalsize', action='store_true')
    parser.add_argument('-v', '--invert', nargs='?', const='__ALL__', default=None,
                        action='append', metavar='FILTER', dest='invert_args')
    return parser


def select_from_args(args: argparse.Namespace, packages: List[dict]) -> List[dict]:
    """Turn parsed shared flags into a filtered, sorted list of records.

    Raises:
        ValueError: for any invalid flag combination or unknown field/filter.
    """
    where = [name for name, on in (
        ('explicit', args.explicit), ('deps', args.deps),
        ('notadep', args.notadep), ('notoptdep', args.notoptdep)) if on]

    invert_all = False
    invert_clauses = None
    if args.invert_args:
        if '__ALL__' in args.invert_args:
            if len(args.invert_args) > 1:
                raise ValueError(
                    "combine -v either bare (invert everything) or with "
                    "specific filter names, not both."
                )
            invert_all = True
        else:
            invert_clauses = [query.resolve_canned_filter_name(n) for n in args.invert_args]
            where = [f for f in where if f not in invert_clauses]

    notes_filter = 'has_note' if args.has_note else ('no_note' if args.no_note else None)
    noted = notes.packages_with_notes() if notes_filter else None

    return query.select(
        packages,
        where_clauses=where or None,
        invert_clauses=invert_clauses,
        invert_all=invert_all,
        field_searches=args.field_searches,
        any_field_searches=args.any_field_searches,
        exact_match=args.exact_match,
        notes_filter=notes_filter,
        noted=noted,
        sort_field=args.sort_field,
        sort_direction='ASC' if args.asc else ('DESC' if args.desc else None),
    )


def describe_total(args: argparse.Namespace) -> str:
    return query.describe_filters(
        explicit=args.explicit, deps=args.deps, notadep=args.notadep,
        notoptdep=args.notoptdep, has_note=args.has_note, no_note=args.no_note,
        field_searches=args.field_searches, any_field_searches=args.any_field_searches,
        bare_invert=bool(args.invert_args) and '__ALL__' in args.invert_args,
    )


def load_and_select(args: argparse.Namespace) -> List[dict]:
    return select_from_args(args, cache.load_packages())


def guarded(main: Callable[[List[str]], int], argv: List[str]) -> int:
    """Run a front-end's main(), translating expected failures into clean
    ``Error: ...`` lines and exit codes (never tracebacks)."""
    try:
        return main(argv)
    except (ValueError, RuntimeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except BrokenPipeError:
        # A downstream reader (head, less) closed the pipe early. Redirect
        # stdout to devnull so the interpreter's shutdown flush can't raise
        # again, then exit quietly.
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        return 0
    except KeyboardInterrupt:
        return 130
