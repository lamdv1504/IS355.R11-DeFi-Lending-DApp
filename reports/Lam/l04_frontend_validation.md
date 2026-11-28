GATE: OPEN 24 (rounds used up)

# L04 — IPFS Document Hub và Analytics

Ngày 28/11/2026 (Asia/Saigon). Lâm, giai đoạn 3. Nhánh `feature/lam-l04-ipfs-hub`, phát triển tiếp từ L03.

## Phạm vi đã triển khai

Đã đọc sheet Lam hàng 5, H5 trong kế hoạch: L04 phụ thuộc H03, Q03, Q04; kết nối ví/backend toàn ứng dụng thuộc L05. Đã kiểm tra đủ module, schema, manifest và bàn giao của Hùng/Quân; Q05 cũng đã có endpoint runtime để adapter sử dụng. Không thiếu file phụ thuộc của thành viên khác.

- `/documents/`: ba nhóm Loan Agreement PDF, Credit Report JSON, Audit Logs; tìm CID, xem dữ liệu, tải PDF/JSON/CSV và kiểm tra SHA-256.
- Biểu mẫu tạo và lưu hồ sơ dùng generator Q05. PDF/report riêng tư được mã hóa phía backend trước khi lưu; không tạo CID/txHash giả.
- `/analytics/`: hai biểu đồ Recharts — cột APY gửi/vay theo tháng và thanh ngang cho MyUSDT/thế chấp/nợ gốc/lãi vay. Bộ lọc 3/6/12 tháng, tooltip và bảng dữ liệu; phân biệt SIMULATED/ON_CHAIN.
- Menu dùng chung dẫn tới đủ bốn màn hình. Giữ navy, Be Vietnam Pro, bề mặt phẳng và nút pill của giao diện hiện tại.
- Sample mặc định chỉ phân phối Audit Logs công khai và bản mã private. Hồ sơ riêng tư thực tế lấy qua backend có phiên xác thực; không cấp quyền giả bằng bộ chọn role ở client.

[Hướng dẫn chạy, API và bàn giao](../../docs/Lam/l04_ipfs_hub_analytics.md).

## Xác minh

| Kiểm tra | Kết quả |
| --- | --- |
| Frontend unit/regression | PASS 52/52 — 22 L04 và 30 L02/L03 |
| H03/Q03/Q04/Q05 pytest | PASS 29/29 |
| TypeScript adapter → Q05 HTTP | PASS 20/20: Guest/Lender/Other Borrower/Owner/Admin × PDF/Credit/Audit JSON/CSV |
| ESLint | PASS trên source cuối |
| Production build / TypeScript | PASS, static export cả bốn màn hình |
| HTTP bản cuối | PASS: 4 route và 27 tài nguyên, [JSON](l04/http-smoke.json) |
| Ảnh responsive | Hai trang tại 1440/1024/768/390/320px |
| IPFS Hub performance | 0 FAIL, 4 WARN (1440/390px, 3 lần tải) |
| Analytics performance | 2 FAIL, 4 WARN (1440/390px, 3 lần tải) |
| Taste Gate | GATE: OPEN 24 (rounds used up) |
| Documents consistency đầy đủ | 89 FAIL, 29 WARN (chưa PASS) |
| Analytics consistency đầy đủ | 82 FAIL, 21 WARN (chưa PASS) |

[API/RBAC JSON](l04/api-rbac.json) dùng **FastAPI Q05 thật, adapter TypeScript thật và kho mã hóa IPFS tạm**. Ví test được tạo ngẫu nhiên; Web3 events là test double. Đây là bằng chứng HTTP/auth/mã hóa/đối chiếu nội dung, không phải kiểm thử RPC/Kubo/Pinata/MetaMask thật. Không ghi token hoặc khóa vào báo cáo.

Các kiểm tra thực tế của Documents: `assets`: PASS; `links`: PASS; `off-viewport`: PASS; `spill`: PASS; `cut-text`: PASS; `collide`: PASS; `tap-size`: PASS; `text-contrast`: PASS; `contrast`: PASS; `heading-order`: PASS; `field-label`: PASS; `focus-visible`: PASS; `focus-hidden`: PASS; `reduced-motion`: PASS; `hover-spill`: PASS; `hidden-content`: PASS.

