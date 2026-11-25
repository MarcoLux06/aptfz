# Releasing

Releases are cut from GitHub: **Actions > Release > Run workflow**, enter a version (no leading `v`, e.g. `0.2.0`)
and optional release notes.

The workflow:

1. validates the version and refuses one whose tag already exists;
2. bumps `__version__` in `src/lib/config.py` (the only place the version lives; the `.deb` and `--version` both read it).
   If the repo is already at that version (typically the first release) there is nothing to commit, and the current
   commit is tagged as is;
3. runs the test suite and builds the `.deb` (`make deb`), **without pushing anything yet**;
4. only if both succeeded: commits the bump (if there was one), tags `vX.Y.Z` and pushes both;
5. creates the GitHub release with `aptfz_X.Y.Z_all.deb` and its `.sha256` attached.

Because the push happens after the tests and the build, a failing run leaves no stray commit or tag. The one remaining
window is step 5: if release creation fails after the push (for example a network error), the tag exists, so re-running
with the same version is refused. Either delete the tag (`git push origin :refs/tags/vX.Y.Z`) and the bump commit's
effect is harmless to repeat, or finish by hand with `gh release create`.

## One-time setup

- **Maintainer name.** The `.deb` needs a `Maintainer:` field. By default it is `Marco Lux <89221170+MarcoLux06@users.noreply.github.com>`
  (a GitHub noreply address, so no private email ends up in the package). To use something else, set a repository
  *variable* (not a secret) named `DEB_MAINTAINER`.
- **Workflow permissions.** The workflow needs write access to contents. If pushes are rejected, check
  *Settings > Actions > General > Workflow permissions*.
- **Branch protection.** The bump commit is pushed straight to the branch the workflow was run on. If that branch
  requires pull requests, the push will be refused; either allow GitHub Actions to bypass it, or run releases from an
  unprotected branch.

## Doing it by hand

```sh
sed -i 's/^__version__ = .*/__version__ = "0.2.0"/' src/lib/config.py
make test
make deb MAINTAINER='Your Name <you@example.org>'
git commit -am "Bump version to 0.2.0" && git tag v0.2.0 && git push origin HEAD v0.2.0
gh release create v0.2.0 build/aptfz_0.2.0_all.deb --title v0.2.0
```
