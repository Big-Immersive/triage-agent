import asyncio
import io

import pytest
from llama_index.core.embeddings import MockEmbedding

from api.services import llm as llm_service
from api.services import runtimes

from .conftest import register
from .fake_llm import NEW_HIGH_BUG, PRAISE, ScriptedLLM

pytestmark = pytest.mark.asyncio


@pytest.fixture
def scripted(monkeypatch):
    """Route every agent's LLM to a script and embeddings to MockEmbedding."""
    def use(script: dict):
        def for_agent(self, agent_name, model_spec):
            from llama_index.core.callbacks import CallbackManager, TokenCountingHandler
            h = TokenCountingHandler()
            self.counters[agent_name] = llm_service.AgentCounter("ollama", "scripted", h)
            return ScriptedLLM(script.get(agent_name, [("text", "nothing to do")]), callback_manager=CallbackManager([h]))
        monkeypatch.setattr(llm_service.RunLlmFactory, "for_agent", for_agent)
        monkeypatch.setattr(runtimes, "make_embed", lambda cfg: MockEmbedding(embed_dim=16))
        monkeypatch.setattr(llm_service.ResolvedLlmConfig, "ready", lambda self: (True, ""))
        from api.services import usage
        async def no_pricing():
            return {}
        monkeypatch.setattr(usage, "pricing", no_pricing)
    return use


