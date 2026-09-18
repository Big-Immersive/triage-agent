"""API shapes: project."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, EmailStr, Field

from .base import ORM


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    icon: str = "▣"
    instructions: str = ""
    template: Optional[str] = None      # "bug-triage" applies agents + sample data


class ProjectPatch(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    instructions: Optional[str] = None
    status: Optional[str] = Field(default=None, pattern="^(draft|active|archived)$")
    config: Optional[dict[str, Any]] = None


class ProjectOut(ORM):
    id: str
    name: str
    slug: str
    description: str
    icon: str
    instructions: str
    status: str
    config: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    last_activity_at: datetime
    agents_total: int = 0
    agents_online: int = 0
    runs_active: int = 0
    approvals_pending: int = 0
    memory_synced: bool = True


# ---- agents
class AgentIn(BaseModel):
    name: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_\-]+$")
    role: str = ""
    description: str = ""
    instructions: str = ""
    model: Optional[str] = None
    tools: list[str] = []
    permissions: dict[str, Any] = {}
    can_handoff_to: list[str] = []
    enabled: bool = True
    position: int = 0


class AgentPatch(BaseModel):
    name: Optional[str] = Field(default=None, pattern=r"^[a-z0-9_\-]+$")
    role: Optional[str] = None
    description: Optional[str] = None
    instructions: Optional[str] = None
    model: Optional[str] = None
    tools: Optional[list[str]] = None
    permissions: Optional[dict[str, Any]] = None
    can_handoff_to: Optional[list[str]] = None
    enabled: Optional[bool] = None
    position: Optional[int] = None


class AgentOut(ORM):
    id: str
    project_id: str
    name: str
    role: str
    description: str
    instructions: str
    model: Optional[str]
    tools: list[str]
    permissions: dict[str, Any]
    can_handoff_to: list[str]
    enabled: bool
    position: int
    status: str
    current_process: Optional[str]
    last_active_at: Optional[datetime]
    created_at: datetime


# ---- tasks
class IntegrationOut(ORM):
    provider: str
    status: str
    config: dict[str, Any]
    connected_at: Optional[datetime]


class IntegrationIn(BaseModel):
    status: str = Field(pattern="^(connected|not_connected)$")
    config: dict[str, Any] = {}
