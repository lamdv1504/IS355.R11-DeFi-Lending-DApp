GATE: OPEN 49 (rounds used up)

# L05 — Báo cáo frontend, ví và API

Ngày: 28–29/11/2026 · Lâm · `feature/lam-l05-metamask-web3` · base `a5fde2a`.

Đã triển khai phiên MetaMask dùng chung, giao dịch xem trước/ký/xác nhận và nối bốn màn hình với Q05. Kiểm thử chức năng đạt; cổng thiết kế chưa đạt. Báo cáo này không chứng nhận đã ký qua tiện ích MetaMask thật hoặc chạy E2E trên Sepolia.

## Phụ thuộc và phạm vi

Kế hoạch Excel L05 yêu cầu L02, L03, L04, Q05, Q06. Các màn hình, auth/prepare/confirm/IPFS/pool/demo, ABI và manifest local/Sepolia đều có trong repo; không tạo file giả thay cho thành viên khác. Không đổi contract, backend hay README tổng. Tài liệu của Lâm nằm trong docs/Lam và reports/Lam.

## Kiểm tra chức năng

| Kiểm tra | Kết quả | Phạm vi |
| --- | --- | --- |
| `npm test` | 88/88 PASS | 55 bài cũ + 33 bài ví/mạng mới |
| TypeScript | PASS | `tsc --noEmit --incremental false`; bản Next build cuối cũng kiểm tra TypeScript |
| `npm run lint` | PASS | Sau toàn bộ thay đổi mã nguồn cuối |
| `npm run build` | PASS | Xuất tĩnh bốn trang và trang hệ thống |
| `python scripts/verify_l05_frontend_api.py` | 9/9 PASS | Q05 HTTP/auth/PDF/confirm thật; EIP-1193 và RPC/receipt là test double |
| `git diff --check` | Đã kiểm tra | Không có lỗi whitespace; Git có thông báo chuyển LF/CRLF theo cấu hình máy |

Các bài mới kiểm tra EIP-191 bytes/signer, từ chối ký, payload khác chain/from/to/value/calldata/gas, allowance sai token/amount, approve riêng, NFT ID 0, thứ tự PDF/CID, binding sai CID, receipt revert, timeout/API outage và retry không broadcast lại, đổi ví/mạng/API/mode, session hết hạn/401, response đến muộn và chặn demo giá/thời gian trên Sepolia.

Chi tiết HTTP: [api-wallet.json](l05/api-wallet.json). Tài khoản test được sinh ngẫu nhiên; key chỉ đi qua môi trường tiến trình test, không ghi vào bundle hoặc báo cáo. Route `__l05_test__` chỉ được thêm vào instance FastAPI test cô lập.

- real Q05 nonce/signature/verify establishes wallet-bound session.
- prepare discovers missing allowance without broadcasting.
- approve exact Pool/amount is signed and checked by Q05 confirm.
- fresh deposit quote passes canonical calldata/gas validation and confirms.
- real Q03 creates encrypted PDF/CID before borrow is signed.
- Q05 verifies LoanBorrowed event and persists Q03 CID/tx binding.
- same signed session retrieves/decrypts owner PDF and browser verifies SHA-256.
- private PDF stays protected from unauthenticated retrieval.
- post-confirm refresh reads selected local network metadata.

## Trình duyệt và thiết kế

Dùng taste-skill 2.5.1 theo yêu cầu trước đó. Kind `software`, category `cho vay MyUSDT`, primary `Kết nối MetaMask`. Giữ palette navy/xanh dương, nền trung tính, Be Vietnam Pro 400/500/600/700 cục bộ, panel phẳng và nút pill theo thiết kế đã có và design.md. Không rút một hero/palette quảng cáo mới cho phần tích hợp ứng dụng.

Voice: tiếng Việt trực tiếp, gọi rõ ví/mạng/CID, tiền WAD chính xác, APR và APY có nguồn; không thêm cam kết lợi nhuận. Tên DeFi Lending và logo hiện có được giữ lại. Không đặt tên thương hiệu mới, không dùng ảnh đứng chỗ, không có slot ảnh khách hàng hoặc form gửi email/.example. Các con số đến từ API hoặc được đánh dấu mô phỏng; chưa có domain triển khai chính thức.

