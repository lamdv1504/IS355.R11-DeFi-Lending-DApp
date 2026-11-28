"""Verify L04's TypeScript adapter against the actual Q05 API with isolated local IPFS.
Uses Q05's test fixture for deterministic Web3 events; no live RPC/Pinata credentials.
Wallets/keys are random test-only accounts. Only short-lived session tokens reach Node.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import uvicorn
from eth_account import Account

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from test_q05_api_auth_rbac import api_env, _login  # noqa: E402

def main() -> None:
    with tempfile.TemporaryDirectory(prefix="l04-api-") as directory:
        fixture = api_env.__wrapped__(Path(directory))
        client = fixture["client"]
        headers = {role: _login(client, fixture[who]) for role, who in [("owner", "owner"), ("lender", "lender"), ("admin", "admin")]}
        headers["other"] = _login(client, Account.create())
        pdf = client.post("/api/ipfs/create-agreement", headers=headers["owner"], json={"principal_wad": str(500 * 10**18), "asset_description": "L04 integration test collateral"})
        assert pdf.status_code == 200, pdf.text
        credit = client.post("/api/ipfs/credit-report/" + fixture["owner"].address, headers=headers["owner"], json={"from_block": 0})
        assert credit.status_code == 200, credit.text
        audit = client.post("/api/ipfs/audit-logs", headers=headers["admin"], json={"from_block": 0, "seed_simulated_months": 6})
        assert audit.status_code == 200, audit.text
        metadata = client.get("/api/ipfs/documents", headers=headers["admin"]).json()["documents"]
        by_cid = {d["cid"]: d for d in metadata}
        sock = socket.socket(); sock.bind(("127.0.0.1", 0)); sock.listen()
        base_url = "http://127.0.0.1:" + str(sock.getsockname()[1])
        server = uvicorn.Server(uvicorn.Config(client.app, log_level="error", access_log=False))
        thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
        thread.start()
        try:
            for _ in range(100):
                if server.started: break
                time.sleep(0.05)
            assert server.started, "Local Q05 API did not start"
            context = {
                "base_url": base_url,
                "tokens": {role: header["Authorization"].removeprefix("Bearer ") for role, header in headers.items()},
                "documents": {name: by_cid[cid] for name, cid in {
                    "pdf": pdf.json()["cid"], "credit": credit.json()["cid"],
                    "audit_json": audit.json()["json"]["cid"], "audit_csv": audit.json()["csv"]["cid"],
                }.items()},
            }
            result = subprocess.run(["node", "--experimental-strip-types", str(ROOT / "frontend/tests/ipfs-api.integration.ts")],
                env={**os.environ, "L04_TEST_CONTEXT": json.dumps(context)}, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=60)
            if result.returncode:
                raise RuntimeError("L04 TypeScript/API integration failed:\n" + result.stdout + result.stderr)
            evidence = json.loads(result.stdout)
            output = ROOT / "reports/Lam/l04/api-rbac.json"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print("PASS: " + str(evidence["scenarios"]) + " real HTTP adapter scenarios; PDF/JSON/CSV, Guest/Lender/Other/Owner/Admin. Web3 event source is a test double.")
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            sock.close()

if __name__ == "__main__":
    main()
