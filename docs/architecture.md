# Architecture

Why aptfz is shaped the way it is. Read this first if you're new to the code.

## Two front-ends, one engine

```
aptfz   interactive: fzf + live preview + notes editing
aptq    non-interactive: prints names (or a total) and exits
   \      /
    src/lib/*.py   (the engine and data layer)
```

`src/aptfz` and `src/aptq` are ~15-line launchers: they locate `lib/` and call `aptfz_cli.run()` / `aptq_cli.run()`.
Neither front-end contains filter logic. A fix in `query.py` is correct in both at once. The only presentation
differences are the ones you'd expect: `aptq` prints bare names, `aptfz` opens the picker and renders previews.

Like pacfz, `src/lib/` is deliberately **not a package** (no `__init__.py`; modules import each other flat). The launchers
add `lib/` to `sys.path`, searching next to the script first (git checkout) and `/usr/share/aptfz/lib` second (installed).
Both layouts mirror each other, so only the base path differs.

## Modules

| Module | Role | I/O? |
|--------|------|------|
| `schema.py` | The normalized record: `FIELD_ORDER`, install-reason strings, field-name resolution | none |
| `config.py` | Version, and cache/notes/dpkg paths (resolved at *call* time) | env only |
| `collect.py` | `dpkg-query` + `apt-mark` -> records. Parsing functions are pure | subprocess |
| `depgraph.py` | Parse dependency fields; compute Required/Recommended/Suggested By | none |
| `cache.py` | Self-validating JSON cache over `collect` | filesystem |
| `query.py` | Filters, invert, search, sort, totals, `-t` sentence | none |
| `render.py` | Preview formatting, sanitizing, `bytes_to_human` | none |
| `notes.py` | JSON notes store | filesystem |
| `common.py` | Shared argparse flags, `SHARED_HELP`, flags -> `query.select` | none |
| `aptq_cli.py`, `aptfz_cli.py` | The two front-ends | stdout/fzf |
| `preview.py` | Script fzf runs for its preview pane | stdout |

Pure modules never print, read `sys.argv` or touch the terminal; the CLI layer owns all of that. That is what keeps
them unit-testable with hand-built records.

## No database: a self-validating cache

pacfz keeps a SQLite cache and you refresh it by hand. aptfz has no database. Collecting everything takes ~0.1-0.2 s, so
queries run in plain Python over a list of dicts, and the only persistence is a JSON cache that exists to make *previews*
(one process per highlighted package) cheap.

The cache can't go stale because it checks itself. It stores a **signature**: mtime, size and inode of

- `/var/lib/dpkg/status`, rewritten (by rename) on every install, upgrade and removal, and
- `/var/lib/apt/extended_states`, rewritten by `apt-mark` and by apt whenever manual/auto marks change.

Each run compares the stored signature to the current one; on mismatch it re-collects and atomically replaces the file
(temp file in the same directory, then `os.replace`). Details worth knowing:

- The signature is taken **before** collecting. If the system changes mid-rebuild, the next run just rebuilds again.
- The cache also records the aptfz version and column list; either changing invalidates it.
- Unreadable, corrupt or truncated cache files are treated as a miss, never an error.
- If the cache can't be written (read-only home), the fresh data is still used, with a warning.
- Layout is `{columns, rows}` (rows as arrays), not a list of dicts: smaller and faster to load.

## Data sources and identity

```
dpkg-query -W -f <FIELD_SEP-delimited fields, RECORD_SEP-terminated>   metadata
apt-mark showmanual / showauto                                          install reason
dpkg --print-architecture                                               native arch
```

- Commands run with `LC_ALL=C` and a **fixed `PATH`**, so output is locale-independent and a poisoned user `PATH` can't
  substitute a fake `dpkg-query`.
- dpkg-query doesn't understand `\x1f`-style escapes, so the real control characters are passed in the format string.
  Records with the wrong field count are skipped with a warning rather than aborting everything.
- Packages in state `rc` (removed, config left) and `un` are skipped; only installed packages are listed.
- **Identity** (`Name`) is the name apt itself accepts: bare for native and `all` packages, `name:arch` for foreign
  architectures. This is deliberately not dpkg-query's `${binary:Package}`, which also qualifies native Multi-Arch: same
  packages (`libc6:amd64`) while `apt-mark` prints them bare. Using one consistent key makes the install-reason join,
  fzf's output, notes and "what you can paste after `apt remove`" all agree.

