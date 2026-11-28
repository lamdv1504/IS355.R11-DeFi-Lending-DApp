# L05 — MetaMask, Web3 và phiên ví dùng chung

Phụ trách: Lâm · Giai đoạn 4 · Nhánh `feature/lam-l05-metamask-web3`.

## Đối chiếu kế hoạch và bàn giao

Đã đọc dòng L05 trong `Kế-hoạch-Blockchain.xlsx`. Phụ thuộc L02, L03, L04, Q05, Q06 đều có trong repo tại base `a5fde2a`: bốn màn hình, API auth/prepare/confirm/IPFS/pool/demo, ABI và manifest local/Sepolia. Không cần tự tạo file thay cho thành viên khác.

L05 nối các màn hình hiện có với ví/API. Kịch bản E2E đầy đủ với tiện ích MetaMask và mạng triển khai thuộc phần kiểm tra tiếp theo; báo cáo không coi test double là giao dịch thật.

## Chạy và cấu hình

1. Chuẩn bị RPC/deployment theo [bàn giao Q06](../Quan/q06_deploy_and_sepolia_handoff.md), dùng đúng manifest với chain đang chạy. Local: Hardhat 31337, RPC `http://127.0.0.1:8545`; Sepolia: 11155111. Nếu khởi động lại/reset local chain, cần triển khai và đồng bộ registry lại theo Q06.
2. Cấu hình backend theo [Q05](../Quan/q05_fastapi_rbac_handoff.md): `AUTH_TOKEN_SECRET` đủ dài, `AUTH_DOMAIN=localhost`, `DOCUMENT_AES_KEY_HEX`, IPFS, RPC và CORS cho origin frontend. Admin/Lender do cấu hình backend quyết định.
3. Khởi động backend theo [README API](../../backend/api/README.md).
4. Trong `frontend`, chạy `npm ci`, `npm run dev`; mở `http://localhost:3000`. Khi dùng preview, thêm `http://127.0.0.1:3000` vào CORS nếu cấu hình chưa có.
5. API mặc định `http://127.0.0.1:8000`. Có thể đặt `NEXT_PUBLIC_API_BASE_URL` khi build hoặc đổi bằng nút cài đặt API. Origin từ xa phải dùng HTTPS; đổi API sẽ xóa phiên.
6. Dùng MetaMask có ETH thử nghiệm để trả gas. Kết nối và chọn mạng ở thanh trên. Với local chưa có trong MetaMask, ứng dụng đề nghị thêm chain 31337; Sepolia dùng cấu hình mạng có sẵn của ví.

Không cần Ganache GUI cho cấu hình Hardhat này. Frontend không nhận khóa riêng/seed phrase; mọi giao dịch do MetaMask ký.

## Luồng thao tác

- **Phiên ví:** request accounts → kiểm tra chain → nonce Q05 → `personal_sign` đúng bytes UTF-8 → kiểm tra signer tại frontend → verify Q05. Token, role và thời hạn lấy từ backend, chỉ giữ trong bộ nhớ.
- **Cho vay:** đọc Pool/snapshot/NFT đang sở hữu. Gửi vốn, rút vốn/lãi, chuyển NFT vị thế đều có báo giá trước khi ký.
- **Thế chấp:** chọn ERC-20 hoặc CollateralNFT thực sự thuộc ví; không cố định token ID. Token ID 0 hợp lệ.
- **Vay:** mô tả tài sản + số tiền → tạo/mã hóa PDF và nhận CID với trạng thái `PRE_BORROW_UNSIGNED` → prepare borrow(amount,CID) + gas/APR/lãi 30 ngày/LTV/HF → xem trước → MetaMask ký → chờ receipt → Q05 đối chiếu tx/event và gắn CID. Link hồ sơ dùng Next navigation để giữ phiên ví.
- **Trả nợ:** trả một phần hoặc tất toán. Tất toán đọc lại nợ và thêm 0,01 MyUSDT đệm; contract thu đúng nợ thực tế và tự trả tài sản.
- **Thanh lý:** nhập ví mục tiêu, đọc HF và nợ; chỉ cho chuẩn bị khi HF < 1 và có nợ. Người thanh lý ký giao dịch riêng.
- **Approve:** nếu thiếu allowance, chuẩn bị/kiểm tra/ký approve riêng. Sau xác nhận, người dùng chuẩn bị lại thao tác chính để lấy gas mới. Trả nợ/thanh lý có đệm allowance 1 bps + 0,01 MyUSDT để hạn chế phải cấp quyền lại vì lãi.
- **IPFS/Analytics:** dùng chung mạng và phiên ví; backend quyết định quyền đọc/tạo. Dữ liệu mẫu chỉ mở khi chủ động chọn, không thay dữ liệu khi API lỗi.

