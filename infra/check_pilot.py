import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.pilot import Pilot  # noqa: E402
from app.settings import ROOT  # noqa: E402

path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "evals/manifests/engineering-fixture.json"
pilot = Pilot.model_validate_json(path.read_text())
for material in pilot.materials:
    file = (ROOT / material.path).resolve()
    if not file.is_relative_to(ROOT) or hashlib.sha256(file.read_bytes()).hexdigest() != material.sha256:
        raise SystemExit(f"MATERIAL_HASH_MISMATCH: {material.id}")
print(json.dumps(pilot.readiness(), ensure_ascii=False, indent=2))
