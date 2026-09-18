"""Accounts and per-user LLM / embedding settings (keys stored encrypted)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, now, pk, project_fk, ts


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = pk()
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = ts()

    settings: Mapped[Optional["UserSettings"]] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")


class UserSettings(Base):
    __tablename__ = "user_settings"
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    provider: Mapped[str] = mapped_column(String(20), default="openrouter")   # openrouter | ollama
    openrouter_key_enc: Mapped[Optional[str]] = mapped_column(Text)
    ollama_url: Mapped[str] = mapped_column(String(255), default="http://localhost:11434")
    default_model: Mapped[Optional[str]] = mapped_column(String(120))
    embed_provider: Mapped[str] = mapped_column(String(20), default="ollama")   # ollama | openai_compatible
    embed_model: Mapped[str] = mapped_column(String(120), default="nomic-embed-text")
    embed_base_url: Mapped[Optional[str]] = mapped_column(String(255))          # e.g. https://api.openai.com/v1
    embed_api_key_enc: Mapped[Optional[str]] = mapped_column(Text)
    updated_at: Mapped[datetime] = ts()

    user: Mapped[User] = relationship(back_populates="settings")
