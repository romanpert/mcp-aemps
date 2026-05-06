# app/auth.py
"""Optional OAuth 2.1 Resource-Server mode.

mcp-aemps exposes public AEMPS data, so authentication is **off by
default**. When ``OAUTH_ENABLED=true``, every MCP tool call (over HTTP at
``/mcp``) requires a valid Bearer token. stdio is unaffected — stdio is
process-local and gated by OS-level access to the binary.

Architecture: this module implements the **Resource Server** half of the
OAuth 2.1 + RFC 9728 (Protected Resource Metadata) + RFC 7591 (Dynamic
Client Registration) flow described in the MCP Authorization spec
(https://modelcontextprotocol.io/specification/draft/basic/authorization).

We do NOT embed an Authorization Server. The ``OAUTH_ISSUER`` config
value points at an external AS (Auth0, Stytch, Cloudflare Workers OAuth
Provider, Hydra, Keycloak, …) which handles user login, DCR, and token
issuance. We only verify tokens — that's enough to be a compliant
Resource Server while keeping mcp-aemps stateless.

Token verification uses pyjwt's ``PyJWKClient`` (TTL-cached JWKS fetch,
RFC 7517) with full signature + `aud` + `exp` + scope checks. The
expected audience is the server's resource indicator
(``OAUTH_AUDIENCE``).
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

import jwt
from jwt import PyJWKClient

if TYPE_CHECKING:
    from mcp.server.auth.provider import AccessToken
    from mcp.server.auth.settings import AuthSettings as MCPAuthSettings

    from app.config import Settings

logger = logging.getLogger(__name__)


class JWKSTokenVerifier:
    """``TokenVerifier`` implementation that validates a JWT against a remote
    JWKS endpoint.

    Conforms to the FastMCP ``TokenVerifier`` protocol::

        async def verify_token(self, token: str) -> AccessToken | None

    Returns ``None`` (≡ unauthorised) when the token is malformed,
    expired, signed with an unknown key, has the wrong audience, or
    lacks the required scopes. Never raises — logs and refuses.
    """

    def __init__(
        self,
        *,
        jwks_url: str,
        audience: str,
        issuer: str | None,
        required_scopes: list[str],
        cache_ttl_seconds: int = 3600,
    ) -> None:
        self._audience = audience
        self._issuer = issuer
        self._required = set(required_scopes)
        self._jwks_client = PyJWKClient(jwks_url, cache_keys=True, lifespan=cache_ttl_seconds)
        logger.info(
            "JWKSTokenVerifier configured (audience=%s, issuer=%s, required_scopes=%s)",
            audience,
            issuer,
            sorted(self._required),
        )

    async def verify_token(self, token: str) -> "AccessToken | None":
        """Validate a Bearer token and return AccessToken if all checks pass."""
        # Local import — keeps the module importable even when `mcp` SDK is
        # absent (e.g., unit tests that monkeypatch).
        from mcp.server.auth.provider import AccessToken

        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(token).key
        except Exception as exc:
            logger.warning("JWKS lookup failed for token (%s)", type(exc).__name__)
            return None

        try:
            decode_kwargs: dict[str, object] = {
                "key": signing_key,
                "algorithms": ["RS256", "RS384", "RS512", "ES256", "ES384"],
                "audience": self._audience,
                "options": {"require": ["exp", "iat", "aud"]},
            }
            if self._issuer:
                decode_kwargs["issuer"] = self._issuer
            payload = jwt.decode(token, **decode_kwargs)
        except jwt.InvalidTokenError as exc:
            logger.info("token rejected: %s", exc)
            return None

        # Scopes can be space-separated string (RFC 6749) OR an array.
        raw_scopes = payload.get("scope") or payload.get("scp") or ""
        if isinstance(raw_scopes, str):
            token_scopes = set(raw_scopes.split())
        elif isinstance(raw_scopes, list):
            token_scopes = set(raw_scopes)
        else:
            token_scopes = set()

        missing = self._required - token_scopes
        if missing:
            logger.info("token missing required scopes: %s", sorted(missing))
            return None

        return AccessToken(
            token=token,
            client_id=str(payload.get("client_id") or payload.get("sub", "")),
            scopes=sorted(token_scopes),
            expires_at=int(payload.get("exp", time.time() + 60)),
            resource=self._audience,
        )


def make_auth_settings(settings: "Settings") -> "MCPAuthSettings | None":
    """Build FastMCP ``AuthSettings`` when OAuth is enabled, else None."""
    if not settings.oauth_enabled:
        return None
    if not (settings.oauth_issuer and settings.oauth_audience):
        raise ValueError("OAUTH_ENABLED=true requires OAUTH_ISSUER and OAUTH_AUDIENCE to be set.")
    from mcp.server.auth.settings import AuthSettings  # type: ignore[import-not-found]
    from pydantic import AnyUrl

    return AuthSettings(
        issuer_url=AnyUrl(settings.oauth_issuer),
        resource_server_url=AnyUrl(settings.oauth_audience),
        required_scopes=list(settings.oauth_required_scopes),
    )


def make_token_verifier(settings: "Settings") -> JWKSTokenVerifier | None:
    """Build a ``TokenVerifier`` when OAuth is enabled, else None."""
    if not settings.oauth_enabled:
        return None
    if not (settings.oauth_jwks_url and settings.oauth_audience):
        raise ValueError("OAUTH_ENABLED=true requires OAUTH_JWKS_URL and OAUTH_AUDIENCE to be set.")
    return JWKSTokenVerifier(
        jwks_url=settings.oauth_jwks_url,
        audience=settings.oauth_audience,
        issuer=settings.oauth_issuer,
        required_scopes=list(settings.oauth_required_scopes),
    )


def make_protected_resource_metadata(settings: "Settings") -> dict[str, object]:
    """Build the RFC 9728 PRM document published at
    ``/.well-known/oauth-protected-resource``."""
    if not settings.oauth_enabled or not settings.oauth_issuer or not settings.oauth_audience:
        raise ValueError("PRM document is only available when OAuth is enabled.")
    return {
        "resource": settings.oauth_audience,
        "authorization_servers": [settings.oauth_issuer],
        "scopes_supported": list(settings.oauth_required_scopes),
        "bearer_methods_supported": ["header"],
        "resource_documentation": "https://github.com/romanpert/mcp-aemps#oauth",
    }
