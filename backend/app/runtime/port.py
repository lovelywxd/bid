import asyncio
import json
import os
import signal
import sys
from dataclasses import dataclass
from typing import Protocol

from app.settings import ROOT


@dataclass
class ActivityOutcome:
    status: str
    exit_code: int | None
    error: str | None = None
    timed_out: bool = False


class RuntimePort(Protocol):
    async def execute(self, invocation: dict) -> ActivityOutcome: ...
    async def stop(self, attempt_id: str, reason: str) -> None: ...


class HarnessPort:
    def __init__(self, business, api_url: str):
        self.business, self.api_url = business, api_url
        self.processes = {}

    async def execute(self, invocation):
        attempt_id = invocation["attempt_id"]
        path = self.business.store.settings.data_dir / "attempts" / attempt_id
        path.mkdir(parents=True, exist_ok=True)
        active = ROOT / "runtime/builds/active.json"
        if not active.exists():
            return ActivityOutcome("failed", None, "RUNTIME_BUILD_MISSING")
        config = json.loads(active.read_text())
        for name, expected in config["files"].items():
            import hashlib
            if not (ROOT / name).is_file() or hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
                return ActivityOutcome("failed", None, "RUNTIME_BUILD_HASH_MISMATCH")
        # An outer clean process is necessary: the upstream SDK merges os.environ.
        env = {"PATH": f"{ROOT}/.tools/node_modules/node/bin:/usr/bin:/bin:/usr/sbin:/sbin",
               "LANG": "en_US.UTF-8", "PYTHONPATH": str(ROOT / "backend"),
               "BID_API_URL": self.api_url, "BID_TASK_TOKEN": invocation["token"],
               "BID_ATTEMPT_ID": attempt_id, "BID_ATTEMPT_DIR": str(path),
               "BID_BUILD_FILE": str(active), "DSH_TELEMETRY_DISABLED": "1"}
        with (path / "stdout.log").open("wb") as stdout, (path / "stderr.log").open("wb") as stderr:
            proc = await asyncio.create_subprocess_exec(sys.executable, "-m", "app.runtime.sdk_runner",
                                                        cwd=ROOT / "backend", env=env,
                                                        stdout=stdout, stderr=stderr, start_new_session=True)
            self.processes[attempt_id] = proc
            cursor = 0
            try:
                while proc.returncode is None:
                    try:
                        await asyncio.wait_for(proc.wait(), timeout=1)
                    except TimeoutError:
                        cursor = self._persist(attempt_id, path, cursor)
                        if not self.business.heartbeat(attempt_id):
                            await self.stop(attempt_id, "permission_revoked_or_deadline")
                            return ActivityOutcome("stopped", proc.returncode, "ACTIVITY_STOPPED", True)
                return ActivityOutcome("completed" if proc.returncode == 0 else "unknown", proc.returncode,
                                       None if proc.returncode == 0 else "RUNTIME_EXECUTION_UNKNOWN")
            finally:
                self.processes.pop(attempt_id, None)
                if proc.returncode is None:
                    await self._terminate(proc)
                self._persist(attempt_id, path, cursor)

    def _persist(self, attempt_id, path, cursor):
        binding_path = path / "binding.json"
        try:
            binding = json.loads(binding_path.read_text()) if binding_path.exists() else None
        except json.JSONDecodeError:
            binding = None  # Writer may still be flushing; next observation retries.
        rows = self.observe(attempt_id, cursor)
        self.business.observe_runtime(attempt_id, binding, rows, cursor)
        return cursor + len(rows)

    async def stop(self, attempt_id, reason):
        proc = self.processes.get(attempt_id)
        if proc and proc.returncode is None:
            # Runner handles SIGTERM by SDK.close/shutdown. Kill group only after grace.
            await self._terminate(proc)

    async def _terminate(self, proc):
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            await asyncio.wait_for(proc.wait(), timeout=4)
        except TimeoutError:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await proc.wait()

    def observe(self, attempt_id, cursor=0):
        path = self.business.store.settings.data_dir / "attempts" / attempt_id / "events.jsonl"
        if not path.exists():
            return []
        rows = []
        for line in path.read_text().splitlines()[cursor:]:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                break  # unflushed last line remains execution_unknown
        return rows
