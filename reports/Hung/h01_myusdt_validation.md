# H01 – Kết quả kiểm thử & xác minh Token ERC-20 MyUSDT

Báo cáo tổng hợp kiểm thử và bàn giao riêng cho hạng mục **H01** của Hùng (tách rõ khỏi báo cáo gộp tại [h02_token_validation.md](h02_token_validation.md)).

- Hợp đồng nguồn: [MyUSDT.sol](../../contracts/tokens/MyUSDT.sol)
- Bộ unit test: [MyUSDT.test.js](../../tests/MyUSDT.test.js)
- ABI & bytecode bàn giao: [MyUSDT.json](../../deployments/abi/MyUSDT.json)
- Tài liệu hướng dẫn tích hợp: [h01_myusdt_handoff.md](../../docs/Hung/h01_myusdt_handoff.md)

## Thông số kỹ thuật đã xác minh

| Thông số | Giá trị xác minh |
|---|---|
| Tên / ký hiệu | `MyUSDT` / `MyUSDT` |
| Chuẩn & thư viện | OpenZeppelin `5.0.2` (`ERC20`, `Ownable`) |
| Decimals | `18` (`1 MyUSDT = 10^18` base units) |
| Nguồn cung khởi tạo (`INITIAL_SUPPLY`) | `1,000,000 MyUSDT` (mint cho deployer) |
| Hạn mức faucet mỗi lần gọi (`MAX_FAUCET_AMOUNT`) | `1,000 MyUSDT` (`InvalidFaucetAmount` khi `0` hoặc `> 1,000 * 10^18`) |
| Trình biên dịch | Solidity `0.8.24`, optimizer `200 runs`, EVM `paris` (**0 warnings**) |

## Kết quả kiểm thử

| Hạng mục | Kết quả |
|---|---|
| `npm run test:myusdt` (`tests/MyUSDT.test.js`) | **23/23 passing** (deployment & ownership: 3; faucet & biên giới hạn: 8; transfer/approve/transferFrom/revoke/infinite allowance/luồng nạp 1.000 MyUSDT: 12) |
| Xuất ABI & đối chiếu manifest | `deployments/abi/MyUSDT.json` khớp 100% với artifact biên dịch và `frontend/src/config/contracts.json` |

## Bằng chứng triển khai Local & Sepolia

- **Local Hardhat (`chainId = 31337`)**: địa chỉ `0x5FbDB2315678afecb367f032d93F642f64180aa3`, ghi nhận trong [deployments/localhost.json](../../deployments/localhost.json) và [h02_local_verification.json](h02_local_verification.json) (dữ liệu local phục vụ demo/seed, không thay thế testnet).
- **Ethereum Sepolia Testnet (`chainId = 11155111`)**: địa chỉ `0xAaB07940F52BB7C105D17681f896E648b8A39881`, deploy tx `0x9f44c3e3b087ce4c77305efdfcdc7f786ab1f6d0d97f335cb5f1f5cd82f0ec8e`, ghi nhận trong [deployments/sepolia.json](../../deployments/sepolia.json) và [q06_deploy_and_sepolia_validation.md](../Quan/q06_deploy_and_sepolia_validation.md).
