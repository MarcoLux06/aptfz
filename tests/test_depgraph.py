import depgraph
from conftest import make_record
from depgraph import compute_reverse_dependencies, parse_dependency_field


def test_parse_strips_versions_arch_restrictions_and_profiles():
    got = parse_dependency_field('libc6 (>= 2.34), foo [amd64] (<< 2.0), bar <!nocheck>')
    assert got == [[('libc6', None)], [('foo', None)], [('bar', None)]]


def test_parse_alternatives_and_qualifiers():
    got = parse_dependency_field('a | b:any, c:i386 (>= 1)')
    assert got == [[('a', None), ('b', 'any')], [('c', 'i386')]]


def test_parse_empty_and_garbage():
    assert parse_dependency_field('') == []
    assert parse_dependency_field(' , | ,') == []


def _rev(records, name, field='Required_By'):
    compute_reverse_dependencies(records)
    return next(r for r in records if r['Name'] == name)[field]


def test_simple_reverse_dependency():
    recs = [make_record('app', Depends_On='lib'), make_record('lib')]
    assert _rev(recs, 'lib') == 'app'
    assert recs[0]['Required_By'] == ''


def test_pre_depends_count_as_required():
    recs = [make_record('app', Pre_Depends='lib'), make_record('lib')]
    assert _rev(recs, 'lib') == 'app'


def test_recommends_and_suggests_are_separate_fields():
    recs = [make_record('app', Recommends='r', Suggests='s'), make_record('r'), make_record('s')]
    compute_reverse_dependencies(recs)
    r, s = recs[1], recs[2]
    assert (r['Recommended_By'], r['Suggested_By'], r['Required_By']) == ('app', '', '')
    assert (s['Suggested_By'], s['Recommended_By'], s['Required_By']) == ('app', '', '')


def test_alternatives_all_installed_alternatives_get_an_edge():
    recs = [make_record('app', Depends_On='a | b | missing'), make_record('a'), make_record('b')]
    compute_reverse_dependencies(recs)
    assert recs[1]['Required_By'] == 'app' and recs[2]['Required_By'] == 'app'


def test_uninstalled_dependency_is_ignored():
    recs = [make_record('app', Depends_On='ghost')]
    assert _rev(recs, 'app') == ''


def test_virtual_package_resolves_through_provides():
    recs = [make_record('app', Depends_On='mail-transport-agent'),
            make_record('postfix', Provides='mail-transport-agent (= 1.0)')]
    assert _rev(recs, 'postfix') == 'app'


def test_self_dependency_is_ignored():
    recs = [make_record('weird', Depends_On='weird', Provides='thing'),
            make_record('other', Depends_On='thing')]
    compute_reverse_dependencies(recs)
    assert recs[0]['Required_By'] == 'other'  # not 'weird'


def test_dependency_cycle_each_requires_the_other():
    recs = [make_record('a', Depends_On='b'), make_record('b', Depends_On='a')]
    compute_reverse_dependencies(recs)
    assert (recs[0]['Required_By'], recs[1]['Required_By']) == ('b', 'a')


def test_multiarch_unqualified_prefers_same_architecture():
    recs = [make_record('libc6'), make_record('libc6:i386', Architecture='i386'),
            make_record('app', Depends_On='libc6'),
            make_record('app32:i386', Architecture='i386', Depends_On='libc6')]
    compute_reverse_dependencies(recs)
    by = {r['Name']: r for r in recs}
    assert by['libc6']['Required_By'] == 'app'
    assert by['libc6:i386']['Required_By'] == 'app32:i386'


def test_multiarch_arch_all_depender_is_conservative():
    recs = [make_record('libc6'), make_record('libc6:i386', Architecture='i386'),
            make_record('docs', Architecture='all', Depends_On='libc6')]
    compute_reverse_dependencies(recs)
    assert recs[0]['Required_By'] == 'docs' and recs[1]['Required_By'] == 'docs'


def test_multiarch_any_and_explicit_qualifiers():
    recs = [make_record('lib'), make_record('lib:i386', Architecture='i386'),
            make_record('anyuser', Depends_On='lib:any'),
            make_record('i386user', Depends_On='lib:i386')]
    compute_reverse_dependencies(recs)
    by = {r['Name']: r for r in recs}
    assert by['lib']['Required_By'] == 'anyuser'
    assert by['lib:i386']['Required_By'] == 'anyuser, i386user'


def test_arch_all_target_satisfies_explicit_qualifier():
    recs = [make_record('data', Architecture='all'), make_record('app', Depends_On='data:amd64')]
    assert _rev(recs, 'data') == 'app'


def test_reverse_lists_are_sorted_and_deduplicated():
    recs = [make_record('lib'), make_record('z', Depends_On='lib', Pre_Depends='lib'),
            make_record('a', Depends_On='lib')]
    assert _rev(recs, 'lib') == 'a, z'


def test_foreign_target_is_found_by_bare_name():
    recs = [make_record('libx:i386', Architecture='i386'),
            make_record('app32:i386', Architecture='i386', Depends_On='libx')]
    assert _rev(recs, 'libx:i386') == 'app32:i386'
