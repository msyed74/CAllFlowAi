from typing import List, Optional, TYPE_CHECKING
from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.core.database import Base
from backend.app.models.base import TimestampMixin, generate_uuid

if TYPE_CHECKING:
    from backend.app.models.users import User
    from backend.app.models.roles import Role
    from backend.app.models.leads import Lead
    from backend.app.models.campaigns import Campaign
    from backend.app.models.calls import Call


class Organization(Base, TimestampMixin):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(50), default="active", nullable=False, index=True)

    # Telephony credentials & numbers
    twilio_account_sid: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    twilio_auth_token_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    twilio_phone_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # LLM & Voice preferences
    openai_api_key_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    default_voice_id: Mapped[str] = mapped_column(String(50), default="alloy", nullable=False)
    default_language: Mapped[str] = mapped_column(String(10), default="en-US", nullable=False)

    # Capacity & quotas
    max_concurrent_calls: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    monthly_call_minutes_limit: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)
    current_month_minutes_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Relationships
    users: Mapped[List["User"]] = relationship("User", back_populates="organization", cascade="all, delete-orphan")
    roles: Mapped[List["Role"]] = relationship("Role", back_populates="organization", cascade="all, delete-orphan")
    leads: Mapped[List["Lead"]] = relationship("Lead", back_populates="organization", cascade="all, delete-orphan")
    campaigns: Mapped[List["Campaign"]] = relationship("Campaign", back_populates="organization", cascade="all, delete-orphan")
    calls: Mapped[List["Call"]] = relationship("Call", back_populates="organization", cascade="all, delete-orphan")
