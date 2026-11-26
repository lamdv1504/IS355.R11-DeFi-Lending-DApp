# HI02 – Xây dựng Hợp đồng Lõi `LendingPool.sol` (Hiếu, Giai đoạn 2)

## 1. Phạm vi và Đầu vào đã tích hợp

`HI02` kế thừa trực tiếp toàn bộ kết quả đã nghiệm thu trên nhánh `main`:
- **Q01 (Quân)**: Mạng Hardhat Local (`31337`), Solidity `0.8.24` (EVM Paris), OpenZeppelin `5.0.2`.
- **H01 (Hùng)**: `contracts/tokens/MyUSDT.sol` (ERC-20, 18 decimals, `faucet`).
- **HI01 (Hiếu)**: `ProtocolConstants.sol`, `ProtocolMath.sol` và bộ 7 Interface trong `contracts/interfaces/`.
- **H02 (Hùng)**: `CollateralNFT`, `CollateralReceiptNFT`, `DebtToken`, `LendingPositionNFT` (kế thừa `PoolControlled` bind một lần duy nhất qua `setLendingPool`).

---

## 2. Các nghiệp vụ cốt lõi đã triển khai trong `contracts/LendingPool.sol`

| Nghiệp vụ / Hàm | Mô tả cơ chế & Ràng buộc an toàn | Sự kiện phát ra |
|---|---|---|
| `depositLender(uint256 amount)` | Chốt lãi tích lũy cũ → thu `MyUSDT` → mint `LendingPositionNFT` ghi nhận vị thế (`principal`, `supplyIndexSnapshot`) → cập nhật `utilizationBps`, `borrowAprBps`, `supplyAprBps`. | `LenderDeposited`, `PositionMinted`, `InterestRateUpdated` |
| `withdrawLender(uint256 positionId, uint256 amount)` | Xác thực **chủ sở hữu NFT hiện tại** (`ownerOf(positionId) == msg.sender`) → chốt lãi → kiểm tra `amount <= claimable` và `amount <= getAvailableLiquidity()` → trừ lãi trước, gốc sau (tránh hưởng lãi 2 lần sau chuyển NFT) → burn NFT khi rút hết. | `LenderWithdrawn`, `PositionBurned` *(khi rút hết)*, `InterestRateUpdated` |
| `depositCollateral(uint256 amountOrTokenId, bool isNFT)` | Hỗ trợ cả **CollateralNFT (`isNFT = true`)** (custody qua `safeTransferFrom` + `IERC721Receiver`) lẫn **ERC-20 collateral (`isNFT = false`)** (tách riêng khỏi thanh khoản cho vay qua `totalTokenCollateralLocked`) → phát hành biên nhận soulbound `CollateralReceiptNFT`. | `CollateralDeposited`, `ReceiptMinted` |
| `borrow(uint256 amount, string agreementCid)` | Yêu cầu có thế chấp active, `agreementCid` không rỗng, kiểm tra trần **LTV ≤ 70%** (`requestedTotalDebt <= maxBorrowable`) và thanh khoản rỗi → lưu CID on-chain → mint `DebtToken` khớp gốc → giải ngân `MyUSDT`. | `LoanBorrowed`, `DebtMinted`, `InterestRateUpdated` |
| `repay(uint256 amount)` | Chốt lãi tới `block.timestamp`, tự động giới hạn số tiền thu tối đa bằng `totalDebt` (tránh trả dư khi chênh lệch block MetaMask), ưu tiên trả lãi trước gốc sau, burn `DebtToken` tương ứng phần gốc. **Khi `remainingDebt == 0`, tự động mở khóa trả tài sản thế chấp và gọi `settleReceipt(receiptId, false)`.** | `LoanRepaid`, `DebtBurned`, `CollateralWithdrawn` & `ReceiptSettled` *(khi tất toán)*, `InterestRateUpdated` |
| `withdrawCollateral()` | Chốt rõ ngữ nghĩa theo mục 7 của `docs/Lam/l01_api_contract.md`: dùng để rút lại tài sản thế chấp khi người vay **chưa phát sinh nợ (`totalDebt == 0`)**; nếu còn nợ sẽ revert `OutstandingDebtExists`. Khi đã trả hết nợ trong `repay()`, tài sản đã được tự động hoàn trả ngay trong giao dịch `repay()`. | `CollateralWithdrawn`, `ReceiptSettled` |
| `liquidate(address borrower)` | Triển khai đầy đủ theo `ILendingPool`: chỉ chạy khi `getHealthFactor(borrower) < 1e18` và có giao dịch gọi từ Liquidator; thu nợ, burn `DebtToken`, chuyển tài sản thế chấp (+5% bonus với ERC-20 hoặc chuyển NFT với NFT collateral) và `settleReceipt(receiptId, true)`. *(Sẽ gắn `PriceOracle.sol` thật và kiểm thử sụt giá chi tiết ở `HI05`)*. | `LoanLiquidated`, `DebtBurned`, `ReceiptSettled`, `InterestRateUpdated` |

