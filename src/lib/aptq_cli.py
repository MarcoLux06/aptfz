"""aptq: non-interactive query. Prints matching package names, one per line."""
from __future__ import annotations

import sys
from typing import List

import common
import config
from render import bytes_to_human
import query


def show_usage() -> None:
    print("Usage: aptq [OPTIONS]")
    print()
    print("Non-interactive package query (no fzf). Prints one package name per")
    print("line, or with -t the total installed size. Output is plain text,")
    print("meant for pipes and scripts.")
    print()
    print(common.SHARED_HELP)
    print()
    print("Other:")
    print("  -h, --help          Show this help message")
    print("  --version           Show the aptfz version")
    print()
    print("The package cache refreshes itself whenever dpkg or apt-mark change")
    print("what is installed; there is nothing to refresh by hand.")


def main(argv: List[str]) -> int:
    parser = common.new_parser("Query installed apt packages")
    args = parser.parse_args(argv)

    if args.help:
        show_usage()
        return 0
    if args.version:
        print(f"aptfz {config.__version__}")
        return 0

    rows = common.load_and_select(args)
    if args.totalsize:
        print(bytes_to_human(query.total_size(rows)))
        return 0
    for row in rows:
        print(row['Name'])
    return 0


def run() -> int:
    return common.guarded(main, sys.argv[1:])
