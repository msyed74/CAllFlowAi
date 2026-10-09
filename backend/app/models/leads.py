from datetime import datetime
from typing import List, Optional, TYPE_CHECKING
from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.core.database import Base
from backend.app.models.base import TimestampMixin, generate_uuid

if TYPE_CHECKING:
    from backend.app.models.organizations import Organization
    from backend.app.models.users import User
    from backend.app.models.customers import Customer
    from backend.app.models.calls import Call
    from backend.app.models.appointments import Appointment
    from backend.app.models.lead_scores import LeadScore


class Lead(Base, TimestampMixin):
    __tablename__ = "leads"
    __table_args__ = (
        UniqueConstraint("organization_id", "phone_number", name="uq_leads_org_phone"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    assigned_user_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    first_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone_number: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    company_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    job_title: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)

    status: Mapped[str] = mapped_column(String(50), default="new", nullable=False, index=True)
    lead_source: Mapped[str] = mapped_column(String(100), default="inbound_web", nullable=False)
    timezone: Mapped[str] = mapped_column(String(50), default="UTC", nullable=False)

    custom_fields: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    last_called_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    call_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Relationships
    organization: Mapped["Organization"] = relationship("Organization", back_populates="leads")
    assigned_user: Mapped[Optional["User"]] = relationship("User", back_populates="assigned_leads")
    customer: Mapped[Optional["Customer"]] = relationship("Customer", back_populates="lead", uselist=False)
    calls: Mapped[List["Call"]] = relationship("Call", back_populates="lead")
    appointments: Mapped[List["Appointment"]] = relationship("Appointment", back_populates="lead")
    lead_scores: Mapped[List["LeadScore"]] = relationship("LeadScore", back_populates="lead")
