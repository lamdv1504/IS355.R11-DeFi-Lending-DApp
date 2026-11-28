"""Q06 tests for deployment ordering, local seed, config sync, and Sepolia guards."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from eth_account import Account
from web3 import Web3
from web3.exceptions import ContractCustomError

from scripts import deploy_and_seed, deploy_sepolia, deploy_utils

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ABI_DIR = PROJECT_ROOT / "deployments" / "abi"
WAD = 10**18


class _FakeEth:
    chain_id = 31337


class _FakeW3:
    def __init__(self) -> None:
        self.eth = _FakeEth()


class _FakeContract:
    def __init__(self, address: str) -> None:
        self.address = address
        self.functions = SimpleNamespace()
        self.events = SimpleNamespace()


def _receipt(index: int, address: str | None = None) -> dict[str, Any]:
    return {
        "status": 1,
        "transactionHash": bytes([index % 255 + 1]) * 32,
        "blockNumber": index,
        "contractAddress": address,
    }


def test_transaction_estimation_retries_rpc_lag_before_signing() -> None:
    attempts = 0

    def build(_transaction: dict[str, Any]) -> dict[str, Any]:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ContractCustomError("temporary stale RPC state")
        return {"gas": 120_000}

    with patch("scripts.deploy_utils.time.sleep") as sleep:
        transaction = deploy_utils._build_transaction_with_retry(
            build,
            {"from": "0x0000000000000000000000000000000000000001"},
            "Build depositLender",
        )

    assert transaction["gas"] == 120_000
    assert attempts == 2
    sleep.assert_called_once_with(1)


def test_deploy_bundle_uses_expected_order_and_binds_pool_and_oracle() -> None:
    w3 = _FakeW3()
    deployer = Account.create()
    deployed_names: list[str] = []
    sent_functions: list[tuple[str, str, tuple[Any, ...]]] = []
    contracts_by_name: dict[str, _FakeContract] = {}
    next_tx = [0]

    def fake_deploy(
        _w3: Any,
        _account: Any,
        artifact: dict[str, Any],
        _args: tuple[Any, ...],
    ) -> tuple[_FakeContract, dict[str, Any]]:
        next_tx[0] += 1
        name = artifact["contractName"]
        deployed_names.append(name)
        contract = _FakeContract(Web3.to_checksum_address(f"0x{next_tx[0]:040x}"))
        contracts_by_name[name] = contract
        return contract, _receipt(next_tx[0], contract.address)

    def fake_transact(
        _w3: Any, _account: Any, contract: _FakeContract, fn: str, *args: Any
    ) -> dict[str, Any]:
        contract_name = next(
            name for name, value in contracts_by_name.items() if value is contract
        )
        sent_functions.append((contract_name, fn, args))
        next_tx[0] += 1
        return _receipt(next_tx[0])

    def fake_call(contract: _FakeContract, fn: str, *_args: Any) -> Any:
        if fn == "lendingPool":
            return contracts_by_name["LendingPool"].address
        if fn == "priceOracle":
            return contracts_by_name["PriceOracle"].address
        if fn == "owner":
            return deployer.address
        if fn == "getCollateralTokenPrice":
            return WAD
        if fn == "priceMultiplierBps":
            return 10_000
        raise AssertionError(f"Unexpected getter {fn}")

    with (
        patch("scripts.deploy_utils.deploy_contract", side_effect=fake_deploy),
        patch("scripts.deploy_utils.transact", side_effect=fake_transact),
        patch("scripts.deploy_utils.call", side_effect=fake_call),
    ):
        manifest, contracts = deploy_utils.deploy_bundle(
            w3,
            deployer,
            network_name="local",
            chain_id=31337,
            explorer_url="http://127.0.0.1:8545",
            abi_dir=ABI_DIR,
        )

    assert deployed_names == [
        "MyUSDT",
        "CollateralNFT",
        "CollateralReceiptNFT",
        "DebtToken",
        "LendingPositionNFT",
        "LendingPool",
        "PriceOracle",
    ]
    assert sent_functions == [
        ("CollateralReceiptNFT", "setLendingPool", (contracts["LendingPool"].address,)),
        ("DebtToken", "setLendingPool", (contracts["LendingPool"].address,)),
        ("LendingPositionNFT", "setLendingPool", (contracts["LendingPool"].address,)),
        ("LendingPool", "setPriceOracle", (contracts["PriceOracle"].address,)),
    ]
    assert manifest["contracts"]["LendingPool"]["status"] == "DEPLOYED_AND_BOUND"
    assert manifest["contracts"]["PriceOracle"]["status"] == "DEPLOYED_AND_BOUND"
    assert manifest["contracts"]["MyUSDT"]["explorerUrl"].startswith(
        "http://127.0.0.1:8545/tx/"
    )


def test_local_seed_faucets_wallets_mints_nft_ids_and_deposits_1000() -> None:
    accounts = [
        {"index": i, "role": f"test-{i}", "account": Account.create()}
        for i in range(3)
    ]
    token = _FakeContract(Web3.to_checksum_address("0x" + "11" * 20))
    collateral = _FakeContract(Web3.to_checksum_address("0x" + "22" * 20))
    pool = _FakeContract(Web3.to_checksum_address("0x" + "33" * 20))
    contracts = {"MyUSDT": token, "CollateralNFT": collateral, "LendingPool": pool}
    calls: list[tuple[str, str, tuple[Any, ...]]] = []

    def fake_transact(
        _w3: Any, _account: Any, contract: _FakeContract, fn: str, *args: Any
    ) -> dict[str, Any]:
        name = next(key for key, value in contracts.items() if value is contract)
        calls.append((name, fn, args))
        return _receipt(len(calls))

    def fake_call(contract: _FakeContract, fn: str, *args: Any) -> Any:
        if contract is token and fn == "balanceOf":
            return 1_000 * WAD
        if contract is collateral and fn == "ownerOf":
            return accounts[int(args[0])]["account"].address
        if contract is pool and fn == "getPoolInfo":
            return (1_000 * WAD, 0, 0, WAD, WAD, 0, 0, 0, 0)
        raise AssertionError(f"Unexpected getter {fn} on {contract.address}")

    with (
        patch("scripts.deploy_and_seed.transact", side_effect=fake_transact),
        patch("scripts.deploy_and_seed.call", side_effect=fake_call),
        patch(
            "scripts.deploy_and_seed._minted_token_id",
            side_effect=[1, 2],
        ) as minted_id,
    ):
        result = deploy_and_seed.seed_local(_FakeW3(), contracts, accounts)

    faucet_calls = [call for call in calls if call[1] == "faucet"]
    assert len(faucet_calls) == 2
    assert all(call[2][1] == 1_000 * WAD for call in faucet_calls)
    assert [row["address"] for row in result["testAccounts"]][1:] == [
        accounts[1]["account"].address,
        accounts[2]["account"].address,
    ]
    assert result["collateralNFTSeeds"]["1"]["owner"] == accounts[1]["account"].address
    assert result["collateralNFTSeeds"]["2"]["owner"] == accounts[2]["account"].address
    assert result["initialLiquidityWad"] == str(1_000 * WAD)
    assert ("LendingPool", "depositLender", (1_000 * WAD,)) in calls
    minted_id.assert_has_calls([((collateral, _receipt(3)),), ((collateral, _receipt(4)),)])


def _manifest(network: str, *, start: int = 1) -> dict[str, Any]:
    is_local = network in {"local", "localhost"}
    return {
        "network": network,
        "chainId": 31337 if is_local else 11155111,
        "explorerUrl": "http://localhost:8545" if is_local else "https://sepolia.etherscan.io",
        "deployedAt": "2026-11-27T00:00:00Z",
        "contracts": {
            name: {
                "address": Web3.to_checksum_address(f"0x{start + index:040x}"),
                "txHash": "0x" + f"{start + index:064x}",
                "blockNumber": index + 1,
                "abiPath": f"deployments/abi/{name}.json",
                "explorerUrl": f"https://explorer.invalid/tx/{start + index}",
                "status": "DEPLOYED_AND_BOUND",
            }
            for index, name in enumerate(deploy_utils.CONTRACT_NAMES)
        },
    }


def test_local_deployment_syncs_three_configs_and_preserves_sepolia(tmp_path: Path) -> None:
    shutil.copytree(ABI_DIR, tmp_path / "deployments" / "abi")
    (tmp_path / "deployments").mkdir(exist_ok=True)
    backend_path = tmp_path / "backend" / "config" / "contracts.json"
    backend_path.parent.mkdir(parents=True)
    sepolia_before = {"chainId": 11155111, "contracts": {"Keep": {"address": "0xabc"}}}
    backend_path.write_text(
        json.dumps({"local": {"chainId": 31337, "contracts": {}}, "sepolia": sepolia_before}),
        encoding="utf-8",
    )

    manifest = _manifest("localhost")
    deployed_contracts = {
        name: _FakeContract(record["address"])
        for name, record in manifest["contracts"].items()
    }
    seed = {"testAccounts": [], "initialLiquidityWad": str(1_000 * WAD)}
    audit = {
        "json": {"cid": "bafy-json", "gateway_url": "http://localhost/ipfs/bafy-json"},
        "csv": {"cid": "bafy-csv", "gateway_url": "http://localhost/ipfs/bafy-csv"},
        "simulatedPeriods": ["2026-10"],
        "containsPii": False,
    }
    with (
        patch(
            "scripts.deploy_and_seed.deploy_bundle",
            return_value=(manifest, deployed_contracts),
        ),
        patch("scripts.deploy_and_seed.call", side_effect=[1_000_000 * WAD, 1_000 * WAD]),
        patch("scripts.deploy_and_seed.seed_local", return_value=seed),
    ):
        result = deploy_and_seed.run_local_deployment(
            _FakeW3(),
            accounts=[{"index": 0, "role": "seed", "account": Account.create()}] * 3,
            project_root=tmp_path,
            audit_service=lambda *_args, **_kwargs: audit,
        )

    deployment = json.loads((tmp_path / "deployments" / "localhost.json").read_text())
    backend = json.loads(backend_path.read_text())
    frontend = json.loads(
        (tmp_path / "frontend" / "src" / "config" / "contracts.json").read_text()
    )
    assert deployment["auditLogs"]["simulatedPeriods"] == ["2026-10"]
    assert deployment["network"] == "localhost"
    assert backend["sepolia"] == sepolia_before
    assert backend["local"]["contracts"]["LendingPool"]["address"] == result["contracts"]["LendingPool"]["address"]
    assert frontend["network"] == "local"
    for name in deploy_utils.CONTRACT_NAMES:
        expected_abi = json.loads((tmp_path / "deployments" / "abi" / f"{name}.json").read_text())["abi"]
        assert frontend["contracts"][name]["address"] == result["contracts"][name]["address"]
        assert frontend["contracts"][name]["txHash"] == result["contracts"][name]["txHash"]
        assert frontend["contracts"][name]["abi"] == expected_abi


def test_sync_manifests_updates_sepolia_backend_and_frontend_abis(tmp_path: Path) -> None:
    shutil.copytree(ABI_DIR, tmp_path / "abi")
    backend_path = tmp_path / "contracts.json"
    backend_path.write_text(
        json.dumps({"local": {"chainId": 31337, "contracts": {"Keep": {"address": "local"}}}, "sepolia": {}}),
        encoding="utf-8",
    )
    manifest = _manifest("sepolia", start=20)
    deploy_utils.sync_manifests(
        manifest,
        deployment_path=tmp_path / "sepolia.json",
        backend_config_path=backend_path,
        frontend_config_path=tmp_path / "frontend" / "src" / "config" / "contracts.json",
        abi_dir=tmp_path / "abi",
    )
    backend = json.loads(backend_path.read_text())
    frontend = json.loads(
        (tmp_path / "frontend" / "src" / "config" / "contracts.json").read_text()
    )
    assert backend["local"]["contracts"]["Keep"]["address"] == "local"
    assert backend["sepolia"]["chainId"] == 11155111
    assert backend["sepolia"]["contracts"]["PriceOracle"]["address"] == manifest["contracts"]["PriceOracle"]["address"]
    assert frontend["network"] == "sepolia"
    assert len(frontend["contracts"]["PriceOracle"]["abi"]) > 0


@pytest.mark.parametrize(
    ("environ", "expected"),
    [
        ({}, "SEPOLIA_RPC_URL"),
        ({"SEPOLIA_RPC_URL": "https://example.invalid"}, "SEPOLIA_DEPLOYER_PRIVATE_KEY"),
        (
            {
                "SEPOLIA_RPC_URL": "https://example.invalid",
                "SEPOLIA_DEPLOYER_PRIVATE_KEY": next(iter(deploy_utils.HARDHAT_DEFAULT_PRIVATE_KEYS)),
            },
            "Hardhat",
        ),
    ],
)
def test_sepolia_environment_guard_rejects_missing_or_hardhat_keys(
    environ: dict[str, str], expected: str
) -> None:
    with pytest.raises(deploy_utils.DeploymentConfigurationError, match=expected):
        deploy_sepolia.validate_sepolia_environment(environ)


def test_sepolia_deployment_requires_positive_deployer_balance() -> None:
    account = Account.create()

    class _SepoliaEth:
        chain_id = 11155111

        @staticmethod
        def get_balance(_address: str) -> int:
            return 0

    provider = SimpleNamespace(is_connected=lambda: True, eth=_SepoliaEth())
    with pytest.raises(deploy_utils.DeploymentConfigurationError, match="số dư"):
        deploy_sepolia.run_sepolia_deployment(
            rpc_url="https://sepolia.example",
            private_key=account.key.hex(),
            w3=provider,
        )
