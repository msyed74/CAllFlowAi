from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, EmailStr, Field


class LeadBase(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone_number: str = Field(..., min_length=7, max_length=50)
    company_name: Optional[str] = None
    job_title: Optional[str] = None
    lead_source: str = "inbound_web"
    timezone: str = "UTC"
    custom_fields: Dict[str, Any] = Field(default_factory=dict)


class LeadCreate(LeadBase):
    pass


class LeadUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[EmailStr] = None
    company_name: Optional[str] = None
    job_title: Optional[str] = None
    status: Optional[str] = None
    timezone: Optional[str] = None
    custom_fields: Optional[Dict[str, Any]] = None


class LeadCallNowRequest(BaseModel):
    campaign_id: Optional[str] = None
    priority: str = "normal"
    override_prompt_context: Optional[Dict[str, Any]] = None


class LeadResponse(LeadBase):
    id: str
    organization_id: str
    assigned_user_id: Optional[str] = None
    status: str
    call_attempts: int
    last_called_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
