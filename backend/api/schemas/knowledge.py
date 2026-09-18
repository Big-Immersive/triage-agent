"""API shapes: knowledge."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, EmailStr, Field

from .base import ORM


class MemoryIn(BaseModel):
    type: str = Field(pattern="^(PROJECT_CONTEXT|DECISIONS|REQUIREMENTS|ARCHITECTURE|KNOWN_ISSUES|COMPLETED_WORK|CURRENT_WORK|AGENT_NOTES|CUSTOM_MEMORY)$")
    content: str = Field(min_length=1)
    source: str = "user"
    related_run_id: Optional[str] = None
    pinned: bool = False


class MemoryPatch(BaseModel):
    type: Optional[str] = None
    content: Optional[str] = None
    pinned: Optional[bool] = None


class MemoryOut(ORM):
    id: str
    project_id: str
    type: str
    source: str
    content: str
    related_run_id: Optional[str]
    pinned: bool
    created_at: datetime
    updated_at: datetime


# ---- knowledge / files
class KnowledgeOut(ORM):
    id: str
    project_id: str
    name: str
    kind: str
    size_bytes: int
    status: str
    progress: int
    indexed_at: Optional[datetime]
    file_id: Optional[str]
    source_url: Optional[str]
    error: Optional[str]
    created_at: datetime


class KnowledgeUrlIn(BaseModel):
    url: str
    name: Optional[str] = None


class KnowledgeTextIn(BaseModel):
    name: str
    text: str
    kind: str = "note"


class FileOut(ORM):
    id: str
    project_id: str
    path: str
    name: str
    kind: str
    size_bytes: int
    mime: str
    created_at: datetime
    updated_at: datetime


class FileMoveIn(BaseModel):
    new_path: str


class FileMkdirIn(BaseModel):
    path: str


# ---- activity / integrations
class ActivityOut(ORM):
    id: int
    project_id: str
    ts: datetime
    category: str
    message: str
    ref_type: Optional[str]
    ref_id: Optional[str]
