# Báo cáo Kiểm thử & Nghiệm thu Tính lãi Thời gian thực – HI04 (Hiếu, Giai đoạn 3)

- **Nhánh thực hiện**: `feature/hieu-gd3-hi04-timestamp-interest`
- **Môi trường kiểm chứng**: Hardhat `2.22.18`, Solidity `0.8.24` (EVM target `paris`), OpenZeppelin `5.0.2`, Python `3.11.9` (`pytest 9.2.0`, `web3`).
- **Kết quả tổng hợp**:
  - `npm run compile`: **0 warnings, 0 errors** (biên dịch đầy đủ `InterestMath.sol`, `InterestMathHarness.sol`, `LendingPool.sol`).
  - `npm run export:hi02`: Xuất mới `deployments/abi/LendingPool.json` và `deployments/abi/interfaces/ILendingPool.json` kèm các hàm realtime HI04.
  - `npm test` (toàn repo `H01` + `H02` + `HI01` + `HI02` + `HI03` + `HI04`): **`111 passing` (2s)** — trong đó `tests/HI04_InterestMath.test.js` đạt **6/6 passing**.
  - `pytest -v` (toàn repo `HI01` + `HI03` + `HI04` + `Q01`): **`18 passed` (2.44s)** — trong đó `tests/test_hi04_interest_and_time_travel.py` đạt **4/4 passing**.

---

## 1. Bảng Đối chiếu Nghiệm thu HI04 (Mục “Kiểm tra xong chưa?”)

| Tiêu chí kiểm chứng HI04 | Kịch bản test thực tế | File test | Kết quả |
|---|---|---|---|
| **Lãi tăng chính xác từng giây, không mất số lẻ chia nguyên (nhân `1e18` trước khi chia)** | Kiểm tra `deltaSeconds = 1s`: `calculateIndexDelta(500, 1) = 1_585_489_599 wei > 0`; vay `500 MyUSDT` ở `10% APR` sinh `1_585_489_599_188 wei/giây`; tăng đơn điệu qua `1s < 2s < 60s < 1d < 30d < 60d < 365d`; đúng `8_219_178_082_191_780_821 wei` cho kịch bản Demo 60 ngày (`Borrower == Lender`). | `tests/HI04_InterestMath.test.js` | **PASS** |
| **Chống tràn số (Solidity 0.8+ checked arithmetic + `Math.mulDiv`)** | Kiểm tra tràn số trong `aprBps * deltaSeconds` (`Panic 0x11`), tràn kết quả 256-bit trong `Math.mulDiv` và tràn `advanceCumulativeIndex` tại `MaxUint256` đều revert an toàn, không wrap-around. | `tests/HI04_InterestMath.test.js` | **PASS** |
| **Phân biệt rõ `APR` vs `APY` (không ghi nhầm APY cho APR)** | Đối khớp `InterestMath.calculateReferenceApyBps` với `backend/config/constants.py`: `0→0`, `500→512`, `1000→1051`, `1500→1617`; `getInterestRateSnapshot()` tách riêng `borrowAprBps`/`supplyAprBps` và `borrowApyRefBps`/`supplyApyRefBps`; kiểm chứng lãi 365 ngày on-chain bằng đúng **simple APR (`50 MyUSDT`)**, không phải compounded APY (`~52.58 MyUSDT`). | `tests/HI04_InterestMath.test.js`, `tests/test_hi04_interest_and_time_travel.py` | **PASS** |
| **Phân bổ lãi Lender theo tỷ trọng vốn góp & dự phóng realtime khớp `0 wei`** | Lender A góp `750` (75%), Lender B góp `250` (25%); sau `evm_increaseTime(30d)` + `evm_mine`, `actualB30d == previewBorrowerInterest` (**0 wei**), `actualLA30d == previewLenderEarnedInterest` (**0 wei**), `actualLA30d == actualLB30d * 3` (**0 wei**) và `actualLA30d + actualLB30d <= actualB30d` (chênh làm tròn floor `500 wei`, an toàn thanh toán 100%). | `tests/HI04_InterestMath.test.js` | **PASS** |
| **Cập nhật lãi đa kỳ khi Utilization đổi — tuyệt đối không hồi tố** | 3 kỳ liên tiếp (`30d @ U=50% [10%/5%]` → `30d @ U=80% [13%/10.4%]` → `30d @ U=40% [9%/3.6%]`): xác nhận `InterestRateUpdated` phát đủ 3 lần, lãi kỳ 1 khóa ở `10%` (không bị áp ngược `13%`), Lender B vào ở ngày 60 bắt đầu từ `0` lãi và chỉ hưởng kỳ 3 (`3.6%`), tổng lãi 2 Lender khớp tổng lãi Borrower sau 90 ngày. | `tests/HI04_InterestMath.test.js` | **PASS** |
| **Công cụ tua thời gian demo chỉ bật trên Local `31337`, chặn Sepolia** | `backend/services/time_travel.py` chặn `Sepolia (11155111)` và `Mainnet (1)` bằng `PermissionError`, chặn giá trị `<= 0` hoặc vượt 10 năm bằng `ValueError`, và thực thi `evm_increaseTime` + `evm_mine` sạch trên Chain ID `31337`. | `tests/test_hi04_interest_and_time_travel.py` | **PASS** |
