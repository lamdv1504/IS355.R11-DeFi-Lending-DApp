# L01 – Dữ liệu UI và đề xuất API bàn giao Q05

## 1. Trạng thái của tài liệu

Nguồn chuẩn: [HI01 6](smart_contract_spec.md), các interface trong
`contracts/interfaces/` và `backend/config/constants.py`.
L01 bổ sung lớp dữ liệu phục vụ 4 wireframe; **các endpoint mới là đề xuất thiết kế,
chưa được implement hoặc được Quân/Hiếu xác nhận**.

Backend hiện có `GET /health` và `GET /api/network-status` trong `backend/main.py`.
`POST /api/ipfs/create-agreement` đã được HI01 mô tả cho Q03; hiện chưa có route runtime.
Không đổi backend, ABI hay constants của các thành viên khác trong L01.

## 2. Quy ước chung

- `network`: `local` hoặc `sepolia`, đi cùng `chain_id` chính xác.
- Địa chỉ contract lấy từ registry của mạng hiện tại; address rỗng hoặc `eth_getCode = 0x`
  trả trạng thái `CONTRACT_NOT_DEPLOYED`, khóa submit và không giả transaction.
- `block_number`, `as_of_timestamp` đi cùng dữ liệu để phân biệt snapshot và dữ liệu cũ.
- Mọi WAD, tokenId, positionId, receiptId, raw uint256: **chuỗi thập phân**.
  Frontend dùng BigInt cho validation, không đổi WAD sang Number trước khi so sánh.
- Tiền tệ chuẩn HI01: `{"amount_wad":"500000000000000000000","amount_display":"500.000000"}`.
- Rate: giữ `borrow_apr_bps` / `supply_apr_bps` và các giá trị phần trăm APR/APY
  đúng tên HI01. APY là quy đổi lãi kép theo ngày, không là lời hứa lãi thực nhận.
- `getMaxBorrowable` trả **trần tổng nợ**, không phải hạn mức vay thêm.
  Trường đề xuất `remaining_ltv_capacity` = `max(0, max_total_debt - total_debt)`;
  `available_to_borrow` = `min(remaining_ltv_capacity, available_liquidity)`.
- Health Factor giữ đủ schema từ `format_health_factor_for_api`:
  `health_factor_wad` (chuỗi), `health_factor` (số hiển thị/null), `is_infinite`,
  `status`, `liquidatable`. Quyết định liquidate dùng WAD chưa làm tròn.
- Không nợ: `health_factor = null`, `is_infinite = true`, UI hiện ∞.
  `HF = 1` là `WARNING` và `liquidatable = false`.
- CID / txHash / SHA-256 chưa có thì `null`; không sinh chuỗi giả có vẻ là bằng chứng thật.
- [JSON ví dụ](wireframes/l01-ui-examples.json) có nhãn `SIMULATED`.
  Dữ liệu minh họa không được âm thầm dùng thay RPC lỗi trong ứng dụng thật.

## 3. Danh sách endpoint đề xuất

Trừ hai route ghi “đã có”, các route đều chờ Q05/Q03/Q04 triển khai và xác nhận.

| Method / path | Mục đích / dữ liệu | Quyền |
|---|---|---|
| GET /health | Health check (đã có Q01) | Công khai |
| GET /api/network-status?network=local | RPC, expected/actual chainId (đã có Q01) | Công khai |
| GET /api/pool?network=local | PoolInfo + availableLiquidity + APR/APY + block/time | Công khai |
| GET /api/accounts/{address}/lending-positions | positionId, principal, interest, claimable, owner, active | Dữ liệu công khai on-chain |
| GET /api/accounts/{address}/loan | LoanPosition, định giá, tổng nợ, HF, capacity, receipt | Dữ liệu công khai on-chain; không trả bản giải mã hồ sơ |
| GET /api/accounts/{address}/balances | MyUSDT, DebtToken, NFT ids và định giá | Dữ liệu công khai on-chain |
| POST /api/auth/nonce | Nonce ngắn hạn, ví, chain, domain, expiry | Ví kết nối |
| POST /api/auth/verify | Signature + nonce → phiên và role backend | Xác minh chữ ký, chống replay |
| POST /api/transactions/prepare | Action + args → unsigned tx và preview | Ví kết nối; thêm auth nếu nghiệp vụ backend cần |
| POST /api/ipfs/create-agreement | Tạo PDF/hash/CID trước vay (HI01 đã đặc tả) | Borrower chính chủ đã auth |
| POST /api/transactions/confirm | Xác minh receipt + bind CID/khoản vay sau giao dịch | Kiểm tra chain, from, to, action, event và chủ hồ sơ |
| GET /api/ipfs/documents | Hồ sơ của ví và Audit Logs công khai | Lọc theo phiên; không liệt kê hồ sơ private của ví khác |
| GET /api/ipfs/documents/{cid}/retrieve | Nội dung đúng quyền; có hash để kiểm tra | Public hoặc owner/Admin đã auth |
| GET /api/analytics/rates | Điểm thời gian, APR, U, nguồn dữ liệu | Công khai |
| POST /api/demo/time | Tăng thời gian Hardhat rồi mine block | Local 31337 + Admin backend |

