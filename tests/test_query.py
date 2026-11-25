import pytest

import query
from query import build_predicate, describe_filters, select, total_size


def names(rows):
    return [r['Name'] for r in rows]


def test_no_filters_returns_everything_sorted_by_name(sample_packages):
    assert names(select(sample_packages)) == ['ctags', 'git', 'gitk', 'libc6', 'vim', 'vim-runtime']


def test_explicit_and_deps_partition_the_set(sample_packages):
    e = set(names(select(sample_packages, where_clauses=['explicit'])))
    d = set(names(select(sample_packages, where_clauses=['deps'])))
    assert e == {'vim', 'git', 'gitk'} and d == {'vim-runtime', 'libc6', 'ctags'}
    assert not e & d


def test_notadep(sample_packages):
    got = names(select(sample_packages, where_clauses=['notadep']))
    assert got == ['ctags', 'git', 'gitk', 'vim']


def test_notoptdep_means_neither_recommended_nor_suggested(sample_packages):
    got = names(select(sample_packages, where_clauses=['notoptdep']))
    assert 'git' not in got      # recommended by gitk
    assert 'ctags' not in got    # suggested by vim
    assert 'gitk' in got and 'vim' in got


def test_filters_are_anded(sample_packages):
    got = names(select(sample_packages, where_clauses=['explicit', 'notadep', 'notoptdep']))
    assert got == ['gitk', 'vim']


def test_field_search_substring_is_case_insensitive(sample_packages):
    assert names(select(sample_packages, field_searches=[('Name', 'VIM')])) == ['vim', 'vim-runtime']


def test_field_search_exact(sample_packages):
    assert names(select(sample_packages, field_searches=[('Name', 'vim')], exact_match=True)) == ['vim']
    assert names(select(sample_packages, field_searches=[('Name', 'VIM')], exact_match=True)) == []


def test_field_name_is_forgiving(sample_packages):
    for spelling in ('install reason', 'Install-Reason', 'install_reason', 'INSTALL_REASON'):
        assert len(select(sample_packages, field_searches=[(spelling, 'Manually')])) == 3
    assert names(select(sample_packages, field_searches=[('package', 'git')], exact_match=True)) == ['git']


def test_unknown_field_raises_with_valid_list(sample_packages):
    with pytest.raises(ValueError, match='Unknown field .*Valid fields:.*Name'):
        select(sample_packages, field_searches=[('Bogus', 'x')])


def test_any_search_matches_any_column(sample_packages):
    assert names(select(sample_packages, any_field_searches=['ctags'])) == ['ctags', 'vim']  # ctags itself + vim's Suggests


def test_multiple_any_searches_are_anded(sample_packages):
    assert names(select(sample_packages, any_field_searches=['vim', 'runtime'])) == ['vim', 'vim-runtime']


def test_searching_empty_exact_finds_empty_fields(sample_packages):
    got = names(select(sample_packages, field_searches=[('Required_By', '')], exact_match=True))
    assert got == ['ctags', 'git', 'gitk', 'vim']


# ---- inversion ------------------------------------------------------------
def test_bare_invert_negates_everything_as_one_unit(sample_packages):
    # NOT(explicit AND notadep)
    got = names(select(sample_packages, where_clauses=['explicit', 'notadep'], invert_all=True))
    assert got == ['ctags', 'libc6', 'vim-runtime']


def test_bare_invert_with_nothing_raises(sample_packages):
    with pytest.raises(ValueError, match='nothing to invert'):
        select(sample_packages, invert_all=True)


def test_invert_one_filter_keeps_other_preconditions(sample_packages):
    # explicit AND NOT notadep -> explicit packages that something requires
    got = names(select(sample_packages, where_clauses=['explicit'], invert_clauses=['notadep']))
    assert got == []  # all explicit sample packages are required by nothing
    got = names(select(sample_packages, where_clauses=['deps'], invert_clauses=['notadep']))
    assert got == ['libc6', 'vim-runtime']


def test_invert_clauses_are_one_negated_group_not_two(sample_packages):
    # NOT(notadep AND notoptdep) over explicit
    got = names(select(sample_packages, where_clauses=['explicit'], invert_clauses=['notadep', 'notoptdep']))
    assert got == ['git']  # the only explicit one that is optional-dep'd


def test_invert_each_negates_independently(sample_packages):
    # NOT(notadep) AND NOT(notoptdep): required by something AND opt-dep of something
    p = build_predicate(invert_each=['notadep', 'notoptdep'])
    assert [r['Name'] for r in sample_packages if p(r)] == []
    p = build_predicate(invert_each=['notadep'])
    assert {r['Name'] for r in sample_packages if p(r)} == {'vim-runtime', 'libc6'}


def test_notes_filter_is_applied_outside_inversion(sample_packages):
    got = names(select(sample_packages, where_clauses=['explicit'], invert_all=True,
                       notes_filter='has_note', noted={'libc6', 'vim'}))
    assert got == ['libc6']  # NOT explicit, then has-note; vim is explicit so it is out


def test_no_note_filter(sample_packages):
    got = names(select(sample_packages, notes_filter='no_note', noted={'vim', 'git'}))
    assert 'vim' not in got and 'git' not in got and 'gitk' in got


def test_resolve_canned_filter_name():
    assert query.resolve_canned_filter_name('N') == 'notadep'
    assert query.resolve_canned_filter_name(' explicit ') == 'explicit'
    with pytest.raises(ValueError, match='Valid filters: deps, explicit, notadep, notoptdep'):
        query.resolve_canned_filter_name('orphan')


# ---- sorting & totals -----------------------------------------------------
def test_sort_by_size_defaults_to_descending_and_is_numeric(sample_packages):
    assert names(select(sample_packages, sort_field='Installed_Size'))[:3] == ['libc6', 'vim-runtime', 'vim']


def test_sort_direction_overrides(sample_packages):
    assert names(select(sample_packages, sort_field='size', sort_direction='ASC'))[0] == 'ctags'
    assert names(select(sample_packages, sort_direction='DESC'))[0] == 'vim-runtime'


def test_sort_is_case_insensitive_with_name_tiebreak():
    from conftest import make_record
    recs = [make_record('b', Section='x'), make_record('a', Section='X'), make_record('c', Section='a')]
    assert names(select(recs, sort_field='Section')) == ['c', 'a', 'b']


def test_unknown_sort_field_raises(sample_packages):
    with pytest.raises(ValueError):
        select(sample_packages, sort_field='nope')


def test_total_size(sample_packages):
    assert total_size(sample_packages) == (3000 + 7000 + 12000 + 500 + 100 + 200) * 1024
    rows = select(sample_packages, where_clauses=['explicit'])
    assert total_size(rows) == (3000 + 500 + 200) * 1024
    assert total_size([]) == 0


# ---- -t sentence ----------------------------------------------------------
def test_describe_defaults_and_composition():
    assert describe_filters() == 'total package size'
    assert describe_filters(explicit=True) == 'total size of manually installed packages'
    assert describe_filters(explicit=True, notadep=True) == \
        'total size of manually installed packages that nothing requires'
    assert describe_filters(has_note=True, field_searches=[('Name', 'vim')]) == \
        'total package size with a note and where Name matches "vim"'
    assert describe_filters(explicit=True, bare_invert=True) == \
        'total size of packages NOT matching: manually installed'
