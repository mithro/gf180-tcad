# Contributing to gf180-tcad

Everything written here is licensed [Apache-2.0](LICENSE). New source files carry the header
`# SPDX-License-Identifier: Apache-2.0`
([SPDX license identifiers](https://spdx.dev/learn/handling-license-info/)).

## Git rules

- One branch and one [worktree](https://git-scm.com/docs/git-worktree) per task, under
  `../gf180-tcad-worktrees/<branch>`. After
  [`git worktree add`](https://git-scm.com/docs/git-worktree), run
  [`git submodule update --init`](https://git-scm.com/docs/git-submodule) in the new worktree
  (and clone with [`git clone --recurse-submodules`](https://git-scm.com/docs/git-clone)), so that
  the [`third_party/gplugins`](https://github.com/mithro/gplugins)
  submodule is checked out. See
  [Getting the source](https://gf180-tcad.readthedocs.io/en/latest/reproduce/index.html#getting-the-source).
- Small logical commits.
- Never commit on `main`.
- Open the PR inside [`mithro/gf180-tcad`](https://github.com/mithro/gf180-tcad) (always pass
  `--repo mithro/gf180-tcad`).
- Every PR is reviewed, and findings are fixed, before merge.
- Merge with [`gh pr merge --merge`](https://cli.github.com/manual/gh_pr_merge) (a real merge
  commit). No squash or rebase merges.
  (Rebasing a branch while you are still working on it is fine.)
- `main` is the latest stable state.

## Review process

Every PR is reviewed by an independent review agent (a separate subagent that did not
write the change). Its findings are fixed before merge. The project owner spot-checks
PRs but is not a merge blocker.

## PR checklist

- The documentation is updated in the same PR as the change, never later. The author updates
  every status page the change affects: the Status section of [README.md](README.md), the
  Status admonition of [docs/index.md](docs/index.md), the task checkboxes of the plan in
  [docs/superpowers/plans](docs/superpowers/plans) (ticked with the PR number and merge date),
  the [limitations index](docs/limitations/index.md), and the results and comparison pages
  whose content it changes. [`tests/test_docs_status.py`](tests/test_docs_status.py) catches
  only two narrow cases (a top-level results tree the Status does not name, and a few known
  stale phrases); passing it says nothing about whether the pages are current.
- Every review checks that those pages were updated correctly at the same time. A PR whose
  documentation lags behind the change is "needs fixes", like any other finding.
- Docs pages follow the writing rules of the [design spec, section 10.3](docs/superpowers/specs/2026-10-18-gf180-tcad-design.md):
  the user's `writing-sourced-docs` and `docs-writing` skills (from the user's
  [mithro/dot-claude](https://github.com/mithro/dot-claude) repository; `docs-writing` is on its
  `docs-writing-skill` branch). A reader page states only what a source backs, with the source
  linked in the sentence. It carries no hedge or unknown word (`not yet`, `unverified`, `not public`,
  `probably`, `likely`, `about` before a number and the others listed in section 10.3). An
  unsourced statement is removed and filed as an issue. Before handing a page over, run
  `uv run --no-project python -I tools/measure_docs.py <page>` ([`tools/measure_docs.py`](tools/measure_docs.py)), `uv run --no-project python -I tools/docs_lint.py --no-front-matter <page>` ([`tools/docs_lint.py`](tools/docs_lint.py)) and the docs tests
  ([`tests/test_doc_style.py`](tests/test_doc_style.py),
  [`tests/test_doc_measure.py`](tests/test_doc_measure.py)); a PR that fixes pages lowers
  [`tests/doc_measure_baseline.json`](tests/doc_measure_baseline.json) with
  `uv run --locked python tests/test_doc_measure.py --write-baseline`.

## Forks only

Never interact with upstream or third-party repositories: no PRs, issues, comments or
stars. Changes to third-party code live only in forks under [github.com/mithro](https://github.com/mithro), and
PRs are opened only inside `mithro/*` repositories.

## Public data only

Every process or [PDK](https://gf180-tcad.readthedocs.io/en/latest/glossary.html#term-PDK) number in the repository, docs, commit history and images must
cite a public source. No NDA-derived material (GF portal, sales kits, private notes)
may enter the repo in any form.

## Latest versions

Use the latest version of every tool, library, PDK and base image. An older version
may be used only to prove that something once worked (for example, a plugin against
the release it was written for). The item is then upgraded to the latest version and
re-verified, and the "worked on old, verified on latest" step is recorded in the docs.

## Development

Needs [uv](https://docs.astral.sh/uv/); lint with [ruff](https://docs.astral.sh/ruff/), test
with [pytest](https://docs.pytest.org/).

```
uv sync --locked
uv run --locked python tools/install-hooks
make lint
uv run pytest -m "not sandbox"
```

`make lint` (ruff check, ruff format --check) is exactly the lint step of the `lint-test` check of
[CI](.github/workflows/ci.yml), which then runs the tests. [`tools/install-hooks`](tools/install-hooks) installs, once per
clone (it covers every git worktree of it), the pre-push hook
[`tools/git-hooks/pre-push`](tools/git-hooks/pre-push): each `git push` first runs `make pre-push` (`make lint`, then
every non-sandbox test except the slow docs build and calibration fits, about a minute) and,
when a pushed commit changes [`docs/`](docs), [`src/`](src), [`results/`](results), README.md or CONTRIBUTING.md,
`make pre-push-docs` (the docs-links rule, a few minutes). A failure refuses the push. A push
can therefore take three minutes or more: an agent runs `git push` in the background or with a
timeout of at least 300 s, and never with `--no-verify`. The hook only checks what most often
broke CI, so run the full `uv run pytest -m "not sandbox"` before asking for review. CI cancels
the run of a superseded commit when a newer one is pushed to the same pull request (runs on
`main` are never cancelled).

By design, the hook also refuses a push of several branches that are not all the checked-out
one, and, when `push.default` is `matching`, any push of a branch other than the checked-out
one. That is what a bare `git push` under `push.default=matching` does, and since every worktree
of a clone shares its branches, it pushes other sessions' unfinished commits (and starts CI on
them). Push with `git push origin HEAD`, and set `git config push.default simple`.

[`uv.lock`](uv.lock) is committed. Tests that run simulators are marked
[`sandbox`](https://gf180-tcad.readthedocs.io/en/latest/glossary.html#term-sandbox); they run only through [`tools/sandbox-run`](tools/sandbox-run)
([sandbox docs](https://gf180-tcad.readthedocs.io/en/latest/reproduce/sandbox.html)) and are excluded from
[CI](.github/workflows/ci.yml) by default.
