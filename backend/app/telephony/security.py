import base64
import hashlib
import hmac
from typing import Dict, Optional
from fastapi import Header, HTTPException, Request, status
from backend.app.core.config import settings


def compute_twilio_signature(url: str, params: Dict[str, str], auth_token: str) -> str:
    """
    Computes Twilio HMAC-SHA1 signature according to the official Twilio specification.
    URL + sorted parameter keys and values hashed against auth_token.
    """
    data = url
    for key in sorted(params.keys()):
        data += f"{key}{params[key]}"

    mac = hmac.new(
        auth_token.encode("utf-8"),
        data.encode("utf-8"),
        hashlib.sha1,
    )
    return base64.b64encode(mac.digest()).decode("utf-8")


async def verify_twilio_signature(
    request: Request,
    x_twilio_signature: Optional[str] = Header(None, alias="X-Twilio-Signature"),
) -> bool:
    """
    FastAPI dependency validating incoming Twilio webhooks.
    In development / test mode without header, passes through.
    """
    if (settings.DEBUG or settings.APP_ENV in ("development", "test")) and not x_twilio_signature:
        return True

    if not x_twilio_signature:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing X-Twilio-Signature header",
        )

    url = str(request.url)
    form_data = await request.form()
    params = {k: str(v) for k, v in form_data.items()}

    expected_signature = compute_twilio_signature(
        url=url,
        params=params,
        auth_token=settings.TWILIO_AUTH_TOKEN,
    )

    if not hmac.compare_digest(expected_signature, x_twilio_signature):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid Twilio signature",
        )

    return True
