"""API shapes: auth."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, EmailStr, Field

from .base import ORM


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    name: str = ""


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(ORM):
    id: str
    email: str
    name: str
    created_at: datetime


class LlmSettingsIn(BaseModel):
    provider: str = Field(pattern="^(openrouter|ollama)$")
    openrouter_key: Optional[str] = None      # None = leave unchanged; "" = clear
    ollama_url: Optional[str] = None
    default_model: Optional[str] = None
    embed_provider: Optional[str] = Field(default=None, pattern="^(ollama|openai_compatible)$")
    embed_model: Optional[str] = None
    embed_base_url: Optional[str] = None
    embed_api_key: Optional[str] = None       # None = leave unchanged; "" = clear


class LlmSettingsOut(BaseModel):
    provider: str
    openrouter_key_masked: Optional[str]
    has_openrouter_key: bool
    ollama_url: str
    default_model: str
    embed_provider: str
    embed_model: str
    embed_base_url: Optional[str]
    embed_api_key_masked: Optional[str]
    has_embed_api_key: bool
    updated_at: Optional[datetime]


# ---- projects