Chỉ dùng script headless của skill, từng Chrome riêng và tuần tự. Layout checker được chạy tại 1440×900, 1024×768, 820×1180, 768×1024, 390×844, 320×740. Bốn trang có ảnh desktop/mobile. Đã xem các ảnh để kiểm tra chữ, xuống dòng và các trạng thái chưa kết nối. Ảnh vòng đầu và các profile nằm tại `frontend/.taste-skill/l05/` (QA cục bộ, đang ignored). Các ảnh vòng đầu có trước sửa nhãn mạng/contrast/lề; gate vòng 2 kiểm tra lại bản cuối ở 1440/390 và quét 320. Vòng 3 áp dụng waiver lên kết quả không đổi của vòng 2 theo cache của gate.

Đã sửa nhãn mạng thành nhãn nhìn thấy được, tăng tương phản chữ hướng dẫn, căn lề toolbar mobile, hiển thị đúng API source trong Analytics và tách tải Recharts khi có dữ liệu vị thế. Danh sách FAIL cuối không còn `field-label`, `text-contrast` hoặc `off-grid`. Không thấy overflow/collision trong các ảnh đã xem; không coi đây là kiểm thử tương tác MetaMask.

Layout checker độc lập không đạt: các nhóm edge-left, screen-short/screen-height, neighbour, hero-fold còn chỉ ra khác biệt với quy tắc một section mỗi màn hình. Gate còn các cảnh báo về khoảng cách, grid, empty state, heading và phần hình ảnh. Giữ dashboard hiện có trong phạm vi L05; không đánh dấu các lỗi chưa waiver là PASS.

Giới hạn vòng kiểm tra: [SKILL.md](C:/Users/ASUS/.codex/plugins/cache/taste-skill/taste-skill/2.5.1/skills/taste-skill/SKILL.md:278) quy định “three rounds at most”. Đã dừng chỉnh thiết kế sau vòng 3 và lưu toàn bộ kết quả, không reset gate hoặc sửa kit.

Kết quả thô: [vòng 1](l05/gate-round-1.json), [vòng 2](l05/gate-round-2.json), [gate cuối](l05/design-gate.json), [waiver cụ thể](l05/design-waivers.json).

### Năm waiver đã áp dụng

| Check | Vị trí | Lý do |
| --- | --- | --- |
| hero-fill | main#main-content > div.live-mode-notice "KẾT NỐI THẬT Hardhat local · chain 31337" | This is the wallet/network status of an operational dashboard. Balances and transaction controls intentionally share the first screen with its compact heading, following the user's existing application. |
| button-styles | (one screen) | The extra style identified here is the existing DeFi Lending brand link, not an action button. The real actions retain the approved primary and secondary pill styles. |
| cta | section#activity "Giao dịch trong phiên" | This section is the real in-memory transaction journal. An empty guest journal has no transaction to confirm or retry; conditional retry actions appear only for actual pending transactions. |
| moment-none | (the page) | L05 extends the user's existing operational lending dashboard and approved navy design. A decorative marketing scroll scene would displace wallet, balance and transaction controls. |
| hero-screen | main#main-content > section.page-heading "CHO VAY MYUSDTTổng quan cho vay.Vốn, lãi" | The application heading is intentionally compact so users can reach wallet and lending data immediately. The user requested integration into the existing dashboard, not a full-screen promotional hero. |

### Toàn bộ 49 FAIL còn mở

