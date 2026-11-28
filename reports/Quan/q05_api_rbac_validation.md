# Q05 — Báo cáo kiểm chứng FastAPI REST API, Auth EIP-191, RBAC & Tương thích L01/L04

- **Thời điểm thực thi (UTC):** `2026-11-28T07:23:29Z`
- **Module kiểm tra:** `backend/api/pool.py`, `backend/api/transactions.py`, `backend/api/dependencies.py`, `backend/schemas/pool.py`, `backend/schemas/transactions.py`, `tests/test_q05_api_auth_rbac.py`

## 1. Các lỗi kỹ thuật Q05 (so với L01/Excel) đã xử lý triệt để

1. **Bổ sung action `TRANSFER_LENDING_POSITION_NFT`:** Xây dựng unsigned tx `LendingPositionNFT.safeTransferFrom(sender, recipient, position_id)`, chặn địa chỉ đích `0x000...000` (`422`), kèm ước lượng gas và preview. Đã kiểm chứng ký & gửi giao dịch thật trên Hardhat 31337 (`txHash = 0x778b00d535dca63b911bbf7937693ed072342314ff9efe151fc4e8a04b272ff9`, Block `29`, gas `57,902`), xác nhận `ownerOf(1)` chuyển thành công sang Lender B (`0x90F79bf6EB2c4f870365E785982E1f101E93b906`).
2. **Sửa lỗi `tokenId = 0` ở `DEPOSIT_COLLATERAL`:** Cho phép số nguyên không âm (`>= 0`) khi `is_nft = true` (vẫn chặn `<= 0` với `is_nft = false`), khớp quy tắc `LendingPool.depositCollateral()`.
3. **Bổ sung `?network=local|sepolia` & `block_number` / `as_of_timestamp` cho `GET /api/pool` (và các route đọc công khai):** Đã kiểm chứng đồng thời `GET /api/pool?network=local` (Block `24`) và `GET /api/pool?network=sepolia` (Block `12228616` từ RPC Sepolia thật), trả `422` khi tên mạng không hợp lệ.
4. **Bổ sung chuỗi lịch sử theo tháng ở `GET /api/analytics/rates`:** Trả mảng `series` (6+ kỳ theo tháng, tách rõ `SIMULATED` và `ON_CHAIN`, có `borrow_apy_percent`, `supply_apy_percent`, `borrow_apr_percent`, `supply_apr_percent`, `utilization_percent`, cùng `rate_model`, `block_number`, `as_of_timestamp`) mà không gây side-effect upload IPFS.
5. **Bổ sung `context`, `availability`, `allowance` và `preview` (`resulting_ltv`, `resulting_hf`) trong `POST /api/transactions/prepare`:** Kiểm chứng thực tế `DEPOSIT_LENDER` báo `approval_required = true/false` theo allowance, `BORROW` `500 MyUSDT` trên thế chấp `1,000 MyUSDT` tính chính xác `resulting_ltv_bps = 5000` (50%) và `resulting_hf.health_factor = 1.6` (`SAFE`).
6. **Vá 2 lỗi thực tế khi chạy `POST /api/transactions/confirm` trên node Hardhat thật:**
   - Chuẩn hóa `transaction["input"]` kiểu `HexBytes` của Web3.py sang hex string `0x...` trước khi đối chiếu với `unsignedTransaction.data`.
   - Giải mã `chainId` từ trường `v` theo chuẩn EIP-155 (`(v - 35) // 2` khi `v >= 35`) cho các giao dịch legacy type-0 mà `eth_getTransactionByHash` không trả trường `chainId` tường minh.
7. **Đồng bộ mapping đường dẫn L01 vs Excel Q05:** Đã ghi rõ bảng quy đổi (`/api/pool-overview` → `GET /api/pool`, `/api/tx/prepare-*` → `POST /api/transactions/prepare`, `/api/demo/fast-forward-time` → `POST /api/demo/time`) trong `docs/Quan/q05_fastapi_rbac_handoff.md`.

## 2. Kiểm chứng tương thích ngược với Frontend L04

- Đã chạy trực tiếp bộ test tích hợp TypeScript thật của Lâm (`frontend/tests/ipfs-api.integration.ts`) trỏ vào FastAPI Q05 live (kết nối Hardhat 31337 thật): **PASS `20/20` kịch bản HTTP thực** (PDF/JSON/CSV, Guest/Lender/Other/Owner/Admin, kiểm tra SHA-256 và 401/403).
