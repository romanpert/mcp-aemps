# Contributing to mcp-aemps

Thank you for your interest in contributing! This document describes the
workflow, standards, and review process.

> **Maintainer:** Román Pérez Dumpert · `roman.p98@gmail.com`
> **License:** Apache-2.0

---

## Branching model — GitFlow (simplified)

```
                                ┌────────────────┐
                                │   master       │  ← protected. PRs only from `dev`. Tagged releases.
                                └────────┬───────┘
                                         │ release PR (squash-merge)
                                ┌────────┴───────┐
                                │     dev        │  ← protected. Default integration branch.
                                └────────┬───────┘
                                         │ feature PRs
                  ┌──────────────────────┼──────────────────────┐
            feature/<topic>        fix/<topic>           docs/<topic>
```

**Rules**

| Branch | Direct push | PR target | Reviews |
|---|---|---|---|
| `master` | ❌ (maintainer bypass only, for tagged releases) | from `dev` only | Maintainer approval required |
| `dev` | ❌ (maintainer bypass only) | from `feature/*`, `fix/*`, `docs/*`, `chore/*` | Maintainer approval required |
| `feature/*`, `fix/*`, `docs/*`, `chore/*` | ✅ | targets `dev` | n/a |

### Branch naming

- `feature/<short-kebab-description>` — new functionality
- `fix/<issue-id-or-short-description>` — bug fixes
- `docs/<area>` — documentation only
- `chore/<area>` — refactor, tooling, deps, no feature/bug change
- `release/vX.Y.Z` — *maintainer only*; cuts a release from `dev` to `master`

---

## Commit messages — Conventional Commits

Format: `<type>(<scope>): <imperative summary>`

```
feat: add new endpoint /problemas-suministro/dcpf
fix(rate_limits): correct 429 Retry-After header
docs(readme): document REDIS_URL fallback behaviour
chore(deps): bump httpx to 0.28.1
test(installers): cover Codex idempotent path
refactor(cache): extract InMemoryCache into separate class
ci: add pytest matrix for python 3.11/3.12/3.13
```

**Types**: `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `ci`, `perf`, `build`, `release`.

**Body** (optional): explain *why*, not *what*. The diff shows what changed.

**Footer** (optional): `Closes #42`, `Refs #17`, `BREAKING CHANGE: ...`

---

## Pull request lifecycle

1. **Open an issue first** for non-trivial changes — describe motivation, design, and acceptance criteria.
2. Fork the repo (external contributors) or branch from `dev` (collaborators).
3. Implement on `feature/<topic>`. Keep PRs small and focused.
4. **Update documentation in the same PR** if you touched anything user-visible. The doc surface and the code surface ship together — never "I'll add the docs in a follow-up PR". This is enforced by review, not CI:
   - `README.md` + `README.en.md` for user-facing features (install commands, env vars, tool catalogue).
   - `SECURITY.md` for anything that changes the threat model, supply-chain surface, secret handling, or a hardening default.
   - `CHANGELOG.md` for every release (Keep a Changelog format).
   - `CONTRIBUTING.md` for any workflow / standards change.
   - Inline code comments for non-obvious "why" decisions (per `CLAUDE.md`).
5. Run the **full pre-commit checklist** locally:
   ```bash
   ruff check app/ tests/
   ruff format --check app/ tests/
   pytest -q
   python -X utf8 -c "import json,urllib.request,jsonschema; d=json.load(open('server.json')); jsonschema.validate(d, json.load(urllib.request.urlopen(d['\$schema']))); print('server.json OK')"
   ```
   All four must pass before you stage files. CI runs the same checks plus the MCP Inspector compliance smoke and a multi-Python-version test matrix; "passes locally" is necessary but not sufficient.
6. Open the PR against `dev`. Use the PR template.
6. CI must pass: `Lint`, `Test (3.11/3.12/3.13)`, `Build`, `Validate server.json`.
7. Maintainer review — expect feedback within 5 business days.
8. Squash-merge into `dev`. Branch auto-deletes.

### Release workflow

Releases are fully automated. As a contributor you do **not** push to
`master` directly. The maintainer cuts the release from `dev` and tags it;
the `release.yml` workflow handles PyPI publication (Trusted Publisher OIDC)
and MCP Registry submission (github-oidc) — no manual tokens involved.

---

## Code standards

### Style

- Python 3.11+. Type hints everywhere; on `app/stdio_server.py` annotations stay eager (no `from __future__ import annotations`) because FastMCP's `func_metadata` resolves them via `__globals__` at registration time.
- **Formatter:** `ruff format` (line length 110).
- **Linter:** `ruff check` — config in `pyproject.toml`.
- No `print()` in app code — use `logging`.
- All CIMA HTTP calls go through `app/cima_client.py` — no raw `httpx` calls in routes. The shared `_get_shared_client()` is the only correct entry point; never instantiate an `AsyncClient` directly in app code outside that module.

### Architectural rules

- **Hard scope rule** (locked 2026-05-07): Community Edition mirrors **CIMA REST API endpoints only**. New MCP tools must be a 1:1 wrapper around an officially-documented CIMA endpoint. Anything else (image processing, PDF extraction, multi-NCA aggregation, snapshot exports, scrapers) belongs in the closed-source `mcp-aemps-enterprise` repo, not here. See `CLAUDE.md` for the rationale.
- **Quality-only window v0.4.x → v1.0.0.** Improvements until 1.0.0 are efficiency / security / scalability / modularity. New endpoints land **only** if AEMPS publishes them.
- **Thin routes**: route handlers (`app/routes/*.py`) delegate to `cima_client` + `helpers`. No business logic in route bodies.
- **Factory-only app instantiation**: never create a `FastAPI()` instance directly outside `app/factory.py`. Downstream consumers extend via `create_app(extra_routers=..., extra_middleware=..., startup_hooks=...)`.
- **Optional Redis**: code must work without Redis. If you add a Redis-dependent feature, gate it behind `if settings.redis_url`.
- **No PII logging**: CIMA returns medicine metadata only. Don't add anything that correlates queries to user identity.

### Tests

- New code must have tests in `tests/`.
- Tests must be hermetic — pass `config_path` (or equivalent) so they never touch the user's real config.
- Use `pytest`. Async tests use `pytest-asyncio`.
- The CI runs the full suite on Python 3.11, 3.12, 3.13.

---

## Reporting bugs / requesting features

Use GitHub Issues. Provide:

- **Bug**: minimal repro (URL, request body, observed vs. expected response), Python version, platform.
- **Feature**: motivation, the official CIMA endpoint or capability it maps to, expected interface.

Security issues — see `SECURITY.md` (do not file public issues for vulnerabilities).

---

## Code of Conduct

Be professional. Be respectful. The pharmaceutical/healthcare domain attracts a wide range of contributors (developers, regulatory experts, healthcare professionals). Assume good faith and ask clarifying questions before disagreeing.

---

## Development quick-start

```bash
git clone https://github.com/romanpert/mcp-aemps.git
cd mcp-aemps
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e .
pip install pytest pytest-asyncio ruff

mcp-aemps dev                                          # auto-reload server on :8000
pytest tests/ -v                                       # run tests
ruff check app/ tests/                                 # lint
ruff format app/ tests/                                # auto-format
```

---

## Questions

Open a GitHub Discussion or email `roman.p98@gmail.com`.
