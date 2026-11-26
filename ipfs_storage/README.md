# Dữ liệu mẫu, JSON Schema và Metadata IPFS (H03)

Thư mục lưu trữ cấu trúc chuẩn và dữ liệu mẫu cho 3 loại hồ sơ Tiêu chí 3 (+ ảnh PNG tùy chọn):

- `schemas/`: JSON Schema máy đọc được cho `loan_agreement`, `loan_tx_binding`, `credit_report`, `audit_logs`, `encrypted_envelope` và `rbac_matrix.json`.
- `samples/`: Hồ sơ mẫu gắn nhãn `SIMULATED` gồm PDF thỏa thuận vay, Credit Report JSON, Audit Logs JSON/CSV, Collateral Proof PNG, các bản mã `*.encrypted.json` (không chứa khóa) và `sample_cids_manifest.json`.
- `local_repo/` *(gitignored)*: Kho block content-addressed dự phòng khi chạy offline.

Sinh lại toàn bộ schema/mẫu và kiểm thử:
```powershell
python scripts/verify_h03_ipfs.py --generate-samples
```
