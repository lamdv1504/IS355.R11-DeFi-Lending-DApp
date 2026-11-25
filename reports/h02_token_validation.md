# H02 – Kết quả kiểm thử Token/NFT

Đây là log tóm tắt các kiểm tra đã chạy trong phiên triển khai H02 của Hùng.
Mã nguồn test: [H02_Tokens.test.js](../tests/H02_Tokens.test.js).
Các giao dịch trong unit test dùng mạng Hardhat tạm và test caller,
không phải giao dịch nghiệp vụ của LendingPool HI02.

## Lệnh và kết quả

| Kiểm tra | Kết quả |
|---|---|
| `npm run compile` | 35 Solidity files biên dịch thành công, EVM Paris, không có cảnh báo |
| `npm test` | **88 passing**: H02 52, HI01 13, H01 23 |
| `python -B -m pytest -q -p no:cacheprovider` | **11 passed** |
| `npm ci --dry-run --ignore-scripts --no-audit --no-fund` | Lockfile hợp lệ; giữ package tùy chọn cho các nền tảng |
| `npm run deploy:myusdt` | Deploy/seed H01 trên node local mới bằng OpenZeppelin 5.0.2 |
| `npm run deploy:h02` | Deploy 4 token H02 và xuất 4 ABI implementation + 4 interface |
| `npm run verify:h02` | Bytecode, receipt, owner, registry, ERC165 IDs và 10 ví H01 khớp |
| Web3.py contract construction | Nạp thành công ABI/bytecode của 4 token H02 |
| `node --check` | Cú pháp 3 script H02 và file unit test hợp lệ |

## Log nghiệp vụ được xác nhận trong unit test

- `mints exactly the principal and burns partial/full repayments through onlyPool`:
  mint 500 DebtToken cho Borrower, burn 200 còn 300, burn 300 còn 0;
  kiểm tra DebtMinted / DebtBurned và totalSupply.
- `moves ownerOf from Lender A to B and clears the previous approval`:
  mint vị thế 1,000 MyUSDT, A chuyển cho B, ownerOf đổi thành B,
  approval cũ bị xóa và A không chuyển tiếp được.
- `burns for the current owner after a transfer, not the original lender`:
  Pool caller burn vị thế sau chuyển; PositionBurned ghi ví B.
- `blocks owner transfers, both safe-transfer overloads and approved operators`:
  Receipt không chuyển được dù Borrower/operator có approval.
- `burns and preserves inactive history on repayment / liquidation`:
  settlement đặt inactive, burn Receipt, xóa activeReceiptOf; đọc được lịch sử.
- `rejects recovery by the former owner or operator after custody transfer`:
  NFT tài sản đang thuộc test caller không thể bị Borrower/operator/admin tự lấy lại.
- Cả ba token kiểm tra owner-only bind, zero/EOA rejection và không rebind.
- Các function/event signatures được so với interface chuẩn HI01 bằng ABI.
- Safe mint từ chối non-receiver contract và rollback state/counter/active receipt.

## Bằng chứng deploy local

Xem [h02_local_verification.json](h02_local_verification.json) và
[deployments/localhost.json](../deployments/localhost.json) để lấy địa chỉ,
txHash, blockNumber, owner và runtimeCodeHash. Không có CID hoặc địa chỉ Pool giả.

Ba token Pool-controlled hiện chưa bind: `lendingPool = address(0)`,
trạng thái `AWAITING_HI02_POOL`. Test caller không có trong registry.
Báo cáo xác minh chỉ có hiệu lực với node local hiện tại; restart node cần deploy lại.

## Phần chờ đầu ra Hiếu (HI02/HI03)

- Pool thật khóa tài sản rồi mint Receipt trong depositCollateral.
- borrow/repay/liquidate mint/burn DebtToken đúng số gốc trong giao dịch nghiệp vụ.
- Pool chặn trả tài sản khi còn nợ; trả/thu giữ tài sản và settle Receipt đúng lúc.
- withdrawLender trả gốc + lãi cho ownerOf hiện tại sau khi Position NFT chuyển A → B.
- Kiểm thử cả chuỗi gửi → thế chấp → vay → trả → rút với tiền và lãi thực tế.

Những mục này không được đánh dấu đã chạy từ unit test token.
Hiếu nhận [hướng dẫn cấu hình và vòng đời H02](../docs/h02_token_nft_handoff.md)
để tích hợp. Không cần tạo implementation LendingPool thay Hiếu trong H02.