| Check | Rộng (px) | Vị trí và phát hiện |
| --- | --- | --- |
| flush | 1440 | main#main-content > section.page-heading > div > p "Vốn, lãi và NFT vị thế từ mạng đang kết " — its last line sits 3px above the rule on top of div.live-mode-notice |
| flush | 1440, 390 | main#main-content > section.kpi-grid > article.kpi-card.kpi-featured "Supply APY tham khảo — APR — / năm" — its first line sits 0px under the top edge of section.kpi-grid, where the ground changes |
| flush | 1440 | form#lending-operation > p.field-hint:nth-of-type(2) "Cấp quyền và thao tác chính là hai giao " — its last line sits -393px above the rule on top of section.panel.liquidity-panel |
| button-styles | 1440, 390 | (the page) — 4 button styles on the page: label and disc, fill #122b50 x1 ("DeFi Lending"); pill, outline #e0e5ed x2 ("Dữ liệu mẫu"); pill, fill #245bd6 x2 ("Kết nối MetaMask"); pill, fill #f6f7f9, outline #e0e5ed x5 ("Nhận 1.000 MyUSDT") |
| copy-headings | 1440 | h2#live-liquidity-title "Thanh khoản và lãi suất" — "Thanh khoản và lãi suất" names no product, part, place or section (2 headings like it; at most one brand line per page) (and 1 more like it: "NFT vị thế của bạn") |
| section-gaps | 1440 | main#main-content > div.overview-grid > section.panel.liquidity-panel / section#positions — 153px between these sections, +134% against the median 66px of gaps at a change of ground |
| section-gaps | 1440 | section#activity / main#main-content > footer.app-footer — 106px between these sections, +100% against the median 53px |
| section-tile | 1440, 390 | section#positions "NFT vị thế của bạn" — the section is 258px tall (0.29 screens at 1440x900), shorter than the screen: its tile, held at the page's end (scroll 964px) shows 258px of it and 199px of the next section, its heading "Thao tác demo trên mạng đã chọ" on screen |
| section-tile | 1440, 390 | section#activity "Giao dịch trong phiên" — the section is 155px tall (0.17 screens at 1440x900), shorter than the screen: its tile, held at the page's end (scroll 964px) shows 155px of it and 199px of the section above, its heading "Thao tác demo trên mạng đã chọ" on screen |
| empty-area | 1440 | section#positions "NFT vị thế của bạn" — 68% of the section is empty: 16px under its last (p.live-empty), 66% beside content that covers under half the container, in its 258px of rows (WARN over 35%, FAIL over 50%) |
| hero-screen | 1440 | main#main-content > div.live-mode-notice "KẾT NỐI THẬTHardhat local · chain 31337 " — 635px of the next section shows on the first screen (from 265px on a 900px screen): nothing below the hero shows at load (SR-1) |
| section-height | 1440 | main#main-content > div.live-read-status.error "Không kết nối được API. Kiểm tra địa chỉ" — the section is 44px tall (0 screens), 856px short of one screen (900px): every section after the hero is one screen or two, 2px either way (SR-2) |
| section-air | 1440 | main#main-content > div.live-mode-notice / main#main-content > div.live-read-status.error — 36px of air between the content of these two sections: 128-480px (64-600px WARN) (every gap out of the band at 1440px, top to bottom: 36px after "KẾT NỐI THẬTHardhat ", 46px after "Không kết nối được A", 78px after "Supply APY tham khảo", 102px after "Giao dịch cho vayKhả", 83px after "NFT vị thế của bạnQu", 78px after "CÔNG CỤ THỬ NGHIỆMTh") (SR-3) |
| section-air | 1440 | main#main-content > div.live-read-status.error / main#main-content > section.kpi-grid — 46px of air between the content of these two sections: 128-480px (64-600px WARN) (SR-3) |
| one-section | 1440 | h2#live-demo-title "Thao tác demo trên mạng đã chọn" — the screen at scroll 900px (stride 1) shows 199px of section 7 and the heading of section 7 whole and the content of 4 sections, over 24px each beside section 6: a screen shows one section (another may peek 8px, 24px WARN) (SR-4) |
| one-section | 1440 | main#main-content > section.page-heading > div > h1 "Tổng quan cho vay." — the screen at scroll 0px (stride 0) shows 182px of section 4 and the heading of section 1 whole and the content of 5 sections, over 24px each beside section 5: a screen shows one section (another may peek 8px, 24px WARN) (and 2 more like it: scroll 120px, scroll 265px) (SR-4) |
| one-heading | 1440 | h2#live-liquidity-title "Thanh khoản và lãi suất" — the section holds 2 h2 headings: one per section, first in its .wrap (SR-5) |
| one-heading | 1440 | h2#live-positions-title "NFT vị thế của bạn" — headings of two sections show whole on one screen at 14 of 20 scroll positions (70%; at scroll 300, 350, 400, 450px), here with "Giao dịch cho vay": at most 3% on a desktop (SR-5) |
| container-edges | 1440 | div.app-shell.live-shell > div.workspace > header.topbar "Ứng dụng /Cho vayDữ liệu mẫuMạngLocal · " — the nav's content runs 288px from the left and 40px from the right (read from its outermost blocks: no .wrap): 288 and 40px are not one margin; the margin is 64-120px at 1440px (one container, equal margins, 2px either way) (SR-6) |
| container-edges | 1440 | main#main-content > section.page-heading "CHO VAY MYUSDTTổng quan cho vay.Vốn, lãi" — the content of section 1 runs 288px from the left and 40px from the right (read from its outermost blocks: no .wrap): 288 and 40px are not one margin; the margin is 64-120px at 1440px (one container, equal margins, 2px either way) (SR-6) |
| container-edges | 1440 | main#main-content > div.live-read-status.error "Không kết nối được API. Kiểm tra địa chỉ" — the content of section 3 runs 288px from the left and 40px from the right (read from its outermost blocks: no .wrap): 288 and 40px are not one margin; the margin is 64-120px at 1440px (one container, equal margins, 2px either way) (and 7 more like it: "Supply APY tham khảo—APR", "NFT vị thế của bạnQuyền ", "CÔNG CỤ THỬ NGHIỆMThao t") (SR-6) |
| container-edges | 1440 | div.app-shell.live-shell "Đến nội dung chínhDeFi LendingKHÔNG GIAN" — a <div> at the top of the page, outside header.nav, main, footer.closing and nav.actionbar (SR-6) |
| container-edges | 1440 | h2#live-liquidity-title "Thanh khoản và lãi suất" — the h2 starts 762px right of the container's left: every h1 and h2 starts on it, 2px either way (SR-6) |
| container-edges | 1440 | h2#live-positions-title "NFT vị thế của bạn" — 10 text blocks start on a left line at x 313, 25px from the container's left: text starts on the container's left, or on one split line (x 761, 856, 951) (also "Quyền hưởng vốn và lãi theo chủ ", "Kết nối ví để đọc dữ liệu tài kh", "Kết nối ví để xem các NFT thuộc ") (and 3 more like it: "Giao dịch cho vay", "NFT vị thế của bạn", x 299) (SR-6) |
| container-edges | 1440 | main#main-content > div.overview-grid > section.panel.live-form-panel "Giao dịch cho vayKhả dụng — MyUSDTGửiRút" — a box over half the container wide runs 288-1001px, not on the container's lines at 288-1400px (SR-6) |
| flush | 390 | main#main-content > section.page-heading > button.button.secondary "Gửi tiền" — its button sits 0px above the rule on top of div.live-mode-notice |
| flush | 390 | main#main-content > section.kpi-grid > article.kpi-card:nth-of-type(4) "Lãi đã tích lũy — MyUSDT · đọc từ contra" — its last line sits 0px above the lower edge of section.kpi-grid, where the ground changes to section.panel.live-form-panel |
| no-visual | 390 | main#main-content > section.kpi-grid "Supply APY tham khảo — APR — / năm Tổng " — no picture, effect or mock in this section; a feature section needs a visual |
| no-visual | 390 | main#main-content > div.overview-grid > section.panel.live-form-panel "Giao dịch cho vay" — no picture, effect or mock in this section; a feature section needs a visual |
| no-visual | 390 | main#main-content > div.overview-grid > section.panel.liquidity-panel "Thanh khoản và lãi suất" — no picture, effect or mock in this section; a feature section needs a visual |
| no-visual | 390 | section#positions "NFT vị thế của bạn" — no picture, effect or mock in this section; a feature section needs a visual |
| no-visual | 390 | main#main-content > section.panel.live-demo "Thao tác demo trên mạng đã chọn" — no picture, effect or mock in this section; a feature section needs a visual |
| section-gaps | 390 | main#main-content > div.live-read-status.error / main#main-content > section.kpi-grid — 24px between these sections, -65% against the median 69px |
| edge-left | 1440 | div.live-mode-notice p "Hardhat local · chain 31337 · Gi" — starts at x 436.1; the lines are 288 and the column starts |
| edge-left | 1440 | div.live-mode-notice p "Kết nối ví để xem vị thế và ký x" — starts at x 305; the lines are 288 and the column starts |
| edge-left | 1440 | div.overview-grid section.panel.liquidity-panel "Thanh khoản và lãi suấtKHẢ DỤNG " — starts at x 1024.8; the lines are 288 and the column starts |
| screen-short | 1440, 390 | section.page-heading section.page-heading "CHO VAY MYUSDTTổng quan cho vay." — 117px tall; one screen under the nav is 900px |
| neighbour | 1440, 390 | section.page-heading section.page-heading "CHO VAY MYUSDTTổng quan cho vay." — framed, 38px of section.kpi-grid section.kpi-grid "Supply APY tham khảo—APR — / năm" shows |
| screen-short | 1440, 390 | section.kpi-grid section.kpi-grid "Supply APY tham khảo—APR — / năm" — 182px tall; one screen under the nav is 900px |
| screen-height | 1440, 390 | section.kpi-grid section.kpi-grid "Supply APY tham khảo—APR — / năm" — 182px, 0.20 screens; a section is exactly one or two (--h) |
| neighbour | 1440 | section.kpi-grid section.kpi-grid "Supply APY tham khảo—APR — / năm" — framed, 49px of #positions section.panel.positions-panel "NFT vị thế của bạnQuyền hưởng vố" shows |
| screen-short | 1440, 390 | #positions section.panel.positions-panel "NFT vị thế của bạnQuyền hưởng vố" — 258px tall; one screen under the nav is 900px |
| neighbour | 1440, 390 | #positions section.panel.positions-panel "NFT vị thế của bạnQuyền hưởng vố" — framed, 48px of section.panel.live-demo section.panel.live-demo "CÔNG CỤ THỬ NGHIỆMThao tác demo " shows |
| screen-short | 1440, 390 | section.panel.live-demo section.panel.live-demo "CÔNG CỤ THỬ NGHIỆMThao tác demo " — 199px tall; one screen under the nav is 900px |
| screen-height | 1440, 390 | section.panel.live-demo section.panel.live-demo "CÔNG CỤ THỬ NGHIỆMThao tác demo " — 199px, 0.22 screens; a section is exactly one or two (--h) |
| neighbour | 1440, 390 | section.panel.live-demo section.panel.live-demo "CÔNG CỤ THỬ NGHIỆMThao tác demo " — framed, 80px of #activity section.panel.live-activity "Giao dịch trong phiênChưa có gia" shows |
| screen-short | 1440, 390 | #activity section.panel.live-activity "Giao dịch trong phiênChưa có gia" — 155px tall; one screen under the nav is 900px |
| hero-fold | 1440, 390 | section.page-heading section.page-heading "CHO VAY MYUSDTTổng quan cho vay." — starts at y 120, not under the nav |
| hero-fold | 1440, 390 | section.kpi-grid section.kpi-grid "Supply APY tham khảo—APR — / năm" — shows on the first screen from y 466 |

