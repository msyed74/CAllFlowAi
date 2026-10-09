import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_readiness_check(client: AsyncClient):
    response = await client.get("/ready")
    assert response.status_code == 200
    assert response.json()["ready"] is True


@pytest.mark.asyncio
async def test_register_and_login_flow(client: AsyncClient):
    # 1. Register a new organization and admin user
    reg_payload = {
        "organization_name": "Apex Voice Tech",
        "first_name": "Sarah",
        "last_name": "Connor",
        "email": "sarah@apexvoicetech.com",
        "password": "SuperSecretPassword123!",
        "phone_number": "+14155552671",
    }
    reg_res = await client.post("/api/v1/auth/register", json=reg_payload)
    assert reg_res.status_code == 201
    tokens = reg_res.json()
    assert "access_token" in tokens
    assert "refresh_token" in tokens
    assert tokens["token_type"] == "Bearer"

    access_token = tokens["access_token"]
    refresh_token = tokens["refresh_token"]

    # 2. Access /auth/me with bearer token
    headers = {"Authorization": f"Bearer {access_token}"}
    me_res = await client.get("/api/v1/auth/me", headers=headers)
    assert me_res.status_code == 200
    profile = me_res.json()
    assert profile["email"] == "sarah@apexvoicetech.com"
    assert profile["first_name"] == "Sarah"
    assert profile["role"] == "OrgAdmin"
    assert "*" in profile["permissions"]

    # 3. Test Login with valid credentials
    login_payload = {
        "email": "sarah@apexvoicetech.com",
        "password": "SuperSecretPassword123!",
    }
    login_res = await client.post("/api/v1/auth/login", json=login_payload)
    assert login_res.status_code == 200
    new_tokens = login_res.json()
    assert "access_token" in new_tokens

    # 4. Test Login with incorrect password
    bad_login = {
        "email": "sarah@apexvoicetech.com",
        "password": "WrongPassword!",
    }
    bad_res = await client.post("/api/v1/auth/login", json=bad_login)
    assert bad_res.status_code == 401

    # 5. Test Refresh Token
    refresh_payload = {"refresh_token": refresh_token}
    refresh_res = await client.post("/api/v1/auth/refresh", json=refresh_payload)
    assert refresh_res.status_code == 200
    refreshed_tokens = refresh_res.json()
    assert "access_token" in refreshed_tokens


@pytest.mark.asyncio
async def test_unauthorized_access(client: AsyncClient):
    # Attempting to access protected route without token
    res = await client.get("/api/v1/auth/me")
    assert res.status_code == 401
