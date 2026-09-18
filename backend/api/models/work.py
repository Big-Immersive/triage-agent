"""Units of work: tasks, runs, run events, tool calls and human approvals."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, now, pk, project_fk, ts


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[str] = pk()
    project_id: Mapped[str] = project_fk()
    external_id: Mapped[str] = mapped_column(String(64), nullable=False)   # FB-001 style, unique per project
    source: Mapped[str] = mapped_column(String(64), default="manual")
    author: Mapped[str] = mapped_column(String(120), default="")
    title: Mapped[str] = mapped_column(String(255), default="")
    text: Mapped[str] = mapped_column(Text, nullable=False)
    rating: Mapped[Optional[int]] = mapped_column(Integer)
    received_at: Mapped[Optional[str]] = mapped_column(String(40))
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="queued")   # queued | running | done | failed
    result: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)
    last_run_id: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = ts()
    __table_args__ = (UniqueConstraint("project_id", "external_id", name="uq_task_project_ext"),)


class Run(Base):
    __tablename__ = "runs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = project_fk()
    task_id: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey("tasks.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(24), default="queued")  # queued|running|waiting_approval|complete|error|cancelled
    starting_agent: Mapped[Optional[str]] = mapped_column(String(64))
    current_agent: Mapped[Optional[str]] = mapped_column(String(64))
    started_at: Mapped[datetime] = ts()
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    tool_call_count: Mapped[int] = mapped_column(Integer, default=0)
    handoff_count: Mapped[int] = mapped_column(Integer, default=0)
    approval_state: Mapped[str] = mapped_column(String(20), default="none")  # none|pending|approved|modified|rejected
    final_text: Mapped[Optional[str]] = mapped_column(Text)
    result: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)
    error: Mapped[Optional[str]] = mapped_column(Text)
    auto_approve: Mapped[bool] = mapped_column(Boolean, default=False)
    worker_id: Mapped[Optional[str]] = mapped_column(String(64))
    heartbeat_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    preapproved: Mapped[Optional[str]] = mapped_column(String(16))   # a human decision carried over from an interrupted attempt


class RunEvent(Base):
    __tablename__ = "run_events"
    __table_args__ = (Index("ix_run_events_run_seq", "run_id", "seq"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = project_fk()
    run_id: Mapped[str] = mapped_column(String(64), ForeignKey("runs.id", ondelete="CASCADE"), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    ts: Mapped[datetime] = ts()
    kind: Mapped[str] = mapped_column(String(24), nullable=False)   # SYSTEM|AGENT|MEMORY|TOOL|TOOL_RESULT|HANDOFF|APPROVAL|ERROR|FINAL
    actor: Mapped[str] = mapped_column(String(64), default="system")
    message: Mapped[str] = mapped_column(Text, default="")
    input: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)
    output: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)


class ToolCallRow(Base):
    __tablename__ = "tool_calls"
    id: Mapped[str] = pk()
    project_id: Mapped[str] = project_fk()
    run_id: Mapped[str] = mapped_column(String(64), ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True)
    agent_name: Mapped[str] = mapped_column(String(64), default="")
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False)
    args: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    result: Mapped[Optional[str]] = mapped_column(Text)
    is_error: Mapped[bool] = mapped_column(Boolean, default=False)
    ts: Mapped[datetime] = ts()
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)


class Approval(Base):
    __tablename__ = "approvals"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = project_fk()
    run_id: Mapped[str] = mapped_column(String(64), ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True)
    agent_name: Mapped[str] = mapped_column(String(64), default="")
    action: Mapped[str] = mapped_column(Text, default="")
    reason: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[Optional[float]] = mapped_column(Float)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)   # severity, component, owner, evidence, prompt
    status: Mapped[str] = mapped_column(String(20), default="pending")   # pending|approved|modified|rejected|expired
    response: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)
    requested_at: Mapped[datetime] = ts()
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
