import hashlib
import json
import secrets
import time

from sqlalchemy import select

from app.contracts import CandidatePayload, TOOLS
from app.domain import (
    Action, Attempt, Candidate, Event, Family, Head, Invocation, Project, Receipt,
    Request, Revision, Run, Task, TaskResult, uid,
)
from app.storage import Storage, canonical, digest


class DomainError(Exception):
    def __init__(self, code: str, status: int = 409):
        self.code, self.status = code, status
        super().__init__(code)


def require(condition, code, status=409):
    if not condition:
        raise DomainError(code, status)


def record(s, project_id, kind, payload, key=None):
    s.add(Event(project_id=project_id, kind=kind, payload=payload, dedup_key=key))


def project(s, project_id):
    value = s.get(Project, project_id)
    require(value is not None, "PROJECT_NOT_FOUND", 404)
    return value


def scoped(s, model, object_id, project_id):
    value = s.get(model, object_id)
    require(value is not None and value.project_id == project_id, "SCOPE_DENIED", 403)
    return value


def idempotent(s, project_id, request_id, payload, perform):
    old = s.scalar(select(Action).where(Action.project_id == project_id, Action.request_id == request_id))
    h = digest(payload)
    if old:
        require(old.payload_hash == h, "IDEMPOTENCY_CONFLICT")
        return old.result
    result = perform()
    s.add(Action(project_id=project_id, request_id=request_id, payload_hash=h, result=result))
    return result


