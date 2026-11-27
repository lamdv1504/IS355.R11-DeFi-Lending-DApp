GATE: OPEN 50 (rounds used up)

# L03 — Báo cáo Borrowing Console

Ngày 27/11/2026, Lâm, giai đoạn 3. Nhánh `feature/lam-l03-borrowing-console`.

## Kết quả và phạm vi

Đã triển khai Borrowing Console tại `/borrow/`: thế chấp Token/NFT, vay/trả nợ, slider LTV, DebtToken, đồng hồ/banner HF, xem trước gas/APR/APY/lãi 30 ngày, cấp quyền và xác nhận riêng, thanh lý mô phỏng, kịch bản giá/thời gian, lưu phiên và reset.

Theo sheet **Lam H4 / 23 cong viec goc J21** trong kế hoạch: L03 phụ thuộc L01 và HI03/HI05; nối Web3.py API ở L05. Đã kiểm tra đủ file L01, bàn giao HI03/HI05, LendingPool/PriceOracle và ABI. Không bị chặn bởi thiếu đầu vào thành viên khác.

Đây là **frontend mô phỏng của L03**, không phải tích hợp L05. Không ký ví, không gửi giao dịch, không tạo CID/txHash hoặc sửa Oracle/clock blockchain thật. Gas ghi rõ tham số giả định; dữ liệu không được trình bày như quote RPC thực.

## Xác minh

| Kiểm tra | Kết quả |
| --- | --- |
| `npm test` | PASS: 30/30 — 21 bài L03 và 9 bài hồi quy L02 |
| `npm run lint` | PASS |
| `npm run build` | PASS: TypeScript và static export /, /borrow, icon, not-found |
| HTTP preview | PASS: / và /borrow/ trả 200; 18 tài nguyên tham chiếu trả 200 |
| Render baseline | 1440/1024/768/390px không ghi nhận lỗi JavaScript |
| Taste gate vòng 3 | OPEN: 50 phát hiện còn mở, 5 miễn trừ đã được chấp nhận |
| Kiểm tra 320px tại gate | Không lỗi JS hoặc phát hiện tràn màn hình |
| Ảnh | Đã xem 1440/1024/768/390px; bổ sung kiểm tra 320px và ảnh hồi quy L02 |
| Performance | 0 FAIL, 5 WARN tại 1440/390px, 3 lần tải mỗi kích thước |

Các kiểm tra gate `assets`, `spill`, `off-viewport`, `cut-text`, `tap-size`, `text-contrast`, `field-label`, `focus-visible`, `focus-hidden`, `heading-order` và `lang` đều PASS ở lượt được lưu.

Kiểm thử nghiệp vụ bao gồm: HF = 1, HF = 1,5 và lệch 1 wei; không nợ/vô hạn; LTV tính cả lãi; thanh khoản riêng; index APR cũ trước khi đổi rate; cấp quyền không tự checkpoint Pool; trả lãi trước gốc; trả hết/cap số trả; ownership NFT/biên nhận; thanh lý NFT và ERC-20 với thưởng 5%/hoàn dư; thiếu tiền/cấp quyền; dữ liệu lưu hỏng; quote/gas units-gwei-ETH; hạn mức hiển thị không làm tròn lên.

## Giới hạn của kết quả Gate và chỉnh hiển thị cuối

Gate kết thúc đủ 3 vòng trên bản kiểm tra với 50 mục còn mở. Sau đó, khi đọc ảnh mobile, phát hiện KPI tiền bị tách dãy số thành nhiều dòng. Đã sửa riêng hiển thị tổng nợ ở ô tổng quan và cỡ chữ KPI tại <=370px để đáp ứng yêu cầu đọc số tiền; không thay đổi công thức WAD, quyền rút/vay, số chi tiết hoặc model.

Đã build lại và chụp lại để xác nhận tại 390px và 320px. Không reset hoặc chạy thêm vòng Gate sau giới hạn, nên **kết quả Gate là của bản trước các chỉnh hiển thị nhỏ này**, không phải chứng nhận PASS của bản giao diện sau cùng. Các ảnh minh chứng lưu phản ánh phần hiển thị đã sửa.

`SKILL.md` cai cuc bo theo [skills-lock.json](../../frontend/skills-lock.json) khớp hash bản plugin đã đọc tại `C:/Users/ASUS/.codex/plugins/cache/taste-skill/taste-skill/2.5.1/skills/taste-skill/SKILL.md`. Skill đặt giới hạn “three rounds at most”; `references/gate.md` cua skill cai cuc bo yêu cầu báo các mục còn mở khi hết vòng. Không sửa checker hoặc ẩn trang khỏi công cụ.

