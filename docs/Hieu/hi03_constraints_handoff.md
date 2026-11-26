# HI03 – Bàn giao 2 Ràng buộc Logic: Tỷ lệ LTV ≤ 70% & Điều kiện Rút tiền Pool (Hiếu, Giai đoạn 2)

## 1. Phạm vi & Liên kết Rubric (Tiêu chí 1 & Tiêu chí 4)

`HI03` hoàn thiện toàn bộ 2 ràng buộc an toàn vốn bắt buộc trên `contracts/LendingPool.sol` cùng bộ hàm view kiểm tra hạn mức và bộ giải mã custom error tiếng Việt (`backend/config/errors.py`) bàn giao cho **Quân (`Q02`/`Q05`)** và **Lâm (`L02`/`L03`)**:

1. **Ràng buộc 1 — Tỷ lệ thế chấp tối đa (`LTV ≤ 70%`)**:
   - `borrow(amount, agreementCid)` chốt lãi tích lũy tới `block.timestamp`, đọc định giá trực tiếp từ `PriceOracle` (hoặc fallback `CollateralNFT.valuation` / `1:1` token price), tính `maxBorrowable = floor(collateralValue * 7000 / 10000)` và chặn ngay lập tức bằng `ExceedsMaxLTV(requestedTotalDebt, maxBorrowable)` nếu `principal + accruedInterest + amount > maxBorrowable`.
   - `withdrawCollateral()` chặn mọi giao dịch rút tài sản thế chấp khi còn bất kỳ dư nợ gốc hoặc lãi nào bằng `OutstandingDebtExists(remainingDebtWad)`.
2. **Ràng buộc 2 — Điều kiện rút tiền Pool theo số dư thực (`MyUSDT.balanceOf`)**:
   - `getAvailableLiquidity()` tính trực tiếp từ số dư on-chain thực tế:
     $$\text{availableLiquidity} = \max\!\big(0,\ \text{MyUSDT.balanceOf}(\text{address(LendingPool)}) - \text{reservedLiquidity} - \text{totalTokenCollateralLocked}\big)$$
     *(khi `collateralToken == myUSDT`, tài sản thế chấp ERC-20 được tách bạch hoàn toàn khỏi thanh khoản cho vay để Lender không bao giờ rút lẹm vào tiền thế chấp của Borrower)*.
   - `withdrawLender(positionId, amount)` kiểm tra đồng thời `ownerOf(positionId) == msg.sender` (hỗ trợ chuyển nhượng `LendingPositionNFT` `A → B → C`), `amount <= claimableForPosition` (`InsufficientClaimableBalance`) và `amount <= availableLiquidity` (`InsufficientPoolLiquidity`).

---

## 2. Bộ hàm View kiểm tra Hạn mức (Bàn giao cho Quân `Q02` & Lâm `L02`/`L03`)

Toàn bộ ABI mới đã được xuất vào `deployments/abi/LendingPool.json` và `deployments/abi/interfaces/ILendingPool.json` (tương thích ngược 100% với `HI02`).

| Hàm View (`ILendingPool` / `LendingPool`) | Hàm đối xứng Python (`backend/config/constants.py`) | Đơn vị | Công thức & Mục đích sử dụng |
|---|---|---|---|
| `getMaxBorrowable(address borrower)` | `calculate_max_borrow(collateral_value_wad)` | `WAD (1e18)` | Trần tổng nợ tối đa theo 70% LTV (`floor(collateralValue * 7000 / 10000)`). |
| `getRemainingBorrowCapacity(address borrower)` | `calculate_remaining_borrow_capacity(collateral, debt)` | `WAD (1e18)` | Hạn mức LTV còn lại có thể vay thêm: `max(0, maxBorrowable - totalDebt)`. Khớp `remaining_ltv_capacity` trong `docs/Lam/l01_api_contract.md`. |
| `getAvailableToBorrow(address borrower)` | `calculate_available_to_borrow(collateral, debt, avail)` | `WAD (1e18)` | Số `MyUSDT` tối đa thực tế vay thêm được ngay lúc này: `min(remainingBorrowCapacity, availableLiquidity)`. |
| `getCurrentLtvBps(address borrower)` | `calculate_ltv_bps(debt, collateral)` | `BPS (10_000)` | Tỷ lệ LTV hiện tại (`0` khi nợ = 0; `type(uint256).max` nếu nợ > 0 & tài sản = 0). Phục vụ thanh trượt LTV của `L03`. |
| `getAvailableLiquidity()` | `calculate_available_liquidity(bal, reserved, locked)` | `WAD (1e18)` | Thanh khoản rỗi thực tế trên `MyUSDT.balanceOf(pool)` sau khi trừ `reservedLiquidity` và `totalTokenCollateralLocked`. |
| `getMaxWithdrawable(uint256 positionId)` | `calculate_max_withdrawable(claimable, avail)` | `WAD (1e18)` | Số `MyUSDT` tối đa rút được ngay lúc này cho `positionId`: `min(claimable, availableLiquidity)`. Khớp `withdrawLimit()` của `L02`. |

---

## 3. Bảng Custom Error & Bộ giải mã tiếng Việt (`backend/config/errors.py`)

