"""Deploy all local contracts from exported artifacts and seed a demo state."""

from __future__ import annotations

import os
import sys
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Mapping

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
from web3 import HTTPProvider, Web3

from scripts.deploy_utils import (
    CHAIN_LOCAL,
    DeploymentConfigurationError,
    DeploymentError,
    PROJECT_ROOT,
    call,
    deploy_bundle,
    local_test_accounts,
    sync_manifests,
    transact,
)

WAD = 10**18
SEED_AMOUNT_WAD = 1_000 * WAD


def _account_by_index(accounts: list[dict[str, Any]], index: int) -> Any:
    for row in accounts:
        if int(row["index"]) == index:
            return row["account"]
    raise DeploymentConfigurationError(f"Không tìm thấy tài khoản Hardhat index={index}.")


def _minted_token_id(contract: Any, receipt: Any) -> int:
    try:
        transfer_logs = contract.events.Transfer().process_receipt(receipt)
        minted = [
            int(log["args"]["tokenId"])
            for log in transfer_logs
            if str(log["args"].get("from", "")).lower()
            == "0x0000000000000000000000000000000000000000"
        ]
    except Exception as exc:
        raise DeploymentError("Không đọc được tokenId từ event mint CollateralNFT.") from exc
    if len(minted) != 1:
        raise DeploymentError("Receipt mint phải chứa đúng một event ERC721 Transfer.")
    return minted[0]


def seed_local(
    w3: Any,
    contracts: Mapping[str, Any],
    accounts: list[dict[str, Any]],
) -> dict[str, Any]:
    """Faucet demo wallets, mint collateral IDs 1/2, and supply lender liquidity."""
    seed_records: dict[str, dict[str, Any]] = {}
    token = contracts["MyUSDT"]
    pool = contracts["LendingPool"]

    for row in accounts[1:]:
        account = row["account"]
        receipt = transact(
            w3, accounts[0]["account"], token, "faucet", account.address, SEED_AMOUNT_WAD
        )
        seed_records[account.address.lower()] = {
            "index": int(row["index"]),
            "role": str(row["role"]),
            "address": account.address,
            "balance": str(call(token, "balanceOf", account.address)),
            "balanceMyUSDT": "1000.0",
            "seedTxHash": Web3.to_hex(receipt["transactionHash"]),
        }

    collateral_nft = contracts["CollateralNFT"]
    lender = _account_by_index(accounts, 1)
    borrower = _account_by_index(accounts, 2)
    mint_lender = transact(
        w3,
        accounts[0]["account"],
        collateral_nft,
        "mintCollateral",
        lender.address,
        SEED_AMOUNT_WAD,
        "ipfs://q06-local-lender-collateral",
    )
    mint_borrower = transact(
        w3,
        accounts[0]["account"],
        collateral_nft,
        "mintCollateral",
        borrower.address,
        SEED_AMOUNT_WAD,
        "ipfs://q06-local-borrower-collateral",
    )
    lender_token_id = _minted_token_id(collateral_nft, mint_lender)
    borrower_token_id = _minted_token_id(collateral_nft, mint_borrower)
    if lender_token_id != 1 or borrower_token_id != 2:
        raise DeploymentError(
            f"CollateralNFT seed IDs không đúng: Lender #{lender_token_id}, Borrower #{borrower_token_id}; cần #1/#2."
        )
    if (
        Web3.to_checksum_address(call(collateral_nft, "ownerOf", lender_token_id))
        != Web3.to_checksum_address(lender.address)
        or Web3.to_checksum_address(call(collateral_nft, "ownerOf", borrower_token_id))
        != Web3.to_checksum_address(borrower.address)
    ):
        raise DeploymentError("Xác minh chủ sở hữu CollateralNFT seed #1/#2 thất bại.")

    lender_approve = transact(
        w3,
        lender,
        token,
        "approve",
        pool.address,
        SEED_AMOUNT_WAD,
    )
    lender_deposit = transact(
        w3, lender, pool, "depositLender", SEED_AMOUNT_WAD
    )
    pool_info = call(pool, "getPoolInfo")
    total_supplied = int(
        pool_info[0]
        if not isinstance(pool_info, Mapping)
        else pool_info.get("totalSupplied", pool_info.get("total_supplied", 0))
    )
    if total_supplied < SEED_AMOUNT_WAD:
        raise DeploymentError("Thanh khoản ban đầu trong LendingPool không đủ sau seed.")

    seed_records[lender.address.lower()]["lenderApprovalTxHash"] = Web3.to_hex(
        lender_approve["transactionHash"]
    )
    seed_records[lender.address.lower()]["lenderDepositTxHash"] = Web3.to_hex(
        lender_deposit["transactionHash"]
    )
    seed_records[lender.address.lower()]["lendingPositionId"] = "1"
    seed_records[borrower.address.lower()]["collateralTokenId"] = "2"
    seed_records[lender.address.lower()]["collateralTokenId"] = "1"

    return {
        "testAccounts": [
            {
                "index": 0,
                "role": str(accounts[0]["role"]),
                "address": accounts[0]["account"].address,
                "balance": str(call(token, "balanceOf", accounts[0]["account"].address)),
                "balanceMyUSDT": str(
                    Decimal(
                        int(call(token, "balanceOf", accounts[0]["account"].address))
                    )
                    / Decimal(WAD)
                ),
                "seedTxHash": None,
            },
            *[seed_records[row["account"].address.lower()] for row in accounts[1:]],
        ],
        "collateralNFTSeeds": {
            "1": {
                "owner": lender.address,
                "valuationWad": str(SEED_AMOUNT_WAD),
                "txHash": Web3.to_hex(mint_lender["transactionHash"]),
            },
            "2": {
                "owner": borrower.address,
                "valuationWad": str(SEED_AMOUNT_WAD),
                "txHash": Web3.to_hex(mint_borrower["transactionHash"]),
            },
        },
        "initialLiquidityWad": str(SEED_AMOUNT_WAD),
        "initialLiquidityTxHash": Web3.to_hex(lender_deposit["transactionHash"]),
        "seededAt": datetime.now(timezone.utc).isoformat(),
    }


