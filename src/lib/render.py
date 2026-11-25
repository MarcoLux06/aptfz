"""Package preview rendering: the one place that formats package data.

Both ``aptfz`` (the fzf preview pane and the final printout) go through
``render_preview``; ``aptq`` deliberately never does, its output is plain
names. Every value passes through ``sanitize_terminal_value`` before being
written anywhere: package metadata is whatever a package's maintainer put in
its control file, which must never be able to inject escape sequences.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional

from schema import REASON_AUTO, REASON_MANUAL

COLORS = {
    'GREEN': '\033[32m',
    'CYAN': '\033[36m',
    'YELLOW': '\033[33m',
    'MAGENTA': '\033[35m',
    'BLUE': '\033[34m',
    'BRIGHT_BLACK': '\033[90m',
    'RESET': '\033[0m',
}
G, C, Y, M, B, K = (COLORS[n] for n in
                    ('GREEN', 'CYAN', 'YELLOW', 'MAGENTA', 'BLUE', 'BRIGHT_BLACK'))

# Layout entries: (record key, label, colour, always_shown).
#   always_shown=True : an empty value is printed as "None"
#   always_shown=False: an empty value hides the line
# None entries are blank separator lines.
LAYOUT = [
    ('Name', 'Name', G, True),
    ('Version', 'Version', C, True),
    ('Description', 'Description', C, True),
    ('Section', 'Section', G, False),
    None,
    ('Depends_On', 'Depends On', Y, True),
    ('Pre_Depends', 'Pre-Depends', Y, False),
    ('Recommends', 'Recommends', Y, True),
    ('Suggests', 'Suggests', Y, True),
    None,
    ('Required_By', 'Required By', Y, True),
    ('Recommended_By', 'Recommended By', Y, True),
    ('Suggested_By', 'Suggested By', Y, True),
    None,
    ('Provides', 'Provides', Y, False),
    ('Conflicts', 'Conflicts', Y, False),
    ('Breaks', 'Breaks', Y, False),
    ('Replaces', 'Replaces', Y, False),
    None,
    ('Installed_Size', 'Installed Size', B, True),
    ('Install_Reason', 'Install Reason', B, True),
    None,
    ('Architecture', 'Architecture', K, False),
    ('Multi_Arch', 'Multi-Arch', K, False),
    ('Priority', 'Priority', K, False),
    ('Essential', 'Essential', K, False),
    ('Maintainer', 'Maintainer', K, False),
    ('Homepage', 'Homepage', K, False),
    ('Source', 'Source', K, False),
    None,
    ('Note', 'Note', M, False),
]

REASON_COLORS = {REASON_MANUAL: G, REASON_AUTO: Y}

# Strips ANSI/OSC escape sequences and C0 control characters before a value is
# written to the terminal (title spoofing, OSC clipboard writes, ...).
_ESCAPE_SEQ_RE = re.compile(
    r'\x1b\[[0-9;]*[a-zA-Z]'  # CSI sequences, e.g. \x1b[31m
    r'|\x1b\][^\x07]*(\x07|\x1b\\)'  # OSC sequences, terminated by BEL or ST
    r'|[\x00-\x08\x0b-\x1f\x7f]'  # other C0 controls and DEL
)


def sanitize_terminal_value(value: str) -> str:
    return _ESCAPE_SEQ_RE.sub('', value)


def bytes_to_human(bytes_value) -> str:
    """Convert a byte count to a human-readable string (e.g. 2.34 MiB)."""
    if bytes_value is None or bytes_value == '':
        return ''
    try:
        bytes_value = int(bytes_value)
    except (ValueError, TypeError):
        return str(bytes_value)
    for unit, divisor in (('TiB', 1024 ** 4), ('GiB', 1024 ** 3),
                          ('MiB', 1024 ** 2), ('KiB', 1024)):
        if bytes_value >= divisor:
            return f"{bytes_value / divisor:.2f} {unit}"
    return f"{bytes_value} B"


def _line(key: str, label: str, color: str, value, use_color: bool) -> str:
    value = sanitize_terminal_value(str(value))
    if key == 'Installed_Size':
        value = bytes_to_human(value)
    value_color = REASON_COLORS.get(value, color) if key == 'Install_Reason' else color
    if value == 'None':
        value_color = K
    if not use_color:
        return f"{label:<16}: {value}"
    reset = COLORS['RESET']
    return f"{color}{label:<16}{reset}{K}: {reset}{value_color}{value}{reset}"


def render_preview(data: Dict, *, use_color: bool = True,
                   note: Optional[str] = None) -> str:
    """Build the full multi-line preview for one package record."""
    data = dict(data)
    if note:
        data['Note'] = note

    lines: List[str] = []
    for entry in LAYOUT:
        if entry is None:
            lines.append('')
            continue
        key, label, color, always = entry
        value = data.get(key, '')
        if value == '' or value is None:
            if not always:
                continue
            value = 'None'
        lines.append(_line(key, label, color, value, use_color))

    # Collapse runs of blank lines left behind by hidden fields.
    out: List[str] = []
    for line in lines:
        if line == '' and (not out or out[-1] == ''):
            continue
        out.append(line)
    while out and out[-1] == '':
        out.pop()
    return '\n'.join(out)