Mock giá dùng unsigned tx `PriceOracle.setPriceMultiplierBps(6000)` với ví
owner on-chain; endpoint chuẩn bị phải chặn mạng không phải local.
Faucet dùng `MyUSDT.faucet(to, amount)`, public theo H01; không gán nhầm onlyAdmin.
Admin API không được ký hộ ví người dùng hoặc bỏ qua modifier owner/onlyPool.

## 4. Mapping hành động, preview và sự kiện xác nhận

| Action UI | Đích / chữ ký chuẩn | Kiểm tra trước ký | Event refresh |
|---|---|---|---|
| Gửi | MyUSDT.approve(Pool, amount), Pool.depositLender(amount) | Balance, allowance; có Pool address/code | Approval, LenderDeposited, PositionMinted, InterestRateUpdated |
| Rút | Pool.withdrawLender(positionId, amount) | ownerOf, claimable, availableLiquidity | LenderWithdrawn, PositionBurned nếu hết, InterestRateUpdated |
| Chuyển vị thế | LendingPositionNFT.safeTransferFrom(from,to,tokenId) | Owner hiện tại, to != 0, địa chỉ người nhận | Transfer; đọc lại ownerOf và danh sách vị thế |
| Thế chấp token | ERC20.approve(Pool,amount), Pool.depositCollateral(amount,false) | Balance, allowance, chưa có thế chấp active | CollateralDeposited, ReceiptMinted |
| Thế chấp NFT | CollateralNFT.approve(Pool,id), Pool.depositCollateral(id,true) | ownerOf, getApproved/isApprovedForAll | CollateralDeposited, ReceiptMinted |
| Vay | Pool.borrow(amount,agreementCid) | CID, hạn mức nợ/LTV, thanh khoản, HF preview | LoanBorrowed, InterestRateUpdated |
| Trả nợ | MyUSDT.approve(Pool,amount), Pool.repay(amount) | Balance, allowance, tổng nợ/lãi snapshot mới | LoanRepaid, ReceiptSettled nếu tất toán, InterestRateUpdated |
| Rút thế chấp | Pool.withdrawCollateral() | Nợ = 0, tài sản còn khóa theo lựa chọn thiết kế L01 | CollateralWithdrawn, ReceiptSettled |
| Thanh lý | MyUSDT.approve(Pool,debt), Pool.liquidate(borrower) | HF_WAD < 1e18, balance và allowance | LoanLiquidated, ReceiptSettled, InterestRateUpdated |
| Faucet | MyUSDT.faucet(to,amount) | 0 < amount <= 1000e18, to != 0 | FaucetUsed, Transfer |
| Giảm giá local | PriceOracle.setPriceMultiplierBps(6000) | Local, owner oracle; không suy từ role UI | PriceMultiplierUpdated; đọc lại HF |

Không gọi “transferPositionNFT” như một hàm Pool chưa tồn tại.
Không gọi mint/burn DebtToken hoặc ReceiptNFT trực tiếp từ UI.
`Transfer` của ERC-721/20 phải lọc đúng address contract và indexed args.
Sự kiện cung cấp tín hiệu refresh; getter/state tại block sau receipt là nguồn xác nhận.

## 5. Payload prepare và chống dùng nhầm transaction

Ví dụ cấu trúc request đề xuất (giá trị ở base units):
```json
{
  "network": "local",
  "chain_id": 31337,
  "account": "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
  "action": "DEPOSIT_LENDER",
  "args": {"amount_wad": "1000000000000000000000"},
  "position_id": null,
  "agreement_cid": null
}
```

Response yêu cầu các nhóm sau; trong JSON minh họa, `unsigned_tx`/gas có thể `null`
vì Pool chưa triển khai. Khi runtime sẵn sàng, không cho ký nếu thiếu nhóm bắt buộc:

| Nhóm | Trường cần có |
|---|---|
| Context | network, chain_id, account, action, block_number, as_of_timestamp |
| Availability | ready, blocked_reason, missing_contracts |
| Allowance | token_address, spender_address, amount_wad, current_allowance_wad, approval_required |
| Preview | amount, current/resulting debt, LTV BPS, HF WAD, APR hiện tại/sau giao dịch |
| Interest estimate | principal_wad, apr_bps, horizon_seconds, interest_wad, nhãn “ước tính” |
| Gas | estimated_gas, gas_price_wei hoặc max_fee_per_gas_wei/max_priority_fee_per_gas_wei; estimated_fee_wei (chuỗi) |
| Transaction | from, to, chainId, data, value; giá trị int lớn dùng chuỗi hex/decimal phù hợp provider |

