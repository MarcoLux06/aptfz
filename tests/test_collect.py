import collect
from collect import (DPKG_QUERY_FORMAT, assign_install_reasons, package_key,
                     parse_dpkg_query, parse_name_list)
from schema import REASON_AUTO, REASON_MANUAL, REASON_UNKNOWN

FS, RS = '\x1f', '\x1e'
# order must match collect._DPKG_FIELDS
_ORDER = [f for f, _ in collect._DPKG_FIELDS]


def rec_text(**fields):
    """Build one dpkg-query record from dpkg field names."""
    defaults = {'Architecture': 'amd64', 'Version': '1.0', 'Installed-Size': '10',
                'db:Status-Abbrev': 'ii ', 'binary:Synopsis': 'a package'}
    defaults.update(fields)
    return FS.join(defaults.get(f, '') for f in _ORDER) + RS


def test_format_string_has_one_placeholder_per_field():
    assert DPKG_QUERY_FORMAT.count('${') == len(_ORDER)
    assert DPKG_QUERY_FORMAT.count(FS) == len(_ORDER) - 1
    assert DPKG_QUERY_FORMAT.endswith(RS)


def test_basic_record():
    out = rec_text(Package='vim', Depends='libc6 (>= 2.34), vim-runtime', Section='editors',
                   **{'Installed-Size': '3000', 'Multi-Arch': 'foreign'})
    [r] = parse_dpkg_query(out, 'amd64')
    assert r['Name'] == 'vim'
    assert r['Installed_Size'] == 3000 * 1024  # KiB -> bytes
    assert r['Depends_On'] == 'libc6 (>= 2.34), vim-runtime'
    assert r['Description'] == 'a package'
    assert r['Multi_Arch'] == 'foreign'
    assert r['Required_By'] == ''  # filled later by depgraph


def test_removed_with_config_left_and_never_installed_are_skipped():
    out = (rec_text(Package='live', **{'db:Status-Abbrev': 'ii '})
           + rec_text(Package='removed-rc', **{'db:Status-Abbrev': 'rc '})
           + rec_text(Package='never', **{'db:Status-Abbrev': 'un '})
           + rec_text(Package='held', **{'db:Status-Abbrev': 'hi '}))
    names = [r['Name'] for r in parse_dpkg_query(out, 'amd64')]
    assert names == ['live', 'held']


def test_multiline_folded_fields_are_flattened():
    out = rec_text(Package='x', Depends='a,\n   b,\n   c')
    [r] = parse_dpkg_query(out, 'amd64')
    assert r['Depends_On'] == 'a, b, c'


def test_malformed_record_is_skipped_not_fatal():
    out = rec_text(Package='good') + 'broken' + FS + 'record' + RS + rec_text(Package='good2')
    assert [r['Name'] for r in parse_dpkg_query(out, 'amd64')] == ['good', 'good2']


def test_bad_installed_size_becomes_zero():
    out = rec_text(Package='x', **{'Installed-Size': 'many'})
    assert parse_dpkg_query(out, 'amd64')[0]['Installed_Size'] == 0


def test_package_key_native_all_and_foreign():
    assert package_key('libc6', 'amd64', 'amd64') == 'libc6'
    assert package_key('docs', 'all', 'amd64') == 'docs'
    assert package_key('libc6', 'i386', 'amd64') == 'libc6:i386'


def test_multiarch_pair_gets_distinct_keys():
    out = rec_text(Package='libc6', Architecture='amd64') + rec_text(Package='libc6', Architecture='i386')
    assert [r['Name'] for r in parse_dpkg_query(out, 'amd64')] == ['libc6', 'libc6:i386']


def test_parse_name_list():
    assert parse_name_list('a\nb:i386\n\n  c \n') == {'a', 'b:i386', 'c'}
    assert parse_name_list('') == set()


def test_install_reasons():
    recs = parse_dpkg_query(
        rec_text(Package='m') + rec_text(Package='a') + rec_text(Package='u')
        + rec_text(Package='f', Architecture='i386') + rec_text(Package='g', Architecture='i386'), 'amd64')
    assign_install_reasons(recs, manual={'m', 'f:i386'}, auto={'a', 'g:i386'})
    got = {r['Name']: r['Install_Reason'] for r in recs}
    assert got == {'m': REASON_MANUAL, 'a': REASON_AUTO, 'u': REASON_UNKNOWN,
                   'f:i386': REASON_MANUAL, 'g:i386': REASON_AUTO}


def test_foreign_arch_not_confused_with_native_same_name():
    recs = parse_dpkg_query(rec_text(Package='libc6') + rec_text(Package='libc6', Architecture='i386'), 'amd64')
    # only the native one is marked manual; i386 is auto
    assign_install_reasons(recs, manual={'libc6'}, auto={'libc6:i386'})
    got = {r['Name']: r['Install_Reason'] for r in recs}
    assert got == {'libc6': REASON_MANUAL, 'libc6:i386': REASON_AUTO}


def test_missing_dpkg_is_a_clean_error(monkeypatch):
    def nope(*a, **k):
        raise FileNotFoundError()
    monkeypatch.setattr(collect.subprocess, 'run', nope)
    import pytest
    with pytest.raises(RuntimeError, match="'dpkg-query' not found.*Debian-based"):
        collect.collect_packages(native_arch='amd64')


def test_failing_command_reports_stderr(monkeypatch):
    import subprocess
    import pytest
    monkeypatch.setattr(collect.subprocess, 'run', lambda *a, **k: subprocess.CompletedProcess(
        a[0], 2, b'', b'dpkg: database locked'))
    with pytest.raises(RuntimeError, match='failed with code 2: dpkg: database locked'):
        collect.collect_packages(native_arch='amd64')


def test_timeout_is_reported(monkeypatch):
    import subprocess
    import pytest

    def slow(*a, **k):
        raise subprocess.TimeoutExpired(a[0], 1)
    monkeypatch.setattr(collect.subprocess, 'run', slow)
    with pytest.raises(RuntimeError, match='timed out'):
        collect.collect_packages(native_arch='amd64')
