# Báo cáo Kiểm thử & Nghiệm thu Ràng buộc Logic – HI03 (Hiếu, Giai đoạn 2)

- **Nhánh thực hiện**: `feature/hieu-gd2-hi03-ltv-liquidity-guards`
- **Môi trường kiểm chứng**: Hardhat `2.22.18`, Solidity `0.8.24` (EVM target `paris`), OpenZeppelin `5.0.2`, Python `3.11.9` (`pytest 9.2.0`, `web3`, `eth_abi`).
- **Kết quả tổng hợp**:
  - `npm run compile`: **Compiled 6 Solidity files successfully (`0 warnings`, `0 errors`)**
  - `npm run export:hi02`: Xuất mới `deployments/abi/LendingPool.json` và `deployments/abi/interfaces/ILendingPool.json` kèm 4 hàm view HI03
  - `npm test` (toàn repo gồm `H01`, `H02`, `HI01`, `HI02`, `HI03`): **`105 passing` (2s)** — trong đó `tests/HI03_Constraints.test.js` đạt **10/10 passing**
  - `pytest -v` (toàn repo gồm `HI01`, `HI03`, `Q01`): **`14 passed` (2.66s)** — trong đó `tests/test_hi03_errors_and_constraints.py` đạt **3/3 passing**

---

## 1. Bảng Đối chiếu Nghiệm thu HI03 (Theo kế hoạch & Rubric Tiêu chí 1, 4)

