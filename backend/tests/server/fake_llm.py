"""A scripted function-calling LLM: each agent gets a list of turns, each turn
either a tool call or a final text. Lets the whole run pipeline (queue, events,
approvals, memories, isolation) be exercised without a model."""

from __future__ import annotations

import json
import uuid
from typing import Any, Sequence

from llama_index.core.base.llms.types import ChatMessage, ChatResponse, ChatResponseAsyncGen, ChatResponseGen, CompletionResponse, LLMMetadata, MessageRole
from llama_index.core.llms.function_calling import FunctionCallingLLM
from llama_index.core.llms.llm import ToolSelection


class ScriptedLLM(FunctionCallingLLM):
    """turns: [("tool", name, kwargs) | ("text", "final reply")]"""

    turns: list = []
    cursor: int = 0

    def __init__(self, turns: list, **kw: Any):
        super().__init__(**kw)
        self.turns = list(turns)
        self.cursor = 0

    @property
    def metadata(self) -> LLMMetadata:
        return LLMMetadata(is_function_calling_model=True, model_name="scripted", context_window=100_000, num_output=1024)

    def _next(self) -> ChatResponse:
        if self.cursor >= len(self.turns):
            turn = ("text", "done")
        else:
            turn = self.turns[self.cursor]
            self.cursor += 1
        if turn[0] == "tool":
            _, name, kwargs = turn
            call = {"id": f"call_{uuid.uuid4().hex[:8]}", "type": "function", "function": {"name": name, "arguments": json.dumps(kwargs)}}
            return ChatResponse(message=ChatMessage(role=MessageRole.ASSISTANT, content="", additional_kwargs={"tool_calls": [call]}), raw={})
        return ChatResponse(message=ChatMessage(role=MessageRole.ASSISTANT, content=turn[1]), raw={})

    # ---- FunctionCallingLLM protocol
    def _prepare_chat_with_tools(self, tools, user_msg=None, chat_history=None, verbose=False, allow_parallel_tool_calls=False, **kwargs):
        msgs = list(chat_history or [])
        if user_msg:
            msgs.append(ChatMessage(role=MessageRole.USER, content=user_msg) if isinstance(user_msg, str) else user_msg)
        return {"messages": msgs}

    def get_tool_calls_from_response(self, response: ChatResponse, error_on_no_tool_call: bool = True, **kwargs) -> list[ToolSelection]:
        calls = response.message.additional_kwargs.get("tool_calls") or []
        return [ToolSelection(tool_id=c["id"], tool_name=c["function"]["name"], tool_kwargs=json.loads(c["function"]["arguments"])) for c in calls]

    def chat(self, messages: Sequence[ChatMessage], **kwargs) -> ChatResponse:
        return self._next()

    async def achat(self, messages: Sequence[ChatMessage], **kwargs) -> ChatResponse:
        return self._next()

    def stream_chat(self, messages, **kwargs) -> ChatResponseGen:
        r = self._next()
        def gen():
            yield ChatResponse(message=r.message, delta=r.message.content or "", raw={})
        return gen()

    async def astream_chat(self, messages, **kwargs) -> ChatResponseAsyncGen:
        r = self._next()
        async def gen():
            yield ChatResponse(message=r.message, delta=r.message.content or "", raw={})
        return gen()

    def complete(self, prompt: str, formatted: bool = False, **kwargs) -> CompletionResponse:
        return CompletionResponse(text=self._next().message.content or "")

    async def acomplete(self, prompt: str, formatted: bool = False, **kwargs) -> CompletionResponse:
        return CompletionResponse(text=self._next().message.content or "")

    def stream_complete(self, prompt: str, formatted: bool = False, **kwargs):
        yield CompletionResponse(text=self._next().message.content or "")

    async def astream_complete(self, prompt: str, formatted: bool = False, **kwargs):
        async def gen():
            yield CompletionResponse(text=self._next().message.content or "")
        return gen()


# Scripts for the four template agents, keyed by agent name.
NEW_HIGH_BUG = {
    "intake": [("tool", "record_intake", {"category": "bug", "summary": "Charged twice for a gem pack", "app_version": "2.4.1", "device": "iPhone 14"}),
               ("tool", "handoff", {"to_agent": "investigator", "reason": "bug"})],
    "investigator": [("tool", "search_tickets", {"query": "double charge gem pack"}),
                     ("tool", "record_investigation", {"verdict": "new", "evidence": "no match", "confidence": 0.9}),
                     ("tool", "handoff", {"to_agent": "triage", "reason": "new"})],
    "triage": [("tool", "record_triage", {"severity": "high", "component": "billing", "rationale": "money", "affected_versions": ["2.4.1"]}),
               ("tool", "handoff", {"to_agent": "writer", "reason": "triaged"})],
    "writer": [("tool", "create_ticket", {"title": "Double charge on gem pack", "repro_steps": ["buy gems"], "expected": "one charge", "actual": "two charges"}),
               ("text", "Created ticket.")],
}

PRAISE = {
    "intake": [("tool", "record_intake", {"category": "praise", "summary": "Loves the game"}),
               ("tool", "close_as_non_bug", {"reason": "praise"}),
               ("text", "Not a bug (praise).")],
}
