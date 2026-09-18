"""Passwords (argon2), sessions (JWT in an httpOnly cookie), and secret encryption (Fernet)."""

from __future__ import annotations

import base64
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken
from fastapi import Depends, HTTPException, Request, WebSocket, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .db import get_session
from ..models import User

_ph = PasswordHasher()
_fernet = Fernet(base64.urlsafe_b64encode(hashlib.sha256(settings.TRIAGE_SECRET_KEY.encode()).digest()))


def hash_password(pw: str) -> str:
    return _ph.hash(pw)


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, pw)
    except VerifyMismatchError:
        return False


def encrypt(secret: str) -> str:
    return _fernet.encrypt(secret.encode()).decode()


def decrypt(token: str) -> str:
    try:
        return _fernet.decrypt(token.encode()).decode()
    except InvalidToken:
        raise HTTPException(500, "Stored secret cannot be decrypted (TRIAGE_SECRET_KEY changed?).")


def mask(secret: Optional[str]) -> Optional[str]:
    if not secret:
        return None
    return secret[:6] + "…" + secret[-4:] if len(secret) > 12 else "•" * len(secret)


def make_token(user_id: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=settings.JWT_TTL_HOURS)
    return jwt.encode({"sub": user_id, "exp": exp}, settings.TRIAGE_SECRET_KEY, algorithm="HS256")


def read_token(token: str) -> Optional[str]:
    try:
        return jwt.decode(token, settings.TRIAGE_SECRET_KEY, algorithms=["HS256"])["sub"]
    except jwt.PyJWTError:
        return None


def _token_from(request: Request | WebSocket) -> Optional[str]:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:]
    # Browsers cannot set headers on WebSocket handshakes; the UI passes ?token=.
    qt = request.query_params.get("token")
    if qt:
        return qt
    return request.cookies.get(settings.COOKIE_NAME)


async def _load_user(session: AsyncSession, token: Optional[str]) -> Optional[User]:
    uid = read_token(token) if token else None
    if not uid:
        return None
    return await session.get(User, uid)


async def current_user(request: Request, session: AsyncSession = Depends(get_session)) -> User:
    user = await _load_user(session, _token_from(request))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    return user


async def ws_user(ws: WebSocket, session: AsyncSession) -> Optional[User]:
    return await _load_user(session, _token_from(ws))
