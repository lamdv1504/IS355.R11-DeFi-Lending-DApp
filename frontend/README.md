# DeFi Lending frontend

Dashboard cho vay MyUSDT của L02, sử dụng Next.js, TypeScript, Tailwind CSS, Recharts, Ethers và Lucide.

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
- `design.md`: bảng màu, Manrope và ngôn ngữ thiết kế đã được cung cấp.
- `src/app/fonts/`: Manrope được lưu cục bộ, kèm giấy phép SIL OFL.

Tài liệu phạm vi và điểm nối API: [L02](../docs/Lam/l02_lending_dashboard.md).
Báo cáo kiểm tra: [L02 validation](../reports/Lam/l02_frontend_validation.md).

Việc kết nối ví thật, LendingPool và API thuộc bước tích hợp L05. Giữ giá trị tiền và ID dưới dạng chuỗi từ API; không chuyển sang Number để kiểm tra giao dịch.