### Toàn bộ WARN được giữ

Các cảnh báo dưới đây được giữ nguyên để người xem đánh giá; không nâng chúng thành PASS. Cảnh báo API phản ánh backend cổng 8000 chưa chạy trong phép đo trình duyệt. Cảnh báo copy/heading/rhythm được giữ cùng nhãn chức năng tiếng Việt và bố cục ứng dụng đã có; không dùng số liệu mẫu để làm đầy các trạng thái chưa đọc được. Danh sách này bao gồm mọi WARN copy-lint/checker và các giả định mà công cụ ghi trong kết quả.

| Check | Rộng (px) | Vị trí và phát hiện |
| --- | --- | --- |
| assets | 1440 | (the page) — the data file http://127.0.0.1:8000/api/pool?network=local did not load (ERR_CONNECTION_REFUSED): the connection dropped, a network blip and not the page; run the check again |
| flush | 1440 | main#main-content > div.live-mode-notice > p:nth-of-type(1) "Hardhat local · chain 31337 · Giao dịch " — its first line sits 22px under the top edge of div.live-mode-notice, where the ground changes |
| flush | 1440 | main#main-content > div.live-mode-notice > p:nth-of-type(2) "Kết nối ví để xem vị thế và ký xác thực " — its last line sits 20px above the lower edge of div.live-mode-notice, where the ground changes to div.live-read-status.error |
| flush | 1440 | h2#lending-form-title "Giao dịch cho vay" — its first line sits 26px under the top edge of section.panel.live-form-panel, where the ground changes |
| flush | 1440 | h2#live-positions-title "NFT vị thế của bạn" — its first line sits 26px under the top edge of section#positions, where the ground changes |
| flush | 1440 | main#main-content > section.panel.live-demo > div:nth-of-type(1) > p.eyebrow "CÔNG CỤ THỬ NGHIỆM" — its first line sits 26px under the top edge of section.panel.live-demo, where the ground changes |
| flush | 1440 | main#main-content > section.panel.live-demo > p.field-hint "Faucet và đổi giá là giao dịch cần ký. T" — its last line sits 28px above the lower edge of section.panel.live-demo, where the ground changes to section#activity |
| flush | 1440 | h2#activity-title "Giao dịch trong phiên" — its first line sits 26px under the top edge of section#activity, where the ground changes |
| copy-buttons | 1440 | header.topbar > div.topbar-right > div.wallet-toolbar > button.wallet-mode "Dữ liệu mẫu" — "Dữ liệu mẫu" does not start with a verb (book, buy, try, start, get, see...) (and 7 more like it: "Kết nối MetaMask", "Gửi tiền", "Xem trước giao dịch", "Tua 30 ngày", ...) |
| copy-actions | 1440 | (the page) — the main action "Kết nối MetaMask" does not read word for word the same in the closing section |
| heading-scale | 1440, 390 | main#main-content > div.overview-grid > section.panel.liquidity-panel > div.liquidity-value "—MyUSDT" — 1 line of plain text set larger than the section headings (36px against h2 18px) |
| off-grid | 1440 | h2#live-liquidity-title "Thanh khoản và lãi suất" — the section's heading starts at 1050px, 762px off the page margin (288px), and no other section starts there |
| body-size | 1440, 390 | main#main-content > div.live-read-status.error > p "Không kết nối được API. Kiểm tra địa chỉ" — 7 of 7 paragraphs of running text are set under 16px (13, 14px) |
| section-gaps | 1440 | main#main-content > div.live-read-status.error / main#main-content > section.kpi-grid — 33px between these sections, -38% against the median 53px |
| section-gaps | 1440, 390 | main#main-content > div.overview-grid > section.panel.live-form-panel / main#main-content > div.overview-grid > section.panel.liquidity-panel — the sections overlap by 367px |
| section-gaps | 1440 | section#positions / main#main-content > section.panel.live-demo — 83px between these sections, +57% against the median 53px |
| section-gaps | 1440 | main#main-content > section.panel.live-demo / section#activity — 78px between these sections, +47% against the median 53px |
| nav-labels | 1440 | div.app-shell.live-shell > aside.sidebar > nav.main-nav > a:nth-of-type(6) "Hoạt động" — "Hoạt động" opens a section headed "Giao dịch trong phiên" |
| label-centre | 1440 | div.app-shell.live-shell > aside.sidebar > a.brand "DeFi Lending" — its label sits 39px off-centre (0px of room at the left, 39px at the right) |
| stranded-action | 1440 | main#main-content > section.page-heading > button.button.secondary "Gửi tiền" — stands 605px across from the nearest text of its block ("Tổng quan cho vay.") |
| one-screen | 1440 | main#main-content > div.overview-grid > section.panel.live-form-panel "Giao dịch cho vay" — 2 sections are shorter than the screen, so the next one's heading or picture shows with them: "Giao dịch cho vay" is 420px of the 900px under the nav, and "Thanh khoản và lãi suất" shows below it ("Thanh khoản và lãi s") |
| skip-link | 1440 | div.app-shell.live-shell:nth-of-type(2) > a.skip-link "Đến nội dung chính" — the first Tab stop is "Đến nội dung chính", not a skip link: a keyboard user tabs through the whole nav on every visit |
| share-meta | 1440 | head — the head lacks og:title, og:description, og:image, twitter:card, theme-color: a shared link shows no picture or title of its own |
| form-fields | 1440 | form#lending-operation — the submit button is disabled before anything is typed: it says nothing about what is missing |
| section-air | 1440 | main#main-content > section.kpi-grid / main#main-content > div.overview-grid — 78px of air between the content of these two sections: 128-480px (64-600px WARN) (SR-3) |
| section-air | 1440 | section#activity "Giao dịch trong phiênChưa có giao dịch n" — the content fills 46.5% of the section's height (72 of 155px): 55% or more (40% WARN) (SR-3) |
| nav | 390 | header.topbar > div.topbar-right > div.wallet-toolbar > button.icon-button — the nav is lopsided: its last item ends 13px inside the content's edge (370px), while its first starts on the other edge |
| button-styles | 390 | main#main-content > section.page-heading > button.button.secondary "Gửi tiền" — on the phone 2 buttons run the full width of their column, but  "Gửi tiền" is 131px of 350px: one action in two sizes |
| section-gaps | 390 | main#main-content > section.page-heading / main#main-content > div.live-mode-notice — 45px between these sections, -35% against the median 69px |
| section-gaps | 390 | main#main-content > div.live-mode-notice / main#main-content > div.live-read-status.error — 40px between these sections, -42% against the median 69px |
| section-gaps | 390 | main#main-content > section.kpi-grid / main#main-content > div.overview-grid > section.panel.live-form-panel — 43px between these sections, -38% against the median 69px |
| orphan | 390 | section#positions > div.panel-head.positions-head > div > p "Quyền hưởng vốn và lãi theo chủ sở hữu h" — its last line holds only "tại." (and 1 more like it: "Kết nối ví để xem các NF") |

