# H03 – Báo cáo Kiểm thử Hạ tầng IPFS, 3 Loại Hồ sơ, Mã hóa AES-256-GCM & RBAC

Báo cáo ghi nhận kết quả kiểm thử tự động và các bằng chứng đầu ra của công việc **H03 (Hùng, Giai đoạn 2)**.
Mã nguồn test: [`tests/test_h03_ipfs.py`](../../tests/test_h03_ipfs.py) | Script xác minh: [`scripts/verify_h03_ipfs.py`](../../scripts/verify_h03_ipfs.py) | Log JSON: [`h03_ipfs_verification.json`](h03_ipfs_verification.json).

---

## 1. Bảng Tóm tắt Kiểm thử Đã Chạy

| Hạng mục kiểm thử | Lệnh chạy | Kết quả |
|---|---|---|
| Sinh schema, mẫu 3 loại hồ sơ (+ PNG) & kiểm thử RBAC 20 trường hợp | `python -B scripts/verify_h03_ipfs.py --generate-samples` | **PASS** (4/4 định dạng tạo thành công, 20/20 kiểm tra RBAC đạt) |
| Bộ Unit & HTTP-Integration Test H03 | `pytest tests/test_h03_ipfs.py -v` | **10/10 PASSED** |
| Kiểm tra không gây hồi quy bộ test Q01 | `pytest tests/test_q01_environment.py -k "not test_fastapi_health_endpoint" -v` | **4/4 Python config/registry PASSED** *(1 test `hardhat` cần `npm ci`; 1 test `TestClient` cần socket ngoài sandbox)* |
| Kiểm tra đồng bộ hằng số HI01 (Python ↔ Solidity) | `pytest tests/test_hi01_constants.py -v` | **4/4 PASSED** *(1 test đọc `artifacts/` yêu cầu chạy `npm run compile` trước)* |

---

## 2. Danh mục Hồ sơ Mẫu, Mã CIDv1 & Đối chiếu SHA-256

> **Ghi chú minh bạch về môi trường chạy kiểm thử & đối chiếu ghim sống Kubo (Q03/Q04)**:
> - Tại thời điểm bàn giao **H03**, 4 hồ sơ mẫu tĩnh bên dưới được sinh bằng tầng content-addressed cục bộ (`local_store` – thuật toán CIDv1 chuẩn `raw-leaves`, đã kiểm chứng khớp bit-for-bit với vector chuẩn của IPFS: `b""` → `bafkreihdwdcefgh4dqkjv67uzcmw7ojee6xedzdetojuzjevtenxquvyku`, `b"hello world"` → `bafkreifzjut3te2nhyekklss27nh3k72ysco7y32koao5eei66wof36n5e`, `b"hello world\n"` CIDv0 → `QmT78zSuBmuS4z925WZfrqQ1qHaJ56DQaTfyMUF7F8ff5o`).
> - Giao thức HTTP thật của **Kubo RPC (`/api/v0/add`, `/api/v0/cat`, `/ipfs/{cid}`)** và **Pinata Cloud (`/pinning/pinFileToIPFS`, `/data/testAuthentication`, Gateway)** đã được kiểm thử đầy đủ qua HTTP transport adapter trong `tests/test_h03_ipfs.py`.
> - **Cập nhật đối chiếu ghim sống Kubo thật (đã hoàn tất ở Q03/Q04)**: Quân đã kiểm chứng end-to-end tầng `src.ipfs` của H03 chạy trực tiếp trên **IPFS Kubo `v0.43.2`** (`PeerID = 12D3KooWFjaQAjmQAVzaBx2cNB6Gv65GwZTnuT6VkJ6siE5C1xEP`, `provider = "kubo"`, **`enable_local_fallback = False`**), ghim đệ quy thành công `4/4` hồ sơ thật kèm 2 ảnh mở trực tiếp trên Kubo Gateway tại [`reports/Quan/q03_q04_ipfs_e2e_validation.md`](../Quan/q03_q04_ipfs_e2e_validation.md). Khi cần ghim lại 4 file mẫu tĩnh của H03 lên daemon cục bộ, chỉ cần chạy `python scripts/verify_h03_ipfs.py --mode live`.