Demo faucet nhận 1.000 MyUSDT là giao dịch cần ký. Tua 30/60 ngày dùng RPC Hardhat; chỉnh Oracle về 60%/100% là giao dịch ký riêng. Hai thao tác thời gian/giá chỉ bật cho Admin trên local. Giá 60% không tự gửi thanh lý; HF thực tế phụ thuộc khoản vay.

## Đối chiếu giao dịch và xử lý lỗi

Frontend kiểm tra account, chain, địa chỉ contract từ registry, value=0, calldata ABI chính xác, token/spender/amount của allowance và số học gas trước khi mở MetaMask. Quote tối đa 2 phút; không chuyển giá trị WAD sang Number để quyết định giao dịch.

Chỉ báo thành công khi receipt status=1 và Q05 confirm khớp giao dịch; borrow còn kiểm tra CID, principal, borrower, chain và txHash trong binding. Receipt revert không được báo thành công.

Nếu đã có hash nhưng API/receipt chưa xác nhận, giao dịch giữ trạng thái chờ. **Kiểm tra lại** chỉ truy vấn và confirm hash cũ, không phát lại giao dịch. Retry yêu cầu đúng ví, mạng và API ban đầu. Phiên đang có giao dịch chờ bị chặn gửi thao tác mới cho đến khi đối chiếu xong.

Đổi account/chain/API/chế độ hoặc hết hạn/401 sẽ hủy request cũ và xóa session, quote, CID/private data; response đến muộn không được ghi lại. Sau receipt, dữ liệu đọc được làm mới ngay và sau đó mỗi 10 giây. Sepolia quét từ block triển khai sớm nhất của bộ contract để không bỏ sót NFT mint trước Pool.

## Giới hạn cần nhớ

- Phiên và nhật ký pending chỉ nằm trong bộ nhớ. Reload/đóng tab mất chúng; lưu txHash để đối chiếu trước khi tự gửi lại. Intent backend có TTL và có thể mất khi backend khởi động lại. Không có chức năng khôi phục pending bền vững trong L05.
- Lỗi API hiển thị rõ; không giả số liệu bằng 0 hoặc tự chuyển về mẫu. Số liệu cũ cùng scope có thể giữ kèm thông báo làm mới thất bại.
- Giao dịch đang chờ/replaced/dropped cần kiểm tra trong ví/explorer; không có tăng tốc/cancel transaction tự động.
- Đây là mạng thử nghiệm và mock Oracle. UI chặn chỉnh giá/tua thời gian trên Sepolia.
- Kiểm thử cô lập dùng IPFS local store và test signer/RPC; chưa chứng minh tiện ích MetaMask, RPC công khai hoặc IPFS pinning công khai hoạt động trên máy người dùng.

## Checklist MetaMask thủ công

1. Khách xem Pool; kết nối/ký xác thực, chuyển bốn trang vẫn giữ đúng phiên.
2. Chấp thuận approve rồi gửi vốn; nhận NFT vị thế, rút một phần, chuyển NFT và kiểm tra quyền của ví mới.
3. Thế chấp NFT/Token đúng ví; vay trong LTV; xác minh PDF có trước giao dịch và CID khớp binding sau receipt.
4. Trả một phần/tất toán; kiểm tra nợ/lãi và mở khóa tài sản.
5. Từ chối chữ ký/giao dịch; đổi account/chain trong lúc chờ; không xuất hiện dữ liệu riêng tư của ví trước.
6. Admin local nhận token, tua 30/60 ngày, giảm giá 40%, đọc HF rồi ký thanh lý riêng. Trên Sepolia time/price luôn tắt.
7. Ngắt API sau broadcast rồi kết nối lại, bấm Kiểm tra lại; chỉ có một giao dịch được gửi.
8. Chủ sở hữu tải PDF; khách/ví khác bị 401/403; Analytics đọc đúng mạng và ví.

## Kiểm tra tự động

```powershell
cd frontend
npm test
npm run typecheck
npm run lint
npm run build
cd ..
python scripts/verify_l05_frontend_api.py
```

Báo cáo: [L05 validation](../../reports/Lam/l05_frontend_validation.md). Kiểm tra HTTP tạo ví thử ngẫu nhiên trong tiến trình test; không cần tài khoản hoặc khóa của người dùng.
