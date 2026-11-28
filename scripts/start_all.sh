#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -x "$ROOT/.venv/bin/python" ]]; then
  PYTHON_EXE="$ROOT/.venv/bin/python"
elif [[ -x "$ROOT/.venv/Scripts/python.exe" ]]; then
  PYTHON_EXE="$ROOT/.venv/Scripts/python.exe"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_EXE="python3"
else
  PYTHON_EXE="python"
fi

RPC_URL="http://127.0.0.1:8545"
IPFS_API_URL="${IPFS_LOCAL_API_URL:-http://127.0.0.1:5001}"
IPFS_PID=""
NODE_PID=""
BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  for pid in "$FRONTEND_PID" "$BACKEND_PID" "$NODE_PID" "$IPFS_PID"; do
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
  done
}
trap cleanup EXIT INT TERM

fallback_if_kubo_unavailable() {
  if [[ "${IPFS_PROVIDER:-}" == "kubo" ]] || [[ "${IPFS_PROVIDER:-}" == "KUBO" ]]; then
    export IPFS_PROVIDER="local_fallback"
    echo "[Q06] IPFS_PROVIDER changed to local_fallback for this run."
    return 0
  fi
  if [[ -f "$ROOT/.env" ]] && grep -Eiq '^[[:space:]]*IPFS_PROVIDER[[:space:]]*=[[:space:]]*kubo[[:space:]]*$' "$ROOT/.env"; then
    export IPFS_PROVIDER="local_fallback"
    echo "[Q06] .env requests Kubo but the daemon is unavailable; using local_fallback for this run."
  fi
}

if ! command -v ipfs >/dev/null 2>&1; then
  echo "[Q06] IPFS Kubo CLI not found; Q04 will use configured Pinata or local fallback store."
  fallback_if_kubo_unavailable
else
  if curl --silent --max-time 2 -X POST "${IPFS_API_URL%/}/api/v0/id" | grep -q '"ID"'; then
    echo "[Q06] Existing IPFS Kubo daemon is ready."
  else
    echo "[Q06] Starting optional IPFS Kubo daemon..."
    ipfs daemon >/tmp/is355_ipfs_kubo.log 2>&1 &
    IPFS_PID=$!
    IPFS_READY=0
    for _ in $(seq 1 10); do
      if curl --silent --max-time 2 -X POST "${IPFS_API_URL%/}/api/v0/id" | grep -q '"ID"'; then
        IPFS_READY=1
        break
      fi
      sleep 1
    done
    if [[ "$IPFS_READY" != "1" ]]; then
      echo "[Q06] Kubo API is unavailable; continuing with configured Pinata or local fallback store."
      fallback_if_kubo_unavailable
    else
      echo "[Q06] IPFS Kubo daemon is ready."
    fi
  fi
fi

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
"$PYTHON_EXE" scripts/deploy_and_seed.py

echo "[Q06] Starting FastAPI on http://127.0.0.1:8000..."
"$PYTHON_EXE" -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 &
BACKEND_PID=$!

echo "[Q06] Starting Next.js on http://127.0.0.1:3000..."
npm --prefix frontend run dev -- --hostname 127.0.0.1 --port 3000 &
FRONTEND_PID=$!

echo "[Q06] Services are running. Press Ctrl+C to stop them."
wait "$BACKEND_PID" "$FRONTEND_PID"
