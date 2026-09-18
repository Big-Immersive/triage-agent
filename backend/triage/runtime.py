"""Per-project runtime: everything the tools used to keep in module globals.

One `ProjectRuntime` per project holds that project's tracker tickets, crash
log, ownership table, release info, and handles to three vector collections
(tracker tickets, batch memory of processed reports, uploaded knowledge). All
three live in ONE vector store; every node carries `project_id` and `kind`
metadata and every search filters on both, so nothing crosses projects even
though the store is shared.

The store is pluggable: the CLI and tests use LlamaIndex's in-memory store;
the server passes a pgvector-backed store so any API replica can serve any
project (no per-process index files). Tools look the runtime up through the
workflow state (`state["project_id"]`).
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from llama_index.core import Document, StorageContext, VectorStoreIndex
from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.schema import BaseNode, NodeWithScore
from llama_index.core.vector_stores import ExactMatchFilter, MetadataFilters
from llama_index.core.vector_stores.types import BasePydanticVectorStore

ArtifactHook = Callable[[str, str, Path, dict, Optional[str]], Any]  # (kind, name, path, payload, run_id) -> awaitable | None
IdAllocator = Callable[[], Awaitable[str]]

KIND_TICKETS, KIND_BATCH, KIND_KNOWLEDGE = "tickets", "batch", "knowledge"
_HIDDEN = ["project_id", "kind", "ticket_id", "status", "component", "feedback_id", "outcome", "item_id"]


def parse_codeowners(text: str) -> dict[str, tuple[str, str]]:
    owners: dict[str, tuple[str, str]] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) >= 3:
            owners[parts[0]] = (parts[1], parts[2])
        elif len(parts) == 2:
            owners[parts[0]] = (parts[1], "")
    return owners


def parse_crashes(text: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(text)))


@dataclass
class ProjectRuntime:
    project_id: str
    embed_model: BaseEmbedding
    out_dir: Path = field(default_factory=lambda: Path(tempfile.mkdtemp(prefix="triage-out-")))
    vector_store: Optional[BasePydanticVectorStore] = None    # None => in-memory (CLI / tests)
    tickets: dict[str, dict] = field(default_factory=dict)
    crash_rows: list[dict] = field(default_factory=list)
    owners: dict[str, tuple[str, str]] = field(default_factory=dict)
    releases: dict = field(default_factory=dict)
    ticket_prefix: str = "OR"
    next_ticket_num: int = 101
    id_allocator: Optional[IdAllocator] = None      # server: atomic counter in Postgres
    artifact_hook: Optional[ArtifactHook] = None
    report_tickets: dict[str, str] = field(default_factory=dict)   # feedback_id -> ticket it resolved to
    index: Optional[VectorStoreIndex] = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    # ------------------------------------------------------------ building --
    @classmethod
    def from_sources(
        cls,
        project_id: str,
        embed_model: BaseEmbedding,
        *,
        tickets: Optional[list[dict]] = None,
        crashes_csv: str = "",
        codeowners: str = "",
        releases: Optional[dict] = None,
        vector_store: Optional[BasePydanticVectorStore] = None,
        out_dir: Optional[Path] = None,
        artifact_hook: Optional[ArtifactHook] = None,
        id_allocator: Optional[IdAllocator] = None,
        index_tickets: bool = True,
    ) -> "ProjectRuntime":
        kw = {"out_dir": out_dir} if out_dir else {}
        rt = cls(project_id=project_id, embed_model=embed_model, vector_store=vector_store, artifact_hook=artifact_hook, id_allocator=id_allocator, **kw)
        rt.tickets = {t["id"]: t for t in (tickets or [])}
        rt.crash_rows = parse_crashes(crashes_csv) if crashes_csv else []
        rt.owners = parse_codeowners(codeowners) if codeowners else {}
        rt.releases = releases or {}
        rt._init_ticket_numbering()
        for sub in ("tickets", "comments", "replies", "dropped"):
            (rt.out_dir / sub).mkdir(parents=True, exist_ok=True)
        rt.open_index()
        if index_tickets:
            rt.rebuild_tickets()
        return rt

    @classmethod
    def from_fixtures(cls, project_id: str, fixtures_dir: Path, embed_model: BaseEmbedding, **kw) -> "ProjectRuntime":
        """What the CLI uses: the demo dataset straight from disk."""
        return cls.from_sources(
            project_id, embed_model,
            tickets=json.loads((fixtures_dir / "tickets.json").read_text()),
            crashes_csv=(fixtures_dir / "crashes.csv").read_text(),
            codeowners=(fixtures_dir / "CODEOWNERS").read_text(),
            releases=json.loads((fixtures_dir / "releases.json").read_text()),
            **kw,
        )

    def _init_ticket_numbering(self) -> None:
        nums = []
        for tid in self.tickets:
            m = re.match(r"([A-Za-z]+)-(\d+)", tid)
            if m:
                self.ticket_prefix = m.group(1)
                nums.append(int(m.group(2)))
        self.next_ticket_num = max(nums, default=100) + 1

    def open_index(self) -> None:
        if self.vector_store is not None:
            self.index = VectorStoreIndex.from_vector_store(self.vector_store, embed_model=self.embed_model)
        else:
            self.index = VectorStoreIndex([], embed_model=self.embed_model, storage_context=StorageContext.from_defaults())

    # --------------------------------------------------------------- nodes --
    def _filters(self, kind: str, **extra: str) -> MetadataFilters:
        fl = [ExactMatchFilter(key="project_id", value=self.project_id), ExactMatchFilter(key="kind", value=kind)]
        fl += [ExactMatchFilter(key=k, value=v) for k, v in extra.items()]
        return MetadataFilters(filters=fl)

    def _doc(self, kind: str, text: str, doc_id: Optional[str] = None, **meta: Any) -> Document:
        meta = {"project_id": self.project_id, "kind": kind, **meta}
        d = Document(text=text, metadata=meta, excluded_embed_metadata_keys=_HIDDEN, excluded_llm_metadata_keys=_HIDDEN)
        if doc_id:
            d.doc_id = doc_id
        return d

    def _insert(self, docs: list[Document]) -> None:
        if self.index is None or not docs:
            return
        for d in docs:
            self.index.insert(d)

    def _delete(self, kind: str, **extra: str) -> None:
        if self.index is None:
            return
        store = self.index.vector_store
        try:
            store.delete_nodes(filters=self._filters(kind, **extra))
        except NotImplementedError:
            pass
        if not store.stores_text:  # in-memory: keep the docstore in step
            docs = self.index.docstore.docs
            for nid in [i for i, n in list(docs.items()) if self._node_matches(n, kind, extra)]:
                self.index.docstore.delete_document(nid, raise_error=False)

    @staticmethod
    def _node_matches(node: BaseNode, kind: str, extra: dict) -> bool:
        m = node.metadata or {}
        return m.get("kind") == kind and all(m.get(k) == v for k, v in extra.items())

    async def _search(self, kind: str, query: str, k: int) -> list[NodeWithScore]:
        if self.index is None:
            return []
        return await self.index.as_retriever(similarity_top_k=k, filters=self._filters(kind)).aretrieve(query)

    def _get_nodes(self, kind: str, **extra: str) -> list[BaseNode]:
        if self.index is None:
            return []
        try:
            return list(self.index.vector_store.get_nodes(filters=self._filters(kind, **extra)))
        except NotImplementedError:
            return [n for n in self.index.docstore.docs.values() if self._node_matches(n, kind, extra)]

    # ------------------------------------------------------------ tickets --
    def _ticket_doc(self, t: dict) -> Document:
        return self._doc(KIND_TICKETS, f"{t['title']}\n{t.get('description') or t.get('actual') or ''}",
                         doc_id=f"{self.project_id}:ticket:{t['id']}",
                         ticket_id=t["id"], status=t.get("status", "open"), component=t.get("component", ""))

    def rebuild_tickets(self) -> None:
        """Replace the tracker collection with the current `tickets` dict."""
        self._delete(KIND_TICKETS)
        self._insert([self._ticket_doc(t) for t in self.tickets.values()])

    def has_ticket_vectors(self) -> bool:
        return bool(self._get_nodes(KIND_TICKETS))

    async def search_tickets(self, query: str, k: int = 3) -> list[NodeWithScore]:
        return await self._search(KIND_TICKETS, query, k)

    async def allocate_ticket_id(self) -> str:
        if self.id_allocator is not None:
            return await self.id_allocator()
        tid = f"{self.ticket_prefix}-{self.next_ticket_num}"
        self.next_ticket_num += 1
        return tid

    def register_ticket(self, ticket: dict) -> None:
        """Make a ticket created during a run searchable and citable like tracker tickets."""
        self.tickets[ticket["id"]] = {
            "id": ticket["id"], "title": ticket["title"], "status": "open", "severity": ticket["severity"],
            "component": ticket["component"], "affected_versions": ticket["affected_versions"],
            "fixed_in": None, "owner": ticket["owner"], "description": ticket["actual"],
        }
        self._insert([self._ticket_doc(self.tickets[ticket["id"]])])

    # ------------------------------------------------------- batch memory --
    def remember_report(self, feedback_id: str, text: str, outcome: str, ticket_id: Optional[str]) -> None:
        """Called once an item is finished, so later items can find it."""
        if ticket_id:
            self.report_tickets[feedback_id] = ticket_id
        self._delete(KIND_BATCH, feedback_id=feedback_id)
        self._insert([self._doc(KIND_BATCH, text, doc_id=f"{self.project_id}:report:{feedback_id}",
                                feedback_id=feedback_id, outcome=outcome, ticket_id=ticket_id or "")])

    async def search_reports(self, query: str, k: int = 3) -> list[NodeWithScore]:
        return await self._search(KIND_BATCH, query, k)

    def ticket_for_report(self, feedback_id: str) -> Optional[str]:
        if feedback_id in self.report_tickets:
            return self.report_tickets[feedback_id]
        for n in self._get_nodes(KIND_BATCH, feedback_id=feedback_id):
            if n.metadata.get("ticket_id"):
                return n.metadata["ticket_id"]
        return None

    # ---------------------------------------------------------- knowledge --
    def add_knowledge(self, item_id: str, name: str, text: str, chunk_cb: Optional[Callable[[int, int], Any]] = None) -> int:
        """Chunk and insert one knowledge item. Returns the number of chunks."""
        from llama_index.core.node_parser import SentenceSplitter

        if self.index is None:
            return 0
        text = text.replace("\x00", "")
        self.remove_knowledge(item_id)
        doc = self._doc(KIND_KNOWLEDGE, text, doc_id=f"{self.project_id}:knowledge:{item_id}", item_id=item_id, name=name)
        nodes = SentenceSplitter(chunk_size=512, chunk_overlap=64).get_nodes_from_documents([doc])
        for i, node in enumerate(nodes, 1):
            self.index.insert_nodes([node])
            if chunk_cb:
                chunk_cb(i, len(nodes))
        return len(nodes)

    def remove_knowledge(self, item_id: str) -> None:
        self._delete(KIND_KNOWLEDGE, item_id=item_id)

    def knowledge_empty(self) -> bool:
        return not self._get_nodes(KIND_KNOWLEDGE)

    async def search_knowledge(self, query: str, k: int = 4) -> list[NodeWithScore]:
        return await self._search(KIND_KNOWLEDGE, query, k)

    # ---------------------------------------------------------- artifacts --
    async def write_artifact(self, sub: str, name: str, payload: dict, body_md: str, run_id: Optional[str] = None) -> str:
        d = self.out_dir / sub
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{name}.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False))
        path = d / f"{name}.md"
        path.write_text(body_md)
        if self.artifact_hook is not None:
            res = self.artifact_hook(sub, name, path, payload, run_id)
            if asyncio.iscoroutine(res):
                await res
        return f"{sub}/{name}.md"


# ------------------------------------------------------------- registry ----
# A per-process cache. The server invalidates entries when a project's
# structured knowledge changes (and other replicas do the same on notify).

_RUNTIMES: dict[str, ProjectRuntime] = {}


def register(rt: ProjectRuntime) -> ProjectRuntime:
    _RUNTIMES[rt.project_id] = rt
    return rt


def unregister(project_id: str) -> None:
    _RUNTIMES.pop(project_id, None)


def get(project_id: str) -> ProjectRuntime:
    try:
        return _RUNTIMES[project_id]
    except KeyError:
        raise RuntimeError(f"No runtime registered for project {project_id!r}") from None


def for_state(state: dict) -> ProjectRuntime:
    return get(state["project_id"])
