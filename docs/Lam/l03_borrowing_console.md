# L03 — Borrowing Console

Lâm, giai đoạn 3. Nhánh `feature/lam-l03-borrowing-console`.

## Đầu vào bắt buộc

Kế hoạch, sheet **Lam**, ô **H4** (đồng thời sheet **23 cong viec goc**, ô **J21**): “Phụ thuộc L01 và HI03/HI05; tích hợp với Web3.py API ở L05.”

Đã đối chiếu các đầu vào có sẵn:

- [L01 wireframe](ui_wireframes.md) và [đề xuất dữ liệu](l01_api_contract.md).
- [HI03 constraints](../Hieu/hi03_constraints_handoff.md).
- [HI05 Oracle/liquidation](../Hieu/hi05_oracle_liquidation_handoff.md).
- [LendingPool](../../contracts/LendingPool.sol), [PriceOracle](../../contracts/PriceOracle.sol), ProtocolMath/InterestMath và ABI tương ứng trong `deployments/abi/`.
- [Q02 Web3 service](../Quan/q02_web3_service_handoff.md), service và các API hiện có để tham chiếu điểm tích hợp sau.

ABI LendingPool có `depositCollateral`, `borrow`, `repay`, `getHealthFactor`, `getLiquidationPreview`, `liquidate` và `getAvailableLiquidity`. Không thiếu file bàn giao bắt buộc nên không bị chặn theo điều kiện của người dùng.

## Phạm vi

Trang `http://localhost:3000/borrow/` triển khai trong Next.js/TypeScript hiện có, tương ứng BorrowingConsole/HealthFactorGauge của bảng kế hoạch. Giữ font Be Vietnam Pro, navy/xanh dương, bề mặt phẳng và nút pill của giao diện hiện tại; tham khảo `frontend/design.md`. Không đổi lại font hoặc palette cũ của L02.

| Yêu cầu L03 | Triển khai |
| --- | --- |
| Hai cột | Tài sản thế chấp và quản lý khoản vay; xếp dọc trên điện thoại |
| Token/NFT | Khóa MyUSDT hoặc NFT #7, cấp quyền riêng, biên nhận, trạng thái khóa/mở khóa |
| Vay và LTV | Thanh trượt và nhập tay; kiểm tra tổng nợ gồm lãi, giới hạn 70% và thanh khoản |
| DebtToken | Nợ gốc; mint/burn mô phỏng khi vay/trả phần gốc; không chuyển nhượng |
| Health Factor | Đồng hồ SVG, nhãn và banner 3 mức; quyết định dùng bigint WAD |
| Gas và lãi | Bảng xem trước ETH/gwei/gas limit, APR trước/sau, APY tham khảo, lãi 30 ngày |
| Xác nhận | Hộp thoại native, kiểm tra lại tại thời điểm xác nhận |
| Thanh lý | Ví riêng, đủ số dư/cấp quyền, HF < 1, xác nhận riêng; không tự thanh lý khi giảm giá |
| Kiểm tra demo | Giá 100/80/60%, tăng 30 ngày, nhận token thử nghiệm, đặt lại phiên trống hoặc khoản vay 500 |

Đây là **mô phỏng phía frontend của L03**. Không gọi ví, không gửi giao dịch, không giả txHash/CID và không thay đổi Oracle hoặc clock blockchain thật. Kết nối thực với MetaMask/API thuộc L05 theo đúng phụ thuộc trong kế hoạch.

## Công thức và trạng thái

