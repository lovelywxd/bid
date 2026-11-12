"""Local deterministic provider fixture, used THROUGH the actual Harness loop."""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx


def chunks(tool=None, args=None, call_id="call-fixture"):
    rows = [{"type": "message_start", "message": {"id": "fixture", "model": "bid-fixture",
             "usage": {"input_tokens": 3, "output_tokens": 0}}}]
    if tool:
        rows += [{"type": "content_block_start", "index": 0,
                  "content_block": {"type": "tool_use", "id": call_id, "name": tool, "input": {}}},
                 {"type": "content_block_delta", "index": 0,
                  "delta": {"type": "input_json_delta", "partial_json": json.dumps(args, ensure_ascii=False)}}]
    else:
        rows += [{"type": "content_block_start", "index": 0,
                  "content_block": {"type": "text", "text": "工程候选已提交，业务内容未验收。"}}]
    return rows + [{"type": "content_block_stop", "index": 0},
                   {"type": "message_delta", "delta": {"stop_reason": "tool_use" if tool else "end_turn"},
                    "usage": {"output_tokens": 3}}, {"type": "message_stop"}]


class FixtureModel:
    def __init__(self, api, token, manifest, evidence_path):
        self.api, self.token, self.manifest = api, token, manifest
        self.path = evidence_path
        self.count = 0
        self.sent_ids = set()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self.handler())
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server.server_port}/anthropic"

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)

    def handler(self):
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["content-length"])))
                request_id = self.headers.get("x-bid-request-id")
                if not request_id or request_id in owner.sent_ids:
                    self.send_error(403, "one permit per send required")
                    return
                owner.sent_ids.add(request_id)
                owner.count += 1
                with owner.path.open("a") as stream:
                    stream.write(json.dumps({"request_id": request_id, "body": body}, ensure_ascii=False) + "\n")
                scenario = owner.manifest["contract"]["scenario"]
                if scenario == "handoff":
                    scenario = "forbidden_tool" if owner.manifest["epoch"] == 1 else "normal"
                headers = {"authorization": f"Bearer {owner.token}"}
                if scenario == "retry" and owner.count == 1:
                    self.send_response(503)
                    self.send_header("content-type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"type":"error","error":{"type":"overloaded_error","message":"fixture transient"}}')
                    httpx.post(f"{owner.api}/internal/settle", headers=headers,
                               json={"request_id": request_id, "usage": None})
                    return
                if scenario == "slow":
                    time.sleep(5)
                calls, results = [], {}
                for message in body["messages"]:
                    for block in message.get("content", []):
                        if block.get("type") == "tool_use":
                            calls.append(block)
                        if block.get("type") == "tool_result":
                            text = block.get("content", [])
                            try:
                                result_text = text if isinstance(text, str) else "".join(x.get("text", "") for x in text)
                                results[block["tool_use_id"]] = json.loads(result_text)
                            except (ValueError, TypeError):
                                results[block["tool_use_id"]] = {"error": result_text}
                refs = owner.manifest["contract"]["source_refs"]
                if not calls:
                    rows = chunks("read_sources", {"source_ids": refs}, "read")
                elif calls[-1]["id"] == "late-read":
                    rows = chunks()
                elif calls[-1]["name"] == "read_sources":
                    if scenario == "forbidden_tool":
                        rows = chunks("bash", {"command": "echo unauthorized"}, "denied")
                    else:
                        payload = {"kind": "engineering_probe", "blocks": [{"block_id": "probe-1",
                                   "text": "合成工程候选，仅核对来源与提交协议。"}],
                                   "source_refs": ["fake-source"] if scenario == "bad_reference" else refs,
                                   "coverage_ids": refs}
                        rows = chunks("save_candidate", {"candidate": payload}, "save")
                elif calls[-1]["name"] == "save_candidate":
                    result = results.get(calls[-1]["id"], {})
                    if "candidate_id" in result:
                        rows = chunks("finish_candidate", result, "finish")
                    else:
                        rows = chunks()
                elif calls[-1]["name"] == "finish_candidate" and scenario == "after_finish":
                    rows = chunks("read_sources", {"source_ids": refs}, "late-read")
                else:
                    rows = chunks()
                self.send_response(200)
                self.send_header("content-type", "text/event-stream")
                self.end_headers()
                try:
                    for row in rows:
                        self.wfile.write(f"event: {row['type']}\ndata: {json.dumps(row, ensure_ascii=False)}\n\n".encode())
                    self.wfile.flush()
                    httpx.post(f"{owner.api}/internal/settle", headers=headers,
                               json={"request_id": request_id, "usage": {"input_tokens": 3, "output_tokens": 3}})
                except (BrokenPipeError, ConnectionResetError):
                    pass  # cancellation keeps the reservation unknown

            def log_message(self, *_):
                pass

        return Handler
