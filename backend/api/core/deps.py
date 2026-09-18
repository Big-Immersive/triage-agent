"""Shared dependencies. `get_project` is the isolation boundary: a project
that exists but belongs to someone else is a 404, never a 403."""

from __future__ import annotations

import re
from typing import Annotated

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db import get_session
from ..models import Project, User
from .security import current_user

Session = Annotated[AsyncSession, Depends(get_session)]
CurrentUser = Annotated[User, Depends(current_user)]


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s[:60] or "project"


async def get_project(project_id: str, user: CurrentUser, session: Session) -> Project:
    p = await session.get(Project, project_id)
    if p is None:
        p = (await session.execute(select(Project).where(Project.owner_id == user.id, Project.slug == project_id))).scalar_one_or_none()
    if p is None or p.owner_id != user.id:
        raise HTTPException(404, "Project not found")
    return p


ProjectDep = Annotated[Project, Depends(get_project)]
