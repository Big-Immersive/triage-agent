"""Activity feed and LLM usage accounting."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, now, pk, project_fk, ts


class Activity(Base):
    __tablename__ = "activities"
    __table_args__ = (Index("ix_activities_project_ts", "project_id", "ts"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = project_fk()
    ts: Mapped[datetime] = ts()
    category: Mapped[str] = mapped_column(String(16), nullable=False)   # PROJECT|AGENT|RUN|MEMORY|FILE|KNOWLEDGE|APPROVAL|SYSTEM
    message: Mapped[str] = mapped_column(Text, nullable=False)
    ref_type: Mapped[Optional[str]] = mapped_column(String(24))
    ref_id: Mapped[Optional[str]] = mapped_column(String(64))


class LlmUsage(Base):
    __tablename__ = "llm_usage"
    __table_args__ = (Index("ix_llm_usage_user_ts", "user_id", "ts"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[str] = project_fk()
    run_id: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey("runs.id", ondelete="SET NULL"))
    agent_name: Mapped[str] = mapped_column(String(64), default="")
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    llm_calls: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    estimated: Mapped[bool] = mapped_column(Boolean, default=True)
    ts: Mapped[datetime] = ts()
