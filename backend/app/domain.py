"""Immutable revisions, durable tasks, leases, budgets and transactional outbox."""
import time
import uuid
from typing import Any

from sqlalchemy import JSON, BigInteger, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def uid() -> str:
    return uuid.uuid4().hex


class Base(DeclarativeBase):
    pass


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String)
    customer: Mapped[str] = mapped_column(String)
    enterprise: Mapped[str] = mapped_column(String)
    volume: Mapped[str] = mapped_column(String, default="技术卷")
    generation: Mapped[int] = mapped_column(Integer, default=1)
    baseline_id: Mapped[str] = mapped_column(String)
    max_requests: Mapped[int] = mapped_column(Integer, default=30)
    max_cost: Mapped[int] = mapped_column(BigInteger, default=100000)
    created_at: Mapped[float] = mapped_column(default=time.time)


class Revision(Base):
    __tablename__ = "revisions"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    logical_id: Mapped[str] = mapped_column(String, index=True)
    kind: Mapped[str] = mapped_column(String)
    parent_id: Mapped[str | None] = mapped_column(String)
    blob_hash: Mapped[str] = mapped_column(String)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    actor: Mapped[str] = mapped_column(String)
    reason: Mapped[str] = mapped_column(String)
    created_at: Mapped[float] = mapped_column(default=time.time)


class Head(Base):
    __tablename__ = "heads"
    __table_args__ = (UniqueConstraint("project_id", "logical_id"),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    logical_id: Mapped[str] = mapped_column(String)
    revision_id: Mapped[str] = mapped_column(ForeignKey("revisions.id"))


class Family(Base):
    __tablename__ = "task_families"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    revisions_used: Mapped[int] = mapped_column(Integer, default=0)
    max_revisions: Mapped[int] = mapped_column(Integer, default=2)
    max_requests: Mapped[int] = mapped_column(Integer, default=9)


class Run(Base):
    __tablename__ = "runs"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    status: Mapped[str] = mapped_column(String, default="queued")
    outcome: Mapped[str | None] = mapped_column(String)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[float] = mapped_column(default=time.time)


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (UniqueConstraint("task_key", "input_hash"),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    family_id: Mapped[str] = mapped_column(ForeignKey("task_families.id"))
    task_key: Mapped[str] = mapped_column(String)
    input_hash: Mapped[str] = mapped_column(String)
    baseline_id: Mapped[str] = mapped_column(String)
    generation: Mapped[int] = mapped_column(Integer)
    contract: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String, default="queued")
    fence: Mapped[int] = mapped_column(Integer, default=0)
    lease_until: Mapped[float | None] = mapped_column()
    owner: Mapped[str | None] = mapped_column(String)
    cancel_requested: Mapped[bool] = mapped_column(default=False)
    epoch: Mapped[int] = mapped_column(Integer, default=1)
    error: Mapped[str | None] = mapped_column(Text)


class Attempt(Base):
    __tablename__ = "attempts"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), index=True)
    fence: Mapped[int] = mapped_column(Integer)
    epoch: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String, default="running")
    token_hash: Mapped[str] = mapped_column(String, unique=True)
    session_id: Mapped[str | None] = mapped_column(String)
    home: Mapped[str | None] = mapped_column(String)
    build_hash: Mapped[str | None] = mapped_column(String)
    profile_hash: Mapped[str | None] = mapped_column(String)
    started_at: Mapped[float] = mapped_column(default=time.time)
    deadline: Mapped[float] = mapped_column()
    ended_at: Mapped[float | None] = mapped_column()


class Candidate(Base):
    __tablename__ = "candidates"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), index=True)
    attempt_id: Mapped[str] = mapped_column(ForeignKey("attempts.id"))
    blob_hash: Mapped[str] = mapped_column(String)
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String, default="candidate")
    finished: Mapped[bool] = mapped_column(default=False)


class Receipt(Base):
    __tablename__ = "validation_receipts"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"))
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id"))
    input_hash: Mapped[str] = mapped_column(String)
    layer: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    checks: Mapped[dict] = mapped_column(JSON)


class TaskResult(Base):
    __tablename__ = "task_results"
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), primary_key=True)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id"))
    input_hash: Mapped[str] = mapped_column(String)
    created_at: Mapped[float] = mapped_column(default=time.time)


class Request(Base):
    __tablename__ = "model_requests"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    attempt_id: Mapped[str] = mapped_column(ForeignKey("attempts.id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    family_id: Mapped[str] = mapped_column(ForeignKey("task_families.id"), index=True)
    payload_hash: Mapped[str] = mapped_column(String)
    purpose: Mapped[str] = mapped_column(String)
    reservation: Mapped[int] = mapped_column(BigInteger)
    actual: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String, default="reserved")
    usage: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[float] = mapped_column(default=time.time)


class Invocation(Base):
    __tablename__ = "tool_invocations"
    __table_args__ = (UniqueConstraint("attempt_id", "request_id"),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    attempt_id: Mapped[str] = mapped_column(ForeignKey("attempts.id"))
    request_id: Mapped[str] = mapped_column(String)
    payload_hash: Mapped[str] = mapped_column(String)
    result: Mapped[dict] = mapped_column(JSON)


class Action(Base):
    __tablename__ = "actions"
    __table_args__ = (UniqueConstraint("project_id", "request_id"),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    request_id: Mapped[str] = mapped_column(String)
    payload_hash: Mapped[str] = mapped_column(String)
    result: Mapped[dict] = mapped_column(JSON)


class Event(Base):
    __tablename__ = "business_events"
    # SQLite autoincrement requires INTEGER; PostgreSQL uses BIGSERIAL.
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    kind: Mapped[str] = mapped_column(String)
    payload: Mapped[dict] = mapped_column(JSON)
    dedup_key: Mapped[str | None] = mapped_column(String, unique=True)
    created_at: Mapped[float] = mapped_column(default=time.time)
