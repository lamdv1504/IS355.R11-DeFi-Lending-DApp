"""Q05 API tests for EIP-191 auth, RBAC, transaction flow, and IPFS documents."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi.testclient import TestClient
from web3 import Web3
from web3.exceptions import ContractLogicError

from backend.main import create_app
from backend.security.auth import AuthenticationError, WalletAuthManager
from backend.services.agreement_generator import AgreementGeneratorService
from backend.services.credit_and_audit_ipfs import CreditAndAuditIPFSService
from backend.services.web3_service import Web3Service
from backend.config import constants
from src.ipfs.encryption import DocumentEncryptor
from src.ipfs.ipfs_client import IPFSClient, IPFSConfig
from src.ipfs.rbac import AuthorizedIPFSGateway, DocumentType, DocumentVisibility


POOL = "0x0000000000000000000000000000000000000010"
TOKEN = "0x0000000000000000000000000000000000000020"
ORACLE = "0x0000000000000000000000000000000000000030"
POSITION_NFT = "0x0000000000000000000000000000000000000040"
COLLATERAL_NFT = "0x0000000000000000000000000000000000000050"


class _FakeEvent:
    def __init__(self, service: "_FakeWeb3Service", name: str) -> None:
        self.service = service
        self.name = name

    def get_logs(
        self,
        *,
        from_block: int,
        to_block: int | str,
        argument_filters: dict[str, Any],
    ) -> list[dict[str, Any]]:
        return [
            log
            for log in self.service.events.get(self.name, [])
            if int(log.get("blockNumber", 0)) >= from_block
            and all(log["args"].get(key) == value for key, value in argument_filters.items())
        ]

    def process_receipt(self, _receipt: Any) -> list[dict[str, Any]]:
        return self.service.borrow_receipt_events


class _FakeEvents:
    def __init__(self, service: "_FakeWeb3Service") -> None:
        self.service = service

    def __getattr__(self, name: str) -> Any:
        return lambda: _FakeEvent(self.service, name)


class _FakeCall:
    def call(self) -> int:
        return 0


class _FakeFunctions:
    def __getattr__(self, _name: str) -> Any:
        return lambda *_args: _FakeCall()


class _FakeEth:
    def __init__(self) -> None:
        self.chain_id = 31337
        self.transaction: dict[str, Any] = {}
        self.receipt: dict[str, Any] = {}
        self.timestamp = int(datetime.now(timezone.utc).timestamp())
        self.block_number = 10

    def get_block(self, _identifier: str) -> dict[str, int]:
        return {"timestamp": self.timestamp, "number": self.block_number}

    def get_transaction(self, _tx_hash: str) -> dict[str, Any]:
        return self.transaction

    def get_transaction_receipt(self, _tx_hash: str) -> dict[str, Any]:
        return self.receipt


class _FakeWeb3:
    def __init__(self) -> None:
        self.eth = _FakeEth()
        self.provider = self

    @staticmethod
    def to_checksum_address(address: str) -> str:
        return Web3.to_checksum_address(address)

    @staticmethod
    def to_hex(value: bytes | str) -> str:
        if isinstance(value, str) and value.startswith("0x"):
            return value
        return Web3.to_hex(value)

    def make_request(self, method: str, params: list[Any]) -> dict[str, Any]:
        if method == "evm_increaseTime":
            self.eth.timestamp += int(params[0])
            return {"result": hex(self.eth.timestamp)}
        if method == "evm_mine":
            self.eth.block_number += 1
            return {"result": "0x0"}
        raise AssertionError(f"Unexpected RPC method: {method}")


class _FakeWeb3Service:
    def __init__(self) -> None:
        self.network = SimpleNamespace(name="local")
        self.chain_id = 31337
        self.w3 = _FakeWeb3()
        self.registry = {
            "contracts": {
                "LendingPool": {"address": POOL},
                "MyUSDT": {"address": TOKEN},
                "CollateralNFT": {"address": COLLATERAL_NFT},
                "LendingPositionNFT": {"address": POSITION_NFT},
                "PriceOracle": {"address": ORACLE},
            }
        }
        self.last_build_call: tuple[str, str, tuple[Any, ...]] | None = None
        self.last_build_kwargs: dict[str, Any] = {}
        self.fail_estimate_gas_when_called: bool = False
        self.myusdt_allowance_wad: int = 0
        self.nft_approved: bool = False
        self.events: dict[str, list[dict[str, Any]]] = {
            "CollateralDeposited": [],
            "LoanBorrowed": [],
            "LoanRepaid": [],
            "LoanLiquidated": [],
            "InterestRateUpdated": [
                {
                    "address": POOL,
                    "args": {
                        "timestamp": 1_672_531_200,
                        "totalSuppliedWad": 1_000 * constants.WAD,
                        "totalBorrowedWad": 200 * constants.WAD,
                        "utilizationBps": 2_000,
                        "borrowAprBps": 700,
                        "supplyAprBps": 140,
                    },
                    "blockNumber": 1,
                    "logIndex": 0,
                    "transactionHash": "0x" + "01" * 32,
                }
            ],
        }
        self.borrow_receipt_events: list[dict[str, Any]] = []

    @staticmethod
    def _checksum_address(address: str, field_name: str) -> str:
        if not Web3.is_address(address):
            raise ValueError(f"Invalid {field_name} address.")
        return Web3.to_checksum_address(address)

    def get_contract(self, name: str) -> Any:
        if name == "LendingPool":
            return SimpleNamespace(events=_FakeEvents(self), functions=_FakeFunctions())
        if name in {"LendingPositionNFT", "CollateralNFT"}:
            return SimpleNamespace(functions=_FakeFunctions())
        raise AssertionError(f"Unexpected contract lookup: {name}")

    def get_pool_info(self) -> dict[str, Any]:
        return {
            "total_supplied": {"wad": str(1_000 * constants.WAD)},
            "total_borrowed": {"wad": str(200 * constants.WAD)},
            "reserved_liquidity": {"wad": "0"},
            "borrow_apr_bps": 700,
            "supply_apr_bps": 140,
            "utilization_bps": 2_000,
        }

    def get_available_liquidity(self) -> dict[str, str]:
        return {"wad": str(800 * constants.WAD), "display": "800"}

    def get_interest_rate_snapshot(self) -> dict[str, Any]:
        return {
            "timestamp": int(datetime.now(timezone.utc).timestamp()),
            "utilization": {"bps": 2_000, "percent": 20.0},
            "borrow_apr": {"bps": 700, "percent": 7.0},
            "supply_apr": {"bps": 140, "percent": 1.4},
            "borrow_apy_reference": {"bps": 725, "percent": 7.2501},
            "supply_apy_reference": {"bps": 140, "percent": 1.4098},
        }

    def get_loan_position(self, borrower: str) -> dict[str, Any]:
        return {
            "borrower": borrower,
            "active": True,
            "receipt_token_id": 7,
            "is_nft_collateral": False,
            "collateral_amount": {"wad": str(1_000 * constants.WAD)},
            "principal": {"wad": str(100 * constants.WAD)},
            "ipfs_agreement_cid": "",
        }

    def get_borrower_risk(self, _borrower: str) -> dict[str, Any]:
        return {
            "collateral_value": {"wad": str(1_000 * constants.WAD)},
            "total_debt": {"wad": str(100 * constants.WAD)},
            "health_factor_wad": str(constants.WAD * 4),
        }

    def get_current_ltv_bps(self, _borrower: str) -> dict[str, Any]:
        return {"bps": 1_000, "percent": 10.0, "is_infinite": False}

    def get_max_borrowable(self, _borrower: str) -> dict[str, str]:
        return {"wad": str(700 * constants.WAD)}

    def get_remaining_borrow_capacity(self, _borrower: str) -> dict[str, str]:
        return {"wad": str(600 * constants.WAD)}

    def get_available_to_borrow(self, _borrower: str) -> dict[str, str]:
        return {"wad": str(600 * constants.WAD)}

    def calculate_accrued_interest(self, _borrower: str) -> dict[str, str]:
        return {"wad": "0"}

    def get_collateral_receipt_info(self, receipt_id: int) -> dict[str, Any]:
        assert receipt_id == 7
        return {
            "active": True,
            "is_nft": False,
            "asset_id_or_amount": {"wad": str(1_000 * constants.WAD)},
        }

    def get_max_withdrawable(self, _position_id: int) -> dict[str, str]:
        return {"wad": "0"}

    def get_myusdt_balance(self, _account: str) -> dict[str, str]:
        return {"wad": "0"}

    def get_debt_token_balance(self, _account: str) -> dict[str, str]:
        return {"wad": "0"}

    def get_myusdt_allowance(
        self, _owner: str, _spender: str
    ) -> dict[str, str]:
        return {"wad": str(self.myusdt_allowance_wad)}

    def get_collateral_nft_valuation(self, _token_id: int) -> dict[str, str]:
        return {"wad": str(1_000 * constants.WAD)}

    def get_collateral_nft_approval_status(
        self, _owner: str, _spender: str, token_id: int
    ) -> dict[str, Any]:
        return {
            "token_id": token_id,
            "approved_address": POOL if self.nft_approved else None,
            "approved_for_all": False,
            "is_approved": self.nft_approved,
        }

    def get_latest_block_context(self) -> dict[str, int]:
        return {
            "block_number": self.w3.eth.block_number,
            "as_of_timestamp": self.w3.eth.timestamp,
        }

    def get_liquidation_preview(self, borrower: str) -> dict[str, Any]:
        return {
            "borrower": borrower,
            "collateral_value": {"wad": str(1_000 * constants.WAD), "display": "1000.000000"},
            "total_debt": {"wad": str(100 * constants.WAD), "display": "100.000000"},
            "seize_value": {"wad": "0", "display": "0.000000"},
            "is_nft_collateral": False,
            **constants.format_health_factor_for_api(constants.WAD * 8),
            "liquidatable": False,
        }

    def get_active_collateral_receipt(self, _borrower: str) -> int:
        return 0

    def build_unsigned_transaction(
        self,
        contract_name: str,
        function_name: str,
        args: tuple[Any, ...],
        *,
        from_address: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        self.last_build_call = (contract_name, function_name, args)
        self.last_build_kwargs = dict(kwargs)
        to_address = self.registry["contracts"][contract_name]["address"]
        skip_gas = bool(kwargs.get("skip_gas_estimation", False))
        if not skip_gas and self.fail_estimate_gas_when_called:
            raise ContractLogicError("execution reverted: ERC20InsufficientAllowance")
        tx: dict[str, Any] = {
            "from": from_address,
            "to": to_address,
            "data": "0x1234",
            "value": 0,
            "chainId": self.chain_id,
        }
        if skip_gas:
            gas_quote: dict[str, Any] = {
                "estimated_gas": None,
                "gas_limit": None,
                "gas_price_wei": "1",
                "estimated_fee_wei": None,
                "estimation_status": "PENDING_APPROVAL",
                "estimation_skipped_reason": (
                    "Token or NFT approval is required before on-chain gas estimation."
                ),
            }
        else:
            tx["gas"] = 100_000
            gas_quote = {
                "estimated_gas": 80_000,
                "gas_limit": 100_000,
                "gas_price_wei": "1",
                "estimation_status": "ESTIMATED",
                "estimation_skipped_reason": None,
            }
        return {
            "transaction": tx,
            "gas_quote": gas_quote,
            "interest_quote": (
                {"apr": {"rate_basis": "simple_apr"}, "apy_reference_percent": 7.2501}
                if "principal_wad" in kwargs
                else None
            ),
            "signing": "client_wallet",
        }


@pytest.fixture
def api_env(tmp_path: Path) -> dict[str, Any]:
    owner = Account.create()
    lender = Account.create()
    admin = Account.create()
    web3_service = _FakeWeb3Service()
    gateway = AuthorizedIPFSGateway(
        IPFSClient(
            IPFSConfig(provider="local_store", local_store_dir=tmp_path / "ipfs")
        ),
        DocumentEncryptor.from_hex_key("11" * 32),
    )
    agreement = AgreementGeneratorService(
        web3_service,
        gateway=gateway,
        binding_store_path=tmp_path / "q03-index.json",
    )
    credit_audit = CreditAndAuditIPFSService(
        web3_service,
        gateway=gateway,
        agreement_generator=agreement,
        metadata_store_path=tmp_path / "q04-index.json",
    )
    manager = WalletAuthManager(
        "test-only-signing-secret-that-is-at-least-32-bytes",
        domain="localhost",
        allowed_chain_ids=(31337,),
        admin_wallets=(admin.address,),
        lender_wallets=(lender.address,),
    )
    app = create_app()
    app.state.auth_manager = manager
    app.state.web3_service = web3_service
    app.state.agreement_generator = agreement
    app.state.credit_audit_service = credit_audit
    return {
        "client": TestClient(app),
        "owner": owner,
        "lender": lender,
        "admin": admin,
        "manager": manager,
        "web3": web3_service,
        "agreement": agreement,
        "credit_audit": credit_audit,
        "gateway": gateway,
    }


def _login(
    client: TestClient, account: Any, *, chain_id: int = 31337
) -> dict[str, str]:
    response = client.post(
        "/api/auth/nonce",
        json={
            "wallet_address": account.address,
            "chain_id": chain_id,
            "domain": "localhost",
        },
    )
    assert response.status_code == 200, response.text
    challenge = response.json()
    signed = Account.sign_message(
        encode_defunct(text=challenge["message"]), account.key
    ).signature.hex()
    if not signed.startswith("0x"):
        signed = "0x" + signed
    verified = client.post(
        "/api/auth/verify",
        json={
            "wallet_address": account.address,
            "chain_id": chain_id,
            "domain": "localhost",
            "nonce": challenge["nonce"],
            "signature": signed,
        },
    )
    assert verified.status_code == 200, verified.text
    return {"Authorization": f"Bearer {verified.json()['access_token']}"}


def test_eip191_nonce_is_wallet_bound_and_single_use(api_env: dict[str, Any]) -> None:
    client = api_env["client"]
    owner = api_env["owner"]
    nonce = client.post(
        "/api/auth/nonce",
        json={"wallet_address": owner.address, "chain_id": 31337},
    ).json()
    signed = Account.sign_message(
        encode_defunct(text=nonce["message"]), owner.key
    ).signature.hex()
    if not signed.startswith("0x"):
        signed = "0x" + signed
    payload = {
        "wallet_address": owner.address,
        "chain_id": 31337,
        "nonce": nonce["nonce"],
        "signature": signed,
    }
    assert signed.startswith("0x")
    assert client.post("/api/auth/verify", json=payload).status_code == 200
    assert client.post("/api/auth/verify", json=payload).status_code == 401
    with pytest.raises(AuthenticationError):
        api_env["manager"].verify_signature(
            api_env["lender"].address,
            31337,
            nonce["nonce"],
            signed,
        )
    second = client.post(
        "/api/auth/nonce",
        json={"wallet_address": owner.address, "chain_id": 31337},
    ).json()
    forged_signature = Account.sign_message(
        encode_defunct(text=second["message"]), api_env["lender"].key
    ).signature.hex()
    if not forged_signature.startswith("0x"):
        forged_signature = "0x" + forged_signature
    forged_payload = {
        "wallet_address": owner.address,
        "chain_id": 31337,
        "nonce": second["nonce"],
        "signature": forged_signature,
    }
    assert client.post("/api/auth/verify", json=forged_payload).status_code == 401
    genuine_signature = Account.sign_message(
        encode_defunct(text=second["message"]), owner.key
    ).signature.hex()
    if not genuine_signature.startswith("0x"):
        genuine_signature = "0x" + genuine_signature
    forged_payload["signature"] = genuine_signature
    assert client.post("/api/auth/verify", json=forged_payload).status_code == 200


def test_nonce_and_session_expiry_are_enforced() -> None:
    now = [1_700_000_000.0]
    account = Account.create()
    manager = WalletAuthManager(
        "test-only-signing-secret-that-is-at-least-32-bytes",
        domain="localhost",
        allowed_chain_ids=(31337,),
        nonce_ttl_seconds=2,
        session_ttl_seconds=2,
        clock=lambda: now[0],
    )
    challenge = manager.issue_nonce(account.address, 31337)
    signature = Account.sign_message(
        encode_defunct(text=challenge["message"]), account.key
    ).signature.hex()
    if not signature.startswith("0x"):
        signature = "0x" + signature
    session = manager.verify_signature(
        account.address, 31337, str(challenge["nonce"]), signature
    )
    manager.verify_session(str(session["access_token"]))
    now[0] += 3
    with pytest.raises(AuthenticationError, match="expired"):
        manager.verify_session(str(session["access_token"]))
    with pytest.raises(AuthenticationError, match="expired"):
        manager.verify_signature(
            account.address, 31337, str(challenge["nonce"]), signature
        )


def test_authentication_and_account_ownership_status_codes(api_env: dict[str, Any]) -> None:
    client = api_env["client"]
    assert client.get("/api/accounts/" + api_env["owner"].address + "/loan").status_code == 200
    headers = _login(client, api_env["owner"])
    assert client.get("/api/pool").status_code == 200
    other = api_env["lender"].address
    assert client.get(f"/api/accounts/{other}/loan", headers=headers).status_code == 200
    assert client.get(
        f"/api/accounts/{api_env['owner'].address}/loan", headers=headers
    ).status_code == 200
    positions = client.get(
        f"/api/accounts/{api_env['owner'].address}/lending-positions",
        headers=headers,
    )
    balances = client.get(
        f"/api/accounts/{api_env['owner'].address}/balances", headers=headers
    )
    assert positions.status_code == balances.status_code == 200
    assert positions.json()["positions"] == []
    assert balances.json()["balances"]["myusdt"]["wad"] == "0"


def test_local_only_admin_demo_and_mock_oracle_guard(api_env: dict[str, Any]) -> None:
    client = api_env["client"]
    owner_headers = _login(client, api_env["owner"])
    assert client.post("/api/demo/time", json={"seconds": 60}, headers=owner_headers).status_code == 403

    web3_service = api_env["web3"]
    admin_headers = _login(client, api_env["admin"])
    local_demo = client.post(
        "/api/demo/time", json={"seconds": 60}, headers=admin_headers
    )
    assert local_demo.status_code == 200
    assert local_demo.json()["environment"] == "LOCAL_DEMO_ONLY"
    local_mock = client.post(
        "/api/transactions/prepare",
        json={
            "wallet_address": api_env["admin"].address,
            "action": "MOCK_ORACLE_MULTIPLIER",
            "multiplier_bps": 12_000,
        },
        headers=admin_headers,
    )
    assert local_mock.status_code == 200
    web3_service.network = SimpleNamespace(name="sepolia")
    assert client.post("/api/demo/time", json={"seconds": 60}, headers=admin_headers).status_code == 403
    mock_oracle = client.post(
        "/api/transactions/prepare",
        json={
            "wallet_address": api_env["admin"].address,
            "action": "MOCK_ORACLE_MULTIPLIER",
            "multiplier_bps": 12_000,
        },
        headers=admin_headers,
    )
    assert mock_oracle.status_code == 403


def test_prepare_and_confirm_borrow_binds_agreement_after_success(api_env: dict[str, Any]) -> None:
    client = api_env["client"]
    owner = api_env["owner"]
    headers = _login(client, owner)
    created = client.post(
        "/api/ipfs/create-agreement",
        json={
            "principal_wad": str(100 * constants.WAD),
            "asset_description": "Test ERC20 collateral",
        },
        headers=headers,
    )
    assert created.status_code == 200, created.text
    agreement = created.json()
    assert agreement["status"] == "PRE_BORROW_UNSIGNED"
    assert agreement["tx_hash"] is None

    prepared = client.post(
        "/api/transactions/prepare",
        json={
            "account": owner.address,
            "network": "local",
            "chain_id": 31337,
            "action": "BORROW",
            "args": {
                "amount_wad": str(100 * constants.WAD),
                "agreement_cid": agreement["cid"],
            },
            "duration_seconds": 86_400,
        },
        headers=headers,
    )
    assert prepared.status_code == 200, prepared.text
    tx_data = prepared.json()
    assert tx_data["unsignedTransaction"]["from"].lower() == owner.address.lower()
    assert tx_data["signing"] == "client_wallet"
    assert tx_data["interest_quote"]["apr"]["rate_basis"] == "simple_apr"

    tx_hash_bytes = bytes.fromhex("ab" * 32)
    web3_service = api_env["web3"]
    web3_service.w3.eth.transaction = {
        "from": owner.address,
        "to": POOL,
        "input": tx_data["unsignedTransaction"]["data"],
        "chainId": 31337,
        "value": 0,
    }
    web3_service.w3.eth.receipt = {
        "status": 1,
        "blockNumber": 42,
        "transactionHash": tx_hash_bytes,
    }
    web3_service.borrow_receipt_events = [
        {
            "address": POOL,
            "args": {
                "borrower": owner.address,
                "amountWad": 100 * constants.WAD,
                "agreementCid": agreement["cid"],
            }
        }
    ]
    confirmed = client.post(
        "/api/transactions/confirm",
        json={"intent_id": tx_data["intent_id"], "tx_hash": "0x" + tx_hash_bytes.hex()},
        headers=headers,
    )
    assert confirmed.status_code == 200, confirmed.text
    binding = confirmed.json()["loan_binding"]
    assert binding["agreement_cid"] == agreement["cid"]
    assert binding["borrower_wallet"].lower() == owner.address.lower()
    assert binding["tx_hash"] == "0x" + tx_hash_bytes.hex()


def test_private_agreement_and_credit_report_rbac_and_integrity(api_env: dict[str, Any]) -> None:
    client = api_env["client"]
    owner = api_env["owner"]
    borrower_headers = _login(client, owner)
    lender_headers = _login(client, api_env["lender"])
    admin_headers = _login(client, api_env["admin"])

    agreement_result = client.post(
        "/api/ipfs/create-agreement",
        json={
            "principal_wad": str(100 * constants.WAD),
            "asset_description": "Encrypted agreement test",
        },
        headers=borrower_headers,
    ).json()
    cid = agreement_result["cid"]
    encrypted_raw = api_env["gateway"].ipfs_client.retrieve_bytes(cid).content
    assert b"%PDF-" not in encrypted_raw
    assert client.get(f"/api/ipfs/documents/{cid}/retrieve").status_code == 401
    assert client.get(
        f"/api/ipfs/documents/{cid}/retrieve", headers=lender_headers
    ).status_code == 403
    owner_pdf = client.get(f"/api/ipfs/documents/{cid}/retrieve", headers=borrower_headers)
    admin_pdf = client.get(f"/api/ipfs/documents/{cid}/retrieve", headers=admin_headers)
    assert owner_pdf.status_code == admin_pdf.status_code == 200
    assert owner_pdf.content.startswith(b"%PDF-")
    assert owner_pdf.headers["X-Content-SHA256"] == agreement_result["pdf_plaintext_sha256"]
    assert owner_pdf.content == admin_pdf.content

    report_response = client.post(
        f"/api/ipfs/credit-report/{owner.address}",
        json={"from_block": 0},
        headers=borrower_headers,
    )
    assert report_response.status_code == 200, report_response.text
    report = report_response.json()
    assert report["credit_score"]["score"] in range(300, 851)
    assert report["acl_metadata"]["encrypted"] is True
    assert client.get(
        f"/api/ipfs/documents/{report['cid']}/retrieve"
    ).status_code == 401
    assert client.get(
        f"/api/ipfs/documents/{report['cid']}/retrieve", headers=lender_headers
    ).status_code == 403
    retrieved = client.get(
        f"/api/ipfs/documents/{report['cid']}/retrieve", headers=borrower_headers
    )
    assert retrieved.status_code == 200, retrieved.text
    assert retrieved.json()["content"]["wallet_address"].lower() == owner.address.lower()
    assert retrieved.headers["X-Content-SHA256"] == report["plaintext_sha256"]
    admin_report = client.get(
        f"/api/ipfs/documents/{report['cid']}/retrieve", headers=admin_headers
    )
    assert admin_report.status_code == 200
    assert admin_report.headers["X-Content-SHA256"] == report["plaintext_sha256"]


def test_admin_audit_publication_and_guest_json_csv_retrieval(api_env: dict[str, Any]) -> None:
    client = api_env["client"]
    borrower_headers = _login(client, api_env["owner"])
    admin_headers = _login(client, api_env["admin"])
    forbidden = client.post(
        "/api/ipfs/audit-logs",
        json={"from_block": 0, "seed_simulated_months": 2},
        headers=borrower_headers,
    )
    assert forbidden.status_code == 403
    generated = client.post(
        "/api/ipfs/audit-logs",
        json={"from_block": 0, "seed_simulated_months": 2},
        headers=admin_headers,
    )
    assert generated.status_code == 200, generated.text
    response = generated.json()
    assert response["json"]["acl_metadata"]["visibility"] == "PUBLIC"
    assert response["csv"]["acl_metadata"]["visibility"] == "PUBLIC"
    assert response["json"]["acl_metadata"]["encrypted"] is False
    assert any(entry["data_kind"] == "ON_CHAIN" for entry in response["entries"])
    assert any(entry["data_kind"] == "SIMULATED" for entry in response["entries"])
    assert response["document"]["contains_pii"] is False

    public_json = client.get(f"/api/ipfs/documents/{response['json']['cid']}/retrieve")
    public_csv = client.get(f"/api/ipfs/documents/{response['csv']['cid']}/retrieve")
    assert public_json.status_code == public_csv.status_code == 200
    assert public_json.json()["content"]["contains_pii"] is False
    assert "period,recorded_at_utc,data_kind" in public_csv.text
    assert public_json.headers["X-Content-SHA256"] == response["json"]["sha256"]
    assert public_csv.headers["X-Content-SHA256"] == response["csv"]["sha256"]


def test_sepolia_history_requires_explicit_from_block(api_env: dict[str, Any]) -> None:
    client = api_env["client"]
    owner = api_env["owner"]
    api_env["web3"].network = SimpleNamespace(name="sepolia")
    api_env["web3"].chain_id = 11155111
    api_env["manager"] = WalletAuthManager(
        "test-only-signing-secret-that-is-at-least-32-bytes",
        domain="localhost",
        allowed_chain_ids=(11155111,),
    )
    client.app.state.auth_manager = api_env["manager"]
    headers = _login(client, owner, chain_id=11155111)
    missing_range = client.post(
        f"/api/ipfs/credit-report/{owner.address}",
        json={},
        headers=headers,
    )
    assert missing_range.status_code == 422


def test_prepare_transfer_lending_position_nft_builds_safe_transfer_from(
    api_env: dict[str, Any],
) -> None:
    client = api_env["client"]
    lender = api_env["lender"]
    recipient = api_env["owner"].address
    headers = _login(client, lender)

    prepared = client.post(
        "/api/transactions/prepare",
        json={
            "account": lender.address,
            "network": "local",
            "chain_id": 31337,
            "action": "TRANSFER_LENDING_POSITION_NFT",
            "args": {"to": recipient, "position_id": 1},
        },
        headers=headers,
    )
    assert prepared.status_code == 200, prepared.text
    body = prepared.json()
    assert body["unsignedTransaction"]["to"].lower() == POSITION_NFT.lower()
    assert api_env["web3"].last_build_call == (
        "LendingPositionNFT",
        "safeTransferFrom",
        (Web3.to_checksum_address(lender.address), Web3.to_checksum_address(recipient), 1),
    )
    assert body["preview"]["position_id"] == 1
    assert body["preview"]["recipient_address"] == Web3.to_checksum_address(recipient)

    zero_recipient = client.post(
        "/api/transactions/prepare",
        json={
            "account": lender.address,
            "action": "TRANSFER_LENDING_POSITION_NFT",
            "args": {"to": "0x0000000000000000000000000000000000000000", "position_id": 1},
        },
        headers=headers,
    )
    assert zero_recipient.status_code == 422


def test_prepare_deposit_collateral_allows_nft_token_id_zero_and_blocks_erc20_zero(
    api_env: dict[str, Any],
) -> None:
    client = api_env["client"]
    owner = api_env["owner"]
    headers = _login(client, owner)

    nft_zero = client.post(
        "/api/transactions/prepare",
        json={
            "account": owner.address,
            "action": "DEPOSIT_COLLATERAL",
            "args": {"is_nft": True, "amount_or_token_id": 0},
        },
        headers=headers,
    )
    assert nft_zero.status_code == 200, nft_zero.text
    body = nft_zero.json()
    assert api_env["web3"].last_build_call == ("LendingPool", "depositCollateral", (0, True))
    assert body["allowance"]["token_id"] == 0
    assert body["allowance"]["approval_required"] is True

    erc20_zero = client.post(
        "/api/transactions/prepare",
        json={
            "account": owner.address,
            "action": "DEPOSIT_COLLATERAL",
            "args": {"is_nft": False, "amount_or_token_id": "0"},
        },
        headers=headers,
    )
    assert erc20_zero.status_code == 422


def test_pool_endpoint_supports_network_query_and_snapshot_metadata(
    api_env: dict[str, Any],
) -> None:
    client = api_env["client"]
    local_resp = client.get("/api/pool?network=local")
    assert local_resp.status_code == 200, local_resp.text
    local_body = local_resp.json()
    assert local_body["network"] == "local"
    assert local_body["chain_id"] == 31337
    assert local_body["block_number"] == 10
    assert local_body["as_of_timestamp"] > 0

    sepolia_fake = _FakeWeb3Service()
    sepolia_fake.network = SimpleNamespace(name="sepolia")
    sepolia_fake.chain_id = 11155111
    sepolia_fake.w3.eth.block_number = 12224613
    client.app.state.web3_services = {"local": api_env["web3"], "sepolia": sepolia_fake}

    sep_resp = client.get("/api/pool?network=sepolia")
    assert sep_resp.status_code == 200, sep_resp.text
    sep_body = sep_resp.json()
    assert sep_body["network"] == "sepolia"
    assert sep_body["chain_id"] == 11155111
    assert sep_body["block_number"] == 12224613

    assert client.get("/api/pool?network=invalid").status_code == 422


def test_analytics_rates_returns_monthly_simulated_and_onchain_series(
    api_env: dict[str, Any],
) -> None:
    client = api_env["client"]
    resp = client.get("/api/analytics/rates?seed_simulated_months=6")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["network"] == "local"
    assert body["block_number"] == 10
    assert body["as_of_timestamp"] > 0
    assert body["rate_model"]["base_borrow_apr_bps"] == constants.BASE_BORROW_APR_BPS
    assert body["rate_model"]["utilization_slope_bps"] == constants.UTILIZATION_SLOPE_BPS
    assert "APR" in body["rate_model"]["apr_vs_apy_note"]
    series = body["series"]
    assert isinstance(series, list) and len(series) >= 6
    assert any(row["data_kind"] == "SIMULATED" for row in series)
    assert any(row["data_kind"] == "ON_CHAIN" for row in series)
    periods = [row["period"] for row in series]
    assert periods == sorted(periods)
    for row in series:
        assert "borrow_apy_percent" in row
        assert "supply_apy_percent" in row
        assert "borrow_apr_percent" in row
        assert "supply_apr_percent" in row
        assert "utilization_percent" in row


def test_prepare_response_includes_allowance_preview_context_and_loan_liquidation_preview(
    api_env: dict[str, Any],
) -> None:
    client = api_env["client"]
    owner = api_env["owner"]
    headers = _login(client, owner)

    deposit_prep = client.post(
        "/api/transactions/prepare",
        json={
            "account": owner.address,
            "action": "DEPOSIT_LENDER",
            "args": {"amount_wad": str(500 * constants.WAD)},
        },
        headers=headers,
    )
    assert deposit_prep.status_code == 200, deposit_prep.text
    dep_body = deposit_prep.json()
    assert dep_body["context"]["block_number"] == 10
    assert dep_body["context"]["action"] == "DEPOSIT_LENDER"
    assert dep_body["availability"]["ready"] is True
    assert dep_body["allowance"]["approval_required"] is True
    assert dep_body["allowance"]["token_address"] == TOKEN
    assert dep_body["allowance"]["spender_address"] == POOL
    assert dep_body["preview"]["is_estimate"] is True

    api_env["web3"].myusdt_allowance_wad = 600 * constants.WAD
    deposit_ok = client.post(
        "/api/transactions/prepare",
        json={
            "account": owner.address,
            "action": "DEPOSIT_LENDER",
            "args": {"amount_wad": str(500 * constants.WAD)},
        },
        headers=headers,
    ).json()
    assert deposit_ok["allowance"]["approval_required"] is False

    borrow_prep = client.post(
        "/api/transactions/prepare",
        json={
            "account": owner.address,
            "action": "BORROW",
            "args": {"amount_wad": str(400 * constants.WAD), "agreement_cid": "bafy-test"},
        },
        headers=headers,
    ).json()
    # Current collateral=1000, current debt=100, borrow +400 => resulting debt=500, LTV=5000 BPS (50%), HF=1.6
    assert borrow_prep["preview"]["resulting_debt_wad"] == str(500 * constants.WAD)
    assert borrow_prep["preview"]["resulting_ltv_bps"] == 5_000
    assert borrow_prep["preview"]["resulting_ltv"]["percent"] == 50.0
    assert borrow_prep["preview"]["resulting_hf"]["health_factor"] == 1.6
    assert borrow_prep["preview"]["resulting_hf"]["status"] == "SAFE"

    loan_resp = client.get(f"/api/accounts/{owner.address}/loan")
    assert loan_resp.status_code == 200
    assert loan_resp.json()["liquidation_preview"]["liquidatable"] is False


def test_confirm_transaction_accepts_bytes_hexbytes_tx_input(
    api_env: dict[str, Any],
) -> None:
    client = api_env["client"]
    owner = api_env["owner"]
    headers = _login(client, owner)
    prepared = client.post(
        "/api/transactions/prepare",
        json={
            "account": owner.address,
            "action": "DEPOSIT_LENDER",
            "args": {"amount_wad": str(100 * constants.WAD)},
        },
        headers=headers,
    )
    assert prepared.status_code == 200, prepared.text
    tx_data = prepared.json()

    tx_hash_bytes = bytes.fromhex("cd" * 32)
    api_env["web3"].w3.eth.transaction = {
        "from": owner.address,
        "to": POOL,
        "input": bytes.fromhex("1234"),
        "v": 31337 * 2 + 35,
        "value": 0,
    }
    api_env["web3"].w3.eth.receipt = {
        "status": 1,
        "blockNumber": 55,
        "transactionHash": tx_hash_bytes,
    }
    confirmed = client.post(
        "/api/transactions/confirm",
        json={"intent_id": tx_data["intent_id"], "tx_hash": "0x" + tx_hash_bytes.hex()},
        headers=headers,
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == 1
    assert confirmed.json()["block_number"] == 55


def test_prepare_checks_allowance_before_gas_estimation_for_erc20_and_nft(
    api_env: dict[str, Any],
) -> None:
    client = api_env["client"]
    owner = api_env["owner"]
    headers = _login(client, owner)
    web3 = api_env["web3"]
    web3.fail_estimate_gas_when_called = True

    # ERC-20 actions (DEPOSIT_LENDER, REPAY, LIQUIDATE) and CollateralNFT deposit
    # must NOT fail with estimate_gas revert when allowance/approval is still missing.
    cases = [
        ("DEPOSIT_LENDER", {"amount_wad": str(500 * constants.WAD)}),
        ("REPAY", {"amount_wad": str(50 * constants.WAD)}),
        ("LIQUIDATE", {"borrower_address": api_env["lender"].address}),
        ("DEPOSIT_COLLATERAL", {"is_nft": True, "amount_or_token_id": 2}),
    ]
    for action, args in cases:
        resp = client.post(
            "/api/transactions/prepare",
            json={"account": owner.address, "action": action, "args": args},
            headers=headers,
        )
        assert resp.status_code == 200, f"{action}: {resp.text}"
        body = resp.json()
        assert body["allowance"]["approval_required"] is True, action
        assert body["gas_quote"]["estimation_status"] == "PENDING_APPROVAL", action
        assert body["gas_quote"]["estimated_gas"] is None, action
        assert "gas" not in body["unsignedTransaction"], action
        assert web3.last_build_kwargs.get("skip_gas_estimation") is True, action

    # Once approved, gas estimation runs normally and returns an estimated gas quote.
    web3.myusdt_allowance_wad = 1_000 * constants.WAD
    web3.nft_approved = True
    web3.fail_estimate_gas_when_called = False

    approved_resp = client.post(
        "/api/transactions/prepare",
        json={
            "account": owner.address,
            "action": "DEPOSIT_COLLATERAL",
            "args": {"is_nft": True, "amount_or_token_id": 2},
        },
        headers=headers,
    )
    assert approved_resp.status_code == 200, approved_resp.text
    approved_body = approved_resp.json()
    assert approved_body["allowance"]["approval_required"] is False
    assert approved_body["gas_quote"]["estimation_status"] == "ESTIMATED"
    assert approved_body["gas_quote"]["estimated_gas"] == 80_000
    assert approved_body["unsignedTransaction"]["gas"] == 100_000
    assert web3.last_build_kwargs.get("skip_gas_estimation") is None


def test_prepare_with_real_web3_service_handles_unapproved_and_decodes_real_reverts() -> None:
    owner = Account.create()

    class _MiniCall:
        def __init__(self, eth: "_MiniEth", fn_name: str) -> None:
            self.eth = eth
            self.fn_name = fn_name

        def call(self) -> Any:
            return self.eth.call_results[self.fn_name]

        def build_transaction(self, tx: dict[str, Any]) -> dict[str, Any]:
            assert "gas" in tx, "build_transaction must pass placeholder gas to avoid premature estimate_gas"
            return {**tx, "data": "0xabcdef01"}

    class _MiniFunctions:
        def __init__(self, eth: "_MiniEth") -> None:
            self.eth = eth

        def __getattr__(self, name: str) -> Any:
            return lambda *_args: _MiniCall(self.eth, name)

    class _MiniEth:
        chain_id = 31337
        gas_price = 1_000_000_000
        block_number = 77

        def __init__(self) -> None:
            self.estimate_calls = 0
            self.estimate_error: Exception | None = ContractLogicError(
                "execution reverted: ERC20InsufficientAllowance"
            )
            self.call_results: dict[str, Any] = {
                "allowance": 0,
                "getPoolInfo": (
                    1_000 * constants.WAD,
                    200 * constants.WAD,
                    0,
                    constants.WAD,
                    constants.WAD,
                    700,
                    140,
                    2_000,
                    1_700_000_000,
                ),
                "getCollateralValue": 1_000 * constants.WAD,
                "getTotalDebt": 100 * constants.WAD,
                "getHealthFactor": 8 * constants.WAD,
                "getInterestRateSnapshot": (
                    1_700_000_000,
                    2_000,
                    700,
                    140,
                    725,
                    140,
                    constants.WAD,
                    constants.WAD,
                ),
            }

        def get_block(self, _identifier: str) -> dict[str, int]:
            return {"number": self.block_number, "timestamp": 1_700_000_100}

        def get_code(self, _address: str) -> bytes:
            return b"\x60\x00"

        def contract(self, address: str, abi: list[dict[str, Any]]) -> Any:
            assert abi
            return SimpleNamespace(address=address, functions=_MiniFunctions(self))

        def estimate_gas(self, _tx: dict[str, Any]) -> int:
            self.estimate_calls += 1
            if self.estimate_error is not None:
                raise self.estimate_error
            return 21_000

    class _MiniW3:
        def __init__(self) -> None:
            self.eth = _MiniEth()

        is_address = staticmethod(Web3.is_address)
        to_checksum_address = staticmethod(Web3.to_checksum_address)

    mini_w3 = _MiniW3()
    real_service = Web3Service(network_name="local", w3=mini_w3)
    real_service.registry["contracts"]["LendingPool"]["address"] = POOL
    real_service.registry["contracts"]["MyUSDT"]["address"] = TOKEN

    manager = WalletAuthManager(
        "test-only-signing-secret-that-is-at-least-32-bytes",
        domain="localhost",
        allowed_chain_ids=(31337,),
    )
    app = create_app()
    app.state.auth_manager = manager
    app.state.web3_service = real_service
    client = TestClient(app)
    headers = _login(client, owner)

    # 1) Allowance = 0: must return 200 without calling estimate_gas.
    unapproved = client.post(
        "/api/transactions/prepare",
        json={
            "account": owner.address,
            "action": "DEPOSIT_LENDER",
            "args": {"amount_wad": str(100 * constants.WAD)},
        },
        headers=headers,
    )
    assert unapproved.status_code == 200, unapproved.text
    assert mini_w3.eth.estimate_calls == 0
    assert unapproved.json()["allowance"]["approval_required"] is True
    assert unapproved.json()["gas_quote"]["estimation_status"] == "PENDING_APPROVAL"
    assert "gas" not in unapproved.json()["unsignedTransaction"]

    # 2) Allowance sufficient + successful estimate_gas -> 200 with real gas quote.
    mini_w3.eth.call_results["allowance"] = 500 * constants.WAD
    mini_w3.eth.estimate_error = None
    approved = client.post(
        "/api/transactions/prepare",
        json={
            "account": owner.address,
            "action": "DEPOSIT_LENDER",
            "args": {"amount_wad": str(100 * constants.WAD)},
        },
        headers=headers,
    )
    assert approved.status_code == 200, approved.text
    assert mini_w3.eth.estimate_calls == 1
    assert approved.json()["allowance"]["approval_required"] is False
    assert approved.json()["gas_quote"]["estimation_status"] == "ESTIMATED"
    assert approved.json()["unsignedTransaction"]["gas"] == 25_200

    # 3) Real business revert (ExceedsMaxLTV) must decode to HTTP 400 (not 503).
    mini_w3.eth.estimate_error = ContractLogicError("execution reverted: ExceedsMaxLTV")
    reverted = client.post(
        "/api/transactions/prepare",
        json={
            "account": owner.address,
            "action": "BORROW",
            "args": {"amount_wad": str(900 * constants.WAD), "agreement_cid": "bafy-test"},
        },
        headers=headers,
    )
    assert reverted.status_code == 400, reverted.text
    assert reverted.json()["code"] == "ExceedsMaxLTV"


def test_prepare_and_confirm_support_dynamic_network_switching_without_restart(
    api_env: dict[str, Any],
) -> None:
    client = api_env["client"]
    owner = api_env["owner"]
    admin = api_env["admin"]

    sepolia_fake = _FakeWeb3Service()
    sepolia_fake.network = SimpleNamespace(name="sepolia")
    sepolia_fake.chain_id = 11155111
    sepolia_fake.w3.eth.chain_id = 11155111
    sepolia_fake.w3.eth.block_number = 12224699
    sepolia_fake.myusdt_allowance_wad = 1_000 * constants.WAD

    manager = WalletAuthManager(
        "test-only-signing-secret-that-is-at-least-32-bytes",
        domain="localhost",
        allowed_chain_ids=(31337, 11155111),
        admin_wallets=(admin.address,),
        lender_wallets=(api_env["lender"].address,),
    )
    client.app.state.auth_manager = manager
    client.app.state.web3_services = {
        "local": api_env["web3"],
        "sepolia": sepolia_fake,
    }

    local_headers = _login(client, owner, chain_id=31337)
    sepolia_headers = _login(client, owner, chain_id=11155111)
    sepolia_admin_headers = _login(client, admin, chain_id=11155111)

    # 1) Explicit body network="sepolia" + chain_id=11155111 succeeds even when default is local.
    prep_body = client.post(
        "/api/transactions/prepare",
        json={
            "account": owner.address,
            "network": "sepolia",
            "chain_id": 11155111,
            "action": "DEPOSIT_LENDER",
            "args": {"amount_wad": str(100 * constants.WAD)},
        },
        headers=sepolia_headers,
    )
    assert prep_body.status_code == 200, prep_body.text
    tx_sep = prep_body.json()
    assert tx_sep["context"]["network"] == "sepolia"
    assert tx_sep["context"]["chain_id"] == 11155111
    assert tx_sep["context"]["block_number"] == 12224699
    assert tx_sep["unsignedTransaction"]["chainId"] == 11155111

    # 2) Query ?network=sepolia, chain_id-only, and session-derived network all route to Sepolia.
    prep_query = client.post(
        "/api/transactions/prepare?network=sepolia",
        json={
            "account": owner.address,
            "action": "DEPOSIT_LENDER",
            "args": {"amount_wad": str(100 * constants.WAD)},
        },
        headers=sepolia_headers,
    )
    assert prep_query.status_code == 200, prep_query.text
    assert prep_query.json()["context"]["network"] == "sepolia"

    prep_chain = client.post(
        "/api/transactions/prepare",
        json={
            "account": owner.address,
            "chain_id": 11155111,
            "action": "DEPOSIT_LENDER",
            "args": {"amount_wad": str(100 * constants.WAD)},
        },
        headers=sepolia_headers,
    )
    assert prep_chain.status_code == 200, prep_chain.text
    assert prep_chain.json()["context"]["network"] == "sepolia"

    prep_session = client.post(
        "/api/transactions/prepare",
        json={
            "account": owner.address,
            "action": "DEPOSIT_LENDER",
            "args": {"amount_wad": str(100 * constants.WAD)},
        },
        headers=sepolia_headers,
    )
    assert prep_session.status_code == 200, prep_session.text
    assert prep_session.json()["context"]["network"] == "sepolia"

    # 3) Cross-network mismatches, invalid networks, and Sepolia mock-oracle stay strictly blocked.
    assert (
        client.post(
            "/api/transactions/prepare",
            json={
                "account": owner.address,
                "network": "sepolia",
                "action": "DEPOSIT_LENDER",
                "args": {"amount_wad": str(100 * constants.WAD)},
            },
            headers=local_headers,
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/transactions/prepare",
            json={
                "account": owner.address,
                "network": "local",
                "action": "DEPOSIT_LENDER",
                "args": {"amount_wad": str(100 * constants.WAD)},
            },
            headers=sepolia_headers,
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/transactions/prepare?network=local",
            json={
                "account": owner.address,
                "network": "sepolia",
                "action": "DEPOSIT_LENDER",
                "args": {"amount_wad": str(100 * constants.WAD)},
            },
            headers=sepolia_headers,
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/transactions/prepare",
            json={
                "account": owner.address,
                "network": "sepolia",
                "chain_id": 31337,
                "action": "DEPOSIT_LENDER",
                "args": {"amount_wad": str(100 * constants.WAD)},
            },
            headers=sepolia_headers,
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/transactions/prepare",
            json={
                "account": owner.address,
                "network": "mainnet",
                "action": "DEPOSIT_LENDER",
                "args": {"amount_wad": str(100 * constants.WAD)},
            },
            headers=sepolia_headers,
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/transactions/prepare",
            json={
                "account": owner.address,
                "chain_id": 999,
                "action": "DEPOSIT_LENDER",
                "args": {"amount_wad": str(100 * constants.WAD)},
            },
            headers=sepolia_headers,
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/transactions/prepare",
            json={
                "wallet_address": admin.address,
                "network": "sepolia",
                "action": "MOCK_ORACLE_MULTIPLIER",
                "multiplier_bps": 6_000,
            },
            headers=sepolia_admin_headers,
        ).status_code
        == 403
    )

    # 4) Confirm verifies against the Sepolia Web3Service; wrong-network attempts return 403
    #    without consuming the prepared intent.
    tx_hash_bytes = bytes.fromhex("ef" * 32)
    tx_hash_hex = "0x" + tx_hash_bytes.hex()
    sepolia_fake.w3.eth.transaction = {
        "from": owner.address,
        "to": POOL,
        "input": tx_sep["unsignedTransaction"]["data"],
        "chainId": 11155111,
        "value": 0,
    }
    sepolia_fake.w3.eth.receipt = {
        "status": 1,
        "blockNumber": 12224705,
        "transactionHash": tx_hash_bytes,
    }

    assert (
        client.post(
            "/api/transactions/confirm",
            json={"intent_id": tx_sep["intent_id"], "tx_hash": tx_hash_hex},
            headers=local_headers,
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/transactions/confirm?network=local",
            json={"intent_id": tx_sep["intent_id"], "tx_hash": tx_hash_hex},
            headers=sepolia_headers,
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/transactions/confirm",
            json={
                "intent_id": tx_sep["intent_id"],
                "tx_hash": tx_hash_hex,
                "chain_id": 31337,
            },
            headers=sepolia_headers,
        ).status_code
        == 403
    )

    confirmed = client.post(
        "/api/transactions/confirm",
        json={"intent_id": tx_sep["intent_id"], "tx_hash": tx_hash_hex},
        headers=sepolia_headers,
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == 1
    assert confirmed.json()["block_number"] == 12224705


def test_account_snapshot_returns_unified_balances_loan_and_block_metadata(
    api_env: dict[str, Any],
) -> None:
    client = api_env["client"]
    owner = api_env["owner"]

    local_snap = client.get(f"/api/accounts/{owner.address}/snapshot")
    assert local_snap.status_code == 200, local_snap.text
    body = local_snap.json()
    assert body["network"] == "local"
    assert body["chain_id"] == 31337
    assert body["block_number"] == 10
    assert body["as_of_timestamp"] > 0
    assert body["balances"]["myusdt"]["wad"] == "0"
    assert body["risk"]["collateral_value"]["wad"] == str(1_000 * constants.WAD)
    assert body["interest"]["accrued"]["wad"] == "0"

    bal = client.get(f"/api/accounts/{owner.address}/balances").json()
    loan = client.get(f"/api/accounts/{owner.address}/loan").json()
    assert bal["block_number"] == loan["block_number"] == 10

    sepolia_fake = _FakeWeb3Service()
    sepolia_fake.network = SimpleNamespace(name="sepolia")
    sepolia_fake.chain_id = 11155111
    sepolia_fake.w3.eth.block_number = 12224888
    client.app.state.web3_services = {"local": api_env["web3"], "sepolia": sepolia_fake}

    sep_snap = client.get(f"/api/accounts/{owner.address}/snapshot?network=sepolia")
    assert sep_snap.status_code == 200, sep_snap.text
    assert sep_snap.json()["network"] == "sepolia"
    assert sep_snap.json()["block_number"] == 12224888


def test_demo_time_rejects_sepolia_admin_session_even_when_backend_active_network_is_local(
    api_env: dict[str, Any],
) -> None:
    client = api_env["client"]
    admin = api_env["admin"]

    sepolia_fake = _FakeWeb3Service()
    sepolia_fake.network = SimpleNamespace(name="sepolia")
    sepolia_fake.chain_id = 11155111
    sepolia_fake.w3.eth.chain_id = 11155111

    manager = WalletAuthManager(
        "test-only-signing-secret-that-is-at-least-32-bytes",
        domain="localhost",
        allowed_chain_ids=(31337, 11155111),
        admin_wallets=(admin.address,),
    )
    client.app.state.auth_manager = manager
    client.app.state.web3_services = {"local": api_env["web3"], "sepolia": sepolia_fake}

    local_admin_headers = _login(client, admin, chain_id=31337)
    sepolia_admin_headers = _login(client, admin, chain_id=11155111)

    # Local admin on local network succeeds.
    ok_local = client.post("/api/demo/time", json={"seconds": 60}, headers=local_admin_headers)
    assert ok_local.status_code == 200, ok_local.text

    # Local admin explicitly requesting Sepolia is blocked.
    assert (
        client.post(
            "/api/demo/time?network=sepolia",
            json={"seconds": 60},
            headers=local_admin_headers,
        ).status_code
        == 403
    )

    # Sepolia admin session is ALWAYS blocked from local time-travel, regardless of network param.
    assert (
        client.post("/api/demo/time", json={"seconds": 60}, headers=sepolia_admin_headers).status_code
        == 403
    )
    assert (
        client.post(
            "/api/demo/time?network=local",
            json={"seconds": 60},
            headers=sepolia_admin_headers,
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/demo/time",
            json={"seconds": 60, "network": "sepolia", "chain_id": 11155111},
            headers=sepolia_admin_headers,
        ).status_code
        == 403
    )


def test_ipfs_write_routes_support_dynamic_sepolia_network_without_restart(
    api_env: dict[str, Any],
) -> None:
    client = api_env["client"]
    owner = api_env["owner"]
    admin = api_env["admin"]

    sepolia_fake = _FakeWeb3Service()
    sepolia_fake.network = SimpleNamespace(name="sepolia")
    sepolia_fake.chain_id = 11155111
    sepolia_fake.w3.eth.chain_id = 11155111
    sepolia_fake.w3.eth.block_number = 12224699
    sepolia_fake.events["InterestRateUpdated"][0]["blockNumber"] = 12224550

    manager = WalletAuthManager(
        "test-only-signing-secret-that-is-at-least-32-bytes",
        domain="localhost",
        allowed_chain_ids=(31337, 11155111),
        admin_wallets=(admin.address,),
        lender_wallets=(api_env["lender"].address,),
    )
    client.app.state.auth_manager = manager
    client.app.state.web3_services = {"local": api_env["web3"], "sepolia": sepolia_fake}

    local_headers = _login(client, owner, chain_id=31337)
    sepolia_headers = _login(client, owner, chain_id=11155111)
    sepolia_admin_headers = _login(client, admin, chain_id=11155111)

    # 1) Pre-borrow agreement on Sepolia succeeds without restarting backend (default is local).
    created = client.post(
        "/api/ipfs/create-agreement",
        json={
            "principal_wad": str(100 * constants.WAD),
            "asset_description": "Sepolia CollateralNFT #2",
            "network": "sepolia",
        },
        headers=sepolia_headers,
    )
    assert created.status_code == 200, created.text
    agreement_cid = created.json()["cid"]

    # Retrieve works immediately from the shared agreement index + gateway.
    pdf_resp = client.get(f"/api/ipfs/documents/{agreement_cid}/retrieve", headers=sepolia_headers)
    assert pdf_resp.status_code == 200
    assert pdf_resp.content.startswith(b"%PDF-")

    # Cross-network mismatch (local session requesting sepolia) is still blocked with 403.
    assert (
        client.post(
            "/api/ipfs/create-agreement?network=sepolia",
            json={
                "principal_wad": str(100 * constants.WAD),
                "asset_description": "Cross-network attempt",
            },
            headers=local_headers,
        ).status_code
        == 403
    )

    # 2) Sepolia credit-report still requires explicit from_block, and succeeds when provided.
    assert (
        client.post(
            f"/api/ipfs/credit-report/{owner.address}?network=sepolia",
            json={},
            headers=sepolia_headers,
        ).status_code
        == 422
    )
    credit = client.post(
        f"/api/ipfs/credit-report/{owner.address}",
        json={"from_block": 12224519, "network": "sepolia"},
        headers=sepolia_headers,
    )
    assert credit.status_code == 200, credit.text

    # 3) Sepolia admin audit-logs succeeds when from_block is provided.
    audit = client.post(
        "/api/ipfs/audit-logs?network=sepolia",
        json={"from_block": 12224519, "seed_simulated_months": 2},
        headers=sepolia_admin_headers,
    )
    assert audit.status_code == 200, audit.text


def test_balances_list_owned_collateral_nfts_and_lending_positions_defaults_sepolia_deploy_block(
    api_env: dict[str, Any],
) -> None:
    client = api_env["client"]
    owner = api_env["owner"]
    web3 = api_env["web3"]

    # Mock wallet owning CollateralNFT #2.
    class _NFTBalanceFunctions:
        def balanceOf(self, _wallet: str) -> Any:
            return SimpleNamespace(call=lambda: 1)

    orig_get_contract = web3.get_contract
    web3.get_contract = (  # type: ignore[method-assign]
        lambda name: SimpleNamespace(functions=_NFTBalanceFunctions())
        if name == "CollateralNFT"
        else orig_get_contract(name)
    )
    web3.get_owned_collateral_nfts = (  # type: ignore[attr-defined]
        lambda wallet, *, from_block=0: [
            {
                "token_id": 2,
                "owner": Web3.to_checksum_address(wallet),
                "valuation": {"wad": str(1_000 * constants.WAD), "display": "1000.000000"},
                "is_approved": False,
                "token_uri": "ipfs://bafy-sample-2",
            }
        ]
    )

    bal_resp = client.get(f"/api/accounts/{owner.address}/balances")
    assert bal_resp.status_code == 200, bal_resp.text
    bal = bal_resp.json()["balances"]
    assert bal["collateral_nft_balance"] == 1
    assert bal["collateral_nft_token_ids"] == [2]
    assert len(bal["collateral_nfts"]) == 1
    assert bal["collateral_nfts"][0]["valuation"]["wad"] == str(1_000 * constants.WAD)

    snap_resp = client.get(f"/api/accounts/{owner.address}/snapshot")
    assert snap_resp.status_code == 200, snap_resp.text
    assert snap_resp.json()["balances"]["collateral_nft_token_ids"] == [2]

    # Sepolia lending-positions automatically uses LendingPool deploy blockNumber without 422.
    sepolia_fake = _FakeWeb3Service()
    sepolia_fake.network = SimpleNamespace(name="sepolia")
    sepolia_fake.chain_id = 11155111
    sepolia_fake.w3.eth.block_number = 12224600
    sepolia_fake.registry["contracts"]["LendingPool"]["blockNumber"] = 12224519
    sepolia_fake.events["LenderDeposited"] = [
        {"blockNumber": 12224588, "args": {"positionId": 1}},
    ]
    sepolia_fake.get_lending_position_owner = lambda _pid: Web3.to_checksum_address(owner.address)  # type: ignore[attr-defined]
    sepolia_fake.get_lender_position = lambda pid: {  # type: ignore[attr-defined]
        "position_id": pid,
        "principal": {"wad": str(1_000 * constants.WAD)},
        "active": True,
    }
    sepolia_fake.get_lender_earned_interest = lambda _pid: {"wad": "0"}  # type: ignore[attr-defined]
    sepolia_fake.get_lender_claimable_balance = lambda _pid: {"wad": str(1_000 * constants.WAD)}  # type: ignore[attr-defined]
    client.app.state.web3_services = {"local": web3, "sepolia": sepolia_fake}

    sep_pos = client.get(f"/api/accounts/{owner.address}/lending-positions?network=sepolia")
    assert sep_pos.status_code == 200, sep_pos.text
    sep_body = sep_pos.json()
    assert sep_body["network"] == "sepolia"
    assert sep_body["chain_id"] == 11155111
    assert sep_body["block_number"] == 12224600
    assert len(sep_body["positions"]) == 1
    assert sep_body["positions"][0]["position_id"] == 1

    # When Sepolia deploy blockNumber is missing, omitting from_block still returns 422.
    del sepolia_fake.registry["contracts"]["LendingPool"]["blockNumber"]
    assert (
        client.get(f"/api/accounts/{owner.address}/lending-positions?network=sepolia").status_code
        == 422
    )


def test_confirm_borrow_rejects_cross_chain_agreement_cid_binding(
    api_env: dict[str, Any],
) -> None:
    client = api_env["client"]
    owner = api_env["owner"]

    sepolia_fake = _FakeWeb3Service()
    sepolia_fake.network = SimpleNamespace(name="sepolia")
    sepolia_fake.chain_id = 11155111
    sepolia_fake.w3.eth.chain_id = 11155111

    manager = WalletAuthManager(
        "test-only-signing-secret-that-is-at-least-32-bytes",
        domain="localhost",
        allowed_chain_ids=(31337, 11155111),
    )
    client.app.state.auth_manager = manager
    client.app.state.web3_services = {"local": api_env["web3"], "sepolia": sepolia_fake}

    local_headers = _login(client, owner, chain_id=31337)
    sepolia_headers = _login(client, owner, chain_id=11155111)

    # Agreement created on local (31337) cannot be bound to a Sepolia (11155111) borrow receipt.
    local_agreement = client.post(
        "/api/ipfs/create-agreement",
        json={
            "principal_wad": str(100 * constants.WAD),
            "asset_description": "Local-only agreement",
        },
        headers=local_headers,
    )
    assert local_agreement.status_code == 200, local_agreement.text
    local_cid = local_agreement.json()["cid"]

    sep_borrow = client.post(
        "/api/transactions/prepare",
        json={
            "account": owner.address,
            "network": "sepolia",
            "chain_id": 11155111,
            "action": "BORROW",
            "args": {
                "amount_wad": str(100 * constants.WAD),
                "agreement_cid": local_cid,
            },
        },
        headers=sepolia_headers,
    )
    assert sep_borrow.status_code == 200, sep_borrow.text
    tx_data = sep_borrow.json()

    tx_hash_bytes = bytes.fromhex("99" * 32)
    sepolia_fake.w3.eth.transaction = {
        "from": owner.address,
        "to": POOL,
        "input": tx_data["unsignedTransaction"]["data"],
        "chainId": 11155111,
        "value": 0,
    }
    sepolia_fake.w3.eth.receipt = {
        "status": 1,
        "blockNumber": 12224900,
        "transactionHash": tx_hash_bytes,
    }
    sepolia_fake.borrow_receipt_events = [
        {
            "address": POOL,
            "args": {
                "borrower": owner.address,
                "amountWad": 100 * constants.WAD,
                "agreementCid": local_cid,
            },
        }
    ]

    rejected = client.post(
        "/api/transactions/confirm",
        json={"intent_id": tx_data["intent_id"], "tx_hash": "0x" + tx_hash_bytes.hex()},
        headers=sepolia_headers,
    )
    assert rejected.status_code == 400, rejected.text
    assert "chain_id" in rejected.text


def test_cors_allows_127_0_0_1_3000_and_settings_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.config.settings import load_settings

    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    loaded = load_settings()
    assert "http://localhost:3000" in loaded.cors_origins
    assert "http://127.0.0.1:3000" in loaded.cors_origins

    app = create_app()
    client = TestClient(app)
    preflight = client.options(
        "/health",
        headers={
            "Origin": "http://127.0.0.1:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert preflight.status_code == 200, preflight.text
    assert preflight.headers.get("access-control-allow-origin") == "http://127.0.0.1:3000"

    health = client.get("/health", headers={"Origin": "http://127.0.0.1:3000"})
    assert health.status_code == 200
    assert health.headers.get("access-control-allow-origin") == "http://127.0.0.1:3000"


@pytest.mark.parametrize("bad_key", ["", "deadbeef", "not-valid-hex"])
def test_missing_or_invalid_aes_key_returns_503_for_ipfs_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    bad_key: str,
) -> None:
    monkeypatch.setenv("DOCUMENT_AES_KEY_HEX", bad_key)
    monkeypatch.setenv("Q03_BINDING_STORE_PATH", str(tmp_path / "agreements.json"))
    monkeypatch.setenv("Q04_METADATA_STORE_PATH", str(tmp_path / "credit_audit.json"))

    # 1) get_agreement_generator must map EncryptionError -> HTTP 503.
    app_agreement = create_app()
    app_agreement.state.web3_service = _FakeWeb3Service()
    resp_agreement = TestClient(app_agreement).get("/api/ipfs/documents")
    assert resp_agreement.status_code == 503, resp_agreement.text
    assert "encryption" in resp_agreement.json()["detail"].lower()

    # 2) get_credit_audit_service must independently map EncryptionError -> HTTP 503.
    app_credit = create_app()
    app_credit.state.web3_service = _FakeWeb3Service()
    app_credit.state.agreement_generator = SimpleNamespace(
        binding_store_path=tmp_path / "agreements.json"
    )
    resp_credit = TestClient(app_credit).get("/api/ipfs/documents")
    assert resp_credit.status_code == 503, resp_credit.text
    assert "encryption" in resp_credit.json()["detail"].lower()
