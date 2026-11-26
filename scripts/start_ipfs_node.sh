#!/usr/bin/env bash
# Start local IPFS Kubo daemon for IS355.R11 DeFi Lending DApp (H03)
# API: http://127.0.0.1:5001 | Local Gateway: http://127.0.0.1:8080/ipfs/<CID>
set -euo pipefail

if ! command -v ipfs >/dev/null 2>&1; then
  echo "[H03] IPFS Kubo CLI ('ipfs') was not found in PATH."
  echo "Install Kubo from https://docs.ipfs.tech/install/command-line/ or run via Docker:"
  echo "  docker run -d --name is355-ipfs-kubo -p 4001:4001 -p 127.0.0.1:8080:8080 -p 127.0.0.1:5001:5001 ipfs/kubo:latest"
  exit 1
fi

if [ ! -f "${IPFS_PATH:-$HOME/.ipfs}/config" ]; then
  echo "[H03] Initializing IPFS Kubo local repository..."
  ipfs init --profile=local-discovery
fi

echo "[H03] Configuring local CORS headers for DApp Frontend/Backend..."
ipfs config --json API.HTTPHeaders.Access-Control-Allow-Origin '["http://localhost:5173", "http://127.0.0.1:5173", "http://127.0.0.1:8000"]'
ipfs config --json API.HTTPHeaders.Access-Control-Allow-Methods '["PUT", "POST", "GET"]'

echo "[H03] Starting IPFS Kubo daemon (API :5001, Gateway :8080)..."
exec ipfs daemon