async def _project(client, h, name="proj", template="bug-triage"):
    r = await client.post("/api/projects", json={"name": name, "template": template}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


async def _wait_knowledge(client, h, pid, timeout=20):
    for _ in range(int(timeout / 0.25)):
        items = (await client.get(f"/api/projects/{pid}/knowledge", headers=h)).json()
        if items and all(i["status"] != "indexing" for i in items):
            return items
        await asyncio.sleep(0.25)
    raise AssertionError("knowledge never finished indexing")


async def _wait_run(client, h, pid, run_id, until=("complete", "error", "cancelled"), timeout=30):
    for _ in range(int(timeout / 0.25)):
        r = (await client.get(f"/api/projects/{pid}/runs/{run_id}", headers=h)).json()
        if r["status"] in until:
            return r
        await asyncio.sleep(0.25)
    raise AssertionError(f"run stuck in {r['status']}")


# ------------------------------------------------------------------ auth ----

async def test_register_login_me_and_key_masking(client):
    h = await register(client, "a@example.com")
    me = await client.get("/api/auth/me", headers=h)
    assert me.status_code == 200 and me.json()["email"] == "a@example.com"
    r = await client.post("/api/auth/login", json={"email": "a@example.com", "password": "wrong"})
    assert r.status_code == 401
    r = await client.put("/api/me/llm", json={"provider": "openrouter", "openrouter_key": "sk-or-v1-abcdefghijklmnop1234"}, headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["has_openrouter_key"] and body["openrouter_key_masked"] == "sk-or-…1234"
    assert "sk-or-v1-abcdefghijklmnop1234" not in r.text
    client.cookies.clear()
    assert (await client.get("/api/auth/me")).status_code == 401


# ------------------------------------------------------------- isolation ----

async def test_projects_are_invisible_across_users(client, scripted):
    scripted(PRAISE)
    ha = await register(client, "a@example.com")
    hb = await register(client, "b@example.com")
    pa = await _project(client, ha, "alpha")
    pb = await _project(client, hb, "beta")
    assert [p["id"] for p in (await client.get("/api/projects", headers=ha)).json()] == [pa["id"]]
    assert [p["id"] for p in (await client.get("/api/projects", headers=hb)).json()] == [pb["id"]]
    # every project-scoped endpoint answers 404 for the other user's project (not 403: no existence leak)
    for path in ("", "/agents", "/tasks", "/runs", "/memories", "/knowledge", "/files", "/approvals", "/activity", "/integrations", "/overview", "/graph"):
        r = await client.get(f"/api/projects/{pb['id']}{path}", headers=ha)
        assert r.status_code == 404, path
    assert (await client.post(f"/api/projects/{pb['id']}/sample-data", headers=ha)).status_code == 404
    assert (await client.patch(f"/api/projects/{pb['id']}", json={"name": "x"}, headers=ha)).status_code == 404
    assert (await client.delete(f"/api/projects/{pb['id']}", headers=ha)).status_code == 404
    # slugs are per owner: both can have "alpha"
    assert (await client.post("/api/projects", json={"name": "alpha"}, headers=hb)).status_code == 201


async def test_runs_never_see_another_projects_tracker(client, scripted):
    """Project A's tracker has OR-104; project B has no tracker. A search in B must not find OR-104."""
    scripted(NEW_HIGH_BUG)
    h = await register(client, "a@example.com")
    pa = await _project(client, h, "with-tracker")
    pb = await _project(client, h, "no-tracker", template=None)
    await _wait_knowledge(client, h, pa["id"])
    # B gets agents but no knowledge, and one task.
    r = await client.post(f"/api/projects/{pb['id']}/sample-data?knowledge_items=false&tasks=false", headers=h)
    assert r.status_code == 200
    await client.patch(f"/api/projects/{pb['id']}", json={"config": {"auto_run": False}}, headers=h)   # run it explicitly below
    t = (await client.post(f"/api/projects/{pb['id']}/tasks", json={"text": "Charged twice for gems on 2.4.1", "external_id": "FB-900"}, headers=h)).json()
    run_id = (await client.post(f"/api/projects/{pb['id']}/tasks/{t['id']}/run?auto_approve=true", headers=h)).json()["run_id"]
    run = await _wait_run(client, h, pb["id"], run_id)
    assert run["status"] == "complete", run
    events = (await client.get(f"/api/projects/{pb['id']}/runs/{run_id}/events", headers=h)).json()
    search = next(e for e in events if e["kind"] == "TOOL_RESULT" and e["actor"] == "SEARCH_TICKETS")
    assert "OR-104" not in search["output"]["text"] and "No tickets found" in search["output"]["text"]
    # ...while the same search in A does find tracker tickets
    ta = next(x for x in (await client.get(f"/api/projects/{pa['id']}/tasks", headers=h)).json() if x["external_id"] == "FB-014")
    run_a = (await client.post(f"/api/projects/{pa['id']}/tasks/{ta['id']}/run?auto_approve=true", headers=h)).json()["run_id"]
    ra = await _wait_run(client, h, pa["id"], run_a)
    assert ra["status"] == "complete", ra
    ev_a = (await client.get(f"/api/projects/{pa['id']}/runs/{run_a}/events", headers=h)).json()
    search_a = next(e for e in ev_a if e["kind"] == "TOOL_RESULT" and e["actor"] == "SEARCH_TICKETS")
    assert "OR-" in search_a["output"]["text"]
    # memories were written to the right projects only
    ma = (await client.get(f"/api/projects/{pa['id']}/memories", headers=h)).json()
    mb = (await client.get(f"/api/projects/{pb['id']}/memories", headers=h)).json()
    assert all(m["project_id"] == pa["id"] for m in ma) and all(m["project_id"] == pb["id"] for m in mb)
    assert any("FB-014" in m["content"] for m in ma) and not any("FB-014" in m["content"] for m in mb)


# ------------------------------------------------------------- approvals ----

async def test_human_gate_round_trip(client, scripted):
    scripted(NEW_HIGH_BUG)
    h = await register(client, "a@example.com")
    p = await _project(client, h)
    await _wait_knowledge(client, h, p["id"])
    task = next(x for x in (await client.get(f"/api/projects/{p['id']}/tasks", headers=h)).json() if x["external_id"] == "FB-014")
    run_id = (await client.post(f"/api/projects/{p['id']}/tasks/{task['id']}/run", headers=h)).json()["run_id"]
    run = await _wait_run(client, h, p["id"], run_id, until=("waiting_approval", "complete", "error"))
    assert run["status"] == "waiting_approval", run
    pending = (await client.get(f"/api/projects/{p['id']}/approvals?status=pending", headers=h)).json()
    assert len(pending) == 1 and pending[0]["details"]["severity"] == "high" and pending[0]["agent_name"] == "writer"
    agents = {a["name"]: a for a in (await client.get(f"/api/projects/{p['id']}/agents", headers=h)).json()}
    assert agents["writer"]["status"] == "human_input"
    r = await client.post(f"/api/projects/{p['id']}/approvals/{pending[0]['id']}/modify", json={"severity": "critical"}, headers=h)
    assert r.status_code == 200 and r.json()["status"] == "modified"
    run = await _wait_run(client, h, p["id"], run_id)
    assert run["status"] == "complete" and run["approval_state"] == "modified"
    assert run["result"]["outcome"] == "new_ticket" and run["result"]["severity"] == "critical"
    files = [f["path"] for f in (await client.get(f"/api/projects/{p['id']}/files", headers=h)).json()]
    assert f"/out/tickets/{run['result']['ticket_id']}.md" in files
    kinds = [e["kind"] for e in (await client.get(f"/api/projects/{p['id']}/runs/{run_id}/events", headers=h)).json()]
    assert kinds.count("APPROVAL") == 2 and "HANDOFF" in kinds and kinds[-1] == "FINAL"
    mem = (await client.get(f"/api/projects/{p['id']}/memories?type=DECISIONS", headers=h)).json()
    assert any("overrode" in m["content"] for m in mem)
    usage = (await client.get("/api/me/usage", headers=h)).json()
    assert {"total_cost_usd", "projects", "models", "recent"} <= set(usage)   # the scripted LLM emits no token counts
    # approving twice is rejected
    assert (await client.post(f"/api/projects/{p['id']}/approvals/{pending[0]['id']}/approve", headers=h)).status_code == 409


async def test_reject_drops_ticket(client, scripted):
    scripted(NEW_HIGH_BUG)
    h = await register(client, "a@example.com")
    p = await _project(client, h)
    await _wait_knowledge(client, h, p["id"])
    task = next(x for x in (await client.get(f"/api/projects/{p['id']}/tasks", headers=h)).json() if x["external_id"] == "FB-014")
    run_id = (await client.post(f"/api/projects/{p['id']}/tasks/{task['id']}/run", headers=h)).json()["run_id"]
    await _wait_run(client, h, p["id"], run_id, until=("waiting_approval",))
    aid = (await client.get(f"/api/projects/{p['id']}/approvals?status=pending", headers=h)).json()[0]["id"]
    assert (await client.post(f"/api/projects/{p['id']}/approvals/{aid}/reject", headers=h)).status_code == 200
    run = await _wait_run(client, h, p["id"], run_id)
    assert run["status"] == "complete" and run["result"]["outcome"] == "dropped"
    assert not any(f["path"].startswith("/out/tickets/") for f in (await client.get(f"/api/projects/{p['id']}/files", headers=h)).json())


# ---------------------------------------------------------- sample data ----

async def test_sample_data_is_idempotent_and_tasks_import(client, scripted):
    scripted(PRAISE)
    h = await register(client, "a@example.com")
    p = await _project(client, h, template=None)
    assert p["status"] == "draft" and p["agents_total"] == 0
    r1 = (await client.post(f"/api/projects/{p['id']}/sample-data", headers=h)).json()
    r2 = (await client.post(f"/api/projects/{p['id']}/sample-data", headers=h)).json()
    assert r1 == {"agents": 4, "knowledge": 4, "tasks": 15} and r2 == {"agents": 0, "knowledge": 0, "tasks": 0}
    assert (await client.get(f"/api/projects/{p['id']}", headers=h)).json()["status"] == "active"
    csv = b"id,source,author,text,app_version\nX-1,email,kim,\"App crashes on launch\",2.4.1\n,discord,lee,\"Love it\",\n"
    r = await client.post(f"/api/projects/{p['id']}/tasks/import", files={"file": ("feedback.csv", io.BytesIO(csv), "text/csv")}, headers=h)
    assert r.status_code == 200 and r.json() == {"created": 2, "skipped": 0, "queued": 2}   # auto_run is on by default
    tasks = (await client.get(f"/api/projects/{p['id']}/tasks", headers=h)).json()
    assert len(tasks) == 17 and any(t["external_id"] == "X-1" and t["meta"] == {"app_version": "2.4.1"} for t in tasks)


# ------------------------------------------------------------- files etc ----

async def test_files_memory_knowledge_crud(client, scripted):
    scripted(PRAISE)
    h = await register(client, "a@example.com")
    p = await _project(client, h, template=None)
    r = await client.post(f"/api/projects/{p['id']}/files/upload", files={"files": ("notes.md", io.BytesIO(b"# hello"), "text/markdown")}, data={"folder": "/docs"}, headers=h)
    assert r.status_code == 201
    f = r.json()[0]
    assert f["path"] == "/docs/notes.md"
    assert (await client.get(f"/api/projects/{p['id']}/files/{f['id']}/preview", headers=h)).json()["text"] == "# hello"
    moved = (await client.post(f"/api/projects/{p['id']}/files/{f['id']}/move", json={"new_path": "/architecture/notes.md"}, headers=h)).json()
    assert moved["path"] == "/architecture/notes.md"
    assert (await client.get(f"/api/projects/{p['id']}/files/{f['id']}/content", headers=h)).content == b"# hello"
    assert (await client.delete(f"/api/projects/{p['id']}/files/{f['id']}", headers=h)).status_code == 204
    m = (await client.post(f"/api/projects/{p['id']}/memories", json={"type": "PROJECT_CONTEXT", "content": "Use PostgreSQL.", "pinned": True}, headers=h)).json()
    assert m["id"].startswith("MEM_") and m["pinned"]
    assert (await client.get(f"/api/projects/{p['id']}/memories?q=postgres", headers=h)).json()[0]["id"] == m["id"]
    k = (await client.post(f"/api/projects/{p['id']}/knowledge/text", json={"name": "arch", "text": "The payments service uses Stripe webhooks."}, headers=h)).json()
    items = await _wait_knowledge(client, h, p["id"])
    assert items[0]["id"] == k["id"] and items[0]["status"] == "ready", items
    assert (await client.delete(f"/api/projects/{p['id']}/knowledge/{k['id']}", headers=h)).status_code == 204
    acts = (await client.get(f"/api/projects/{p['id']}/activity?category=FILES", headers=h)).json()
    assert all(a["category"] == "FILE" for a in acts) and acts


async def test_dashboard_and_health(client, scripted):
    scripted(PRAISE)
    h = await register(client, "a@example.com")
    await _project(client, h, "one", template=None)
    d = (await client.get("/api/dashboard", headers=h)).json()
    assert d["metrics"]["total_projects"] == 1 and d["recent_projects"][0]["slug"] == "one"
    hz = (await client.get("/api/system/health", headers=h)).json()
    assert hz["checks"]["database"]["ok"] and "replica" in hz
    assert any(t["name"] == "create_ticket" and t["gated"] for t in (await client.get("/api/system/tools", headers=h)).json())


def test_extract_text_sniffs_pdf_and_strips_nul():
    from api.services.knowledge import clean_text, detect_kind, extract_text
    from pypdf import PdfWriter
    import io as _io
    w = PdfWriter(); w.add_blank_page(width=72, height=72)
    buf = _io.BytesIO(); w.write(buf); pdf = buf.getvalue()
    assert detect_kind("resume", pdf) == "pdf"
    assert "\x00" not in extract_text("document", "Resume.pdf", pdf)          # declared 'document', still parsed as PDF
    assert clean_text("a\x00b\x01c") == "abc"
    with pytest.raises(ValueError):
        extract_text("document", "blob.bin", bytes(range(256)) * 4)


async def test_integrations_catalog_secrets_and_webhook_delivery(client, scripted, monkeypatch):
    """Secrets are encrypted at rest and masked on read; a signed webhook is delivered on ticket.created."""
    import hashlib, hmac, json as _json
    from api.integrations import adapters as svc
    scripted(PRAISE)
    h = await register(client, "a@example.com")
    p = await _project(client, h, template=None)
    cat = (await client.get(f"/api/projects/{p['id']}/integrations", headers=h)).json()
    assert {c["provider"] for c in cat} >= {"github", "jira", "linear", "slack", "discord", "email", "webhook", "sentry", "gdrive", "custom"}
    assert all(c["steps"] and c["how_it_works"] for c in cat)
    r = await client.put(f"/api/projects/{p['id']}/integrations/webhook", json={"status": "connected", "config": {"url": "https://hooks.example.com/x", "secret": "topsecret", "events": ""}}, headers=h)
    assert r.status_code == 200 and r.json()["config"]["secret"] != "topsecret" and "topsecret" not in r.text
    from api.models import Integration
    from api.core.db import SessionLocal
    from sqlalchemy import select
    async with SessionLocal() as s:
        row = (await s.execute(select(Integration).where(Integration.project_id == p["id"]))).scalar_one()
        assert row.config["secret"].startswith("enc:")
    sent = {}
    class FakeResp:
        status_code = 200
        def raise_for_status(self): pass
    class FakeClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def post(self, url, content=None, headers=None, **k): sent.update(url=url, body=content, headers=headers); return FakeResp()
    monkeypatch.setattr(svc.httpx, "AsyncClient", FakeClient)
    from api.models import Project
    async with SessionLocal() as s:
        proj = await s.get(Project, p["id"])
        await svc._deliver(p["id"], "ticket.created", {"ticket": {"id": "OR-1", "title": "t", "severity": "high", "component": "c"}})
    assert sent["headers"]["X-Triage-Event"] == "ticket.created"
    expected = "sha256=" + hmac.new(b"topsecret", sent["body"], hashlib.sha256).hexdigest()
    assert sent["headers"]["X-Triage-Signature"] == expected
    assert _json.loads(sent["body"])["project"]["slug"] == proj.slug
    acts = (await client.get(f"/api/projects/{p['id']}/activity", headers=h)).json()
    assert any("WEBHOOK delivered" in a["message"] for a in acts)


async def test_auto_run_and_intake_endpoint(client, scripted):
    scripted(PRAISE)
    h = await register(client, "a@example.com")
    p = await _project(client, h, template=None)
    await client.post(f"/api/projects/{p['id']}/sample-data?knowledge_items=false&tasks=false", headers=h)
    # auto_run default on: creating a task queues a run
    t = (await client.post(f"/api/projects/{p['id']}/tasks", json={"text": "Great game!", "external_id": "FB-500"}, headers=h)).json()
    assert t["status"] == "queued" and t["last_run_id"] is not None
    run = await _wait_run(client, h, p["id"], t["last_run_id"])
    assert run["status"] == "complete"
    # switch off, create again: no run
    await client.patch(f"/api/projects/{p['id']}", json={"config": {"auto_run": False}}, headers=h)
    t2 = (await client.post(f"/api/projects/{p['id']}/tasks", json={"text": "Also great", "external_id": "FB-501"}, headers=h)).json()
    assert t2["last_run_id"] is None
    # intake key: 401 without, works with, hash never leaks
    assert (await client.post(f"/api/intake/{p['id']}", json={"text": "x"})).status_code == 401
    key = (await client.post(f"/api/projects/{p['id']}/intake-key", headers=h)).json()["key"]
    assert "intake_key_hash" not in (await client.get(f"/api/projects/{p['id']}", headers=h)).json()["config"]
    await client.patch(f"/api/projects/{p['id']}", json={"config": {"auto_run": True}}, headers=h)
    r = await client.post(f"/api/intake/{p['id']}", json={"items": [{"id": "APP-1", "source": "app_store", "text": "Crashes on launch", "metadata": {"app_version": "2.4.1"}}, {"text": ""}]}, headers={"X-Intake-Key": key})
    assert r.status_code == 200 and r.json()["created"] == ["APP-1"] and r.json()["skipped"] == 1 and len(r.json()["queued"]) == 1
    assert (await client.post(f"/api/intake/{p['id']}", json={"text": "x"}, headers={"X-Intake-Key": "tik_wrong"})).status_code == 401
    assert (await client.delete(f"/api/projects/{p['id']}/intake-key", headers=h)).status_code == 204
    assert (await client.post(f"/api/intake/{p['id']}", json={"text": "x"}, headers={"X-Intake-Key": key})).status_code == 401


async def test_outputs_page_lists_approved_ticket(client, scripted):
    scripted(NEW_HIGH_BUG)
    h = await register(client, "a@example.com")
    p = await _project(client, h)
    await _wait_knowledge(client, h, p["id"])
    task = next(x for x in (await client.get(f"/api/projects/{p['id']}/tasks", headers=h)).json() if x["external_id"] == "FB-014")
    run_id = (await client.post(f"/api/projects/{p['id']}/tasks/{task['id']}/run", headers=h)).json()["run_id"]
    await _wait_run(client, h, p["id"], run_id, until=("waiting_approval",))
    aid = (await client.get(f"/api/projects/{p['id']}/approvals?status=pending", headers=h)).json()[0]["id"]
    await client.post(f"/api/projects/{p['id']}/approvals/{aid}/approve", headers=h)
    run = await _wait_run(client, h, p["id"], run_id)
    tid = run["result"]["ticket_id"]
    tickets = (await client.get(f"/api/projects/{p['id']}/outputs?kind=tickets", headers=h)).json()
    assert [t["id"] for t in tickets] == [tid] and tickets[0]["approved_by"] == "human" and tickets[0]["run_id"] == run_id
    one = (await client.get(f"/api/projects/{p['id']}/outputs/tickets/{tid}", headers=h)).json()
    assert one["data"]["severity"] == "high" and one["markdown"].startswith(f"# {tid}")
    assert (await client.get(f"/api/projects/{p['id']}/outputs/counts", headers=h)).json()["tickets"] == 1
    resolved = (await client.get(f"/api/projects/{p['id']}/approvals?status=approved", headers=h)).json()
    assert resolved[0]["ticket_id"] == tid


async def test_parked_run_lets_next_task_start(client, scripted):
    """Run 1 stops at the gate; run 2 (auto-approved) must complete while run 1 is still waiting; then run 1 resumes."""
    scripted(NEW_HIGH_BUG)
    h = await register(client, "a@example.com")
    p = await _project(client, h)
    await _wait_knowledge(client, h, p["id"])
    tasks = {t["external_id"]: t for t in (await client.get(f"/api/projects/{p['id']}/tasks", headers=h)).json()}
    r1 = (await client.post(f"/api/projects/{p['id']}/tasks/{tasks['FB-014']['id']}/run", headers=h)).json()["run_id"]
    await _wait_run(client, h, p["id"], r1, until=("waiting_approval",))
    r2 = (await client.post(f"/api/projects/{p['id']}/tasks/{tasks['FB-010']['id']}/run?auto_approve=true", headers=h)).json()["run_id"]
    run2 = await _wait_run(client, h, p["id"], r2)
    assert run2["status"] == "complete", run2
    assert (await client.get(f"/api/projects/{p['id']}/runs/{r1}", headers=h)).json()["status"] == "waiting_approval"
    aid = (await client.get(f"/api/projects/{p['id']}/approvals?status=pending", headers=h)).json()[0]["id"]
    await client.post(f"/api/projects/{p['id']}/approvals/{aid}/approve", headers=h)
    run1 = await _wait_run(client, h, p["id"], r1)
    assert run1["status"] == "complete" and run1["result"]["outcome"] == "new_ticket"
    ids = {t["id"] for t in (await client.get(f"/api/projects/{p['id']}/outputs?kind=tickets", headers=h)).json()}
    assert len(ids) == 2


async def test_approval_survives_worker_loss_and_reruns(client, scripted):
    """Run dies while parked (simulated); approval stays pending; approving re-runs the task with the decision."""
    from api.services.runs import run_service
    from api.core.db import SessionLocal
    from api.models import Run
    scripted(NEW_HIGH_BUG)
    h = await register(client, "a@example.com")
    p = await _project(client, h)
    await _wait_knowledge(client, h, p["id"])
    task = next(x for x in (await client.get(f"/api/projects/{p['id']}/tasks", headers=h)).json() if x["external_id"] == "FB-014")
    r1 = (await client.post(f"/api/projects/{p['id']}/tasks/{task['id']}/run", headers=h)).json()["run_id"]
    await _wait_run(client, h, p["id"], r1, until=("waiting_approval",))
    # simulate the replica dying: cancel its wait and mark the run interrupted, approval stays pending
    run_service.cancel_local = getattr(run_service, "cancel_local", None)
    async with SessionLocal() as s:
        run = await s.get(Run, r1); run.status, run.error = "error", "interrupted while awaiting approval"; await s.commit()
    fut = run_service._pending.get((await client.get(f"/api/projects/{p['id']}/approvals?status=pending", headers=h)).json()[0]["id"])
    aid = (await client.get(f"/api/projects/{p['id']}/approvals?status=pending", headers=h)).json()[0]["id"]
    r = await client.post(f"/api/projects/{p['id']}/approvals/{aid}/modify", json={"severity": "critical"}, headers=h)
    assert r.status_code == 200 and r.json()["response"].get("rerun_id")
    if fut and not fut.done():
        fut.set_result("n")   # the dead attempt's coroutine, if still around, must not create anything
    rerun = await _wait_run(client, h, p["id"], r.json()["response"]["rerun_id"])
    assert rerun["status"] == "complete" and rerun["result"]["outcome"] == "new_ticket" and rerun["result"]["severity"] == "critical"
    assert rerun["approval_state"] == "modified"
    tickets = (await client.get(f"/api/projects/{p['id']}/outputs?kind=tickets", headers=h)).json()
    assert len(tickets) == 1 and tickets[0]["severity"] == "critical"
    kinds = [e["message"] for e in (await client.get(f"/api/projects/{p['id']}/runs/{rerun['id']}/events", headers=h)).json() if e["kind"] == "APPROVAL"]
    assert any("carried over" in m for m in kinds)


async def test_inbound_push_providers(client, scripted):
    """Slack (challenge + signed event), GitHub (HMAC), Jira (token), generic webhook (signed) all create tasks; bad auth is rejected."""
    import hashlib, hmac, json as _json, time as _time
    scripted(PRAISE)
    h = await register(client, "a@example.com")
    p = await _project(client, h, template=None)
    await client.post(f"/api/projects/{p['id']}/sample-data?knowledge_items=false&tasks=false", headers=h)
    await client.patch(f"/api/projects/{p['id']}", json={"config": {"auto_run": False}}, headers=h)

    # --- slack
    r = await client.put(f"/api/projects/{p['id']}/integrations/slack", json={"status": "connected", "config": {"webhook_url": "https://hooks.slack.com/x", "signing_secret": "s3cr3t", "intake_channel": "C123"}}, headers=h)
    assert r.status_code == 200
    cat = {c["provider"]: c for c in (await client.get(f"/api/projects/{p['id']}/integrations", headers=h)).json()}
    assert cat["slack"]["inbound"]["url"].endswith(f"/api/inbound/slack/{p['id']}") and cat["slack"]["inbound"]["mode"] == "push"
    url = f"/api/inbound/slack/{p['id']}"
    def slack_sign(body: bytes):
        ts = str(int(_time.time()))
        return {"x-slack-request-timestamp": ts, "x-slack-signature": "v0=" + hmac.new(b"s3cr3t", f"v0:{ts}:".encode() + body, hashlib.sha256).hexdigest(), "content-type": "application/json"}
    body = _json.dumps({"type": "url_verification", "challenge": "abc"}).encode()
    r = await client.post(url, content=body, headers=slack_sign(body))
    assert r.status_code == 200 and r.json() == {"challenge": "abc"}
    ev = _json.dumps({"type": "event_callback", "team_id": "T1", "event": {"type": "message", "channel": "C123", "user": "U42", "text": "shop crashes on open, pixel 8, 2.4.1", "ts": "1726650000.000100"}}).encode()
    assert (await client.post(url, content=ev, headers={**slack_sign(ev), "x-slack-signature": "v0=bad"})).status_code == 401
    r = await client.post(url, content=ev, headers=slack_sign(ev))
    assert r.status_code == 200 and r.json()["created"] == ["SL-0000000100"]
    r = await client.post(url, content=ev, headers=slack_sign(ev))          # redelivery → skipped
    assert r.json()["skipped"] == 1 and r.json()["created"] == []
    other = _json.dumps({"type": "event_callback", "event": {"type": "message", "channel": "C999", "user": "U1", "text": "ignore me", "ts": "1.2"}}).encode()
    assert (await client.post(url, content=other, headers=slack_sign(other))).json() == {"ok": True}
    assert (await client.get(f"/api/projects/{p['id']}/integrations", headers=h)).json() and {c["provider"]: c for c in (await client.get(f"/api/projects/{p['id']}/integrations", headers=h)).json()}["slack"]["inbound"]["verified"]

    # --- github
    await client.put(f"/api/projects/{p['id']}/integrations/github", json={"status": "connected", "config": {"repository": "acme/app", "token": "ghp_x", "webhook_secret": "ghs", "intake_label": "triage"}}, headers=h)
    gh = _json.dumps({"action": "opened", "issue": {"number": 7, "title": "Crash on launch", "body": "steps…", "html_url": "https://github.com/acme/app/issues/7", "user": {"login": "kim"}, "labels": [{"name": "triage"}], "created_at": "2026-09-18T10:00:00Z"}, "repository": {"full_name": "acme/app"}}).encode()
    sig = "sha256=" + hmac.new(b"ghs", gh, hashlib.sha256).hexdigest()
    assert (await client.post(f"/api/inbound/github/{p['id']}", content=gh, headers={"x-hub-signature-256": "sha256=nope", "content-type": "application/json"})).status_code == 401
    r = await client.post(f"/api/inbound/github/{p['id']}", content=gh, headers={"x-hub-signature-256": sig, "content-type": "application/json"})
    assert r.status_code == 200 and r.json()["created"] == ["GH-7"]
    unl = _json.dumps({"action": "opened", "issue": {"number": 8, "title": "no label", "body": "", "labels": [], "user": {}}, "repository": {}}).encode()
    assert (await client.post(f"/api/inbound/github/{p['id']}", content=unl, headers={"x-hub-signature-256": "sha256=" + hmac.new(b"ghs", unl, hashlib.sha256).hexdigest(), "content-type": "application/json"})).json() == {"ok": True}

    # --- jira (token in URL)
    await client.put(f"/api/projects/{p['id']}/integrations/jira", json={"status": "connected", "config": {"site_url": "https://acme.atlassian.net", "project_key": "PAY", "email": "a@b.c", "api_token": "t"}}, headers=h)
    cat = {c["provider"]: c for c in (await client.get(f"/api/projects/{p['id']}/integrations", headers=h)).json()}
    jurl = cat["jira"]["inbound"]["url"]
    assert "?token=" in jurl
    jira_ev = {"webhookEvent": "jira:issue_created", "issue": {"key": "PAY-42", "fields": {"summary": "VAT rounding", "description": {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "off by a cent"}]}]}, "reporter": {"displayName": "Lee"}, "created": "2026-09-18T10:00:00Z", "issuetype": {"name": "Bug"}}}}
    assert (await client.post(jurl.replace("http://localhost:8000", "") + "wrong", json=jira_ev)).status_code == 401
    r = await client.post(jurl.replace("http://localhost:8000", ""), json=jira_ev)
    assert r.status_code == 200 and r.json()["created"] == ["PAY-42"]
    t = next(x for x in (await client.get(f"/api/projects/{p['id']}/tasks", headers=h)).json() if x["external_id"] == "PAY-42")
    assert "off by a cent" in t["text"] and t["meta"]["url"] == "https://acme.atlassian.net/browse/PAY-42"

    # --- generic webhook, signed
    await client.put(f"/api/projects/{p['id']}/integrations/webhook", json={"status": "connected", "config": {"url": "https://example.com/out", "inbound_secret": "inb"}}, headers=h)
    wb = _json.dumps({"items": [{"id": "Z-1", "source": "zapier", "text": "Lost progress after update", "metadata": {"app_version": "2.4.1"}}, {"text": ""}]}).encode()
    r = await client.post(f"/api/inbound/webhook/{p['id']}", content=wb, headers={"x-triage-signature": "sha256=" + hmac.new(b"inb", wb, hashlib.sha256).hexdigest(), "content-type": "application/json"})
    assert r.status_code == 200 and r.json()["created"] == ["Z-1"] and r.json()["skipped"] == 1
    assert (await client.post(f"/api/inbound/webhook/{p['id']}", content=wb, headers={"content-type": "application/json"})).status_code == 401
    # not connected provider → 401
    assert (await client.post(f"/api/inbound/linear/{p['id']}", json={})).status_code == 401
    # counts
    cat = {c["provider"]: c for c in (await client.get(f"/api/projects/{p['id']}/integrations", headers=h)).json()}
    assert cat["slack"]["inbound"]["count"] == 1 and cat["github"]["inbound"]["count"] == 1 and cat["webhook"]["inbound"]["count"] == 1