class Business:
    def __init__(self, storage: Storage):
        self.store = storage

    def create_project(self, data):
        with self.store.tx() as s:
            p = Project(id=uid(), baseline_id=uid(), **data.model_dump())
            s.add(p)
            s.flush()
            payload = {"knowledge_release": None, "sources": [], "scope": "技术卷", "synthetic": True}
            s.add(Revision(id=p.baseline_id, project_id=p.id, logical_id="baseline", kind="baseline",
                           blob_hash=self.store.put(payload), payload=payload, actor="local-user",
                           reason="创建项目，真实资料尚未核对"))
            record(s, p.id, "project.created", {"project_id": p.id})
            return {"id": p.id, "generation": p.generation, "baseline_id": p.baseline_id}

    def save_revision(self, project_id, data):
        with self.store.tx() as s:
            p = project(s, project_id)

            def perform():
                head = s.scalar(select(Head).where(Head.project_id == p.id, Head.logical_id == data.logical_id))
                require((head.revision_id if head else None) == data.expected_revision, "REVISION_CONFLICT")
                payload = data.payload
                require(len(canonical(payload)) <= 100000, "OBJECT_TOO_LARGE", 422)
                if data.kind == "source":
                    require(payload.get("synthetic") is True and isinstance(payload.get("text"), str),
                            "PHASE1_SYNTHETIC_TEXT_ONLY", 422)
                    require(bool(payload["text"].strip()), "SOURCE_UNREADABLE", 422)
                if data.kind == "model_profile":
                    require(set(payload) <= {"mode", "provider", "model", "capabilities"},
                            "PROFILE_SECRET_OR_FIELD_DENIED", 422)
                    require(payload.get("mode") == "fixture", "REAL_PROVIDER_NOT_ENABLED", 422)
                previous = s.get(Revision, head.revision_id) if head else None
                h = self.store.put(payload)
                if previous and previous.blob_hash == h and previous.kind == data.kind:
                    return {"id": previous.id, "generation": p.generation, "deduplicated": True}
                if previous:
                    require(previous.kind == data.kind, "OBJECT_KIND_CONFLICT")
                # Locked blocks cannot be changed, even by an unrelated late candidate.
                if data.kind == "draft":
                    locks = s.scalars(select(Revision).join(Head, Head.revision_id == Revision.id)
                                      .where(Revision.project_id == p.id, Revision.kind == "lock")).all()
                    blocks = {b["block_id"]: b for b in payload.get("blocks", [])}
                    for lock in locks:
                        if lock.payload.get("logical_id") == data.logical_id:
                            for block_id, expected in lock.payload.get("hashes", {}).items():
                                require(block_id in blocks and digest(blocks[block_id]) == expected,
                                        "LOCK_CONFLICT")
                if data.kind == "lock":
                    target = s.scalar(select(Head).where(Head.project_id == p.id,
                                                        Head.logical_id == payload.get("logical_id")))
                    require(target is not None, "LOCK_TARGET_MISSING", 422)
                    current = s.get(Revision, target.revision_id)
                    require(payload.get("draft_revision") == current.id, "REVISION_CONFLICT")
                    blocks = {b["block_id"]: b for b in current.payload.get("blocks", [])}
                    require(bool(payload.get("hashes")), "EMPTY_LOCK", 422)
                    require(all(k in blocks and digest(blocks[k]) == v for k, v in payload["hashes"].items()),
                            "LOCK_HASH_INVALID", 422)
                rev = Revision(id=uid(), project_id=p.id, logical_id=data.logical_id, kind=data.kind,
                               parent_id=data.expected_revision, blob_hash=h, payload=payload,
                               actor=data.actor, reason=data.reason)
                s.add(rev)
                s.flush()
                if head:
                    head.revision_id = rev.id
                else:
                    s.add(Head(project_id=p.id, logical_id=data.logical_id, revision_id=rev.id))
                p.generation += 1
                p.baseline_id = uid()
                baseline = {"generation": p.generation, "changed_revision": rev.id,
                            "previous_baseline": previous.id if previous else None}
                s.add(Revision(id=p.baseline_id, project_id=p.id, logical_id="baseline", kind="baseline",
                               blob_hash=self.store.put(baseline), payload=baseline, actor=data.actor,
                               reason=data.reason))
                # Conservative invalidation until dependency propagation is implemented.
                for task in s.scalars(select(Task).where(Task.project_id == p.id, Task.status != "cancelled")):
                    task.status, task.error = "stale", "STALE_INPUT"
                    task.fence += 1
                    for candidate in s.scalars(select(Candidate).where(Candidate.task_id == task.id)):
                        candidate.status = "stale"
                for run in s.scalars(select(Run).where(Run.project_id == p.id, Run.status != "cancelled")):
                    run.status, run.outcome = "waiting_input", "needs_input"
                    run.revision += 1
                record(s, p.id, "baseline.changed", {"revision_id": rev.id, "generation": p.generation})
                return {"id": rev.id, "generation": p.generation, "deduplicated": False}

            return idempotent(s, p.id, data.request_id, data.model_dump(), perform)

    def create_probe(self, project_id, data):
        with self.store.tx() as s:
            p = project(s, project_id)

            def perform():
                require(p.generation == data.expected_generation, "STALE_INPUT")
                refs = sorted(set(data.source_ids))
                for ref in refs:
                    source = scoped(s, Revision, ref, p.id)
                    require(source.kind == "source" and source.payload.get("synthetic") is True,
                            "DATA_SCOPE_DENIED", 403)
                    require(self.store.verify(source.blob_hash), "SOURCE_UNREADABLE")
                    head = s.scalar(select(Head).where(Head.project_id == p.id,
                                                        Head.logical_id == source.logical_id))
                    require(head is not None and head.revision_id == ref, "STALE_INPUT")
                if data.family_id:
                    family = scoped(s, Family, data.family_id, p.id)
                else:
                    family = Family(id=uid(), project_id=p.id)
                    s.add(family)
                run = Run(id=uid(), project_id=p.id)
                s.add(run)
                s.flush()
                contract = {"kind": "engineering_probe", "source_refs": refs, "expected_items": refs,
                            "allowed_tools": list(TOOLS), "mode": "fixture", "scenario": data.scenario,
                            "input_limit_bytes": 64000, "output_limit_bytes": 32000,
                            "validation_layers": ["program"], "business_acceptance": "not_run",
                            "retry": {"mode": "normal", "maxRetries": 2},
                            "model_profile": "fixture-v1", "max_http_per_attempt": 9,
                            "price_snapshot": "fixture-units-v1", "max_tools": 12}
                task = Task(id=uid(), project_id=p.id, run_id=run.id, family_id=family.id,
                            baseline_id=p.baseline_id, generation=p.generation, contract=contract,
                            task_key=f"{p.id}:{run.id}:engineering_probe", input_hash=digest(contract))
                s.add(task)
                record(s, p.id, "run.queued", {"run_id": run.id, "task_id": task.id})
                return {"id": run.id, "task_id": task.id, "family_id": family.id}

            return idempotent(s, p.id, data.request_id, data.model_dump(), perform)

    def control(self, project_id, run_id, data):
        with self.store.tx() as s:
            run = scoped(s, Run, run_id, project_id)

            def perform():
                require(run.revision == data.expected_revision, "REVISION_CONFLICT")
                tasks = s.scalars(select(Task).where(Task.run_id == run.id)).all()
                require(run.status not in {"cancelled", "finished", "failed"}, "RUN_TERMINAL")
                if data.action == "pause":
                    run.status = "paused"
                    # Pause ends active activity at a guarded boundary; no new sends.
                elif data.action == "cancel":
                    run.status, run.outcome = "cancelled", "cancelled"
                    for t in tasks:
                        t.cancel_requested, t.status = True, "cancelled"
                        t.fence += 1
                else:
                    require(run.status in {"paused", "waiting_input"}, "RUN_NOT_RESUMABLE")
                    for t in tasks:
                        require(t.generation == project(s, project_id).generation, "STALE_INPUT")
                        require(not t.cancel_requested, "CANCELLED")
                        # Active lease must end or expire before reconcile grants new ownership.
                        if t.lease_until and t.lease_until > time.time() and t.status == "running":
                            raise DomainError("ACTIVITY_STILL_STOPPING")
                        self._unknown(s, t.id)
                        uncertain = s.scalar(select(Request).join(Attempt, Request.attempt_id == Attempt.id)
                            .where(Attempt.task_id == t.id, Request.status.in_(["unknown", "reserved"])))
                        require(uncertain is None, "RECONCILIATION_REQUIRED")
                        partial = s.scalar(select(Candidate).where(Candidate.task_id == t.id,
                                                                  Candidate.finished.is_(False)))
                        require(partial is None, "PARTIAL_CANDIDATE_REQUIRES_REVIEW")
                        if t.status == "waiting_input":
                            require(t.epoch < 2, "CONTEXT_REBUILD_LIMIT")
                            t.status = "queued"
                            t.epoch += 1
                    run.status = "queued"
                run.revision += 1
                record(s, project_id, f"run.{data.action}", {"run_id": run.id})
                return {"id": run.id, "status": run.status, "revision": run.revision}

            return idempotent(s, project_id, data.request_id, data.model_dump(), perform)

    def claim(self, owner):
        now = time.time()
        with self.store.tx() as s:
            active = s.scalar(select(Task).where(Task.status == "running", Task.lease_until > now))
            if active:
                return None
            for t in s.scalars(select(Task).where(Task.status.in_(["queued", "running", "checking"])).order_by(Task.id)):
                run = s.get(Run, t.run_id)
                if run.status in {"paused", "cancelled", "waiting_input"}:
                    continue
                p = s.get(Project, t.project_id)
                if p.generation != t.generation:
                    t.status, t.error = "stale", "STALE_INPUT"
                    continue
                result = s.get(TaskResult, t.id)
                if result:
                    self._unknown(s, t.id)
                    t.status, run.status, run.outcome = "succeeded", "finished", "engineering_only"
                    continue
                finished = s.scalar(select(Candidate).where(Candidate.task_id == t.id, Candidate.finished.is_(True)))
                if finished:
                    self._unknown(s, t.id)
                    self._validate_commit(s, t, finished)
                    continue
                # Never replay an uncertain/partially executed activity automatically.
                if t.status in {"running", "checking"}:
                    t.status, t.error = "waiting_input", "EXECUTION_UNKNOWN"
                    run.status, run.outcome = "waiting_input", "needs_input"
                    self._unknown(s, t.id)
                    continue
                token = secrets.token_urlsafe(32)
                t.fence += 1
                t.owner, t.lease_until, t.status = owner, now + self.store.settings.lease_seconds, "running"
                run.status = "running"
                attempt = Attempt(id=uid(), task_id=t.id, fence=t.fence, epoch=t.epoch,
                                  token_hash=hashlib.sha256(token.encode()).hexdigest(),
                                  deadline=now + self.store.settings.activity_seconds)
                s.add(attempt)
                s.flush()
                context = self._context(s, t)
                if len(canonical(context)) > t.contract["input_limit_bytes"] // 2:
                    attempt.status, attempt.ended_at = "not_started", now
                    t.status, t.error = "waiting_input", "CONTEXT_REBUILD_REQUIRED"
                    run.status, run.outcome = "waiting_input", "needs_input"
                    continue
                snapshot_hash = self.store.put(context)
                record(s, p.id, "context.snapshot", {"attempt_id": attempt.id, "epoch": t.epoch,
                       "blob_hash": snapshot_hash}, f"context:{attempt.id}")
                record(s, p.id, "attempt.started", {"task_id": t.id, "attempt_id": attempt.id, "fence": t.fence})
                return {"attempt_id": attempt.id, "task_id": t.id, "token": token,
                        "contract": t.contract, "input_hash": t.input_hash, "epoch": t.epoch}
            return None

    def authorize(self, s, token):
        a = s.scalar(select(Attempt).where(Attempt.token_hash == hashlib.sha256(token.encode()).hexdigest()))
        require(a is not None, "TASK_TOKEN_DENIED", 403)
        t = s.get(Task, a.task_id)
        p, run = s.get(Project, t.project_id), s.get(Run, t.run_id)
        require(not t.cancel_requested and run.status != "cancelled", "CANCELLED", 403)
        require(run.status != "paused", "PAUSED", 403)
        require(t.fence == a.fence and (t.lease_until or 0) > time.time(), "LEASE_LOST", 403)
        require(t.generation == p.generation and t.baseline_id == p.baseline_id, "STALE_INPUT", 403)
        require(t.epoch == a.epoch, "CONTEXT_INVALID", 403)
        require(a.status == "running" and a.deadline > time.time(), "ACTIVITY_EXPIRED", 403)
        return a, t, p

    def tool(self, token, call):
        with self.store.tx() as s:
            a, t, p = self.authorize(s, token)
            require(call.tool in t.contract["allowed_tools"], "ACTION_NOT_ALLOWED", 403)
            schema = TOOLS.get(call.tool)
            require(schema is not None, "ACTION_NOT_ALLOWED", 403)
            args = schema.model_validate(call.arguments)
            h = digest(call.model_dump())
            old = s.scalar(select(Invocation).where(Invocation.attempt_id == a.id,
                                                   Invocation.request_id == call.request_id))
            if old:
                require(old.payload_hash == h, "IDEMPOTENCY_CONFLICT")
                return old.result
            invocations = s.scalars(select(Invocation).where(Invocation.attempt_id == a.id)).all()
            require(len(invocations) < t.contract["max_tools"], "TOOL_BUDGET_EXHAUSTED", 403)
            require(not s.scalar(select(Candidate).where(Candidate.attempt_id == a.id,
                                                         Candidate.finished.is_(True))),
                    "CANDIDATE_ALREADY_FINISHED", 403)
            if call.tool == "read_sources":
                require(set(args.source_ids) <= set(t.contract["source_refs"]), "SCOPE_DENIED", 403)
                result = {"sources": [{"id": ref, "payload": scoped(s, Revision, ref, p.id).payload}
                                      for ref in args.source_ids], "truncated": False}
            elif call.tool == "save_candidate":
                payload = args.candidate.model_dump()
                require(len(canonical(payload)) <= t.contract["output_limit_bytes"], "OUTPUT_TOO_LARGE", 422)
                c = Candidate(id=uid(), task_id=t.id, attempt_id=a.id,
                              blob_hash=self.store.put(payload), payload=payload)
                s.add(c)
                result = {"candidate_id": c.id, "blob_hash": c.blob_hash}
                record(s, p.id, "candidate.saved", result)
            else:
                c = s.get(Candidate, args.candidate_id)
                require(c is not None and c.attempt_id == a.id, "SCOPE_DENIED", 403)
                require(c.blob_hash == args.blob_hash and self.store.verify(c.blob_hash), "HASH_MISMATCH")
                c.finished = True
                result = {"candidate_id": c.id, "finished": True}
            s.add(Invocation(attempt_id=a.id, request_id=call.request_id, payload_hash=h, result=result))
            return result

    def _context(self, s, t):
        refs = [{"id": ref, "payload": scoped(s, Revision, ref, t.project_id).payload}
                for ref in t.contract["source_refs"]]
        heads = s.scalars(select(Revision).join(Head, Head.revision_id == Revision.id)
                         .where(Revision.project_id == t.project_id, Revision.kind != "source")
                         .order_by(Revision.logical_id)).all()
        requests = s.scalars(select(Request).where(Request.family_id == t.family_id)
                             .order_by(Request.id)).all()
        actions = s.scalars(select(Invocation).join(Attempt, Invocation.attempt_id == Attempt.id)
                            .where(Attempt.task_id == t.id).order_by(Invocation.id)).all()
        return {"task_id": t.id, "baseline_id": t.baseline_id, "input_hash": t.input_hash,
                "epoch": t.epoch, "contract": t.contract, "required_sources": refs,
                "authority": [{"id": r.id, "kind": r.kind, "payload": r.payload} for r in heads],
                "completed_actions": [{"id": a.id, "result": a.result} for a in actions],
                "next_action": "read_sources", "budget_family": t.family_id,
                "prior_requests": [{"id": r.id, "status": r.status, "reservation": r.reservation,
                                     "actual": r.actual} for r in requests],
                "pending": [r.id for r in heads if r.kind == "decision"
                            and r.payload.get("status") != "confirmed"], "synthetic": True}

    def _snapshot(self, s, a):
        event = s.scalar(select(Event).where(Event.dedup_key == f"context:{a.id}"))
        require(event is not None and self.store.verify(event.payload["blob_hash"]), "CONTEXT_INVALID", 403)
        return json.loads((self.store.blobs / event.payload["blob_hash"]).read_bytes())

    def manifest(self, token):
        with self.store.tx() as s:
            a, t, p = self.authorize(s, token)
            return self._snapshot(s, a)

    def admission(self, token, data):
        with self.store.tx() as s:
            a, t, p = self.authorize(s, token)
            require(self.store.settings.runtime_mode == "fixture", "REAL_PROVIDER_NOT_ENABLED", 403)
            wire = data.payload
            allowed = {"model", "messages", "system", "max_tokens", "stream", "tools", "tool_choice",
                       "temperature", "top_p", "thinking", "metadata", "stop_sequences"}
            require(set(wire) <= allowed, "UNAUTHORIZED_WIRE_FIELDS", 403)
            require(wire.get("model") == "bid-fixture", "DATA_SCOPE_DENIED", 403)
            require(not wire.get("metadata"), "UNAUTHORIZED_WIRE_FIELDS", 403)
            require(len(canonical(wire)) <= t.contract["input_limit_bytes"], "CONTEXT_REBUILD_REQUIRED", 403)
            tools = wire.get("tools", [])
            require(all(x.get("name") in t.contract["allowed_tools"] for x in tools), "SCOPE_DENIED", 403)
            pending_calls, seen_calls = set(), set()
            for message in wire.get("messages", []):
                blocks = message.get("content", [])
                require(isinstance(blocks, list), "CONTEXT_INVALID", 403)
                for block in blocks:
                    if block.get("type") == "tool_use":
                        call_id = block.get("id")
                        require(isinstance(call_id, str) and call_id not in seen_calls,
                                "TOOL_PAIR_INVALID", 403)
                        pending_calls.add(call_id)
                        seen_calls.add(call_id)
                    elif block.get("type") == "tool_result":
                        call_id = block.get("tool_use_id")
                        require(call_id in pending_calls, "TOOL_PAIR_INVALID", 403)
                        pending_calls.remove(call_id)
            require(not pending_calls, "TOOL_PAIR_INVALID", 403)
            manifests = []
            for message in wire.get("messages", []):
                for block in message.get("content", []):
                    if block.get("type") != "text":
                        continue
                    try:
                        value = json.loads(block.get("text", ""))
                    except (ValueError, TypeError):
                        continue
                    if isinstance(value, dict) and value.get("task_id") == t.id:
                        manifests.append(value)
            require(len(manifests) == 1, "CONTEXT_INVALID", 403)
            context = manifests[0]
            require(context == self._snapshot(s, a), "CONTEXT_INVALID", 403)
            old = s.get(Request, data.request_id)
            # A permit is single-use, never reusable as a second HTTP send.
            require(old is None, "REQUEST_ALREADY_ADMITTED", 403)
            rows = s.scalars(select(Request).where(Request.project_id == p.id)).all()
            family = s.get(Family, t.family_id)
            family_rows = [r for r in rows if r.family_id == family.id]
            attempt_rows = [r for r in rows if r.attempt_id == a.id]
            require(len(rows) < p.max_requests and len(family_rows) < family.max_requests
                    and len(attempt_rows) < t.contract["max_http_per_attempt"], "BUDGET_EXHAUSTED", 403)
            held = sum(r.actual if r.status == "settled" else r.reservation for r in rows)
            require(held + 100 <= p.max_cost, "BUDGET_EXHAUSTED", 403)
            s.add(Request(id=data.request_id, attempt_id=a.id, project_id=p.id, family_id=family.id,
                          payload_hash=digest(wire), purpose=data.purpose, reservation=100))
            record(s, p.id, "request.admitted", {"request_id": data.request_id, "synthetic": True})
            return {"permitted": True, "request_id": data.request_id}

    def settle(self, token, data):
        # Settlement is allowed after cancellation; it cannot authorize further sends or writes.
        with self.store.tx() as s:
            a = s.scalar(select(Attempt).where(Attempt.token_hash == hashlib.sha256(token.encode()).hexdigest()))
            require(a is not None, "TASK_TOKEN_DENIED", 403)
            row = s.get(Request, data.request_id)
            require(row is not None and row.attempt_id == a.id, "SCOPE_DENIED", 403)
            usage = data.usage
            valid = usage is not None and all(type(usage.get(k)) is int and usage[k] >= 0
                                             for k in ("input_tokens", "output_tokens"))
            actual = usage["input_tokens"] + usage["output_tokens"] if valid else None
            if row.status == "settled":
                require(row.actual == actual and row.usage == usage, "SETTLEMENT_CONFLICT")
            else:
                row.status, row.actual, row.usage = "settled" if valid else "unknown", actual, usage
            return {"status": row.status}

    def heartbeat(self, attempt_id):
        with self.store.tx() as s:
            a = s.get(Attempt, attempt_id)
            t = s.get(Task, a.task_id)
            run = s.get(Run, t.run_id)
            now = time.time()
            if (a.status != "running" or t.status != "running" or t.fence != a.fence
                    or (t.lease_until or 0) <= now or a.deadline <= now
                    or run.status in {"paused", "cancelled"}):
                return False
            t.lease_until = now + self.store.settings.lease_seconds
            return True

    def complete(self, attempt_id, outcome, error=None):
        with self.store.tx() as s:
            a = s.get(Attempt, attempt_id)
            t, now = s.get(Task, a.task_id), time.time()
            run = s.get(Run, t.run_id)
            if a.ended_at is not None or s.get(TaskResult, t.id):
                return
            a.status, a.ended_at = outcome, now
            self._unknown(s, t.id)
            if t.cancel_requested or t.status in {"stale", "cancelled"} or t.fence != a.fence:
                return
            if (t.lease_until or 0) <= now or a.deadline <= now:
                t.status, t.error = "checking", "ACTIVITY_EXPIRED"
                record(s, t.project_id, "attempt.expired", {"attempt_id": a.id})
                return  # A separate reconciliation may validate a durably finished candidate.
            t.lease_until = now
            require(t.generation == s.get(Project, t.project_id).generation, "STALE_INPUT")
            if run.status == "paused":
                t.status, t.error = "waiting_input", "PAUSED"
                return
            candidate = s.scalar(select(Candidate).where(Candidate.attempt_id == a.id,
                                                         Candidate.finished.is_(True)))
            if candidate:
                self._validate_commit(s, t, candidate)
            else:
                t.status, t.error = "waiting_input", error or "EXECUTION_UNKNOWN"
                run.status, run.outcome = "waiting_input", "needs_input"
            record(s, t.project_id, "attempt.ended", {"attempt_id": a.id, "outcome": outcome,
                                                     "error": t.error})

    def observe_runtime(self, attempt_id, binding, rows, offset=0):
        """Idempotently project runtime evidence; events never grant business authority."""
        with self.store.tx() as s:
            a = s.get(Attempt, attempt_id)
            t = s.get(Task, a.task_id)
            if binding:
                for name in ("session_id", "home", "build_hash", "profile_hash"):
                    setattr(a, name, binding[name])
            for index, row in enumerate(rows, offset):
                key = f"runtime:{a.id}:{index}"
                if not s.scalar(select(Event).where(Event.dedup_key == key)):
                    record(s, t.project_id, "runtime.observed", {"attempt_id": a.id, "event": row}, key)

    def _unknown(self, s, task_id):
        for row in s.scalars(select(Request).join(Attempt, Request.attempt_id == Attempt.id)
                             .where(Attempt.task_id == task_id, Request.status == "reserved")):
            row.status = "unknown"

    def _validate_commit(self, s, t, candidate):
        # Engineering acceptance intentionally cannot accept business prose or release files.
        require(t.generation == s.get(Project, t.project_id).generation, "STALE_INPUT")
        value = CandidatePayload.model_validate(candidate.payload)
        expected = set(t.contract["expected_items"])
        valid = (set(value.coverage_ids) == expected and set(value.source_refs) == expected
                 and self.store.verify(candidate.blob_hash)
                 and len({b.block_id for b in value.blocks}) == len(value.blocks))
        status = "passed" if valid else "failed"
        for layer in ("program", "semantic", "human"):
            s.add(Receipt(task_id=t.id, candidate_id=candidate.id, input_hash=t.input_hash, layer=layer,
                          status=status if layer == "program" else "not_run",
                          checks={"expected": sorted(expected), "checked": sorted(expected) if valid else [],
                                  "unresolved": [] if valid else sorted(expected), "scope": "engineering_only"}))
        run = s.get(Run, t.run_id)
        if not valid:
            candidate.status, t.status, t.error = "rejected", "waiting_input", "VALIDATOR_FAILED"
            run.status, run.outcome = "waiting_input", "needs_input"
            return
        if not s.get(TaskResult, t.id):
            s.add(TaskResult(task_id=t.id, candidate_id=candidate.id, input_hash=t.input_hash))
            record(s, t.project_id, "task.committed", {"task_id": t.id, "candidate_id": candidate.id,
                                                      "scope": "engineering_only"}, f"result:{t.id}")
        candidate.status, t.status, t.error = "accepted", "succeeded", None
        run.status, run.outcome = "finished", "engineering_only"
