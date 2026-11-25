# Hướng dẫn Thiết lập Môi trường Blockchain, Web3.py, MetaMask & Sepolia Testnet (Q01)

Tài liệu này chuẩn hóa toàn bộ hạ tầng phát triển và kiểm thử cho 4 thành viên nhóm **IS355.R11 – DeFi Lending DApp** (Hùng, Hiếu, Quân, Lâm), đảm bảo mọi thành viên chạy chung một cấu hình mạng Local (`Chain ID = 31337`) và sẵn sàng triển khai nghiệm thu bắt buộc trên **Ethereum Sepolia Testnet (`Chain ID = 11155111`)**.

---

## 1. Yêu cầu công cụ cài đặt

- **Node.js**: `>= 18.x` (khuyến nghị `20.x` hoặc `22.x` LTS) và `npm`.
- **Python**: `>= 3.10` (`3.10` hoặc `3.11`).
- **Trình duyệt + Ví Web3**: Google Chrome / Brave / Edge có cài extension **MetaMask**.
- **Git**: Đã cấu hình tài khoản GitHub của nhóm.

---

## 2. Khởi tạo nhanh môi trường dự án (Chạy lần đầu)

### Bước 2.1. Tạo file biến môi trường `.env`
Tại thư mục gốc dự án:

```powershell
Copy-Item .env.example .env
```

> **Quy tắc bảo mật bắt buộc**:
> - File `.env` đã được chặn trong `.gitignore` — **tuyệt đối không commit** `.env`, Pinata API Secret hoặc Private Key thật lên GitHub.
> - **Không dùng chung ví**: Các Private Key mặc định của Hardhat chỉ dùng trên mạng Local (`31337`). Mạng Sepolia Testnet phải dùng một ví test mới tạo riêng biệt (chỉ chứa SepoliaETH, không chứa tài sản thật).

### Bước 2.2. Cài đặt thư viện Smart Contract (Hardhat + OpenZeppelin)

```powershell
npm install
```

Dự án cố định **Solidity `0.8.24`** (tương thích `^0.8.20`) và **`@openzeppelin/contracts` `^5.0.2`** để Hùng (`H01`, `H02`) và Hiếu (`HI01`–`HI05`) sử dụng thống nhất.

### Bước 2.3. Cài đặt môi trường Python (FastAPI + Web3.py)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

---

## 3. Vận hành mạng Blockchain Local (`Chain ID = 31337`)

### Bước 3.1. Bật Hardhat Local Node
Mở một cửa sổ Terminal riêng và chạy một trong hai lệnh:

```powershell
npm run node
# Hoặc trên Windows:
.\scripts\start_local_node.bat
```

Node sẽ lắng nghe cố định tại `http://127.0.0.1:8545` với `Chain ID = 31337` và khởi tạo sẵn **10 ví test (mỗi ví `10,000 ETH`)** từ cùng một mnemonic cố định.

Để in lại danh sách 10 ví kèm số dư bất kỳ lúc nào:

```powershell
npm run accounts
```

### Bước 3.2. Danh sách 10 ví Local Test cố định (CHỈ DÙNG LOCAL)

Mnemonic cố định: `test test test test test test test test test test test junk`

