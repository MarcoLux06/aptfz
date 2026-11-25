"""The normalized package record: field names and vocabulary.

Everything downstream (cache, query engine, renderers) only knows about this
schema, never about dpkg's raw field names. Column names mirror pacfz's where
the concept exists on both systems (Name, Version, Installed_Size,
Install_Reason, Required_By, ...), so ``-f Name vim`` works the same way.
"""
from __future__ import annotations

from typing import Dict, List

# Column order is also the cache layout; changing it invalidates old caches.
FIELD_ORDER: List[str] = [
    'Name', 'Version', 'Architecture', 'Description', 'Installed_Size',
    'Install_Reason', 'Section', 'Priority', 'Maintainer', 'Homepage',
    'Source', 'Essential', 'Multi_Arch',
    'Depends_On', 'Pre_Depends', 'Recommends', 'Suggests',
    'Conflicts', 'Breaks', 'Provides', 'Replaces',
    'Required_By', 'Recommended_By', 'Suggested_By',
]

# Install_Reason values (derived from `apt-mark showmanual` / `showauto`).
REASON_MANUAL = 'Manually installed'
REASON_AUTO = 'Automatically installed (as a dependency)'
REASON_UNKNOWN = 'Unknown'

# Friendly spellings accepted by -f / -s in addition to the exact column
# names (matching is case-insensitive and treats ' ', '-' and '_' alike).
FIELD_ALIASES: Dict[str, str] = {
    'package': 'Name',
    'depends': 'Depends_On',
    'size': 'Installed_Size',
}


def normalize_field_token(text: str) -> str:
    return text.strip().replace(' ', '_').replace('-', '_').lower()


def resolve_field_name(field: str) -> str:
    """Resolve a user-supplied field name to its exact column name.

    Raises:
        ValueError: if no column matches.
    """
    token = normalize_field_token(field)
    for col in FIELD_ORDER:
        if col.lower() == token:
            return col
    if token in FIELD_ALIASES:
        return FIELD_ALIASES[token]
    raise ValueError(
        f"Unknown field '{field}'. Valid fields: {', '.join(FIELD_ORDER)}"
    )


def bare_name(key: str) -> str:
    """'libc6:i386' -> 'libc6'; plain names are returned unchanged."""
    return key.partition(':')[0]
