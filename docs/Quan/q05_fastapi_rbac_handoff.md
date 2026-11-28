# Q05 - FastAPI, MetaMask Nonce Auth & RBAC Handoff

## Security and session model

Q05 exposes the API from `backend/main.py`. It never accepts or stores a
user's private key. A client requests a one-use challenge, signs the exact
returned `message` using MetaMask's EIP-191 `personal_sign` flow, and submits
the signature to the verification endpoint. The backend recovers the signer
with `encode_defunct` and `Account.recover_message`; a successful verification
consumes the nonce and returns a short-lived HMAC-SHA256 bearer token.

The challenge is bound to the checksummed wallet address, configured domain,
chain ID and nonce TTL. Session tokens include the wallet, chain, server-mapped
roles, issue/expiry times, and session ID. They are URL-safe Base64 payloads
authenticated with stdlib `hmac`/`hashlib`; they are not JWTs. Role claims are
derived only from server configuration:

```dotenv
AUTH_TOKEN_SECRET=<at-least-32-random-bytes>
AUTH_DOMAIN=localhost
AUTH_NONCE_TTL_SECONDS=300
AUTH_SESSION_TTL_SECONDS=3600
ADMIN_WALLETS=0x...
LENDER_WALLETS=0x...
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
```

Set `AUTH_TOKEN_SECRET` through a secret manager or environment configuration;
the API returns 503 for authentication when it is absent or shorter than 32
bytes. Do not commit the value. Wallets in `ADMIN_WALLETS` map to `ADMIN`,
wallets in `LENDER_WALLETS` map to `LENDER`, and other verified wallets map to
`BORROWER`. Client-supplied role values are never used. `http://localhost:3000`
is allowed in addition to configured CORS origins.

## Endpoint contract

| Endpoint | Access | Behavior |
|---|---|---|
| `POST /api/auth/nonce` | Public | `{wallet_address, chain_id, domain?}` -> nonce and exact EIP-191 message |
| `POST /api/auth/verify` | Public | `{wallet_address, chain_id, domain?, nonce, signature}` -> bearer session |
| `GET /api/pool?network=local\|sepolia` | Public | Pool totals/liquidity, APR/APY snapshot, `block_number`, and `as_of_timestamp` |
| `GET /api/analytics/rates?network=...` | Public | Current pool/rate snapshot plus monthly `series` (`SIMULATED` + `ON_CHAIN`) for charts |
| `GET /api/accounts/{address}/lending-positions` | Public on-chain data | Current LendingPositionNFT ownership and claimable values (optional `?network=`) |
| `GET /api/accounts/{address}/loan` | Public on-chain data | Loan position, risk, LTV, borrowing capacity, accrued interest, and `liquidation_preview` |
| `GET /api/accounts/{address}/balances` | Public on-chain data | MyUSDT/DebtToken balances, NFT counts, receipt, pool allowance (optional `?network=`) |
| `POST /api/transactions/prepare` | Verified wallet | Builds unsigned tx (including `TRANSFER_LENDING_POSITION_NFT` and `DEPOSIT_COLLATERAL` with NFT `tokenId >= 0`), `gas_quote`, `interest_quote`, `context`, `availability`, `allowance`, and `preview` (`resulting_ltv`, `resulting_hf`) |
| `POST /api/transactions/confirm` | Prepared-intent wallet | Checks mined transaction/receipt against the server-side prepare intent |
| `POST /api/ipfs/create-agreement` | Verified borrower | Creates a private encrypted pre-borrow agreement |
| `POST /api/ipfs/credit-report/{address}` | Owner/Admin | Generates an encrypted credit report |
| `POST /api/ipfs/audit-logs` | Admin | Publishes public monthly JSON and CSV audit logs |
| `GET /api/ipfs/documents` | Optional session | Lists public documents and private documents visible to owner/Admin |
| `GET /api/ipfs/documents/{cid}/retrieve` | Optional session | Applies document RBAC; returns plaintext only after authorization |
| `POST /api/demo/time` | Admin, local only | Advances local Hardhat time |

Private agreement and report retrieval semantics match H03: unauthenticated
Guest receives `401`, a different borrower or lender receives `403`, and the
document owner or Admin receives `200`. Public audit JSON/CSV are readable by
Guest. `X-Content-SHA256` accompanies retrieved documents. Private IPFS CIDs
resolve to AES-256-GCM ciphertext at the raw gateway; decryption is performed
only after backend authorization.

## Route synchronization with Excel plan (L01 canonical vs Excel Q05 draft)

The implemented Q05 routes follow the team-agreed `docs/Lam/l01_api_contract.md`
specification rather than the early draft path names in `Kế_hoạch_Blockchain.xlsx`:

| Early Excel Q05 draft | Canonical L01 / Q05 route |
|---|---|
| `GET /api/pool-overview` | `GET /api/pool?network=local\|sepolia` |
| `POST /api/tx/prepare-*` | `POST /api/transactions/prepare` (dispatched by `action`, including `TRANSFER_LENDING_POSITION_NFT`) + `POST /api/transactions/confirm` |
| `POST /api/demo/fast-forward-time` | `POST /api/demo/time` |
| Monthly rate history | `GET /api/analytics/rates?network=local\|sepolia&seed_simulated_months=6` (`series` array with `SIMULATED` and `ON_CHAIN` provenance) |
| IPFS document endpoints | `POST /api/ipfs/create-agreement`, `POST /api/ipfs/credit-report/{address}`, `POST /api/ipfs/audit-logs`, `GET /api/ipfs/documents`, `GET /api/ipfs/documents/{cid}/retrieve` |

