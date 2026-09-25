"""Auth tests (spec §7.5): login, token enforcement, role gate.

RED/GREEN contract: a valid login returns a working token; unknown emails,
wrong passwords, the legacy placeholder hash and missing/expired/tampered
tokens all answer 401 with a generic message; the `manager` role on an
operator route answers 403.
"""

import pytest

from app.security.passwords import verify_password
from app.security.tokens import issue_token, verify_token
from tests.conftest import (
    DEMO_PASSWORD,
    MANAGER_ID,
    OPERATOR_ID,
    TEST_SETTINGS,
    auth_headers,
)


def test_verify_password_roundtrip() -> None:
    from app.security.passwords import hash_password

    hashed = hash_password("s3cret")
    assert verify_password("s3cret", hashed) is True
    assert verify_password("wrong", hashed) is False


def test_placeholder_hash_never_authenticates() -> None:
    assert verify_password(DEMO_PASSWORD, "demo-not-a-real-hash") is False
    assert verify_password("", "demo-not-a-real-hash") is False
    assert verify_password("demo-not-a-real-hash", "demo-not-a-real-hash") is False


def test_garbage_hash_fails_closed() -> None:
    assert verify_password("anything", "not-a-hash-at-all") is False


def test_token_roundtrip() -> None:
    token, expires_in = issue_token(MANAGER_ID, "manager", TEST_SETTINGS)
    assert expires_in == TEST_SETTINGS.jwt_expires_minutes * 60
    claims = verify_token(token, TEST_SETTINGS)
    assert claims is not None
    assert claims.manager_id == MANAGER_ID
    assert claims.role == "manager"


def test_tampered_token_rejected() -> None:
    token, _ = issue_token(MANAGER_ID, "manager", TEST_SETTINGS)
    assert verify_token(token + "x", TEST_SETTINGS) is None
    assert verify_token(token[:-3] + "abc", TEST_SETTINGS) is None


def test_expired_token_rejected() -> None:
    from app.core.config import Settings

    expired_settings = Settings(
        jwt_secret="test-secret", jwt_expires_minutes=-1, _env_file=None
    )
    token, _ = issue_token(MANAGER_ID, "manager", expired_settings)
    assert verify_token(token, TEST_SETTINGS) is None


def test_wrong_secret_rejected() -> None:
    from app.core.config import Settings

    token, _ = issue_token(MANAGER_ID, "manager", TEST_SETTINGS)
    other = Settings(jwt_secret="another-secret-also-long-enough-32-bytes", _env_file=None)
    assert verify_token(token, other) is None


@pytest.mark.parametrize("payload", [{}, {"sub": "mgr_1"}, {"sub": 1, "role": 2}])
def test_malformed_claims_rejected(payload: dict) -> None:
    import jwt

    forged = jwt.encode(payload, TEST_SETTINGS.jwt_secret, algorithm="HS256")
    assert verify_token(forged, TEST_SETTINGS) is None


async def test_login_success(client) -> None:
    response = await client.post(
        "/api/auth/login",
        json={"email": "manager@test.demo", "password": DEMO_PASSWORD},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["tokenType"] == "Bearer"
    assert body["accessToken"]
    assert body["expiresIn"] == TEST_SETTINGS.jwt_expires_minutes * 60
    assert body["manager"]["id"] == MANAGER_ID
    assert body["manager"]["role"] == "manager"


async def test_login_token_works_on_protected_route(client) -> None:
    login = await client.post(
        "/api/auth/login",
        json={"email": "manager@test.demo", "password": DEMO_PASSWORD},
    )
    token = login.json()["accessToken"]
    response = await client.get(
        "/api/locations", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200


async def test_login_unknown_email_is_generic_401(client) -> None:
    response = await client.post(
        "/api/auth/login",
        json={"email": "nobody@test.demo", "password": DEMO_PASSWORD},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


async def test_login_wrong_password_is_generic_401(client) -> None:
    response = await client.post(
        "/api/auth/login",
        json={"email": "manager@test.demo", "password": "not-the-password"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


async def test_placeholder_hash_manager_cannot_login(client) -> None:
    """The legacy placeholder hash must never authenticate anything."""
    response = await client.post(
        "/api/auth/login",
        json={"email": "legacy@test.demo", "password": "demo-not-a-real-hash"},
    )
    assert response.status_code == 401
    response = await client.post(
        "/api/auth/login",
        json={"email": "legacy@test.demo", "password": DEMO_PASSWORD},
    )
    assert response.status_code == 401


async def test_missing_token_answers_401(client) -> None:
    response = await client.get("/api/locations")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


async def test_malformed_header_answers_401(client) -> None:
    response = await client.get("/api/locations", headers={"Authorization": "Basic abc"})
    assert response.status_code == 401


async def test_expired_token_answers_401(client) -> None:
    from app.core.config import Settings

    expired = Settings(jwt_secret="test-secret", jwt_expires_minutes=-1, _env_file=None)
    token, _ = issue_token(MANAGER_ID, "manager", expired)
    response = await client.get(
        "/api/locations", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401


async def test_tampered_token_answers_401(client) -> None:
    token, _ = issue_token(MANAGER_ID, "manager", TEST_SETTINGS)
    response = await client.get(
        "/api/locations", headers={"Authorization": f"Bearer {token}tampered"}
    )
    assert response.status_code == 401


async def test_manager_on_operator_route_answers_403(client) -> None:
    response = await client.get(
        "/api/interpretations", headers=auth_headers(MANAGER_ID, "manager")
    )
    assert response.status_code == 403


async def test_operator_on_operator_route_answers_200(client) -> None:
    response = await client.get(
        "/api/interpretations", headers=auth_headers(OPERATOR_ID, "operator")
    )
    assert response.status_code == 200
