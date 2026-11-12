import concurrent.futures

import pytest
from sqlalchemy import select

from app.contracts import Admission, ControlInput, ProbeInput, ProjectInput, RevisionInput, Settlement, ToolCall
from app.domain import Attempt, Candidate, Event, Head, Project, Receipt, Request, Task, TaskResult
from app.services import DomainError
from app.storage import digest


def failure(code, fn):
    with pytest.raises(DomainError, match=code):
        fn()


def payload(ref):
    return {"kind": "engineering_probe", "blocks": [{"block_id": "b1", "text": "工程候选"}],
            "source_refs": [ref], "coverage_ids": [ref]}


def tool(b, inv, name, args, key=None):
    return b.tool(inv["token"], ToolCall(request_id=key or name, tool=name, arguments=args))


def finish(b, inv, ref):
    saved = tool(b, inv, "save_candidate", {"candidate": payload(ref)})
    tool(b, inv, "finish_candidate", saved)
    return saved


def wire(b, inv):
    import json
    return {"model": "bid-fixture", "messages": [{"role": "user", "content": [
        {"type": "text", "text": json.dumps(b.manifest(inv["token"]), ensure_ascii=False)}]}]}


def test_cross_project_read_and_token_identity(prepared):
    b, p, ref, _ = prepared
    inv = b.claim("one")
    other = b.create_project(ProjectInput(name="other", customer="other", enterprise="other"))
    foreign = b.save_revision(other["id"], RevisionInput(request_id="foreign", logical_id="s", kind="source",
                    payload={"synthetic": True, "text": "私有资料"}, actor="tester", reason="fixture"))
    failure("SCOPE_DENIED", lambda: tool(b, inv, "read_sources", {"source_ids": [foreign["id"]]}))
    failure("TASK_TOKEN_DENIED", lambda: b.manifest("invalid"))
    assert tool(b, inv, "read_sources", {"source_ids": [ref["id"]]})["sources"][0]["id"] == ref["id"]


def test_single_worker_lease_across_concurrent_claims(prepared):
    b, *_ = prepared
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(b.claim, ["one", "two", "three", "four"]))
    assert sum(r is not None for r in results) == 1


def test_task_and_action_idempotency(prepared):
    b, p, ref, run = prepared
    request = ProbeInput(request_id="run", expected_generation=ref["generation"], source_ids=[ref["id"]])
    assert b.create_probe(p["id"], request) == run
    request.scenario = "retry"
    failure("IDEMPOTENCY_CONFLICT", lambda: b.create_probe(p["id"], request))


def test_tool_idempotency_and_payload_conflict(prepared):
    b, _, ref, _ = prepared
    inv = b.claim("one")
    args = {"candidate": payload(ref["id"])}
    first = tool(b, inv, "save_candidate", args, "same")
    assert first == tool(b, inv, "save_candidate", args, "same")
    args["candidate"]["blocks"][0]["text"] = "different"
    failure("IDEMPOTENCY_CONFLICT", lambda: tool(b, inv, "save_candidate", args, "same"))
    with b.store.tx() as s:
        assert len(s.scalars(select(Candidate)).all()) == 1


def test_cancel_revokes_sends_tools_and_late_commit(prepared):
    b, p, ref, run = prepared
    inv = b.claim("one")
    finish(b, inv, ref["id"])
    b.control(p["id"], run["id"], ControlInput(request_id="cancel", expected_revision=1, action="cancel"))
    failure("CANCELLED", lambda: b.manifest(inv["token"]))
    b.complete(inv["attempt_id"], "completed")
    with b.store.tx() as s:
        assert s.get(TaskResult, inv["task_id"]) is None
        assert s.get(Task, inv["task_id"]).status == "cancelled"


def test_manual_edit_invalidates_and_preserves_late_candidate(prepared):
    b, p, ref, _ = prepared
    inv = b.claim("one")
    candidate = finish(b, inv, ref["id"])
    b.save_revision(p["id"], RevisionInput(request_id="manual", logical_id="draft", kind="draft",
        actor="human", reason="人工改稿", payload={"blocks": [{"block_id": "b1", "text": "人工正文"}]}))
    b.complete(inv["attempt_id"], "completed")
    with b.store.tx() as s:
        assert s.get(Candidate, candidate["candidate_id"]).status == "stale"
        assert s.get(TaskResult, inv["task_id"]) is None
        head = s.scalar(select(Head).where(Head.logical_id == "draft"))
        assert s.get(__import__('app.domain', fromlist=['Revision']).Revision, head.revision_id).actor == "human"


