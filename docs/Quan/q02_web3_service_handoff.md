# Q02 - Web3Service handoff

## Scope and trust boundary

`backend/services/web3_service.py` exposes read-only LendingPool/token/NFT views,
an unsigned transaction builder for browser wallets, and a separate signing
method reserved for configured automation. Backend APIs must never accept,
persist, or process a user's private key or seed phrase. User transactions are
signed by MetaMask (or another client wallet), not `sign_system_transaction()`.

All token amounts and cumulative indices are returned as `{ "wad": "<integer>",
"display": "<decimal>" }` using WAD = `1e18`. Rates use BPS = `10000`.
On-chain interest accrues as simple APR per second; APY is labeled as a daily
compounding reference and is not the protocol accrual model. A zero debt value
is preserved as zero for debt/interest views, and risk helpers report an
infinite health factor for zero debt.

## Read methods

- Pool: `get_pool_info()`, `get_available_liquidity()`,
  `get_interest_rate_snapshot()`.
- Borrower: `get_borrower_risk(address)`, `get_max_borrowable(address)`,
  `get_remaining_borrow_capacity(address)`, `get_available_to_borrow(address)`,
  `get_current_ltv_bps(address)`, `calculate_accrued_interest(address)`,
  `preview_borrower_interest(address, extra_seconds)`,
  `get_loan_position(address)`.
- Lender: `get_lender_position(position_id)`,
  `get_lender_earned_interest(position_id)`,
  `preview_lender_earned_interest(position_id, extra_seconds)`,
  `get_lender_claimable_balance(position_id)`, `get_max_withdrawable(position_id)`.
- Tokens/NFTs: `get_myusdt_balance(address)`,
  `get_myusdt_allowance(owner, spender)`, `get_debt_token_balance(address)`,
  `get_lending_position_owner(token_id)`,
  `get_active_collateral_receipt(borrower)`,
  `get_collateral_receipt_info(receipt_id)`,
  `get_collateral_nft_owner(token_id)`,
  `get_collateral_nft_valuation(token_id)`.
- Oracle: `get_oracle_price()` (available once a deployed PriceOracle is registered).

`get_contract()` validates the configured address and requires non-empty runtime
bytecode. A configured address with no code raises `ContractNotDeployedError`,
which also indicates that the local Hardhat node may have restarted.

## Unsigned MetaMask flow (Q05, Lâm L02/L05)

The client sends a wallet address and the requested contract operation to the
backend. The backend returns a quote, but does not request wallet credentials:

```json
{
  "unsignedTransaction": {
    "from": "0xClientWallet",
    "to": "0xConfiguredContract",
    "data": "0xEncodedContractCall",
    "value": 0,
    "chainId": 31337,
    "gas": 25200,
    "gasPrice": 1000000000
  },
  "gas_quote": {
    "estimated_gas": 21000,
    "gas_limit": 25200,
    "gas_price_wei": "1000000000",
    "estimated_fee_wei": "21000000000000",
    "estimated_fee_eth": "0.000021",
    "eth_usd_price": null,
    "estimated_fee_usd": null
  },
  "interest_quote": null,
  "signing": "client_wallet"
}
```

In the current Python response, the transaction is under `transaction`; clients
may expose/map that property as `unsignedTransaction` in their API contract.
The backend calculates transaction data, calls `estimate_gas()`, adds the gas
buffer, reads `gas_price`, and can include an optional ETH/USD fee estimate and
simple-interest quote. It does not submit or sign the client transaction.

Client sequence:

1. Connect the user's wallet and verify its chain ID matches the selected
   network (31337 for local Hardhat).
2. Request the unsigned quote with the connected wallet address.
3. Show the APR (simple, per-second) and optional APY reference separately,
   along with gas/interest estimates; obtain user approval.
4. Pass `transaction` to the connected provider's `eth_sendTransaction`.
   MetaMask performs the signature and broadcast; the client tracks the hash.
5. Refresh read views after confirmation.

`build_unsigned_transaction()` remains the browser-wallet path.
`sign_system_transaction()` is isolated to bot/script usage and signs only with
the configured `LOCAL_SYSTEM_PRIVATE_KEY` or `SEPOLIA_DEPLOYER_PRIVATE_KEY`;
it fills a missing nonce from the connected RPC.

## Deployment and handoff status

`PriceOracle` (`HI05`) is intentionally not registered with a live local
address yet. Connect the real address as soon as Hiếu merges HI05; until then,
`get_oracle_price()` correctly reports that PriceOracle has no deployment
address. Do not substitute or deploy a mock oracle for this handoff.

Focused offline test status is recorded after running:

```powershell
pytest tests/test_q02_web3_service.py tests/test_hi01_constants.py
```

For local integration after changes to the node or deployments:

1. Start the Hardhat node in one terminal with `npm run node`.
2. In another terminal, confirm RPC chain ID 31337 and deploy the project
   contracts using the repository's deployment scripts in their prescribed
   order: `npm run deploy:myusdt`, `npm run deploy:h02`, then
   `npm run deploy:hi02`. On a fresh node, `deploy:h02` requires
   `backend/config/contracts.json`'s `local.contracts.LendingPool.address` to
   be empty; the checked-in local registry currently has an address, so
   coordinate/reset that stale local deployment entry before deploying to a
   restarted node. Run `npm run verify:h02` after H02 but before HI02; it
   expects the pool to remain unregistered. Do not blindly rerun deployment
   scripts against an already registered pool.
3. Confirm `deployments/localhost.json` and
   `backend/config/contracts.json` contain the addresses and ABI paths from
   that same node. Verify each registered address with `eth_getCode` and make
   sure it is not `0x`; a node restart invalidates old local addresses.
4. Start the backend with `ACTIVE_NETWORK=local`; call the read views above
   against known seeded wallets. Exercise borrower/lender positions after
   their corresponding state-changing transactions and verify zero-debt,
   liquidity, and WAD/BPS results.
5. Request an unsigned transaction from the frontend and complete a local
   MetaMask transaction, checking the wallet, chain ID, gas estimate, receipt,
   and refreshed state. Keep user signing entirely client-side.
6. Repeat `get_oracle_price()` after HI05 is merged and its real deployment
   address is registered.

This handoff does not merge or modify `main`, and does not change `contracts/`.
