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

## Q06 acceptance evidence

### Local reset (executed)

A fresh Hardhat node (`31337`) was started, then the seven contracts were
deployed and bound, local wallets/liquidity/NFTs were seeded, and Q04 wrote the
first simulated Audit Logs record to the local IPFS fallback. The full
start-RPC, deploy, seed, and audit-log command completed successfully in
**10.94 seconds** (target: at most 30 seconds). The generated manifest records
the addresses and deployment transaction hashes:

| Contract | Local address | Deployment txHash |
|---|---|---|
| MyUSDT | `0x5FbDB2315678afecb367f032d93F642f64180aa3` | `0x9705d97b58fe7114bcebab75253c7f2ada0e153c40a391332528f12b8b52476e` |
| CollateralNFT | `0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512` | `0xef35d6837cc652c7819423fef163f0daa9267a9046bf7126e88a06b37669cc16` |
| CollateralReceiptNFT | `0x9fE46736679d2D9a65F0992F2272dE9f3c7fa6e0` | `0x7bc31ab744f678da18fedd6ee964032b0cc6cb96a33ddb6718ec6b0f0b886fec` |
| DebtToken | `0xCf7Ed3AccA5a467e9e704C703E8D87F634fB0Fc9` | `0xd01d0019604bf3681834509ead0d3f35dd6a241cef02301ad29f3f6b4f8d4ab7` |
| LendingPositionNFT | `0xDc64a140Aa3E981100a9becA4E685f962f0cF6C9` | `0x900afe56eb54d707ef87619aa92119e27f47f827ae5d4d289fc414e726aa0992` |
| LendingPool | `0x5FC8d32690cc91D4c39d9d3abcBD16989F875707` | `0x3c67cbbe9380a302a9321e733bec77bdcbb867c31bc6fd3ae53dc311e6847485` |
| PriceOracle | `0x8A791620dd6260079BF849Dc5567aDC3F2FdC318` | `0x61554ac9216f1e59018268efd39601b9e6a5409106571363cdc916fbdfb4fc8e` |

These are ephemeral localhost addresses and hashes, **not Sepolia evidence**.
The Lender A seed deposited `1,000 MyUSDT`
(`0xd07e75862be3244b23d207a0d94e563f95b2b07cdc552e6c0b419571f037d6f5`);
the JSON audit record CID is
`bafkreifwuo3ocztcmgbe75cx5ndaia7ioafribzkzol7thq5gacgtyekzm`.

### Sepolia deployment and smoke test (executed)

The deployment and smoke test completed on chain ID `11155111`. All seven
contract addresses, deployment transaction hashes, and explorer URLs are
recorded in `deployments/sepolia.json` and synchronized to both application
registries:

