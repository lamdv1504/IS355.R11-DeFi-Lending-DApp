#!/usr/bin/env bash
set -euo pipefail

echo "============================================================================"
echo "Starting Hardhat Local Blockchain Node (Chain ID: 31337, RPC: 127.0.0.1:8545)"
echo "WARNING: Local test accounts and private keys are FOR LOCAL DEV ONLY!"
echo "============================================================================"
npx hardhat node --hostname 127.0.0.1 --port 8545
