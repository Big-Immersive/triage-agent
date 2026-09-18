"""The structured records each agent produces.

Rather than asking the LLM for free-form JSON, each agent calls a `record_*`
tool whose arguments are validated against one of these models. That gives us
typed state, clear error messages the model can self-correct from, and
something an eval can score.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

Category = Literal["bug", "feature_request", "praise", "spam", "support_question", "other"]
Verdict = Literal["new", "duplicate", "needs_info"]
Severity = Literal["low", "medium", "high", "critical"]
Outcome = Literal["new_ticket", "duplicate", "needs_info", "dropped", "unresolved"]


class RawFeedback(BaseModel):
    id: str
    source: str
    received_at: str
    author: str
    rating: Optional[int] = None
    metadata: dict = Field(default_factory=dict)
    text: str

    def as_prompt(self) -> str:
        meta = ", ".join(f"{k}={v}" for k, v in self.metadata.items() if v) or "none"
        rating = f" rating={self.rating}/5" if self.rating is not None else ""
        return (
            f"Feedback {self.id} from {self.source}{rating} by {self.author} at {self.received_at}\n"
            f"Metadata: {meta}\n"
            f"Text:\n{self.text}"
        )


class Intake(BaseModel):
    category: Category
    summary: str = Field(description="One-sentence English summary of the report")
    language: str = Field(default="en", description="ISO 639-1 code of the original text")
    app_version: Optional[str] = None
    device: Optional[str] = None
    os: Optional[str] = None
    steps: list[str] = Field(default_factory=list, description="Reproduction steps if the user gave any")


class Investigation(BaseModel):
    verdict: Verdict
    matched_ticket_id: Optional[str] = Field(default=None, description="Existing tracker ticket id, e.g. OR-104")
    matched_report_id: Optional[str] = Field(default=None, description="Earlier feedback id in this batch, e.g. FB-001")
    crash_signature: Optional[str] = None
    evidence: str = Field(description="What was found and why it supports the verdict")
    confidence: float = Field(ge=0, le=1)
    missing_info: list[str] = Field(default_factory=list, description="For needs_info: what to ask the user")


class Triage(BaseModel):
    severity: Severity
    component: str
    owner: str
    rationale: str
    affected_versions: list[str] = Field(default_factory=list)


class Ticket(BaseModel):
    id: str
    title: str
    severity: Severity
    component: str
    owner: str
    affected_versions: list[str]
    repro_steps: list[str]
    expected: str
    actual: str
    evidence: str
    source_feedback: list[str]
    approved_by: str = "auto"


class Result(BaseModel):
    """What the pipeline produced for one feedback item — used by the eval."""
    feedback_id: str
    outcome: Outcome
    category: Category
    verdict: Optional[Verdict] = None
    severity: Optional[Severity] = None
    component: Optional[str] = None
    duplicate_of: Optional[str] = None
    ticket_id: Optional[str] = None
    artifact: Optional[str] = None
