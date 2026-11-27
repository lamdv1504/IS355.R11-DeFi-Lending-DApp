# Dịch vụ nghiệp vụ

Dành cho logic xử lý nghiệp vụ của backend, kết nối hợp đồng bằng Web3.py và phối hợp các module xử lý hồ sơ, tích hợp IPFS trong thư mục src ở gốc dự án.

`web3_service.py` cung cấp đọc trạng thái LendingPool/PriceOracle, nạp ABI theo
cấu hình và ABI fallback của interface, cùng transaction unsigned để frontend
chuyển sang MetaMask ký. Khi core contract chưa deploy, service báo
`ContractNotDeployedError` kèm tên mạng và contract.

APR trong giao thức là lãi đơn năm hóa theo giây; `apy_reference_percent` chỉ là
APY tham khảo giả định ghép lãi hằng ngày, không phải lãi suất được contract
tính trực tiếp. Phí gas USD chỉ được trả về khi caller cung cấp giá ETH/USD.
Backend không nhận private key người dùng. `sign_system_transaction()` chỉ dành
cho bot/script và lấy khóa hệ thống từ cấu hình môi trường.