async def test_pull_sync_scheduler(client, scripted, monkeypatch):
    """A pull provider is polled by the scheduler with a cursor; items become tasks; knowledge items are upserted."""
    from api.integrations import pollers
    from api.services.sync import sync_scheduler
    scripted(PRAISE)
    h = await register(client, "a@example.com")
    p = await _project(client, h, template=None)
    await client.post(f"/api/projects/{p['id']}/sample-data?knowledge_items=false&tasks=false", headers=h)
    await client.patch(f"/api/projects/{p['id']}", json={"config": {"auto_run": False}}, headers=h)
    calls = []
    async def fake_discord(cfg, cursor):
        calls.append(dict(cursor))
        if not cursor.get("after"):
            return [], {"after": "100"}, "cursor initialised"
        return [{"id": "DC-101", "source": "discord", "author": "mo", "text": "crash when opening shop", "metadata": {}},
                {"kind": "knowledge", "name": "synced-notes.md", "type": "markdown", "data": b"# notes\nshop crash known"}], {"after": "101"}, "1 new message(s)"
    monkeypatch.setitem(pollers.POLLERS, "discord", fake_discord)
    r = await client.put(f"/api/projects/{p['id']}/integrations/discord", json={"status": "connected", "config": {"webhook_url": "https://discord.com/api/webhooks/x", "bot_token": "b", "intake_channel_id": "1"}}, headers=h)
    assert r.status_code == 200
    r1 = (await client.post(f"/api/projects/{p['id']}/integrations/discord/sync", headers=h)).json()["result"]
    assert "cursor initialised" in r1
    r2 = (await client.post(f"/api/projects/{p['id']}/integrations/discord/sync", headers=h)).json()["result"]
    assert "1 new message" in r2 and "1 task(s)" in r2 and calls[1] == {"after": "100"}
    tasks = (await client.get(f"/api/projects/{p['id']}/tasks", headers=h)).json()
    assert any(t["external_id"] == "DC-101" and t["source"] == "discord" for t in tasks)
    items = await _wait_knowledge(client, h, p["id"])
    assert any(k["name"] == "synced-notes.md" and k["status"] == "ready" for k in items)
    cat = {c["provider"]: c for c in (await client.get(f"/api/projects/{p['id']}/integrations", headers=h)).json()}
    assert cat["discord"]["inbound"]["count"] == 1 and cat["discord"]["inbound"]["next_sync_at"]
    # the scheduler claims due rows itself
    from api.core.db import SessionLocal
    from api.models import Integration
    from sqlalchemy import update
    async with SessionLocal() as s:
        await s.execute(update(Integration).where(Integration.project_id == p["id"]).values(next_sync_at=now_utc()))
        await s.commit()
    # either the background loop or a manual claim runs it; wait for the effect
    before = cat["discord"]["inbound"]["last_sync_at"]
    claimed = await sync_scheduler._claim()
    if claimed:
        await sync_scheduler.run_sync(claimed)
    for _ in range(40):
        cat = {c["provider"]: c for c in (await client.get(f"/api/projects/{p['id']}/integrations", headers=h)).json()}
        if cat["discord"]["inbound"]["last_sync_at"] != before:
            break
        await asyncio.sleep(0.25)
    assert cat["discord"]["inbound"]["last_sync_at"] != before and "1 new message" in cat["discord"]["inbound"]["last_sync_result"]
    # push-only providers refuse SYNC NOW
    await client.put(f"/api/projects/{p['id']}/integrations/slack", json={"status": "connected", "config": {"webhook_url": "https://hooks.slack.com/x", "signing_secret": "s"}}, headers=h)
    assert (await client.post(f"/api/projects/{p['id']}/integrations/slack/sync", headers=h)).status_code == 409


def now_utc():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)
