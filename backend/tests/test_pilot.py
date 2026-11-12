import json

import pytest
from pydantic import ValidationError

from app.pilot import Pilot
from app.settings import ROOT


def manifest():
    return json.loads((ROOT / "evals/manifests/engineering-fixture.json").read_text())


def test_fixture_cannot_claim_business_acceptance():
    value = manifest()
    assert Pilot.model_validate(value).readiness()["ready_for_real_pilot"] is False
    value["L4"] = "passed"
    with pytest.raises(ValidationError, match="cannot certify"):
        Pilot.model_validate(value)


def test_unfair_or_unidentified_comparisons_rejected():
    value = manifest()
    value["comparisons"][1]["material_ids"] = []
    with pytest.raises(ValidationError, match="same known materials"):
        Pilot.model_validate(value)