## Reverse dependencies (`depgraph.py`)

`dpkg` stores forward dependencies only. We invert them over the installed set:

- `Depends` + `Pre-Depends` -> **Required By**; `Recommends` -> **Recommended By**; `Suggests` -> **Suggested By**.
- Conservative resolution: every installed alternative of `a | b` gets an edge; unresolvable names are virtual and go
  through `Provides`; version constraints, `[arch]` and `<profile>` restrictions are stripped and ignored.
- Multiarch: an unqualified dependency prefers candidates of the depender's own architecture (or `all`); a depender of
  arch `all` matches all candidates; `:any` matches all; `:arch` restricts.
- Self-edges are dropped. Cycles are fine (each requires the other).

The guiding rule is "when in doubt, draw the edge": a false edge only hides a package from `-n`; a missing edge would
tell someone a needed package is unused.

## Query model (`query.py`)

Identical semantics to pacfz's `build_query`, expressed as predicates instead of SQL:

- Active canned filters, `-f` and `-a` are **preconditions**, AND'd.
- `-v FILTER ...` AND's the named filters into one group and negates it (NOT(A AND B)); that filter is removed from the
  preconditions.
- Bare `-v` moves *all* conditions into the negated group (error if there are none).
- `invert_each` negates each key independently (for tri-state facet UIs).
- The notes filter is applied *outside* the inversion, so `-v` never flips `--has-note`.
- `-f`/`-a` substring matching is case-insensitive (`casefold`); `-x` is exact and case-sensitive. `-a` ORs across every
  column.
- Sort: size is numeric and descending by default; everything else case-insensitive, ascending, tie-broken by name.

Field names resolve case-insensitively with `' '`, `'-'`, `'_'` equivalent, plus aliases `package`, `depends`, `size`.

## Where output formatting lives

- Package metadata rendering (colors, field order, "None" placeholders, hiding empty optional fields, the note line)
  lives only in `render.render_preview()`. `aptfz` uses it in-process for the final printout and via `preview.py` for
  fzf's preview pane. `aptq` never uses it.
- Help text for the shared flags lives once, in `common.SHARED_HELP`, printed by both front-ends' `-h`.
- Color is on when stdout is a TTY and `NO_COLOR` is unset; the fzf preview command passes `--color=always` explicitly
  because fzf's pane isn't a TTY.

## Flag ownership

| Owner | Flags |
|-------|-------|
| `common.py` (both) | `-e -d -n -k --has-note --no-note -f -a -x -v -s --asc --desc -t -h --version` |
| `aptfz` only | `--exact --hide-notes --print-selection`; `-D` and `--notes-list` (first argument only, routed to notes code, never touching the cache) |
| `aptq` only | nothing extra |

To add a **filter/sort/size flag**: add it in `common.new_parser`, wire it in `select_from_args`, add its text to
`SHARED_HELP`, and implement it in `query.py`. Neither launcher needs a change. To add a **front-end-only flag**: add it
in that front-end's `main()` and document it in its `show_usage()`.

## Security notes

- Package metadata is whatever a maintainer put in a control file. Every value passes through
  `sanitize_terminal_value()` (ANSI/OSC sequences, C0 controls, DEL) before being printed, unconditionally, inside the
  renderer. New code that prints a raw field value should go through it too.
- fzf's `{}` placeholder is shell-quoted by fzf; the preview command quotes the interpreter and script paths with
  `shlex.quote` and passes the name after `--`.
- Cache and notes writes are atomic. A notes file that can't be parsed is never overwritten.

## Testing

`make test`. Nothing in the suite needs root or modifies the system.

- `conftest.py` builds records by hand (`make_record`) and gives every test scratch cache/notes/status paths through the
  `APTFZ_*_PATH` overrides. Those overrides exist for this; users rarely need them.
- `test_collect.py` / `test_depgraph.py` / `test_query.py` / `test_cache.py` / `test_notes_render.py` are pure unit
  tests over crafted input.
- `test_cli.py` runs the real launchers as subprocesses against a *primed* cache (so no dpkg is needed), with a stub
  `fzf` that records its arguments and selects the first line. One class of tests uses the real dpkg/apt and skips
  itself on other systems.

What the suite does **not** cover: a real fzf (the stub verifies what aptfz sends it, not how fzf draws it), and the
rendering of the man pages.
