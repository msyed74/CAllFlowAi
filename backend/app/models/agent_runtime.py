from datetime import datetime, timezone
from typing import List, Optional, TYPE_CHECKING
from sqlalchemy import (
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
from backend.app.models.base import generate_uuid

if TYPE_CHECKING:
    from backend.app.models.calls import Call


class AgentSession(Base):
    __tablename__ = "agent_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    call_id: Mapped[str] = mapped_column(String(36), ForeignKey("calls.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    openai_session_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    system_prompt_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    voice_persona: Mapped[str] = mapped_column(String(50), default="alloy", nullable=False)
    active_tools: Mapped[dict] = mapped_column(JSON, default=list, nullable=False)
    temperature: Mapped[float] = mapped_column(Float, default=0.7, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    call: Mapped["Call"] = relationship("Call", back_populates="agent_session")
    tool_calls: Mapped[List["AgentToolCall"]] = relationship("AgentToolCall", back_populates="agent_session", cascade="all, delete-orphan")


class AgentToolCall(Base):
    __tablename__ = "agent_tool_calls"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    agent_session_id: Mapped[str] = mapped_column(String(36), ForeignKey("agent_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    call_id: Mapped[str] = mapped_column(String(36), ForeignKey("calls.id", ondelete="CASCADE"), nullable=False, index=True)

    tool_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    tool_call_id: Mapped[str] = mapped_column(String(100), nullable=False)
    arguments: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    response: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    execution_time_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    is_successful: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    agent_session: Mapped["AgentSession"] = relationship("AgentSession", back_populates="tool_calls")
