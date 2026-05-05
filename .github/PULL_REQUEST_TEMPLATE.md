# Pull Request

## What changed
<!-- One sentence summary -->

## Why
<!-- Motivation. Link the issue: Closes #N -->

## Type
- [ ] feat — new feature
- [ ] fix — bug fix
- [ ] docs — documentation only
- [ ] chore — refactor / tooling / deps
- [ ] test — tests only
- [ ] release — version bump + changelog

## Checklist
- [ ] PR targets `dev` (or `master` only for release PRs)
- [ ] Branch named `<type>/<short-description>`
- [ ] Conventional commit messages
- [ ] `ruff check app/ tests/` passes
- [ ] `pytest tests/ -v` passes locally
- [ ] New code has tests (if applicable)
- [ ] CHANGELOG.md updated under `[Unreleased]` (for user-visible changes)
- [ ] Maps to an official CIMA endpoint (if adding a tool)
- [ ] No PII logging introduced
- [ ] No required Redis dependency added (must work in-memory)

## How to test
<!-- Concrete steps a reviewer can follow to verify the change -->

## Screenshots / Logs
<!-- If UI/CLI/log output changes -->
