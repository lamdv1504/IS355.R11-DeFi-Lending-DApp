# H01 – MyUSDT ERC-20 (Hùng, Giai đoạn 1)

## Phạm vi và đầu vào

H01 sử dụng phần Q01 của Quân đã có: `hardhat.config.js`, `package-lock.json`,
`.env.example`, mạng localhost và danh sách 10 ví test.
Xem [hướng dẫn môi trường Q01](q01_environment_and_metamask_guide.md) để cài đặt và import ví.

Đầu ra: MyUSDT.sol, unit test, script deploy/seed, ABI + bytecode, địa chỉ contract
và danh sách tài khoản có số dư token. H01 không cần LendingPool của Hiếu
hoặc giao diện của Lâm để kiểm thử ERC-20. Tích hợp Pool thực hiện ở HI02;
triển khai toàn hệ thống trên Sepolia thuộc Q06 theo hướng dẫn bàn giao Q01.

## Thông số Token & Faucet

| Thông số | Giá trị |
|---|---|
| Tên / ký hiệu | `MyUSDT` / `MyUSDT` |
| Chuẩn | OpenZeppelin ERC-20, kế thừa Ownable |
| Decimals | `18` (mặc định của ERC20) |
| Compiler Q01 | Solidity `0.8.24`, optimizer 200 runs, EVM Paris |
| Nguồn cung ban đầu | `1,000,000 MyUSDT`, cấp hết cho deployer |
| Owner ban đầu | Deployer |
| Faucet | `faucet(address to, uint256 amount)` |
| Quyền gọi faucet | Bất kỳ tài khoản nào, có thể nhận cho địa chỉ khác |
| Giới hạn | `0 < amount <= 1,000 * 10^18` mỗi lần gọi |
| Địa chỉ nhận | Phải khác địa chỉ zero |
| Tổng cung | Tăng theo lượng mint từ faucet |
| Sự kiện | `Transfer`, `Approval`, `FaucetUsed(caller, to, amount)` |

Giới hạn faucet áp dụng cho từng giao dịch, không có cooldown hoặc hạn mức
tích lũy theo ví; có thể gọi nhiều lần. Đây là cơ chế cấp token test theo H01.
Ownable quản lý quyền sở hữu; faucet vẫn công khai sau khi chuyển ownership.
Contract không cung cấp hàm mint quản trị riêng.

`approve`, `allowance`, `transfer`, `transferFrom` dùng trực tiếp triển khai
ERC-20 của OpenZeppelin để giữ đúng hành vi chuẩn.
Mọi lượng token ở ABI dùng base unit: `1 MyUSDT = 10^18 base units`.

## Biên dịch, kiểm thử và xuất ABI

Chạy tại thư mục gốc:

```powershell
npm ci
npm run compile
npm run test:myusdt
npm run export:myusdt
```

- Artifact Hardhat: `artifacts/contracts/tokens/MyUSDT.sol/MyUSDT.json`.
- Bản bàn giao được lưu trong Git: `deployments/abi/MyUSDT.json`.
- JSON bàn giao chứa `abi`, `bytecode`, `deployedBytecode` và các trường link của
  artifact Hardhat. Web3.py đọc `artifact["abi"]` và `artifact["bytecode"]`.

Test bao gồm initial mint/ownership, faucet và các biên giới hạn, địa chỉ zero,
transfer chính xác tới base unit, approve, allowance, transferFrom, thu hồi
allowance, infinite allowance, lỗi số dư và luồng cấp/chuyển 1,000 MyUSDT.

## Deploy và cấp token trên mạng local

Terminal 1, bật node Q01 và giữ node chạy:

```powershell
npm run node
```

Terminal 2:

```powershell
npm run deploy:myusdt
```

Script chỉ chạy trên `localhost`, kiểm tra Chain ID khớp Q01 trước khi gửi
giao dịch, deploy MyUSDT rồi cấp `1,000 MyUSDT` qua faucet cho 9 ví còn lại.
Sau seed, deployer giữ `1,000,000 MyUSDT`, mỗi ví #1–#9 có `1,000 MyUSDT`,
tổng cung là `1,009,000 MyUSDT`.

Script cập nhật:

- `deployments/localhost.json`: địa chỉ, deployment txHash/block, thông số token,
  ABI path và 10 ví với vai trò, số dư, seed txHash; không xuất private key.
- `backend/config/contracts.json`: riêng mục `local.contracts.MyUSDT`.
- `deployments/abi/MyUSDT.json`: ABI và bytecode biên dịch.

Các mục contract khác được giữ nguyên. Chạy lại sẽ deploy một MyUSDT mới
và cập nhật địa chỉ bàn giao. Nếu node local khởi động lại, dữ liệu chain bị reset:
cần deploy lại và dùng địa chỉ từ manifest mới nhất. Địa chỉ/txHash trong manifest
là bằng chứng local, không phải giao dịch Sepolia.

## Tích hợp cho Hiếu, Quân và Lâm

Đọc địa chỉ tại `deployments/localhost.json`, mục `contracts.MyUSDT.address`,
hoặc `backend/config/contracts.json`, mục `local.contracts.MyUSDT.address`.
Danh sách ví có token nằm ở `contracts.MyUSDT.testAccounts` trong manifest local;
vai trò ví giữ theo Q01.

Ví dụ Ethers v6 khi đã có `token`, signer `lender` và `poolAddress` từ HI02:

```javascript
const amount = ethers.parseUnits("1000", 18);
const lenderAddress = await lender.getAddress();
if ((await token.balanceOf(lenderAddress)) < amount) {
  await (await token.connect(lender).faucet(lenderAddress, amount)).wait();
}
await (await token.connect(lender).approve(poolAddress, amount)).wait();
const allowance = await token.allowance(lenderAddress, poolAddress);
if (allowance < amount) throw new Error("Insufficient MyUSDT allowance");
// Khi HI02 đã có Pool:
// await (await pool.connect(lender).depositLender(amount)).wait();
```

Borrower cũng approve Pool trước khi `repay()`. Backend đọc số dư/allowance hoặc
chuẩn bị calldata; MetaMask ký giao dịch theo Q01.

Kiểm thử H01 dùng một signer làm spender để xác nhận `transferFrom` hoạt động.
Kiểm thử gọi `depositLender()` trên Pool thật chờ đầu ra HI02 của Hiếu.

## Tài liệu tham khảo

- [OpenZeppelin ERC-20](https://docs.openzeppelin.com/contracts/5.x/erc20)
- [OpenZeppelin Ownable](https://docs.openzeppelin.com/contracts/5.x/access-control)
- [Hardhat compilation artifacts](https://v2.hardhat.org/hardhat-runner/docs/advanced/artifacts)
