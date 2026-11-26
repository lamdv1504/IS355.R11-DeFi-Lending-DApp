# Kiểm thử hệ thống

Dành cho các bài kiểm thử hợp đồng và hệ thống, bao gồm gửi và rút token, nộp và rút tài sản thế chấp, vay, trả nợ, tính lãi, Health Factor, thanh lý và lưu trữ IPFS có mã hóa/RBAC.

## H02

Chạy `npm run test:h02` cho [bộ test Token/NFT](H02_Tokens.test.js).
[H02TokenCaller](../contracts/mocks/H02TokenCaller.sol) chỉ dùng trong unit test; kiểm thử nghiệp vụ LendingPool thật chờ HI02/HI03.

## H03

Chạy bộ test IPFS, 3 loại hồ sơ, mã hóa AES-256-GCM và phân quyền RBAC tại [test_h03_ipfs.py](test_h03_ipfs.py):

```powershell
pytest tests/test_h03_ipfs.py -v
```