Collateral & repayment rule note: `LendingPool.repay()` automatically releases
collateral and settles `CollateralReceiptNFT` when remaining debt reaches `0`.
`WITHDRAW_COLLATERAL` (`LendingPool.withdrawCollateral()`) is used only when
`totalDebt == 0` while collateral is still locked (for example, after depositing
collateral before borrowing).

## Unsigned transaction flow

Prepare requests accept the L01 envelope (`network`, `chain_id`, `account`,
`action`, and `args`) as well as the equivalent flattened Q05 fields:

```json
{
  "network": "local",
  "chain_id": 31337,
  "account": "0xBorrowerWallet",
  "action": "BORROW",
  "args": {
    "amount_wad": "100000000000000000000",
    "agreement_cid": "bafy..."
  },
  "duration_seconds": 31536000
}
```

The prepare response contains:

```json
{
  "intent_id": "opaque-short-lived-id",
  "unsignedTransaction": {
    "from": "0xBorrowerWallet",
    "to": "0xLendingPool",
    "data": "0x...",
    "value": 0,
    "chainId": 31337,
    "gas": 120000,
    "gasPrice": 1000000000
  },
  "gas_quote": {
    "estimated_gas": 100000,
    "estimated_fee_wei": "100000000000000"
  },
  "interest_quote": {
    "apr": {"rate_basis": "simple_apr"},
    "apy_reference_percent": 7.2501
  },
  "signing": "client_wallet"
}
```

The frontend must submit `unsignedTransaction` to MetaMask (for example
`ethereum.request({method: "eth_sendTransaction", params: [tx]})`) and then
send `{intent_id, tx_hash}` to `/api/transactions/confirm`. Do not send a user
private key to the backend or call `sign_system_transaction()` for a browser
wallet. The backend checks sender, destination, input, chain and receipt
success against the short-lived prepared intent. For `BORROW`, it also verifies
the expected `LoanBorrowed` event and only then appends the Q03
`LoanTxBindingRecord`.

The APR returned in the quote is simple interest accrued per second by the
contracts. APY is explicitly labeled as a daily-compounded reference and is
not the protocol accrual model. Amounts use WAD integer strings and rates use
BPS (`10_000` BPS = 100%).

## Network and historical scan notes

- Time travel and `MOCK_ORACLE_MULTIPLIER` preparation are rejected unless the
  configured Web3 service network is `local`; HI04 additionally validates
  Hardhat chain ID `31337`.
- Historical event endpoints accept `from_block`. Local mode defaults it to
  zero; on Sepolia callers must provide a non-negative `from_block` so API
  requests do not start an unbounded scan from genesis.
- `ContractNotDeployedError` / contract configuration problems map to `503`,
  transaction input validation to `422`, private-document authentication to
  `401`, and authenticated access denial to `403`. Solidity custom errors use
  the shared decoder in `backend/config/errors.py`.
- Q03 and Q04 local JSON indexes are protected by per-path `threading.Lock`
  instances in `backend/api/dependencies.py`. Use durable, access-controlled
  storage for production deployments; this local index is not a distributed
  database.

## Frontend integration handoff (L03-L05)

- Call `/api/auth/nonce` after wallet connection and sign the returned message
  exactly; do not reconstruct or modify the challenge.
- Keep the bearer token in the frontend's session lifecycle and include
  `Authorization: Bearer <token>` on private API calls. Do not persist
  signatures or keys server-side.
- Use `GET /api/pool` and `/api/analytics/rates` for pool state. Present simple
  APR separately from reference APY and label WAD/BPS consistently.
- Create the agreement before preparing `BORROW`; pass its CID in the borrow
  intent. Only the successful confirm response represents a completed
  CID/loan/transaction binding.
- Use the document listing/retrieve endpoints for the IPFS hub. Show
  `SIMULATED` and `ON_CHAIN` audit rows distinctly; the audit payload is
  aggregate and `contains_pii=false`.
- Admin controls must be hidden in the UI for convenience, but server routes
  remain the authority for role checks.

## Tests and local verification

The focused suite is:

```powershell
pytest tests/test_q05_api_auth_rbac.py
```

It exercises signature replay prevention, 200/401/403 behavior, account
ownership, unsigned borrow prepare/confirm and Q03 receipt binding, local-only
guards, encrypted agreement/credit-report retrieval and public audit JSON/CSV
integrity. Existing contract/service tests remain part of the regression run.

For manual Hardhat integration:

1. Configure `AUTH_TOKEN_SECRET` (32+ random bytes), `DOCUMENT_AES_KEY_HEX`,
   `ACTIVE_NETWORK=local`, and local IPFS settings.
2. Start the Hardhat node and deploy the current contracts; confirm
   `backend/config/contracts.json` points to the current node deployment.
3. Start the API and frontend on `http://localhost:3000`; verify CORS and
   request an auth nonce for the connected wallet.
4. Sign and verify the nonce in MetaMask, then check pool/account reads.
5. Create an agreement, prepare a borrow transaction, sign it in MetaMask, and
   confirm the receipt; inspect the Q03 index for the CID/loan/tx binding.
6. Generate a credit report and audit logs, then test owner, other-wallet,
   lender, admin, and guest retrieval outcomes.
7. Switch to Sepolia configuration and verify `/api/demo/time` and mock Oracle
   prepare are blocked; provide bounded `from_block` values for history reads.