| Hạng mục kiểm thử HI03 | Kịch bản kiểm chứng cụ thể | File kiểm thử | Kết quả |
|---|---|---|---|
| **Ràng buộc 1 — Biên chính xác LTV ≤ 70%** | Thế chấp NFT `1,000 MyUSDT` → `getMaxBorrowable = 700`; vay `700 + 1 wei` bị revert ngay lập tức `ExceedsMaxLTV(700e18 + 1, 700e18)`; vay đúng `700` thành công (`getCurrentLtvBps == 7000`, `getRemainingBorrowCapacity == 0`). | `tests/HI03_Constraints.test.js` | **PASS** |
| **Ràng buộc 1 — LTV tính cả lãi tích lũy đa đợt** | Vay đợt 1 `500 MyUSDT`, tua `90 ngày` (lãi ~`12.33 MyUSDT`) → `getRemainingBorrowCapacity` giảm chính xác theo lãi tích lũy; vay thêm `200` bị chặn `ExceedsMaxLTV`; vay trong hạn mức `180` thành công. | `tests/HI03_Constraints.test.js` | **PASS** |
| **Ràng buộc 1 — Biến động giá qua `PriceOracle` (NFT & ERC-20)** | `MockPriceOracle` giảm hệ số xuống `50%` (NFT `1,000 → 500`, `maxBorrow = 350 < debt 400`) → `getRemainingBorrowCapacity == 0`, vay thêm `1 wei` revert `ExceedsMaxLTV`; định giá ERC-20 `0.80 MyUSDT/token` (`1,000` token = `800`, `maxBorrow = 560`) chặn đúng tại `560 + 1 wei`. | `tests/HI03_Constraints.test.js` | **PASS** |
| **Ràng buộc 1 — Chặn `withdrawCollateral()` khi còn nợ** | Bị revert `OutstandingDebtExists(remainingDebtWad)` cả khi còn toàn bộ gốc lẫn sau trả một phần (`299/300`), chỉ mở khóa khi nợ = `0`. | `tests/HI03_Constraints.test.js` | **PASS** |
| **Ràng buộc 2 — Rút theo `MyUSDT.balanceOf(pool)` thực tế & chống thanh khoản giả** | Lender gửi `1,000`, Borrower vay `600` → `availableLiquidity == 400`; rút `400 + 1 wei` revert `InsufficientPoolLiquidity(400e18 + 1, 400e18)`; sau rút `400`, cả `balanceOf(pool)` và `availableLiquidity` về `0`, rút `1 wei` bị chặn ngay `InsufficientPoolLiquidity(1, 0)`. | `tests/HI03_Constraints.test.js` | **PASS** |
| **Ràng buộc 2 — `reservedLiquidity` & phân quyền `onlyOwner`** | Chặn ví ngoài gọi `setReservedLiquidity` (`OwnableUnauthorizedAccount`); trừ đúng khoản dự phòng khỏi `getAvailableLiquidity()` và `getMaxWithdrawable()`; không tràn ngược khi `reservedLiquidity > balanceOf(pool)`. | `tests/HI03_Constraints.test.js` | **PASS** |
| **Ràng buộc 2 — Giới hạn quyền lợi theo từng `positionId`** | Lender A gửi `300`, Lender B gửi `700` (`available = 1,000`); Lender A rút `300 + 1 wei` bị chặn `InsufficientClaimableBalance(300e18 + 1, 300e18)`, không chạm được vốn của Lender B. | `tests/HI03_Constraints.test.js` | **PASS** |
| **Bổ sung Rubric — Số dư Pool thực tế qua 4 lượt đa người dùng** | 2 Lender (`lenderA`, `lenderB`) + 2 Borrower (`NFT` & `ERC-20`) xen kẽ gửi → vay → tua `30d/45d/60d` → trả một phần → rút một phần → tất toán toàn bộ. Sau mọi giao dịch: `getAvailableLiquidity() == balanceOf(pool) - totalTokenCollateralLocked - reservedLiquidity`, `getMaxWithdrawable == min(claimable, available)`, `getAvailableToBorrow == min(remainingCapacity, available)`. Kết thúc 4 lượt: `totalSupplied == 0`, `totalBorrowed == 0`, Pool còn số dư thặng dư làm tròn BPS không âm (`0.0265 MyUSDT`, đảm bảo khả năng thanh toán 100%). | `tests/HI03_Constraints.test.js` | **PASS** |
| **Chuyển nhượng `LendingPositionNFT` (`A → B → C`)** | Kiểm tra `ownerOf(positionId) == msg.sender` qua 2 chặng chuyển nhượng: `A` bị chặn `NotPositionOwner(1, A)`, `B` rút một phần `300` rồi chuyển sang `C`, `B` bị chặn `NotPositionOwner(1, B)`, `C` chỉ rút được đúng phần còn lại (`InsufficientClaimableBalance` nếu đòi `1,000`), burn NFT cho `C` và chặn tái rút `PositionNotFound(1)`. | `tests/HI03_Constraints.test.js` | **PASS** |
| **Giải mã Custom Error tiếng Việt & đối khớp ABI 4-byte selector** | Đối chiếu 100% custom error trong `deployments/abi/interfaces/ILendingPool.json` khớp từng byte selector với `backend/config/errors.py`, không trùng selector, giải mã đúng tham số WAD sang thông báo tiếng Việt có số liệu rõ ràng. | `tests/test_hi03_errors_and_constraints.py` | **PASS** |

---

## 2. Ghi nhận Kế toán Số dư Thực sau 4 Lượt Đa Người Dùng

Trong kịch bản stress-test 4 lượt (`tests/HI03_Constraints.test.js`, Suite 3):
- Ở mọi thời điểm khi `Borrower B` khóa `1,000 MyUSDT` dạng ERC-20 collateral cùng `400 MyUSDT` tiền mặt rỗi của Lender, `myUSDT.balanceOf(pool) == 1,400 MyUSDT` nhưng `getAvailableLiquidity()` trả chính xác **`400 MyUSDT`** — tách bạch tuyệt đối tiền thế chấp khỏi thanh khoản cho vay.
- Khi tất cả khoản vay và vị thế Lender tất toán hoàn toàn sau 135 ngày tích lũy qua nhiều mức Utilization lẻ (`9166 BPS`, ...), do phép làm tròn xuống (floor) của `utilizationBps` và `supplyAprBps` về số nguyên `BPS`, tổng lãi thu từ người vay luôn lớn hơn hoặc bằng tổng lãi phân bổ cho người cho vay (`0.0265075... MyUSDT` thặng dư dương còn lại trong Pool), đảm bảo **không bao giờ xảy ra âm quỹ hay lỗi `InsufficientPoolLiquidity` khi tất cả Lender đồng loạt rút hết vốn + lãi**.