Phần lớn mục còn mở yêu cầu hero/section một màn hình, nhịp trang giới thiệu, vị trí cột hoặc số liệu nhỏ hơn tiêu đề. Đó không phải bố cục thao tác hai cột của L03. Đồng hồ và các KPI là số liệu nghiệp vụ; không thêm cảnh quảng cáo hoặc khoảng trống toàn màn hình để đổi kết quả.

## Thiết kế và copy

Giữ Be Vietnam Pro 400/500/600/700, navy/xanh dương, bề mặt phẳng, nút pill và ngôn ngữ UI hiện tại; dùng `design.md` làm tham chiếu. Tách shell dùng chung để L02 và L03 có menu nhất quán, có scroll trên màn hình thấp, drawer hỗ trợ focus/Escape. Hộp xác nhận dùng dialog native. Việc thao tác end-to-end bằng browser tương tác chưa được xác minh đầy đủ.

Voice card: tiếng Việt trực tiếp, tên hành động cụ thể, số liệu và giả định minh bạch; không bịa giao dịch, danh tính khách hàng hay cam kết lợi nhuận.

`copy-lint` không có FAIL. WARN `copy-em-dash`: 8 dấu “—” trong HTML build, là placeholder trong lúc tải dữ liệu, không phải lối viết tu từ; được giữ. INFO `copy-rhythm`: 16 câu, trung bình 19,1 từ. Không có dữ kiện thị trường giả định; số khởi tạo lấy từ fixture L01/HI01 và được gắn mô phỏng.

Bộ consistency đầy đủ ban đầu báo các chữ hướng dẫn thiếu ngưỡng tương phản Taste và nút tối đa 40px ở 320px; đã tăng tương phản/body size và vùng bấm 44px. Các FAIL `loop-pause`/`reduced-motion` ban đầu nhận thay đổi số lãi theo giây như animation; CSS đã tắt chuyển động khi reduced motion, số liệu vẫn cập nhật để giữ chức năng nghiệp vụ.

## Hiệu năng và giới hạn

[Performance JSON](l03/performance.json), 3 lần tải/kích thước:

- Tổng truyền khoảng 370,8 KiB desktop / 370,4 KiB mobile.
- JavaScript khoảng 534,5 KiB trước nén / 164,3 KiB truyền nén: WARN.
- 4 font WOFF hiện có, tổng 180,4 KiB: WARN.
- CLS desktop 0,136: WARN; mobile 0,000: PASS.
- Không request hỏng, không WebGL và không module tải mà không mount.
- FCP/LCP trung vị khoảng 172ms desktop / 164ms mobile trong phép đo CPU local. Không coi đây là Core Web Vitals ngoài thực tế.

Phép đo này sau khi sửa tổng nợ KPI; quy tắc cỡ chữ riêng <=370px được thêm sau đó và không nằm trong hai viewport đo 1440/390. Cần kiểm tra hiệu năng lại nếu thay đổi cấu trúc hoặc bắt đầu dùng API thật.

Browser runtime liệt kê không có browser khả dụng, nên chưa chạy kiểm thử click/ký đầy đủ bằng browser tương tác. Đã dùng CLI Chrome headless của Taste để render/check/chụp; kiểm thử nghiệp vụ là kiểm thử model thuần. Chưa kiểm tra giao dịch MetaMask, API/RBAC thật hoặc receipt trên blockchain — thuộc L05.

## Ảnh minh chứng

- [1440px](l03/screenshots/1440.png)
- [1024px](l03/screenshots/1024.png)
- [768px](l03/screenshots/768.png)
- [390px](l03/screenshots/390.png)
- [320px](l03/screenshots/320.png)
- [Hồi quy L02: điều hướng dùng chung](l03/screenshots/lending-regression.png)

Ảnh dài được ghép qua nhiều giây, nên các chữ số lãi ở các panel có thể khác nhau một lượng nhỏ theo thời điểm chụp.

## Phạm vi file

Tài liệu nghiệp vụ và điểm tích hợp: [L03 handoff](../../docs/Lam/l03_borrowing_console.md). Có hướng dẫn chạy/thử trong `frontend/README.md`.

