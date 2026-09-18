"""API shapes: work."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, EmailStr, Field

from .base import ORM


class TaskIn(BaseModel):
    external_id: Optional[str] = None
    source: str = "manual"
    author: str = ""
    title: str = ""
    text: str = Field(min_length=1)
    rating: Optional[int] = None
    received_at: Optional[str] = None
    meta: dict[str, Any] = {}


class TaskOut(ORM):
    id: str
    project_id: str
    external_id: str
    source: str
    author: str
    title: str
    text: str
    rating: Optional[int]
    received_at: Optional[str]
    meta: dict[str, Any]
    status: str
    result: Optional[dict[str, Any]]
    last_run_id: Optional[str]
    created_at: datetime
    last_run_status: Optional[str] = None


# ---- runs
class RunOut(ORM):
    id: str
    project_id: str
    task_id: Optional[str]
    status: str
    starting_agent: Optional[str]
    current_agent: Optional[str]
    started_at: datetime
    ended_at: Optional[datetime]
    duration_ms: Optional[int]
    tool_call_count: int
    handoff_count: int
    approval_state: str
    final_text: Optional[str]
    result: Optional[dict[str, Any]]
    error: Optional[str]
    auto_approve: bool
    task_external_id: Optional[str] = None


class RunEventOut(ORM):
    id: int
    run_id: str
    seq: int
    ts: datetime
    kind: str
    actor: str
    message: str
    input: Optional[Any]
    output: Optional[Any]
    meta: dict[str, Any]
    duration_ms: Optional[int]


class ToolCallOut(ORM):
    id: str
    run_id: str
    agent_name: str
    tool_name: str
    args: dict[str, Any]
    result: Optional[str]
    is_error: bool
    ts: datetime
    duration_ms: Optional[int]


# ---- approvals
class ApprovalOut(ORM):
    id: str
    project_id: str
    run_id: str
    agent_name: str
    action: str
    reason: str
    confidence: Optional[float]
    details: dict[str, Any]
    status: str
    response: Optional[dict[str, Any]]
    requested_at: datetime
    resolved_at: Optional[datetime]
    ticket_id: Optional[str] = None


class ApprovalModifyIn(BaseModel):
    severity: str = Field(pattern="^(low|medium|high|critical)$")


# ---- memory
