"""Render one package's preview. Run as a script by fzf for its preview pane:

    preview.py [--color=always|never|auto] [--hide-notes] [--] PACKAGE

Always goes through the same cache as everything else (so a preview can never
disagree with the list next to it) and through render.render_preview.
"""
from __future__ import annotations

import argparse
import os
import sys

import cache
import notes
from render import render_preview


def main() -> int:
    parser = argparse.ArgumentParser(usage=argparse.SUPPRESS)
    parser.add_argument('--hide-notes', action='store_true')
    parser.add_argument('--color', choices=('always', 'never', 'auto'), default='auto')
    parser.add_argument('pkg')
    args = parser.parse_args()

    use_color = (args.color == 'always'
                 or (args.color == 'auto' and sys.stdout.isatty()
                     and 'NO_COLOR' not in os.environ))
    try:
        packages = cache.load_packages()
    except RuntimeError as e:
        print(f"Error: {e}")
        return 1

    name = args.pkg.strip()
    record = next((p for p in packages if p['Name'] == name), None)
    if record is None:
        return 0
    note = None if args.hide_notes else notes.get_note(name)
    print(render_preview(record, use_color=use_color, note=note))
    return 0


if __name__ == '__main__':
    sys.exit(main())