def test_resume_after_committed_result_never_replays(prepared):
    b, _, ref, _ = prepared
    inv = b.claim("one")
    finish(b, inv, ref["id"])
    b.complete(inv["attempt_id"], "completed")
    with b.store.tx() as s:
        task = s.get(Task, inv["task_id"])
        task.status, task.lease_until = "running", 0
    assert b.claim("two") is None
    with b.store.tx() as s:
        assert len(s.scalars(select(TaskResult)).all()) == 1
        assert len(s.scalars(select(Event).where(Event.kind == "task.committed")).all()) == 1
        assert len(s.scalars(select(Attempt)).all()) == 1


def test_recover_finished_candidate_without_repeating_generation(prepared):
    b, _, ref, _ = prepared
    inv = b.claim("one")
    finish(b, inv, ref["id"])
    with b.store.tx() as s:
        s.get(Task, inv["task_id"]).lease_until = 0
    assert b.claim("two") is None
    with b.store.tx() as s:
        assert s.get(TaskResult, inv["task_id"]) is not None
        assert len(s.scalars(select(Attempt)).all()) == 1


def test_expired_lease_cannot_write_and_does_not_auto_replay(prepared):
    b, *_ = prepared
    inv = b.claim("one")
    with b.store.tx() as s:
        s.get(Task, inv["task_id"]).lease_until = 0
    failure("LEASE_LOST", lambda: b.manifest(inv["token"]))
    assert b.claim("two") is None
    with b.store.tx() as s:
        assert s.get(Task, inv["task_id"]).status == "waiting_input"


def test_fake_references_and_semantic_unrun(prepared):
    b, _, ref, _ = prepared
    inv = b.claim("one")
    finish(b, inv, "not-a-source")
    b.complete(inv["attempt_id"], "completed")
    with b.store.tx() as s:
        assert s.get(TaskResult, inv["task_id"]) is None
        receipts = s.scalars(select(Receipt)).all()
        assert {r.layer: r.status for r in receipts} == {"program": "failed", "semantic": "not_run", "human": "not_run"}


def test_hidden_tool_direct_call_denied(prepared):
    b, *_ = prepared
    inv = b.claim("one")
    for name in ["bash", "run_code", "confirm_fact", "release", "plugin_install", "/goal"]:
        failure("ACTION_NOT_ALLOWED", lambda: tool(b, inv, name, {}))


def test_hash_tampering_never_commits(prepared):
    b, _, ref, _ = prepared
    inv = b.claim("one")
    candidate = finish(b, inv, ref["id"])
    (b.store.blobs / candidate["blob_hash"]).write_bytes(b"corrupt fixture")
    b.complete(inv["attempt_id"], "completed")
    with b.store.tx() as s:
        assert s.get(TaskResult, inv["task_id"]) is None


def test_immutable_upload_and_compare_exchange(prepared):
    b, p, ref, _ = prepared
    same = RevisionInput(request_id="again", logical_id="source-1", kind="source", expected_revision=ref["id"],
        payload={"synthetic": True, "text": "new version"}, actor="tester", reason="new")
    new = b.save_revision(p["id"], same)
    same.request_id = "conflict"
    failure("REVISION_CONFLICT", lambda: b.save_revision(p["id"], same))
    assert new["id"] != ref["id"]


def test_pause_revokes_admission_and_resume_keeps_family(prepared):
    b, p, ref, run = prepared
    inv = b.claim("one")
    b.control(p["id"], run["id"], ControlInput(request_id="pause", expected_revision=1, action="pause"))
    failure("PAUSED", lambda: b.manifest(inv["token"]))
    b.complete(inv["attempt_id"], "stopped")
    b.control(p["id"], run["id"], ControlInput(request_id="resume", expected_revision=2, action="resume"))
    other = b.claim("two")
    with b.store.tx() as s:
        assert s.get(Task, other["task_id"]).family_id == run["family_id"]


def test_lock_protects_manual_blocks(prepared):
    b, p, *_ = prepared
    blocks = [{"block_id": "a", "text": "人工锁定"}]
    draft = b.save_revision(p["id"], RevisionInput(request_id="draft", logical_id="draft", kind="draft",
                       actor="human", reason="manual", payload={"blocks": blocks}))
    b.save_revision(p["id"], RevisionInput(request_id="lock", logical_id="lock", kind="lock", actor="human",
        reason="protect", payload={"logical_id": "draft", "draft_revision": draft["id"],
                                    "hashes": {"a": digest(blocks[0])}}))
    failure("LOCK_CONFLICT", lambda: b.save_revision(p["id"], RevisionInput(request_id="bad", logical_id="draft",
        kind="draft", expected_revision=draft["id"], actor="human", reason="edit",
        payload={"blocks": [{"block_id": "a", "text": "覆盖"}]})))


