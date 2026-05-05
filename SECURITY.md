# Security Policy

## Supported versions

| Version | Supported |
|---|---|
| 0.1.x | ✅ |
| < 0.1 | ❌ |

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
- Server-side request forgery (SSRF), authentication/authorization bypass,
  injection in URL/headers/body, log tampering, supply-chain (deps,
  workflows, build), insecure defaults.

**Out of scope** (filed via the normal issue tracker)
- AEMPS upstream availability or correctness — CIMA is the source of truth.
- Bugs in user-supplied Redis/OTel infrastructure.
- Misuse of the data downstream (clinical decisions made on the basis of
  CIMA data are the integrator's responsibility).

## Data handling

- **No PII processed.** CIMA returns metadata about authorised medicines —
  no patient records, no prescriptions, no pharmacovigilance reports tied
  to individuals.
- **No request body logging.** Logs include endpoint path, status, and
  timing; never query content with user identifiers.
- **No outbound network beyond CIMA.** The server only contacts
  `cima.aemps.es` (and Redis, if configured).
- **Audit trail** — structured JSON logs with correlation IDs are produced
  by default. Retention configurable via `LOG_RETENTION_DAYS`.

## Self-imposed rate limits (per-user)

AEMPS does not publish formal rate limits on CIMA. We self-impose the
following defaults to be a good citizen of the public registry:

| Tier | Per-user limit | Per-server fan-out cap |
|---|---|---|
| Local-only (no CIMA call) | 120 / minute | n/a |
| Single CIMA call | 30 / minute | n/a |
| Document fetch (PDF/HTML) | 10 / minute | n/a |
| Batch / multi-call | 6 / minute | 4 concurrent |

In addition, the server caps total concurrent CIMA connections via
`asyncio.Semaphore` and uses `If-None-Match` revalidation against AEMPS's
30-minute HTTP cache.

These limits are **courtesy defaults**, not AEMPS-mandated thresholds.

## Hardening checklist for production deployments

- [ ] Set `ALLOWED_ORIGINS` to your real frontends (never `*` in production)
- [ ] Set `METRICS_KEY` to gate `/internal/metrics`
- [ ] Run behind a reverse proxy with TLS (nginx, Caddy, Traefik)
- [ ] Provide `REDIS_URL` for distributed rate limiting and cache (multi-replica)
- [ ] Set `LOG_LEVEL=INFO` (not DEBUG) and ship logs to a SIEM
- [ ] Use the Docker image with the non-root user (`UID 10001`)
- [ ] Enable OTel export by deploying the **Enterprise Edition** if you need
      distributed tracing (the Community Edition does not bundle OTel)
