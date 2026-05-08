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
- JWT validation uses `pyjwt[crypto]` with an asymmetric-only
  algorithm whitelist and required-claim enforcement. We never
  re-introduced `python-jose` (CVE-2024-33663) — covered by a hard
  rule in `CLAUDE.md`.
- Stdio transport is **never** gated by OAuth — the spawn is local to
  the host process; access control is whatever the host enforces.

When `OAUTH_ENABLED=false` (the default), the data plane is open to
any client that can reach the listening port. CIMA data is public
read-only metadata, but you should still restrict reachability via
network policy (firewall, VPC security group, reverse-proxy allow
rules, or loopback-only bind) when the listener is exposed to
untrusted neighbours. See the hardening checklist below.

## Transport security (v0.4.5+, hardened in v0.4.16)

Three secure-by-default flips landed in v0.4.16. Pre-0.4.16 deployments
that relied on the previous lax defaults must update one or more env
vars / CLI flags before upgrading.

- **Loopback bind by default.** `UVICORN_HOST` defaults to `127.0.0.1`
  (was `0.0.0.0` until v0.4.15). The listener is no longer reachable
  from the LAN unless you explicitly opt in. Docker / reverse-proxy
  deployments use `mcp-aemps up --bind-all` (the shipped Dockerfile
  already does); bare-metal deployments that need LAN reachability
  set `UVICORN_HOST=0.0.0.0` or pass `--bind-all`.
- **DNS rebinding protection on by default.**
  `MCP_AEMPS_DNS_REBINDING_PROTECTION` defaults to `true` (was `false`
  until v0.4.15). The default `allowed_hosts` list covers `localhost`,
  `127.0.0.1`, `[::1]` and FastAPI TestClient's `testserver`, so dev /
  test workflows keep working. Reverse-proxy deployments must extend
  `MCP_AEMPS_ALLOWED_HOSTS=your-host.example.com,…` and optionally
  `MCP_AEMPS_ALLOWED_ORIGINS=https://your-host.example.com,…`. Set the
  protection env var to `false` only if you accept the residual risk
  (read-only public data + OAuth audience binding bound the impact).
- **`/internal/metrics` fail-closed when `METRICS_KEY` is unset.** The
  pre-0.4.16 startup `WARNING` was routinely missed in noisy log
  streams. The endpoint now returns `503 metrics disabled` until a key
  is configured. Scrapers must send the matching `X-Metrics-Key`
  header.

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

## Hardening checklist for production deployments

- [ ] Set `ALLOWED_ORIGINS` to your real frontends (never `*` in prod).
- [ ] Set `METRICS_KEY` (required since v0.4.16 — endpoint is 503 until
      configured).
- [ ] If exposing behind a reverse proxy, configure
      `MCP_AEMPS_ALLOWED_HOSTS` / `_ORIGINS` for your public hostname.
      DNS rebinding protection is on by default since v0.4.16; without
      these env vars the proxy's hostname is rejected.
- [ ] Run behind a reverse proxy with TLS (nginx, Caddy, Traefik).
- [ ] Provide `REDIS_URL` for distributed cache, rate limiting, and
      ETag store sharing across replicas.
- [ ] Enable `OAUTH_ENABLED=true` with audience binding to gate the
      Streamable-HTTP endpoint when serving non-trusted clients.
- [ ] Set `LOG_LEVEL=INFO` (not DEBUG) and ship logs to a SIEM. The
      Claude Code hook recipes in the README work for this.
- [ ] Use the Docker image with the non-root user (UID 10001).
- [ ] Bind defaults to loopback (`127.0.0.1`) since v0.4.16. Use
      `mcp-aemps up --bind-all` (or `UVICORN_HOST=0.0.0.0`) only when
      the listener must be reachable from outside the host (Docker,
      reverse-proxy on a different host).
- [ ] Rotate `METRICS_KEY` and any OAuth client credentials on the
      schedule your compliance regime requires.
- [ ] Set `MCP_AEMPS_SKIP_UPDATE_CHECK=1` in air-gapped deployments
      (no outbound to PyPI). Keep it unset in normal deployments —
      the WARNING surfaces when CVE patches land.
- [ ] If you need distributed tracing, plug an OTel exporter via the
      factory's `extra_middleware` / `startup_hooks` extension points.
      The default build does not bundle OTel — keep deps minimal.

## Audit cadence

Every minor release is preceded by an internal end-to-end review of
this policy against the running code. Findings that result in
public-facing changes show up in `CHANGELOG.md` under the
`### Security` heading; internal hardening backlog is tracked
privately and rolled into the pre-1.0 milestone.
