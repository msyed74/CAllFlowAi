from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING
from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.core.database import Base
from backend.app.models.base import generate_uuid

if TYPE_CHECKING:
    from backend.app.models.calls import Call
    from backend.app.models.leads import Lead


class LeadScore(Base):
    __tablename__ = "lead_scores"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    call_id: Mapped[str] = mapped_column(String(36), ForeignKey("calls.id", ondelete="CASCADE"), nullable=False, index=True)
    lead_id: Mapped[str] = mapped_column(String(36), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True)
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)

    composite_score: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    budget_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    authority_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    need_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    timeline_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    score_breakdown: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    reasoning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    call: Mapped["Call"] = relationship("Call", back_populates="lead_scores")
    lead: Mapped["Lead"] = relationship("Lead", back_populates="lead_scores")
