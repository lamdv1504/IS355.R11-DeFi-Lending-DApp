"""HI05 PriceOracle ABI, Error Selector, Manifest & Liquidation Math Verification Tests."""

from __future__ import annotations

import json
from pathlib import Path

from eth_abi import encode as abi_encode
from web3 import Web3

from backend.config import constants as c
from backend.config.errors import ERRORS_BY_CODE, decode_contract_error

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ORACLE_ABI_PATH = PROJECT_ROOT / "deployments" / "abi" / "PriceOracle.json"
ORACLE_IFACE_ABI_PATH = PROJECT_ROOT / "deployments" / "abi" / "interfaces" / "IPriceOracle.json"
POOL_ABI_PATH = PROJECT_ROOT / "deployments" / "abi" / "LendingPool.json"
CONTRACTS_JSON_PATH = PROJECT_ROOT / "backend" / "config" / "contracts.json"
LOCALHOST_MANIFEST_PATH = PROJECT_ROOT / "deployments" / "localhost.json"


def _encode_error(signature: str, arg_types: list[str], args: list[object]) -> str:
    selector = Web3.keccak(text=signature)[:4]
    encoded_args = abi_encode(arg_types, args) if arg_types else b""
    return "0x" + (selector + encoded_args).hex()


def test_exported_price_oracle_and_pool_abis_expose_hi05_surface() -> None:
    """Verify PriceOracle, IPriceOracle, and LendingPool ABIs expose all HI05 functions & events."""
    for path in (ORACLE_ABI_PATH, ORACLE_IFACE_ABI_PATH, POOL_ABI_PATH):
        assert path.exists(), f"Missing exported ABI: {path}. Run `npm run export:hi05`."

    oracle_artifact = json.loads(ORACLE_ABI_PATH.read_text(encoding="utf-8"))
    assert oracle_artifact.get("bytecode", "").startswith("0x") and len(oracle_artifact["bytecode"]) > 10
    oracle_abi = oracle_artifact["abi"]
    oracle_fns = {x["name"] for x in oracle_abi if x.get("type") == "function"}
    oracle_evts = {x["name"] for x in oracle_abi if x.get("type") == "event"}

    for fn in (
        "getCollateralTokenPrice",
        "getCollateralNFTValuation",
        "priceMultiplierBps",
        "setCollateralTokenPrice",
        "setCollateralNFTValuation",
        "clearCollateralNFTValuationOverride",
        "setPriceMultiplierBps",
        "resetDemoPrices",
        "owner",
    ):
        assert fn in oracle_fns, f"Missing PriceOracle function: {fn}"

    for evt in ("PriceUpdated", "PriceMultiplierUpdated"):
        assert evt in oracle_evts, f"Missing PriceOracle event: {evt}"

    pool_abi = json.loads(POOL_ABI_PATH.read_text(encoding="utf-8"))["abi"]
    pool_fns = {x["name"] for x in pool_abi if x.get("type") == "function"}
    pool_evts = {x["name"] for x in pool_abi if x.get("type") == "event"}
    for fn in ("getHealthFactor", "liquidate", "getLiquidationPreview", "setPriceOracle", "priceOracle"):
        assert fn in pool_fns, f"Missing HI05 LendingPool function: {fn}"
    assert "LoanLiquidated" in pool_evts


def test_hi05_oracle_and_liquidation_error_decoding_matches_abi_selectors() -> None:
    """Verify OwnableUnauthorizedAccount, InvalidMultiplierBps & HealthFactorSafe decode to Vietnamese."""
    oracle_abi = json.loads(ORACLE_ABI_PATH.read_text(encoding="utf-8"))["abi"]
    for err in oracle_abi:
        if err.get("type") != "error":
            continue
        name = err["name"]
        if name in ERRORS_BY_CODE:
            sig = f"{name}({','.join(inp['type'] for inp in err['inputs'])})"
            expected_sel = "0x" + Web3.keccak(text=sig)[:4].hex()
            assert ERRORS_BY_CODE[name].selector == expected_sel

    attacker = "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC"
    payload_unauth = _encode_error("OwnableUnauthorizedAccount(address)", ["address"], [attacker])
    dec_unauth = decode_contract_error(payload_unauth)
    assert dec_unauth.code == "OwnableUnauthorizedAccount"
    assert dec_unauth.http_status == 403
    assert attacker in dec_unauth.message_vi
    assert "PriceOracle" in dec_unauth.message_vi

    payload_mult = _encode_error("InvalidMultiplierBps(uint256,uint256)", ["uint256", "uint256"], [60_000, 50_000])
    dec_mult = decode_contract_error(payload_mult)
    assert dec_mult.code == "InvalidMultiplierBps"
    assert dec_mult.http_status == 400
    assert "60000" in dec_mult.message_vi
    assert "50000" in dec_mult.message_vi

    payload_safe = _encode_error("HealthFactorSafe(uint256)", ["uint256"], [c.WAD])
    dec_safe = decode_contract_error(payload_safe)
    assert dec_safe.code == "HealthFactorSafe"
    assert dec_safe.http_status == 400
    assert "1.0000" in dec_safe.message_vi


def test_localhost_manifests_register_all_7_mvp_contracts_including_price_oracle() -> None:
    """Verify HI05 handoff manifests contain deployed localhost addresses & ABI paths for all 7 contracts."""
    registry = json.loads(CONTRACTS_JSON_PATH.read_text(encoding="utf-8"))
    manifest = json.loads(LOCALHOST_MANIFEST_PATH.read_text(encoding="utf-8"))

    local_contracts = registry["local"]["contracts"]
    for name in c.MVP_CONTRACT_NAMES:
        entry = local_contracts[name]
        assert Web3.is_address(entry["address"]), f"{name} missing valid localhost address in contracts.json"
        assert (PROJECT_ROOT / entry["abiPath"]).exists(), f"{name} ABI missing at {entry['abiPath']}"

    oracle_manifest = manifest["contracts"]["PriceOracle"]
    assert oracle_manifest["status"] == "DEPLOYED_AND_BOUND"
    assert Web3.is_address(oracle_manifest["address"])
    assert manifest["contracts"]["LendingPool"]["priceOracle"] == oracle_manifest["address"]
