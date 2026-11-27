# Q03 - Agreement Generator handoff

## Luồng hai pha

`AgreementGeneratorService` tạo PDF trước giao dịch `borrow()` và không giả lập
transaction hash:

1. `create_pre_borrow_agreement(borrower_wallet, principal_wad, *,
   asset_description, wallet_auth_signature=None)` đọc loan position, collateral
   receipt, debt/risk, current LTV, max borrow và interest-rate snapshot từ
   `Web3Service`. Dịch vụ xác nhận receipt còn active, đối chiếu current LTV với
   debt/valuation, và từ chối nếu `current_debt + principal_wad` vượt
   `get_max_borrowable()` hoặc trần 70% LTV.
2. Tạo `LoanAgreementPayload` với `status="PRE_BORROW_UNSIGNED"` và
   `tx_hash=None`; APR đơn on-chain và APY ghép lãi theo ngày chỉ để tham khảo
   được lưu tách biệt. PDF được render, băm SHA-256, mã hóa AES-256-GCM ở chế độ
   PRIVATE, rồi upload qua `AuthorizedIPFSGateway`.
3. Index cục bộ JSON lưu `DocumentAccessMetadata` và dữ liệu cần để đối chiếu
   agreement. `retrieve_agreement_pdf(cid, context)` gọi
   `retrieve_authorized_document()` trước khi trả PDF, do đó giữ nguyên RBAC
   (`401` guest, `403` ví không phải owner, `200` owner/admin), giải mã và so
   SHA-256.
4. Sau khi client gửi `borrow(amount, agreement_cid)` bằng MetaMask và nhận
   receipt thành công (`status == 1`), gọi
   `bind_loan_transaction(agreement_cid, loan_id, borrower_wallet,
   transaction_receipt)`. Hàm ghi một `LoanTxBindingRecord` gắn CID, loan,
   borrower, tx hash và block number. Receipt lỗi không được bind.

Không gửi private key/seed phrase của người dùng vào backend. `wallet_auth_signature`
nếu có chỉ là chữ ký xác thực phiên ví; kiểm tra session thực tế thuộc Q05.
Khóa AES backend lấy từ `DOCUMENT_AES_KEY_HEX` qua
`DocumentEncryptor.from_env()` khi khởi tạo gateway mặc định. Không ghi khóa
giải mã vào index, metadata IPFS, PDF, hoặc CID.

## Giao diện bàn giao Q05 và Lâm L04/L05

Khởi tạo service:

```python
service = AgreementGeneratorService(
    web3_service,
    binding_store_path=Path("backend/data/agreement_bindings.json"),
    # gateway=authorized_gateway,  # Có thể inject gateway/test double
)
```

Q05 cung cấp borrower wallet đã xác thực, `principal_wad` dạng integer WAD và
mô tả tài sản. Response tạo agreement có dạng:

```json
{
  "cid": "bafy...",
  "pdf_plaintext_sha256": "<64 hex>",
  "encrypted_ipfs_sha256": "<64 hex>",
  "gateway_url": "http://127.0.0.1:8080/ipfs/bafy...",
  "agreement_id": "Q03-...",
  "agreement_nonce": "<random nonce>",
  "status": "PRE_BORROW_UNSIGNED",
  "tx_hash": null,
  "acl_metadata": {
    "document_type": "LOAN_AGREEMENT",
    "visibility": "PRIVATE",
    "encrypted": true,
    "owner_wallet": "0x..."
  }
}
```

Q05 dùng `cid` làm CID argument của `borrow()`, chờ transaction receipt thành
công, rồi truyền receipt và `loan_id` vào hàm bind. `retrieve_agreement_pdf()`
nhận `AccessContext` đã xác thực phía server; không tự tin cậy role/wallet do
client gửi mà chưa xác minh chữ ký phiên. L04/L05 dùng CID/URL cho trạng thái
loading và hiển thị/tải PDF qua endpoint có RBAC; tuyệt đối không tải bản rõ
trực tiếp từ public IPFS gateway. `retrieve_raw_by_cid()` chỉ trả envelope mã
hóa.

## Kiểm thử

`tests/test_q03_agreement_generator.py` dùng local IPFS store trong thư mục
pytest tạm để kiểm tra PDF, mã hóa, CID/raw ciphertext, quyền Guest/Lender/
borrower khác/chính chủ/Admin, SHA-256 và tx binding mà không cần Hardhat, Kubo,
Pinata hoặc thông tin xác thực bên ngoài.

Chạy các test tích hợp liên quan:

```powershell
pytest tests/test_q02_web3_service.py tests/test_q03_agreement_generator.py tests/test_hi01_constants.py tests/test_hi05_oracle_and_liquidation.py
```

Thử tích hợp thật tiếp theo: cấu hình `DOCUMENT_AES_KEY_HEX` trong môi trường
backend, chạy IPFS local hoặc cấu hình provider phù hợp; khởi động Hardhat và
backend với cùng registry; tạo collateral cho borrower, tạo agreement, ký
`borrow(..., cid)` bằng MetaMask, bind receipt sau `status == 1`, rồi thử lấy PDF
với owner/admin và xác nhận Guest/Lender bị chặn đúng mã HTTP. Không dùng khóa
ví người dùng trong backend.