def _create_local_audit_record(
    w3: Any,
    *,
    project_root: Path,
    metadata_store_path: Path | None = None,
) -> dict[str, Any]:
    from backend.services.credit_and_audit_ipfs import CreditAndAuditIPFSService
    from backend.services.web3_service import Web3Service
    from backend.config.settings import settings
    from src.ipfs.encryption import DocumentEncryptor
    from src.ipfs.ipfs_client import IPFSClient, IPFSConfig
    from src.ipfs.rbac import AuthorizedIPFSGateway

    raw_key = os.getenv("DOCUMENT_AES_KEY_HEX", "").strip()
    if not raw_key:
        raise DeploymentConfigurationError(
            "Thiếu DOCUMENT_AES_KEY_HEX trong .env; cần khóa AES hợp lệ để khởi tạo Q04."
        )
    try:
        encryptor = DocumentEncryptor.from_hex_key(raw_key)
    except ValueError as exc:
        raise DeploymentConfigurationError(
            "DOCUMENT_AES_KEY_HEX không hợp lệ; cần khóa AES-256-GCM 32 bytes dạng hex."
        ) from exc

    ipfs_config = replace(
        IPFSConfig.from_env(),
        provider="local_fallback",
        pinata_jwt="",
        pinata_api_key="",
        pinata_secret_api_key="",
    )
    gateway = AuthorizedIPFSGateway(IPFSClient(ipfs_config), encryptor)
    service = CreditAndAuditIPFSService(
        Web3Service(network_name="local", w3=w3, app_settings=settings),
        gateway=gateway,
        metadata_store_path=(
            metadata_store_path
            or project_root / "backend" / "data" / "credit_audit_ipfs_index.json"
        ),
    )
    result = service.generate_monthly_audit_logs(
        from_block=0,
        to_block="latest",
        seed_simulated_months=6,
    )
    simulated = [
        row for row in result["entries"] if row["data_kind"] == "SIMULATED"
    ]
    if not simulated:
        raise DeploymentError("Q04 không tạo được bản ghi Audit Logs SIMULATED.")
    return {
        "json": result["json"],
        "csv": result["csv"],
        "simulatedPeriods": [row["period"] for row in simulated],
        "containsPii": result["document"].contains_pii,
    }