- Tiền/ID lưu dạng chuỗi, xử lý bằng bigint WAD 1e18. Number chỉ dùng định dạng/vẽ hoặc BPS nhỏ trên slider.
- `maxTotalDebt = floor(collateralValue * 7000 / 10000)`.
- `availableToBorrow = max(0, min(maxTotalDebt - totalDebt, poolCash))`.
- `HF_WAD = floor(collateralValue * 8000 * 1e18 / (totalDebt * 10000))`.
- Không nợ: HF vô hạn. HF >= 1,5 xanh; 1 <= HF < 1,5 vàng; HF < 1 đỏ. **HF = 1 chặn liquidate**.
- Hiển thị HF làm tròn xuống 4 chữ số để giá trị ngay dưới 1 không hiện thành 1,0000.
- APR theo HI01/HI04: `500 + floor(U_bps * 1000 / 10000)`. APY ghép hằng ngày chỉ là tham khảo.
- Index cộng dồn HI04 tính theo giây; chốt APR cũ trước nghiệp vụ Pool. Approve, đổi giá và tăng thời gian không tự checkpoint Pool.
- Trả lãi trước rồi gốc; cap số trả tại tổng nợ. “Trả hết” đọc lại tổng nợ khi xác nhận và tự mở khóa/settle biên nhận.
- Liquidator trả toàn bộ nợ. NFT chuyển nguyên chiếc; ERC-20 thu tối đa theo giá trị nợ cộng thưởng 5%, hoàn token thừa.
- Pool cash là tiền khả dụng riêng. Không cộng collateral ERC-20 đang khóa vào tiền cho vay được.
- Nút tối đa giữ dư địa nhỏ khi đã có nợ, tránh quote hết hạn mức bị lãi phát sinh vượt trần trong lúc xem trước. Đây là lựa chọn UI, không nâng giới hạn 70%.

## Gas minh họa

Các tham số được ghi rõ là **SIMULATED**, không phải `estimateGas` từ RPC:

| Thao tác | Gas units giả định |
| --- | ---: |
| Approve MyUSDT/NFT | 50.000 |
| Deposit collateral | 145.000 |
| Borrow | 180.000 |
| Repay | 160.000 |
| Withdraw collateral | 100.000 |
| Liquidate | 230.000 |

Giá mặc định 2 gwei, người dùng có thể đổi. Giới hạn gas = units × 1,2; phí ETH minh họa = units × gasPriceWei / 1e18. Không quy đổi USD khi chưa có nguồn giá ETH/USD. Không trừ ETH mô phỏng.

## Tổ chức mã và tích hợp L05

- `src/components/app-shell.tsx`: điều hướng, chọn ví và drawer dùng chung L02/L03; nội dung và model L02 được giữ.
- `src/components/borrowing-console.tsx`: form và kịch bản.
- `src/components/health-factor-gauge.tsx`: đồng hồ.
- `src/components/borrow-transaction-preview.tsx`: preview/cấp quyền/xác nhận.
- `src/lib/borrowing-demo.ts`: mô hình thuần và kiểm tra dữ liệu.
- `src/hooks/use-borrowing-demo.ts`: phiên localStorage và đồng hồ.
- `src/app/borrow/`: route, metadata, CSS riêng.
- `tests/borrowing-demo.test.ts`: các bất biến nghiệp vụ, biên HF/LTV và gas.

Mô phỏng L03 dùng khóa lưu riêng `defi-borrowing-l03-v1`; không ghi đè phiên L02. Kịch bản mặc định: NFT trị giá 1.000, nợ gốc 500, Pool cash 500; ví người vay 1.500, liquidator 2.000 MyUSDT. Hai ví là tài khoản test từ bàn giao, không phải kết nối ví hoặc vai trò xác thực thật.

Ở L05, thay hook bằng dữ liệu Q05/Web3Service; giữ amount WAD và ID dạng chuỗi. Đọc HF, available liquidity, allowance/ownership mới; lấy quote unsigned từ backend; tạo PDF/CID trước borrow; MetaMask ký client và kiểm tra receipt trước cập nhật thành công. Không gửi private key vào backend. Kiểm tra bytecode/RPC mới, không coi registry local là bằng chứng node đang chạy. Các điều khiển giá/clock chỉ được nối mạng local và kiểm tra quyền đúng theo HI05/Q05; không mở mock giá trên Sepolia.

Kết quả và ảnh minh chứng: [báo cáo L03](../../reports/Lam/l03_frontend_validation.md).

KPI summarizes total debt to at most 2 decimal places; detailed interest/debt and all checks retain WAD precision. On screens <=370px, KPI text uses 20px and stays on one line. Displayed borrowing capacity is floored.
