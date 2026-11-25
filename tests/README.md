# Kiểm thử hệ thống

Dành cho các bài kiểm thử hợp đồng và hệ thống, bao gồm gửi và rút token, nộp và rút tài sản thế chấp, vay, trả nợ, tính lãi, Health Factor và thanh lý.

## H02

Chạy `npm run test:h02` cho [bộ test Token/NFT](H02_Tokens.test.js).
[H02TokenCaller](../contracts/mocks/H02TokenCaller.sol) chỉ dùng trong unit test; kiểm thử nghiệp vụ LendingPool thật chờ HI02/HI03.
