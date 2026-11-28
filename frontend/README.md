# DeFi Lending frontend

Frontend DeFi Lending gồm Lending Dashboard, Borrowing Console, IPFS Hub và Analytics; sử dụng Next.js, TypeScript, Tailwind CSS, Recharts, Ethers và Lucide.

## Chạy tại máy

Yêu cầu Node.js 22.18+ (để chạy bộ kiểm thử TypeScript).

```powershell
cd frontend
npm ci
npm run dev
```

Mở http://localhost:3000. Bản mô phỏng này không cần Ganache, MetaMask hoặc backend.

```powershell
npm test
npm run typecheck
npm run build
npm run preview
```

Lệnh build xuất trang tĩnh vào `out/`; preview phục vụ bản build tại http://127.0.0.1:3000. Đổi cổng bằng biến môi trường `PORT` nếu cần.

## Thử các thao tác

- Ví A ban đầu sở hữu Position #1 với vốn gốc 1.000 MyUSDT; Pool chỉ có 500 MyUSDT khả dụng.
- Gửi MyUSDT để nhận NFT vị thế mới. Nhận thêm 1.000 token thử nghiệm từ thẻ ví nếu cần.
- Rút hơn 500 MyUSDT khi chưa có giao dịch khác sẽ bị từ chối do thiếu thanh khoản.
- Chuyển NFT từ A sang B rồi đổi ví ở đầu trang để xem vốn gốc, lãi và quyền rút thuộc ví B.
- Thử tìm mã NFT, đổi biểu đồ 7/30 ngày và tải lại trang. Dữ liệu được giữ trong localStorage.
- “Đặt lại mô phỏng” xóa phiên thử và khôi phục dữ liệu ban đầu.

Đây là dữ liệu mô phỏng, không phải giao dịch blockchain. Không có khóa riêng, chữ ký ví, giao dịch thật hoặc txHash giả.

## Tổ chức mã

- `src/lib/lending-demo.ts`: số tiền WAD, công thức HI01, checkpoint lãi, gửi/rút/chuyển NFT và kiểm tra dữ liệu lưu.
- `src/hooks/use-lending-demo.ts`: tải/lưu phiên và đồng hồ cập nhật lãi.
- `src/components/`: dashboard, biểu đồ dự phóng và dialog có xác nhận.
- `design.md`: tài liệu thiết kế tham chiếu. Giao diện dùng nền trung tính, bề mặt phẳng và nút pill; chuyển sang xanh navy/xanh dương theo yêu cầu.
- `src/app/fonts/`: Be Vietnam Pro 400/500/600/700 được lưu cục bộ dạng WOFF, hỗ trợ tiếng Việt và kèm giấy phép SIL OFL (`BeVietnamPro-OFL.txt`).

Tài liệu phạm vi và điểm nối API: [L02](../docs/Lam/l02_lending_dashboard.md).
Báo cáo kiểm tra: [L02 validation](../reports/Lam/l02_frontend_validation.md).

Việc kết nối ví thật, LendingPool và API thuộc bước tích hợp L05. Giữ giá trị tiền và ID dưới dạng chuỗi từ API; không chuyển sang Number để kiểm tra giao dịch.

## Borrowing Console — L03

Mở http://localhost:3000/borrow/ hoặc chọn **Vay thế chấp** ở menu. Mặc định có NFT trị giá 1.000 MyUSDT, nợ gốc 500 và Pool khả dụng 500.

- Thử nhập vay vượt hạn mức hoặc kéo slider: tổng nợ gồm lãi luôn bị giới hạn ở 70% và không vượt tiền Pool.
- Chọn **Trả nợ**, cấp quyền mô phỏng rồi thử trả một phần hoặc **Trả hết**. Trả hết đọc lại nợ khi xác nhận và tự mở khóa tài sản.
- Giá 80% đưa HF về vùng cảnh báo; 60% đưa về vùng thanh lý. Việc đổi giá không tự thực hiện thanh lý.
- Chọn **Ví thanh lý**, cấp quyền MyUSDT rồi xem trước và xác nhận riêng để thử thanh lý.
- **Đặt lại mô phỏng L03 → Bắt đầu chưa thế chấp** để thử Token/NFT từ đầu.
- **Thêm 30 ngày** chỉ tăng thời gian demo, không gọi blockchain.
- Bảng gas ghi rõ tham số giả định; phần mở rộng và hộp xác nhận có đủ gas units, gwei, ETH và giới hạn +20%.
- Mỗi màn hình có phiên mô phỏng riêng. Không cần Ganache/MetaMask để chạy L03; ký ví/API thật thuộc L05.

Chi tiết: [L03 handoff](../docs/Lam/l03_borrowing_console.md) · [L03 validation](../reports/Lam/l03_frontend_validation.md).

## IPFS Hub và Analytics — L04

Mở `/documents/` để tra cứu CID, tải file và dùng ba generator PDF/Credit Report/Audit Logs của backend. `/analytics/` có biểu đồ APY theo tháng và bốn thành phần số dư ví. Hai trang mặc định dùng dữ liệu mẫu ghi rõ SIMULATED; frontend chỉ phân phối Audit Logs công khai và bản mã của hồ sơ riêng tư.

Chọn **Đổi nguồn dữ liệu** để dùng Q05 API. Token phiên đã xác thực chỉ giữ trong bộ nhớ của trang; quyền xem do backend quyết định (401/403/200). Phần nối MetaMask và phiên dùng chung thuộc L05. Khi API lỗi, giao diện báo lỗi, không thay số liệu bằng mẫu.

Chi tiết cách chạy, SHA-256, quyền và giới hạn: [L04 handoff](../docs/Lam/l04_ipfs_hub_analytics.md) · [L04 validation](../reports/Lam/l04_frontend_validation.md).
