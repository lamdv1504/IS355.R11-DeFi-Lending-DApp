GATE: OPEN 55 (rounds used up)

# L02 — Báo cáo frontend

Ngày 26/11/2026. Nhánh `feature/lam-l02-lending-dashboard`. Mã L02 được giao Lâm trong bảng kế hoạch.

## Kết quả

Đã triển khai dashboard mô phỏng: KPI/APY, biểu đồ dự phóng, gửi/rút có xác nhận, kiểm tra thanh khoản, danh sách và chuyển NFT, đổi ví A/B, lịch sử và lưu phiên. Dữ liệu đầu vào L01 đầy đủ; Q02 chạy song song và tích hợp thật thuộc L05.

| Kiểm tra | Kết quả |
| --- | --- |
| `npm test` | PASS — 9/9 bài kiểm thử |
| `npm run lint` | PASS |
| `npm run build` | PASS — Next.js xuất trang tĩnh thành công, kèm TypeScript |
| Preview cục bộ | PASS — trang chính và 10 tài nguyên tham chiếu trả HTTP 200; lang=vi |
| Ảnh bản cuối | Đã chụp và xem ở 1440, 1024, 768 và 390px |
| Taste consistency ban đầu | Render đủ 4 cỡ trên, không có lỗi JavaScript; nhiều FAIL theo quy tắc trang giới thiệu |
| Taste gate cuối | OPEN — 55 phát hiện, hết 3 vòng; không phải PASS |
| Kiểm tra 320px của gate cuối | Không có lỗi JavaScript hoặc phát hiện tràn màn hình |
| Performance | FAIL ngân sách JS ở 1440 và 390px; chi tiết bên dưới |
| Waivers | Không có; không sửa hoặc vô hiệu hóa checker |

9 kiểm thử kiểm tra công thức HI01/APY; parser WAD chính xác; gửi và kiểm tra số dư; checkpoint APR cũ và phần dư; thanh khoản tách khỏi tổng vốn; chuyển chủ và quyền rút; rút hết đóng NFT; dữ liệu lưu hỏng; faucet mô phỏng.

Bộ kiểm tra từng phát hiện nhãn trường chỉ có cho screen reader, chữ phụ thiếu tương phản theo ngưỡng Taste và nút nhận token bị chật ở tablet. Các điểm này đã được sửa. Lượt gate 2 không đọc được consistency đầy đủ; sau đó build báo ENOSPC. Đã dọn cache và profile do phiên kiểm tra tạo, build lại thành công và chạy gate 3.

## Thiết kế và copy

Dùng palette Neobank Mint và Manrope từ `frontend/design.md`; xanh mint cho nền tài chính nhẹ, xanh đậm cho chữ và xanh lá cho hành động. Font được lưu cục bộ, kèm SIL OFL. Tham khảo nét chữ của ảnh đính kèm; không dùng logo, ảnh hay nội dung LendTrust.

Đây là ứng dụng thao tác dữ liệu. Không dùng hero quảng cáo, shader, ảnh trang trí, scene hay dealt moment. Chuyển động chỉ dùng cho phản hồi nút/menu; CSS có reduced motion. Số lãi thay đổi mỗi giây là dữ liệu nghiệp vụ, không phải animation quảng cáo.

Voice card: tiếng Việt rõ ràng, gọi đúng MyUSDT/Pool/NFT, mô tả kết quả thao tác cụ thể, giữ nhãn mô phỏng và giả định dự phóng, không bịa lợi nhuận hay giao dịch thật. Các con số khởi tạo là fixture L01/HI01, không phải số liệu thị trường. Không có assumed fact về ngân hàng, khách hàng, doanh thu hoặc cam kết lợi nhuận.

## Các điểm còn mở

Phần lớn kết quả Taste liên quan hero toàn màn hình, chiều cao section, vị trí cột, hình minh họa, số lớn KPI hoặc bộ từ vựng tiếng Anh của checker. Các quy tắc đó không phù hợp hoàn toàn với dashboard tiếng Việt và `design.md`. Không kéo KPI hoặc bảng thành các section toàn màn hình để đạt điểm.