Các kiểm tra thực tế của Analytics: `assets`: PASS; `links`: PASS; `off-viewport`: PASS; `spill`: PASS; `cut-text`: PASS; `collide`: PASS; `tap-size`: PASS; `text-contrast`: PASS; `contrast`: PASS; `heading-order`: PASS; `field-label`: PASS; `focus-visible`: PASS; `focus-hidden`: PASS; `reduced-motion`: PASS; `hover-spill`: PASS; `hidden-content`: PASS.

Không coi số lượng assertion, ảnh hoặc checklist là điểm rubric đạt được.

## Quyền truy cập và toàn vẹn

- Guest/private nhận 401, nhắc ký xác thực ví.
- Ví khác hoặc Lender nhận 403, hiển thị “Không có quyền truy cập”.
- Owner/Admin nhận nội dung qua backend sau kiểm quyền, giải mã và đối chiếu hash.
- Audit Logs public cho Guest đọc. Khi API lỗi, UI báo lỗi và không dùng sample để thay dữ liệu.
- Token chỉ giữ trong bộ nhớ của trang; đổi nguồn/token xóa preview và hủy request cũ. Không gửi private key hoặc lưu plaintext private trong static assets.
- CID mẫu lấy nguyên từ H03. Sample dùng local_store, chưa có bằng chứng public pin sống.

PDF/CSV dùng nguyên byte response và đối chiếu SHA-256 tại browser. Q05 trả JSON qua wrapper `{cid, sha256, content}`; UI ghi rõ backend xác minh hash gốc, đồng thời tính riêng hash JSON xuất tải. Không đánh đồng hash của serialization mới với hash IPFS gốc.

Credit Report đọc đúng score/summary/history lồng trong schema Q04. Hai biểu đồ giữ WAD dạng chuỗi cho số dư chính xác; Number chỉ phục vụ vẽ. Nợ và lãi vay là nghĩa vụ, không cộng vào tổng tài sản. APY quy đổi ghép lãi hằng ngày được tách khỏi APR đơn theo giây.

## Hiệu năng và giới hạn

[Documents performance](l04/documents-performance.json) · [Analytics performance](l04/analytics-performance.json).

- IPFS Hub — 1440px: total transfer 373 KiB (PASS), JS parsed 537.5 KiB (WARN), font bytes 180.4 KiB (WARN), layout shift 0.000 (PASS), broken requests 0 (PASS); 390px: total transfer 372.6 KiB (PASS), JS parsed 537.5 KiB (WARN), font bytes 180.4 KiB (WARN), layout shift 0.000 (PASS), broken requests 0 (PASS)
- Analytics — 1440px: total transfer 501.2 KiB (PASS), JS parsed 972.1 KiB (FAIL), font bytes 180.4 KiB (WARN), layout shift 0.000 (PASS), broken requests 0 (PASS); 390px: total transfer 500.8 KiB (PASS), JS parsed 972.1 KiB (FAIL), font bytes 180.4 KiB (WARN), layout shift 0.000 (PASS), broken requests 0 (PASS)

Đổi APY từ LineChart sang BarChart đã giảm JS parsed từ 994,9 xuống 972,1 KiB; ngưỡng FAIL của Taste là trên 900 KiB.

Analytics còn một vấn đề budget JS, được ghi FAIL tại hai viewport. Dù thời gian vẽ/CLS và request không hỏng, kết quả này **không phải PASS toàn bộ**. Chưa thay framework hoặc thư viện đã chốt chỉ để đổi số kiểm tra. Các kết quả CPU local không phải Core Web Vitals ngoài thực tế.

## Taste và các mục còn mở

Dùng [SKILL.md đã đọc](C:/Users/ASUS/.codex/plugins/cache/taste-skill/taste-skill/2.5.1/skills/taste-skill/SKILL.md), tái lập nguồn theo [skills-lock.json](../../frontend/skills-lock.json). Gate đã chạy đúng 3 vòng; không reset vòng, sửa checker hoặc giấu nội dung. Quy định tại `references/gate.md`: “At the last round the gate says once ‘rounds used up’: stop fixing, put the open FAILs in the report, finish.”

Kết quả cuối: **GATE: OPEN 24 (rounds used up)**. Báo cáo giữ nguyên các phát hiện còn mở; không tuyên bố đạt toàn bộ Taste.

