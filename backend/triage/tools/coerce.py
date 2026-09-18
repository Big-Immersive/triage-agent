"""Argument coercion for small local models.

Models driven through Ollama frequently send list arguments as strings:
'["a", "b"]', 'a; b', or just 'a'. Rejecting those wastes a round-trip (or,
with a weak model, loops forever). Accept them and normalise instead.
"""

import json
import re
from typing import Optional, Union

StrList = Optional[Union[list[str], str]]


def as_list(value: StrList) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    s = str(value).strip()
    if not s or s.lower() in ("null", "none", "[]"):
        return []
    if s.startswith("["):
        try:
            parsed = json.loads(s)
            if isinstance(parsed, list):
                return [str(v).strip() for v in parsed if str(v).strip()]
        except json.JSONDecodeError:
            pass
    # "1. tap shop 2. crash" / "a; b" / "a\nb"
    parts = re.split(r"\n+|;\s*|(?<=\D)\s+(?=\d+[.)]\s)", s)
    parts = [re.sub(r"^\d+[.)]\s*", "", p).strip() for p in parts]
    return [p for p in parts if p]


def as_float(value, default: float = 0.5) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
