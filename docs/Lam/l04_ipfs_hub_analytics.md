# L04 — IPFS Document Hub và Analytics

Lâm, giai đoạn 3. Nhánh `feature/lam-l04-ipfs-hub`, kế thừa nền tảng giao diện L02/L03.

## Phạm vi theo kế hoạch

Sheet **Lam, hàng 5 (B5 = L04), H5** của `Kế-hoạch-Blockchain.xlsx` yêu cầu IPFS Hub, tra cứu/tải CID, phân quyền và hai biểu đồ; phụ thuộc H03, Q03, Q04. Kết nối toàn ứng dụng với MetaMask/backend thuộc L05.

Đã kiểm tra đủ đầu vào, không tự tạo thay phần bàn giao của thành viên khác:

| Người / task | File đã có | Sử dụng |
| --- | --- | --- |
| Hùng / H03 | [Handoff IPFS/RBAC](../Hung/h03_ipfs_storage_rbac_handoff.md), `src/ipfs/`, `ipfs_storage/schemas/`, manifest và bộ mẫu | Loại tài liệu, ciphertext, SHA-256, CIDv1, quyền owner/Admin |
| Quân / Q03 | [Agreement Generator](../Quan/q03_agreement_generator_handoff.md), `backend/services/agreement_generator.py` | Sinh PDF trước borrow, mã hóa, lưu CID, tải có RBAC |
| Quân / Q04 | [Credit/Audit](../Quan/q04_credit_and_audit_handoff.md), `backend/services/credit_and_audit_ipfs.py` | Score/summary/history và nhật ký APY có nguồn |
| Quân / Q05 | [API/Auth](../Quan/q05_fastapi_rbac_handoff.md), `backend/api/ipfs.py`, `backend/api/pool.py` | Route đã có để adapter L04 sử dụng |
| Lâm / L01–L03 | Wireframe, API contract, AppShell, mô hình Borrowing Console | Giao diện và dữ liệu mô phỏng nhất quán |

## Chạy giao diện

```powershell
cd frontend
npm run dev
```

- `http://localhost:3000/documents/`: Loan Agreement PDF, Credit Report JSON, Audit Logs JSON/CSV.
- `http://localhost:3000/analytics/`: APY gửi/vay và bốn thành phần số dư ví.
- Menu dùng chung dẫn tới đủ bốn màn hình L01. Giữ font Be Vietnam Pro, navy, bề mặt phẳng và nút pill của giao diện trước.

Mặc định là **Mẫu cục bộ / SIMULATED**. CID lấy nguyên từ manifest H03, không tự tạo CID hoặc txHash giả. Audit JSON được copy nguyên byte và kiểm SHA-256 khi tra cứu. Hai file riêng tư chỉ phân phối **bản mã AES-256-GCM**, không đóng gói PDF/credit report bản rõ hoặc khóa giải mã trong frontend. Sample chưa ghim lên gateway công khai: manifest H03 ghi `provider_used=local_store`.

## Dùng backend đã có

1. Khởi chạy Q05 với cấu hình IPFS/blockchain/auth theo bàn giao của Quân.
2. Chọn **Đổi nguồn dữ liệu**, nhập origin API (mặc định `http://127.0.0.1:8000`).
3. Để token trống để thử Guest. Với owner/Lender/Admin, dùng access token của phiên Q05 đã ký EIP-191.
4. **Áp dụng kết nối** tải danh mục server cho phép xem. Dán CID private của ví khác để thử 403.
5. Analytics chọn Audit JSON và đọc số dư địa chỉ ví qua các endpoint công khai.

Token chỉ tồn tại trong React state của trang hiện tại; không ghi localStorage/cookie, URL hoặc log. Đổi nguồn/token xóa nội dung đã xem và hủy request cũ. Không có bộ chọn role cấp quyền giả ở client. Tích hợp Connect Wallet, ký nonce, tự đổi tài khoản/chain và quản lý phiên chung giữa các trang thuộc L05.

Frontend chỉ nhận origin HTTPS hoặc HTTP loopback, không nhận credentials, query hay subpath trong API origin. Request dùng `no-store`, `credentials: omit`, chặn redirect. CORS phía Q05 phải cho phép origin frontend; nếu thiếu, UI báo lỗi kết nối.

## Tra cứu, tải và tạo hồ sơ

CID input hỗ trợ CIDv0 SHA2-256, CIDv1 base32 với raw/dag-pb/dag-cbor, `ipfs://CID` và link gateway `/ipfs/CID`. Không nhận đường dẫn con/traversal. CID ngoài index nhận 404: không tự truy xuất bản rõ private qua gateway.