Cần giữ riêng các mục chưa xác minh: `focus-visible` tại ô tìm NFT và nút đặt lại mô phỏng. CSS có focus ring; chưa hoàn tất xác minh thủ công hai điểm này trong browser tương tác. Không coi chúng là đã PASS. Phát hiện `placeholder` coi phần thập phân của lãi như số điện thoại mẫu là nhận diện sai của checker; không có số liên hệ giả trên trang.

[Taste SKILL.md](../../frontend/.agents/skills/design-taste-frontend/SKILL.md) ghi: “Fix what it lists and run it again until its last line is `GATE: PASS` or `GATE: OPEN`, three rounds at most”. [Gate reference](../../frontend/.agents/skills/design-taste-frontend/references/gate.md) yêu cầu dừng sửa khi hết vòng và báo các FAIL còn mở. Vì vậy mã được giữ ở bản cuối đã build; báo cáo này không tuyên bố đã qua toàn bộ Taste.

## Hiệu năng

[JSON đo hiệu năng](l02/performance.json) lưu 3 lần tải ở mỗi kích thước 1440/390px.

- Tổng truyền khoảng 447,8 KiB desktop / 447,4 KiB mobile, trong đó JavaScript nén khoảng 266 KiB.
- JavaScript trước nén 905,8 KiB, vượt ngân sách của Taste ở cả hai kích thước: 2 FAIL.
- Một font 161 KiB; checker cảnh báo dung lượng font.
- Không có request hỏng, WebGL hoặc module tải mà không mount.
- CLS trung vị khoảng 0,003 desktop và 0,000 mobile.
- Host bận: CPU trước/sau khoảng 95/63%. Không dùng timing này như Core Web Vitals ngoài thực tế.

Điểm cần tối ưu tiếp là lượng JavaScript của Next/Recharts/Ethers và định dạng font. Chưa thực hiện thay thư viện hoặc chia tải sau khi gate kết thúc.

## Ảnh minh chứng

- [Desktop 1440px](l02/screenshots/1440.png)
- [Desktop nhỏ 1024px](l02/screenshots/1024.png)
- [Tablet 768px](l02/screenshots/768.png)
- [Mobile 390px](l02/screenshots/390.png)

## Giới hạn xác minh

Chưa kết nối API Q02, ký ví, approval hoặc gửi giao dịch LendingPool. Không có txHash giả. Chưa chạy kiểm thử thao tác đầy đủ end-to-end trong browser tương tác; runtime browser của môi trường không khởi tạo được. CLI headless của Taste đã dùng để render, kiểm tra và chụp ảnh.

Chỉ xóa các SVG/favicon mẫu Next.js không còn được dùng và cache/profile kiểm tra do phiên này tạo. Giữ `design.md`, skill đã cài và thay đổi scaffold có sẵn. Không sửa README tổng của dự án. Tài liệu/report mới thuộc thư mục Lam.

## Danh sách đầy đủ 55 phát hiện còn mở

Bảng dưới lấy nguyên dữ liệu gate vòng 3; không đánh dấu miễn trừ.