UI kiểm tra `from` bằng ví hiện tại, `chainId` bằng mạng chọn, `to` bằng registry,
selector/data khớp action và `value` dự kiến (giao dịch ERC-20 không gửi ETH nghiệp vụ).
So sánh payload với form trước khi yêu cầu ký. Chặn địa chỉ hoặc action không biết.
Approve và action được prepare/ước lượng riêng, chờ receipt approve rồi đọc lại allowance.
Không tái dùng preview sau đổi amount, ví, chain hoặc snapshot đã cũ.
`gasUsed` trong receipt mới là chi phí thực tế; gas preview phải ghi là ước lượng.

## 6. Hồ sơ IPFS, auth và lỗi

Loan Agreement:
1. Borrower auth bằng nonce; backend lấy điều khoản từ state/HI01.
2. Tạo PDF + SHA-256, mã hóa nếu nhạy cảm, upload IPFS → trả CID và trạng thái chờ vay.
3. UI ký `borrow(amount,cid)`; không yêu cầu txHash tồn tại trước PDF.
4. Confirm endpoint tự xác minh receipt.status, contract, from, amount, event và CID.
5. Chỉ sau bước 4 mới lưu quan hệ CID ↔ khoản vay ↔ txHash đã xác nhận.
6. Khi hủy/revert, không dựng khoản vay thành công; CID chờ xử lý theo chính sách Q03.

Nonce phải gắn domain, address, chainId, mục đích và thời hạn; chỉ dùng một lần.
Role trả từ backend, không lấy quyền từ dropdown đổi vai trò trên UI.
Phiên phải bị vô hiệu hóa trong UI khi accountsChanged / chainChanged / disconnect.
Không đưa private key người dùng, khóa AES hoặc nội dung private vào query URL/log.
Nhập CID không thay cho xác thực; backend vẫn thực thi owner/Admin và trả đúng 401/403.

| Lỗi | Thông báo / hành vi |
|---|---|
| Invalid amount / CID | Báo ngay tại input; không mở MetaMask |
| 401 | Kết nối ví và ký đăng nhập |
| 403 | Không có quyền; không trả nội dung private |
| ExceedsMaxLTV | Vượt trần tổng nợ 70%; cập nhật lại hạn mức |
| InsufficientPoolLiquidity | Pool không đủ thanh khoản rỗi để thực hiện |
| InsufficientClaimableBalance | Vượt quyền rút của vị thế |
| NotPositionOwner | Ví hiện tại không sở hữu Position NFT |
| OutstandingDebtExists | Còn dư nợ; chưa rút được thế chấp |
| HealthFactorSafe | HF >= 1; không đủ điều kiện thanh lý |
| RPC/gas estimation unavailable | Tạm khóa ký; cho thử lại; không giả gas = 0 |
| Hash không khớp | Dừng mở tài liệu; cho kiểm tra/tải lại |
| Giao dịch thay thế / receipt chưa rõ | Tra cứu hash thực tế trước khi gửi lại |

Không có endpoint trả khóa giải mã cho người không có quyền.
Cách vận chuyển nội dung private đã giải mã cần Quân chốt ở Q05; wireframe chỉ yêu cầu
người dùng được phép mở/tải và không quảng bá rằng gateway công khai cấp được bản rõ.

## 7. Những mục chờ các thành viên xác nhận

| Mục | Người xác nhận | Trạng thái |
|---|---|---|
| Endpoint names, pagination, response envelope, expiry/refresh preview | Quân + Lâm | Đề xuất |
| Policy auth/session và Admin quyền đọc hồ sơ | Quân + Hùng + Lâm | Theo HI01, chờ Q05 thực thi/chốt |
| Ngữ nghĩa withdrawCollateral và auto-unlock khi repay hết | Hiếu | Cần xác nhận điểm chưa đồng nhất ở HI01 |
| Lãi preview khi rate/index đổi giữa các block | Hiếu + Quân | Tuân thủ HI01, chờ implementation |
| Đơn vị/nguồn gas và transaction confirm | Quân + Lâm | Đề xuất |
| Liệt kê position/NFT theo owner từ event indexer | Hùng + Quân | Chờ H02/Q02–Q04 |
| Tối thiểu gửi/vay/trả nợ chạy thật, txHash/status UI | Hiếu + Quân + Lâm | Nghiệm thu L05 sau khi đủ contract/API |

Tài liệu này là đầu ra review L01, không là bằng chứng các thành viên đã đồng ý
hoặc các endpoint chưa có đã chạy được.
