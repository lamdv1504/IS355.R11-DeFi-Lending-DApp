# Hệ thống tín dụng và cho vay phi tập trung (DeFi Lending DApp)

## 1. Giới thiệu dự án

**DeFi Lending DApp** là đồ án xây dựng ứng dụng tín dụng và cho vay phi tập trung (Decentralized Finance – DeFi) trên nền tảng Blockchain Ethereum. Hệ thống mô phỏng hoạt động kết nối giữa người có nguồn vốn nhàn rỗi và người có nhu cầu vay vốn thông qua các hợp đồng thông minh (Smart Contract), hạn chế sự phụ thuộc vào đơn vị trung gian.

Thay vì gửi tiền và vay vốn thông qua một tổ chức tài chính truyền thống, người dùng có thể tương tác trực tiếp với ứng dụng bằng ví Web3 như MetaMask. Người cho vay gửi token vào quỹ thanh khoản (Liquidity Pool) để nhận lãi; người đi vay gửi tài sản số làm tài sản thế chấp và vay token trong giới hạn cho phép.

Dự án hướng đến việc minh họa cách Blockchain có thể hỗ trợ **tài chính toàn diện (Financial Inclusion)**, giúp mở rộng khả năng tiếp cận nguồn vốn thông qua tài sản thế chấp số và các quy tắc minh bạch, có thể kiểm chứng trên Blockchain.

## 2. Mục tiêu dự án

- Xây dựng Smart Contract bằng Solidity để quản lý quỹ thanh khoản, tài sản thế chấp và vòng đời khoản vay.
- Phát triển giao diện DApp giúp người dùng kết nối ví MetaMask, đọc dữ liệu Blockchain và gửi giao dịch.
- Tích hợp Web3.py để Backend có thể tương tác với Smart Contract.
- Tạo và sử dụng token ERC-20 làm tài sản cho vay, đồng thời ứng dụng NFT để đại diện cho biên nhận tài sản thế chấp hoặc vị thế cho vay.
- Tích hợp IPFS để lưu trữ và truy xuất hồ sơ, thỏa thuận vay và dữ liệu kiểm toán.
- Kiểm thử các nghiệp vụ chính trên mạng local và triển khai hợp đồng lên Sepolia Testnet.

## 3. Các chức năng chính

### 3.1. Quỹ thanh khoản – Lending

Người cho vay (Lender) có thể gửi token MyUSDT vào Liquidity Pool. Hệ thống ghi nhận số tiền đã gửi, số dư và phần lãi phát sinh theo cơ chế lãi suất được cấu hình. Người cho vay có thể yêu cầu rút vốn khi quỹ có đủ thanh khoản và việc rút tiền không ảnh hưởng đến nghĩa vụ của các khoản vay đang hoạt động.

### 3.2. Thế chấp và vay vốn – Borrowing

Người đi vay (Borrower) chuyển tài sản được hệ thống chấp nhận vào Smart Contract làm tài sản thế chấp. Dựa trên giá trị tài sản và tỷ lệ cho vay trên giá trị tài sản thế chấp (Loan-to-Value – LTV), hệ thống xác định hạn mức vay tối đa.

Các nghiệp vụ cốt lõi gồm:

- `depositCollateral()`: Nộp tài sản thế chấp vào hợp đồng.
- `borrow()`: Kiểm tra hạn mức và giải ngân token từ Liquidity Pool.
- `repay()`: Hoàn trả tiền gốc và lãi của khoản vay.
- Rút tài sản thế chấp: Chỉ được thực hiện khi khoản vay đã đáp ứng điều kiện hoàn trả.

### 3.3. Theo dõi rủi ro và thanh lý

DApp hiển thị thông tin khoản vay và **Health Factor** để người dùng theo dõi mức độ an toàn của tài sản thế chấp. Khi giá trị tài sản thế chấp giảm hoặc khoản nợ tăng khiến vị thế không còn đáp ứng ngưỡng an toàn, khoản vay có thể đủ điều kiện thanh lý theo quy tắc của Smart Contract.

### 3.4. Token ERC-20 và NFT

- **MyUSDT (ERC-20):** Token ổn định giả lập, được sử dụng làm đơn vị tiền tệ trong các nghiệp vụ gửi và vay.
- **Debt Token:** Đại diện hoặc hỗ trợ theo dõi nghĩa vụ nợ của người vay.
- **Collateral Receipt NFT:** Biên nhận NFT đại diện cho tài sản đã được đưa vào thế chấp.
- **Lending Position NFT:** Đại diện cho vị thế cho vay và hỗ trợ minh họa việc chuyển nhượng vị thế giữa các người cho vay.

### 3.5. Lưu trữ hồ sơ với IPFS

Hệ thống sử dụng IPFS để lưu trữ và truy xuất các nhóm dữ liệu liên quan đến hoạt động cho vay:

- **Loan Agreement:** Thỏa thuận vay dưới dạng PDF.
- **Credit Report:** Thông tin tóm tắt lịch sử tín dụng on-chain dưới dạng metadata JSON.
- **Audit Logs:** Nhật ký ghi nhận biến động lãi suất và các hoạt động liên quan dưới dạng dữ liệu có cấu trúc.

