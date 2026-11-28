"""Offline tests for Q02 Web3 contract access and unsigned transaction quotes."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from eth_account import Account
from web3 import Web3

from backend.config import constants
from backend.config.settings import settings
from backend.services.web3_service import (
    ContractNotDeployedError,
    TransactionValidationError,
    Web3Service,
)


class _FakeCall:
    def __init__(self, eth: "_FakeEth", name: str, args: tuple[Any, ...]) -> None:
        self.eth = eth
        self.name = name
        self.args = args

    def call(self) -> Any:
        return self.eth.call_results.get(self.name)

    def build_transaction(self, transaction: dict[str, Any]) -> dict[str, Any]:
        return {**transaction, "data": "0x1234"}


class _FakeFunctions:
    def __init__(self, eth: "_FakeEth") -> None:
        self.eth = eth

    def __getattr__(self, name: str) -> Any:
        return lambda *args: _FakeCall(self.eth, name, args)


class _FakeContract:
    def __init__(self, address: str, eth: "_FakeEth") -> None:
        self.address = address
        self.functions = _FakeFunctions(eth)


class _FakeEth:
    chain_id = 31337
    gas_price = 1_000_000_000

    def __init__(self) -> None:
        self.call_results: dict[str, Any] = {
            "getPoolInfo": (
                1_000 * constants.WAD,
                500 * constants.WAD,
                0,
                constants.WAD,
                constants.WAD,
                1_000,
                500,
                5_000,
                123,
            ),
            "getCollateralValue": 1_000 * constants.WAD,
            "getTotalDebt": 0,
            "getHealthFactor": constants.INFINITE_HEALTH_FACTOR,
            "getAvailableLiquidity": 400 * constants.WAD,
            "getInterestRateSnapshot": (
                1_700_000_000,
                5_000,
                1_000,
                500,
                1_051,
                512,
                constants.WAD + 10,
                constants.WAD + 5,
            ),
            "getMaxBorrowable": 700 * constants.WAD,
            "getRemainingBorrowCapacity": 700 * constants.WAD,
            "getAvailableToBorrow": 400 * constants.WAD,
            "getCurrentLtvBps": 0,
            "calculateAccruedInterest": 0,
            "previewBorrowerInterest": 0,
            "getLoanPosition": (
                "0x0000000000000000000000000000000000000001",
                False,
                1_000 * constants.WAD,
                0,
                8,
                0,
                constants.WAD,
                0,
                1_700_000_000,
                1_700_000_000,
                "",
                False,
            ),
            "getLenderPosition": (3, 100 * constants.WAD, constants.WAD, 0, 1_700_000_000, True),
            "getLenderEarnedInterest": 2 * constants.WAD,
            "previewLenderEarnedInterest": 3 * constants.WAD,
            "getLenderClaimableBalance": 102 * constants.WAD,
            "getMaxWithdrawable": 90 * constants.WAD,
            "balanceOf": 1_000 * constants.WAD,
            "allowance": 500 * constants.WAD,
            "ownerOf": "0x0000000000000000000000000000000000000001",
            "activeReceiptOf": 8,
            "getReceiptInfo": (
                "0x0000000000000000000000000000000000000001",
                False,
                1_000 * constants.WAD,
                1_700_000_000,
                True,
            ),
            "valuation": 25 * constants.WAD,
            "getApproved": "0x0000000000000000000000000000000000000002",
            "isApprovedForAll": False,
            "getLiquidationPreview": (
                False,
                constants.INFINITE_HEALTH_FACTOR,
                0,
                1_000 * constants.WAD,
                0,
                True,
            ),
        }
        self.estimated_transaction: dict[str, Any] | None = None
        self.code = b"\x60\x00"
        self.nonce_requests: list[str] = []
        self.block_number = 42

    def get_block(self, _identifier: str) -> dict[str, int]:
        return {"number": self.block_number, "timestamp": 1_700_000_123}

    def contract(self, address: str, abi: list[dict[str, Any]]) -> _FakeContract:
        assert abi
        return _FakeContract(address, self)

    def get_code(self, address: str) -> bytes:
        return self.code

    def estimate_gas(self, transaction: dict[str, Any]) -> int:
        self.estimated_transaction = transaction
        return 21_000

    def get_transaction_count(self, address: str) -> int:
        self.nonce_requests.append(address)
        return 7


class _FakeWeb3:
    def __init__(self) -> None:
        self.eth = _FakeEth()

    is_address = staticmethod(Web3.is_address)
    to_checksum_address = staticmethod(Web3.to_checksum_address)


@pytest.fixture
def web3_service() -> tuple[Web3Service, _FakeWeb3]:
    fake_w3 = _FakeWeb3()
    service = Web3Service(network_name="local", w3=fake_w3)
    service.registry["contracts"]["LendingPool"]["address"] = (
        "0x0000000000000000000000000000000000000002"
    )
    return service, fake_w3


def test_missing_core_deployment_has_clear_error(tmp_path: Path) -> None:
    config_path = tmp_path / "contracts.json"
    config_path.write_text(
        json.dumps({"local": {"chainId": 31337, "contracts": {"PriceOracle": {"address": ""}}}}),
        encoding="utf-8",
    )
    service = Web3Service(
        network_name="local",
        w3=_FakeWeb3(),
        app_settings=replace(settings, contracts_config_path=config_path),
    )

    with pytest.raises(ContractNotDeployedError, match="PriceOracle has no deployment address"):
        service.get_contract("PriceOracle")


@pytest.mark.parametrize("empty_code", (b"", "0x"))
def test_configured_address_without_bytecode_has_clear_error(
    web3_service: tuple[Web3Service, _FakeWeb3],
    empty_code: bytes | str,
) -> None:
    service, fake_w3 = web3_service
    fake_w3.eth.code = empty_code

    with pytest.raises(ContractNotDeployedError, match="no deployed bytecode.*local node may have restarted"):
        service.get_contract("LendingPool")


def test_pool_info_preserves_wad_bps_and_apr_apy_distinction(
    web3_service: tuple[Web3Service, _FakeWeb3],
) -> None:
    service, _ = web3_service

    info = service.get_pool_info()

    assert info["total_supplied"] == {"wad": str(1_000 * constants.WAD), "display": "1000.000000"}
    assert info["utilization_bps"] == 5_000
    assert info["borrow_apr"]["percent"] == 10.0
    assert info["borrow_apr"]["apy_reference_percent"] == 10.5156
    assert info["borrow_apr"]["rate_basis"] == "simple_apr"


def test_pool_info_accepts_named_web3_struct_result(
    web3_service: tuple[Web3Service, _FakeWeb3],
) -> None:
    service, fake_w3 = web3_service
    fake_w3.eth.call_results["getPoolInfo"] = {
        "totalSupplied": constants.WAD,
        "totalBorrowed": 0,
        "reservedLiquidity": 0,
        "borrowIndex": constants.WAD,
        "supplyIndex": constants.WAD,
        "borrowAprBps": 500,
        "supplyAprBps": 0,
        "utilizationBps": 0,
        "lastAccrualTimestamp": 100,
    }

    info = service.get_pool_info()

    assert info["total_supplied"]["display"] == "1.000000"
    assert info["borrow_index"]["wad"] == str(constants.WAD)
    assert info["borrow_apr"]["bps"] == 500


def test_pool_liquidity_and_rate_snapshot_normalize_wad_bps_and_apr_apy(
    web3_service: tuple[Web3Service, _FakeWeb3],
) -> None:
    service, _ = web3_service

    assert service.get_available_liquidity()["wad"] == str(400 * constants.WAD)
    snapshot = service.get_interest_rate_snapshot()

    assert snapshot["utilization"] == {"bps": 5_000, "percent": 50.0}
    assert snapshot["borrow_apr"]["rate_basis"] == "simple_apr_per_second"
    assert snapshot["borrow_apr"]["percent"] == 10.0
    assert snapshot["borrow_apy_reference"] == {
        "bps": 1_051,
        "percent": 10.51,
        "rate_basis": "daily_compounded_reference",
    }
    assert snapshot["borrow_index"]["wad"] == str(constants.WAD + 10)


def test_borrower_read_methods_handle_zero_debt_and_format_positions(
    web3_service: tuple[Web3Service, _FakeWeb3],
) -> None:
    service, fake_w3 = web3_service
    borrower = "0x0000000000000000000000000000000000000001"

    assert service.get_max_borrowable(borrower)["wad"] == str(700 * constants.WAD)
    assert service.get_remaining_borrow_capacity(borrower)["wad"] == str(700 * constants.WAD)
    assert service.get_available_to_borrow(borrower)["wad"] == str(400 * constants.WAD)
    assert service.get_current_ltv_bps(borrower) == {
        "bps": 0,
        "percent": 0.0,
        "is_infinite": False,
    }
    assert service.calculate_accrued_interest(borrower)["wad"] == "0"
    assert service.preview_borrower_interest(borrower, 3_600)["wad"] == "0"
    loan = service.get_loan_position(borrower)
    assert loan["principal"]["wad"] == "0"
    assert loan["collateral_amount"]["wad"] == str(1_000 * constants.WAD)
    assert loan["active"] is False

    fake_w3.eth.call_results["getCurrentLtvBps"] = constants.INFINITE_HEALTH_FACTOR
    infinite_ltv = service.get_current_ltv_bps(borrower)
    assert infinite_ltv["percent"] is None
    assert infinite_ltv["is_infinite"] is True


def test_lender_token_and_nft_read_methods(
    web3_service: tuple[Web3Service, _FakeWeb3],
) -> None:
    service, _ = web3_service
    wallet = "0x0000000000000000000000000000000000000001"

    assert service.get_lender_position(3)["principal"]["wad"] == str(100 * constants.WAD)
    assert service.get_lender_earned_interest(3)["wad"] == str(2 * constants.WAD)
    assert service.preview_lender_earned_interest(3, 3_600)["wad"] == str(3 * constants.WAD)
    assert service.get_lender_claimable_balance(3)["wad"] == str(102 * constants.WAD)
    assert service.get_max_withdrawable(3)["wad"] == str(90 * constants.WAD)
    assert service.get_myusdt_balance(wallet)["wad"] == str(1_000 * constants.WAD)
    assert service.get_myusdt_allowance(wallet, wallet)["wad"] == str(500 * constants.WAD)
    assert service.get_debt_token_balance(wallet)["wad"] == str(1_000 * constants.WAD)
    assert service.get_lending_position_owner(3) == Web3.to_checksum_address(wallet)
    assert service.get_active_collateral_receipt(wallet) == 8
    receipt = service.get_collateral_receipt_info(8)
    assert receipt["asset_id_or_amount"]["wad"] == str(1_000 * constants.WAD)
    assert service.get_collateral_nft_owner(9) == Web3.to_checksum_address(wallet)
    assert service.get_collateral_nft_valuation(9)["wad"] == str(25 * constants.WAD)


def test_zero_debt_health_factor_is_explicitly_infinite(
    web3_service: tuple[Web3Service, _FakeWeb3],
) -> None:
    service, _ = web3_service

    risk = service.get_borrower_risk("0x0000000000000000000000000000000000000001")

    assert risk["health_factor_wad"] == str(constants.INFINITE_HEALTH_FACTOR)
    assert risk["health_factor"] is None
    assert risk["is_infinite"] is True
    assert risk["status"] == "SAFE"


def test_unsigned_transaction_is_validated_and_contains_fee_quote(
    web3_service: tuple[Web3Service, _FakeWeb3],
) -> None:
    service, fake_w3 = web3_service
    wallet = "0x0000000000000000000000000000000000000001"

    quote = service.build_unsigned_transaction(
        "MyUSDT",
        "transfer",
        (wallet, 1),
        from_address=wallet,
        eth_usd_price="2000",
        principal_wad=100 * constants.WAD,
        apr_bps=1_000,
        duration_seconds=constants.SECONDS_PER_YEAR,
    )

    tx = quote["transaction"]
    assert tx["chainId"] == 31337
    assert tx["to"] == Web3.to_checksum_address("0x5FbDB2315678afecb367f032d93F642f64180aa3")
    assert tx["from"] == Web3.to_checksum_address(wallet)
    assert tx["data"] == "0x1234"
    assert tx["value"] == 0
    assert tx["gas"] == 25_200
    assert quote["gas_quote"]["estimated_fee_wei"] == "21000000000000"
    assert quote["gas_quote"]["estimated_fee_eth"] == "0.000021"
    assert quote["gas_quote"]["estimated_fee_usd"] == "0.04"
    assert quote["interest_quote"]["estimated_interest"]["wad"] == str(10 * constants.WAD)
    assert fake_w3.eth.estimated_transaction is not None
    assert quote["signing"] == "client_wallet"


def test_system_transaction_signing_fills_nonce_without_using_user_key(
    web3_service: tuple[Web3Service, _FakeWeb3],
) -> None:
    service, fake_w3 = web3_service
    system_key = Account.create().key.hex()
    service.app_settings = replace(service.app_settings, local_system_private_key=system_key)
    tx = {
        "chainId": 31337,
        "to": "0x0000000000000000000000000000000000000002",
        "data": "0x1234",
        "value": 0,
        "gas": 21_000,
        "gasPrice": fake_w3.eth.gas_price,
    }

    raw_transaction = service.sign_system_transaction(tx)

    assert Account.recover_transaction(raw_transaction) == Account.from_key(system_key).address
    assert fake_w3.eth.nonce_requests == [Account.from_key(system_key).address]


def test_invalid_wallet_is_rejected_before_transaction_build(
    web3_service: tuple[Web3Service, _FakeWeb3],
) -> None:
    service, _ = web3_service

    with pytest.raises(TransactionValidationError, match="Invalid wallet address"):
        service.build_unsigned_transaction(
            "MyUSDT", "transfer", (), from_address="not-an-address"
        )


@pytest.mark.parametrize(
    ("changes", "message"),
    (
        ({"chainId": 1}, "chainId"),
        ({"to": "not-an-address"}, "'to'"),
        ({"data": "0xzz"}, "'data'"),
        ({"value": -1}, "'value'"),
    ),
)
def test_unsigned_transaction_fields_are_validated(
    web3_service: tuple[Web3Service, _FakeWeb3],
    changes: dict[str, Any],
    message: str,
) -> None:
    service, _ = web3_service
    tx = {
        "chainId": 31337,
        "to": "0x0000000000000000000000000000000000000002",
        "data": "0x1234",
        "value": 0,
    }

    with pytest.raises(TransactionValidationError, match=message):
        service._validate_unsigned_transaction({**tx, **changes})


def test_liquidation_preview_normalizes_safe_and_liquidatable_states(
    web3_service: tuple[Web3Service, _FakeWeb3],
) -> None:
    service, fake_w3 = web3_service
    borrower = "0x0000000000000000000000000000000000000001"

    safe_preview = service.get_liquidation_preview(borrower)
    assert safe_preview["liquidatable"] is False
    assert safe_preview["is_infinite"] is True
    assert safe_preview["status"] == "SAFE"
    assert safe_preview["is_nft_collateral"] is True
    assert safe_preview["seize_value"]["wad"] == "0"

    fake_w3.eth.call_results["getLiquidationPreview"] = (
        True,
        900_000_000_000_000_000,
        500 * constants.WAD,
        562_500_000_000_000_000_000,
        525 * constants.WAD,
        False,
    )
    risky_preview = service.get_liquidation_preview(borrower)
    assert risky_preview["liquidatable"] is True
    assert risky_preview["is_infinite"] is False
    assert risky_preview["status"] == "LIQUIDATABLE"
    assert risky_preview["health_factor"] == 0.9
    assert risky_preview["seize_value"]["wad"] == str(525 * constants.WAD)


def test_collateral_nft_approval_and_latest_block_context(
    web3_service: tuple[Web3Service, _FakeWeb3],
) -> None:
    service, _ = web3_service
    owner = "0x0000000000000000000000000000000000000001"
    pool = "0x0000000000000000000000000000000000000002"

    approval = service.get_collateral_nft_approval_status(owner, pool, 0)
    assert approval["token_id"] == 0
    assert approval["is_approved"] is True

    ctx = service.get_latest_block_context()
    assert ctx == {"block_number": 42, "as_of_timestamp": 1_700_000_123}


def test_real_lending_position_nft_abi_encodes_3_arg_safe_transfer_from() -> None:
    abi_path = Path(__file__).resolve().parents[1] / "deployments" / "abi" / "LendingPositionNFT.json"
    abi = json.loads(abi_path.read_text(encoding="utf-8"))["abi"]
    w3 = Web3()
    nft = w3.eth.contract(
        address=Web3.to_checksum_address("0xDc64a140Aa3E981100a9becA4E685f962f0cF6C9"),
        abi=abi,
    )
    sender = Web3.to_checksum_address("0x70997970C51812dc3A010C7d01b50e0d17dc79C8")
    recipient = Web3.to_checksum_address("0x90F79bf6EB2c4f870365E785982E1f101E93b906")
    tx = nft.functions.safeTransferFrom(sender, recipient, 1).build_transaction(
        {"from": sender, "chainId": 31337, "gas": 100_000, "gasPrice": 1_000_000_000}
    )
    # Selector for safeTransferFrom(address,address,uint256) is 0x42842e0e
    assert tx["data"].lower().startswith("0x42842e0e")


def test_sepolia_web3_service_loads_sepolia_manifest_without_attribute_error() -> None:
    fake_w3 = _FakeWeb3()
    fake_w3.eth.chain_id = 11155111
    service = Web3Service(network_name="sepolia", w3=fake_w3)
    assert service.chain_id == 11155111
    assert service.registry["contracts"]["LendingPool"]["address"].startswith("0x")
    assert service.registry["contracts"]["PriceOracle"]["address"].startswith("0x")
