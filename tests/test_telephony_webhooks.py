import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.config import settings
from backend.app.models.calls import Call
from backend.app.models.organizations import Organization
from backend.app.telephony.security import compute_twilio_signature


@pytest.mark.asyncio
async def test_twilio_signature_calculation():
    test_url = "http://testserver/api/v1/telephony/inbound"
    test_params = {
        "CallSid": "CA1234567890abcdef",
        "From": "+14155550199",
        "To": "+18005550100",
    }
    auth_token = "test_auth_token_12345"

    sig = compute_twilio_signature(test_url, test_params, auth_token)
    assert isinstance(sig, str)
    assert len(sig) > 0

    # Ensure deterministic computation
    sig2 = compute_twilio_signature(test_url, test_params, auth_token)
    assert sig == sig2


@pytest.mark.asyncio
async def test_invalid_twilio_signature_rejected(client: AsyncClient):
    # When X-Twilio-Signature header is provided, it MUST match or return 403
    bad_headers = {"X-Twilio-Signature": "invalid_forged_signature_xyz"}
    inbound_payload = {
        "CallSid": "CA_test_forged",
        "From": "+14155559988",
        "To": "+18005550100",
    }
    response = await client.post(
        "/api/v1/telephony/inbound",
        data=inbound_payload,
        headers=bad_headers,
    )
    assert response.status_code == 403
    assert "Invalid Twilio signature" in response.json()["error"]["message"]


@pytest.mark.asyncio
async def test_inbound_call_webhook(client: AsyncClient, db_session: AsyncSession):
    # 1. Seed an active organization
    org = Organization(
        name="Telephony Test Corp",
        slug="telephony-test-corp",
        status="active",
        twilio_phone_number="+18005550100",
    )
    db_session.add(org)
    await db_session.commit()

    # 2. Simulate Twilio inbound call POST
    inbound_payload = {
        "CallSid": "CA_test_inbound_001",
        "From": "+14155559988",
        "To": "+18005550100",
    }
    response = await client.post("/api/v1/telephony/inbound", data=inbound_payload)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/xml")

    # 3. Assert TwiML contains <Stream> tag with correct parameters
    content = response.text
    assert "<Connect>" in content
    assert "<Stream" in content
    assert f'value="{org.id}"' in content
    assert 'value="CA_test_inbound_001"' in content

    # 4. Assert Call record was created in database
    stmt = select(Call).where(Call.twilio_call_sid == "CA_test_inbound_001")
    call = (await db_session.execute(stmt)).scalar_one_or_none()
    assert call is not None
    assert call.direction == "inbound"
    assert call.status == "ringing"
    assert call.from_number == "+14155559988"


@pytest.mark.asyncio
async def test_status_callback_webhook(client: AsyncClient, db_session: AsyncSession):
    # 1. Seed an organization and existing Call record
    org = Organization(
        name="Callback Test Org",
        slug="callback-test-org",
        status="active",
    )
    db_session.add(org)
    await db_session.flush()

    call = Call(
        organization_id=org.id,
        twilio_call_sid="CA_test_status_002",
        direction="outbound",
        from_number="+18005550100",
        to_number="+14155559988",
        status="ringing",
    )
    db_session.add(call)
    await db_session.commit()

    # 2. Send status-callback: in-progress
    await client.post(
        "/api/v1/telephony/status-callback",
        data={"CallSid": "CA_test_status_002", "CallStatus": "in-progress"},
    )
    await db_session.refresh(call)
    assert call.status == "in_progress"
    assert call.answered_at is not None

    # 3. Send status-callback: completed with duration
    await client.post(
        "/api/v1/telephony/status-callback",
        data={
            "CallSid": "CA_test_status_002",
            "CallStatus": "completed",
            "CallDuration": "45",
        },
    )
    await db_session.refresh(call)
    assert call.status == "completed"
    assert call.duration_seconds == 45
    assert call.ended_at is not None


@pytest.mark.asyncio
async def test_transfer_fallback_webhook(client: AsyncClient):
    response = await client.post("/api/v1/telephony/transfer-fallback")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/xml")
    assert "<Say" in response.text
    assert "<Hangup/>" in response.text
