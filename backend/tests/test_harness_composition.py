import asyncio
import json
import socket
import threading
import time

import pytest
import uvicorn
from sqlalchemy import select

from app.api import create_app
from app.contracts import ControlInput, ProbeInput, RevisionInput
from app.domain import Attempt, Invocation, Project, Request, Task, TaskResult
from app.runtime.port import HarnessPort
from app.settings import ROOT


@pytest.fixture
def local_api(business):
    app = create_app(business.store.settings)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    url = f"http://127.0.0.1:{sock.getsockname()[1]}"
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", access_log=False))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    deadline = time.time() + 5
    while not server.started and time.time() < deadline:
        time.sleep(0.01)
    assert server.started
    yield url
    server.should_exit = True
    thread.join(5)
    sock.close()
    assert not thread.is_alive()


def evidence(b, inv, label):
    import shutil
    root = ROOT / "evals/results/stage1" / (label + "-" + inv["attempt_id"][:8])
    source = b.store.settings.data_dir / "attempts" / inv["attempt_id"]
    shutil.copytree(source, root, ignore=shutil.ignore_patterns("session.lock"))
    with b.store.tx() as s:
        requests = s.scalars(select(Request)).all()
        tasks = s.scalars(select(Task)).all()
        value = {"label": label, "requests": [{"id": r.id, "status": r.status, "actual": r.actual,
                    "reservation": r.reservation} for r in requests],
                 "task_statuses": [t.status for t in tasks], "L3": "not_run", "L4": "not_run"}
    (root / "result.json").write_text(json.dumps(value, indent=2))
    return root


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario,accepted,count", [
    ("normal", True, 4), ("retry", True, 5), ("bad_reference", False, 4),
    ("forbidden_tool", False, 3), ("after_finish", True, 5),
])
async def test_actual_sdk_plugin_loop_and_wire(prepared, local_api, scenario, accepted, count):
    b, _, _, run = prepared
    with b.store.tx() as s:
        task = s.get(Task, run["task_id"])
        task.contract = {**task.contract, "scenario": scenario}
        from app.storage import digest
        task.input_hash = digest(task.contract)
    inv = b.claim("composition")
    port = HarnessPort(b, local_api)
    outcome = await port.execute(inv)
    b.complete(inv["attempt_id"], outcome.status, outcome.error)
    root = evidence(b, inv, scenario)
    assert outcome.exit_code == 0, (root / "stderr.log").read_text()
    wire = [json.loads(line) for line in (root / "wire.jsonl").read_text().splitlines()]
    assert len(wire) == count
    with b.store.tx() as s:
        result = s.get(TaskResult, run["task_id"])
        assert (result is not None) == accepted
        requests = s.scalars(select(Request)).all()
        assert len(requests) == len(wire)
        assert {r.id for r in requests} == {r["request_id"] for r in wire}
        if scenario == "retry":
            assert sum(r.status == "unknown" for r in requests) == 1
    for row in wire:
        assert not {"dsh_session_log", "dsh_plugin_packages"} & row["body"].keys()
        assert {t["name"] for t in row["body"]["tools"]} == {"read_sources", "save_candidate", "finish_candidate"}
    text = (root / "events.jsonl").read_text()
    if scenario == "forbidden_tool":
        assert '"isError": true' in text and 'bash' in text
    if scenario == "after_finish":
        rows = [json.loads(line) for line in text.splitlines()]
        results = [r["payload"]["event"]["data"]["message"] for r in rows
                   if r["method"] == "session.event" and r["payload"]["event"]["type"] == "tool/result"]
        late = next(r for r in results if r["toolCallId"] == "late-read")
        assert late["isError"] is True
        assert "only permits the assigned business tools" in late["content"][0]["text"]
        with b.store.tx() as s:
            assert len(s.scalars(select(Invocation)).all()) == 3
    with b.store.tx() as s:
        assert s.get(Attempt, inv["attempt_id"]).session_id is not None


