# HI05 – Bàn giao `PriceOracle.sol`, Health Factor & Cơ chế Thanh lý `liquidate()` (Hiếu, Giai đoạn 3)

## 1. Phạm vi & Nguyên tắc Vận hành (Mô tả bài toán + Rubric Tiêu chí 1 & 2)

`HI05` hoàn thiện hợp đồng định giá tài sản thế chấp `contracts/PriceOracle.sol`, gắn trực tiếp với `contracts/LendingPool.sol` (`setPriceOracle`), bổ sung hàm view `getLiquidationPreview(address borrower)` cho **Quân (`Q02`, `Q05`)** và **Lâm (`L03` Borrowing Console)**, đồng thời bàn giao đầy đủ ABI, bytecode và địa chỉ deploy local của **cả 7 Smart Contract MVP**:

1. **Kiểm soát quyền cập nhật giá Oracle (`onlyOwner`)**:
   - Mọi hàm ghi trên `PriceOracle.sol` (`setCollateralTokenPrice`, `setCollateralNFTValuation`, `clearCollateralNFTValuationOverride`, `setPriceMultiplierBps`, `resetDemoPrices`) đều gắn `onlyOwner` (OpenZeppelin v5).
   - Mọi ví không có quyền (Borrower, Liquidator, ví ngoài) gọi vào sẽ bị revert `OwnableUnauthorizedAccount(caller)` (selector `0x118cdaa7`) và `backend/config/errors.py` tự giải mã thành HTTP `403` tiếng Việt.
   - Chế độ mô phỏng giảm giá (`setPriceMultiplierBps(6000)` = giảm 40%) **chỉ phục vụ demo/test trên Hardhat Local (`Chain ID = 31337`)**, không mở nút chỉnh giá giả trên Sepolia.
