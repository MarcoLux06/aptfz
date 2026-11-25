# aptfz

**A fast explorer for the packages installed on your Debian-based system**: rich previews, powerful filtering and
per-package notes, built on top of [fzf](https://github.com/junegunn/fzf). It is the apt counterpart of pacfz, with the
same flags and the same feel.

Two front-ends share one query engine:

- **`aptfz`**: an interactive fzf picker with a colorized preview pane.
- **`aptq`**: the same engine, non-interactive, one package name per line. Made for pipes and scripts.

There is no database and nothing to refresh: the package list is cached in one small file that checks itself against
dpkg and apt on every run and rebuilds in a fraction of a second when something changed.

## Features

**Filtering.** Narrow the list by install reason (manual / automatic), by whether anything *requires* a package, and by
whether anything *recommends or suggests* it. Filters stack.

**Field and free-text search.** Search any field with substring or exact matching (`-f`, `-a`, `-x`), and invert either
the whole query or just one filter (`-v`).

**Sorting and totals.** Sort by any field; `-t` reports the installed size of exactly what your filters selected.

**Notes.** Attach a free-text note to any package. Notes show up in the preview pane.

**Reverse dependencies.** dpkg only records what a package needs, not what needs *it*. aptfz computes it, so the preview
shows *Required By*, *Recommended By* and *Suggested By* alongside the forward fields.

## Requirements

- A Debian-based system (Debian, Ubuntu, Mint, ...) with `dpkg` and `apt`.
- `python3` 3.8 or newer, standard library only.
- `fzf`, for the interactive `aptfz` (`aptq` works without it): `sudo apt install fzf`.
- `python3-pytest`, only to run the test suite.

## Install

Download `aptfz_<version>_all.deb` from the GitHub Releases page and install it with
`sudo apt install ./aptfz_<version>_all.deb`. Or build it yourself:

```sh
make install                                          # builds, then `sudo apt install ./build/aptfz_*.deb`
make deb MAINTAINER='Your Name <you@example.org>'     # just build it (output in build/)
```

| What                        | Where                    |
|-----------------------------|--------------------------|
| `aptfz`, `aptq` launchers   | `/usr/bin`               |
| Python modules              | `/usr/share/aptfz/lib`   |
| Shell key bindings          | `/usr/share/aptfz/`      |
| Man pages                   | `man aptfz`, `man aptq`  |

Or run straight from a checkout, no install: `./src/aptfz`, `./src/aptq`.

### Shell shortcut

```sh
source /usr/share/aptfz/key-bindings.bash    # bash
source /usr/share/aptfz/key-bindings.zsh     # zsh
```

Binds **ctrl+p** to open the picker and insert the chosen name at your cursor, so `apt remove ` + ctrl+p + Enter gives
you `apt remove firefox`, ready to run.

### Uninstall

```sh
sudo apt remove aptfz
```

Your notes (`~/.local/share/aptfz/notes.json`) and the cache are never touched by this.

## Usage

```
Usage: aptfz [OPTIONS]

Filter Options:
  -e, --explicit      Show only manually installed packages
  -d, --deps          Show only automatically installed packages
  -n, --notadep       Not required by any installed package
  -k, --notoptdep     Not recommended or suggested by any installed package
  --has-note          Only packages that have a user note
  --no-note           Only packages without a user note
  -f, --field F V     Only packages where field F matches value V (repeatable)
  -a, --any V         Only packages where any field matches value V (repeatable)
  -x, --exact-match   Exact equality instead of case-insensitive substring
  -v, --invert [F]    Bare -v inverts everything else; -v FILTER inverts just
                      that one canned filter (repeatable)

Sort Options:
  -s, --sort-by [F]   Sort by field F (bare -s means Installed_Size)
  --asc / --desc      Sort direction

Size:
  -t, --totalsize     Total size of the (filtered) packages

Display Options (aptfz only):
  --exact             Exact matching in fzf
  --hide-notes        Hide notes in the preview

Notes (aptfz only):
  -D <pkg> <note>     Set a note          -D <pkg> -d   Delete it
  --notes-list        List all notes
```

`aptq -h` / `aptfz -h` print the complete reference, including the list of fields.

### Examples

```sh
aptq -e                       # manually installed packages
aptq -e -n                    # ... that nothing requires
aptq -e -n -k -s --desc       # ... and nothing recommends or suggests, biggest first
aptq -d -t                    # total size of dependency packages
aptq -f Section games         # packages in a section containing "games"
aptq -n -k | xargs apt show   # feed names to other tools
aptfz -e -n                   # browse those interactively
aptfz -D htop "check swap use with this"
```

### Inverting

Bare `-v` inverts *everything else you asked for*, as a single unit. `-v FILTER` inverts *only that one named filter*
and leaves every other filter in place. It is repeatable, and repeated `-v FILTER`s combine as NOT(A AND B).

```sh
aptq -e -v notadep                 # manually installed packages that something requires
aptq -e -v notadep -v notoptdep    # manual packages where NOT(notadep AND notoptdep)
                                   # i.e. something requires, recommends or suggests them
aptq -f Name lib -v                # everything whose name does NOT contain "lib"
```

`FILTER` is one of `explicit`, `deps`, `notadep`, `notoptdep` (or `e`/`d`/`n`/`k`). `--has-note`/`--no-note` are never
inverted by `-v`.

## How apt's concepts map

apt differs from pacman in ways that matter for these filters, so here are the exact definitions.

| Flag | Meaning here |
|------|--------------|
| `-e` / `-d` | Manual / automatic, straight from `apt-mark showmanual` / `showauto`. |
| `-n` | No installed package lists it in `Depends` or `Pre-Depends`. |
| `-k` | No installed package lists it in `Recommends` or `Suggests`. |

**Install reason is noisier than on Arch.** Installers and tasksel mark many packages as manual, so `-e` alone is less
selective than pacman's "explicitly installed". `-e -n` ("manual, and nothing needs it") is usually the useful view. Even
then, metapackages like `ubuntu-desktop` depend on hundreds of packages, which then count as required.

**Recommends is its own tier.** apt installs Recommends by default; Suggests is the closest thing to pacman's optional
dependencies. They are shown, and filtered, separately (`Recommends`/`Suggests` forward, `Recommended By`/`Suggested By`
in reverse; `-k` means neither).

**Reverse dependencies are conservative.** For `a | b` alternatives every *installed* alternative counts as required, and
virtual packages resolve through `Provides`. Version constraints are ignored. The aim is that `-n` never lists a package
that something really needs; it may occasionally omit one that something only *could* use instead.

**Multiarch.** A package is shown by the name apt accepts: the plain name normally, `name:arch` for a foreign
architecture (e.g. `libc6:i386`). Notes are keyed the same way.

**Sizes** are dpkg's `Installed-Size`, a figure the package maintainer declares, not a measurement of the disk.

**Not carried over from pacfz:** foreign/AUR (`-m`) and orphans (`-o`). Third-party repositories are ordinary apt
sources, so there is no AUR-style "foreign" notion; `apt autoremove` is the tool for orphans.

## Where your files live

| File         | Default location                  | Override           |
|--------------|-----------------------------------|--------------------|
| Package cache| `~/.cache/aptfz/packages.json`    | `APTFZ_CACHE_PATH` |
| Notes        | `~/.local/share/aptfz/notes.json` | `APTFZ_NOTES_PATH` |

Both follow the XDG base-directory variables. The cache is disposable: delete it any time. Notes are yours; a notes file
that can't be parsed is never overwritten.

## Development

```sh
make test      # pytest
make check     # syntax checks
make deb       # build the package
```

See [docs/architecture.md](docs/architecture.md) for how it is put together and
[docs/releasing.md](docs/releasing.md) for cutting a release.

## License

MIT. See [LICENSE](LICENSE).
