"""Clean child process owning one SDK and its isolated profile/session."""
import hashlib
import json
import os
import signal
import sys
from pathlib import Path

import httpx

from app.runtime.fixture_model import FixtureModel
from app.settings import ROOT


def main():
    build = json.loads(Path(os.environ["BID_BUILD_FILE"]).read_text())
    source = Path(build["source_dir"])
    sys.path.insert(0, str(source / "python/sdk/src"))
    from deepseek_harness import DeepSeekHarness
    api, token = os.environ["BID_API_URL"], os.environ["BID_TASK_TOKEN"]
    path = Path(os.environ["BID_ATTEMPT_DIR"])
    headers = {"authorization": f"Bearer {token}"}
    response = httpx.get(f"{api}/internal/manifest", headers=headers)
    response.raise_for_status()
    manifest = response.json()
    (path / "context.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    home = path / "home"
    profile = home / "profiles/bid"
    profile.mkdir(parents=True, exist_ok=True)
    # A custom profile has no implicit base/sdk-minimal bundle. All rows are explicit.
    (profile / "package.json").write_text(json.dumps({"name": "bid-private-profile", "private": True,
                                                      "type": "module", "dsh": {"profile": {"bundles": []}}}))
    rows = json.loads((ROOT / "runtime/profiles/bid.json").read_text())
    plugins = rows[0]["insert"]
    for item in plugins:
        if item["id"] == "sessions":
            item["config"]["root"] = str(home / "sessions")
    plugins.append({"id": "bid-business-tools", "name": (ROOT / "runtime/bid-plugin/dist/index.mjs").as_uri()})
    patch = path / "profile.patch.json"
    patch.write_text(json.dumps(rows, ensure_ascii=False, indent=2))
    session_id = f"bid-{os.environ['BID_ATTEMPT_ID']}"
    with FixtureModel(api, token, manifest, path / "wire.jsonl") as model:
        os.environ["BID_MODEL_URL"] = f"{model.url}/v1/messages"
        with DeepSeekHarness(provider="deepseek-official", model="bid-fixture", reasoning_effort="off",
                             max_tokens=2000, api_key="local-fixture-not-a-credential", base_url=model.url,
                             dsh_bin=str(source / "apps/cli/lib/bin.js"), dsh_home=str(home), profile="bid",
                             patches=(str(patch),), cwd=str(path), initialize_timeout_seconds=20,
                             request_timeout_seconds=10, shutdown_timeout_seconds=1) as harness:
            def stop(*_):
                harness.close()
                raise SystemExit(143)
            signal.signal(signal.SIGTERM, stop)
            (path / "binding.json").write_text(json.dumps({"session_id": session_id, "home": str(home),
                "build_hash": build["build_hash"], "profile_hash": hashlib.sha256(patch.read_bytes()).hexdigest()}))
            client = harness.client
            # session/prompt skips native command routing; command/skill plugins are absent as well.
            with client.subscribe_session_notifications(session_id) as subscription:
                client.session_prompt(session_id, [{"type": "text", "text": json.dumps(manifest, ensure_ascii=False)}])
                saw_event = False
                with (path / "events.jsonl").open("a") as events:
                    while True:
                        event = subscription.next(timeout_seconds=40)
                        payload = event.payload
                        if event.method == "session.event":
                            saw_event = True
                        events.write(json.dumps({"method": event.method, "payload": payload}, ensure_ascii=False) + "\n")
                        events.flush()
                        if saw_event and event.method == "session.status" and payload.get("status") == "idle":
                            break


if __name__ == "__main__":
    main()