### Lưu ý bảo mật & Tương thích kỹ thuật
1. **Chống Reentrancy**: Mọi hàm ghi trên `LendingPool` đều gắn `ReentrancyGuard` (`nonReentrant`) kết hợp mô hình Checks-Effects-Interactions, đã kiểm chứng bằng contract tấn công giả lập `contracts/mocks/ReentrantAttacker.sol`.
2. **Bảo vệ nhận NFT (`IERC721Receiver`)**: `onERC721Received` chỉ chấp nhận `CollateralNFT` được chính `LendingPool` kéo vào trong `depositCollateral()`, chặn người ngoài chuyển nhầm NFT trực tiếp vào địa chỉ Pool.
3. **Tách biệt tài sản thế chấp ERC-20**: Khi dùng `MyUSDT` làm tài sản thế chấp ERC-20 (`collateralToken == myUSDT`), `getAvailableLiquidity()` tự trừ `totalTokenCollateralLocked` khỏi `myUSDT.balanceOf(address(this))` nên Lender không thể rút lẹm vào tiền thế chấp của Borrower.
4. **Sẵn sàng gắn `PriceOracle` ở `HI05`**: Khi `priceOracle == address(0)`, Pool mặc định đọc `CollateralNFT.valuation(tokenId)` và giá token `1:1` (`1e18`). Khi `HI05` hoàn thành `PriceOracle.sol`, chỉ cần gọi `setPriceOracle(oracleAddress)` mà không làm thay đổi ABI hiện tại.

---

## 3. Lệnh Biên dịch, Kiểm thử & Triển khai Local (Dành cho Quân `Q02`, Lâm `L02`/`L03`, Hiếu `HI03`)

```powershell
# Biên dịch & chạy test HI02 + toàn bộ repo
npm run compile
npm run test:hi02
npm test

# Xuất ABI vào deployments/abi/LendingPool.json và deployments/abi/interfaces/ILendingPool.json
npm run export:hi02
```

Triển khai đầy đủ chuỗi `H01 → H02 → HI02` trên Hardhat Local Node (`Chain ID = 31337`):

```powershell
# Terminal 1
npm run node

# Terminal 2
npm run deploy:myusdt
npm run deploy:h02
npm run deploy:hi02
```

Sau khi chạy `npm run deploy:hi02`:
- `DebtToken`, `CollateralReceiptNFT`, `LendingPositionNFT` tự động được bind 1 lần duy nhất tới `LendingPool` và cập nhật trạng thái `BOUND_TO_POOL` trong `deployments/localhost.json`.
- Địa chỉ và ABI của `LendingPool` được ghi vào `backend/config/contracts.json` (`local.contracts.LendingPool`) và `deployments/abi/LendingPool.json` sẵn sàng cho **Quân (`Q02`)** nạp vào `Web3.py`.
