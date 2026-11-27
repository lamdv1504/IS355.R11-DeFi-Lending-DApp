# Q06 - One-Click Local Deploy & Sepolia Deployment Handoff

## What is delivered

- `scripts/deploy_and_seed.py` deploys the seven checked-in ABI/bytecode artifacts
  without reading any old contract addresses:
  `MyUSDT` -> the four NFT/token contracts -> `LendingPool` -> pool-binding
  calls -> `PriceOracle` -> `LendingPool.setPriceOracle()`.
- `scripts/deploy_sepolia.py` uses a dedicated Sepolia key/RPC, verifies the
  configured chain and positive deployer ETH balance, deploys and binds the
  same seven contracts, and runs an on-chain faucet/lend/collateral/borrow/repay
  smoke test.
- `scripts/start_all.bat` and `scripts/start_all.sh` start Hardhat, wait for
  chain ID `31337`, deploy/seed and publish the Q04 simulated audit record,
  then start FastAPI (`8000`) and Next.js (`3000`).
- Both deploy paths atomically write their deployment manifest, update only
  the target network in `backend/config/contracts.json`, preserve the other
  backend network, and generate `frontend/src/config/contracts.json` with the
  ABI arrays required by the frontend.

## Local one-click use

Install the project's existing dependencies and copy `.env.example` to `.env`.
The local path uses the standard public Hardhat test mnemonic unless
`LOCAL_MNEMONIC` is set. Those deterministic keys are development-only and
must never be used on Sepolia or any real network.

The Q04 Audit Logs operation needs `DOCUMENT_AES_KEY_HEX` because the Q04
service initializes its AES-GCM encryptor even though the audit artifact itself
is public and unencrypted. A valid local IPFS fallback store is used; Kubo is
optional. Configure `IPFS_LOCAL_STORE_DIR` if local artifacts should be kept
outside the default repository data folder.

Windows:

```powershell
scripts\start_all.bat
```

Linux/macOS:

```bash
bash scripts/start_all.sh
```

For deployment/seed without starting the app services:

```powershell
npx hardhat node --hostname 127.0.0.1 --port 8545
python scripts\deploy_and_seed.py
```

Expected local seed state:

- Test accounts 1-9 receive `1,000 MyUSDT` each through `MyUSDT.faucet()`;
  account 0 retains the contract's initial supply.
- `CollateralNFT` token `#1` belongs to Lender A and token `#2` belongs to
  Borrower A. They are minted with `1,000 WAD` collateral valuation and are not
  silently deposited into the Pool.
- Lender A approves and deposits `1,000 MyUSDT`; this initializes the Pool's
  liquidity and creates lender position `#1`.
- Q04 publishes public Audit Logs JSON and CSV through local-fallback IPFS,
  with at least one historical seed period labeled `SIMULATED`.
- `deployments/localhost.json` stores deployment, binding, seed, transaction,
  and audit CID information. The frontend registry contains all seven ABI
  arrays as well as current addresses and deploy transaction hashes.

The script deploys fresh bytecode every time. For a state reset, stop the
existing Hardhat process and start a fresh node before running it again. It
does not reuse or require current `contracts.json` addresses for deployment.

## Sepolia safety and smoke test

Configure these values in an environment or a local, untracked `.env`:

```dotenv
ACTIVE_NETWORK=sepolia
SEPOLIA_RPC_URL=https://<your-sepolia-rpc>
SEPOLIA_CHAIN_ID=11155111
SEPOLIA_EXPLORER_URL=https://sepolia.etherscan.io
SEPOLIA_DEPLOYER_PRIVATE_KEY=<dedicated-funded-sepolia-key>
DOCUMENT_AES_KEY_HEX=<32-byte-key-for-application-documents>
```

Run the deploy only when deliberately deploying to the public testnet:

```powershell
python scripts\deploy_sepolia.py
```

The script fails with Vietnamese diagnostics if the RPC or key is missing,
the RPC is unreachable or is not Chain ID `11155111`, the key is invalid or is
one of the standard Hardhat development keys, or the deployer has no Sepolia
ETH. The private key is read from the process environment and is never written
to the manifests.

The smoke sequence uses the deployer as lender and borrower: faucet 1,000
MyUSDT, approve/deposit 500 MyUSDT to the Pool, mint/approve/deposit a
1,000-WAD CollateralNFT, borrow 100 MyUSDT, approve a repayment buffer and
repay the whole accrued debt. `deployments/sepolia.json` records every contract
address, deployment transaction, block and Etherscan URL plus each smoke-test
transaction and URL. The deployer must have enough test ETH for seven
deployments, bindings, and all smoke transactions; the script only checks that
the initial balance is nonzero.

## Generated configuration contract

`backend/config/contracts.json` keeps its `{local, sepolia}` registry and
updates only the network deployed by the script. Every contract record has its
address, artifact-relative `abiPath`, deployment `txHash`, and explorer URL.
`deployments/{localhost,sepolia}.json` contains the fuller deployment receipt
and binding records. The frontend file is intentionally self-contained:

```json
{
  "network": "local",
  "chainId": 31337,
  "explorerUrl": "http://127.0.0.1:8545",
  "contracts": {
    "LendingPool": {
      "address": "0x...",
      "txHash": "0x...",
      "abi": []
    }
  }
}
```

The exact structure applies to both local and Sepolia; the generated ABI is the
canonical array from `deployments/abi/<Contract>.json`. Generated manifests
contain addresses and transaction metadata only, never private keys.

## Validation and integration

Focused, network-independent tests:

```powershell
pytest tests/test_q06_deploy_and_seed.py -q
```

The tests verify contract order/bindings, local faucet and NFT/Pool seed calls,
all three config outputs and ABI parity, preservation of the untouched
network's backend registry, Sepolia missing-env/key guards, and the positive
deployer-balance prerequisite. They do not broadcast transactions to Hardhat
or Sepolia.

For an actual local integration check, start Hardhat and run `start_all.bat`
or `start_all.sh`, then verify:

1. `/health` responds on `http://127.0.0.1:8000/health`.
2. `frontend/src/config/contracts.json` shows chain ID `31337` and deployed
   addresses that have non-empty bytecode.
3. Lender A has a `1,000 MyUSDT` position and its LendingPositionNFT; Borrower
   A owns CollateralNFT `#2`.
4. The Q04 `auditLogs.json.cid` can be fetched from the configured IPFS
   fallback and its payload has `SIMULATED` entries.
5. To verify Sepolia, run the script only with the funded dedicated test
   wallet, then confirm deployment/smoke hashes using the Etherscan URLs in
   `deployments/sepolia.json`.

The `ipfs_storage/samples/audit_logs_sample.csv` file is not part of this task;
do not regenerate or normalize it as part of deployment.