Mọi revert từ `LendingPool` và token/NFT H01–H02 đều có mã selector 4-byte chuẩn và được `backend/config/errors.py` tự động giải mã thành thông báo tiếng Việt có số liệu tường minh cho Web3.py (`Q02`/`Q05`) và Frontend (`L02`/`L03`/`L05`):

| Mã lỗi (`code`) | Selector 4-byte | Chữ ký ABI | HTTP Status | Ngữ cảnh kích hoạt |
|---|---|---|---|---|
| `ExceedsMaxLTV` | `0xd83e978f` | `ExceedsMaxLTV(uint256,uint256)` | `400` | Vay vượt trần 70% LTV (kể cả sau khi cộng lãi tích lũy hoặc giá Oracle giảm) |
| `InsufficientPoolLiquidity` | `0x7d61b360` | `InsufficientPoolLiquidity(uint256,uint256)` | `409` | Lender rút hoặc Borrower vay vượt `getAvailableLiquidity()` thực tế |
| `InsufficientClaimableBalance` | `0x297f860e` | `InsufficientClaimableBalance(uint256,uint256)` | `400` | Lender rút vượt quyền lợi `principal + accruedInterest` của `positionId` |
| `NotPositionOwner` | `0x606840e0` | `NotPositionOwner(uint256,address)` | `403` | Ví gọi `withdrawLender` không phải `ownerOf(positionId)` hiện tại |
| `PositionNotFound` | `0xf7154807` | `PositionNotFound(uint256)` | `404` | `positionId` không tồn tại hoặc đã rút hết và burn |
| `OutstandingDebtExists` | `0x467548a3` | `OutstandingDebtExists(uint256)` | `409` | Gọi `withdrawCollateral()` khi vẫn còn dư nợ gốc hoặc lãi |
| `NoActiveCollateral` | `0xece89986` | `NoActiveCollateral(address)` | `400` | Gọi `borrow`/`repay`/`withdrawCollateral` khi chưa khóa tài sản thế chấp |
| `CollateralAlreadyLocked` | `0x6c690e53` | `CollateralAlreadyLocked(address)` | `409` | Ví đã có vị thế thế chấp đang hoạt động |
| `HealthFactorSafe` | `0x053bbeed` | `HealthFactorSafe(uint256)` | `400` | Gọi `liquidate()` khi `HF_WAD >= 1e18` |
| `EmptyAgreementCid` | `0xa2ef4a9a` | `EmptyAgreementCid()` | `400` | Gọi `borrow()` với `agreementCid` rỗng |
| `ZeroAmount` | `0x1f2a2005` | `ZeroAmount()` | `400` | Tham số số lượng bằng `0` |
| `InvalidAddress` | `0xe6c4247b` | `InvalidAddress()` | `400` | Địa chỉ zero khi cấu hình hợp đồng / Oracle |
| `UnauthorizedNFTTransfer` | `0x47207f9d` | `UnauthorizedNFTTransfer(address,address)` | `403` | Chuyển trực tiếp NFT vào Pool không qua `depositCollateral()` |
| `ERC20InsufficientBalance` | `0xe450d38c` | `ERC20InsufficientBalance(address,uint256,uint256)` | `400` | Số dư `MyUSDT` trong ví không đủ |
| `ERC20InsufficientAllowance` | `0xfb8f41b2` | `ERC20InsufficientAllowance(address,uint256,uint256)` | `400` | Chưa `approve()` đủ hạn mức cho `LendingPool` |
| `OnlyLendingPool` | `0xf59de49d` | `OnlyLendingPool(address,address)` | `403` | Gọi trực tiếp hàm `onlyPool` trên `DebtToken`/`ReceiptNFT`/`PositionNFT` |
| `ReceiptNonTransferable` | `0xe7a41791` | `ReceiptNonTransferable()` | `403` | Cố chuyển nhượng `CollateralReceiptNFT` (soulbound) |
| `DebtTokenNonTransferable` | `0x59f39a79` | `DebtTokenNonTransferable()` | `403` | Cố chuyển nhượng `DebtToken` |

### Ví dụ tích hợp cho Quân (`Q02` / `Q05`)

```python
from web3.exceptions import ContractCustomError, ContractLogicError
from backend.config.errors import format_error_for_api

try:
    pool_contract.functions.withdrawLender(position_id, amount_wad).call({"from": wallet})
except (ContractCustomError, ContractLogicError) as exc:
    err = format_error_for_api(exc)
    # err = {
    #   "code": "InsufficientPoolLiquidity",
    #   "selector": "0x7d61b360",
    #   "http_status": 409,
    #   "message_vi": "Pool không đủ thanh khoản rỗi: yêu cầu 600.0000 MyUSDT nhưng số dư khả dụng thực tế hiện chỉ còn 400.0000 MyUSDT.",
    #   "details": {"requestedWad": "...", "availableLiquidityWad": "...", ...}
    # }
```

---

## 4. Lệnh Kiểm thử nhanh HI03

```powershell
npm run compile
npm run export:hi02
npm run test:hi03
npm test
.\.venv\Scripts\pytest.exe -v
```
