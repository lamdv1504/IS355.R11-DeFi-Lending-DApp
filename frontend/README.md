# DeFi Lending frontend

Frontend DeFi Lending gồm Lending Dashboard, Borrowing Console, IPFS Hub và Analytics; sử dụng Next.js, TypeScript, Tailwind CSS, Recharts, Ethers và Lucide.

## Chạy tại máy

Yêu cầu Node.js 22.18+ (để chạy bộ kiểm thử TypeScript).

```powershell
cd frontend
npm ci
npm run dev
```

Mở http://localhost:3000. Mặc định dùng kết nối thật qua MetaMask và Q05 API. Nút **Dữ liệu mẫu** mở các phiên mô phỏng độc lập, không cần blockchain/backend.

```powershell
npm test
npm run typecheck
npm run build
npm run preview
```

Lệnh build xuất trang tĩnh vào `out/`; preview phục vụ bản build tại http://127.0.0.1:3000. Đổi cổng bằng biến môi trường `PORT` nếu cần.

## Thử các thao tác với dữ liệu mẫu

Chọn **Dữ liệu mẫu** ở thanh trên trước khi thử các ví và số liệu dưới đây.

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

L05 đã nối MetaMask, LendingPool và API qua phiên ví dùng chung. Giữ giá trị tiền và ID dưới dạng chuỗi từ API; không chuyển sang Number để kiểm tra giao dịch.

## Borrowing Console — L03

Mở http://localhost:3000/borrow/ hoặc chọn **Vay thế chấp** ở menu. Trong chế độ dữ liệu mẫu có NFT trị giá 1.000 MyUSDT, nợ gốc 500 và Pool khả dụng 500.

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

Mở `/documents/` để tra cứu CID, tải file và dùng ba generator PDF/Credit Report/Audit Logs của backend. `/analytics/` có biểu đồ APY theo tháng và bốn thành phần số dư ví. Hai trang dùng chung mạng và phiên đã ký; khi chủ động chuyển sang dữ liệu mẫu, frontend chỉ phân phối Audit Logs công khai và bản mã của hồ sơ riêng tư.

Kết nối MetaMask và **Ký xác thực** để dùng Q05 API. Token phiên chỉ giữ trong bộ nhớ của ứng dụng và dùng chung qua các trang; quyền xem do backend quyết định (401/403/200). Đổi ví, mạng hoặc API sẽ xóa phiên và dữ liệu riêng tư. Khi API lỗi, giao diện báo lỗi, không thay số liệu bằng mẫu.

Chi tiết cách chạy, SHA-256, quyền và giới hạn: [L04 handoff](../docs/Lam/l04_ipfs_hub_analytics.md) · [L04 validation](../reports/Lam/l04_frontend_validation.md).

## MetaMask và giao dịch thật — L05

Chạy backend Q05 theo `backend/api/README.md`; dùng deployment Q06 tương ứng với RPC đang chạy. Đặt `NEXT_PUBLIC_API_BASE_URL` nếu API khác `http://127.0.0.1:8000`. Local dùng Hardhat chain 31337; Sepolia dùng chain 11155111. Ganache GUI không phải yêu cầu của frontend này.

1. Kết nối MetaMask, chọn mạng, ký xác thực nonce (không tốn gas).
2. Xem trước giao dịch: ví, contract, mạng, số tiền, gas, APR và CID nếu vay.
3. Nếu thiếu allowance, chuẩn bị và ký approve riêng; sau receipt, chuẩn bị lại thao tác chính.
4. Ký thao tác chính trong MetaMask. Ứng dụng chỉ báo thành công sau receipt và xác nhận Q05.
5. Nếu đã có hash nhưng chưa xác nhận, dùng **Kiểm tra lại** trong cùng phiên để tránh gửi trùng.

PDF thỏa thuận vay được mã hóa/lưu IPFS trước borrow; CID được đối chiếu với sự kiện sau receipt. Phiên và nhật ký giao dịch chỉ giữ trong bộ nhớ, mất khi tải lại trang. Không nhập khóa riêng hoặc seed phrase vào DApp/backend. Tua thời gian và chỉnh giá chỉ bật với Admin trên local.

Kiểm tra tích hợp cô lập: từ repo root chạy `python scripts/verify_l05_frontend_api.py` (cần môi trường Python backend và uvicorn). Ví ký/RPC trong kiểm tra là test double, không phải tiện ích MetaMask hoặc giao dịch Sepolia.

Chi tiết vận hành và kiểm tra MetaMask thủ công: [L05 handoff](../docs/Lam/l05_metamask_web3.md) · [L05 validation](../reports/Lam/l05_frontend_validation.md).