| Thao tác | API |
| --- | --- |
| Danh mục theo phiên | `GET /api/ipfs/documents` |
| Tra cứu/tải | `GET /api/ipfs/documents/{cid}/retrieve` |
| Tạo PDF rồi mã hóa/lưu | `POST /api/ipfs/create-agreement` |
| Tạo Credit Report | `POST /api/ipfs/credit-report/{address}` |
| Xuất bản Audit JSON/CSV | `POST /api/ipfs/audit-logs` (Admin) |

**Tạo & lưu IPFS** sử dụng generator của backend, không phải upload file tùy ý vì Q05 không có endpoint generic upload. PDF cần collateral hợp lệ và khoản vay dự kiến; UI không gửi giao dịch borrow hay tự bind txHash. Report cần địa chỉ owner; audit cần quyền Admin. Block bắt đầu được nhập rõ cho các truy vấn lịch sử. Chỉ báo tạo thành công sau HTTP thành công và CID hợp lệ từ backend.

- Guest truy cập private: **401**, nhắc ký xác thực ví.
- Lender hoặc Borrower khác: **403**, hiển thị **“Không có quyền truy cập”**.
- Owner/Admin: server kiểm quyền, giải mã AES-GCM, so hash rồi trả bản rõ.
- Audit Logs public: Guest cũng được đọc. Lỗi API không fallback âm thầm sang số liệu mẫu.
- Nút tải bản mã chỉ có ở sample private; hash so với ciphertext, không tuyên bố đó là PDF/JSON bản rõ.

PDF/CSV dùng nguyên byte response và đối chiếu SHA-256 tại trình duyệt bằng Web Crypto. Q05 đóng gói JSON `{cid, sha256, content}`, không giữ nguyên serialization IPFS: UI kiểm CID/hash metadata, ghi rõ **backend xác minh hash bản gốc**, và tính riêng hash file JSON xuất tải về. Không giả vờ hash của JSON xuất lại chính là hash nội dung IPFS ban đầu. Web Crypto/Clipboard cần secure context (HTTPS hoặc localhost).

## Hai biểu đồ

1. **APY gửi/vay theo tháng**: BarChart Recharts, chọn 3/6/12 tháng, tooltip, bảng dữ liệu đọc bằng bàn phím. SIMULATED dùng cột nhạt có viền đứt, ON_CHAIN dùng cột đậm; tách series và giữ nhãn nguồn cho mỗi kỳ. APR đơn theo giây được giải thích riêng với APY quy đổi ghép lãi hằng ngày.
2. **Số dư ví**: BarChart so sánh MyUSDT khả dụng, giá trị collateral theo MyUSDT, DebtToken/nợ gốc và lãi vay tích lũy. Dùng bốn thanh ngang độc lập, không cộng nợ vào tổng tài sản. Số tiền gốc giữ chuỗi WAD, Number chỉ dùng vẽ; tooltip đọc lại WAD.

Sample số dư đọc phiên L03 mỗi 3 giây, không ghi đè trạng thái. Chọn ví thanh lý để so sánh. Backend đọc balances + loan/risk/accrued interest theo snapshot khi bấm nút. Hai endpoint chưa cố định cùng một block nên không cam kết snapshot nguyên tử; chưa có định giá USD ngoại sinh.

## Kiểm thử và bàn giao tiếp

```powershell
cd frontend
npm test
npm run lint
npm run build
cd ..
python -m pytest tests/test_h03_ipfs.py tests/test_q03_agreement_generator.py tests/test_q04_credit_and_audit_ipfs.py tests/test_q05_api_auth_rbac.py -q
python scripts/verify_l04_frontend_api.py
```

Harness cuối chạy **API Q05 thật + adapter TypeScript thật** qua HTTP loopback, ví test ngẫu nhiên, kho mã hóa IPFS tạm. Web3 events là test double; không thay thế kiểm thử RPC/Kubo/Pinata/MetaMask thật. Không ghi khóa/token vào báo cáo.

L05 tiếp tục nối provider MetaMask với state kết nối dùng chung, kiểm tra đổi account/chain/expiry, chạy live upload/retrieve và kịch bản ký borrow. L06 kiểm thử E2E click/download và ảnh thành công/403 trên một phiên browser thực tế.

[Báo cáo xác minh và ảnh](../../reports/Lam/l04_frontend_validation.md).
