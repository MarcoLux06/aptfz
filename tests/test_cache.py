import json
import os

import cache
import config
from conftest import make_record


class Collector:
    """Counts how many times the (expensive) collection ran."""

    def __init__(self, packages):
        self.packages, self.calls = packages, 0

    def __call__(self):
        self.calls += 1
        return self.packages


def test_first_run_collects_and_writes_cache(env, sample_packages):
    c = Collector(sample_packages)
    got = cache.load_packages(collector=c)
    assert c.calls == 1 and got == sample_packages
    assert os.path.exists(env['cache'])


def test_second_run_is_served_from_cache(env, sample_packages):
    c = Collector(sample_packages)
    cache.load_packages(collector=c)
    got = cache.load_packages(collector=c)
    assert c.calls == 1 and got == sample_packages


def test_changed_dpkg_status_invalidates(env, sample_packages):
    c = Collector(sample_packages)
    cache.load_packages(collector=c)
    with open(env['status'], 'a') as fh:  # simulates dpkg installing something
        fh.write('Package: another\n')
    cache.load_packages(collector=c)
    assert c.calls == 2


def test_replaced_status_file_invalidates_even_if_same_size(env, sample_packages):
    c = Collector(sample_packages)
    cache.load_packages(collector=c)
    tmp = env['status'] + '.new'
    with open(tmp, 'w') as fh:  # dpkg replaces the file via rename
        fh.write(open(env['status']).read())
    os.replace(tmp, env['status'])
    cache.load_packages(collector=c)
    assert c.calls == 2


def test_apt_mark_change_invalidates(env, sample_packages):
    c = Collector(sample_packages)
    cache.load_packages(collector=c)
    with open(env['states'], 'w') as fh:  # apt-mark auto/manual rewrites this file
        fh.write('Package: x\nAuto-Installed: 1\n')
    cache.load_packages(collector=c)
    assert c.calls == 2
    cache.load_packages(collector=c)
    assert c.calls == 2  # and is then stable again


def test_missing_extended_states_is_fine(env, sample_packages):
    assert not os.path.exists(env['states'])
    c = Collector(sample_packages)
    cache.load_packages(collector=c)
    cache.load_packages(collector=c)
    assert c.calls == 1


def test_corrupt_cache_is_rebuilt(env, sample_packages):
    c = Collector(sample_packages)
    cache.load_packages(collector=c)
    with open(env['cache'], 'w') as fh:
        fh.write('{"truncated": ')
    assert cache.load_packages(collector=c) == sample_packages
    assert c.calls == 2
    json.load(open(env['cache']))  # valid again


def test_cache_from_other_version_or_layout_is_ignored(env, sample_packages):
    c = Collector(sample_packages)
    cache.load_packages(collector=c)
    data = json.load(open(env['cache']))
    data['version'] = '0.0.0-other'
    json.dump(data, open(env['cache'], 'w'))
    cache.load_packages(collector=c)
    assert c.calls == 2

    data = json.load(open(env['cache']))
    data['columns'] = data['columns'][:-1]
    json.dump(data, open(env['cache'], 'w'))
    cache.load_packages(collector=c)
    assert c.calls == 3


def test_roundtrip_preserves_types(env):
    recs = [make_record('a', Installed_Size=123456), make_record('b:i386', Architecture='i386')]
    cache.load_packages(collector=lambda: recs)
    got = cache.load_packages(collector=lambda: [])
    assert got == recs and isinstance(got[0]['Installed_Size'], int)


def test_unwritable_cache_warns_but_still_returns_data(env, sample_packages, capsys):
    # a *file* where the cache directory should be
    parent = os.path.dirname(env['cache'])
    with open(parent, 'w') as fh:
        fh.write('x')
    got = cache.load_packages(collector=lambda: sample_packages)
    assert got == sample_packages
    assert 'could not write cache' in capsys.readouterr().err


def test_failed_rebuild_leaves_old_cache_intact_and_no_temp_files(env, sample_packages):
    cache.load_packages(collector=lambda: sample_packages)
    before = open(env['cache']).read()
    with open(env['status'], 'a') as fh:
        fh.write('change\n')

    def boom():
        raise RuntimeError('dpkg exploded')

    try:
        cache.load_packages(collector=boom)
    except RuntimeError:
        pass
    assert open(env['cache']).read() == before
    assert [f for f in os.listdir(os.path.dirname(env['cache'])) if f.endswith('.tmp')] == []


def test_paths_resolve_at_call_time(monkeypatch, tmp_path):
    monkeypatch.setenv('APTFZ_CACHE_PATH', str(tmp_path / 'a.json'))
    assert config.cache_path() == str(tmp_path / 'a.json')
    monkeypatch.setenv('APTFZ_CACHE_PATH', str(tmp_path / 'b.json'))
    assert config.cache_path() == str(tmp_path / 'b.json')


def test_default_paths_follow_xdg(monkeypatch, tmp_path):
    for var in ('APTFZ_CACHE_PATH', 'APTFZ_NOTES_PATH'):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv('XDG_CACHE_HOME', str(tmp_path / 'c'))
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path / 'd'))
    assert config.cache_path() == str(tmp_path / 'c' / 'aptfz' / 'packages.json')
    assert config.notes_path() == str(tmp_path / 'd' / 'aptfz' / 'notes.json')
