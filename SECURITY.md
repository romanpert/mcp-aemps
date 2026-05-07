# Security Policy

## Supported versions

| Version | Status | Notes |
|---|---|---|
| 0.4.x | ✅ Active | Security + bug fixes |
| 0.3.x | — | Skipped (jumped 0.2.11 → 0.4.0); no public release |
| 0.2.x | ⚠️  EOL | Last v0.2.11 (2026-05-06). Upgrade to 0.4.x |
| < 0.2 | ❌ | Unsupported |

Always run `mcp-aemps>=0.4.10` — that release fixed the 7-of-9 installer
bug that wrote `http://localhost:8765/mcp` into client configs by
default, leaking a non-functional configuration that could be confused
for a working install (operational hazard, not a CVE).

## Reporting a vulnerability

**Do not file a public GitHub issue for security vulnerabilities.**

Email `roman.p98@gmail.com` with:

- Type of vulnerability (auth, injection, denial-of-service, etc.)
- Affected version(s)
- Reproduction steps
- Suggested fix (if any)

You should receive an acknowledgement within **48 hours**. Coordinated
disclosure is preferred — typical timeline:

1. Day 0: report received
2. Day 0–7: triage and fix in private branch
3. Day 7–14: patch release on PyPI + advisory published on GitHub
4. Public disclosure: with patch release notes

## Threat model

`mcp-aemps` is a **read-only proxy** over the public AEMPS CIMA REST API.

**In scope**

- Server-side request forgery (SSRF), auth bypass on the OAuth 2.1
  Resource-Server mode, header / URL / body injection, JWT validation
  bypass, log tampering.
- Supply-chain (deps, workflows, build) including the npm wrapper,
  the MCPB bundle and the GitHub Pages site.
- DNS rebinding against the Streamable-HTTP `/mcp` endpoint
  (mitigated by FastMCP's `TransportSecuritySettings`; see
  `MCP_AEMPS_DNS_REBINDING_PROTECTION` env var).
- Insecure defaults shipped to first-time users.
- Secret exposure in logs, errors, telemetry.

**Out of scope** (file via the normal issue tracker)

- AEMPS upstream availability or correctness — CIMA is the source of
  truth. Stale or wrong data on CIMA is not a `mcp-aemps` issue.
- Bugs in user-supplied Redis/Valkey, OTel collector, or reverse-proxy
  infrastructure.
- Misuse of the data downstream — clinical decisions made on the basis
  of CIMA data are the integrator's responsibility. Patient-facing
  prompts ship a "no medical advice" disclaimer (covered by CI).
- Vulnerabilities in third-party extensions or forks of this server.
  They are out of scope for this repository's security policy.

## Authentication & authorization (v0.2.8+)

OAuth 2.1 Resource-Server mode is **opt-in**:

- Disabled by default (CIMA itself is public; many self-hosted users
  want zero auth).
- Enable with `OAUTH_ENABLED=true` plus `OAUTH_ISSUER`,
  `OAUTH_JWKS_URL`, `OAUTH_AUDIENCE` and the required scopes via
  `OAUTH_REQUIRED_SCOPES`.
- We do **not** embed an Authorization Server — bring your own Auth0
  / Keycloak / Hydra. RFC 9728 Protected Resource Metadata is exposed
  at `/.well-known/oauth-protected-resource` so DCR-aware clients
  discover the AS automatically.
- JWT validation uses `pyjwt[crypto]`. We never re-introduced
  `python-jose` (CVE-2024-33663) — covered by a hard rule in
  `CLAUDE.md`.
- Stdio transport is **never** gated by OAuth — the spawn is local to
  the host process; access control is whatever the host enforces.

### JWT algorithm whitelist (audited 2026-05-07)

The token verifier (`app/auth.py:90-98`) calls `jwt.decode` with an
explicit, hard-coded algorithm whitelist:

```python
algorithms = ["RS256", "RS384", "RS512", "ES256", "ES384"]
```

`HS256` and other symmetric algorithms are **not** accepted, which
prevents the classic "alg confusion" attack (where an attacker
replays an asymmetric public key as an HMAC secret). `none` is also
rejected — pyjwt enforces signature presence when `algorithms` is
non-empty. Required claims (`exp`, `iat`, `aud`) are enforced via
`options={"require": [...]}`. If `OAUTH_ISSUER` is set, `iss` is
also validated.

Audit your Authorization Server emits tokens with one of these
algorithms; if it emits `EdDSA` / `PS256` etc., open an issue and
we'll evaluate widening the list.

