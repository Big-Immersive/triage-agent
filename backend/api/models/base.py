"""SQLAlchemy base + shared column helpers. Every project-scoped table carries
project_id with ON DELETE CASCADE (see models/__init__ for the full map)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base
from ..core.ids import uid


def now() -> datetime:
    return datetime.now(timezone.utc)


def pk() -> Mapped[str]:
    return mapped_column(String(64), primary_key=True, default=uid)


def ts() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), default=now, nullable=False)


def project_fk() -> Mapped[str]:
    return mapped_column(String(64), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)


__all__ = ["Base", "now", "pk", "ts", "project_fk"]
