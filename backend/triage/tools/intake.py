"""Intake agent tools: classify the raw report and extract facts."""


from typing import Optional

from pydantic import ValidationError
from workflows import Context

from ..schemas import Intake
from ..state import update_state
from .coerce import StrList, as_list


async def record_intake(
    ctx: Context,
    category: str,
    summary: str,
    language: str = "en",
    app_version: Optional[str] = None,
    device: Optional[str] = None,
    os: Optional[str] = None,
    steps: StrList = None,
) -> str:
    """Record the classification of the feedback item. Call this exactly once.

    Args:
        category: one of bug, feature_request, praise, spam, support_question, other.
            'bug' = something is broken or crashes. 'support_question' = user asks how to do
            something that works. 'feature_request' = asks for something that does not exist.
        summary: one-sentence summary IN ENGLISH, even if the original is another language.
        language: ISO code of the original text, e.g. en, es, de.
        app_version: version string from metadata or text, e.g. "2.4.1", if known.
        device: device model if known, e.g. "Pixel 8".
        os: operating system if known, e.g. "Android 14".
        steps: reproduction steps the user described, as a list of short strings.
    """
    try:
        intake = Intake(
            category=category, summary=summary, language=language,
            app_version=app_version, device=device, os=os, steps=as_list(steps),
        )
    except ValidationError as exc:
        return f"Invalid intake, fix and call again: {exc.errors()[0]['msg']} (field: {exc.errors()[0]['loc']})"

    await update_state(ctx, intake=intake.model_dump())
    if intake.category == "bug":
        return (
            f"Recorded intake: {intake.model_dump_json()}\n"
            "This is a bug. NOW call handoff(to_agent='investigator', reason='bug report needs duplicate check')."
        )
    return (
        f"Recorded intake: {intake.model_dump_json()}\n"
        f"This is NOT a bug ({intake.category}). NOW call close_as_non_bug with a short reason. Do not hand off."
    )
