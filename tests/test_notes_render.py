import json
import re

import pytest

import notes
from conftest import make_record
from render import bytes_to_human, render_preview, sanitize_terminal_value
from schema import REASON_AUTO


# ---- notes ------------------------------------------------------------------
def test_set_get_delete_list(env):
    assert notes.get_note('vim') is None
    notes.set_note('vim', 'daily editor')
    notes.set_note('git', 'vcs')
    assert notes.get_note('vim') == 'daily editor'
    assert notes.list_notes() == [('git', 'vcs'), ('vim', 'daily editor')]
    assert notes.packages_with_notes() == {'git', 'vim'}
    assert notes.delete_note('vim') is True
    assert notes.delete_note('vim') is False
    assert notes.get_note('vim') is None


def test_reading_never_creates_the_file(env):
    import os
    notes.get_note('x'); notes.list_notes(); notes.packages_with_notes()
    assert not os.path.exists(env['notes'])


def test_overwrite_and_unicode(env):
    notes.set_note('vim', 'one')
    notes.set_note('vim', 'zwei – ünïcode ✓')
    assert notes.get_note('vim') == 'zwei – ünïcode ✓'


def test_empty_note_rejected(env):
    with pytest.raises(RuntimeError, match='empty'):
        notes.set_note('vim', '   ')


def test_corrupt_notes_file_is_never_overwritten(env):
    import os
    os.makedirs(os.path.dirname(env['notes']))
    with open(env['notes'], 'w') as fh:
        fh.write('{ not json')
    assert notes.get_note('vim') is None  # reads degrade gracefully
    with pytest.raises(RuntimeError, match='refusing to overwrite'):
        notes.set_note('vim', 'x')
    with pytest.raises(RuntimeError, match='refusing to overwrite'):
        notes.delete_note('vim')
    assert open(env['notes']).read() == '{ not json'


def test_wrong_shape_notes_file_is_protected(env):
    import os
    os.makedirs(os.path.dirname(env['notes']))
    json.dump({'vim': 123}, open(env['notes'], 'w'))
    with pytest.raises(RuntimeError, match='unexpected format'):
        notes.set_note('git', 'x')


# ---- sanitizing ---------------------------------------------------------------
@pytest.mark.parametrize('dirty, clean', [
    ('plain', 'plain'),
    ('\x1b[31mred\x1b[0m', 'red'),
    ('title\x1b]0;pwned\x07here', 'titlehere'),
    ('osc\x1b]52;c;ZXZpbA==\x1b\\done', 'oscdone'),
    ('bell\x07 nul\x00 del\x7f', 'bell nul del'),
    ('ünïcode ✓ stays', 'ünïcode ✓ stays'),
])
def test_sanitize(dirty, clean):
    assert sanitize_terminal_value(dirty) == clean


def test_hostile_description_cannot_reach_output():
    rec = make_record('evil', Description='\x1b]0;owned\x07nice\x1b[2J')
    out = render_preview(rec, use_color=False)
    assert '\x1b' not in out and '\x07' not in out and 'nice' in out


def test_hostile_note_is_sanitized_too():
    out = render_preview(make_record('x'), use_color=False, note='\x1b[31mhi')
    assert 'Note' in out and '\x1b' not in out


# ---- layout -------------------------------------------------------------------
def test_preview_plain_has_expected_fields_and_none_for_empty_deps():
    out = render_preview(make_record('vim', Depends_On='libc6', Section='editors'), use_color=False)
    lines = out.splitlines()
    assert lines[0].startswith('Name') and lines[0].endswith(': vim')
    assert any(l.startswith('Depends On') and l.endswith('libc6') for l in lines)
    for label in ('Recommends', 'Suggests', 'Required By', 'Recommended By', 'Suggested By'):
        assert any(l.startswith(label) and l.endswith(': None') for l in lines), label
    assert any(l.startswith('Installed Size') and l.endswith('1.00 KiB') for l in lines)


def test_optional_fields_hidden_when_empty_shown_when_set():
    bare = render_preview(make_record('x'), use_color=False)
    for label in ('Homepage', 'Conflicts', 'Breaks', 'Pre-Depends', 'Essential', 'Note'):
        assert label not in bare
    full = render_preview(make_record('x', Homepage='https://e.x', Essential='yes',
                                      Pre_Depends='a'), use_color=False, note='n')
    for label in ('Homepage', 'Essential', 'Pre-Depends', 'Note'):
        assert label in full


def test_no_color_means_no_escape_codes_and_color_means_some():
    assert '\x1b' not in render_preview(make_record('x'), use_color=False)
    assert '\x1b[32m' in render_preview(make_record('x'), use_color=True)


def test_no_double_blank_lines_or_edge_blanks():
    out = render_preview(make_record('x'), use_color=False)
    assert not out.startswith('\n') and not out.endswith('\n') and '\n\n\n' not in out


def test_install_reason_is_colored_by_value():
    manual = render_preview(make_record('x'), use_color=True)
    auto = render_preview(make_record('x', Install_Reason=REASON_AUTO), use_color=True)
    assert re.search(r'\x1b\[32mManually installed', manual)
    assert re.search(r'\x1b\[33mAutomatically installed', auto)


@pytest.mark.parametrize('n, text', [
    (0, '0 B'), (1023, '1023 B'), (1024, '1.00 KiB'), (1536, '1.50 KiB'),
    (1024 ** 2, '1.00 MiB'), (5 * 1024 ** 3, '5.00 GiB'), (2 * 1024 ** 4, '2.00 TiB'),
])
def test_bytes_to_human(n, text):
    assert bytes_to_human(n) == text


def test_bytes_to_human_odd_inputs():
    assert bytes_to_human(None) == '' and bytes_to_human('') == ''
    assert bytes_to_human('junk') == 'junk' and bytes_to_human('2048') == '2.00 KiB'
