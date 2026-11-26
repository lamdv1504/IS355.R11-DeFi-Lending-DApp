# Tích hợp IPFS (H03)

Module dùng chung do **Hùng (`H03`)** bàn giao cho **Quân (`Q03`, `Q04`, `Q05`)** và **Lâm (`L04`)**:

- [`ipfs_client.py`](ipfs_client.py): `IPFSClient`, `IPFSConfig`, `LocalPinnedStore` hỗ trợ Pinata Cloud, IPFS Kubo Local Node và tầng dự phòng local content-addressed kèm xác minh SHA-256/CIDv1.
- [`cid_utils.py`](cid_utils.py): Tính SHA-256, IPFS CIDv1 chuẩn `raw-leaves` / UnixFS `dag-pb`, xác thực định dạng CIDv0/CIDv1.
- [`encryption.py`](encryption.py): Mã hóa xác thực `AES-256-GCM` + dẫn xuất khóa `HKDF-SHA256` theo từng tài liệu cho hồ sơ riêng tư.
- [`rbac.py`](rbac.py): Ma trận phân quyền `GUEST / LENDER / BORROWER / ADMIN` và `AuthorizedIPFSGateway` cưỡng chế kiểm tra quyền `401 / 403 / 200` trước khi giải mã.

Xem hướng dẫn chi tiết tại [Tài liệu bàn giao H03](../../docs/Hung/h03_ipfs_storage_rbac_handoff.md).
