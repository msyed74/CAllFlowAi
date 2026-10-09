from datetime import datetime, timezone
from typing import List, Optional, TYPE_CHECKING
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.core.database import Base
from backend.app.models.base import TimestampMixin, generate_uuid

if TYPE_CHECKING:
    from backend.app.models.organizations import Organization
    from backend.app.models.campaigns import Campaign
    from backend.app.models.leads import Lead
    from backend.app.models.customers import Customer
    from backend.app.models.appointments import Appointment
    from backend.app.models.agent_runtime import AgentSession
    from backend.app.models.lead_scores import LeadScore


class Call(Base, TimestampMixin):
    __tablename__ = "calls"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    campaign_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True, index=True)
    lead_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("leads.id", ondelete="SET NULL"), nullable=True, index=True)
    customer_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True, index=True)

    twilio_call_sid: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String(20), nullable=False)  # 'inbound' or 'outbound'
    from_number: Mapped[str] = mapped_column(String(50), nullable=False)
    to_number: Mapped[str] = mapped_column(String(50), nullable=False)

    status: Mapped[str] = mapped_column(String(50), default="initiated", nullable=False, index=True)
    termination_reason: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    duration_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    billed_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    audio_recording_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    initiated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    answered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    organization: Mapped["Organization"] = relationship("Organization", back_populates="calls")
    campaign: Mapped[Optional["Campaign"]] = relationship("Campaign", back_populates="calls")
    lead: Mapped[Optional["Lead"]] = relationship("Lead", back_populates="calls")
    customer: Mapped[Optional["Customer"]] = relationship("Customer", back_populates="calls")

    events: Mapped[List["CallEvent"]] = relationship("CallEvent", back_populates="call", cascade="all, delete-orphan")
    transcripts: Mapped[List["CallTranscript"]] = relationship("CallTranscript", back_populates="call", cascade="all, delete-orphan")
    summary: Mapped[Optional["CallSummary"]] = relationship("CallSummary", back_populates="call", uselist=False, cascade="all, delete-orphan")
    agent_session: Mapped[Optional["AgentSession"]] = relationship("AgentSession", back_populates="call", uselist=False, cascade="all, delete-orphan")
    appointments: Mapped[List["Appointment"]] = relationship("Appointment", back_populates="call")
    lead_scores: Mapped[List["LeadScore"]] = relationship("LeadScore", back_populates="call")


class CallEvent(Base):
    __tablename__ = "call_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    call_id: Mapped[str] = mapped_column(String(36), ForeignKey("calls.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    timestamp_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    call: Mapped["Call"] = relationship("Call", back_populates="events")


class CallTranscript(Base):
    __tablename__ = "call_transcripts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    call_id: Mapped[str] = mapped_column(String(36), ForeignKey("calls.id", ondelete="CASCADE"), nullable=False, index=True)
    speaker_role: Mapped[str] = mapped_column(String(20), nullable=False)  # 'user', 'assistant', 'system', 'supervisor'
    content: Mapped[str] = mapped_column(Text, nullable=False)
    start_time_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    end_time_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    speech_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_interrupted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    call: Mapped["Call"] = relationship("Call", back_populates="transcripts")


class CallSummary(Base):
    __tablename__ = "call_summaries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    call_id: Mapped[str] = mapped_column(String(36), ForeignKey("calls.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)

    executive_summary: Mapped[str] = mapped_column(Text, nullable=False)
    sentiment_overall: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    primary_intent: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    qualification_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    pain_points: Mapped[dict] = mapped_column(JSON, default=list, nullable=False)
    objections_raised: Mapped[dict] = mapped_column(JSON, default=list, nullable=False)
    action_items: Mapped[dict] = mapped_column(JSON, default=list, nullable=False)
    recommended_follow_up: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    raw_llm_response: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    call: Mapped["Call"] = relationship("Call", back_populates="summary")
