"""Q01 Environment & Web3.py Verification Script.

Usage:
  python scripts/verify_env.py              # Kiểm tra mạng local (mặc định)
  python scripts/verify_env.py --all        # Kiểm tra cả Local Hardhat và Sepolia Testnet
  python scripts/verify_env.py --sepolia    # Chỉ kiểm tra kết nối Sepolia Testnet
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from eth_account import Account  # noqa: E402
from web3 import Web3  # noqa: E402

from backend.config.blockchain import check_network_connection, get_web3  # noqa: E402
from backend.config.settings import settings  # noqa: E402

DEFAULT_MNEMONIC = "test test test test test test test test test test test junk"


def verify_required_packages() -> bool:
    """Ensure all required Q01 Python libraries import cleanly."""
    required_modules = [
        "web3",
        "fastapi",
        "uvicorn",
        "pydantic",
        "reportlab",
        "requests",
        "dotenv",
        "cryptography",
    ]
    missing = []
    for mod in required_modules:
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)

    if missing:
        print(f"[FAIL] Thiếu thư viện Python: {', '.join(missing)}")
        return False

    print("[PASS] Đã cài đặt đầy đủ các thư viện Python theo requirements.txt.")
    return True


def verify_local_network() -> bool:
    """Check Local Hardhat RPC (w3.is_connected() == True, Chain ID == 31337, 10 test wallets)."""
    status = check_network_connection("local")
    if not status.get("connected"):
        print(
            f"[FAIL] Local Blockchain chưa kết nối được tại {status.get('rpc_url')}: "
            f"{status.get('error')} (Hãy bật `npm run node` trước)."
        )
        return False

    if not status.get("chain_id_matches"):
        print(
            f"[FAIL] Sai Chain ID trên Local! Mong đợi {status.get('expected_chain_id')}, "
            f"nhận được {status.get('actual_chain_id')}."
        )
        return False

    w3 = get_web3("local")
    Account.enable_unaudited_hdwallet_features()
    zero_or_low = []
    for idx in range(10):
        acct = Account.from_mnemonic(
            DEFAULT_MNEMONIC, account_path=f"m/44'/60'/0'/0/{idx}"
        )
        bal_eth = Web3.from_wei(w3.eth.get_balance(acct.address), "ether")
        if bal_eth < 1000:
            zero_or_low.append((idx, acct.address, bal_eth))

    if zero_or_low:
        print(f"[FAIL] Một số ví test Local không đủ ETH: {zero_or_low}")
        return False

    acct0 = Account.from_mnemonic(DEFAULT_MNEMONIC, account_path="m/44'/60'/0'/0/0")
    balance_eth = Web3.from_wei(w3.eth.get_balance(acct0.address), "ether")

    print(
        f"[PASS] Local Hardhat Node kết nối thành công! "
        f"w3.is_connected()={w3.is_connected()} | Chain ID={status['actual_chain_id']} | "
        f"Block={status['latest_block']} | Đủ 10/10 ví test (Account #0 {acct0.address} = {balance_eth} ETH)"
    )
    return True


def verify_sepolia_network() -> bool:
    """Check Sepolia Testnet RPC connectivity (Chain ID == 11155111)."""
    status = check_network_connection("sepolia")
    if not status.get("connected"):
        print(
            f"[FAIL] Không kết nối được Sepolia RPC ({status.get('rpc_url')}): "
            f"{status.get('error')}"
        )
        return False

    if not status.get("chain_id_matches"):
        print(
            f"[FAIL] Sai Chain ID trên Sepolia! Mong đợi {status.get('expected_chain_id')}, "
            f"nhận được {status.get('actual_chain_id')}."
        )
        return False

    w3 = get_web3("sepolia")
    gas_gwei = Web3.from_wei(w3.eth.gas_price, "gwei")
    deployer_info = (
        "[WARN] Chưa điền SEPOLIA_DEPLOYER_PRIVATE_KEY trong .env "
        "(Cần tạo ví Testnet riêng & nhận SepoliaETH từ Faucet trước khi deploy)"
    )
    if settings.sepolia_deployer_private_key:
        deployer_acct = Account.from_key(settings.sepolia_deployer_private_key)
        bal = Web3.from_wei(w3.eth.get_balance(deployer_acct.address), "ether")
        level = "OK" if bal > 0 else "WARN - Số dư 0 SepoliaETH, cần lấy từ Faucet"
        deployer_info = f"[{level}] Deployer {deployer_acct.address} | Số dư: {bal} SepoliaETH"

    print(
        f"[PASS] Sepolia Testnet RPC kết nối thành công! "
        f"w3.is_connected()={w3.is_connected()} | Chain ID={status['actual_chain_id']} | "
        f"Latest Block={status['latest_block']} | Gas Price={gas_gwei:.4f} Gwei | {deployer_info}"
    )
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Kiểm tra môi trường Q01 (Web3.py + Hardhat + Sepolia)")
    parser.add_argument("--all", action="store_true", help="Kiểm tra cả mạng Local và Sepolia")
    parser.add_argument("--sepolia", action="store_true", help="Chỉ kiểm tra mạng Sepolia")
    args = parser.parse_args()

    ok = verify_required_packages()
    if args.sepolia:
        ok = verify_sepolia_network() and ok
    elif args.all:
        ok = verify_local_network() and ok
        ok = verify_sepolia_network() and ok
    else:
        ok = verify_local_network() and ok

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
