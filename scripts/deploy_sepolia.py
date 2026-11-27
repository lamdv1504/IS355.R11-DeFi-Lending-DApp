"""Safely deploy, bind, smoke-test, and sync the seven Sepolia contracts."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
from eth_account import Account
from web3 import HTTPProvider, Web3

from scripts.deploy_utils import (
    CHAIN_SEPOLIA,
    HARDHAT_DEFAULT_PRIVATE_KEYS,
    DeploymentConfigurationError,
    DeploymentError,
    PROJECT_ROOT,
    call,
    deploy_bundle,
    sync_manifests,
    transact,
)

WAD = 10**18


def validate_sepolia_environment(
    environ: Mapping[str, str] | None = None,
) -> tuple[str, str]:
    """Validate required Sepolia variables and reject all standard Hardhat keys."""
    env = os.environ if environ is None else environ
    rpc_url = env.get("SEPOLIA_RPC_URL", "").strip()
    private_key = env.get("SEPOLIA_DEPLOYER_PRIVATE_KEY", "").strip().lower()
    if not rpc_url:
        raise DeploymentConfigurationError(
            "Thiếu SEPOLIA_RPC_URL. Hãy cấu hình RPC Sepolia trước khi deploy."
        )
    if not private_key:
        raise DeploymentConfigurationError(
            "Thiếu SEPOLIA_DEPLOYER_PRIVATE_KEY. Hãy cấu hình ví deployer Sepolia."
        )
    if not private_key.startswith("0x"):
        private_key = f"0x{private_key}"
    if private_key in HARDHAT_DEFAULT_PRIVATE_KEYS:
        raise DeploymentConfigurationError(
            "TỪ CHỐI deploy: SEPOLIA_DEPLOYER_PRIVATE_KEY đang dùng private key mặc định Hardhat."
        )
    try:
        Account.from_key(private_key)
    except (ValueError, TypeError) as exc:
        raise DeploymentConfigurationError(
            "SEPOLIA_DEPLOYER_PRIVATE_KEY không phải private key Ethereum hợp lệ."
        ) from exc
    return rpc_url, private_key


def _smoke_test(
    w3: Any,
    account: Any,
    contracts: Mapping[str, Any],
    *,
    explorer_url: str,
) -> list[dict[str, Any]]:
    """Exercise faucet, lender deposit, NFT collateral, borrow and full repay."""
    records: list[dict[str, Any]] = []

    def send(label: str, contract: Any, function_name: str, *args: Any) -> Any:
        receipt = transact(w3, account, contract, function_name, *args)
        from scripts.deploy_utils import receipt_info

        records.append({"action": label, **receipt_info(receipt, explorer_url)})
        return receipt

    amount = 1_000 * WAD
    send("faucet", contracts["MyUSDT"], "faucet", account.address, amount)
    send("approve_lender", contracts["MyUSDT"], "approve", contracts["LendingPool"].address, amount)
    send("depositLender", contracts["LendingPool"], "depositLender", 500 * WAD)

    mint_receipt = send(
        "mintCollateralNFT",
        contracts["CollateralNFT"],
        "mintCollateral",
        account.address,
        1_000 * WAD,
        "ipfs://q06-sepolia-smoke-collateral",
    )
    mint_logs = contracts["CollateralNFT"].events.Transfer().process_receipt(mint_receipt)
    token_ids = [
        int(log["args"]["tokenId"])
        for log in mint_logs
        if str(log["args"].get("from", "")).lower()
        == "0x0000000000000000000000000000000000000000"
    ]
    if len(token_ids) != 1:
        raise DeploymentError("Smoke test không đọc được tokenId NFT vừa mint.")
    token_id = token_ids[0]
    send("approve_collateral_nft", contracts["CollateralNFT"], "approve", contracts["LendingPool"].address, token_id)
    send("depositCollateral", contracts["LendingPool"], "depositCollateral", token_id, True)

    borrowed_wad = 100 * WAD
    send("borrow", contracts["LendingPool"], "borrow", borrowed_wad, "q06-sepolia-smoke")
    total_debt_wad = int(call(contracts["LendingPool"], "getTotalDebt", account.address))
    if total_debt_wad <= 0:
        raise DeploymentError("Smoke test borrow không tạo dư nợ.")
    send(
        "approve_repayment",
        contracts["MyUSDT"],
        "approve",
        contracts["LendingPool"].address,
        total_debt_wad + WAD,
    )
    send(
        "repay",
        contracts["LendingPool"],
        "repay",
        total_debt_wad + WAD,
    )
    remaining = int(call(contracts["LendingPool"], "getTotalDebt", account.address))
    if remaining != 0:
        raise DeploymentError(
            f"Smoke test repay chưa tất toán dư nợ: còn {remaining} WAD."
        )
    return records


def run_sepolia_deployment(
    *,
    rpc_url: str,
    private_key: str,
    project_root: Path = PROJECT_ROOT,
    w3: Any | None = None,
    abi_dir: Path | None = None,
) -> dict[str, Any]:
    """Deploy only after strict network/balance checks, then smoke-test and sync configs."""
    if not rpc_url.strip():
        raise DeploymentConfigurationError("Thiếu SEPOLIA_RPC_URL.")
    normalized_key = private_key.strip().lower()
    if normalized_key and not normalized_key.startswith("0x"):
        normalized_key = "0x" + normalized_key
    if not normalized_key:
        raise DeploymentConfigurationError("Thiếu SEPOLIA_DEPLOYER_PRIVATE_KEY.")
    if normalized_key in HARDHAT_DEFAULT_PRIVATE_KEYS:
        raise DeploymentConfigurationError(
            "TỪ CHỐI deploy: private key mặc định Hardhat không được dùng trên Sepolia."
        )
    try:
        account = Account.from_key(normalized_key)
    except (ValueError, TypeError) as exc:
        raise DeploymentConfigurationError(
            "SEPOLIA_DEPLOYER_PRIVATE_KEY không hợp lệ."
        ) from exc

    provider = w3 or Web3(HTTPProvider(rpc_url, request_kwargs={"timeout": 20}))
    try:
        if not provider.is_connected():
            raise DeploymentConfigurationError(
                f"Không kết nối được RPC Sepolia: {rpc_url}"
            )
        actual_chain_id = int(provider.eth.chain_id)
        if actual_chain_id != CHAIN_SEPOLIA:
            raise DeploymentConfigurationError(
                f"RPC sai mạng: yêu cầu Sepolia Chain ID {CHAIN_SEPOLIA}, nhận {actual_chain_id}."
            )
        balance = int(provider.eth.get_balance(account.address))
    except DeploymentConfigurationError:
        raise
    except Exception as exc:
        raise DeploymentConfigurationError(
            "Không kiểm tra được kết nối hoặc số dư deployer trên Sepolia."
        ) from exc
    if balance <= 0:
        raise DeploymentConfigurationError(
            f"Ví deployer {account.address} không có Sepolia ETH; cần số dư lớn hơn 0."
        )

    explorer_url = os.getenv("SEPOLIA_EXPLORER_URL", "https://sepolia.etherscan.io").strip()
    manifest, contracts = deploy_bundle(
        provider,
        account,
        network_name="sepolia",
        chain_id=CHAIN_SEPOLIA,
        explorer_url=explorer_url,
        abi_dir=abi_dir or project_root / "deployments" / "abi",
    )
    manifest["deployer"] = {
        "address": account.address,
        "balanceWeiBeforeDeploy": str(balance),
    }
    manifest["smokeTestTransactions"] = _smoke_test(
        provider, account, contracts, explorer_url=explorer_url
    )
    manifest["smokeTestPassedAt"] = datetime.now(timezone.utc).isoformat()

    sync_manifests(
        manifest,
        deployment_path=project_root / "deployments" / "sepolia.json",
        backend_config_path=project_root / "backend" / "config" / "contracts.json",
        frontend_config_path=project_root / "frontend" / "src" / "config" / "contracts.json",
        abi_dir=abi_dir or project_root / "deployments" / "abi",
    )
    return manifest


def main() -> int:
    try:
        load_dotenv(PROJECT_ROOT / ".env")
        rpc_url, private_key = validate_sepolia_environment()
        manifest = run_sepolia_deployment(
            rpc_url=rpc_url,
            private_key=private_key,
        )
    except (DeploymentError, OSError, ValueError) as exc:
        print(f"LỖI Q06 SEPOLIA: {exc}", file=sys.stderr)
        return 1
    print("Deploy, bind và smoke-test Sepolia hoàn tất.")
    for name in (
        "MyUSDT",
        "CollateralNFT",
        "CollateralReceiptNFT",
        "DebtToken",
        "LendingPositionNFT",
        "LendingPool",
        "PriceOracle",
    ):
        contract = manifest["contracts"][name]
        print(f"{name}: {contract['address']} ({contract['explorerUrl']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
