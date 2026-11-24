## Type of change

- [ ] hotfix
- [ ] release
- [ ] feature
- [ ] fix
- [ ] docs
- [ ] chore
- [ ] test

## Branch target

- [ ] `develop` (required). `main` only via the `develop` → `main` promotion PR (squash merge pinned).

## Checklist

- [ ] Conventional Commit; subject ≤ 72 columns.
- [ ] `just quality` green locally (lint, format, types, unit).
- [ ] Full `just ci` run — required when preparing a release or hotfix.
- [ ] No secrets committed (keys, `.env*`, `.tepochcalli/{config,db,models,venv,bin}`).
- [ ] Docs/specs updated if a contract changed (tools, config, layout).
- [ ] `docs/BACKLOG.md` §8 entry if requirements changed (+ ADR/amendment if it is a decision).

> CI gate = `quality` + `test-acceptance` + `rust-ci` (< 10 min); the full suite
> stays local — `just ci`, and `just coverage` only at phase close.
