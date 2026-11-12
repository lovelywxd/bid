from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProjectInput(Strict):
    name: str = Field(min_length=1, max_length=120)
    customer: str = Field(min_length=1, max_length=120)
    enterprise: str = Field(min_length=1, max_length=120)
    max_requests: int = Field(default=30, ge=0, le=1000)
    max_cost: int = Field(default=100000, ge=0, le=100000000)


class RevisionInput(Strict):
    request_id: str = Field(min_length=1, max_length=100)
    logical_id: str = Field(min_length=1, max_length=100)
    kind: Literal["source", "decision", "draft", "lock", "model_profile"]
    expected_revision: str | None = None
    payload: dict
    actor: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=300)


class ProbeInput(Strict):
    request_id: str = Field(min_length=1, max_length=100)
    expected_generation: int = Field(ge=1)
    source_ids: list[str] = Field(min_length=1, max_length=8)
    family_id: str | None = None
    scenario: Literal["normal", "retry", "slow", "bad_reference", "forbidden_tool", "after_finish", "handoff"] = "normal"


class ControlInput(Strict):
    request_id: str = Field(min_length=1, max_length=100)
    expected_revision: int = Field(ge=1)
    action: Literal["pause", "resume", "cancel"]


class Block(Strict):
    block_id: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=8000)


class CandidatePayload(Strict):
    kind: Literal["engineering_probe"]
    blocks: list[Block] = Field(min_length=1, max_length=16)
    source_refs: list[str] = Field(min_length=1, max_length=16)
    coverage_ids: list[str] = Field(min_length=1, max_length=16)


class ReadSources(Strict):
    source_ids: list[str] = Field(min_length=1, max_length=8)


class SaveCandidate(Strict):
    candidate: CandidatePayload


class FinishCandidate(Strict):
    candidate_id: str
    blob_hash: str


TOOLS = {"read_sources": ReadSources, "save_candidate": SaveCandidate, "finish_candidate": FinishCandidate}


class ToolCall(Strict):
    request_id: str = Field(min_length=1, max_length=100)
    tool: str
    arguments: dict


class Admission(Strict):
    request_id: str = Field(min_length=1, max_length=100)
    payload: dict
    purpose: Literal["generation"] = "generation"


class Settlement(Strict):
    request_id: str
    usage: dict | None = None


def schemas():
    return {name: model.model_json_schema() for name, model in TOOLS.items()}
