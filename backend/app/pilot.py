"""Pilot intake only. Validation does not authorize model calls or release."""
from typing import Literal

from pydantic import Field, model_validator

from app.contracts import Strict


class Material(Strict):
    id: str
    path: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    synthetic: bool
    role: Literal["source", "knowledge", "label", "expert_revision", "holdout"]


class Comparison(Strict):
    group: Literal["A", "B", "C"]
    description: str
    material_ids: list[str]
    model_profile: str | None = None
    max_requests: int = Field(ge=0)
    max_cost: int = Field(ge=0)
    confounds: list[str]


class Permission(Strict):
    real_provider: bool = False
    business_data_egress: bool = False
    approved_by: str | None = None
    purpose: str | None = None


class Pilot(Strict):
    version: Literal["pilot-v1"]
    id: str
    scope: Literal["engineering_fixture", "real_chapters", "real_book", "holdout"]
    materials: list[Material]
    chapter_types: list[str]
    comparisons: list[Comparison] = Field(min_length=3, max_length=3)
    labels_status: Literal["not_run", "prepared", "reviewed"]
    expert_reviewers: list[str]
    permission: Permission
    L3: Literal["not_run", "passed", "failed", "blocked"]
    L4: Literal["not_run", "passed", "failed", "blocked"]

    @model_validator(mode="after")
    def consistent(self):
        ids = {m.id for m in self.materials}
        if len(ids) != len(self.materials) or {c.group for c in self.comparisons} != {"A", "B", "C"}:
            raise ValueError("Unique material IDs and all three comparison groups are required")
        shared = set(self.comparisons[0].material_ids)
        if any(set(c.material_ids) != shared or not set(c.material_ids) <= ids for c in self.comparisons):
            raise ValueError("Comparison groups must have the same known materials")
        if self.scope == "engineering_fixture":
            if any(not m.synthetic for m in self.materials) or self.L3 != "not_run" or self.L4 != "not_run":
                raise ValueError("Fixture results cannot certify real provider/business acceptance")
            if self.permission.real_provider or self.permission.business_data_egress:
                raise ValueError("Engineering fixtures cannot grant real-provider/data permission")
        return self

    def readiness(self):
        missing = []
        if self.scope == "engineering_fixture":
            missing.append("real_pilot_materials")
        if len(set(self.chapter_types)) < 3:
            missing.append("three_chapter_types")
        if self.labels_status != "reviewed":
            missing.append("independent_reviewed_labels")
        if not self.expert_reviewers:
            missing.append("named_expert_reviewers")
        if not (self.permission.real_provider and self.permission.business_data_egress
                and self.permission.approved_by and self.permission.purpose):
            missing.append("provider_purpose_data_budget_authorization")
        if self.L3 != "passed":
            missing.append("L3_provider_acceptance")
        return {"ready_for_real_pilot": not missing, "missing": missing,
                "L3": self.L3, "L4": self.L4, "execution_authorized": False}
