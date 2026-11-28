"""Shared deployment, transaction, and manifest helpers for Q06."""

from __future__ import annotations

import json
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from eth_account import Account
from web3 import Web3
from web3.exceptions import (
    ContractLogicError,
    ProviderConnectionError,
    TooManyRequests,
    Web3RPCError,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CHAIN_LOCAL = 31337
CHAIN_SEPOLIA = 11155111
CONTRACT_NAMES = (
    "MyUSDT",
    "CollateralNFT",
    "CollateralReceiptNFT",
    "DebtToken",
    "LendingPositionNFT",
    "LendingPool",
    "PriceOracle",
)
POOL_BOUND_NAMES = ("CollateralReceiptNFT", "DebtToken", "LendingPositionNFT")
HARDHAT_DEFAULT_PRIVATE_KEYS = frozenset(
    {
        "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",
        "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d",
        "0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a",
        "0x7c852118294e51e653712a81e05800f419141751be58f605c371e15141b007a6",
        "0x47e179ec197488593b187f80a00eb0da91f1b9d0b13f8733639f19c30a34926a",
        "0x8b3a350cf5c34c9194ca85829a2df0ec3153be0318b5e2d3348e872092edffba",
        "0x92db14e403b83dfe3df233f83dfa3a0d7096f21ca9b0d6d6b8d88b2b4ec1564e",
        "0x4bbbf85ce3377467afe5d46f804f221813b2bb87f24d81f60f1fcdbf7cbf4356",
        "0xdbda1821b80551c9d65939329250298aa3472ba22feea921c0cf5d620ea67b97",
        "0x2a871d0798f97d79848a013d4936a73bf4cc922c825d33c1cf7073dff6d409c6",
    }
)


class DeploymentError(RuntimeError):
    """Raised when a deployment or seed transaction cannot be completed."""


class DeploymentConfigurationError(DeploymentError):
    """Raised for missing, unsafe, or mismatched deployment configuration."""


def _build_transaction_with_retry(
    builder: Any,
    transaction: Mapping[str, Any],
    operation: str,
) -> dict[str, Any]:
    retryable_errors = (
        ContractLogicError,
        ProviderConnectionError,
        TooManyRequests,
        Web3RPCError,
    )
    delays = (1, 2, 4, 8)
    for attempt in range(len(delays) + 1):
        try:
            return builder(dict(transaction))
        except retryable_errors as exc:
            if attempt == len(delays):
                raise DeploymentError(
                    f"{operation} transaction estimation failed after "
                    f"{attempt + 1} attempts ({type(exc).__name__})."
                ) from exc
            time.sleep(delays[attempt])
    raise AssertionError("Transaction build retry loop terminated unexpectedly.")


def load_artifact(contract_name: str, abi_dir: Path | None = None) -> dict[str, Any]:
    path = (abi_dir or PROJECT_ROOT / "deployments" / "abi") / f"{contract_name}.json"
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DeploymentConfigurationError(
            f"Không đọc được ABI/bytecode của {contract_name}: {path}"
        ) from exc
    abi = artifact.get("abi")
    bytecode = artifact.get("bytecode")
    if not isinstance(abi, list) or not isinstance(bytecode, str) or not bytecode.startswith("0x"):
        raise DeploymentConfigurationError(
            f"Artifact {contract_name} thiếu ABI hoặc bytecode hợp lệ: {path}"
        )
    if len(bytecode) <= 2 or artifact.get("linkReferences"):
        raise DeploymentConfigurationError(
            f"Bytecode {contract_name} rỗng hoặc cần link thư viện chưa được hỗ trợ."
        )
    return artifact


def _wait_receipt(w3: Any, tx_hash: Any) -> Any:
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    if int(receipt["status"]) != 1:
        raise DeploymentError(f"Giao dịch {Web3.to_hex(tx_hash)} thất bại on-chain.")
    return receipt


def _sign_and_send(w3: Any, account: Any, tx: Mapping[str, Any]) -> Any:
    transaction = dict(tx)
    transaction.setdefault("from", account.address)
    transaction.setdefault("chainId", int(w3.eth.chain_id))
    transaction.setdefault(
        "nonce",
        int(w3.eth.get_transaction_count(account.address, "pending")),
    )
    transaction.setdefault("gasPrice", int(w3.eth.gas_price))
    if "gas" not in transaction:
        transaction["gas"] = int(w3.eth.estimate_gas(transaction))
    signed = Account.sign_transaction(transaction, account.key)
    raw_tx = getattr(signed, "raw_transaction", getattr(signed, "rawTransaction", None))
    if raw_tx is None:
        raise DeploymentError("Không lấy được signed raw transaction từ eth-account.")
    return w3.eth.send_raw_transaction(raw_tx)


def deploy_contract(
    w3: Any,
    account: Any,
    artifact: Mapping[str, Any],
    constructor_args: Sequence[Any] = (),
) -> tuple[Any, Any]:
    factory = w3.eth.contract(abi=artifact["abi"], bytecode=artifact["bytecode"])
    transaction = _build_transaction_with_retry(
        factory.constructor(*constructor_args).build_transaction,
        {
            "from": account.address,
            "chainId": int(w3.eth.chain_id),
            "nonce": int(w3.eth.get_transaction_count(account.address, "pending")),
            "gasPrice": int(w3.eth.gas_price),
        },
        f"Deploy {artifact.get('contractName', 'contract')}",
    )
    tx_hash = _sign_and_send(w3, account, transaction)
    receipt = _wait_receipt(w3, tx_hash)
    address = receipt.get("contractAddress")
    if not address or not w3.is_address(address):
        raise DeploymentError(
            f"Receipt deploy {artifact.get('contractName', 'contract')} thiếu contractAddress."
        )
    contract = w3.eth.contract(address=address, abi=artifact["abi"])
    return contract, receipt


def transact(
    w3: Any,
    account: Any,
    contract: Any,
    function_name: str,
    *args: Any,
) -> Any:
    try:
        function = getattr(contract.functions, function_name)(*args)
    except (AttributeError, TypeError) as exc:
        raise DeploymentError(
            f"Không tạo được lời gọi {function_name} với tham số hợp lệ."
        ) from exc
    transaction = _build_transaction_with_retry(
        function.build_transaction,
        {
            "from": account.address,
            "chainId": int(w3.eth.chain_id),
            "nonce": int(w3.eth.get_transaction_count(account.address, "pending")),
            "gasPrice": int(w3.eth.gas_price),
        },
        f"Build {function_name}",
    )
    return _wait_receipt(w3, _sign_and_send(w3, account, transaction))


def call(contract: Any, function_name: str, *args: Any) -> Any:
    try:
        return getattr(contract.functions, function_name)(*args).call()
    except Exception as exc:
        raise DeploymentError(f"Đọc {function_name} từ contract thất bại.") from exc


def receipt_info(receipt: Any, explorer_url: str = "") -> dict[str, Any]:
    tx_hash = Web3.to_hex(receipt["transactionHash"])
    info: dict[str, Any] = {
        "txHash": tx_hash,
        "blockNumber": int(receipt["blockNumber"]),
    }
    if explorer_url:
        info["explorerUrl"] = f"{explorer_url.rstrip('/')}/tx/{tx_hash}"
    return info


def deploy_bundle(
    w3: Any,
    account: Any,
    *,
    network_name: str,
    chain_id: int,
    explorer_url: str,
    abi_dir: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Deploy the seven ABI artifacts, bind Pool-controlled tokens and the oracle."""
    if int(w3.eth.chain_id) != chain_id:
        raise DeploymentConfigurationError(
            f"Chain ID RPC không khớp: cần {chain_id}, nhận {int(w3.eth.chain_id)}."
        )

    artifacts = {name: load_artifact(name, abi_dir) for name in CONTRACT_NAMES}
    deployed: dict[str, Any] = {}
    manifest_contracts: dict[str, Any] = {}

    def deploy(name: str, args: Sequence[Any] = ()) -> Any:
        contract, receipt = deploy_contract(w3, account, artifacts[name], args)
        address = Web3.to_checksum_address(contract.address)
        deployed[name] = contract
        record = {
            "address": address,
            **receipt_info(receipt, explorer_url),
            "deployer": account.address,
            "abiPath": f"deployments/abi/{name}.json",
            "status": "DEPLOYED",
        }
        manifest_contracts[name] = record
        return contract

    myusdt = deploy("MyUSDT")
    collateral_nft = deploy("CollateralNFT")
    receipt_nft = deploy("CollateralReceiptNFT")
    debt_token = deploy("DebtToken")
    position_nft = deploy("LendingPositionNFT")

    pool = deploy(
        "LendingPool",
        (
            myusdt.address,
            myusdt.address,
            collateral_nft.address,
            receipt_nft.address,
            debt_token.address,
            position_nft.address,
            Web3.to_checksum_address("0x0000000000000000000000000000000000000000"),
        ),
    )
    binding_hashes: dict[str, str] = {}
    for name in POOL_BOUND_NAMES:
        receipt = transact(w3, account, deployed[name], "setLendingPool", pool.address)
        bound_address = call(deployed[name], "lendingPool")
        if Web3.to_checksum_address(bound_address) != Web3.to_checksum_address(pool.address):
            raise DeploymentError(f"Kiểm tra liên kết LendingPool thất bại cho {name}.")
        binding_hashes[name] = Web3.to_hex(receipt["transactionHash"])
        manifest_contracts[name]["status"] = "BOUND_TO_POOL"
        manifest_contracts[name]["lendingPool"] = pool.address
        manifest_contracts[name]["bindTxHash"] = binding_hashes[name]

    oracle = deploy("PriceOracle", (collateral_nft.address,))
    oracle_bind_receipt = transact(
        w3, account, pool, "setPriceOracle", oracle.address
    )
    if Web3.to_checksum_address(call(pool, "priceOracle")) != Web3.to_checksum_address(
        oracle.address
    ):
        raise DeploymentError("Kiểm tra liên kết PriceOracle trong LendingPool thất bại.")

    for name in ("LendingPool", "PriceOracle"):
        manifest_contracts[name]["status"] = "DEPLOYED_AND_BOUND"
    manifest_contracts["LendingPool"]["boundTokens"] = binding_hashes
    manifest_contracts["LendingPool"]["priceOracle"] = oracle.address
    manifest_contracts["LendingPool"]["priceOracleBindTxHash"] = Web3.to_hex(
        oracle_bind_receipt["transactionHash"]
    )
    manifest_contracts["PriceOracle"].update(
        {
            "owner": call(oracle, "owner"),
            "collateralNFT": collateral_nft.address,
            "lendingPool": pool.address,
            "bindTxHash": Web3.to_hex(oracle_bind_receipt["transactionHash"]),
            "collateralTokenPriceWad": str(call(oracle, "getCollateralTokenPrice")),
            "priceMultiplierBps": str(call(oracle, "priceMultiplierBps")),
        }
    )
    manifest_contracts["LendingPool"]["interfaceAbiPath"] = (
        "deployments/abi/interfaces/ILendingPool.json"
    )
    manifest = {
        "network": network_name,
        "chainId": chain_id,
        "explorerUrl": explorer_url,
        "deployedAt": datetime.now(timezone.utc).isoformat(),
        "contracts": manifest_contracts,
    }
    return manifest, deployed


def registry_network(manifest: Mapping[str, Any]) -> dict[str, Any]:
    contracts: dict[str, Any] = {}
    for name, record in manifest["contracts"].items():
        contracts[name] = {
            "address": record["address"],
            "abiPath": record["abiPath"],
            "txHash": record["txHash"],
            "explorerUrl": record.get("explorerUrl"),
        }
    return {
        "chainId": int(manifest["chainId"]),
        "explorerUrl": manifest.get(
            "explorerUrl",
            "https://sepolia.etherscan.io"
            if int(manifest["chainId"]) == CHAIN_SEPOLIA
            else "http://127.0.0.1:8545",
        ),
        "contracts": contracts,
    }


def build_frontend_config(
    manifest: Mapping[str, Any], abi_dir: Path | None = None
) -> dict[str, Any]:
    contracts: dict[str, Any] = {}
    for name, record in manifest["contracts"].items():
        artifact = load_artifact(name, abi_dir)
        contracts[name] = {
            "address": record["address"],
            "abi": artifact["abi"],
            "txHash": record["txHash"],
        }
    network_name = str(manifest["network"])
    return {
        "network": "local" if network_name == "localhost" else network_name,
        "chainId": int(manifest["chainId"]),
        "explorerUrl": manifest.get(
            "explorerUrl",
            "https://sepolia.etherscan.io"
            if int(manifest["chainId"]) == CHAIN_SEPOLIA
            else "http://127.0.0.1:8545",
        ),
        "contracts": contracts,
    }


def write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f"{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary_path = Path(stream.name)
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary_path.replace(path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def sync_manifests(
    manifest: Mapping[str, Any],
    *,
    deployment_path: Path,
    backend_config_path: Path,
    frontend_config_path: Path,
    abi_dir: Path | None = None,
) -> None:
    """Atomically emit the selected network's manifest, backend registry and UI ABI set."""
    try:
        backend_config = json.loads(backend_config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DeploymentConfigurationError(
            f"Không đọc được backend registry hiện tại: {backend_config_path}"
        ) from exc
    network_name = str(manifest["network"])
    registry_name = "local" if network_name == "localhost" else network_name
    backend_config[registry_name] = registry_network(manifest)
    write_json_atomic(deployment_path, manifest)
    write_json_atomic(backend_config_path, backend_config)
    write_json_atomic(frontend_config_path, build_frontend_config(manifest, abi_dir))


def local_test_accounts(mnemonic: str | None = None) -> list[dict[str, Any]]:
    """Derive the public Hardhat test accounts for local-only seeding."""
    phrase = mnemonic or os.getenv(
        "LOCAL_MNEMONIC",
        "test test test test test test test test test test test junk",
    )
    Account.enable_unaudited_hdwallet_features()
    labels = (
        "Deployer / Admin / System Seed",
        "Lender A",
        "Borrower A",
        "Lender B",
        "Liquidator / Keeper",
        "Borrower B",
        "Hung",
        "Hieu",
        "Quan",
        "Lam",
    )
    return [
        {
            "index": index,
            "role": label,
            "account": Account.from_mnemonic(
                phrase, account_path=f"m/44'/60'/0'/0/{index}"
            ),
        }
        for index, label in enumerate(labels)
    ]
