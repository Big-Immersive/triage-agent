from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import APIRouter, HTTPException, Request, Response
from sqlalchemy import select

from ..core.config import settings
from ..core.deps import CurrentUser, Session
from ..models import User, UserSettings
from ..schemas import LoginIn, RegisterIn, UserOut
from ..core.security import hash_password, make_token, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Small per-replica limiter for the credential endpoints (10 attempts / minute / IP).
_attempts: dict[str, deque] = defaultdict(deque)


def _rate_limit(request: Request) -> None:
    ip = request.client.host if request.client else "?"
    q = _attempts[ip]
    now_ = time.monotonic()
    while q and now_ - q[0] > 60:
        q.popleft()
    if len(q) >= 10:
        raise HTTPException(429, "Too many attempts; try again in a minute")
    q.append(now_)


def _session(resp: Response, user: User) -> dict:
    """The token goes in the body (the UI is a separate origin and sends it as a Bearer header)
    and in an httpOnly cookie for same-origin deployments."""
    token = make_token(user.id)
    resp.set_cookie(settings.COOKIE_NAME, token, httponly=True, samesite="lax", secure=settings.COOKIE_SECURE,
                    max_age=settings.JWT_TTL_HOURS * 3600, path="/")
    return {"user": UserOut.model_validate(user), "token": token}


@router.post("/register", status_code=201)
async def register(body: RegisterIn, resp: Response, request: Request, session: Session):
    _rate_limit(request)
    email = body.email.lower()
    if (await session.execute(select(User).where(User.email == email))).scalar_one_or_none():
        raise HTTPException(409, "An account with that email already exists")
    user = User(email=email, password_hash=hash_password(body.password), name=body.name or email.split("@")[0])
    session.add(user)
    await session.flush()
    session.add(UserSettings(user_id=user.id))
    await session.commit()
    return _session(resp, user)


@router.post("/login")
async def login(body: LoginIn, resp: Response, request: Request, session: Session):
    _rate_limit(request)
    user = (await session.execute(select(User).where(User.email == body.email.lower()))).scalar_one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Invalid email or password")
    return _session(resp, user)


@router.post("/logout", status_code=204)
async def logout(resp: Response):
    resp.delete_cookie(settings.COOKIE_NAME, path="/")


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser):
    return user
