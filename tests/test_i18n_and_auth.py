"""Tests for the v0.2.8 surface: locale dispatcher (EN/ES) and the
opt-in OAuth 2.1 Resource-Server mode (with PRM endpoint).

Both surfaces are configured via env vars at import time, but tests must
not rely on importlib.reload — reloading ``app.config`` / ``app.factory``
across tests pollutes other modules that hold stale references to the
old ``settings`` instance. We:

* Test the locale dispatcher by importing both ``_mcp_constants_es`` and
  ``_mcp_constants_en`` directly and asserting they expose the same
  public surface.
* Test OAuth by mutating attributes of the singleton ``settings`` (with
  monkeypatch.setattr — pytest auto-restores) and constructing helpers
  with the live values.
"""

from __future__ import annotations

import asyncio
import time

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# i18n locale dispatcher
# ---------------------------------------------------------------------------


def test_es_module_carries_spanish_strings() -> None:
    """The Spanish module exports Spanish content (default locale)."""
    import app._mcp_constants_es as es

    assert "Eres un" in es.MCP_AEMPS_SYSTEM_PROMPT
    assert "Devuelve la ficha completa" in es.medicamento_description


def test_en_module_carries_english_strings() -> None:
    """The English module exports English translations of the same surface."""
    import app._mcp_constants_en as en

    assert "You are a" in en.MCP_AEMPS_SYSTEM_PROMPT
    assert "Returns the complete record" in en.medicamento_description
    # Source citation preserved.
    assert "AEMPS" in en.medicamento_description


def test_both_locales_export_the_same_public_names() -> None:
    """The two _mcp_constants_*.py modules must be drop-in replacements —
    that's how the dispatcher in app/mcp_constants.py picks one or the
    other via star-import."""
    import app._mcp_constants_en as en
    import app._mcp_constants_es as es

    public_es = {n for n in dir(es) if not n.startswith("_") and (n.isupper() or "description" in n)}
    public_en = {n for n in dir(en) if not n.startswith("_") and (n.isupper() or "description" in n)}
    missing = public_es - public_en
    extra = public_en - public_es
    assert not missing, f"EN module missing names from ES: {missing}"
    assert not extra, f"EN module has extra names not in ES: {extra}"


def test_dispatcher_default_falls_back_to_spanish() -> None:
    """Without MCP_AEMPS_LOCALE in env, mcp_constants resolves to ES."""
    import app.mcp_constants as mc

    # The dispatcher imported one of the two locale modules; default is ES.
    assert "Eres un" in mc.MCP_AEMPS_SYSTEM_PROMPT
    # Tool annotations are locale-independent — keep them stable.
    assert mc.READ_ONLY_AEMPS_ANNOTATIONS.readOnlyHint is True


def test_invalid_locale_raises_validation_error() -> None:
    """Construct a fresh Settings with an invalid locale → Pydantic fails."""
    from pydantic import ValidationError

    from app.config import Settings

    with pytest.raises(ValidationError):
        Settings(mcp_aemps_locale="fr")


# ---------------------------------------------------------------------------
# OAuth 2.1 — disabled by default
# ---------------------------------------------------------------------------


def test_oauth_disabled_by_default() -> None:
    """No env vars → no auth, no PRM endpoint, public access keeps working."""
    from app.factory import create_app

    app = create_app(mount_mcp=False)
    with TestClient(app) as client:
        # /health is public regardless.
        assert client.get("/health").status_code == 200
        # PRM endpoint is NOT exposed when OAuth is off.
        assert client.get("/.well-known/oauth-protected-resource").status_code == 404


def test_oauth_helpers_return_none_when_disabled() -> None:
    """auth.make_*() returns None when OAUTH_ENABLED is false."""
    from app.auth import make_auth_settings, make_token_verifier
    from app.config import settings

    assert not settings.oauth_enabled
    assert make_auth_settings(settings) is None
    assert make_token_verifier(settings) is None


# ---------------------------------------------------------------------------
# OAuth 2.1 — enabled mode (settings overridden, JWKS stubbed)
# ---------------------------------------------------------------------------


def _make_jwt_keypair_and_token(audience: str, issuer: str, scopes: str = "mcp:read"):
    """Build an RS256 keypair and a signed token in memory.

    Returns ``(public_pem, token)``. The public PEM is what we'll use to
    stub the verifier's JWKS resolution — no network, no JWK conversion
    edge cases.
    """
    import jwt as _jwt
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    now = int(time.time())
    token = _jwt.encode(
        {
            "iss": issuer,
            "aud": audience,
            "sub": "test-user",
            "client_id": "test-client",
            "scope": scopes,
            "iat": now,
            "exp": now + 3600,
        },
        private_pem,
        algorithm="RS256",
        headers={"kid": "test-key-1"},
    )
    return public_pem, token


class _StubSigningKey:
    """Mimics the object returned by ``PyJWKClient.get_signing_key_from_jwt``
    — only the ``.key`` attribute is read by our verifier."""

    def __init__(self, public_pem: bytes) -> None:
        from cryptography.hazmat.primitives import serialization

        self.key = serialization.load_pem_public_key(public_pem)