| STT | Vai trò thống nhất trong nhóm / Demo | Địa chỉ ví (`Address`) | Private Key (Chỉ import MetaMask khi test Local) |
|---|---|---|---|
| `#0` | **Deployer / Admin / System Seed** | `0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266` | `0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80` |
| `#1` | **Lender A** *(Gửi 1000 MyUSDT ở Demo)* | `0x70997970C51812dc3A010C7d01b50e0d17dc79C8` | `0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d` |
| `#2` | **Borrower A** *(Thế chấp & Vay 500 MyUSDT)* | `0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC` | `0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a` |
| `#3` | **Lender B** *(Nhận chuyển nhượng Position NFT)* | `0x90F79bf6EB2c4f870365E785982E1f101E93b906` | `0x7c852118294e51e653712a81e05800f419141751be58f605c371e15141b007a6` |
| `#4` | **Liquidator / Keeper** *(Gọi `liquidate()`)* | `0x15d34AAf54267DB7D7c367839AAf71A00a2C6A65` | `0x47e179ec197488593b187f80a00eb0da91f1b9d0b13f8733639f19c30a34926a` |
| `#5` | **Borrower B** *(Test chặn quyền RBAC 403 IPFS)* | `0x9965507D1a55bcC2695C58ba16FB37d819B0A4dc` | `0x8b3a350cf5c34c9194ca85829a2df0ec3153be0318b5e2d3348e872092edffba` |
| `#6` | Ví test cá nhân – **Hùng** | `0x976EA74026E726554dB657fA54763abd0C3a0aa9` | `0x92db14e403b83dfe3df233f83dfa3a0d7096f21ca9b0d6d6b8d88b2b4ec1564e` |
| `#7` | Ví test cá nhân – **Hiếu** | `0x14dC79964da2C08b23698B3D3cc7Ca32193d9955` | `0x4bbbf85ce3377467afe5d46f804f221813b2bb87f24d81f60f1fcdbf7cbf4356` |
| `#8` | Ví test cá nhân – **Quân** | `0x23618e81E3f5cdF7f54C3d65f7FBc0aBf5B21E8f` | `0xdbda1821b80551c9d65939329250298aa3472ba22feea921c0cf5d620ea67b97` |
| `#9` | Ví test cá nhân – **Lâm** | `0xa0Ee7A142d267C1f36714E4a8F75612F20a79720` | `0x2a871d0798f97d79848a013d4936a73bf4cc922c825d33c1cf7073dff6d409c6` |

---

## 4. Hướng dẫn cấu hình Ví MetaMask

### 4.1. Thêm mạng Hardhat Local vào MetaMask
1. Mở MetaMask → bấm biểu tượng chọn mạng (góc trên bên trái) → **Add a custom network**.
2. Điền chính xác các thông số:
   - **Network name**: `Hardhat Localhost 31337`
   - **Default RPC URL**: `http://127.0.0.1:8545`
   - **Chain ID**: `31337`
   - **Currency symbol**: `ETH`
   - **Block explorer URL**: *(để trống)*
3. Bấm **Save**.
4. Import ví test: Mở menu tài khoản → **Add account or hardware wallet** → **Import account** → dán Private Key của ví `#1` (Lender A) và `#2` (Borrower A) ở bảng trên → kiểm tra số dư hiển thị **`10,000 ETH`**.

> **Mẹo xử lý lỗi Nonce khi khởi động lại Hardhat Node**: Mỗi lần tắt/bật lại `npm run node`, chuỗi Local quay về Block `0` nên MetaMask có thể báo lỗi `Nonce too high`. Cách xử lý trong 3 giây: Vào **MetaMask → Settings → Advanced → Clear activity tab data**.

---

### 4.2. Cấu hình mạng Ethereum Sepolia Testnet (BẮT BUỘC)

Theo Rubric **Tiêu chí 1**, việc triển khai và kiểm thử hợp đồng trên mạng **Sepolia Testnet** là **bắt buộc** (không được thay thế bằng bản chạy Local).

#### Thông số mạng Sepolia trên MetaMask
1. Trong MetaMask, bật tùy chọn **Show test networks** để chọn sẵn mạng **Sepolia**, hoặc cấu hình thủ công:
   - **Network name**: `Sepolia Testnet`
   - **RPC URL**:
     - Public RPC sẵn dùng: `https://ethereum-sepolia-rpc.publicnode.com`
     - Hoặc RPC riêng từ **Alchemy** (`https://eth-sepolia.g.alchemy.com/v2/<API_KEY>`) / **Infura** (`https://sepolia.infura.io/v3/<PROJECT_ID>`) để ổn định tốc độ cao.
   - **Chain ID**: `11155111`
   - **Currency symbol**: `SepoliaETH`
   - **Block explorer URL**: `https://sepolia.etherscan.io`