Danh sách **tất cả mục Gate còn mở**, vị trí, hướng sửa và các waiver nằm trong [gate-final.txt](l04/gate-final.txt). Kết quả đầy đủ từng trang: [Documents log](l04/documents-consistency.txt), [Analytics log](l04/analytics-consistency.txt); JSON tương ứng cũng được lưu trong thư mục l04.

Nhóm Gate còn mở: `button-styles`, `container`, `container-edges`, `copy-headings`, `cta`, `flush`, `hero-screen`, `no-visual`, `one-heading`, `one-section`, `section-air`, `section-gaps`, `section-height`.

Năm miễn trừ đã khai báo:

- `nav` — `(the first screen)`: L04 extends the existing application sidebar shared by L02/L03. Its four functional routes are the requested navigation; this is not a marketing navigation bar.
- `moment-none` — `(the page)`: L04 is the actual document search and authorization workspace. Existing user-approved flat navy UI takes priority over an unrelated marketing scroll scene.
- `hero-fill` — `main#main-content > div.hub-connection`: The requested CID search and document list must be visible immediately in this operational app; a full-screen promotional hero would displace its main controls.
- `hero-screen` — `main#main-content > div.page-heading.hub-heading`: The compact application title intentionally leaves room for CID retrieval on the first screen, consistent with the existing app and design reference.
- `text-only` — `main#main-content > section.panel.hub-audit`: This is the requested actual audit data table with rates, utilization and provenance. Replacing data with a decorative photograph or UI mock would reduce the utility of this app screen.

Các phát hiện về hero trọn màn hình, footer trọn màn hình, khoảng trống theo trang giới thiệu và sidebar được giữ trong log vì đây là workspace thao tác theo giao diện hiện có. Không tự đổi các FAIL còn lại thành PASS.

Documents full check còn `forms`: checker không quan sát request từ form CID mặc định. Form chỉ gửi sau khi CID hợp lệ; adapter valid CID đã được kiểm qua HTTP. **Chưa xác minh click/submit/download end-to-end**, nên không dùng kết quả adapter để tuyên bố form browser đã được nghiệm thu.

Voice card: tiếng Việt trực tiếp, tên hành động cụ thể, nguồn và giới hạn rõ ràng. Không bịa dữ kiện thị trường, giao dịch, tên khách hàng hoặc public pin; các số mẫu lấy từ H03/L03. Không dùng ảnh stand-in, ảnh khách hàng hoặc slot ảnh còn thiếu; đối tượng thị giác là UI và dữ liệu thật của ứng dụng. Copy WARN và các phát hiện localization giữ nguyên trong raw logs.

## Ảnh bản giao diện hiện tại

| Trang | 1440 | 1024 | 768 | 390 | 320 |
| --- | --- | --- | --- | --- | --- |
| IPFS Hub | [Ảnh](l04/screenshots/documents-1440.png) | [Ảnh](l04/screenshots/documents-1024.png) | [Ảnh](l04/screenshots/documents-768.png) | [Ảnh](l04/screenshots/documents-390.png) | [Ảnh](l04/screenshots/documents-320.png) |
| Analytics | [Ảnh](l04/screenshots/analytics-1440.png) | [Ảnh](l04/screenshots/analytics-1024.png) | [Ảnh](l04/screenshots/analytics-768.png) | [Ảnh](l04/screenshots/analytics-390.png) | [Ảnh](l04/screenshots/analytics-320.png) |

Ảnh Analytics đã được chụp lại với APY cột và số dư thanh ngang, gồm 320px. Không có ảnh giả thành công/403 ở browser; bằng chứng vai trò hiện là HTTP adapter.

## Điểm nối tiếp

L05 nối MetaMask, phiên ví dùng chung, đổi account/chain/expiry và live upload/retrieve/borrow; L06 chạy kịch bản E2E browser và ảnh role 200/403. Các API balances/loan hiện là hai lần đọc riêng, chưa cam kết cùng block. Chưa xác minh live pin, gateway hoặc Sepolia trong L04.

Các thay đổi L04 được bàn giao trên nhánh `feature/lam-l04-ipfs-hub`. README tổng được giữ nguyên; CSV IPFS đã bẩn từ trước chỉ khác xuống dòng, được giữ ngoài phạm vi L04.
