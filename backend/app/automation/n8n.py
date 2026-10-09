"""
n8n Workflow Automation Bridge.

Dispatches enriched post-call intelligence events to n8n webhooks for CRM sync
(HubSpot, Salesforce, Pipedrive, etc.), lead notifications, and workflow automation.
Tracks every webhook dispatch in the `automation_jobs` table with retries and response logs.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import settings
from backend.app.models.automation import AutomationJob

logger = logging.getLogger("automation.n8n")


async def trigger_n8n_workflow(
    organization_id: str,
    workflow_name: str,
    payload: Dict[str, Any],
    db_session: AsyncSession,
    call_id: Optional[str] = None,
    http_client: Optional[httpx.AsyncClient] = None,
    max_retries: int = 3,
) -> AutomationJob:
    """
    Submits an automated job to n8n and tracks execution in automation_jobs.
    """
    job_id = str(uuid.uuid4())
    endpoint = f"{settings.N8N_WEBHOOK_BASE_URL.rstrip('/')}/{workflow_name}"

    job = AutomationJob(
        id=job_id,
        organization_id=organization_id,
        call_id=call_id,
        workflow_name=workflow_name,
        target_endpoint=endpoint,
        payload=payload,
        status="pending",
        retry_count=0,
        max_retries=max_retries,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(job)
    await db_session.flush()

    headers = {
        "Content-Type": "application/json",
        "X-N8N-API-KEY": settings.N8N_API_KEY,
    }

    try:
        if http_client:
            resp = await http_client.post(endpoint, json=payload, headers=headers)
        else:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(endpoint, json=payload, headers=headers)

        job.response_code = resp.status_code
        job.response_body = resp.text[:2000]

        if 200 <= resp.status_code < 300:
            job.status = "success"
            logger.info("n8n workflow '%s' triggered successfully for call %s", workflow_name, call_id)
        else:
            job.status = "failed"
            job.retry_count += 1
            logger.warning(
                "n8n workflow '%s' returned HTTP %d for call %s: %s",
                workflow_name, resp.status_code, call_id, resp.text[:200],
            )
    except Exception as e:
        logger.warning(
            "Could not reach n8n webhook '%s' for call %s: %s. Setting status to failed.",
            endpoint, call_id, e,
        )
        job.status = "failed"
        job.response_code = 0
        job.response_body = f"Network or connection error: {str(e)}"
        job.retry_count += 1

    await db_session.commit()
    await db_session.refresh(job)
    return job
