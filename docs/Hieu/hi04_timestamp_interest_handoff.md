# HI04 – Bàn giao Tính toán Lãi suất Thời gian thực (Timestamp), `InterestMath.sol` & Tiện ích Tua thời gian Demo (Hiếu, Giai đoạn 3)

## 1. Phạm vi & Nguyên tắc Kỹ thuật (GĐ2/GĐ3 Workflow + Rubric)

`HI04` hoàn thiện mô-đun toán học tính lãi theo từng giây `block.timestamp` trên `contracts/libraries/InterestMath.sol`, tích hợp trực tiếp vào `contracts/LendingPool.sol`, bổ sung bộ hàm đọc/dự phóng lãi realtime cho **Quân (`Q02`/`Q04`/`Q05`)** và **Lâm (`L02`/`L03`/`L04`)**, kèm tiện ích tua thời gian chỉ chạy trên môi trường local (`Chain ID = 31337`):

1. **Kỷ luật số học Solidity `0.8.24` + `Math.mulDiv` (OpenZeppelin v5)**:
   - Solidity `^0.8.20` tự động kiểm tra overflow/underflow ở mức opcode (`Panic 0x11`), không cần phụ thuộc thư viện `SafeMath` cũ của OpenZeppelin v4.
   - `InterestMath.sol` dùng `Math.mulDiv` (trung gian 512-bit), nhân `WAD (1e18)` trước khi chia cho `SECONDS_PER_YEAR * BPS` (`315_360_000_000`) một lần duy nhất ở cuối → ngay cả khoảng **1 giây** vẫn sinh lãi `> 0 wei`, không bao giờ mất số lẻ về `0`.
2. **Phân biệt rõ `APR` (on-chain đơn) vs. `APY` (quy đổi lãi kép tham khảo)**:
   - Lãi tích lũy thật trên Smart Contract tuân thủ tuyệt đối **APR đơn theo từng giây**.
   - Hàm `InterestMath.calculateReferenceApyWad` / `calculateReferenceApyBps` và `LendingPool.getInterestRateSnapshot()` tách bạch trường `borrowAprBps`/`supplyAprBps` khỏi `borrowApyRefBps`/`supplyApyRefBps` (`(1 + APR/365)^365 - 1`) để giao diện **không bao giờ ghi nhầm `APY` cho giá trị `APR`**.
3. **Cộng dồn chỉ số đa kỳ — tuyệt đối không hồi tố**:
   - Trước mọi thay đổi `totalSupplied` hoặc `totalBorrowed`, `LendingPool` gọi `_accruePoolInterest()` khóa toàn bộ kỳ lịch sử vào `borrowIndex` và `supplyIndex` theo lãi suất **CŨ**, sau đó mới tính và phát sự kiện `InterestRateUpdated(...)` với lãi suất **MỚI**.
   - Lãi suất mới chỉ áp dụng từ `block.timestamp` trở về sau; Lender mới nạp vào Pool không thể hưởng ngược lãi của các kỳ trước.

---

## 2. Hàm Đọc Lãi Realtime & Snapshot (Bàn giao cho Quân & Lâm)

ABI mới nhất đã được xuất ra `deployments/abi/LendingPool.json` và `deployments/abi/interfaces/ILendingPool.json` (tương thích ngược 100% với `HI02` & `HI03`).

| Hàm trên `ILendingPool` / `LendingPool` | Mục đích sử dụng cho Backend (`Q02`/`Q04`/`Q05`) & Frontend (`L02`/`L03`/`L04`) |
|---|---|
| `getInterestRateSnapshot()` | Trả về `InterestRateSnapshot` gồm `timestamp`, `utilizationBps`, `borrowAprBps`, `supplyAprBps` (on-chain đơn), `borrowApyRefBps`, `supplyApyRefBps` (tham khảo ghép ngày), `borrowIndexWad`, `supplyIndexWad`. |
| `calculateAccruedInterest(address borrower)` | Trả tổng lãi vay đã tích lũy tới `block.timestamp` hiện tại (WAD), tăng liên tục từng giây. |
| `previewBorrowerInterest(address borrower, uint256 extraSeconds)` | Dự phóng tổng lãi vay của `borrower` sau `extraSeconds` giây nữa (khớp `0 wei` với kết quả sau `evm_increaseTime`). |
| `getLenderEarnedInterest(uint256 positionId)` | Trả lãi thực tế Lender nhận được theo tỷ trọng vốn góp trong Pool và thời gian gửi (WAD). |
| `previewLenderEarnedInterest(uint256 positionId, uint256 extraSeconds)` | Dự phóng tổng lãi Lender của `positionId` sau `extraSeconds` giây nữa (hỗ trợ đồng hồ nhảy số realtime trên `L02`). |
| `accrueInterest()` *(write)* | Chốt chỉ số lãi tích lũy tới `block.timestamp` và phát sự kiện `InterestRateUpdated(...)` phục vụ `Q04` Audit Logs hoặc sau khi tua thời gian demo. |

### Hàm đối xứng bên Python (`backend/config/constants.py`)
- `calculate_reference_apy_wad(apr_bps)` & `calculate_reference_apy_bps(apr_bps)`: khớp nguyên từng đơn vị BPS với `InterestMath.sol`.
- `format_rate_snapshot_for_api(borrow_apr_bps, supply_apr_bps, utilization_bps)`: chuẩn hóa JSON tách riêng `borrow_apr_percent` / `borrow_apy_ref_percent`, `supply_apr_percent` / `supply_apy_ref_percent`, kèm `accrual_model: "SIMPLE_APR_PER_SECOND"` và ghi chú tiếng Việt `apy_disclaimer_vi`.

---

## 3. Công cụ Tua thời gian Demo (CHỈ BẬT TRÊN LOCAL `31337`, CHẶN SEPOLIA)

> **Lưu ý bảo mật Rubric:** Không gắn biến chỉnh đồng hồ giả vào `LendingPool.sol` production. Chức năng tua thời gian chỉ thực thi qua RPC `evm_increaseTime` + `evm_mine` trên Hardhat Local (`Chain ID = 31337`) và tự động báo lỗi nếu chạy trên Sepolia (`11155111`).

- **CLI Hardhat (`scripts/fast_forward_time.js`)**:
  ```powershell
  # Tua mặc định 30 ngày trên localhost (Chain ID 31337)
  npm run demo:fast-forward

  # Tua 60 ngày hoặc số giây tùy chọn
  $env:DAYS="60"; npm run demo:fast-forward
  $env:SECONDS="7776000"; npm run demo:fast-forward
  ```
- **Python Backend Helper (`backend/services/time_travel.py`) — sẵn sàng cho Quân (`Q05` `POST /api/demo/fast-forward-time`) & Hiếu (`HI06`)**:
  ```python
  from backend.services.time_travel import fast_forward_days

  result = fast_forward_days(w3, 60)  # Tự chặn PermissionError nếu chain_id != 31337
  return result.to_dict()
  ```

---

## 4. Lệnh Kiểm thử nhanh HI04

```powershell
npm run compile
npm run export:hi02
npm run test:hi04
npm test
.\.venv\Scripts\pytest.exe -v
```
