# Xử lý hồ sơ vay (H03)

Module định nghĩa schema chuẩn và bộ sinh tài liệu bàn giao từ **Hùng (`H03`)** cho **Quân (`Q03`, `Q04`)**:

- [`schemas.py`](schemas.py): Schema Pydantic v2 cho `LoanAgreementPayload`, `LoanTxBindingRecord`, `CreditReportDocument`, `AuditLogsDocument` (+ xuất CSV) và `EncryptedEnvelopeSchema`, đồng bộ hằng số từ `backend/config/constants.py` (`HI01`).
- [`loan_agreement_template.py`](loan_agreement_template.py): Template ReportLab sinh file PDF *Thỏa thuận vay vốn phi tập trung* (không ghi `txHash` giả trước khi `borrow()` xác nhận).
- [`collateral_proof_template.py`](collateral_proof_template.py): Bộ sinh ảnh PNG minh chứng tài sản thế chấp tùy chọn (bổ sung định dạng ảnh thứ 3 cùng PDF/JSON).
