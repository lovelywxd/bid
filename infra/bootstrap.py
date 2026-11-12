"""Explicit setup/build entry; normal startup never downloads or upgrades."""
import argparse
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHA = "e8f7b93a344964de3dca1ace9e72b6e4d6de87cb"
SOURCE = ROOT / f"runtime/builds/harness-e8f7b93/deepseek-harness-{SHA}"


def run(args, cwd=ROOT, env=None):
    print("Running:", " ".join(map(str, args)), flush=True)
    subprocess.run(list(map(str, args)), cwd=cwd, env=env, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install", action="store_true", help="Explicitly download locked dependencies")
    parser.add_argument("--build-harness", action="store_true", help="Run official build:artifacts and build:check")
    args = parser.parse_args()
    if args.install:
        tools = ROOT / ".tools"
        tools.mkdir(exist_ok=True)
        for name in ("package.json", "package-lock.json"):
            shutil.copy2(ROOT / "infra/toolchain" / name, tools / name)
        run(["npm", "ci", "--prefix", tools, "--registry=https://registry.npmjs.org"])
    node = ROOT / ".tools/node_modules/node/bin/node"
    pnpm = ROOT / ".tools/node_modules/pnpm/bin/pnpm.mjs"
    env = {**os.environ, "PATH": f"{node.parent}:{os.environ.get('PATH', '')}",
           "NPM_CONFIG_REGISTRY": "https://registry.npmjs.org"}
    if args.install:
        if not SOURCE.exists():
            SOURCE.mkdir(parents=True)
            run(["git", "init"], SOURCE)
            run(["git", "fetch", "--depth=1", "https://github.com/deepseek-ai/deepseek-harness.git", SHA], SOURCE)
            run(["git", "checkout", "--detach", "FETCH_HEAD"], SOURCE)
        run(["uv", "sync", "--project", "backend", "--frozen", "--python", "3.13"], env=env)
        # Native build needs the matching Node headers; only the local binary is affected.
        header = node.parent.parent / "include/node/node.h"
        if not header.exists():
            archive = ROOT / "runtime/builds/harness-e8f7b93/node-headers.tar.xz"
            run(["curl", "--fail", "--location", "--output", archive,
                 "https://nodejs.org/dist/v24.11.1/node-v24.11.1-headers.tar.xz"])
            run(["tar", "-xf", archive, "--strip-components=1", "-C", node.parent.parent,
                 "node-v24.11.1/include"])
        run([node, pnpm, "install", "--frozen-lockfile"], SOURCE, env)
        run(["npm", "ci", "--registry=https://registry.npmjs.org"], ROOT / "frontend", env)
    actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=SOURCE, text=True).strip()
    if actual != SHA:
        raise SystemExit("Fixed Harness SHA mismatch; no checkout was modified")
    patch = ROOT / "runtime/upstream-patches/0001-send-admission.patch"
    applied = subprocess.run(["git", "apply", "--reverse", "--check", str(patch)],
                             cwd=SOURCE, capture_output=True).returncode == 0
    if not applied:
        run(["git", "apply", "--check", patch], SOURCE)
        run(["git", "apply", patch], SOURCE)
    if args.build_harness:
        run([node, pnpm, "run", "build:artifacts"], SOURCE, env)
        run([node, pnpm, "run", "build:check"], SOURCE, env)
    plugin = ROOT / "runtime/bid-plugin"
    run([node, "typecheck.mjs"], plugin, env)
    run([node, "build.mjs"], plugin, env)
    run(["npm", "run", "build"], ROOT / "frontend", env)
    run(["uv", "run", "--project", "backend", "python", "infra/build_runtime.py"], env=env)


if __name__ == "__main__":
    main()