Giữ thay đổi có sẵn về font/design/layout của người dùng. Không sửa CSV IPFS, contract, backend hoặc README tổng. Mã L02 chỉ tách điều hướng/header sang shell chung; model L02 giữ nguyên và 9 kiểm thử hồi quy đạt. Dọn profile kiểm tra do phiên L03 tạo sau khi lưu minh chứng.

## Miễn trừ đã chấp nhận

<!-- L03_GATE_FINDINGS -->

| Check | Target | Reason |
| --- | --- | --- |
| hero-fill | main#main-content > div.demo-notice | L03 is the requested operational two-column borrowing console, not a marketing landing page. Full-screen hero spacing would hide required financial controls. |
| placeholder | section#loan > div.loan-balances > div:nth-of-type(2) > strong | The flagged digits are accrued MyUSDT interest and projected debt from WAD math, not an example contact or phone number. |
| nav | (the first screen) | The application uses the existing sidebar navigation and wallet header consistently with L02 and design.md; a marketing navigation bar is not the requested layout. |
| heading-scale | main#main-content > section.kpi-grid > article.kpi-card:nth-of-type(1) > div.kpi-value | This finding targets a KPI value, not a heading. Readable financial metrics are intentionally larger than section labels in the existing application system. |
| moment-none | (the page) | The functional Health Factor gauge is the visual subject of L03. An advertising scene or scroll moment is unrelated to the requested transaction console and flat design reference. |

## Open findings (50)

