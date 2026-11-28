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

### IPFS Kubo Live Gateway (Tiêu chí 3)
- [ipfs_01_audit_logs_gateway.png](./screenshots/ipfs_01_audit_logs_gateway.png) — Mở trực tiếp CID **Audit Logs JSON (PUBLIC)** trên Kubo Gateway thật (`HTTP 200`, `contains_pii: false`, có đủ kỳ `SIMULATED` và `ON_CHAIN`).
- [ipfs_02_private_ciphertext_gateway.png](./screenshots/ipfs_02_private_ciphertext_gateway.png) — Mở trực tiếp CID **Loan Agreement PDF (PRIVATE)** trên Kubo Gateway thật (`HTTP 200`, chỉ hiển thị phong bì mã hóa `AES-256-GCM`, không rò rỉ `%PDF-` bản rõ).

### Ethereum Sepolia Etherscan (Tiêu chí 1 & 4)
- [sepolia_01_lending_pool_contract.png](./screenshots/sepolia_01_lending_pool_contract.png) — Hợp đồng lõi `LendingPool` trên Sepolia (`0x2BC016744561Dca45a1398dF4309572ccB66a0c1`).
- [sepolia_02_price_oracle_contract.png](./screenshots/sepolia_02_price_oracle_contract.png) — Hợp đồng `PriceOracle` trên Sepolia (`0x85cdeb0BA90C69006D61f13F131BC03f16Da484a`).
- [sepolia_03_deployer_all_7_contracts.png](./screenshots/sepolia_03_deployer_all_7_contracts.png) — Ví Deployer Sepolia (`0x3bEda0f07bf14749B907707b6D48135f2B1a73E7`) thể hiện đủ 7 giao dịch deploy hợp đồng, bind và smoke-test.
- [sepolia_04_tx_deposit_lender.png](./screenshots/sepolia_04_tx_deposit_lender.png) — Giao dịch `depositLender` (`Success`, nạp `500 MyUSDT`, mint `LendingPositionNFT #1`).
- [sepolia_05_tx_deposit_collateral_nft.png](./screenshots/sepolia_05_tx_deposit_collateral_nft.png) — Giao dịch `depositCollateral` (`Success`, khóa `CollateralNFT #1`, mint `CollateralReceiptNFT #1`).
- [sepolia_06_tx_borrow.png](./screenshots/sepolia_06_tx_borrow.png) — Giao dịch `borrow` (`Success`, vay `100 MyUSDT`, mint `100 DEBT`).
- [sepolia_07_tx_repay.png](./screenshots/sepolia_07_tx_repay.png) — Giao dịch `repay` (`Success`, trả gốc + lãi `100.000005... MyUSDT`, burn `DEBT` & `CollateralReceiptNFT #1`, hoàn trả `CollateralNFT #1`).