def test_admission_unknown_and_cancellation_settlement(prepared):
    b, p, ref, run = prepared
    inv = b.claim("one")
    data = Admission(request_id="http1", payload=wire(b, inv))
    assert b.admission(inv["token"], data)["permitted"]
    failure("REQUEST_ALREADY_ADMITTED", lambda: b.admission(inv["token"], data))
    b.control(p["id"], run["id"], ControlInput(request_id="cancel", expected_revision=1, action="cancel"))
    assert b.settle(inv["token"], Settlement(request_id="http1"))["status"] == "unknown"
    with b.store.tx() as s:
        assert s.get(Request, "http1").actual is None
        assert s.get(Request, "http1").reservation == 100


def test_project_budget_atomic_under_parallel_sends(prepared):
    b, p, *_ = prepared
    inv = b.claim("one")
    body = wire(b, inv)
    with b.store.tx() as s:
        s.get(Project, p["id"]).max_requests = 1

    def send(i):
        try:
            return b.admission(inv["token"], Admission(request_id=f"http-{i}", payload=body))["permitted"]
        except DomainError as e:
            return e.code
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(send, range(4)))
    assert results.count(True) == 1 and results.count("BUDGET_EXHAUSTED") == 3


def test_context_epoch_and_extra_upload_fields_rejected(prepared):
    b, *_ = prepared
    inv = b.claim("one")
    body = wire(b, inv)
    body["dsh_session_log"] = "private logs"
    failure("UNAUTHORIZED_WIRE_FIELDS", lambda: b.admission(inv["token"], Admission(request_id="bad", payload=body)))
    with b.store.tx() as s:
        s.get(Task, inv["task_id"]).epoch += 1
    failure("CONTEXT_INVALID", lambda: b.manifest(inv["token"]))


def test_stale_control_card_is_rejected(prepared):
    b, p, _, run = prepared
    first = ControlInput(request_id="pause", expected_revision=1, action="pause")
    assert b.control(p["id"], run["id"], first) == b.control(p["id"], run["id"], first)
    failure("REVISION_CONFLICT", lambda: b.control(p["id"], run["id"],
        ControlInput(request_id="old", expected_revision=1, action="cancel")))


@pytest.mark.parametrize("expired", ["lease", "deadline"])
def test_expired_completion_requires_separate_reconciliation(prepared, expired):
    b, _, ref, _ = prepared
    inv = b.claim("one")
    finish(b, inv, ref["id"])
    with b.store.tx() as s:
        if expired == "lease":
            s.get(Task, inv["task_id"]).lease_until = 0
        else:
            s.get(Attempt, inv["attempt_id"]).deadline = 0
            s.get(Task, inv["task_id"]).lease_until = 0
    b.complete(inv["attempt_id"], "completed")
    with b.store.tx() as s:
        assert s.get(TaskResult, inv["task_id"]) is None
    assert b.claim("reconcile") is None
    with b.store.tx() as s:
        assert s.get(TaskResult, inv["task_id"]) is not None
        assert len(s.scalars(select(Attempt)).all()) == 1


def test_unknown_usage_blocks_explicit_resume(prepared):
    b, p, _, run = prepared
    inv = b.claim("one")
    b.admission(inv["token"], Admission(request_id="uncertain", payload=wire(b, inv)))
    b.complete(inv["attempt_id"], "unknown")
    failure("RECONCILIATION_REQUIRED", lambda: b.control(p["id"], run["id"],
        ControlInput(request_id="resume", expected_revision=1, action="resume")))
    assert b.claim("two") is None
    with b.store.tx() as s:
        assert s.get(Request, "uncertain").reservation == 100


def test_partial_candidate_blocks_blind_replay(prepared):
    b, p, ref, run = prepared
    inv = b.claim("one")
    tool(b, inv, "save_candidate", {"candidate": payload(ref["id"])})
    b.complete(inv["attempt_id"], "unknown")
    failure("PARTIAL_CANDIDATE_REQUIRES_REVIEW", lambda: b.control(p["id"], run["id"],
        ControlInput(request_id="resume", expected_revision=1, action="resume")))


