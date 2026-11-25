"""End-to-end tests: run the real launchers as subprocesses against a primed
cache (no dpkg needed) and, for the picker, a stub fzf."""
import json
import os
import shutil
import subprocess
import sys

import pytest

import collect


def run(launchers, which, args, env, extra_env=None, input_text=None):
    full_env = dict(os.environ, **extra_env) if extra_env else dict(os.environ)
    return subprocess.run([sys.executable, launchers[which], *args], capture_output=True,
                          text=True, env=full_env, input=input_text)


def lines(res):
    return res.stdout.split('\n')[:-1]


# ---- aptq -------------------------------------------------------------------
def test_aptq_lists_names_one_per_line(primed_env, launchers):
    r = run(launchers, 'aptq', [], primed_env)
    assert r.returncode == 0 and r.stderr == ''
    assert lines(r) == ['ctags', 'git', 'gitk', 'libc6', 'vim', 'vim-runtime']


def test_aptq_filters_sort_and_total(primed_env, launchers):
    assert lines(run(launchers, 'aptq', ['-e'], primed_env)) == ['git', 'gitk', 'vim']
    assert lines(run(launchers, 'aptq', ['-d', '-s', '--desc'], primed_env))[0] == 'libc6'
    assert lines(run(launchers, 'aptq', ['-e', '-t'], primed_env)) == ['3.61 MiB']
    assert lines(run(launchers, 'aptq', ['-f', 'Name', 'vim', '-x'], primed_env)) == ['vim']
    r = run(launchers, 'aptq', ['-e', '-v', 'notadep'], primed_env)
    assert lines(r) == []


def test_aptq_totalsize_is_just_the_number(primed_env, launchers):
    r = run(launchers, 'aptq', ['-n', '-t'], primed_env)
    assert len(lines(r)) == 1 and 'total' not in r.stdout


def test_aptq_has_note_filter(primed_env, launchers):
    json.dump({'git': 'x'}, open(_mk(primed_env['notes']), 'w'))
    assert lines(run(launchers, 'aptq', ['--has-note'], primed_env)) == ['git']
    assert 'git' not in lines(run(launchers, 'aptq', ['--no-note'], primed_env))


