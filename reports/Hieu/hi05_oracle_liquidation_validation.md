# Báo cáo Kiểm thử & Nghiệm thu PriceOracle, Health Factor & Thanh lý – HI05 (Hiếu, Giai đoạn 3)

- **Nhánh thực hiện**: `feature/hieu-gd3-hi05-oracle-liquidation`
- **Môi trường kiểm chứng**: Hardhat `2.22.18`, Solidity `0.8.24` (EVM target `paris`), OpenZeppelin `5.0.2`, Python `3.11.9` (`pytest 9.2.0`, `web3`, `eth_abi`).
- **Kết quả tổng hợp**:
  - `npm run compile`: **Compiled 6 Solidity files successfully (`0 warnings`, `0 errors`)**
  - `npm run export:hi05`: Xuất mới `deployments/abi/PriceOracle.json`, `deployments/abi/interfaces/IPriceOracle.json`, `deployments/abi/LendingPool.json`, `deployments/abi/interfaces/ILendingPool.json`.
  - `npm test` (toàn repo `H01` + `H02` + `HI01` + `HI02` + `HI03` + `HI04` + `HI05`): **`119 passing` (7s)** — trong đó `tests/HI05_OracleLiquidation.test.js` đạt **8/8 passing**.
  - `pytest -v` (toàn repo `H03` + `HI01` + `HI03` + `HI04` + `HI05` + `Q01`): **`31 passed` (5.62s)** — trong đó `tests/test_hi05_oracle_and_liquidation.py` đạt **3/3 passing**.

---

## 1. Bảng Đối chiếu Nghiệm thu HI05 (Mục “Kiểm tra xong chưa?” & Bổ sung Rubric)

| Tiêu chí kiểm chứng HI05 | Kịch bản kiểm thử cụ thể | File kiểm thử | Kết quả |
|---|---|---|---|
| **Giá giữ nguyên (`HF > 1.0`) không ai thanh lý được** | Nợ = `0` (`HF = ∞`) và vay `500/1000` (`HF = 1.60`, `SAFE`): Liquidator gọi `liquidate()` bị revert ngay lập tức `HealthFactorSafe`. | `tests/HI05_OracleLiquidation.test.js` | **PASS** |
| **Biên chính xác `HF == 1.0` bị chặn thanh lý** | Tính chính xác giá trị tài sản thế chấp ứng với `HF == 1.000000e18` tại block mục tiêu → `liquidate()` vẫn bị revert `HealthFactorSafe` (chỉ cho phép khi `HF < 1e18` nghiêm ngặt). | `tests/HI05_OracleLiquidation.test.js` | **PASS** |
| **Giảm giá chỉ tạo trạng thái đủ điều kiện, không tự chạy thanh lý khi chưa có tx `liquidate()`** | Sau khi Owner gọi `setPriceMultiplierBps(6000)` (-40% → `HF = 0.96 < 1.0`), xác nhận khoản vay vẫn `active == true`, `CollateralNFT` vẫn nằm tại Pool và `DebtToken == 500` cho tới khi Liquidator ký gửi `liquidate(borrower)`. | `tests/HI05_OracleLiquidation.test.js` + Live Localhost | **PASS** |
| **Thanh lý `CollateralNFT` + thu hồi 100% vốn cho Pool** | Sau 30 ngày + giảm giá 40%, Liquidator gọi `liquidate()` trả `~504.11 MyUSDT`, nhận `CollateralNFT #1`, burn `500 DebtToken`, `ReceiptSettled(1, borrower, true)`, phát `LoanLiquidated`, và Lender A rút thành công toàn bộ `1,000 + lãi`. | `tests/HI05_OracleLiquidation.test.js` + Live Localhost | **PASS** |
| **Thanh lý ERC-20 (+5% Liquidation Bonus, hoàn phần dư & chặn tràn khi sập 55%)** | Giảm 40% (`0.60/token`): Liquidator trả `~500`, thu giữ `~875` token (`525 MyUSDT` = nợ + 5% thưởng), Borrower nhận lại `~125` token dư. Giảm sâu 55% (`0.45/token`): chặn gọn tại 100% tài sản khóa (`1,000` token, `0` dư, không tràn ngược). | `tests/HI05_OracleLiquidation.test.js` | **PASS** |
| **Thanh lý do lãi vay tích lũy vượt 80% khi giá giữ nguyên** | Vay kịch trần `700/1000` (`12% APR`), tua 450 ngày làm tổng nợ vượt `800` (`HF < 1.0`) → `liquidate()` thành công không cần chỉnh Oracle. | `tests/HI05_OracleLiquidation.test.js` | **PASS** |
| **Kiểm soát quyền cập nhật Oracle (`onlyOwner`)** | Borrower, Liquidator và ví ngoài gọi `setCollateralTokenPrice`, `setCollateralNFTValuation`, `setPriceMultiplierBps`, `clearCollateralNFTValuationOverride`, `resetDemoPrices` hoặc `LendingPool.setPriceOracle` đều bị revert `OwnableUnauthorizedAccount` (`0x118cdaa7`, HTTP `403`). | `tests/HI05_OracleLiquidation.test.js`, `tests/test_hi05_oracle_and_liquidation.py` | **PASS** |

