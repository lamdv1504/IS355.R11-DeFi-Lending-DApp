#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
RPC_URL="http://127.0.0.1:8545"
NODE_PID=""
BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  for pid in "$FRONTEND_PID" "$BACKEND_PID" "$NODE_PID"; do
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
  done
}
trap cleanup EXIT INT TERM

echo "[Q06] Starting Hardhat node on 127.0.0.1:8545..."
npx hardhat node --hostname 127.0.0.1 --port 8545 &
NODE_PID=$!

echo "[Q06] Waiting for Hardhat JSON-RPC..."
RPC_READY=0
for _ in $(seq 1 45); do
  if curl --silent --show-error --max-time 2 \
    -H "Content-Type: application/json" \
    --data '{"jsonrpc":"2.0","method":"eth_chainId","params":[],"id":1}' \
    "$RPC_URL" | grep -q '"result":"0x7a69"'; then
    RPC_READY=1
    break
  fi
  sleep 2
done
if [[ "$RPC_READY" != "1" ]]; then
  echo "[Q06] ERROR: Hardhat RPC did not become ready within 90 seconds." >&2
  exit 1
fi

echo "[Q06] Deploying contracts, seeding local wallets, and publishing Q04 audit logs..."
python scripts/deploy_and_seed.py

echo "[Q06] Starting FastAPI on http://127.0.0.1:8000..."
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 &
BACKEND_PID=$!

echo "[Q06] Starting Next.js on http://127.0.0.1:3000..."
npm --prefix frontend run dev -- --hostname 127.0.0.1 --port 3000 &
FRONTEND_PID=$!

echo "[Q06] Services are running. Press Ctrl+C to stop them."
wait "$BACKEND_PID" "$FRONTEND_PID"