def run_local_deployment(
    w3: Any,
    *,
    accounts: list[dict[str, Any]] | None = None,
    project_root: Path = PROJECT_ROOT,
    audit_service: Callable[..., dict[str, Any]] | None = None,
    abi_dir: Path | None = None,
) -> dict[str, Any]:
    """Deploy + bind + seed and write all three local configuration manifests."""
    if int(w3.eth.chain_id) != CHAIN_LOCAL:
        raise DeploymentConfigurationError(
            f"Local deploy chỉ chạy trên Hardhat Chain ID {CHAIN_LOCAL}; nhận {int(w3.eth.chain_id)}."
        )
    test_accounts = accounts or local_test_accounts()
    if len(test_accounts) < 3:
        raise DeploymentConfigurationError("Cần ít nhất 3 ví Hardhat để seed local.")
    deployer = test_accounts[0]["account"]
    manifest, contracts = deploy_bundle(
        w3,
        deployer,
        network_name="localhost",
        chain_id=CHAIN_LOCAL,
        explorer_url="http://127.0.0.1:8545",
        abi_dir=abi_dir or project_root / "deployments" / "abi",
    )
    manifest["contracts"]["MyUSDT"].update(
        {
            "decimals": 18,
            "initialSupply": str(call(contracts["MyUSDT"], "INITIAL_SUPPLY")),
            "maxFaucetAmount": str(call(contracts["MyUSDT"], "MAX_FAUCET_AMOUNT")),
        }
    )
    manifest["seed"] = seed_local(w3, contracts, test_accounts)

    deployment_path = project_root / "deployments" / "localhost.json"
    backend_path = project_root / "backend" / "config" / "contracts.json"
    frontend_path = project_root / "frontend" / "src" / "config" / "contracts.json"
    sync_manifests(
        manifest,
        deployment_path=deployment_path,
        backend_config_path=backend_path,
        frontend_config_path=frontend_path,
        abi_dir=abi_dir or project_root / "deployments" / "abi",
    )

    audit_writer = audit_service or _create_local_audit_record
    manifest["auditLogs"] = audit_writer(
        w3,
        project_root=project_root,
        metadata_store_path=project_root
        / "backend"
        / "data"
        / "credit_audit_ipfs_index.json",
    )
    sync_manifests(
        manifest,
        deployment_path=deployment_path,
        backend_config_path=backend_path,
        frontend_config_path=frontend_path,
        abi_dir=abi_dir or project_root / "deployments" / "abi",
    )
    return manifest


def main() -> int:
    try:
        load_dotenv(PROJECT_ROOT / ".env")
        rpc_url = os.getenv("LOCAL_RPC_URL", "http://127.0.0.1:8545").strip()
        if not rpc_url:
            raise DeploymentConfigurationError("LOCAL_RPC_URL không được để trống.")
        w3 = Web3(HTTPProvider(rpc_url, request_kwargs={"timeout": 5}))
        if not w3.is_connected():
            raise DeploymentConfigurationError(
                f"Không kết nối được Hardhat RPC tại {rpc_url}; hãy khởi động node trước."
            )
        manifest = run_local_deployment(w3)
    except (DeploymentError, OSError, ValueError) as exc:
        print(f"LỖI Q06 LOCAL: {exc}", file=sys.stderr)
        return 1
    print("Deploy và seed Hardhat hoàn tất.")
    print(f"LendingPool: {manifest['contracts']['LendingPool']['address']}")
    print(f"PriceOracle: {manifest['contracts']['PriceOracle']['address']}")
    print(f"Audit Logs JSON CID: {manifest['auditLogs']['json']['cid']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
