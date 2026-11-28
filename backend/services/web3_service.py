"""Non-custodial Web3 access, read helpers, and unsigned transaction quotes."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, Sequence

from eth_account import Account
from web3 import Web3

from backend.config import constants
from backend.config.blockchain import get_web3
from backend.config.settings import AppSettings, settings


class Web3ServiceError(RuntimeError):
    """Base error for Web3 service configuration and contract access."""


class ContractNotDeployedError(Web3ServiceError):
    """Raised when a configured contract has no usable deployment address."""


class ContractConfigurationError(Web3ServiceError):
    """Raised when network or ABI configuration is invalid."""


class TransactionValidationError(Web3ServiceError):
    """Raised when a wallet address or unsigned transaction is unsafe."""


_INTERFACE_NAMES = {
    "MyUSDT": "IMyUSDT",
    "CollateralNFT": "ICollateralNFT",
    "CollateralReceiptNFT": "ICollateralReceiptNFT",
    "DebtToken": "IDebtToken",
    "LendingPositionNFT": "ILendingPositionNFT",
    "PriceOracle": "IPriceOracle",
    "LendingPool": "ILendingPool",
}

_POOL_INFO_FIELDS = (
    "total_supplied",
    "total_borrowed",
    "reserved_liquidity",
    "borrow_index",
    "supply_index",
    "borrow_apr_bps",
    "supply_apr_bps",
    "utilization_bps",
    "last_accrual_timestamp",
)
_POOL_WAD_FIELDS = {
    "total_supplied",
    "total_borrowed",
    "reserved_liquidity",
    "borrow_index",
    "supply_index",
}


def _format_wad(value: int) -> dict[str, str]:
    amount = int(value)
    return {
        "wad": str(amount),
        "display": constants.wad_to_decimal_str(amount),
    }


def _format_bps(value: int) -> dict[str, Any]:
    amount = int(value)
    return {
        "bps": amount,
        "percent": constants.apr_bps_to_percent(amount),
    }


class Web3Service:
    """Provides read-only contract access and unsigned transactions for MetaMask.

    The service never accepts or stores a user's private key. The optional
    system signing method only reads a backend-configured automation key.
    """

    def __init__(
        self,
        network_name: str | None = None,
        *,
        w3: Any | None = None,
        app_settings: AppSettings = settings,
        contracts_config_path: Path | None = None,
        sepolia_deployment_path: Path | None = None,
    ) -> None:
        self.app_settings = app_settings
        self.network = app_settings.get_network(network_name)
        self.w3 = w3 or get_web3(self.network.name)
        self.project_root = Path(__file__).resolve().parents[2]
        self.contracts_config_path = (
            Path(contracts_config_path)
            if contracts_config_path is not None
            else Path(app_settings.contracts_config_path)
        )
        self.sepolia_deployment_path = (
            Path(sepolia_deployment_path)
            if sepolia_deployment_path is not None
            else self.project_root / "deployments" / "sepolia.json"
        )
        self.chain_id = int(self.network.chain_id)
        self.registry = self._load_registry()
        configured_chain_id = int(self.registry.get("chainId", self.chain_id))
        if configured_chain_id != self.chain_id:
            raise ContractConfigurationError(
                f"Configured {self.network.name} chainId {configured_chain_id} "
                f"does not match settings chainId {self.chain_id}."
            )

    def _load_registry(self) -> dict[str, Any]:
        try:
            with self.contracts_config_path.open("r", encoding="utf-8") as file:
                root = json.load(file)
        except (OSError, json.JSONDecodeError) as exc:
            raise ContractConfigurationError(
                f"Cannot load contracts registry: {self.contracts_config_path}"
            ) from exc

        network_registry = root.get(self.network.name, {})
        registry = dict(network_registry)
        contracts = dict(network_registry.get("contracts", {}))
        if self.network.name == "sepolia" and self.sepolia_deployment_path.exists():
            try:
                with self.sepolia_deployment_path.open("r", encoding="utf-8") as file:
                    deployment = json.load(file)
            except (OSError, json.JSONDecodeError) as exc:
                raise ContractConfigurationError(
                    f"Cannot load Sepolia deployment: {self.sepolia_deployment_path}"
                ) from exc
            if int(deployment.get("chainId", self.chain_id)) != self.chain_id:
                raise ContractConfigurationError(
                    "Sepolia deployment chainId does not match configured network."
                )
            contracts.update(deployment.get("contracts", {}))
            registry["chainId"] = deployment.get("chainId", registry.get("chainId"))
        registry["contracts"] = contracts
        return registry

    def _contract_entry(self, contract_name: str) -> Mapping[str, Any]:
        try:
            entry = self.registry["contracts"][contract_name]
        except KeyError as exc:
            raise ContractConfigurationError(
                f"Contract '{contract_name}' is not present in the {self.network.name} registry."
            ) from exc
        if not isinstance(entry, Mapping):
            raise ContractConfigurationError(
                f"Invalid configuration for contract '{contract_name}'."
            )
        address = entry.get("address")
        if not address:
            raise ContractNotDeployedError(
                f"{contract_name} has no deployment address on {self.network.name}."
            )
        if not self.w3.is_address(address):
            raise ContractConfigurationError(
                f"{contract_name} has an invalid deployment address: {address!r}."
            )
        return entry

    def _abi_candidates(self, contract_name: str, entry: Mapping[str, Any]) -> list[Path]:
        interface_name = _INTERFACE_NAMES.get(contract_name, f"I{contract_name}")
        candidates: list[Path] = []
        configured_path = entry.get("abiPath")
        if configured_path:
            configured = Path(str(configured_path))
            candidates.append(
                configured if configured.is_absolute() else self.project_root / configured
            )
        candidates.extend(
            (
                self.project_root / "deployments" / "abi" / f"{contract_name}.json",
                self.project_root / "deployments" / "abi" / "interfaces" / f"{interface_name}.json",
                self.project_root / "artifacts" / "contracts" / "interfaces"
                / f"{interface_name}.sol" / f"{interface_name}.json",
                self.project_root / "artifacts" / "contracts" / "interfaces"
                / f"{interface_name}.json",
            )
        )
        return candidates

    def _load_abi(self, contract_name: str, entry: Mapping[str, Any]) -> list[dict[str, Any]]:
        attempted: list[str] = []
        for path in self._abi_candidates(contract_name, entry):
            path_string = str(path)
            if path_string in attempted or not path.is_file():
                continue
            attempted.append(path_string)
            try:
                with path.open("r", encoding="utf-8") as file:
                    artifact = json.load(file)
            except (OSError, json.JSONDecodeError) as exc:
                raise ContractConfigurationError(f"Cannot read ABI file: {path}") from exc
            abi = artifact.get("abi") if isinstance(artifact, dict) else artifact
            if isinstance(abi, list):
                return abi
            raise ContractConfigurationError(f"ABI file does not contain an ABI list: {path}")
        searched = ", ".join(attempted) if attempted else "no ABI files found"
        raise ContractConfigurationError(
            f"No ABI found for '{contract_name}'. Checked configured ABI and fallback paths "
            f"({searched})."
        )

    def get_contract(self, contract_name: str) -> Any:
        """Return a bound contract or raise a clear configuration/deployment error."""
        entry = self._contract_entry(contract_name)
        abi = self._load_abi(contract_name, entry)
        address = self.w3.to_checksum_address(entry["address"])
        bytecode = self.w3.eth.get_code(address)
        if not bytecode or bytecode in (b"\x00", "0x", "0x0"):
            raise ContractNotDeployedError(
                f"{contract_name} has an address configured on {self.network.name} "
                f"({address}) but no deployed bytecode. The local node may have restarted; "
                "redeploy the contracts and update the registry."
            )
        return self.w3.eth.contract(address=address, abi=abi)

    @staticmethod
    def _tuple_fields(value: Any, fields: Sequence[str], label: str) -> dict[str, Any]:
        if isinstance(value, Mapping):
            values = [value.get(name) for name in fields]
        else:
            values = list(value)
        if len(values) != len(fields):
            raise Web3ServiceError(f"{label} returned an unexpected shape.")
        return dict(zip(fields, values))

    def get_pool_info(self) -> dict[str, Any]:
        """Read pool totals and APR/APY values, preserving WAD and BPS units."""
        raw_info = self.get_contract("LendingPool").functions.getPoolInfo().call()
        if isinstance(raw_info, Mapping):
            values = [
                raw_info.get(
                    name,
                    raw_info.get(
                        "".join(
                            part.capitalize() if index else part
                            for index, part in enumerate(name.split("_"))
                        )
                    ),
                )
                for name in _POOL_INFO_FIELDS
            ]
        else:
            values = list(raw_info)
        if len(values) != len(_POOL_INFO_FIELDS):
            raise Web3ServiceError("LendingPool.getPoolInfo returned an unexpected shape.")

        result: dict[str, Any] = {}
        for name, value in zip(_POOL_INFO_FIELDS, values):
            amount = int(value)
            if name.endswith("_bps"):
                result[name] = amount
            elif name in _POOL_WAD_FIELDS:
                result[name] = _format_wad(amount)
            else:
                result[name] = amount

        borrow_apr = int(values[5])
        supply_apr = int(values[6])
        result["borrow_apr"] = {
            **_format_bps(borrow_apr),
            "apy_reference_percent": constants.apr_bps_to_apy_percent(borrow_apr),
            "rate_basis": "simple_apr",
        }
        result["supply_apr"] = {
            **_format_bps(supply_apr),
            "apy_reference_percent": constants.apr_bps_to_apy_percent(supply_apr),
            "rate_basis": "simple_apr",
        }
        return result

    def get_available_liquidity(self) -> dict[str, str]:
        """Return currently available pool liquidity in WAD."""
        value = self.get_contract("LendingPool").functions.getAvailableLiquidity().call()
        return _format_wad(int(value))

    def get_interest_rate_snapshot(self) -> dict[str, Any]:
        """Read the on-chain APR and its separately labeled daily-compounded APY reference."""
        raw = self.get_contract("LendingPool").functions.getInterestRateSnapshot().call()
        fields = (
            "timestamp",
            "utilizationBps",
            "borrowAprBps",
            "supplyAprBps",
            "borrowApyRefBps",
            "supplyApyRefBps",
            "borrowIndexWad",
            "supplyIndexWad",
        )
        snapshot = self._tuple_fields(raw, fields, "LendingPool.getInterestRateSnapshot")
        borrow_apr_bps = int(snapshot["borrowAprBps"])
        supply_apr_bps = int(snapshot["supplyAprBps"])
        return {
            "timestamp": int(snapshot["timestamp"]),
            "utilization": _format_bps(int(snapshot["utilizationBps"])),
            "borrow_apr": {
                **_format_bps(borrow_apr_bps),
                "rate_basis": "simple_apr_per_second",
            },
            "supply_apr": {
                **_format_bps(supply_apr_bps),
                "rate_basis": "simple_apr_per_second",
            },
            "borrow_apy_reference": {
                "bps": int(snapshot["borrowApyRefBps"]),
                "percent": constants.apr_bps_to_percent(int(snapshot["borrowApyRefBps"])),
                "rate_basis": "daily_compounded_reference",
            },
            "supply_apy_reference": {
                "bps": int(snapshot["supplyApyRefBps"]),
                "percent": constants.apr_bps_to_percent(int(snapshot["supplyApyRefBps"])),
                "rate_basis": "daily_compounded_reference",
            },
            "borrow_index": _format_wad(int(snapshot["borrowIndexWad"])),
            "supply_index": _format_wad(int(snapshot["supplyIndexWad"])),
        }

    def get_max_borrowable(self, borrower_address: str) -> dict[str, str]:
        borrower = self._checksum_address(borrower_address, "borrower")
        value = self.get_contract("LendingPool").functions.getMaxBorrowable(borrower).call()
        return _format_wad(int(value))

    def get_remaining_borrow_capacity(self, borrower_address: str) -> dict[str, str]:
        borrower = self._checksum_address(borrower_address, "borrower")
        value = self.get_contract("LendingPool").functions.getRemainingBorrowCapacity(borrower).call()
        return _format_wad(int(value))

    def get_available_to_borrow(self, borrower_address: str) -> dict[str, str]:
        borrower = self._checksum_address(borrower_address, "borrower")
        value = self.get_contract("LendingPool").functions.getAvailableToBorrow(borrower).call()
        return _format_wad(int(value))

    def get_current_ltv_bps(self, borrower_address: str) -> dict[str, Any]:
        borrower = self._checksum_address(borrower_address, "borrower")
        value = int(
            self.get_contract("LendingPool").functions.getCurrentLtvBps(borrower).call()
        )
        infinite = value >= constants.INFINITE_HEALTH_FACTOR
        return {
            "bps": value,
            "percent": None if infinite else constants.apr_bps_to_percent(value),
            "is_infinite": infinite,
        }

    def calculate_accrued_interest(self, borrower_address: str) -> dict[str, str]:
        borrower = self._checksum_address(borrower_address, "borrower")
        value = self.get_contract("LendingPool").functions.calculateAccruedInterest(borrower).call()
        return _format_wad(int(value))

    def preview_borrower_interest(
        self, borrower_address: str, extra_seconds: int
    ) -> dict[str, str]:
        borrower = self._checksum_address(borrower_address, "borrower")
        value = self.get_contract("LendingPool").functions.previewBorrowerInterest(
            borrower, extra_seconds
        ).call()
        return _format_wad(int(value))

    def get_loan_position(self, borrower_address: str) -> dict[str, Any]:
        borrower = self._checksum_address(borrower_address, "borrower")
        raw = self.get_contract("LendingPool").functions.getLoanPosition(borrower).call()
        fields = (
            "borrower", "isNFTCollateral", "collateralAmount", "collateralTokenId",
            "receiptTokenId", "principal", "borrowIndexSnapshot", "accruedInterest",
            "startTimestamp", "lastInterestUpdate", "ipfsAgreementCid", "active",
        )
        position = self._tuple_fields(raw, fields, "LendingPool.getLoanPosition")
        return {
            "borrower": self.w3.to_checksum_address(position["borrower"]),
            "is_nft_collateral": bool(position["isNFTCollateral"]),
            "collateral_amount": _format_wad(int(position["collateralAmount"])),
            "collateral_token_id": int(position["collateralTokenId"]),
            "receipt_token_id": int(position["receiptTokenId"]),
            "principal": _format_wad(int(position["principal"])),
            "borrow_index_snapshot": _format_wad(int(position["borrowIndexSnapshot"])),
            "accrued_interest": _format_wad(int(position["accruedInterest"])),
            "start_timestamp": int(position["startTimestamp"]),
            "last_interest_update": int(position["lastInterestUpdate"]),
            "ipfs_agreement_cid": position["ipfsAgreementCid"],
            "active": bool(position["active"]),
        }

    def get_lender_position(self, position_id: int) -> dict[str, Any]:
        raw = self.get_contract("LendingPool").functions.getLenderPosition(position_id).call()
        fields = (
            "positionId", "principal", "supplyIndexSnapshot",
            "accruedInterest", "depositedAt", "active",
        )
        position = self._tuple_fields(raw, fields, "LendingPool.getLenderPosition")
        return {
            "position_id": int(position["positionId"]),
            "principal": _format_wad(int(position["principal"])),
            "supply_index_snapshot": _format_wad(int(position["supplyIndexSnapshot"])),
            "accrued_interest": _format_wad(int(position["accruedInterest"])),
            "deposited_at": int(position["depositedAt"]),
            "active": bool(position["active"]),
        }

    def get_lender_earned_interest(self, position_id: int) -> dict[str, str]:
        value = self.get_contract("LendingPool").functions.getLenderEarnedInterest(position_id).call()
        return _format_wad(int(value))

    def preview_lender_earned_interest(
        self, position_id: int, extra_seconds: int
    ) -> dict[str, str]:
        value = self.get_contract("LendingPool").functions.previewLenderEarnedInterest(
            position_id, extra_seconds
        ).call()
        return _format_wad(int(value))

    def get_lender_claimable_balance(self, position_id: int) -> dict[str, str]:
        value = self.get_contract("LendingPool").functions.getLenderClaimableBalance(position_id).call()
        return _format_wad(int(value))

    def get_max_withdrawable(self, position_id: int) -> dict[str, str]:
        value = self.get_contract("LendingPool").functions.getMaxWithdrawable(position_id).call()
        return _format_wad(int(value))

    def get_myusdt_balance(self, account_address: str) -> dict[str, str]:
        account = self._checksum_address(account_address, "account")
        value = self.get_contract("MyUSDT").functions.balanceOf(account).call()
        return _format_wad(int(value))

    def get_myusdt_allowance(
        self, owner_address: str, spender_address: str
    ) -> dict[str, str]:
        owner = self._checksum_address(owner_address, "owner")
        spender = self._checksum_address(spender_address, "spender")
        value = self.get_contract("MyUSDT").functions.allowance(owner, spender).call()
        return _format_wad(int(value))

    def get_debt_token_balance(self, account_address: str) -> dict[str, str]:
        account = self._checksum_address(account_address, "account")
        value = self.get_contract("DebtToken").functions.balanceOf(account).call()
        return _format_wad(int(value))

    def get_lending_position_owner(self, token_id: int) -> str:
        owner = self.get_contract("LendingPositionNFT").functions.ownerOf(token_id).call()
        return self.w3.to_checksum_address(owner)

    def get_active_collateral_receipt(self, borrower_address: str) -> int:
        borrower = self._checksum_address(borrower_address, "borrower")
        value = self.get_contract("CollateralReceiptNFT").functions.activeReceiptOf(borrower).call()
        return int(value)

    def get_collateral_receipt_info(self, receipt_id: int) -> dict[str, Any]:
        raw = self.get_contract("CollateralReceiptNFT").functions.getReceiptInfo(receipt_id).call()
        fields = ("borrower", "isNFT", "assetIdOrAmount", "depositedAt", "active")
        receipt = self._tuple_fields(raw, fields, "CollateralReceiptNFT.getReceiptInfo")
        asset_value = int(receipt["assetIdOrAmount"])
        return {
            "borrower": self.w3.to_checksum_address(receipt["borrower"]),
            "is_nft": bool(receipt["isNFT"]),
            "asset_id_or_amount": (
                asset_value if receipt["isNFT"] else _format_wad(asset_value)
            ),
            "deposited_at": int(receipt["depositedAt"]),
            "active": bool(receipt["active"]),
        }

    def get_collateral_nft_owner(self, token_id: int) -> str:
        owner = self.get_contract("CollateralNFT").functions.ownerOf(token_id).call()
        return self.w3.to_checksum_address(owner)

    def get_collateral_nft_valuation(self, token_id: int) -> dict[str, str]:
        value = self.get_contract("CollateralNFT").functions.valuation(token_id).call()
        return _format_wad(int(value))

    def get_collateral_nft_approval_status(
        self, owner_address: str, spender_address: str, token_id: int
    ) -> dict[str, Any]:
        """Check whether spender is approved for a specific CollateralNFT tokenId."""
        owner = self._checksum_address(owner_address, "owner")
        spender = self._checksum_address(spender_address, "spender")
        nft = self.get_contract("CollateralNFT")
        approved_raw = nft.functions.getApproved(token_id).call()
        approved_for_all = bool(nft.functions.isApprovedForAll(owner, spender).call())
        approved_address = (
            self.w3.to_checksum_address(approved_raw)
            if isinstance(approved_raw, str) and self.w3.is_address(approved_raw)
            else None
        )
        is_approved = approved_for_all or (
            approved_address is not None and approved_address.lower() == spender.lower()
        )
        return {
            "token_id": int(token_id),
            "approved_address": approved_address,
            "approved_for_all": approved_for_all,
            "is_approved": is_approved,
        }

    def get_latest_block_context(self) -> dict[str, int]:
        """Read latest block number and timestamp for snapshot freshness metadata."""
        block_number: int | None = None
        timestamp: int | None = None
        get_block = getattr(self.w3.eth, "get_block", None)
        if callable(get_block):
            try:
                latest = get_block("latest")
                if latest is not None:
                    raw_number = (
                        latest.get("number")
                        if isinstance(latest, Mapping)
                        else getattr(latest, "number", None)
                    )
                    raw_ts = (
                        latest.get("timestamp")
                        if isinstance(latest, Mapping)
                        else getattr(latest, "timestamp", None)
                    )
                    if raw_number is not None:
                        block_number = int(raw_number)
                    if raw_ts is not None:
                        timestamp = int(raw_ts)
            except Exception:
                pass
        if block_number is None:
            raw_bn = getattr(self.w3.eth, "block_number", 0)
            block_number = int(raw_bn) if raw_bn is not None else 0
        if timestamp is None:
            try:
                timestamp = int(self.get_interest_rate_snapshot()["timestamp"])
            except Exception:
                timestamp = 0
        return {
            "block_number": block_number,
            "as_of_timestamp": timestamp,
        }

    def get_borrower_risk(self, borrower_address: str) -> dict[str, Any]:
        """Read collateral, debt, and on-chain Health Factor for a wallet."""
        borrower = self._checksum_address(borrower_address, "borrower")
        pool = self.get_contract("LendingPool")
        collateral_wad = int(pool.functions.getCollateralValue(borrower).call())
        debt_wad = int(pool.functions.getTotalDebt(borrower).call())
        onchain_health_factor_wad = int(pool.functions.getHealthFactor(borrower).call())
        health_factor_wad = (
            constants.INFINITE_HEALTH_FACTOR if debt_wad == 0 else onchain_health_factor_wad
        )
        return {
            "collateral_value": _format_wad(collateral_wad),
            "total_debt": _format_wad(debt_wad),
            **constants.format_health_factor_for_api(health_factor_wad),
        }

    def get_liquidation_preview(self, borrower_address: str) -> dict[str, Any]:
        """Wrap LendingPool.getLiquidationPreview(borrower) from HI05."""
        borrower = self._checksum_address(borrower_address, "borrower")
        raw = self.get_contract("LendingPool").functions.getLiquidationPreview(borrower).call()
        fields = (
            "liquidatable",
            "healthFactorWad",
            "totalDebtWad",
            "collateralValueWad",
            "seizeValueWad",
            "isNFTCollateral",
        )
        preview = self._tuple_fields(raw, fields, "LendingPool.getLiquidationPreview")
        debt_wad = int(preview["totalDebtWad"])
        collateral_wad = int(preview["collateralValueWad"])
        seize_wad = int(preview["seizeValueWad"])
        hf_wad = (
            constants.INFINITE_HEALTH_FACTOR
            if debt_wad == 0
            else int(preview["healthFactorWad"])
        )
        formatted_hf = constants.format_health_factor_for_api(hf_wad)
        return {
            "borrower": borrower,
            "collateral_value": _format_wad(collateral_wad),
            "total_debt": _format_wad(debt_wad),
            "seize_value": _format_wad(seize_wad),
            "is_nft_collateral": bool(preview["isNFTCollateral"]),
            **formatted_hf,
            "liquidatable": bool(preview["liquidatable"]),
        }

    def get_oracle_price(self) -> dict[str, Any]:
        """Read current ERC-20 collateral price and price multiplier."""
        oracle = self.get_contract("PriceOracle")
        price_wad = int(oracle.functions.getCollateralTokenPrice().call())
        multiplier_bps = int(oracle.functions.priceMultiplierBps().call())
        return {
            "collateral_token_price": _format_wad(price_wad),
            "price_multiplier_bps": multiplier_bps,
            "price_multiplier_percent": constants.apr_bps_to_percent(multiplier_bps),
        }

    @staticmethod
    def estimate_interest(
        principal_wad: int, apr_bps: int, duration_seconds: int
    ) -> dict[str, Any]:
        """Estimate protocol simple interest; report compounded APY as reference only."""
        interest_wad = constants.calculate_simple_interest(
            principal_wad, apr_bps, duration_seconds
        )
        return {
            "principal": _format_wad(principal_wad),
            "estimated_interest": _format_wad(interest_wad),
            "apr": {
                **_format_bps(apr_bps),
                "rate_basis": "simple_apr",
            },
            "apy_reference_percent": constants.apr_bps_to_apy_percent(apr_bps),
            "duration_seconds": duration_seconds,
        }

    def _checksum_address(self, address: str, field_name: str) -> str:
        if not isinstance(address, str) or not self.w3.is_address(address):
            raise TransactionValidationError(f"Invalid {field_name} address.")
        return self.w3.to_checksum_address(address)

    def _validate_unsigned_transaction(
        self,
        transaction: Mapping[str, Any],
        *,
        expected_to: str | None = None,
        expected_from: str | None = None,
    ) -> dict[str, Any]:
        tx = dict(transaction)
        if int(tx.get("chainId", -1)) != self.chain_id:
            raise TransactionValidationError("Unsigned transaction chainId does not match network.")
        if "to" not in tx or not self.w3.is_address(tx["to"]):
            raise TransactionValidationError("Unsigned transaction has an invalid 'to' address.")
        tx["to"] = self.w3.to_checksum_address(tx["to"])
        if expected_to and tx["to"] != self.w3.to_checksum_address(expected_to):
            raise TransactionValidationError("Unsigned transaction 'to' does not match contract.")
        if expected_from:
            actual_from = tx.get("from")
            if not actual_from or not self.w3.is_address(actual_from):
                raise TransactionValidationError("Unsigned transaction has an invalid 'from' address.")
            if self.w3.to_checksum_address(actual_from) != self.w3.to_checksum_address(expected_from):
                raise TransactionValidationError("Unsigned transaction 'from' does not match wallet.")
            tx["from"] = self.w3.to_checksum_address(actual_from)
        data = tx.get("data")
        if not isinstance(data, str) or not data.startswith("0x") or len(data) % 2:
            raise TransactionValidationError("Unsigned transaction has invalid hexadecimal 'data'.")
        try:
            bytes.fromhex(data[2:])
        except ValueError as exc:
            raise TransactionValidationError("Unsigned transaction has invalid hexadecimal 'data'.") from exc
        value = tx.get("value", 0)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise TransactionValidationError("Unsigned transaction 'value' must be a non-negative integer.")
        tx["value"] = value
        tx["chainId"] = self.chain_id
        return tx

    def build_unsigned_transaction(
        self,
        contract_name: str,
        function_name: str,
        args: Sequence[Any] = (),
        *,
        from_address: str,
        value_wei: int = 0,
        gas_buffer_bps: int = 2_000,
        eth_usd_price: Decimal | str | int | float | None = None,
        principal_wad: int | None = None,
        apr_bps: int | None = None,
        duration_seconds: int | None = None,
        skip_gas_estimation: bool = False,
    ) -> dict[str, Any]:
        """Build a MetaMask-ready transaction and a pre-signing gas/interest quote."""
        sender = self._checksum_address(from_address, "wallet")
        if isinstance(value_wei, bool) or not isinstance(value_wei, int) or value_wei < 0:
            raise TransactionValidationError("value_wei must be a non-negative integer.")
        if not 0 <= gas_buffer_bps <= constants.BPS:
            raise ValueError("gas_buffer_bps must be between 0 and BPS.")
        usd_price = None if eth_usd_price is None else Decimal(str(eth_usd_price))
        if usd_price is not None and (not usd_price.is_finite() or usd_price < 0):
            raise ValueError("eth_usd_price must be a finite non-negative value.")
        configured_chain_id = int(self.w3.eth.chain_id)
        if configured_chain_id != self.chain_id:
            raise TransactionValidationError(
                f"Connected RPC chainId {configured_chain_id} does not match {self.chain_id}."
            )

        contract = self.get_contract(contract_name)
        contract_address = self.w3.to_checksum_address(contract.address)
        function = getattr(contract.functions, function_name)(*args)
        gas_price = int(self.w3.eth.gas_price)
        try:
            # Supply a placeholder gas value so web3.py encodes calldata without
            # invoking an implicit estimate_gas() inside fill_transaction_defaults.
            built = function.build_transaction(
                {
                    "from": sender,
                    "chainId": self.chain_id,
                    "value": value_wei,
                    "gasPrice": gas_price,
                    "gas": 0,
                }
            )
            if not built.get("to"):
                built["to"] = contract_address
        except Exception as exc:
            raise Web3ServiceError(
                f"Could not encode {contract_name}.{function_name} transaction."
            ) from exc

        unsigned = self._validate_unsigned_transaction(
            built, expected_to=contract_address, expected_from=sender
        )
        unsigned["gasPrice"] = gas_price

        if skip_gas_estimation:
            # Do not emit a fake gas=0 limit when on-chain approval is still pending.
            unsigned.pop("gas", None)
            gas_quote: dict[str, Any] = {
                "estimated_gas": None,
                "gas_limit": None,
                "gas_price_wei": str(gas_price),
                "estimated_fee_wei": None,
                "estimated_fee_eth": None,
                "max_fee_wei": None,
                "max_fee_eth": None,
                "eth_usd_price": None if usd_price is None else str(usd_price),
                "estimated_fee_usd": None,
                "estimation_status": "PENDING_APPROVAL",
                "estimation_skipped_reason": (
                    "Token or NFT approval is required before on-chain gas estimation."
                ),
            }
        else:
            gas_estimate = int(
                self.w3.eth.estimate_gas(
                    {
                        "from": sender,
                        "to": contract_address,
                        "data": unsigned["data"],
                        "value": value_wei,
                    }
                )
            )
            gas_limit = (
                gas_estimate * (constants.BPS + gas_buffer_bps) + constants.BPS - 1
            ) // constants.BPS
            estimated_fee_wei = gas_estimate * gas_price
            max_fee_wei = gas_limit * gas_price
            unsigned["gas"] = gas_limit
            gas_quote = {
                "estimated_gas": gas_estimate,
                "gas_limit": gas_limit,
                "gas_price_wei": str(gas_price),
                "estimated_fee_wei": str(estimated_fee_wei),
                "estimated_fee_eth": str(Decimal(estimated_fee_wei) / Decimal(constants.WAD)),
                "max_fee_wei": str(max_fee_wei),
                "max_fee_eth": str(Decimal(max_fee_wei) / Decimal(constants.WAD)),
                "eth_usd_price": None if usd_price is None else str(usd_price),
                "estimated_fee_usd": (
                    None
                    if usd_price is None
                    else str(
                        (
                            Decimal(estimated_fee_wei) / Decimal(constants.WAD) * usd_price
                        ).quantize(Decimal("0.01"))
                    )
                ),
                "estimation_status": "ESTIMATED",
                "estimation_skipped_reason": None,
            }

        interest_fields = (principal_wad, apr_bps, duration_seconds)
        if any(field is not None for field in interest_fields) and not all(
            field is not None for field in interest_fields
        ):
            raise ValueError(
                "principal_wad, apr_bps, and duration_seconds must be provided together."
            )
        interest_quote = (
            None
            if principal_wad is None
            else self.estimate_interest(principal_wad, int(apr_bps), int(duration_seconds))
        )
        return {
            "transaction": unsigned,
            "gas_quote": gas_quote,
            "interest_quote": interest_quote,
            "signing": "client_wallet",
        }

    def sign_system_transaction(self, transaction: Mapping[str, Any]) -> Any:
        """Sign a bot/script transaction with the configured system key, never a user key."""
        key_field = (
            "local_system_private_key"
            if self.network.is_local
            else "sepolia_deployer_private_key"
        )
        private_key = getattr(self.app_settings, key_field, "")
        if not private_key:
            raise Web3ServiceError(
                f"System signing is not configured for {self.network.name}."
            )
        account = Account.from_key(private_key)
        tx = self._validate_unsigned_transaction(
            transaction,
            expected_from=account.address if transaction.get("from") else None,
        )
        tx["from"] = account.address
        if "nonce" not in tx:
            tx["nonce"] = int(self.w3.eth.get_transaction_count(account.address))
        signed = Account.sign_transaction(tx, private_key)
        return getattr(signed, "raw_transaction", getattr(signed, "rawTransaction", None))
