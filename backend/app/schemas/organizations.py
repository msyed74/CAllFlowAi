from typing import Optional
from pydantic import BaseModel, Field


class OrganizationBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    slug: Optional[str] = None
    default_voice_id: str = "alloy"
    default_language: str = "en-US"


class OrganizationCreate(OrganizationBase):
    pass


class OrganizationUpdate(BaseModel):
    name: Optional[str] = None
    default_voice_id: Optional[str] = None
    default_language: Optional[str] = None
    twilio_phone_number: Optional[str] = None
    max_concurrent_calls: Optional[int] = None


class OrganizationResponse(OrganizationBase):
    id: str
    status: str
    twilio_phone_number: Optional[str] = None
    max_concurrent_calls: int
    monthly_call_minutes_limit: int
    current_month_minutes_used: int

    class Config:
        from_attributes = True