Sau khi tải dữ liệu lên IPFS, hệ thống lưu mã định danh nội dung (CID) để phục vụ việc truy xuất. Các tài liệu nhạy cảm cần được mã hóa và áp dụng cơ chế phân quyền truy cập phù hợp trước khi chia sẻ.

### 3.6. Giao diện DApp và kết nối ví

Người dùng thao tác trên giao diện web và kết nối ví MetaMask để xác thực, ký giao dịch. Giao diện dự kiến cung cấp:

- **Lending Dashboard:** Theo dõi số tiền đã gửi, lãi suất và tiền lãi dự tính.
- **Borrowing Console:** Theo dõi tài sản thế chấp, dư nợ, hạn mức vay và Health Factor.
- **Wallet & Transaction:** Hiển thị địa chỉ ví, trạng thái giao dịch và phí gas ước tính.
- **Loan Documents:** Xem hoặc tải hồ sơ vay thông qua CID trên IPFS.

## 4. Quy trình hoạt động minh họa

1. Người cho vay gửi **1.000 MyUSDT** vào Liquidity Pool.
2. Người đi vay nộp tài sản số làm tài sản thế chấp.
3. Smart Contract kiểm tra giá trị tài sản, LTV và thanh khoản hiện có trước khi cho vay.
4. Người đi vay thực hiện vay **500 MyUSDT** nếu đáp ứng các điều kiện của hệ thống.
5. Khoản nợ được theo dõi và tính lãi theo thời gian.
6. Người đi vay hoàn trả tiền gốc và lãi; sau khi đáp ứng điều kiện, tài sản thế chấp được hoàn trả.
7. Người cho vay có thể rút lại khoản tiền đã gửi khi Liquidity Pool đáp ứng đủ điều kiện thanh khoản.

*Các con số trên là kịch bản minh họa. Hạn mức vay thực tế phụ thuộc vào giá trị tài sản thế chấp, LTV được cấu hình và số dư khả dụng của quỹ.*

## 5. Công nghệ sử dụng

| Thành phần | Công nghệ | Vai trò |
|---|---|---|
| Blockchain | Ethereum | Nền tảng triển khai Smart Contract |
| Smart Contract | Solidity | Xử lý nghiệp vụ cho vay, trả nợ, thế chấp và token |
| Môi trường phát triển | Hardhat | Biên dịch, triển khai và kiểm thử hợp đồng |
| Kết nối ví | MetaMask | Kết nối ví và ký giao dịch |
| Backend | Python, FastAPI, Web3.py | Xây dựng API và tương tác Blockchain |
| Frontend | React, Vite | Xây dựng giao diện DApp |
| Lưu trữ phi tập trung | IPFS | Lưu trữ và truy xuất hồ sơ |
| Mạng kiểm thử | Hardhat Local Network, Sepolia | Kiểm thử và triển khai thử nghiệm |

## 6. Cấu trúc thư mục

```text
DeFi-Lending-DApp/
├── README.md
├── contracts/                 # Các hợp đồng thông minh Solidity
│   ├── tokens/                # ERC-20, Debt Token và NFT
│   ├── interfaces/            # Interface dùng chung
│   ├── libraries/             # Thư viện hỗ trợ
│   └── mocks/                 # Contract giả lập để kiểm thử
├── scripts/                   # Script triển khai và tương tác
├── deployments/               # Thông tin triển khai local và Sepolia
├── backend/                   # Backend API và Web3.py
│   ├── api/                   # Các API endpoint
│   ├── schemas/               # Schema dữ liệu
│   ├── services/              # Xử lý nghiệp vụ
│   ├── security/              # Xác thực và bảo mật
│   └── config/                # Cấu hình Backend
├── frontend/                  # Giao diện React
│   ├── public/                # Tài nguyên tĩnh
│   └── src/
│       ├── components/        # Component giao diện
│       ├── pages/             # Các trang chức năng
│       ├── hooks/             # Custom React hooks
│       ├── services/          # Kết nối API và Smart Contract
│       └── assets/            # Hình ảnh và tài nguyên
├── src/                       # Module Python dùng chung
│   ├── documents/             # Xử lý hồ sơ vay
│   └── ipfs/                  # Tích hợp IPFS
├── ipfs_storage/              # Dữ liệu mẫu và metadata
├── tests/                     # Kiểm thử hệ thống
├── docs/                      # Tài liệu thiết kế
└── reports/                   # Báo cáo và minh chứng
```

## 7. Phạm vi thực hiện

Đây là dự án học thuật nhằm nghiên cứu và minh họa mô hình DeFi Lending. MyUSDT là token giả lập phục vụ thử nghiệm; các giao dịch được thực hiện trên mạng local hoặc testnet. Tài sản, dữ liệu và khoản vay trong demo không đại diện cho tiền hoặc tài sản có giá trị thực tế.

Dự án không phải nền tảng cung cấp dịch vụ tài chính hay sản phẩm đầu tư. Các chức năng được hoàn thiện và đánh giá thông qua quá trình phát triển, kiểm thử và trình diễn theo yêu cầu đồ án.

## 8. H01 - MyUSDT (Hùng)

[Thông số Token, Faucet, unit test và hướng dẫn deploy/bàn giao](docs/h01_myusdt_handoff.md).
