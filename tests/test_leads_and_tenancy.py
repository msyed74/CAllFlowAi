import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_multi_tenant_isolation_and_leads(client: AsyncClient):
    # 1. Register Tenant A
    org_a_res = await client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": "Tenant Alpha Corp",
            "first_name": "Alice",
            "last_name": "Smith",
            "email": "alice@alpha.com",
            "password": "Password123!",
        },
    )
    assert org_a_res.status_code == 201
    token_a = org_a_res.json()["access_token"]
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # 2. Register Tenant B
    org_b_res = await client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": "Tenant Beta LLC",
            "first_name": "Bob",
            "last_name": "Jones",
            "email": "bob@beta.com",
            "password": "Password123!",
        },
    )
    assert org_b_res.status_code == 201
    token_b = org_b_res.json()["access_token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # 3. Tenant A creates Lead A
    lead_payload = {
        "first_name": "John",
        "last_name": "Doe",
        "email": "john.doe@prospect.com",
        "phone_number": "+14155550199",
        "company_name": "Prospect Enterprise",
        "timezone": "America/New_York",
        "custom_fields": {"budget": 50000},
    }
    create_lead_res = await client.post("/api/v1/leads", json=lead_payload, headers=headers_a)
    assert create_lead_res.status_code == 201
    lead_a = create_lead_res.json()
    lead_a_id = lead_a["id"]
    assert lead_a["phone_number"] == "+14155550199"

    # 4. Tenant B lists leads -> Must be empty!
    list_b_res = await client.get("/api/v1/leads", headers=headers_b)
    assert list_b_res.status_code == 200
    leads_for_b = list_b_res.json()
    assert len(leads_for_b) == 0

    # 5. Tenant B attempts to access Lead A by ID -> Must return 404
    cross_access_res = await client.get(f"/api/v1/leads/{lead_a_id}", headers=headers_b)
    assert cross_access_res.status_code == 404

    # 6. Tenant A accesses Lead A -> 200 OK
    get_a_res = await client.get(f"/api/v1/leads/{lead_a_id}", headers=headers_a)
    assert get_a_res.status_code == 200
    assert get_a_res.json()["id"] == lead_a_id

    # 7. Tenant A opts out Lead A -> status = 'dnc'
    opt_out_res = await client.post(f"/api/v1/leads/{lead_a_id}/opt-out", headers=headers_a)
    assert opt_out_res.status_code == 200
    assert opt_out_res.json()["status"] == "dnc"

    # 8. Check Organization Settings retrieval
    org_settings_res = await client.get("/api/v1/organizations/current", headers=headers_a)
    assert org_settings_res.status_code == 200
    org_settings = org_settings_res.json()
    assert org_settings["name"] == "Tenant Alpha Corp"
    assert org_settings["default_voice_id"] == "alloy"