| # | Check | Widths | Target | Finding | Suggested fix |
| --- | --- | --- | --- | --- | --- |
| 1 | hero-fill | 1440,390 | main#main-content > div.demo-notice "MÔ PHỎNG Dữ liệu thử nghiệm trong trình " | the next section shows on the first screen: it starts at 259px on a 900px screen (the hero ends at 231px) | let the hero fill the first screen alone (min-height: 100svh, less above it): nothing of the next section on load |
| 2 | flush | 1440,390 | main#main-content > section.kpi-grid > article.kpi-card.kpi-featured "Supply APY 5,13% APR 5% / năm" | its first line sits 0px under the top edge of section.kpi-grid, where the ground changes | give the section its padding at the edge where the ground changes (the closing call keeps a clear gap above the footer) |
| 3 | flush | 1440 | main#main-content > div.overview-grid > section.panel.interest-panel > p.chart-note "Giả định APR giữ nguyên, chưa tái đầu tư" | its last line sits -371px above the rule on top of section.panel.liquidity-panel | give the section its padding at the edge where the ground changes (the closing call keeps a clear gap above the footer) |
| 4 | flush | 1440 | section#activity > div.activity-empty > p > span "Lần gửi, rút hoặc chuyển NFT sẽ xuất hiệ" | its last line sits -128px above the rule on top of section.panel.demo-wallet | give the section its padding at the edge where the ground changes (the closing call keeps a clear gap above the footer) |
| 5 | placeholder | 1440 | main#main-content > section.kpi-grid > article.kpi-card:nth-of-type(4) > div.kpi-value.interest-value "0,00000633" | a stand-in contact printed on the page ("00000633"): no visitor can use it | print the real address and number, or a form or a button that names the action: never an example.com address or a number of zeros |
| 6 | nav | 1440 | (the first screen) | no nav bar across the top of the first screen (a header with the brand, the section links and the main action) | make the nav one bar from the content's left edge to its right edge, with every link and action inside it |
| 7 | button-styles | 1440 | (one screen) | 3 button styles on one screen: soft, fill #ffffff, outline #d3e2d7 ("Rút tiền"); soft, fill #e7f6eb ("Tổng quan"); soft, fill #28c76f ("Gửi tiền"); the odd one out: "Gửi tiền" | one primary and one secondary button: one shape, one height per size, one label size |
| 8 | button-styles | 1440 | (the page) | 3 button styles on the page: soft, fill #e7f6eb x1 ("Tổng quan"); soft, fill #ffffff, outline #d3e2d7 x4 ("Rút tiền"); soft, fill #28c76f x1 ("Gửi tiền") | one primary and one secondary button: one shape, one height per size, one label size |
| 9 | copy-headline | 1440 | h1#page-title "Tổng quan cho vay." | "Tổng quan cho vay." does not name what is sold (defi lending dashboard, defi, lending, dashboard, from flags) | put the category noun in the h1 (and who it is for, or where), in 2 to 8 words |
| 10 | copy-headings | 1440 | h2#chart-title "Dự phóng tiền lãi" | "Dự phóng tiền lãi" names no product, part, place or section (3 headings like it; at most one brand line per page) (and 2 more like it: "Hoạt động gần đây", "Ví trải nghiệm A") | name the thing in every heading: the product, a part, the place or a section noun |
| 11 | heading-scale | 1440,390 | main#main-content > section.kpi-grid > article.kpi-card.kpi-featured > div.kpi-value "5,13%" | the figure "5,13%" is set at 31.7px, larger than the section headings (h2 18px); 6 more like it | set figures at the h2 size or under: a stat reads as data, not as the heading |
| 12 | off-grid | 1440,390 | main#main-content > div.demo-notice > span.demo-label "MÔ PHỎNG" | left edge at 288px, 16px off the page margin at 272px (8 elements, like p) | move it onto the page margin, or the column edge its section uses |
| 13 | focus-visible | 1440 | input#position-search | Tab stop 13, input "": the focus lands on something you cannot see | keep the kit's ring (system.css :focus-visible, 2px in --action, there at once); a control that hides itself shows on focus |
| 14 | focus-visible | 1440 | main#main-content > footer.app-footer > button.text-button "Đặt lại mô phỏng" | Tab stop 17, button "Đặt lại mô phỏng": the focus lands on something you cannot see | keep the kit's ring (system.css :focus-visible, 2px in --action, there at once); a control that hides itself shows on focus |
| 15 | moment-none | 1440 | (the page) | a software page (--type) deals no moment: every kind carries one, two on a long page (moments.md) | deal one (moments.mjs pick --page software) and mount it in its own section |
| 16 | hero-screen | 1440 | section#overview "CHO VAY MYUSDTTổng quan cho vay.Theo dõi" | the hero ends at 231px on a 900px screen, 669px above the fold: it ends at the fold, 1px either way (SR-1) | make the hero exactly one screen (height: 100svh, its content fitted inside), never taller or shorter |
| 17 | hero-screen | 1440 | main#main-content > div.demo-notice "MÔ PHỎNGDữ liệu thử nghiệm trong trình d" | 641px of the next section shows on the first screen (from 259px on a 900px screen): nothing below the hero shows at load (SR-1) | end the hero at the fold so nothing of the next section shows at load (hero height: 100svh) |
| 18 | section-height | 1440 | main#main-content > div.demo-notice "MÔ PHỎNGDữ liệu thử nghiệm trong trình d" | the section is 54px tall (0.1 screens), 846px short of one screen (900px): every section after the hero is one screen or two, 2px either way (SR-2) | set the section to one screen or two (height: calc(var(--h,1) * 100vh), --h 1 or 2) and cut or split its content to fit |
| 19 | section-air | 1440 | main#main-content > div.demo-notice / main#main-content > section.kpi-grid | 52px of air between the content of these two sections: 128-480px (64-600px WARN) (every gap out of the band at 1440px, top to bottom: 52px after "MÔ PHỎNGDữ liệu thử ", 74px after "Supply APY5,13%APR 5", 77px after "ƯỚC TÍNH TỪ VỐN GỐC ", 67px after "NFT vị thế của bạn 1") (SR-3) | keep 128-480px of air between the content of neighbouring sections (112-420px on a phone): the sections' padding (--padt, --padb) |
| 20 | one-section | 1440 | h2#activity-title "Hoạt động gần đây" | the screen at scroll 733px (the top of section 5) shows 246px of section 6 and the heading of section 6 whole and the content of 4 sections, over 24px each beside section 5: a screen shows one section (another may peek 8px, 24px WARN) (SR-4) | make each section exactly one screen or two, so a screen shows one section and no neighbour peeks |
| 21 | one-section | 1440 | h2#positions-title "NFT vị thế của bạn 1" | the screen at scroll 259px (the top of section 2) shows 198px of section 5 and the heading of section 5 whole and the content of 4 sections, over 24px each beside section 4: a screen shows one section (another may peek 8px, 24px WARN) (SR-4) | make each section exactly one screen or two, so a screen shows one section and no neighbour peeks |
| 22 | one-section | 1440 | h1#page-title "Tổng quan cho vay." | the screen at scroll 0px (stride 0) shows 176px of section 3 and the heading of section 1 whole and the content of 4 sections, over 24px each beside section 4: a screen shows one section (another may peek 8px, 24px WARN) (and 1 more like it: scroll 120px) (SR-4) | make each section exactly one screen or two, so a screen shows one section and no neighbour peeks |
| 23 | one-section | 1440 | main#main-content > div.demo-notice "MÔ PHỎNGDữ liệu thử nghiệm trong trình d" | a <div> sits directly in <main>: every part of <main> is a <section> (SR-4) | put every block of <main> in a <section>, and give a band its own section instead of a ground inside one |
| 24 | one-heading | 1440 | h2#liquidity-title "Thanh khoản Pool" | the section holds 2 h2 headings: one per section, first in its .wrap (SR-5) | give each section one h2, first in its .wrap, and the hero only its h1 |
| 25 | one-heading | 1440 | h2#wallet-title "Ví trải nghiệm A" | the section holds 2 h2 headings: one per section, first in its .wrap (SR-5) | give each section one h2, first in its .wrap, and the hero only its h1 |
| 26 | one-heading | 1440 | h2#positions-title "NFT vị thế của bạn 1" | headings of two sections show whole on one screen at 12 of 15 scroll positions (80%; at scroll 150, 200, 250, 300px), here with "Dự phóng tiền lãi": at most 3% on a desktop (SR-5) | make the sections one screen tall so their headings sit a screen apart and two never share one |
| 27 | container-edges | 1440 | section#overview "CHO VAY MYUSDTTổng quan cho vay.Theo dõi" | the content of section 1 runs 272px from the left and 40px from the right (read from its outermost blocks: no .wrap): 272 and 40px are not one margin; the margin is 64-120px at 1440px (one container, equal margins, 2px either way) (SR-6) | use one container on every section and the nav (.wrap): one margin left and right, 64-120px on a desktop, 16-24px on a phone |
| 28 | container-edges | 1440 | main#main-content > section.kpi-grid "Supply APY5,13%APR 5% / nămTổng vốn gửi " | the content of section 3 runs 272px from the left and 40px from the right (read from its outermost blocks: no .wrap): 272 and 40px are not one margin; the margin is 64-120px at 1440px (one container, equal margins, 2px either way) (and 6 more like it: "NFT vị thế của bạn 1Mỗi ", "DeFi Lending · Lãi suất ", "ƯỚC TÍNH TỪ VỐN GỐC HIỆN") (SR-6) | use one container on every section and the nav (.wrap): one margin left and right, 64-120px on a desktop, 16-24px on a phone |
| 29 | container-edges | 1440 | div.app-shell "Đến nội dung chínhDeFi LendingKHÔNG GIAN" | a <div> at the top of the page, outside header.nav, main, footer.closing and nav.actionbar (SR-6) | build the page as header.nav, a main of sections (each one in-flow .wrap plus background layers) and footer.closing |
| 30 | container-edges | 1440 | span#recharts_measurement_span "0.0" | a <span> at the top of the page, outside header.nav, main, footer.closing and nav.actionbar (and 7 more like it: "CHO VAY MYUSDTTổng quan ", "MÔ PHỎNGDữ liệu thử nghi", "Supply APY5,13%APR 5% / ") (SR-6) | build the page as header.nav, a main of sections (each one in-flow .wrap plus background layers) and footer.closing |
| 31 | container-edges | 1440 | main#main-content > div.demo-notice > button.icon-button "Tìm hiểu chế độ mô phỏng" | "Tìm hiểu chế độ mô phỏng" runs 1344-1388px, outside the container lines of section 2 at 288-1332px: full width is for background layers and grounds only (SR-6) | keep it inside the container lines (.wrap): full width is for background layers and grounds only |
| 32 | container-edges | 1440 | h2#liquidity-title "Thanh khoản Pool" | the h2 starts 772px right of the container's left: every h1 and h2 starts on it, 2px either way (SR-6) | start the text on the container's left, or on the one split line every split shares |
| 33 | container-edges | 1440 | h2#wallet-title "Ví trải nghiệm A" | the h2 starts 772px right of the container's left: every h1 and h2 starts on it, 2px either way (and 6 more like it: x 332, x 297, "Dự phóng tiền lãi") (SR-6) | start the text on the container's left, or on the one split line every split shares |
| 34 | container-edges | 1440 | main#main-content > div.overview-grid > section.panel.interest-panel "ƯỚC TÍNH TỪ VỐN GỐC HIỆN TẠIDự phóng tiề" | a box over half the container wide runs 272-995px, not on the container's lines at 272-1400px (and 1 more like it: "Hoạt động gần đâyTrong m") (SR-6) | run the picture or box from the container's left line to its right line, or put it in a row or a split |
| 35 | row-lines | 1440 | section#positions > div.table-foot "Chỉ ví sở hữu NFT hiện tại có quyền rút " | a row of 2 items: its first item starts at 297px, the container's left line at 273px; its last item ends at 1375px, the container's right line at 1399px (2px either way) (SR-7) | start the row's first item on the container's left line and end its last on the right line, every item one height |
| 36 | row-lines | 1440 | main#main-content > div.demo-notice > button.icon-button "Tìm hiểu chế độ mô phỏng" | "Tìm hiểu chế độ mô phỏng" ends at 1388px, past the container's right line at 1332px (SR-7) | end it at the container's right line |
| 37 | flush | 390 | section#overview > div.heading-actions > button.button.secondary "Rút tiền" | its button sits 0px above the lower edge of section#overview, where the ground changes to div.demo-notice | give the section its padding at the edge where the ground changes (the closing call keeps a clear gap above the footer) |
| 38 | flush | 390 | main#main-content > section.kpi-grid > article.kpi-card:nth-of-type(3) "Vốn gốc của bạn 1.000 MyUSDT" | its last line sits 0px above the lower edge of section.kpi-grid, where the ground changes to section.panel.interest-panel | give the section its padding at the edge where the ground changes (the closing call keeps a clear gap above the footer) |
| 39 | no-visual | 390 | main#main-content > section.kpi-grid "Supply APY 5,13% APR 5% / năm Tổng vốn g" | no picture, effect or mock in this section; a feature section needs a visual | give the section a visual: a UI fragment on a ground, real icons, or a photograph that fits |
| 40 | no-visual | 390 | main#main-content > div.overview-grid > section.panel.liquidity-panel "Thanh khoản Pool" | no picture, effect or mock in this section; a feature section needs a visual | give the section a visual: a UI fragment on a ground, real icons, or a photograph that fits |
| 41 | no-visual | 390 | section#positions "NFT vị thế của bạn 1" | no picture, effect or mock in this section; a feature section needs a visual | give the section a visual: a UI fragment on a ground, real icons, or a photograph that fits |
| 42 | text-only | 390 | main#main-content > div.lower-grid > section.panel.demo-wallet "Ví trải nghiệm A" | the closing section is only text: no picture, icon, mock or effect in it | give the section a visual: a photograph that fits, the real icons, or a UI fragment on a ground |
| 43 | card-visual | 390 | main#main-content > section.kpi-grid "Supply APY 5,13% APR 5% / năm Tổng vốn g" | 4 cards hold only text: no picture, icon, UI fragment or effect in any of them | give the cards a visual: an inset panel with a UI fragment, a photograph or real icons |
| 44 | heading-scale | 390 | main#main-content > div.overview-grid > section.panel.liquidity-panel > div.liquidity-value "500MyUSDT" | the figure "500MyUSDT" is set at 36px, larger than the h1 (32px) | set figures below the h1: a stat reads as data, not as the headline |
| 45 | edge-left | 1440 | div.demo-notice p "Dữ liệu thử nghiệm trong trình d" | starts at x 394.5; the lines are 272 and the column starts | start it on the .wrap left line |
| 46 | edge-left | 1440 | div.overview-grid section.panel.liquidity-panel "Thanh khoản PoolKHẢ DỤNG ĐỂ RÚT5" | starts at x 1019.3; the lines are 272 and the column starts | start it on the .wrap left line |
| 47 | edge-left | 1440 | div.lower-grid section.panel.demo-wallet "Ví trải nghiệm ASố dư dùng để th" | starts at x 1019.3; the lines are 272 and the column starts | start it on the .wrap left line |
| 48 | screen-short | 1440,390 | #overview section.page-heading "CHO VAY MYUSDTTổng quan cho vay." | 111px tall; one screen under the nav is 900px | make the section one full screen (--h: 1, layout-v4.md section 2) |
| 49 | neighbour | 1440,390 | #overview section.page-heading "CHO VAY MYUSDTTổng quan cho vay." | framed, 38px of section.kpi-grid section.kpi-grid "Supply APY5,13%APR 5% / nămTổng " shows | keep the next section's heading and picture out of this screen |
| 50 | screen-short | 1440,390 | section.kpi-grid section.kpi-grid "Supply APY5,13%APR 5% / nămTổng " | 176px tall; one screen under the nav is 900px | make the section one full screen (--h: 1, layout-v4.md section 2) |
| 51 | screen-height | 1440,390 | section.kpi-grid section.kpi-grid "Supply APY5,13%APR 5% / nămTổng " | 176px, 0.20 screens; a section is exactly one or two (--h) | make the section exactly one or two screens (--h: 1 or 2) |
| 52 | neighbour | 1440 | section.kpi-grid section.kpi-grid "Supply APY5,13%APR 5% / nămTổng " | framed, 139px of #positions section.panel.positions-panel "NFT vị thế của bạn 1Mỗi NFT là q" shows | keep the next section's heading and picture out of this screen |
| 53 | screen-short | 1440,390 | #positions section.panel.positions-panel "NFT vị thế của bạn 1Mỗi NFT là q" | 314px tall; one screen under the nav is 900px | make the section one full screen (--h: 1, layout-v4.md section 2) |
| 54 | hero-fold | 1440,390 | #overview section.page-heading "CHO VAY MYUSDTTổng quan cho vay." | starts at y 120, not under the nav | the hero fills the first screen alone, its button inside it |
| 55 | hero-fold | 1440,390 | section.kpi-grid section.kpi-grid "Supply APY5,13%APR 5% / nămTổng " | shows on the first screen from y 359 | the hero fills the first screen alone, its button inside it |

## Copy-lint WARN

`copy-em-dash`: 7 em dashes in the built HTML (budget 2). Kept because these are loading-state dashes for unavailable values before client hydration, not rhetorical punctuation or fake metrics. No copy-lint FAIL.