def test_cross_session_rebuild_preserves_authority_and_budget(business):
    from app.services import Business
    b = business
    p = b.create_project(ProjectInput(name="交接", customer="合成客户", enterprise="合成企业"))
    def revision(kind, logical_id, value):
        return b.save_revision(p["id"], RevisionInput(request_id=logical_id, logical_id=logical_id,
            kind=kind, actor="human", reason="合成恢复场景", payload=value))
    source = revision("source", "source", {"synthetic": True, "text": "三年；未经批准不得自动承诺。"})
    revision("decision", "pending", {"status": "unverified", "text": "自动迁移能力待核"})
    revision("decision", "confirmed", {"status": "confirmed", "text": "仅限已确认范围"})
    block = {"block_id": "locked", "text": "人工锁定的限定条件"}
    draft = revision("draft", "draft", {"blocks": [block]})
    lock = revision("lock", "lock", {"logical_id": "draft", "draft_revision": draft["id"],
                                     "hashes": {"locked": digest(block)}})
    run = b.create_probe(p["id"], ProbeInput(request_id="run", expected_generation=lock["generation"],
                                             source_ids=[source["id"]]))
    inv = b.claim("one")
    b.admission(inv["token"], Admission(request_id="first", payload=wire(b, inv)))
    b.settle(inv["token"], Settlement(request_id="first", usage={"input_tokens": 3, "output_tokens": 3}))
    tool(b, inv, "read_sources", {"source_ids": [source["id"]]})
    for index in range(1):
        b.control(p["id"], run["id"], ControlInput(request_id=f"pause-{index}",
                   expected_revision=1+index*2, action="pause"))
        b.complete(inv["attempt_id"], "stopped")
        b = Business(b.store)  # Controller restart; only durable state survives.
        b.control(p["id"], run["id"], ControlInput(request_id=f"resume-{index}",
                   expected_revision=2+index*2, action="resume"))
        old = inv
        inv = b.claim("new-session")
        failure("LEASE_LOST", lambda: b.manifest(old["token"]))
        context = b.manifest(inv["token"])
        assert context["epoch"] == index + 2
        assert context["budget_family"] == run["family_id"]
        assert context["required_sources"][0]["payload"]["text"] == "三年；未经批准不得自动承诺。"
        assert len(context["authority"]) == 4 and len(context["pending"]) == 1
        assert context["prior_requests"] == [{"id": "first", "status": "settled", "reservation": 100, "actual": 6}]
        assert len(context["completed_actions"]) == 1
    b.control(p["id"], run["id"], ControlInput(request_id="pause-again", expected_revision=3, action="pause"))
    b.complete(inv["attempt_id"], "stopped")
    failure("CONTEXT_REBUILD_LIMIT", lambda: b.control(p["id"], run["id"],
        ControlInput(request_id="resume-again", expected_revision=4, action="resume")))


@pytest.mark.parametrize("mutation", ["drop_condition", "change_epoch", "drop_pending", "claim_support"])
def test_context_distortion_refuses_send(prepared, mutation):
    import json
    b, *_ = prepared
    inv = b.claim("one")
    context = b.manifest(inv["token"])
    if mutation == "drop_condition":
        context["required_sources"][0]["payload"]["text"] = "服务期三年"
    elif mutation == "change_epoch":
        context["epoch"] += 1
    elif mutation == "drop_pending":
        del context["pending"]
    else:
        context["authority"] = [{"kind": "decision", "payload": {"status": "confirmed", "text": "支持自动迁移"}}]
    body = {"model": "bid-fixture", "messages": [{"role": "user", "content": [
        {"type": "text", "text": json.dumps(context, ensure_ascii=False)}]}]}
    failure("CONTEXT_INVALID", lambda: b.admission(inv["token"], Admission(request_id="bad", payload=body)))
    with b.store.tx() as s:
        assert not s.scalars(select(Request)).all()


def test_output_bound_and_duplicate_completion(prepared):
    b, _, ref, _ = prepared
    inv = b.claim("one")
    huge = payload(ref["id"])
    huge["blocks"] = [{"block_id": str(i), "text": "中" * 8000} for i in range(2)]
    failure("OUTPUT_TOO_LARGE", lambda: tool(b, inv, "save_candidate", {"candidate": huge}, "huge"))
    finish(b, inv, ref["id"])
    b.complete(inv["attempt_id"], "completed")
    b.complete(inv["attempt_id"], "completed")
    with b.store.tx() as s:
        assert len(s.scalars(select(Receipt)).all()) == 3


@pytest.mark.parametrize("blocks", [
    [{"type": "tool_use", "id": "missing-result", "name": "read_sources", "input": {}}],
    [{"type": "tool_result", "tool_use_id": "missing-call", "content": []}],
    [{"type": "tool_use", "id": "duplicate", "name": "read_sources", "input": {}},
     {"type": "tool_use", "id": "duplicate", "name": "read_sources", "input": {}}],
])
def test_unpaired_tool_history_cannot_send(prepared, blocks):
    b, *_ = prepared
    inv = b.claim("one")
    body = wire(b, inv)
    body["messages"].append({"role": "assistant", "content": blocks})
    failure("TOOL_PAIR_INVALID", lambda: b.admission(inv["token"], Admission(request_id="bad", payload=body)))
    with b.store.tx() as s:
        assert not s.scalars(select(Request)).all()