2. **Ai kích hoạt giao dịch thanh lý (`liquidate()`)?**:
   - **Smart Contract KHÔNG tự chạy ngầm theo thời gian** và việc giảm giá trên `PriceOracle` **KHÔNG tự động thanh lý** khoản vay.
   - Thanh lý chỉ thực thi khi một **Liquidator / Keeper** (trên local là ví test **Account #4**: `0x15d34AAf54267DB7D7c367839AAf71A00a2C6A65`, hoặc bất kỳ ví nào đã `MyUSDT.approve(LendingPool, totalDebt)`) gửi và ký giao dịch `LendingPool.liquidate(borrower)` khi và chỉ khi **`getHealthFactor(borrower) < 1e18`**.
   - Nếu `HF == 1.0e18` (đúng biên 80%) hoặc `HF > 1.0e18` → revert ngay lập tức `HealthFactorSafe(hfBefore)`.
3. **Hiệu ứng khi `liquidate(borrower)` thành công**:
   - Thu toàn bộ `totalDebt` (`principal + accruedInterest`) bằng `MyUSDT` từ Liquidator về Pool (khôi phục 100% vốn + lãi cho Lenders rút).
   - Gọi `DebtToken.burn(borrower, principal)` xóa nợ on-chain cho Borrower.
   - Chuyển tài sản thế chấp cho Liquidator:
     - **`CollateralNFT`**: chuyển nguyên NFT (`safeTransferFrom`) cho Liquidator.
     - **ERC-20 collateral**: tính `seizeValue = min(collateralValue, totalDebt * 1.05)` (gồm **+5% Liquidation Bonus**), chuyển lượng token tương ứng cho Liquidator và hoàn phần dư (nếu có) về Borrower.
   - Gọi `CollateralReceiptNFT.settleReceipt(receiptId, true)` và phát sự kiện `LoanLiquidated(borrower, liquidator, debtCoveredWad, collateralSeizedWad, healthFactorBeforeWad, timestamp)` để Quân (`Q04`) ghi vào **Credit Report JSON** trên IPFS.

---

## 2. Bảng Địa chỉ & ABI đầy đủ 7 Hợp đồng MVP trên Localhost (`Chain ID = 31337`)

Toàn bộ ABI + bytecode đã xuất trong `deployments/abi/` và đồng bộ vào `deployments/localhost.json` + `backend/config/contracts.json`:

| # | Contract | Địa chỉ Localhost (`31337`) | Trạng thái | File ABI + Bytecode |
|---|---|---|---|---|
| 1 | `MyUSDT` | `0x5FbDB2315678afecb367f032d93F642f64180aa3` | `DEPLOYED` | `deployments/abi/MyUSDT.json` |
| 2 | `CollateralNFT` | `0x610178dA211FEF7D417bC0e6FeD39F05609AD788` | `DEPLOYED` | `deployments/abi/CollateralNFT.json` |
| 3 | `CollateralReceiptNFT` | `0xB7f8BC63BbcaD18155201308C8f3540b07f84F5e` | `BOUND_TO_POOL` | `deployments/abi/CollateralReceiptNFT.json` |
| 4 | `DebtToken` | `0xA51c1fc2f0D1a1b8494Ed1FE312d7C3a78Ed91C0` | `BOUND_TO_POOL` | `deployments/abi/DebtToken.json` |
| 5 | `LendingPositionNFT` | `0x0DCd1Bf9A1b36cE34237eEaFef220932846BCD82` | `BOUND_TO_POOL` | `deployments/abi/LendingPositionNFT.json` |
| 6 | `LendingPool` | `0x9A676e781A523b5d0C0e43731313A708CB607508` | `DEPLOYED_AND_BOUND` (`ORACLE_BOUND`) | `deployments/abi/LendingPool.json` |
| 7 | **`PriceOracle`** | **`0x68B1D87F95878fE05B998F19b66F4baba5De1aed`** | **`DEPLOYED_AND_BOUND`** | **`deployments/abi/PriceOracle.json`** |

---

## 3. Hàm View / Write Bàn giao cho Quân (`Q02`, `Q05`) & Lâm (`L03`)

| Hợp đồng | Hàm / Event | Công dụng cho `Q02`/`Q05` & `L03` |
|---|---|---|
| `LendingPool` | `getHealthFactor(address borrower)` | Trả `HF_WAD` (`1e18`, `type(uint256).max` nếu nợ = 0); phối hợp `format_health_factor_for_api()` trong `backend/config/constants.py`. |
| `LendingPool` | `getLiquidationPreview(address borrower)` | Trả 1 lần duy nhất `LiquidationPreview { liquidatable, healthFactorWad, totalDebtWad, collateralValueWad, seizeValueWad, isNFTCollateral }` cho nút **Liquidate** & Pre-Transaction Preview trên `L03`. |
| `LendingPool` | `liquidate(address borrower)` | Thực thi thanh lý khi `HF < 1e18`; yêu cầu Liquidator đã `MyUSDT.approve(pool, totalDebt)` trước. |
| `LendingPool` | `LoanLiquidated(...)` *(Event)* | Nguồn sự kiện on-chain cho `Q04` Credit Report (giảm điểm tín dụng khi bị thanh lý). |
| `PriceOracle` | `setPriceMultiplierBps(uint256 newMultiplierBps)` *(onlyOwner)* | Giả lập giảm giá thị trường trên local (vd: `6000` = giảm 40%, `10000` = khôi phục 100%); phát `PriceMultiplierUpdated` + `PriceUpdated`. |
| `PriceOracle` | `setCollateralTokenPrice(uint256)` / `setCollateralNFTValuation(tokenId, wad)` *(onlyOwner)* | Cập nhật định giá từng tài sản ERC-20 hoặc từng `CollateralNFT`; phát `PriceUpdated`. |
| `PriceOracle` | `resetDemoPrices()` *(onlyOwner)* | Khôi phục giá token về `1e18` và hệ số về `10_000 BPS` sau buổi demo. |

---

## 4. Lệnh Biên dịch, Export ABI, Test & Deploy đầy đủ 7 Contract Localhost

```powershell
# 1. Biên dịch, xuất ABI HI05 và chạy test
npm run compile
npm run export:hi05
npm run test:hi05
npm test
.\.venv\Scripts\pytest.exe -v

# 2. Deploy đủ 7 contract trên Hardhat Local Node mới (Terminal 1: npm run node)
# (Nếu backend/config/contracts.json đã có LendingPool từ lần chạy trước, reset LendingPool.address="" trước khi chạy deploy:h02)
npm run deploy:myusdt
npm run deploy:h02
npm run deploy:hi02
npm run deploy:hi05
```