## Hiệu năng

Đo bản build ba lần mỗi kích thước, lấy median. Sau tách tải biểu đồ, JavaScript parsed giảm từ 1069,8 xuống 637,8 KiB; JS gzip từ 325,9 xuống 199,1 KiB. Tổng transfer khoảng 405 KiB. JS parsed còn WARN so với ngân sách skill; giữ các thư viện Next/React/Ethers cần cho ứng dụng và tải biểu đồ theo nhu cầu. Font 180,4 KiB còn WARN, giữ đủ bốn weight Be Vietnam Pro hỗ trợ tiếng Việt theo giao diện hiện có.

Kết quả vẫn FAIL ở broken requests: một request `/api/pool?network=local` bị từ chối kết nối trong mỗi viewport do backend port 8000 chưa chạy. Không chặn request hoặc thay bằng dữ liệu giả để vượt kiểm tra. Bài HTTP cô lập xác minh API riêng. Host CPU 27/57% khiến phép đo thời gian có giới hạn độ tin cậy; đây là số đo CPU tổng hợp, không phải Core Web Vitals thực địa.

Chi tiết: [performance.json](l05/performance.json), [trước tối ưu](l05/performance-before-lazy-chart.json).

| Rộng | Kiểm tra | Giá trị | Kết quả | Ghi chú |
| --- | --- | --- | --- | --- |
| 1440 | host CPU load (before/after) | 27/57 % | WARN | busy host: timing verdicts capped at WARN, rerun when idle |
| 1440 | total transfer | 405.1 KiB | PASS | html 7.8K  css 9.5K  js 199.1K  font 180.4K  other 8.3K |
| 1440 | requests | 18 | PASS | 17 by load |
| 1440 | images bytes | 0 KiB | PASS | 0 files |
| 1440 | JS parsed | 637.8 KiB | WARN | 9 files, 199.1K gz |
| 1440 | CSS | 9.5 KiB | PASS | 1 files |
| 1440 | font families | 2 | PASS | beVietnam, beVietnam Fallback |
| 1440 | font files | 4 | PASS | 180.4K |
| 1440 | font bytes | 180.4 KiB | WARN |  |
| 1440 | images without width+height | 0 | PASS |  |
| 1440 | below-fold images not lazy | 0 | PASS |  |
| 1440 | oversized images (natural > 2.2x shown) | 0 | PASS |  |
| 1440 | WebGL live at load | 0 | PASS |  |
| 1440 | WebGL live at bottom | 0 | PASS |  |
| 1440 | WebGL peak live | 0 | PASS | 0 contexts made in all |
| 1440 | long tasks | 2 | PASS | runs 3, 1..2, max 118ms |
| 1440 | blocking time | 45 ms | PASS | runs 3, 39..70 ms; at load 45ms |
| 1440 | FCP (CPU, relative) | 196 ms | PASS | runs 3, 180..436 |
| 1440 | LCP (CPU, relative) | 196 ms | PASS | runs 3, 180..436, h1 |
| 1440 | layout shift | 0.000 | PASS | runs 3, 0.000..0.000; at load 0.000 |
| 1440 | modules loaded, never mounted | 0 | PASS |  |
| 1440 | broken requests | 1 | FAIL | api/pool?network=local |
| 1440 | page height | 2.1 screens | PASS | DOM 287 nodes |
| 390 | host CPU load (before/after) | 27/57 % | WARN | busy host: timing verdicts capped at WARN, rerun when idle |
| 390 | total transfer | 404.7 KiB | PASS | html 7.8K  css 9.5K  js 199.1K  font 180.4K  other 7.8K |
| 390 | requests | 17 | PASS | 16 by load |
| 390 | images bytes | 0 KiB | PASS | 0 files |
| 390 | JS parsed | 637.8 KiB | WARN | 9 files, 199.1K gz |
| 390 | CSS | 9.5 KiB | PASS | 1 files |
| 390 | font families | 2 | PASS | beVietnam, beVietnam Fallback |
| 390 | font files | 4 | PASS | 180.4K |
| 390 | font bytes | 180.4 KiB | WARN |  |
| 390 | images without width+height | 0 | PASS |  |
| 390 | below-fold images not lazy | 0 | PASS |  |
| 390 | oversized images (natural > 2.2x shown) | 0 | PASS |  |
| 390 | WebGL live at load | 0 | PASS |  |
| 390 | WebGL live at bottom | 0 | PASS |  |
| 390 | WebGL peak live | 0 | PASS | 0 contexts made in all |
| 390 | long tasks | 2 | PASS | runs 3, 1..2, max 107ms |
| 390 | blocking time | 61 ms | PASS | runs 3, 33..62 ms; at load 61ms |
| 390 | FCP (CPU, relative) | 208 ms | PASS | runs 3, 160..244 |
| 390 | LCP (CPU, relative) | 208 ms | PASS | runs 3, 160..244, p |
| 390 | layout shift | 0.000 | PASS | runs 3, 0.000..0.000; at load 0.000 |
| 390 | modules loaded, never mounted | 0 | PASS |  |
| 390 | broken requests | 1 | FAIL | api/pool?network=local |
| 390 | page height | 3.8 screens | PASS | DOM 287 nodes |

## Chưa kiểm tra trực tiếp và giới hạn vận hành

- Chưa mở/nhấn ký qua extension MetaMask thật, chưa broadcast giao dịch local/Sepolia bằng ví người dùng, chưa kiểm tra CORS với backend đang chạy trong browser.
- Chưa chứng nhận full E2E/Oracle/liquidation trên chain thật hoặc pinning/gateway IPFS công khai. Bộ HTTP dùng IPFS local store và Web3 test double; L06 cần kiểm tra đầy đủ.
- Session và pending journal chỉ giữ trong bộ nhớ; reload/đóng tab làm mất dữ liệu này. Intent backend có TTL; tx dropped/replaced cần đối chiếu thủ công trước khi gửi lại.
- Các màn hình số dư/hồ sơ của ví đã xác thực, review dialog với extension và các trạng thái này ở mọi kích thước còn trong checklist kiểm tra thủ công.

Hướng dẫn cấu hình và checklist: [docs/Lam/l05_metamask_web3.md](../../docs/Lam/l05_metamask_web3.md). Tổng hợp máy đọc được: [validation.json](l05/validation.json).