| Loại hồ sơ | Định dạng | Quyền / Mã hóa | File mẫu | Mã CIDv1 (Payload lưu IPFS) | SHA-256 Plaintext | Trạng thái dữ liệu |
|---|---|---|---|---|---|---|
| **Loan Agreement** | PDF | `PRIVATE` (`AES-256-GCM`) | [`loan_agreement_sample.pdf`](../../ipfs_storage/samples/loan_agreement_sample.pdf) / [bản mã](../../ipfs_storage/samples/loan_agreement_sample.encrypted.json) | `bafkreihkemritep5uxob6ymkzsc5n6qcf3yxwhzrspct2hyukxa46xthfu` | `44960ce49b66a8c45a2181f2d86895020d06a204f0c7955f1409383bab2b355c` | `SIMULATED` (`tx_hash: null`) |
| **Credit Report** | JSON | `PRIVATE` (`AES-256-GCM`) | [`credit_report_sample.json`](../../ipfs_storage/samples/credit_report_sample.json) / [bản mã](../../ipfs_storage/samples/credit_report_sample.encrypted.json) | `bafkreibrhtjgbutfb7axl2irz3ublip72ldhce3jngpdd3jhn2gcxsrll4` | `96b8a8ea7e2b1e934e8f688811fdd5a8d88a5baf66aec81402c5d464af5f41aa` | `SIMULATED` |
| **Audit Logs** | JSON / CSV | `PUBLIC` (Không mã hóa) | [`audit_logs_sample.json`](../../ipfs_storage/samples/audit_logs_sample.json) / [CSV](../../ipfs_storage/samples/audit_logs_sample.csv) | `bafkreiaubcy6lpxuh3fe3746ey2zubeb7cevnk3yaby3fjv6da7b3dqenm` | `1408b1e5bef43eca4dff9e26359a0481f88956ab780071b2a6be183e1d8e046b` | `SIMULATED` (6 tháng seed) |
| **Collateral Proof *(tùy chọn)*** | PNG | `PRIVATE` (`AES-256-GCM`) | [`collateral_proof_sample.png`](../../ipfs_storage/samples/collateral_proof_sample.png) / [bản mã](../../ipfs_storage/samples/collateral_proof_sample.encrypted.json) | `bafkreibtrlkzopzrkijgrjh466ye3zf5mvaxiftuvge3i46am62o35toee` | `812b0008182d16bb70d674810ea111258152a8b14fae1b043c73ecdcd1a85a95` | `SIMULATED` |

---

## 3. Minh chứng Kiểm thử Bảo mật, Mã hóa & Phân quyền RBAC

1. **Chứng minh "biết CID không đọc được bản rõ"**:
   - Gọi `retrieve_raw_by_cid()` trực tiếp với CID của `CREDIT_REPORT` và `LOAN_AGREEMENT` chỉ trả về JSON envelope chứa `ciphertext_b64`, `nonce_b64`, `key_salt_b64`, `aad_b64`.
   - Không chứa chuỗi nhạy cảm (`LOAN-SAMPLE-001`, `"score": 760`, header `%PDF-`), không chứa `DOCUMENT_AES_KEY_HEX` hay DEK.
2. **Chứng minh chống giả mạo AES-256-GCM**:
   - Sinh `nonce` 12 bytes và `salt` 16 bytes ngẫu nhiên mới ở mỗi lần mã hóa (mã hóa cùng dữ liệu 2 lần ra 2 bản mã hoàn toàn khác nhau).
   - Dùng sai khóa chủ, sửa 1 bit trong `ciphertext_b64`, hoặc đổi `owner_wallet` (sai lệch AAD) đều bị chặn bởi `DecryptionError` (`InvalidTag`).
3. **Kết quả 20/20 kiểm tra RBAC** (chi tiết tại [`h03_ipfs_verification.json`](h03_ipfs_verification.json)):

| Hồ sơ | `GUEST` | `LENDER A (#1)` | `BORROWER B (#5)` | `BORROWER A (#2 – Chủ)` | `ADMIN (#0)` |
|---|---|---|---|---|---|
| `LOAN_AGREEMENT` (PDF) | `401` (Chặn) | `403` (Chặn) | `403` (Chặn) | `200` (Giải mã + Khớp SHA-256) | `200` (Giải mã + Khớp SHA-256) |
| `CREDIT_REPORT` (JSON) | `401` (Chặn) | `403` (Chặn) | `403` (Chặn) | `200` (Giải mã + Khớp SHA-256) | `200` (Giải mã + Khớp SHA-256) |
| `AUDIT_LOGS` (JSON) | `200` (Công khai) | `200` (Công khai) | `200` (Công khai) | `200` (Công khai) | `200` (Công khai) |
| `COLLATERAL_PROOF` (PNG) | `401` (Chặn) | `403` (Chặn) | `403` (Chặn) | `200` (Giải mã + Khớp SHA-256) | `200` (Giải mã + Khớp SHA-256) |

---

## 4. Trạng thái Tích hợp & Bước Tiếp theo

- **Ghim sống lên IPFS Kubo thật**: **Đã được kiểm chứng E2E bởi Quân (`Q03`/`Q04`)** trên Kubo `v0.43.2` với `enable_local_fallback = False`, `4/4` recursive pin và 2 ảnh Gateway tại [`reports/Quan/q03_q04_ipfs_e2e_validation.md`](../Quan/q03_q04_ipfs_e2e_validation.md) (đồng bộ tham chiếu trong [`ipfs_storage/samples/sample_cids_manifest.json`](../../ipfs_storage/samples/sample_cids_manifest.json)).
- **Quân (`Q03`, `Q04`, `Q05`)**: **Đã hoàn tất tích hợp** `src.ipfs` và `src.documents` vào các endpoint FastAPI (`/api/ipfs/create-agreement`, `/api/ipfs/credit-report/{address}`, `/api/ipfs/audit-logs`, `/api/ipfs/documents/{cid}/retrieve`) kèm xác thực chữ ký EIP-191 nonce.
- **Lâm (`L04` → `L05`)**: `L04` đã nối adapter HTTP tới các endpoint RBAC trên (20/20 kịch bản PASS); bước tiếp theo tại `L05`/`Q07`/`L06` là nối phiên ví MetaMask trực tiếp và chụp ảnh trình duyệt `200`/`403` + test Kubo offline.
