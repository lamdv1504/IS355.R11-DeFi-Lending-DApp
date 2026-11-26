# L02 — Dashboard cho vay

L02 trong bảng kế hoạch được giao cho **Lâm**. Triển khai theo mã công việc L02, giai đoạn 2, trên nhánh `feature/lam-l02-lending-dashboard`.

## Phạm vi và đầu vào

Đầu vào bắt buộc là L01: [wireframe](ui_wireframes.md), [đề xuất dữ liệu/API](l01_api_contract.md) và [fixture](wireframes/l01-ui-examples.json). Các tài liệu này đều có sẵn.

L02 chạy song song Q02; tích hợp ví, contract và API thật nằm ở L05. Vì vậy thiếu API Q02 hoặc LendingPool triển khai chưa chặn phần frontend mô phỏng của L02. Khi chuyển sang tích hợp, phải kiểm tra đầu vào của các thành viên trước; không tự bịa API, ABI hoặc địa chỉ Pool.

Tham chiếu công thức: [HI01](../Hieu/smart_contract_spec.md), [constants](../../backend/config/constants.py). Fixture ban đầu: tổng vốn gửi 1.000, tổng vay 500, thanh khoản khả dụng 500 MyUSDT; U 50%, borrow APR 10%, supply APR 5%, APY tham khảo 5,1267%.

## Chức năng

| Phần | Hành vi |
| --- | --- |
| KPI | Supply APY, tổng vốn Pool, vốn gốc của ví và lãi tích lũy theo thời gian |
| Biểu đồ | Dự phóng 7/30 ngày từ vốn gốc và APR hiện tại; ghi rõ giả định giữ APR và không tái đầu tư |
| Gửi | Kiểm tra số dư, tạo NFT mới, cập nhật vốn Pool và tiền khả dụng |
| Rút | Chọn NFT, giới hạn theo min(quyền lợi NFT, thanh khoản khả dụng), kiểm tra lại khi xác nhận |
| Chuyển | Kiểm tra địa chỉ nhận, từ chối ví hiện tại/zero, giữ vốn gốc/lãi khi đổi chủ |
| Ví A/B | Đổi ví trải nghiệm để kiểm tra danh sách và quyền sở hữu |
| Lịch sử | Ghi các thao tác mô phỏng, không sinh txHash hoặc explorer link giả |
| Trạng thái | Tải dữ liệu, danh sách rỗng, tìm kiếm không có kết quả, lỗi nhập và xác nhận |
| Phiên | Lưu localStorage, kiểm tra dữ liệu khi đọc, khôi phục phiên mặc định khi dữ liệu hỏng, đặt lại có xác nhận |

Không gọi faucet thật; nút nhận token chỉ tăng số dư mô phỏng 1.000 MyUSDT mỗi lần.

## Thiết kế

Dùng `frontend/design.md`: Manrope, nền mint `#F3FAF5`, chữ xanh `#0D3B2E`, nút `#28C76F`, bề mặt trắng. Ảnh đính kèm chỉ tham khảo kiểu sans bo gọn và độ đậm; không sao chép logo, hình hoặc nội dung LendTrust.

Font Manrope lưu cục bộ cùng giấy phép SIL OFL. Chữ phụ và điều khiển tối thiểu 14px; đoạn mô tả chính 16px. Chữ trên nút xanh dùng màu tối để đảm bảo tương phản. Có focus rõ, skip link, dialog native giữ focus/Escape và điều hướng mobile giữ focus trong menu. CSS tắt chuyển động khi yêu cầu reduced motion; số tiền vẫn được cập nhật vì đó là dữ liệu nghiệp vụ.

Áp dụng Taste skill đã cài tại `frontend/.agents/skills/design-taste-frontend/SKILL.md`. Quy tắc trang giới thiệu như hero toàn màn hình, ảnh quảng cáo và mỗi màn hình chỉ một section không được áp vào ứng dụng thao tác tài chính. Giữ nhãn mô phỏng rõ ràng dù bộ kiểm tra copy có thể ưu tiên trang quảng cáo.

## Quy tắc tính toán

Tiền và NFT ID là chuỗi; kiểm tra tiền bằng bigint WAD 18 chữ số thập phân. Chỉ đổi sang Number để vẽ biểu đồ và định dạng hiển thị.

- `U_bps = min(10000, borrowed * 10000 / supplied)`, 0 nếu supplied bằng 0.
- `borrowAPR_bps = 500 + floor(U_bps * 1000 / 10000)`.
- `supplyAPR_bps = floor(borrowAPR_bps * U_bps / 10000)`.
- APY tham khảo ghép lãi hằng ngày; lãi thực trong demo tính trên vốn gốc bằng APR.
- Checkpoint tất cả vị thế với APR cũ trước thay đổi số dư Pool; giữ phần dư phép chia để chia nhỏ khoảng thời gian không mất lãi.
- Thanh khoản là sổ tiền riêng, không thay bằng totalSupplied trừ totalBorrowed.
- Chỉ owner hiện tại được rút/chuyển NFT. Rút hết quyền lợi đóng vị thế.
- Quy ước thanh toán demo: trả lãi trước rồi trừ vốn gốc. Cần đối chiếu contract/API thật ở L05.

`src/lib/lending-demo.ts` là mô hình thuần, `use-lending-demo.ts` quản lý phiên/đồng hồ; các thành phần React chỉ nhận dữ liệu và gửi action. Điểm thay thế khi tích hợp là hook dịch vụ; không để component tự suy ra số dư từ giao dịch giả.

## Bước tích hợp L05

Cần API Q02 đã thống nhất, ABI/địa chỉ LendingPool đúng chain, ownerOf hiện tại và cơ chế cập nhật sau receipt. Dùng Ethers BrowserProvider/Signer cho ví thật, xử lý đổi account/chain, approval, reject/revert và trạng thái transaction. Không tái sử dụng thông báo mô phỏng làm bằng chứng giao dịch thành công.

`DemoState` không phải schema API đã triển khai. Phải map dữ liệu thật sang view model, giữ amount_wad và ID dưới dạng chuỗi, lấy available_liquidity và quyền rút từ nguồn có thẩm quyền. Không nhập khóa riêng trong frontend.
