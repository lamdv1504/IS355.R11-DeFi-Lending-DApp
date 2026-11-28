# Q01 — Báo cáo kiểm chứng môi trường Blockchain & Bảo mật cấu hình

- **Thời điểm thực thi (UTC):** `2026-11-28T07:23:29Z`
- **Nhánh:** `fix/quan-q01-q06-audit-gaps`

## 1. Kiểm thử tự động (`pytest tests/test_q01_environment.py`)

- Kiểm tra 10/10 ví Hardhat deterministic khớp mnemonic chuẩn và nằm trong tập chặn `HARDHAT_DEFAULT_PRIVATE_KEYS`.
- Xác nhận cố định Chain ID `31337` (Local) và `11155111` (Sepolia).
- Xác nhận cả Python `load_settings()` lẫn `hardhat.config.js` đều từ chối dùng private key Hardhat cho `SEPOLIA_DEPLOYER_PRIVATE_KEY`.
- Xác nhận `backend/config/contracts.json` có đủ 7/7 hợp đồng MVP trên cả `local` và `sepolia`.
- Xác nhận `GET /health` trả `custodial_wallet_keys_stored: false`.

## 2. Kết quả chạy thực tế `python scripts/verify_env.py --all`

Chạy với Hardhat Local node (`127.0.0.1:8545`) và Ethereum Sepolia RPC thực tế (`11155111`), mã thoát `0`:

```text
[PASS] Đã cài đặt đầy đủ các thư viện Python theo requirements.txt.
[PASS] Local Hardhat Node kết nối thành công! w3.is_connected()=True | Chain ID=31337 | Block=0 | Đủ 10/10 ví test (Account #0 0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266 = 10000 ETH)
[PASS] Sepolia Testnet RPC kết nối thành công! w3.is_connected()=True | Chain ID=11155111 | Latest Block=12228615 | Gas Price=0.0000 Gwei | [OK] Deployer 0x3bEda0f07bf14749B907707b6D48135f2B1a73E7 | Số dư: 0.049999998880395587 SepoliaETH
```

## 3. Vệ sinh bảo mật `.env.example`

- Đã xóa chuỗi khóa mẫu cố định `0123456789abcdef...` khỏi `DOCUMENT_AES_KEY_HEX` trong `.env.example`, thay bằng giá trị rỗng kèm hướng dẫn sinh khóa ngẫu nhiên 32-byte (`python -c "import secrets; print(secrets.token_hex(32))"`).
- Quá trình chạy kiểm thử live E2E Q03–Q06 sử dụng khóa AES-256-GCM và `AUTH_TOKEN_SECRET` sinh ngẫu nhiên trong phiên (không dùng chuỗi mẫu, không ghi khóa ra log hay file báo cáo).