### Anonymous mode + bind host (acceptable residual risk)

When `OAUTH_ENABLED=false` (the default), every HTTP client that can
reach the listening port can call MCP tools without authentication.
The default `uvicorn_host` is `0.0.0.0` (bind to all interfaces) so
the CLI examples (`mcp-aemps up`) work behind reverse proxies
without extra config.

This is **acceptable residual risk** because the data plane is
read-only public CIMA data — no PII, no patient context, no write
methods. But it is a footgun on a multi-tenant or untrusted network:

- **Single-user dev / loopback only**: bind to `127.0.0.1` explicitly
  (`mcp-aemps up --host 127.0.0.1`) so only local processes can
  reach the port.
- **Office LAN / cloud VPC with untrusted neighbours**: enable
  `OAUTH_ENABLED=true` (audience-bound JWT) **or** restrict access
  via firewall / security group / reverse-proxy `allow` rules.
- **Public internet**: always enable both OAuth and DNS rebinding
  protection. mcp-aemps was not designed to face the open internet
  unauthenticated.

## Transport security (v0.4.5+)

`MCP_AEMPS_DNS_REBINDING_PROTECTION` (default `false`) gates host /
origin validation on the Streamable-HTTP endpoint. Default off because
the threat model — read-only public data, OAuth audience binding —
makes the protection load-bearing only behind a reverse proxy.

When enabling, set:

- `MCP_AEMPS_ALLOWED_HOSTS=your-host.example.com,…`
- `MCP_AEMPS_ALLOWED_ORIGINS=https://your-host.example.com,…`