class _StubJWKSClient:
    """Drop-in for ``PyJWKClient`` that returns a fixed signing key."""

    def __init__(self, public_pem: bytes) -> None:
        self._sk = _StubSigningKey(public_pem)

    def get_signing_key_from_jwt(self, _token: str) -> _StubSigningKey:
        return self._sk


@pytest.fixture
def _oauth_enabled(monkeypatch):
    """Mutate the live ``settings`` to enable OAuth and patch the verifier
    constructor to use an in-memory JWKS stub. ``monkeypatch`` auto-reverts
    on test teardown — no module reloads, no test-pollution risk."""
    audience = "https://mcp-aemps.test/mcp"
    issuer = "https://auth.test"
    public_pem, token = _make_jwt_keypair_and_token(audience, issuer)

    from app.config import settings

    monkeypatch.setattr(settings, "oauth_enabled", True)
    monkeypatch.setattr(settings, "oauth_issuer", issuer)
    monkeypatch.setattr(settings, "oauth_jwks_url", "https://auth.test/.well-known/jwks.json")
    monkeypatch.setattr(settings, "oauth_audience", audience)
    monkeypatch.setattr(settings, "oauth_required_scopes", ["mcp:read"])

    # Replace the JWKS client at the verifier-class level so any verifier
    # constructed inside this test uses the in-memory stub.
    import app.auth as auth_mod

    def patched_init(
        self,
        *,
        jwks_url,
        audience,
        issuer,
        required_scopes,
        cache_ttl_seconds=3600,
    ):
        self._audience = audience
        self._issuer = issuer
        self._required = set(required_scopes)
        self._jwks_client = _StubJWKSClient(public_pem)

    monkeypatch.setattr(auth_mod.JWKSTokenVerifier, "__init__", patched_init)

    yield {
        "audience": audience,
        "issuer": issuer,
        "public_pem": public_pem,
        "token": token,
    }


def test_oauth_enabled_publishes_prm_endpoint(_oauth_enabled) -> None:
    """When OAuth is on, /.well-known/oauth-protected-resource returns the
    RFC 9728 metadata document pointing at the configured AS."""
    from app.factory import create_app

    app = create_app(mount_mcp=False)
    with TestClient(app) as client:
        r = client.get("/.well-known/oauth-protected-resource")
        assert r.status_code == 200
        body = r.json()
        assert body["resource"] == _oauth_enabled["audience"]
        assert body["authorization_servers"] == [_oauth_enabled["issuer"]]
        assert "mcp:read" in body["scopes_supported"]
        assert "header" in body["bearer_methods_supported"]


def test_oauth_token_verifier_accepts_valid_token(_oauth_enabled) -> None:
    """A signed JWT with correct aud + iss + scope passes verification."""
    from app.auth import make_token_verifier
    from app.config import settings

    verifier = make_token_verifier(settings)
    assert verifier is not None
    result = asyncio.run(verifier.verify_token(_oauth_enabled["token"]))
    assert result is not None, "valid token must pass verification"
    assert "mcp:read" in result.scopes


def test_oauth_token_verifier_rejects_wrong_audience(_oauth_enabled) -> None:
    """Token signed for a different audience must be rejected."""
    _other_pem, other_token = _make_jwt_keypair_and_token(
        audience="https://other.test", issuer=_oauth_enabled["issuer"]
    )
    from app.auth import make_token_verifier
    from app.config import settings

    verifier = make_token_verifier(settings)
    result = asyncio.run(verifier.verify_token(other_token))
    assert result is None, "token with wrong audience signed by an unrelated key must be rejected"


def test_oauth_token_verifier_rejects_missing_scopes(_oauth_enabled) -> None:
    """Token without the required scope must be rejected."""
    from app.auth import JWKSTokenVerifier

    # Build a verifier asking for a scope the fixture token does not carry.
    verifier = JWKSTokenVerifier(
        jwks_url="https://auth.test/.well-known/jwks.json",
        audience=_oauth_enabled["audience"],
        issuer=_oauth_enabled["issuer"],
        required_scopes=["mcp:write"],  # fixture token only has mcp:read
    )
    result = asyncio.run(verifier.verify_token(_oauth_enabled["token"]))
    assert result is None, "token missing required scope must be rejected"


def test_oauth_misconfiguration_raises(monkeypatch) -> None:
    """OAUTH_ENABLED=true but missing OAUTH_AUDIENCE must fail loudly."""
    from app.auth import make_auth_settings
    from app.config import settings

    monkeypatch.setattr(settings, "oauth_enabled", True)
    monkeypatch.setattr(settings, "oauth_issuer", "https://auth.test")
    monkeypatch.setattr(settings, "oauth_audience", None)

    with pytest.raises(ValueError, match="OAUTH_AUDIENCE"):
        make_auth_settings(settings)