def _mk(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


@pytest.mark.parametrize('args, msg', [
    (['-f', 'Bogus', 'x'], 'Unknown field'),
    (['-v'], 'nothing to invert'),
    (['-e', '-v', '-v', 'notadep'], 'not both'),
    (['-v', 'orphan'], 'Unknown filter'),
    (['-s', 'nope'], 'Unknown field'),
])
def test_aptq_errors_are_clean(primed_env, launchers, args, msg):
    r = run(launchers, 'aptq', args, primed_env)
    assert r.returncode == 1 and r.stdout == ''
    assert r.stderr.startswith('Error: ') and msg in r.stderr and 'Traceback' not in r.stderr


def test_aptq_unknown_flag_and_removed_pacfz_flags_rejected(primed_env, launchers):
    for flag in ('--bogus', '-m', '-o', '--orphans', '--foreign', '-r', '--refresh'):
        r = run(launchers, 'aptq', [flag], primed_env)
        assert r.returncode == 2, flag


def test_aptq_abbreviated_long_flags_are_not_accepted(primed_env, launchers):
    assert run(launchers, 'aptq', ['--expl'], primed_env).returncode == 2


def test_aptq_help_and_version(primed_env, launchers):
    r = run(launchers, 'aptq', ['-h'], primed_env)
    assert r.returncode == 0 and 'Usage: aptq' in r.stdout and 'Filter Options' in r.stdout
    assert 'Installed_Size' in r.stdout  # field list
    r = run(launchers, 'aptq', ['--version'], primed_env)
    assert r.stdout.startswith('aptfz ')


def test_aptq_closed_pipe_exits_quietly(primed_env, launchers):
    p = subprocess.Popen([sys.executable, launchers['aptq']], stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, env=dict(os.environ))
    p.stdout.close()
    assert b'Traceback' not in p.stderr.read()
    p.wait()


def test_aptq_does_not_need_dpkg_when_cache_is_fresh(primed_env, launchers):
    r = run(launchers, 'aptq', [], primed_env, extra_env={'PATH': '/nonexistent'})
    assert r.returncode == 0 and len(lines(r)) == 6


@pytest.mark.skipif(not (shutil.which('dpkg-query') and shutil.which('apt-mark')),
                    reason='needs a Debian-based system')
def test_stale_cache_is_rebuilt_from_the_real_system(primed_env, launchers):
    with open(primed_env['status'], 'a') as fh:  # make the primed (6-package) cache stale
        fh.write('changed\n')
    r = run(launchers, 'aptq', [], primed_env)
    assert r.returncode == 0 and len(lines(r)) > 50  # real dpkg data, not the 6 fakes
    again = run(launchers, 'aptq', [], primed_env)   # and now it is cached again
    assert lines(again) == lines(r)


@pytest.mark.skipif(not (shutil.which('dpkg-query') and shutil.which('apt-mark')),
                    reason='needs a Debian-based system')
def test_dpkg_is_found_via_a_fixed_path_not_the_users_path(primed_env, launchers):
    """A hostile $PATH must not be able to substitute dpkg-query."""
    with open(primed_env['status'], 'a') as fh:
        fh.write('changed\n')
    r = run(launchers, 'aptq', [], primed_env, extra_env={'PATH': '/nonexistent'})
    assert r.returncode == 0 and len(lines(r)) > 50


# ---- aptfz: non-picker paths ----------------------------------------------------
def test_aptfz_notes_roundtrip(primed_env, launchers):
    r = run(launchers, 'aptfz', ['-D', 'vim', 'my editor'], primed_env)
    assert r.returncode == 0 and "Note set for 'vim'" in r.stdout
    r = run(launchers, 'aptfz', ['--notes-list'], primed_env)
    assert 'vim' in r.stdout and 'my editor' in r.stdout
    r = run(launchers, 'aptfz', ['-D', 'vim', '-d'], primed_env)
    assert "Note deleted for 'vim'" in r.stdout
    assert 'No note found' in run(launchers, 'aptfz', ['-D', 'vim', '-d'], primed_env).stdout
    assert 'No notes found' in run(launchers, 'aptfz', ['--notes-list'], primed_env).stdout


def test_aptfz_notes_usage_errors(primed_env, launchers):
    assert run(launchers, 'aptfz', ['-D', 'vim'], primed_env).returncode == 2
    r = run(launchers, 'aptfz', ['-D', 'vim', '  '], primed_env)
    assert r.returncode == 1 and 'empty' in r.stderr


def test_aptfz_notes_commands_never_need_the_cache(env, launchers):
    r = run(launchers, 'aptfz', ['-D', 'vim', 'x'], env, extra_env={'PATH': '/nonexistent'})
    assert r.returncode == 0 and not os.path.exists(env['cache'])


def test_aptfz_total_has_description(primed_env, launchers):
    r = run(launchers, 'aptfz', ['-e', '-n', '-t'], primed_env)
    assert lines(r)[0] == 'total size of manually installed packages that nothing requires:'
    assert lines(r)[1] == '3.61 MiB'


def test_aptfz_help_lists_notes_and_exact(primed_env, launchers):
    r = run(launchers, 'aptfz', ['--help'], primed_env)
    for needle in ('-D <pkg> <note>', '--notes-list', '--hide-notes', '--exact', 'Filter Options'):
        assert needle in r.stdout


def test_aptfz_no_matches_says_so_without_needing_fzf(primed_env, launchers):
    r = run(launchers, 'aptfz', ['-f', 'Name', 'zzzz'], primed_env, extra_env={'PATH': os.path.dirname(sys.executable)})
    assert r.returncode == 0 and r.stdout.strip() == 'No packages found.'


def test_aptfz_without_fzf_gives_install_hint(primed_env, launchers):
    r = run(launchers, 'aptfz', [], primed_env, extra_env={'PATH': os.path.dirname(sys.executable)})
    assert r.returncode == 1 and 'sudo apt install fzf' in r.stderr and 'aptq works' in r.stderr


# ---- aptfz: picker, with a stub fzf ---------------------------------------------
def with_fzf(fake_fzf):
    return {'PATH': fake_fzf['bindir'] + os.pathsep + os.environ['PATH']}


def test_aptfz_picker_feeds_filtered_names_and_prints_preview(primed_env, launchers, fake_fzf):
    r = run(launchers, 'aptfz', ['-e'], primed_env, extra_env=with_fzf(fake_fzf))
    assert r.returncode == 0, r.stderr
    assert open(fake_fzf['log'] + '.stdin').read().split() == ['git', 'gitk', 'vim']
    assert r.stdout.startswith('Name') and ': git' in r.stdout.splitlines()[0]  # first line selected
    assert 'Recommended By' in r.stdout and '\x1b' not in r.stdout  # not a tty -> no color


def test_aptfz_picker_passes_preview_command_and_options(primed_env, launchers, fake_fzf):
    run(launchers, 'aptfz', ['--exact', '--hide-notes'], primed_env, extra_env=with_fzf(fake_fzf))
    args = open(fake_fzf['log'] + '.args').read().split('\n')
    assert '-e' in args
    preview = args[args.index('--preview') + 1]
    assert 'preview.py' in preview and '--hide-notes' in preview and '--color=always' in preview
    assert preview.endswith("-- {}")


def test_aptfz_print_selection_prints_bare_name(primed_env, launchers, fake_fzf):
    r = run(launchers, 'aptfz', ['--print-selection', '-d'], primed_env, extra_env=with_fzf(fake_fzf))
    assert r.stdout == 'libc6\n' or r.stdout == 'ctags\n'  # first of the sorted deps
    assert r.stdout.strip() == open(fake_fzf['log'] + '.stdin').read().split()[0]


def test_aptfz_shows_note_in_final_preview_unless_hidden(primed_env, launchers, fake_fzf):
    run(launchers, 'aptfz', ['-D', 'ctags', 'handy tags'], primed_env)
    r = run(launchers, 'aptfz', [], primed_env, extra_env=with_fzf(fake_fzf))
    assert 'handy tags' in r.stdout
    r = run(launchers, 'aptfz', ['--hide-notes'], primed_env, extra_env=with_fzf(fake_fzf))
    assert 'handy tags' not in r.stdout


def test_aptfz_cancelled_picker_is_silent_success(primed_env, launchers, tmp_path):
    bindir = tmp_path / 'cancel'
    bindir.mkdir()
    (bindir / 'fzf').write_text('#!/bin/sh\ncat >/dev/null\nexit 130\n')
    (bindir / 'fzf').chmod(0o755)
    r = run(launchers, 'aptfz', [], primed_env, extra_env={'PATH': f"{bindir}{os.pathsep}{os.environ['PATH']}"})
    assert r.returncode == 0 and r.stdout == '' and r.stderr == ''


def test_aptfz_fzf_failure_is_reported(primed_env, launchers, tmp_path):
    bindir = tmp_path / 'broken'
    bindir.mkdir()
    (bindir / 'fzf').write_text('#!/bin/sh\ncat >/dev/null\nexit 2\n')
    (bindir / 'fzf').chmod(0o755)
    r = run(launchers, 'aptfz', [], primed_env, extra_env={'PATH': f"{bindir}{os.pathsep}{os.environ['PATH']}"})
    assert r.returncode == 1 and 'fzf exited with code 2' in r.stderr


# ---- the preview script fzf calls --------------------------------------------------
def preview(primed_env, lib_args, extra_env=None):
    script = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'src', 'lib', 'preview.py')
    return subprocess.run([sys.executable, script, *lib_args], capture_output=True, text=True,
                          env=dict(os.environ, **(extra_env or {})))


