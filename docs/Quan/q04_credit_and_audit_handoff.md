# Q04 - Credit Report JSON & Audit Logs handoff

## Service and lifecycle

`backend/services/credit_and_audit_ipfs.py` defines
`CreditAndAuditIPFSService`. Its default gateway is constructed from
`IPFSClient()` and `DocumentEncryptor.from_env("DOCUMENT_AES_KEY_HEX")`.
Pass an already configured `AuthorizedIPFSGateway` in tests or deployments with
explicit provider settings. The service stores `DocumentAccessMetadata` by CID
in a local JSON index (default:
`backend/data/credit_audit_ipfs_index.json`); set `metadata_store_path` to a
durable volume path for production. The AES master key is never written to that
index or IPFS.

The service only uses Web3 reads and event logs. It does not submit
transactions, request wallet private keys, or treat a client-provided role as
authenticated identity. Q05 must create `AccessContext` from its verified
wallet-signature session.

## API/method signatures

```python
CreditAndAuditIPFSService(
    web3_service: Web3Service,
    *,
    gateway: AuthorizedIPFSGateway | None = None,
    agreement_generator: AgreementGeneratorService | None = None,
    metadata_store_path: Path | None = None,
)

generate_credit_report(
    wallet_address: str,
    *,
    from_block: int = 0,
    to_block: int | str = "latest",
) -> dict[str, Any]

generate_monthly_audit_logs(
    *,
    from_block: int = 0,
    to_block: int | str = "latest",
    seed_simulated_months: int = 6,
) -> dict[str, Any]

retrieve_credit_report(cid: str, context: AccessContext) -> CreditReportDocument
retrieve_audit_logs(cid: str) -> AuditLogsDocument | str
retrieve_from_ipfs(
    cid: str,
    context: AccessContext | None = None,
) -> AuthorizedDocumentResult
```

`generate_credit_report` scans borrower-filtered `CollateralDeposited`,
`LoanBorrowed`, `LoanRepaid`, and `LoanLiquidated` logs, then combines the live
debt/risk result from `Web3Service.get_borrower_risk()`. Borrower event fields
become `CreditLoanRecord`s; `agreementCid` from `LoanBorrowed` is preferred.
When absent, the service looks for a successful Q03 `LoanTxBindingRecord` in the
provided `AgreementGeneratorService.binding_store_path`, keyed by transaction
hash. Loan identity is transaction hash plus log index. The deterministic score
is clamped to 300-850 and uses the schema's five tiers; it is informational,
not an underwriting decision.

The Credit Report payload follows `CreditReportDocument`: `data_kind` is
`ON_CHAIN`, `visibility` is `PRIVATE`, and `encryption_required` is `true`.
The uploaded AES-256-GCM envelope's CID and ciphertext SHA-256 are separate
from the plaintext report hash. Plaintext may be returned only after gateway
RBAC authorization.

`generate_monthly_audit_logs` aggregates the last `InterestRateUpdated` event
per month in the requested block range, then adds a current live
`Web3Service` pool/rate snapshot for the current UTC month. Historical
`available_liquidity` is derived from `total_supplied - total_borrowed` because
the event itself does not contain a liquidity field; the entry notes this
derivation. The live row uses `get_available_liquidity()`. Missing months are
filled from explicitly labeled `SIMULATED` seed samples. A matching on-chain
month takes precedence over a simulated sample.

The returned dictionary includes:

```json
{
  "json": {
    "cid": "bafy...",
    "gateway_url": "http://127.0.0.1:8080/ipfs/bafy...",
    "sha256": "<plaintext sha256>",
    "acl_metadata": {"document_type": "AUDIT_LOGS", "visibility": "PUBLIC"}
  },
  "csv": {
    "cid": "bafy...",
    "gateway_url": "http://127.0.0.1:8080/ipfs/bafy...",
    "sha256": "<plaintext sha256>",
    "acl_metadata": {"document_type": "AUDIT_LOGS", "visibility": "PUBLIC"}
  }
}
```

Both audit artifacts are uploaded `PUBLIC`, unencrypted, and schema-validated
with `contains_pii=false`. JSON retrieval returns `AuditLogsDocument`; CSV
retrieval returns UTF-8 text. Public audit reads allow Guest, Borrower, Lender,
and Admin. Private Credit Report reads return 401 for unauthenticated Guest and
403 for another wallet or Lender; owner Borrower and Admin receive 200.
Gateway integrity checks the CID and recorded SHA-256 before returning
plaintext.

## Q05 and L04 integration notes

- Q05 should expose a credit-report generation endpoint that accepts an
  authenticated borrower wallet and an optional bounded block range. Return CID,
  score/tier, summary and hashes, but not raw ciphertext internals or key data.
- For read endpoints, construct `AccessContext` only after verifying the
  wallet-signature nonce session. Pass it to `retrieve_credit_report()` or
  `retrieve_from_ipfs()`. Convert `AccessDeniedError.http_status` directly to
  HTTP 401/403. Do not fetch/decrypt a private report based only on knowledge of
  a CID.
- Admin-only publication of audit logs must be enforced at the Q05 route layer;
  the gateway's public document access policy is for reads, not proof of
  publisher identity.
- L04 can consume JSON and CSV CIDs/gateway URLs independently. JSON carries
  monthly entries with a `data_kind` label. Render `SIMULATED` as sample data
  and `ON_CHAIN` as event/live observations; do not combine them without showing
  their provenance. Both formats are public and have `contains_pii=false`.
- `agreement_generator` is optional. When passed, already persisted Q03
  transaction bindings are used only to fill agreement CID values missing from
  `LoanBorrowed` event data.

## Validation

Run the Q04 tests and core document/Web3 tests with:

```powershell
pytest tests/test_q04_credit_and_audit_ipfs.py tests/test_q02_web3_service.py tests/test_q03_agreement_generator.py tests/test_h03_ipfs.py tests/test_hi01_constants.py tests/test_hi05_oracle_and_liquidation.py
```

Unit/integration tests use a temporary local IPFS store and fake event reads;
live Hardhat, Kubo, and wallet-session integration should be checked separately
with `DOCUMENT_AES_KEY_HEX` configured via environment or a secret manager.
