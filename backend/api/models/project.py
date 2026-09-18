"""Projects, their agents, integrations and the per-project ticket counter."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, now, pk, project_fk, ts


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("owner_id", "slug", name="uq_project_owner_slug"),)
    id: Mapped[str] = pk()
    owner_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(140), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    icon: Mapped[str] = mapped_column(String(16), default="▣")
    instructions: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="draft")   # draft | active | archived
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)  # approval.config, memory.config ...
    created_at: Mapped[datetime] = ts()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now, nullable=False)
    last_activity_at: Mapped[datetime] = ts()


class Agent(Base):
    __tablename__ = "agents"
    __table_args__ = (UniqueConstraint("project_id", "name", name="uq_agent_project_name"),)
    id: Mapped[str] = pk()
    project_id: Mapped[str] = project_fk()
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    role: Mapped[str] = mapped_column(String(120), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    instructions: Mapped[str] = mapped_column(Text, default="")
    model: Mapped[Optional[str]] = mapped_column(String(120))
    tools: Mapped[list[str]] = mapped_column(JSONB, default=list)
    permissions: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    can_handoff_to: Mapped[list[str]] = mapped_column(JSONB, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="idle")
    current_process: Mapped[Optional[str]] = mapped_column(String(255))
    last_active_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = ts()


class Integration(Base):
    __tablename__ = "integrations"
    __table_args__ = (UniqueConstraint("project_id", "provider", name="uq_integration_project_provider"),)
    id: Mapped[str] = pk()
    project_id: Mapped[str] = project_fk()
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="not_connected")   # connected|not_connected|error
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    connected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    # inbound side: push providers verify with inbound_token / secrets; pull providers are polled by the sync scheduler
    inbound_token: Mapped[Optional[str]] = mapped_column(String(64))
    sync_cursor: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    next_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    sync_locked_by: Mapped[Optional[str]] = mapped_column(String(64))
    sync_locked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_sync_result: Mapped[Optional[str]] = mapped_column(Text)
    inbound_count: Mapped[int] = mapped_column(Integer, default=0)


class TicketCounter(Base):
    """Atomic per-project ticket numbering, safe across API replicas."""
    __tablename__ = "ticket_counters"
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True)
    prefix: Mapped[str] = mapped_column(String(16), default="OR")
    next_num: Mapped[int] = mapped_column(Integer, default=101)
