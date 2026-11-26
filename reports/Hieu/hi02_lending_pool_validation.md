# Báo cáo Kiểm thử & Xác minh Triển khai Local – HI02 (`LendingPool.sol`)

## 1. Môi trường kiểm thử
- **Nhánh**: `feature/hieu-gd2-hi02-lending-pool-core`
- **Trình biên dịch**: Solidity `0.8.24`, optimizer `200 runs`, EVM `paris`, `@openzeppelin/contracts@5.0.2`
- **Biên dịch**: `npm run compile` — **0 warnings, 0 errors**

## 2. Kết quả kiểm thử tự động
- **Hardhat (`npm test`)**: **`95/95 passing`** (bao gồm toàn bộ test `H01` `MyUSDT`, `HI01` `ProtocolMath`, `H02` Token/NFT và `HI02` `LendingPool` — không làm gãy bất kỳ kiểm thử cũ nào).
- **Pytest (`pytest -v`)**: **`11/11 passed`** (bao gồm đối chiếu hằng số & chỉ số APR tuyến tính giữa `ProtocolMath.sol` và `backend/config/constants.py`).

## 3. Các kịch bản trọng tâm đã kiểm chứng trong `tests/HI02_LendingPool.test.js`
1. **Binding & Custody an toàn**: Khớp toàn bộ địa chỉ `H01`/`H02`; chặn địa chỉ zero ở constructor; chặn chuyển trực tiếp `CollateralNFT` vào Pool bỏ qua `depositCollateral` (`UnauthorizedNFTTransfer`).
2. **Vòng đời chuẩn với `CollateralNFT`**: `depositLender(1000)` → `depositCollateral(tokenId=1, true)` phát hành `CollateralReceiptNFT #1` → `borrow(500, cid)` mint `500 DebtToken` & lưu `ipfsAgreementCid` → trả góp một phần (`repay(200)`) giữ nguyên thế chấp → tua 60 ngày & trả đủ nợ tự động burn `DebtToken`, hoàn trả `CollateralNFT #1`, `settleReceipt(1, false)` (burn biên nhận nhưng giữ lịch sử `getReceiptInfo`) → thế chấp vay vòng mới (`Receipt #2`) không bị trùng trạng thái → Lender rút `1000 + lãi` và burn `LendingPositionNFT #1`.
3. **Thế chấp ERC-20 & Tách biệt thanh khoản**: `totalTokenCollateralLocked` tách biệt khỏi `getAvailableLiquidity()`, ngăn Lender rút lẹm tài sản thế chấp của Borrower; kiểm thử `withdrawCollateral()` thành công khi dư nợ bằng `0`.
4. **Chuyển nhượng `LendingPositionNFT` (Lender A → B → A)**: Chủ cũ bị chặn `NotPositionOwner`; chủ mới rút một phần rồi chuyển lại không gây hưởng lãi 2 lần (`InsufficientClaimableBalance` nếu rút vượt phần còn lại); `PositionBurned` ghi đúng `ownerOf` hiện tại.
5. **Ràng buộc & Bảo mật Reentrancy**: Chặn vay vượt 70% LTV (`ExceedsMaxLTV`), chặn CID rỗng (`EmptyAgreementCid`), và chặn tấn công tái nhập qua `onERC721Received` bằng `ReentrantAttacker` (`ReentrancyGuard`).

## 4. Kết quả triển khai chuỗi `H01 → H02 → HI02` trên Localhost (`Chain ID = 31337`)
| Hợp đồng | Địa chỉ Localhost | Trạng thái sau `deploy:hi02` |
|---|---|---|
| `MyUSDT` | `0x5FbDB2315678afecb367f032d93F642f64180aa3` | Deployed & Seeded (`H01`) |
| `CollateralNFT` | `0x610178dA211FEF7D417bC0e6FeD39F05609AD788` | `DEPLOYED` (`H02`) |
| `CollateralReceiptNFT` | `0xB7f8BC63BbcaD18155201308C8f3540b07f84F5e` | `BOUND_TO_POOL` |
| `DebtToken` | `0xA51c1fc2f0D1a1b8494Ed1FE312d7C3a78Ed91C0` | `BOUND_TO_POOL` |
| `LendingPositionNFT` | `0x0DCd1Bf9A1b36cE34237eEaFef220932846BCD82` | `BOUND_TO_POOL` |
| `LendingPool` | `0x9A676e781A523b5d0C0e43731313A708CB607508` | `DEPLOYED_AND_BOUND` |

*(Các địa chỉ và `txHash` trên là bằng chứng chạy mạng Local Hardhat `31337`; triển khai Sepolia Testnet thuộc `Q06` / `HI06`).*
