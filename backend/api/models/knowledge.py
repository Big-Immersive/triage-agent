"""Persistent project intelligence: memories, knowledge items and files."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, now, pk, project_fk, ts


class Memory(Base):
    __tablename__ = "memories"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = project_fk()
    type: Mapped[str] = mapped_column(String(32), nullable=False)   # PROJECT_CONTEXT | DECISIONS | ...
    source: Mapped[str] = mapped_column(String(64), default="user")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    related_run_id: Mapped[Optional[str]] = mapped_column(String(64))
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = ts()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now, nullable=False)


class KnowledgeItem(Base):
    __tablename__ = "knowledge_items"
    id: Mapped[str] = pk()
    project_id: Mapped[str] = project_fk()
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)   # document|pdf|markdown|code|url|note|tracker|crashlog|releases|codeowners
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="indexing")   # ready|indexing|failed
    progress: Mapped[int] = mapped_column(Integer, default=0)
    indexed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    file_id: Mapped[Optional[str]] = mapped_column(String(64))
    source_url: Mapped[Optional[str]] = mapped_column(Text)
    error: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = ts()


class File(Base):
    __tablename__ = "files"
    __table_args__ = (UniqueConstraint("project_id", "path", name="uq_file_project_path"),)
    id: Mapped[str] = pk()
    project_id: Mapped[str] = project_fk()
    path: Mapped[str] = mapped_column(String(1024), nullable=False)   # "/docs/architecture.md"
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(8), default="file")   # file | dir
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    mime: Mapped[str] = mapped_column(String(120), default="application/octet-stream")
    storage_key: Mapped[Optional[str]] = mapped_column(String(255))   # relative to data/projects/{id}/files
    created_at: Mapped[datetime] = ts()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now, nullable=False)
