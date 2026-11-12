"""Build metadata for an already locked, patched official source build."""
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHA = "e8f7b93a344964de3dca1ace9e72b6e4d6de87cb"
source = ROOT / f"runtime/builds/harness-e8f7b93/deepseek-harness-{SHA}"
assert subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip() == SHA


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


files = [source / "pnpm-lock.yaml", source / "apps/cli/lib/bin.js",
         source / "packages/llm/llm-deepseek/lib/index.js",
         ROOT / "runtime/bid-plugin/dist/index.mjs", ROOT / "runtime/profiles/bid.json",
         source / "packages/llm/llm-deepseek/src/bid-admission.ts",
         source / "packages/llm/llm-deepseek/src/adapter.ts",
         ROOT / "runtime/upstream-patches/0001-send-admission.patch",
         ROOT / ".tools/node_modules/node/bin/node", ROOT / "backend/uv.lock"]
files += list((source / "python/sdk/src").rglob("*.py"))
for directory in ("packages", "vendor", "apps/cli/lib"):
    files += [p for p in (source / directory).rglob("*.js")
              if "node_modules" not in p.parts and ("lib" in p.parts or directory == "apps/cli/lib")]
files = sorted(set(files))
hashes = {str(p.relative_to(ROOT)): sha(p) for p in files}
manifest = {"upstream_sha": SHA, "version": "0.2.2-rc.2", "sdk_source_version": "0.0.0.dev0",
            "carrier": "official-built-node-cli", "source_dir": str(source), "files": hashes,
            "build_hash": hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest(),
            "mode": "fixture_text_only", "L3": "not_run", "L4": "not_run"}
(ROOT / "runtime/builds/active.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({k: v for k, v in manifest.items() if k != "files"}, ensure_ascii=False, indent=2))
print(f"Verified {len(files)} files; third-party dependency versions are pinned by pnpm-lock.yaml.")
