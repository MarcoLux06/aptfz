"""Test setup: make src/lib importable and keep every test away from the
user's real cache, notes and dpkg state.

Each test gets scratch cache/notes paths via environment overrides. Tests that
need package data build records by hand (``make_record``) or craft dpkg-query
text; none of them require a Debian system, except the one clearly marked
integration test, which skips itself elsewhere.
"""
import os
import pathlib
import shutil
import sys

import pytest

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
LIB_DIR = ROOT / 'src' / 'lib'
SRC_DIR = ROOT / 'src'
sys.path.insert(0, str(LIB_DIR))

from schema import FIELD_ORDER, REASON_AUTO, REASON_MANUAL  # noqa: E402


def make_record(name, **overrides):
    """A fully populated record with sensible defaults."""
    rec = {col: '' for col in FIELD_ORDER}
    rec.update(Name=name, Version='1.0', Architecture='amd64',
               Description=f'{name} description', Installed_Size=1024,
               Install_Reason=REASON_MANUAL)
    rec.update(overrides)
    return rec


@pytest.fixture
def sample_packages():
    """A small, hand-built system exercising every filter."""
    return [
        make_record('vim', Installed_Size=3000 * 1024, Install_Reason=REASON_MANUAL,
                    Depends_On='libc6, vim-runtime', Suggests='ctags',
                    Required_By='', Recommended_By='', Suggested_By=''),
        make_record('vim-runtime', Installed_Size=7000 * 1024, Install_Reason=REASON_AUTO,
                    Required_By='vim', Recommended_By='', Suggested_By=''),
        make_record('libc6', Installed_Size=12000 * 1024, Install_Reason=REASON_AUTO,
                    Required_By='vim, git', Recommended_By='', Suggested_By=''),
        make_record('git', Installed_Size=500 * 1024, Install_Reason=REASON_MANUAL,
                    Required_By='', Recommended_By='gitk', Suggested_By=''),
        make_record('ctags', Installed_Size=100 * 1024, Install_Reason=REASON_AUTO,
                    Required_By='', Recommended_By='', Suggested_By='vim'),
        make_record('gitk', Installed_Size=200 * 1024, Install_Reason=REASON_MANUAL,
                    Required_By='', Recommended_By='', Suggested_By=''),
    ]


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Scratch cache/notes/status paths, applied to os.environ."""
    paths = {
        'cache': str(tmp_path / 'cache' / 'packages.json'),
        'notes': str(tmp_path / 'data' / 'notes.json'),
        'status': str(tmp_path / 'status'),
        'states': str(tmp_path / 'extended_states'),
    }
    pathlib.Path(paths['status']).write_text('Package: fake\n')
    monkeypatch.setenv('APTFZ_CACHE_PATH', paths['cache'])
    monkeypatch.setenv('APTFZ_NOTES_PATH', paths['notes'])
    monkeypatch.setenv('APTFZ_STATUS_PATH', paths['status'])
    monkeypatch.setenv('APTFZ_STATES_PATH', paths['states'])
    return paths


@pytest.fixture
def primed_env(env, sample_packages):
    """``env`` plus a valid, fresh cache holding ``sample_packages``, so
    launchers run as subprocesses never need dpkg."""
    import cache
    cache._write_cache(env['cache'], cache.current_signature(), sample_packages)
    return env


@pytest.fixture
def launchers():
    return {'aptfz': str(SRC_DIR / 'aptfz'), 'aptq': str(SRC_DIR / 'aptq')}


@pytest.fixture
def fake_fzf(tmp_path):
    """A stub fzf on PATH: records its argv and stdin, selects stdin's first line."""
    bindir = tmp_path / 'bin'
    bindir.mkdir()
    log = tmp_path / 'fzf.log'
    stub = bindir / 'fzf'
    stub.write_text(
        '#!/bin/sh\n'
        f'printf "%s\\n" "$@" > {log}.args\n'
        f'cat > {log}.stdin\n'
        'head -n 1 ' + f'{log}.stdin\n'
    )
    stub.chmod(0o755)
    return {'bindir': str(bindir), 'log': str(log)}