#### Tạo ví Testnet riêng & nhận SepoliaETH miễn phí (Faucet)
1. Trong MetaMask, bấm **Add account → Create a new account** và đặt tên `IS355 Sepolia Test Wallet` (tách biệt hoàn toàn với ví cá nhân thật và ví Hardhat Local).
2. Nhận `SepoliaETH` thử nghiệm từ một trong các Faucet uy tín:
   - **Google Cloud Web3 Faucet**: https://cloud.google.com/application/web3/faucet/ethereum/sepolia
   - **Alchemy Sepolia Faucet**: https://www.alchemy.com/faucets/ethereum-sepolia
   - **Infura Sepolia Faucet**: https://www.infura.io/faucet/sepolia
   - **Sepolia PoW Faucet**: https://sepolia-faucet.pk910.de/
3. Điền `SEPOLIA_RPC_URL` và `SEPOLIA_DEPLOYER_PRIVATE_KEY` (của ví `IS355 Sepolia Test Wallet`) vào file `.env` cục bộ khi cần chạy lệnh deploy testnet. Hệ thống trong `hardhat.config.js` và `backend/config/settings.py` đã tích hợp sẵn chốt chặn tự động từ chối nếu phát hiện nhầm Private Key của Hardhat Local.

---

## 5. Kế hoạch Triển khai & Kiểm thử Sepolia thống nhất cho cả nhóm

| Giai đoạn | Phụ trách | Nội dung thực hiện trên Local vs. Sepolia | Sản phẩm / Minh chứng lưu trữ |
|---|---|---|---|
| **GĐ1 (`Q01`)** | Quân | Chuẩn hóa `hardhat.config.js` & `backend/config/blockchain.py` hỗ trợ song song `local` (`31337`) và `sepolia` (`11155111`). | `.env.example`, `hardhat.config.js`, kết quả `verify_env.py --all`. |
| **GĐ1–GĐ3 (`H01`–`HI05`)** | Hùng, Hiếu | Phát triển và unit test 7 hợp đồng trên mạng Local (`MyUSDT`, `CollateralNFT`, `CollateralReceiptNFT`, `DebtToken`, `LendingPositionNFT`, `PriceOracle`, `LendingPool`). | Bộ hợp đồng Solidity biên dịch `0 warnings`; các hàm tua giờ/mock giá chỉ mở cho môi trường Local. |
| **GĐ4 (`Q06`)** | Quân | Viết script `scripts/deploy_sepolia.*` (tách biệt khỏi `deploy_and_seed.py` của Local) để deploy toàn bộ 7 hợp đồng lên Sepolia. | Cập nhật địa chỉ + `txHash` vào `deployments/sepolia.json` và `backend/config/contracts.json`. |
| **GĐ4 (`HI06`)** | Hiếu, Quân | Thực hiện chuỗi giao dịch **Smoke-Test thật trên Sepolia**: Faucet/Mint `MyUSDT` → `depositLender` → `depositCollateral` → `borrow` → `repay` → đọc trạng thái on-chain. | Lưu `contract address`, `txHash`, link `https://sepolia.etherscan.io/tx/...`, receipt và ảnh chụp màn hình phục vụ Báo cáo. |

---

## 6. Kiểm tra nghiệm thu `Q01` (Dành cho cả 4 thành viên)

Sau khi bật `npm run node` ở Terminal 1, mở Terminal 2 và chạy:

```powershell
# 1. Kiểm tra tự động cả Local Hardhat (31337) và Sepolia Testnet (11155111)
python scripts/verify_env.py --all

# 2. Khởi chạy thử FastAPI Backend
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

Sau đó mở trình duyệt kiểm tra:
- Swagger UI: `http://127.0.0.1:8000/docs`
- Trạng thái mạng Local: `http://127.0.0.1:8000/api/network-status?network=local` (`connected: true`, `actual_chain_id: 31337`)
- Trạng thái mạng Sepolia: `http://127.0.0.1:8000/api/network-status?network=sepolia` (`connected: true`, `actual_chain_id: 11155111`)
