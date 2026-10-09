from datetime import datetime
from typing import List, Optional, TYPE_CHECKING
from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.core.database import Base
from backend.app.models.base import TimestampMixin, generate_uuid

if TYPE_CHECKING:
    from backend.app.models.organizations import Organization
    from backend.app.models.calls import Call


class Campaign(Base, TimestampMixin):
    __tablename__ = "campaigns"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="draft", nullable=False, index=True)

    voice_agent_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    caller_phone_number: Mapped[str] = mapped_column(String(50), nullable=False)

    daily_start_time: Mapped[str] = mapped_column(String(10), default="09:00:00", nullable=False)
    daily_end_time: Mapped[str] = mapped_column(String(10), default="17:00:00", nullable=False)
    allowed_days: Mapped[dict] = mapped_column(JSON, default=lambda: [1, 2, 3, 4, 5], nullable=False)

    max_retries_per_lead: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    retry_delay_hours: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    concurrent_calls_limit: Mapped[int] = mapped_column(Integer, default=2, nullable=False)

    total_leads_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed_calls_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    successful_bookings_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    organization: Mapped["Organization"] = relationship("Organization", back_populates="campaigns")
    calls: Mapped[List["Call"]] = relationship("Call", back_populates="campaign")
