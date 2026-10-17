# Contributing to gf180-tcad

Everything written here is licensed Apache-2.0. New source files carry the header
`# SPDX-License-Identifier: Apache-2.0`.

## Git rules

- One branch and one worktree per task, under `../gf180-tcad-worktrees/<branch>`.
- Small logical commits.
- Never commit on `main`.
- Open the PR inside `mithro/gf180-tcad` (always pass `--repo mithro/gf180-tcad`).
- Every PR is reviewed, and findings are fixed, before merge.
- Merge with `gh pr merge --merge` (a real merge commit). No squash or rebase merges.
  (Rebasing a branch while you are still working on it is fine.)
- `main` is the latest stable state.

## Review process

Every PR is reviewed by an independent review agent (a separate subagent that did not
write the change). Its findings are fixed before merge. The project owner spot-checks
PRs but is not a merge blocker.

## Forks only

Never interact with upstream or third-party repositories: no PRs, issues, comments or
stars. Changes to third-party code live only in forks under `github.com/mithro/`, and
PRs are opened only inside `mithro/*` repositories.

## Public data only

Every process or PDK number in the repository, docs, commit history and images must
cite a public source. No NDA-derived material (GF portal, sales kits, private notes)
may enter the repo in any form.

## Latest versions

Use the latest version of every tool, library, PDK and base image. An older version
may be used only to prove that something once worked (for example, a plugin against
the release it was written for). The item is then upgraded to the latest version and
re-verified, and the "worked on old, verified on latest" step is recorded in the docs.

## Development

```
uv sync --locked
uv run ruff check
uv run ruff format --check
uv run pytest -m "not sandbox"
```

`uv.lock` is committed. Tests that run simulators are marked `sandbox`; they run only
through `tools/sandbox-run` and are excluded from CI by default.