def test_preview_script_renders_a_package(primed_env):
    r = preview(primed_env, ['--color=never', '--', 'vim'])
    assert r.returncode == 0 and ': vim' in r.stdout and 'Suggests' in r.stdout and 'ctags' in r.stdout


def test_preview_script_color_modes(primed_env):
    assert '\x1b' in preview(primed_env, ['--color=always', 'vim']).stdout
    assert '\x1b' not in preview(primed_env, ['--color=never', 'vim']).stdout


def test_preview_script_unknown_package_prints_nothing(primed_env):
    r = preview(primed_env, ['--', 'no-such-package'])
    assert r.returncode == 0 and r.stdout == ''


def test_preview_script_note_and_hide_notes(primed_env):
    json.dump({'vim': 'remember me'}, open(_mk(primed_env['notes']), 'w'))
    assert 'remember me' in preview(primed_env, ['--color=never', 'vim']).stdout
    assert 'remember me' not in preview(primed_env, ['--color=never', '--hide-notes', 'vim']).stdout


def test_preview_script_handles_hostile_package_name_safely(primed_env):
    r = preview(primed_env, ['--', "x'; touch /tmp/pwned; '"])
    assert r.returncode == 0 and not os.path.exists('/tmp/pwned')


# ---- integration against the real dpkg (skips elsewhere) -----------------------------
@pytest.mark.skipif(not (shutil.which('dpkg-query') and shutil.which('apt-mark')),
                    reason='needs a Debian-based system')
def test_real_system_collection_is_sane():
    recs = collect.collect_packages()
    names = [r['Name'] for r in recs]
    assert len(names) == len(set(names)) > 50           # unique identities
    assert 'dpkg' in names and 'apt' in names
    by = {r['Name']: r for r in recs}
    assert by['dpkg']['Installed_Size'] > 0 and by['dpkg']['Version']
    assert all(r['Install_Reason'] in ('Manually installed', 'Automatically installed (as a dependency)')
               for r in recs)
    # something essential is certainly depended upon
    assert by['libc6']['Required_By'] if 'libc6' in by else True
    # every Required_By entry names a real installed package
    known = set(names)
    for r in recs:
        for dep in filter(None, r['Required_By'].split(', ')):
            assert dep in known