| # | Check | Widths | Target | Finding | Suggested fix |
| --- | --- | --- | --- | --- | --- |
| 1 | flush | 1440 | main#main-content > div.demo-notice > p "Dữ liệu thử nghiệm trong trình duyệt. Kh" | its first line sits 10px under the top edge of div.demo-notice, where the ground changes | give the section its padding at the edge where the ground changes (the closing call keeps a clear gap above the footer) |
| 2 | flush | 1440,390 | main#main-content > section.kpi-grid > article.kpi-card:nth-of-type(1) "Giá trị thế chấp 1.000 MyUSDT · theo giá" | its first line sits 0px under the top edge of section.kpi-grid, where the ground changes | give the section its padding at the edge where the ground changes (the closing call keeps a clear gap above the footer) |
| 3 | flush | 1440 | section#borrow-activity > div.activity-empty > p > span "Giao dịch và thay đổi kịch bản sẽ xuất h" | its last line sits -127px above the rule on top of section.panel.demo-wallet | give the section its padding at the edge where the ground changes (the closing call keeps a clear gap above the footer) |
| 4 | button-styles | 1440 | (one screen) | 3 button styles on one screen: pill, fill #edf3fd ("Vay thế chấp"); pill, outline #e0e5ed ("Hướng dẫn"); label and disc, fill #122b50 ("DeFi Lending"); the odd one out: "DeFi Lending" | one primary and one secondary button: one shape, one height per size, one label size |
| 5 | button-styles | 1440,390 | (the page) | 5 button styles on the page: label and disc, fill #122b50 x1 ("DeFi Lending"); pill, fill #edf3fd x2 ("Vay thế chấp"); pill, outline #e0e5ed x2 ("Hướng dẫn"); pill, fill #f6f7f9, outline #e0e5ed x2 ("Xem trước thanh lý"); pill, fill #245bd6 x1 ("Xem trước khoản vay") | one primary and one secondary button: one shape, one height per size, one label size |
| 6 | off-grid | 1440,390 | main#main-content > div.demo-notice > span.demo-label "MÔ PHỎNG" | left edge at 307px, 19px off the page margin at 288px (11 elements, like p) | move it onto the page margin, or the column edge its section uses |
| 7 | section-tile | 1440,390 | main#main-content > div.borrow-lower-grid "Hoạt động khoản vay" | the section is 248px tall (0.28 screens at 1440x900), shorter than the screen: its tile, held at the page's end (scroll 1811px) shows 248px of it and 171px of the section above, its heading "Quan sát rủi ro khi giá thay đ" on screen | set every section after the hero to one screen or two (height: calc(var(--h,1) * 100vh)) and fit its content above --padb |
| 8 | hero-screen | 1440 | main#main-content > section.page-heading "BORROWING CONSOLEVay thế chấp MyUSDT.Quả" | the hero ends at 237px on a 900px screen, 663px above the fold: it ends at the fold, 1px either way (SR-1) | make the hero exactly one screen (height: 100svh, its content fitted inside), never taller or shorter |
| 9 | hero-screen | 1440 | main#main-content > div.demo-notice "MÔ PHỎNGDữ liệu thử nghiệm trong trình d" | 635px of the next section shows on the first screen (from 265px on a 900px screen): nothing below the hero shows at load (SR-1) | end the hero at the fold so nothing of the next section shows at load (hero height: 100svh) |
| 10 | section-height | 1440 | main#main-content > div.demo-notice "MÔ PHỎNGDữ liệu thử nghiệm trong trình d" | the section is 40px tall (0 screens), 860px short of one screen (900px): every section after the hero is one screen or two, 2px either way (SR-2) | set the section to one screen or two (height: calc(var(--h,1) * 100vh), --h 1 or 2) and cut or split its content to fit |
| 11 | section-air | 1440 | main#main-content > div.demo-notice / main#main-content > div.risk-banner.risk-safe | 57px of air between the content of these two sections: 128-480px (64-600px WARN) (every gap out of the band at 1440px, top to bottom: 57px after "MÔ PHỎNGDữ liệu thử ", 72px after "Khoản vay đang an to", 78px after "Giá trị thế chấp1.00", 75px after "Tài sản thế chấpCOLL", 79px after "KỊCH BẢN THỬ NGHIỆMQ") (SR-3) | keep 128-480px of air between the content of neighbouring sections (112-420px on a phone): the sections' padding (--padt, --padb) |
| 12 | one-section | 1440 | h2#scenarios-title "Quan sát rủi ro khi giá thay đổi" | the screen at scroll 1800px (stride 2) shows 248px of section 7 and the heading of section 6 whole and the content of 4 sections, over 24px each beside section 5: a screen shows one section (another may peek 8px, 24px WARN) (SR-4) | make each section exactly one screen or two, so a screen shows one section and no neighbour peeks |
| 13 | one-section | 1440 | h1#borrow-title "Vay thế chấp MyUSDT." | the screen at scroll 0px (stride 0) shows 200px of section 4 and the heading of section 1 whole and the content of 4 sections, over 24px each beside section 5: a screen shows one section (another may peek 8px, 24px WARN) (and 2 more like it: scroll 120px, scroll 265px) (SR-4) | make each section exactly one screen or two, so a screen shows one section and no neighbour peeks |
| 14 | one-section | 1440 | main#main-content > div.demo-notice "MÔ PHỎNGDữ liệu thử nghiệm trong trình d" | a <div> sits directly in <main>: every part of <main> is a <section> (SR-4) | put every block of <main> in a <section>, and give a band its own section instead of a ground inside one |
| 15 | one-heading | 1440 | h2#health-title "Sức khỏe khoản vay" | the section holds 3 h2 headings: one per section, first in its .wrap (SR-5) | give each section one h2, first in its .wrap, and the hero only its h1 |
| 16 | one-heading | 1440 | div.borrow-lower-grid > section.panel.demo-wallet > div.panel-head > h2 "Ví người vay" | the section holds 2 h2 headings: one per section, first in its .wrap (SR-5) | give each section one h2, first in its .wrap, and the hero only its h1 |
| 17 | one-heading | 1440 | h2#borrow-activity-title "Hoạt động khoản vay" | headings of two sections show whole on one screen at 6 of 37 scroll positions (16.2%; at scroll 1550, 1600, 1650, 1700px), here with "Quan sát rủi ro khi giá thay đổi": at most 3% on a desktop (SR-5) | make the sections one screen tall so their headings sit a screen apart and two never share one |
| 18 | container-edges | 1440 | main#main-content > div.risk-banner.risk-safe "Khoản vay đang an toànTiếp tục theo dõi " | the content of section 3 runs 345px from the left and 61px from the right (read from its outermost blocks: no .wrap): the page's container starts at 288px; 345 and 61px are not one margin; the margin is 64-120px at 1440px (one container, equal margins, 2px either way) (SR-6) | use one container on every section and the nav (.wrap): one margin left and right, 64-120px on a desktop, 16-24px on a phone |
| 19 | container-edges | 1440 | main#main-content > div.demo-notice "MÔ PHỎNGDữ liệu thử nghiệm trong trình d" | the content of section 2 runs 307px from the left and 52px from the right (read from its outermost blocks: no .wrap): the page's container starts at 288px; 307 and 52px are not one margin; the margin is 64-120px at 1440px (one container, equal margins, 2px either way) (and 7 more like it: "BORROWING CONSOLEVay thế", "Giá trị thế chấp1.000MyU", "KỊCH BẢN THỬ NGHIỆMQuan ") (SR-6) | use one container on every section and the nav (.wrap): one margin left and right, 64-120px on a desktop, 16-24px on a phone |
| 20 | container-edges | 1440 | div.app-shell.borrowing-shell "Đến nội dung chínhDeFi LendingKHÔNG GIAN" | a <div> at the top of the page, outside header.nav, main, footer.closing and nav.actionbar (SR-6) | build the page as header.nav, a main of sections (each one in-flow .wrap plus background layers) and footer.closing |
| 21 | container-edges | 1440 | main#main-content > section.page-heading "BORROWING CONSOLEVay thế chấp MyUSDT.Quả" | the section needs exactly one in-flow child .wrap (it has 2 in-flow children, 0 .wrap) (and 7 more like it: "MÔ PHỎNGDữ liệu thử nghi", "Khoản vay đang an toànTi", "Giá trị thế chấp1.000MyU") (SR-6) | build the page as header.nav, a main of sections (each one in-flow .wrap plus background layers) and footer.closing |
| 22 | container-edges | 1440 | div.borrow-lower-grid > section.panel.demo-wallet > div.panel-head > h2 "Ví người vay" | the h2 starts 702px right of the container's left: every h1 and h2 starts on it, 2px either way (SR-6) | start the text on the container's left, or on the one split line every split shares |
| 23 | container-edges | 1440 | div#loan-form > div.ltv-control > div.ltv-caption > label "LTV dự kiến" | 8 text blocks start on a left line at x 815, 527px from the container's left: text starts on the container's left, or on one split line (x 761, 856, 951) (also "Giá gas giả định", "DebtToken dự kiến mint", "LTV sau thao tác") (and 7 more like it: "Quản lý khoản vay", x 349, x 313) (SR-6) | start the text on the container's left, or on the one split line every split shares |
| 24 | container-edges | 1440 | section#loan "Quản lý khoản vayDebtToken · không chuyể" | a box over half the container wide runs 790-1400px, not on the container's lines at 288-1400px (SR-6) | run the picture or box from the container's left line to its right line, or put it in a row or a split |
| 25 | container-edges | 1440 | section#borrow-activity "Hoạt động khoản vayTrong mô phỏngChưa có" | a box over half the container wide runs 288-941px, not on the container's lines at 288-1400px (SR-6) | run the picture or box from the container's left line to its right line, or put it in a row or a split |
| 26 | row-lines | 1440 | section#loan > div.loan-balances "DebtToken / nợ gốc500 MyUSDTLãi phát sin" | a row of 2 items: its first item starts at 815px, the container's left line at 288px; its last item ends at 1375px, the container's right line at 1400px (2px either way) (SR-7) | start the row's first item on the container's left line and end its last on the right line, every item one height |
| 27 | flush | 390 | main#main-content > section.kpi-grid > article.kpi-card:nth-of-type(3) "Có thể vay thêm 199,9999 MyUSDT · LTV tố" | its last line sits 0px above the lower edge of section.kpi-grid, where the ground changes to section#collateral | give the section its padding at the edge where the ground changes (the closing call keeps a clear gap above the footer) |
| 28 | flush | 390 | main#main-content > footer.app-footer > span "DeFi Lending · APR tính lãi theo giây · " | its first line sits 2px under the top edge of footer.app-footer, where the ground changes | give the section its padding at the edge where the ground changes (the closing call keeps a clear gap above the footer) |
| 29 | no-visual | 390 | main#main-content > section.kpi-grid "Giá trị thế chấp 1.000 MyUSDT · theo giá" | no picture, effect or mock in this section; a feature section needs a visual | give the section a visual: a UI fragment on a ground, real icons, or a photograph that fits |
| 30 | no-visual | 390 | section#collateral "Tài sản thế chấp" | no picture, effect or mock in this section; a feature section needs a visual | give the section a visual: a UI fragment on a ground, real icons, or a photograph that fits |
| 31 | no-visual | 390 | section#loan "Quản lý khoản vay" | no picture, effect or mock in this section; a feature section needs a visual | give the section a visual: a UI fragment on a ground, real icons, or a photograph that fits |
| 32 | no-visual | 390 | main#main-content > section.panel.borrowing-scenarios "Quan sát rủi ro khi giá thay đổi" | no picture, effect or mock in this section; a feature section needs a visual | give the section a visual: a UI fragment on a ground, real icons, or a photograph that fits |
| 33 | text-only | 390 | main#main-content > div.borrow-lower-grid > section.panel.demo-wallet "Ví người vay" | the closing section is only text: no picture, icon, mock or effect in it | give the section a visual: a photograph that fits, the real icons, or a UI fragment on a ground |
| 34 | heading-scale | 390 | section.panel.health-panel > div.hf-gauge.hf-safe > div.hf-reading > strong "1,5999" | the figure "1,5999" is set at 36px, larger than the h1 (30px) | set figures below the h1: a stat reads as data, not as the headline |
| 35 | right-edge | 390 | div.workspace > header.topbar > div.topbar-right > div.wallet-control "Người vay · 0x3C44…93BC Thanh lý · 0x15d" | its right edge runs 4px past the content's right edge (370px, where 9 boxes end) | end it on the content's right edge, like the other blocks of its section |
| 36 | section-gaps | 390 | section#collateral / main#main-content > div.borrowing-grid > div.borrowing-column > section.panel.health-panel | 1790px between these sections (never on one screen), +3342% against the median 52px | use one gap between sections (all within 25% of each other) |
| 37 | section-gaps | 390 | section#loan / main#main-content > section.panel.borrowing-scenarios | 772px between these sections, +1385% against the median 52px | use one gap between sections (all within 25% of each other) |
| 38 | section-gaps | 390 | section#borrow-activity / main#main-content > div.borrow-lower-grid > section.panel.demo-wallet | 85px between these sections, +63% against the median 52px | use one gap between sections (all within 25% of each other) |
| 39 | edge-left | 1440 | div.demo-notice p "Dữ liệu thử nghiệm trong trình d" | starts at x 419.6; the lines are 288 and the column starts | start it on the .wrap left line |
| 40 | edge-left | 1440,390 | div.risk-banner.risk-safe p "Tiếp tục theo dõi giá tài sản và" | starts at x 345; the lines are 288 and the column starts | start it on the .wrap left line |
| 41 | edge-left | 1440 | div.borrowing-grid section.panel.loan-panel "Quản lý khoản vayDebtToken · khô" | starts at x 789.7; the lines are 288 and the column starts | start it on the .wrap left line |
| 42 | edge-left | 1440 | div.borrow-lower-grid section.panel.demo-wallet "Ví người vay0x3C44…93BC1.500MyUS" | starts at x 964.8; the lines are 288 and the column starts | start it on the .wrap left line |
| 43 | screen-short | 1440,390 | section.page-heading section.page-heading "BORROWING CONSOLEVay thế chấp My" | 117px tall; one screen under the nav is 900px | make the section one full screen (--h: 1, layout-v4.md section 2) |
| 44 | neighbour | 1440,390 | section.page-heading section.page-heading "BORROWING CONSOLEVay thế chấp My" | framed, 42px of section.kpi-grid section.kpi-grid "Giá trị thế chấp1.000MyUSDT · th" shows | keep the next section's heading and picture out of this screen |
| 45 | screen-short | 1440,390 | section.kpi-grid section.kpi-grid "Giá trị thế chấp1.000MyUSDT · th" | 200px tall; one screen under the nav is 900px | make the section one full screen (--h: 1, layout-v4.md section 2) |
| 46 | screen-height | 1440,390 | section.kpi-grid section.kpi-grid "Giá trị thế chấp1.000MyUSDT · th" | 200px, 0.22 screens; a section is exactly one or two (--h) | make the section exactly one or two screens (--h: 1 or 2) |
| 47 | screen-short | 1440,390 | section.panel.borrowing-scenarios section.panel.borrowing-scenarios "KỊCH BẢN THỬ NGHIỆMQuan sát rủi " | 171px tall; one screen under the nav is 900px | make the section one full screen (--h: 1, layout-v4.md section 2) |
| 48 | screen-height | 1440,390 | section.panel.borrowing-scenarios section.panel.borrowing-scenarios "KỊCH BẢN THỬ NGHIỆMQuan sát rủi " | 171px, 0.19 screens; a section is exactly one or two (--h) | make the section exactly one or two screens (--h: 1 or 2) |
| 49 | hero-fold | 1440,390 | section.page-heading section.page-heading "BORROWING CONSOLEVay thế chấp My" | starts at y 120, not under the nav | the hero fills the first screen alone, its button inside it |
| 50 | hero-fold | 1440,390 | section.kpi-grid section.kpi-grid "Giá trị thế chấp1.000MyUSDT · th" | shows on the first screen from y 468 | the hero fills the first screen alone, its button inside it |
