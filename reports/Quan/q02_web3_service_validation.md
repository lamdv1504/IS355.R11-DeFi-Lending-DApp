# Q02 — Báo cáo kiểm chứng Web3Service, PriceOracle & Liquidation Preview

- **Thời điểm thực thi (UTC):** `2026-11-28T07:23:29Z`
- **Module kiểm tra:** `backend/services/web3_service.py`, `tests/test_q02_web3_service.py`, `docs/Quan/q02_web3_service_handoff.md`

## 1. Các hạng mục bổ sung & lỗi đã vá

1. **Bổ sung `get_liquidation_preview(borrower_address)`:** Bọc đầy đủ hàm `LendingPool.getLiquidationPreview(address)` của HI05, trả chuẩn WAD/display (`collateral_value`, `total_debt`, `seize_value`), `is_nft_collateral`, Health Factor an toàn cho JSON (`health_factor_wad`, `health_factor`, `is_infinite`, `status`) và cờ `liquidatable`.
2. **Bổ sung `get_latest_block_context()` & `get_collateral_nft_approval_status(owner, spender, token_id)`:** Cung cấp `block_number` / `as_of_timestamp` cho snapshot đọc và trạng thái duyệt NFT cho `POST /api/transactions/prepare`.
3. **Vá lỗi khởi tạo `Web3Service(network_name="sepolia")`:** Di chuyển `self.chain_id = int(self.network.chain_id)` lên trước `self._load_registry()` trong `Web3Service.__init__` (trước đó gây `AttributeError` khi nạp `deployments/sepolia.json` thật).
4. **Kiểm chứng ABI `LendingPositionNFT.safeTransferFrom`:** Xác nhận bằng ABI thật `deployments/abi/LendingPositionNFT.json` rằng lời gọi 3 tham số `(from, to, positionId)` tạo đúng selector `0x42842e0e` (không xung đột overload 4 tham số).
5. **Cập nhật tài liệu handoff:** Đã bỏ ghi chú lỗi thời về việc `PriceOracle` chưa deploy trong `docs/Quan/q02_web3_service_handoff.md`.

## 2. Kiểm chứng Live trên Hardhat (31337) & Sepolia (11155111)

| Mạng | Kiểm tra | Kết quả thực tế |
|---|---|---|
| **Sepolia (`11155111`)** | `get_pool_info()` | `total_supplied = 500.000000 MyUSDT` |
| **Sepolia (`11155111`)** | `get_oracle_price()` | `price_multiplier_bps = 10000` (100%) |
| **Sepolia (`11155111`)** | `get_liquidation_preview(deployer)` | `liquidatable = false` |
| **Local (`31337`)** | `get_liquidation_preview(Borrower A)` sau vay `500 MyUSDT` + tua `30 ngày` | `collateral_value = 1000.000000`, `total_debt = 504.109589`, `health_factor = 1.586957`, `status = SAFE`, `liquidatable = false`, `is_nft_collateral = true` |