(Empty defaults route to a dev-friendly allow-list including
`localhost`, `127.0.0.1`, and FastAPI TestClient's `testserver`.)

## Data handling

- **No PII processed.** CIMA returns metadata about authorised
  medicines — no patient records, no prescriptions, no
  pharmacovigilance reports tied to individuals.
- **No request body logging.** Logs include endpoint path, status,
  and timing; never query content with user identifiers. The
  `SENSITIVE_KEYS` set in `app/helpers.py` redacts headers / params
  containing `token`, `password`, `secret`, etc. before they reach
  any log line.
- **No outbound network beyond CIMA + PyPI.** The server only
  contacts:
  - `cima.aemps.es` (every CIMA tool call).
  - `pypi.org` once per process startup, for the
    outdated-version check (v0.4.11+). Skip with
    `MCP_AEMPS_SKIP_UPDATE_CHECK=1` for air-gapped deployments.
  - Redis (only if `REDIS_URL` is configured).
- **Audit trail** — structured JSON logs with correlation IDs are
  produced by default. Retention configurable via
  `LOG_RETENTION_DAYS`. The log directory defaults to a per-user
  OS-canonical path (`~/.local/state/mcp-aemps/logs` on Linux,
  `%LOCALAPPDATA%\mcp-aemps\logs` on Windows,
  `~/Library/Application Support/mcp-aemps/logs` on macOS); falls
  back to the system temp dir, then to console-only logging — Settings
  construction never raises on read-only filesystems.

## Self-imposed rate limits (per-user)

AEMPS does not publish formal rate limits on CIMA. We self-impose
defaults to be a good citizen. Tuned 2026-05-08 for multi-agent pharma
intranet deployments:

| Tier | Per-user limit | Notes |
|---|---:|---|
| Local-only (no CIMA call) | 500 / minute | metadata-only |
| Single CIMA call | 300 / minute | most tools |
| Document fetch (PDF/HTML) | 200 / minute | leaflets / SmPCs |
| Batch / multi-call | 100 / minute | fan-out tools |

In addition, two **process-wide** caps protect the upstream:

- `CIMA_FANOUT_SEMAPHORE` = 32 concurrent — hard ceiling on total
  in-flight CIMA requests across all clients.
- `BATCH_FANOUT_LIMIT` = 20 — max parallel CIMA calls within a
  single batch endpoint.

These are **courtesy defaults**, not AEMPS-mandated thresholds. The
shared `httpx.AsyncClient` (v0.4.11+) reuses TCP+TLS connections so
the upstream cost per call is much lower than the per-tier numbers
suggest.

## NPM / PyPI / GHCR supply chain

- **PyPI** publication uses Trusted Publisher (OIDC) — no long-lived
  API token in the repo. Configured at the `pypi` GitHub environment
  with reviewer = repo owner.
- **MCP Registry** publication uses `mcp-publisher login github-oidc`
  — no token.
- **npm** publication uses a Granular Access Token scoped only to
  `mcp-aemps` (publish permission). Token lives as repo secret
  `NPM_TOKEN`. Why classic auth and not OIDC: npm's Trusted Publishers
  reject `workflow_dispatch` events by design, and we want manual
  re-firing capability. Granular access (vs Automation token) means
  rotations expire on a known schedule.
- **GHCR (Docker)** uses the workflow's automatic `GITHUB_TOKEN` —
  rotates per-run, scoped to this repo.
- **Docker MCP Registry** auto-PR uses a personal access token
  (`MCP_REGISTRY_PAT`, scope `public_repo`) for opening PRs against
  the docker/mcp-registry fork. Only fires on MINOR releases (v0.x.0)
  to avoid review noise.

## /internal/metrics token management (audited 2026-05-07)

The metrics endpoint protects access via `X-Metrics-Key` matched
against the `METRICS_KEY` env var (`app/factory.py:212-219`). The
comparison is plain string equality, but the endpoint is rate-limited
on the `local` tier (500/min) — brute-forcing a long random key in
that budget is impractical.

What the endpoint exposes: aggregate request counters keyed by path,
HTTP-status histograms, in-flight count, and process uptime. **No
secrets, no tokens, no PII** — the data is operational, not
sensitive. Even a leaked `METRICS_KEY` does not compromise medicine
data, OAuth tokens, or any other asset.

What the endpoint does **not** provide: token rotation. The same
static `METRICS_KEY` remains valid until you change the env var and
restart. Treat it as a long-lived secret:

- Generate with `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
- Rotate annually, or immediately on suspected leak.
- For multi-tenant production scrapers, prefer fronting `/internal/metrics`
  behind a reverse proxy that does its own (short-lived) auth, and
  treat the static key as a defense-in-depth fallback.
- Loud warning is logged on startup if `METRICS_KEY` is unset
  (`app/factory.py:236-240`); the endpoint stays public-readable in
  that case, which is fine for single-tenant dev but should never
  reach production.

## Hardening checklist for production deployments

- [ ] Set `ALLOWED_ORIGINS` to your real frontends (never `*` in prod).
- [ ] Set `METRICS_KEY` to gate `/internal/metrics`.
- [ ] Enable `MCP_AEMPS_DNS_REBINDING_PROTECTION=true` and configure
      `MCP_AEMPS_ALLOWED_HOSTS` / `_ORIGINS` for your reverse-proxy
      hostname.
- [ ] Run behind a reverse proxy with TLS (nginx, Caddy, Traefik).
- [ ] Provide `REDIS_URL` for distributed cache, rate limiting, and
      ETag store sharing across replicas.
- [ ] Enable `OAUTH_ENABLED=true` with audience binding to gate the
      Streamable-HTTP endpoint when serving non-trusted clients.
- [ ] Set `LOG_LEVEL=INFO` (not DEBUG) and ship logs to a SIEM. The
      Claude Code hook recipes in the README work for this.
- [ ] Use the Docker image with the non-root user (UID 10001).
- [ ] Bind explicitly to `127.0.0.1` if loopback-only
      (`--host 127.0.0.1`) — anonymous mode + `0.0.0.0` is fine in
      single-user dev but exposes the listener to LAN neighbours
      otherwise.

## Threat model audit log

Every minor release ships with an end-to-end review of this file's
claims against the running code. The most recent pass:

- **2026-05-07 (v0.4.15)** — STRIDE walk over the running v0.4.15
  surface. Findings: 0 P0, 1 P1 (JWT alg whitelist confirmed sound;
  documented above), 2 P2 (metrics token rotation guidance + DNS
  rebinding default-off rationale; both documented). Already
  mitigated: token leak in OAuth errors, CIMA URL injection, path
  traversal in HTML downloads, secrets in `safe_dump`, CORS,
  rate-limit bypass via HTTP method override, predictable
  correlation IDs, Docker non-root, GitHub Actions OIDC scope.
  Acceptable residual: anonymous mode on `0.0.0.0` (documented
  above with mitigation guidance per deployment topology).
- [ ] Set `MCP_AEMPS_SKIP_UPDATE_CHECK=1` in air-gapped deployments
      (no outbound to PyPI). Keep it unset in normal deployments —
      the WARNING surfaces when CVE patches land.
- [ ] If you need distributed tracing, plug an OTel exporter via the
      factory's `extra_middleware` / `startup_hooks` extension points.
      The default build does not bundle OTel — keep deps minimal.
