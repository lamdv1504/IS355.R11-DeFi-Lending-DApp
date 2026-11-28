"""L05 WalletClient against real Q05 HTTP/auth/PDF/confirm. RPC and MetaMask are test doubles.
Runs with random ephemeral test accounts; never imports user wallets or broadcasts a chain tx.
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
import uvicorn
from fastapi import Request
from web3 import Web3

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from test_q05_api_auth_rbac import api_env  # noqa: E402

def main() -> None:
    with tempfile.TemporaryDirectory(prefix="l05-api-") as directory:
        fixture = api_env.__wrapped__(Path(directory))
        app, service = fixture["client"].app, fixture["web3"]
        original_build = service.build_unsigned_transaction
        abis = {name: json.loads((ROOT / "deployments/abi" / (name + ".json")).read_text(encoding="utf-8")) for name in service.registry["contracts"]}
        contracts = {name: Web3().eth.contract(abi=abi["abi"] if isinstance(abi, dict) else abi) for name, abi in abis.items()}
        def build(name, method, args, **kwargs):
            result = original_build(name, method, args, **kwargs)
            result["transaction"]["data"] = contracts[name].encode_abi(method, args=list(args))
            result["transaction"]["gasPrice"] = 1
            gas = result["gas_quote"]
            pending = gas["estimation_status"] == "PENDING_APPROVAL"
            gas.update(estimated_fee_wei=None if pending else "80000", max_fee_wei=None if pending else "100000",
                       estimated_fee_eth=None if pending else "0.00000000000008", max_fee_eth=None if pending else "0.0000000000001")
            return result
        service.build_unsigned_transaction = build
        receipts = {}
        # Only added to this isolated test app; absent from backend.main production app.
        @app.post("/__l05_test__/broadcast")
        async def broadcast(request: Request):
            tx = await request.json()
            tx_hash = "0x" + format(len(receipts) + 1, "064x")
            name = next(name for name, entry in service.registry["contracts"].items() if entry["address"].lower() == tx["to"].lower())
            function, args = contracts[name].decode_function_input(tx["data"])
            service.w3.eth.transaction = {**tx, "value": int(tx["value"], 16), "input": tx["data"]}
            receipt = {"status": 1, "transactionHash": tx_hash, "blockNumber": 11 + len(receipts)}
            service.w3.eth.receipt = receipt
            receipts[tx_hash] = {"status": "0x1", "transactionHash": tx_hash, "blockNumber": hex(receipt["blockNumber"])}
            if name == "MyUSDT" and function.fn_name == "approve":
                service.myusdt_allowance_wad = int(list(args.values())[1])
            if name == "LendingPool" and function.fn_name == "borrow":
                amount, cid = list(args.values())
                service.borrow_receipt_events = [{"address": service.registry["contracts"]["LendingPool"]["address"],
                    "args": {"borrower": tx["from"], "amountWad": amount, "agreementCid": cid}}]
            return {"hash": tx_hash}
        @app.get("/__l05_test__/receipt/{tx_hash}")
        async def receipt(tx_hash: str):
            return receipts.get(tx_hash)
        sock = socket.socket(); sock.bind(("127.0.0.1", 0)); sock.listen()
        base = "http://127.0.0.1:" + str(sock.getsockname()[1])
        server = uvicorn.Server(uvicorn.Config(app, log_level="error", access_log=False))
        thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
        thread.start()
        try:
            for _ in range(100):
                if server.started: break
                time.sleep(0.05)
            assert server.started
            # Random fixture key only, carried through the child environment and never logged.
            context = {"base": base, "test_key": fixture["owner"].key.hex(), "contracts": service.registry["contracts"]}
            result = subprocess.run(["node", "--experimental-strip-types", str(ROOT / "frontend/tests/wallet-api.integration.ts")],
                cwd=ROOT, env={**os.environ, "L05_TEST_CONTEXT": json.dumps(context)}, capture_output=True, text=True, encoding="utf-8", timeout=90)
            if result.returncode: raise RuntimeError(result.stdout + result.stderr)
            evidence = json.loads(result.stdout)
            output = ROOT / "reports/Lam/l05/api-wallet.json"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print("PASS: " + str(len(evidence["checks"])) + " L05 real Q05 HTTP checks; EIP-1193/RPC are isolated test doubles.")
        finally:
            server.should_exit = True; thread.join(timeout=10); sock.close()
if __name__ == "__main__": main()
