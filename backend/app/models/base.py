import uuid
from datetime import datetime, timezone
from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column
from backend.app.core.database import Base


def generate_uuid() -> str:
    """Generates standard UUID4 string identifier."""
    return str(uuid.uuid4())


class TimestampMixin:
    """Provides created_at and updated_at UTC timestamps."""
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class TenantMixin:
    """Enforces multi-tenant scoping via organization_id."""
    organization_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
    )