---

## 2. Log Triển khai 7 Contract & Giao dịch `liquidate()` Thực tế trên Localhost (`Chain ID = 31337`)

### 2.1. Kết quả chuỗi `deploy:myusdt → deploy:h02 → deploy:hi02 → deploy:hi05`
- **`LendingPool`**: `0x9A676e781A523b5d0C0e43731313A708CB607508` (Block `15`, deploy tx: `0xa8eb93b58fb177247eb0ab6c56c71b78a87b73ec4d24e72d68a86280736e0813`)
- **`PriceOracle`**: `0x68B1D87F95878fE05B998F19b66F4baba5De1aed` (Block `19`, deploy tx: `0x58ed4b1763cec07ef9355e3e6a54445913b9a753cc6323799f2801e19e8a036c`)
- **Binding `LendingPool.setPriceOracle(PriceOracle)`**: tx `0xc31ddc26197f6aa20bddda1f43f3eb7d91041f342ff3f4dc9b231fdcdec375a5` (đã xác nhận `pool.priceOracle() == 0x68B1D87F95878fE05B998F19b66F4baba5De1aed`)

### 2.2. Log Giao dịch Thực tế (Web3.py ↔ Hardhat Local Node `31337`)

```text
[VERIFIED BINDING] LendingPool(0x9A676e781A523b5d0C0e43731313A708CB607508) -> PriceOracle(0x68B1D87F95878fE05B998F19b66F4baba5De1aed)
  [REVERT DECODED] code=OwnableUnauthorizedAccount selector=0x118cdaa7 http=403
                   vi="Ví 0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC không có quyền chủ sở hữu (onlyOwner) để cập nhật cấu hình hoặc giá PriceOracle."
[CHECK 1 - SAFE] HF=1.6 status=SAFE liquidatable=False
  [REVERT DECODED] code=HealthFactorSafe selector=0x053bbeed http=400
                   vi="Khoản vay vẫn an toàn (Health Factor = 1.6000 >= 1.00), chưa đủ điều kiện thanh lý."
[CHECK 2 - 40% DROP] txHash=0xbd263f9b4a8c8adb391d3ce504e2b2216dcc3bf1b6740bcc4f3b35830d3dc37a HF=0.96 status=LIQUIDATABLE
[CHECK 3 - LIQUIDATED] txHash=0x83897909768c6323353b83ae35921c077a55039b395c8f6e0ae2bd02aa97c385
                       block=29 gasUsed=229148
                       borrower=0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC
                       liquidator=0x15d34AAf54267DB7D7c367839AAf71A00a2C6A65 (Account #4 - Liquidator / Keeper)
                       debtCovered=500.000005 MyUSDT
                       collateralSeized=600.000000 MyUSDT (CollateralNFT #1 -> liquidator)
                       hfBefore=0.960000
[CHECK 4 - POOL RECOVERED] Lender A withdrew full claimable=1000.000005 MyUSDT
ALL LIVE HI05 ORACLE & LIQUIDATION CHECKS PASSED 100%!
```
