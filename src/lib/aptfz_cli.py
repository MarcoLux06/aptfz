"""aptfz: interactive fzf picker with a live preview pane, plus notes editing."""
from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
import sys
from typing import List

import common
import config
import notes
import query
from render import COLORS, bytes_to_human, render_preview

LIB_DIR = os.path.dirname(os.path.abspath(__file__))
PREVIEW_SCRIPT = os.path.join(LIB_DIR, 'preview.py')


def show_usage() -> None:
    print("Usage: aptfz [OPTIONS]")
    print()
    print(common.SHARED_HELP)
    print()
    print("Display Options:")
    print("  --exact             Use exact matching in fzf (-e flag)")
    print("  --hide-notes        Hide user notes in the preview pane")
    print()
    print("Notes:")
    print("  -D <pkg> <note>     Set a note for a package")
    print("  -D <pkg> -d         Delete the note for a package")
    print("  --notes-list        List all packages that have notes")
    print()
    print("Other:")
    print("  -h, --help          Show this help message")
    print("  --version           Show the aptfz version")
    print()
    print("The package cache refreshes itself whenever dpkg or apt-mark change")
    print("what is installed; there is nothing to refresh by hand.")


# ---------------------------------------------------------------------------
# notes (-D / --notes-list); never touches the package cache
# ---------------------------------------------------------------------------
def notes_command(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(usage=argparse.SUPPRESS, add_help=False)
    parser.add_argument('pkg')
    parser.add_argument('note', nargs='?')
    parser.add_argument('-d', '--delete', action='store_true')
    args = parser.parse_args(argv)

    if args.delete:
        if args.note is not None:
            parser.error("-d takes no note text")
        if notes.delete_note(args.pkg):
            print(f"✓ Note deleted for '{args.pkg}'")
        else:
            print(f"No note found for '{args.pkg}'")
    elif args.note is not None:
        notes.set_note(args.pkg, args.note)
        print(f"✓ Note set for '{args.pkg}'")
    else:
        parser.error("provide a note string or -d to delete")
    return 0


def list_notes() -> int:
    rows = notes.list_notes()
    if not rows:
        print("No notes found.")
        return 0
    width = max(len(name) for name, _ in rows)
    for name, note in rows:
        print(f"{name:<{width}}  {note}")
    return 0


# ---------------------------------------------------------------------------
# interactive picker
# ---------------------------------------------------------------------------
def _use_color() -> bool:
    return sys.stdout.isatty() and 'NO_COLOR' not in os.environ


def pick(rows: List[dict], *, exact: bool, hide_notes: bool) -> str:
    """Run fzf over ``rows``; return the chosen package name ('' if none).

    Raises:
        RuntimeError: if fzf is missing or fails.
    """
    if shutil.which('fzf') is None:
        raise RuntimeError(
            "fzf is not installed, but is required for the interactive picker.\n"
            "Install it with: sudo apt install fzf\n"
            "(aptq works without fzf, if you just need non-interactive queries.)"
        )

    # fzf runs this through a shell with {} substituted (and quoted) by fzf.
    preview_cmd = ' '.join([
        shlex.quote(sys.executable), shlex.quote(PREVIEW_SCRIPT), '--color=always',
        *(['--hide-notes'] if hide_notes else []), '--', '{}',
    ])
    opts = ['--height=26', '--preview-window=right,70%', '--preview', preview_cmd]
    if exact:
        opts.append('-e')

    proc = subprocess.run(
        ['fzf', *opts], input='\n'.join(r['Name'] for r in rows) + '\n',
        stdout=subprocess.PIPE, encoding='utf-8',
    )
    if proc.returncode in (1, 130):  # no match / cancelled
        return ''
    if proc.returncode != 0:
        raise RuntimeError(f"fzf exited with code {proc.returncode}")
    return proc.stdout.strip()


def main(argv: List[str]) -> int:
    # Notes commands are routed first, exactly like pacfz: -D collides with
    # nothing in the shared parser, and -d after it means "delete".
    if argv[:1] == ['-D']:
        return notes_command(argv[1:])
    if argv[:1] == ['--notes-list']:
        return list_notes()

    parser = common.new_parser("Interactive explorer for installed apt packages")
    parser.add_argument('--exact', action='store_true')
    parser.add_argument('--hide-notes', action='store_true')
    parser.add_argument('--print-selection', action='store_true')
    args = parser.parse_args(argv)

    if args.help:
        show_usage()
        return 0
    if args.version:
        print(f"aptfz {config.__version__}")
        return 0

    rows = common.load_and_select(args)

    if args.totalsize:
        number = bytes_to_human(query.total_size(rows))
        print(common.describe_total(args) + ':')
        print(f"{COLORS['GREEN']}{number}{COLORS['RESET']}" if _use_color() else number)
        return 0

    if not rows:
        print("No packages found.")
        return 0

    chosen = pick(rows, exact=args.exact, hide_notes=args.hide_notes)
    if not chosen:
        return 0

    # --print-selection powers the shell key bindings: print the bare name
    # instead of a rendered preview so it can be spliced into the command line.
    if args.print_selection:
        print(chosen)
        return 0

    record = next((r for r in rows if r['Name'] == chosen), None)
    if record is None:
        return 0
    note = None if args.hide_notes else notes.get_note(chosen)
    print(render_preview(record, use_color=_use_color(), note=note))
    return 0


def run() -> int:
    return common.guarded(main, sys.argv[1:])