@pytest.mark.asyncio
async def test_actual_budget_denial_prevents_second_http(prepared, local_api):
    b, p, _, run = prepared
    with b.store.tx() as s:
        s.get(Project, p["id"]).max_requests = 1
    inv = b.claim("budget")
    outcome = await HarnessPort(b, local_api).execute(inv)
    b.complete(inv["attempt_id"], outcome.status, outcome.error)
    root = evidence(b, inv, "budget")
    assert len((root / "wire.jsonl").read_text().splitlines()) == 1
    assert "BUDGET_EXHAUSTED" in (root / "events.jsonl").read_text()
    with b.store.tx() as s:
        assert s.get(TaskResult, run["task_id"]) is None
        assert len(s.scalars(select(Request)).all()) == 1


@pytest.mark.asyncio
async def test_actual_cancel_stops_process_and_rejects_late_result(prepared, local_api):
    b, p, _, run = prepared
    with b.store.tx() as s:
        task = s.get(Task, run["task_id"])
        task.contract = {**task.contract, "scenario": "slow"}
        from app.storage import digest
        task.input_hash = digest(task.contract)
    inv = b.claim("cancel")
    port = HarnessPort(b, local_api)
    activity = asyncio.create_task(port.execute(inv))
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        await asyncio.sleep(.05)
        with b.store.tx() as s:
            if s.scalar(select(Request)):
                break
    start = time.monotonic()
    b.control(p["id"], run["id"], ControlInput(request_id="cancel", expected_revision=1, action="cancel"))
    outcome = await asyncio.wait_for(activity, timeout=7)
    b.complete(inv["attempt_id"], outcome.status, outcome.error)
    root = evidence(b, inv, "cancel")
    assert time.monotonic() - start < 7
    assert port.processes == {}
    with b.store.tx() as s:
        assert s.get(TaskResult, run["task_id"]) is None
        assert s.get(Task, run["task_id"]).status == "cancelled"
        assert all(r.status in {"unknown", "settled"} for r in s.scalars(select(Request)))
    assert len((root / "wire.jsonl").read_text().splitlines()) == 1


@pytest.mark.asyncio
async def test_actual_new_session_handoff_preserves_pending_and_lock(prepared, local_api):
    from app.storage import digest
    b, p, ref, _ = prepared
    decision = b.save_revision(p["id"], RevisionInput(request_id="pending", logical_id="pending",
        kind="decision", actor="human", reason="合成待核", payload={"status": "unverified", "text": "自动迁移待核"}))
    block = {"block_id": "protected", "text": "未经批准不得增加承诺"}
    draft = b.save_revision(p["id"], RevisionInput(request_id="draft", logical_id="draft", kind="draft",
        actor="human", reason="合成人工稿", payload={"blocks": [block]}))
    lock = b.save_revision(p["id"], RevisionInput(request_id="lock", logical_id="lock", kind="lock",
        actor="human", reason="合成锁定", payload={"logical_id": "draft", "draft_revision": draft["id"],
                                                    "hashes": {"protected": digest(block)}}))
    run = b.create_probe(p["id"], ProbeInput(request_id="handoff", expected_generation=lock["generation"],
                                             source_ids=[ref["id"]], scenario="handoff"))
    first = b.claim("session-one")
    port = HarnessPort(b, local_api)
    outcome = await port.execute(first)
    b.complete(first["attempt_id"], outcome.status, outcome.error)
    evidence(b, first, "handoff-first")
    b.control(p["id"], run["id"], ControlInput(request_id="resume", expected_revision=1, action="resume"))
    second = b.claim("session-two")
    assert second["epoch"] == 2
    outcome = await port.execute(second)
    b.complete(second["attempt_id"], outcome.status, outcome.error)
    root = evidence(b, second, "handoff")
    context = json.loads((root / "context.json").read_text())
    assert context["pending"] == [decision["id"]]
    assert context["budget_family"] == run["family_id"]
    assert len(context["prior_requests"]) == 3
    assert any(r["kind"] == "lock" and r["payload"]["hashes"]["protected"] == digest(block)
               for r in context["authority"])
    with b.store.tx() as s:
        assert s.get(TaskResult, run["task_id"]) is not None
        assert s.get(Attempt, first["attempt_id"]).session_id != s.get(Attempt, second["attempt_id"]).session_id
