# Báo cáo và minh chứng kiểm thử của Quân (Q01–Q06)

Tổng hợp kết quả kiểm thử tự động (`pytest`), kiểm thử live trên Hardhat Local (`31337`) + **IPFS Kubo v0.43.2 live daemon**, và kiểm chứng trực tiếp trên Ethereum Sepolia Testnet (`11155111`).

| Task | Phạm vi | Báo cáo chi tiết | Trạng thái |
|---|---|---|---|
| **Q01** | Môi trường Hardhat 31337, Sepolia RPC 11155111, `.env.example`, guard private key | [q01_environment_validation.md](./q01_environment_validation.md) | **PASS** (Unit + Live RPC) |
| **Q02** | `Web3Service`, `PriceOracle`, `get_liquidation_preview()`, ước lượng Gas, ABI NFT | [q02_web3_service_validation.md](./q02_web3_service_validation.md) | **PASS** (Unit + Live Local/Sepolia) |
| **Q03 & Q04** | Loan Agreement PDF, Credit Report JSON, Audit Logs JSON/CSV, AES-256-GCM, RBAC, **Live Pin IPFS Kubo** | [q03_q04_ipfs_e2e_validation.md](./q03_q04_ipfs_e2e_validation.md) | **PASS** (Live Pin Kubo thật + ảnh Gateway + RBAC) |
| **Q05** | FastAPI REST API, EIP-191 Auth, RBAC, `TRANSFER_LENDING_POSITION_NFT`, `series`, `allowance`/`preview`, tương thích L04 | [q05_api_rbac_validation.md](./q05_api_rbac_validation.md) | **PASS** (Unit + Live Hardhat/Sepolia + 20 kịch bản L04 TS) |
| **Q06** | One-Click `start_all.bat`/`.sh`, `deploy_and_seed.py` (`4.54s <= 30s`), dual-network frontend config, **Live Pin Kubo**, Sepolia 7/7 contracts | [q06_deploy_and_sepolia_validation.md](./q06_deploy_and_sepolia_validation.md) | **PASS** (Unit + Live Local + Kubo + Live Sepolia 7/7) |

## Ảnh minh chứng trong `reports/Quan/screenshots/`

- [ipfs_01_audit_logs_gateway.png](./screenshots/ipfs_01_audit_logs_gateway.png) — Mở trực tiếp CID **Audit Logs JSON (PUBLIC)** trên Kubo Gateway thật (`HTTP 200`, `contains_pii: false`, có đủ kỳ `SIMULATED` và `ON_CHAIN`).
- [ipfs_02_private_ciphertext_gateway.png](./screenshots/ipfs_02_private_ciphertext_gateway.png) — Mở trực tiếp CID **Loan Agreement PDF (PRIVATE)** trên Kubo Gateway thật (`HTTP 200`, chỉ hiển thị phong bì mã hóa `AES-256-GCM`, không rò rỉ `%PDF-` bản rõ).
- **Ảnh chụp trình duyệt Etherscan (TC1):** Tất cả 7 hợp đồng và 4 giao dịch smoke-test chính trên Sepolia đã được kiểm chứng trực tiếp qua RPC (`eth_getCode`, `eth_getTransactionReceipt`, `status == 1`). Khi tự động mở `sepolia.etherscan.io` bằng headless Chrome bị chặn bởi cơ chế chống bot Cloudflare (và Chrome thường chưa bật remote debugging), nên các ảnh chụp màn hình trình duyệt Etherscan cần mở trực tiếp từ danh sách URL trong [q06_deploy_and_sepolia_validation.md](./q06_deploy_and_sepolia_validation.md) và lưu bổ sung vào `reports/Quan/screenshots/`.
