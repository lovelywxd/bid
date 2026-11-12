"""Create synthetic project and queue an actual Harness combination probe."""
import json
import sys
import uuid

import httpx

api = "http://127.0.0.1:8765/api"
headers = {"x-bid-local": "1"}
with httpx.Client(headers=headers, timeout=20) as client:
    def post(path, data):
        response = client.post(api + path, json=data)
        response.raise_for_status()
        return response.json()

    p = post("/projects", {"name": "工程验收合成项目", "customer": "合成客户", "enterprise": "合成企业"})
    source = post(f"/projects/{p['id']}/revisions", {
        "request_id": uuid.uuid4().hex, "logical_id": "source-1", "kind": "source",
        "payload": {"synthetic": True, "text": "服务期为三年；仅在用户确认后生效，未经批准不得增加承诺。",
                    "locator": "fixture/page-1/paragraph-1"},
        "actor": "fixture-runner", "reason": "工程合成输入"})
    run = post(f"/projects/{p['id']}/runs", {"request_id": uuid.uuid4().hex,
               "expected_generation": source["generation"], "source_ids": [source["id"]],
               "scenario": sys.argv[1] if len(sys.argv) > 1 else "normal"})
    print(json.dumps({"project": p, "run": run}, ensure_ascii=False))