| Contract | Sepolia address | Deployment txHash | Etherscan |
|---|---|---|---|
| MyUSDT | `0xAaB07940F52BB7C105D17681f896E648b8A39881` | `0x9f44c3e3b087ce4c77305efdfcdc7f786ab1f6d0d97f335cb5f1f5cd82f0ec8e` | [contract](https://sepolia.etherscan.io/address/0xAaB07940F52BB7C105D17681f896E648b8A39881) · [deploy tx](https://sepolia.etherscan.io/tx/0x9f44c3e3b087ce4c77305efdfcdc7f786ab1f6d0d97f335cb5f1f5cd82f0ec8e) |
| CollateralNFT | `0x19D6c92fd592f5B077189D4300a8737532506500` | `0xa1343649a5ecfca3647a3a6cc9f291d1de0ee67c1b382e7c9ea4da8e3654fc3c` | [contract](https://sepolia.etherscan.io/address/0x19D6c92fd592f5B077189D4300a8737532506500) · [deploy tx](https://sepolia.etherscan.io/tx/0xa1343649a5ecfca3647a3a6cc9f291d1de0ee67c1b382e7c9ea4da8e3654fc3c) |
| CollateralReceiptNFT | `0x37daF2FA967b3A72024Ad7ED0BBCe889ab63f858` | `0xf3621c54c7fff81621fe1a01a767caca0734fe8134375e570add4039ed921940` | [contract](https://sepolia.etherscan.io/address/0x37daF2FA967b3A72024Ad7ED0BBCe889ab63f858) · [deploy tx](https://sepolia.etherscan.io/tx/0xf3621c54c7fff81621fe1a01a767caca0734fe8134375e570add4039ed921940) |
| DebtToken | `0x5893DE5fe88057dBdE28672C9d85Dcf2FdAaBc92` | `0x711a426c32af6ac9dbc02dd7787766d882e1510ee2ddc10bd57c8241f9e64768` | [contract](https://sepolia.etherscan.io/address/0x5893DE5fe88057dBdE28672C9d85Dcf2FdAaBc92) · [deploy tx](https://sepolia.etherscan.io/tx/0x711a426c32af6ac9dbc02dd7787766d882e1510ee2ddc10bd57c8241f9e64768) |
| LendingPositionNFT | `0x288bD02c150b2eEC0FCB82331791AB2dcC37C79F` | `0xa7247f8f3dea94dc3f5e3b66f5bbd893b81fd4f409d287af627bc0b6a83d87a4` | [contract](https://sepolia.etherscan.io/address/0x288bD02c150b2eEC0FCB82331791AB2dcC37C79F) · [deploy tx](https://sepolia.etherscan.io/tx/0xa7247f8f3dea94dc3f5e3b66f5bbd893b81fd4f409d287af627bc0b6a83d87a4) |
| LendingPool | `0x2BC016744561Dca45a1398dF4309572ccB66a0c1` | `0x59dcb57103917c5357ccb7910dd8e0f34f5d4ab6e0232ecad00128306987dd19` | [contract](https://sepolia.etherscan.io/address/0x2BC016744561Dca45a1398dF4309572ccB66a0c1) · [deploy tx](https://sepolia.etherscan.io/tx/0x59dcb57103917c5357ccb7910dd8e0f34f5d4ab6e0232ecad00128306987dd19) |
| PriceOracle | `0x85cdeb0BA90C69006D61f13F131BC03f16Da484a` | `0x8a4fb3fc4f38d8e178a6a727f73af188391410cd9b93d5dc106aa2acd28dfb4f` | [contract](https://sepolia.etherscan.io/address/0x85cdeb0BA90C69006D61f13F131BC03f16Da484a) · [deploy tx](https://sepolia.etherscan.io/tx/0x8a4fb3fc4f38d8e178a6a727f73af188391410cd9b93d5dc106aa2acd28dfb4f) |

The verified smoke sequence deposited `500 MyUSDT`, deposited a valued NFT
collateral, borrowed `100 MyUSDT`, then repaid the full debt; the final on-chain
borrower debt is `0`. Key operation receipts:

| Action | txHash | Etherscan |
|---|---|---|
| depositLender | `0xca79806161e128a215c9a323e9d8f647cfa2b863e12c7010d156493ddbee6474` | [view tx](https://sepolia.etherscan.io/tx/0xca79806161e128a215c9a323e9d8f647cfa2b863e12c7010d156493ddbee6474) |
| depositCollateral | `0xe4c9bb82a72c2cf01290edf03eb8c9c8ffb9427a9556e782af07b1689d1f5196` | [view tx](https://sepolia.etherscan.io/tx/0xe4c9bb82a72c2cf01290edf03eb8c9c8ffb9427a9556e782af07b1689d1f5196) |
| borrow | `0xae4834106c6911370355a9018bdb78fc40bac5adc320c3a7d0ff80abef72bf8f` | [view tx](https://sepolia.etherscan.io/tx/0xae4834106c6911370355a9018bdb78fc40bac5adc320c3a7d0ff80abef72bf8f) |
| repay | `0x7b01aff9caae11dedcd9908ee60e713c477b21047cc5b0741a9370cec588157d` | [view tx](https://sepolia.etherscan.io/tx/0x7b01aff9caae11dedcd9908ee60e713c477b21047cc5b0741a9370cec588157d) |

One initial borrow transaction failed (`0xbd583320635a63711dbaeebcf8fe107226f92624933b24b9aa13df092041dcac`);
the subsequent borrow receipt above succeeded and the loan was fully repaid.
The failed receipt and retry setup transactions are retained in the manifest
for an auditable record. The first deployment invocation stopped during
transaction construction after six deployments; those confirmed contracts
were recovered from receipts and completed without deploying duplicate
contracts. The shared helper now retries bounded transient RPC/estimation
errors before signing or broadcasting.

The deployed addresses and receipts are synchronized to
`backend/config/contracts.json` (`sepolia`) and
`frontend/src/config/contracts.json`. TC1 Sepolia deployment and smoke-test
evidence is now **achieved**; localhost evidence remains separately labeled.

The local machine has no Kubo CLI or API daemon, so the executed local reset
used Q04's configured local fallback. `start_all.bat` now prefers the project
virtualenv Python and starts Kubo opportunistically when its CLI is installed;
if Kubo is unavailable, the local fallback remains available.

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
