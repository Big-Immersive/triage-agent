"""Short, spec-shaped identifiers: RUN_8FA21, MEM_0192, APPROVAL_REQ_021."""

from __future__ import annotations

import secrets
import uuid


def uid() -> str:
    return uuid.uuid4().hex


def run_id() -> str:
    return "RUN_" + secrets.token_hex(3).upper()[:5]


def memory_id() -> str:
    return "MEM_" + secrets.token_hex(2).upper()


def approval_id() -> str:
    return "APPROVAL_REQ_" + secrets.token_hex(2).upper()[:3]


def task_id() -> str:
    return "TASK_" + secrets.token_hex(3).upper()[:5]
