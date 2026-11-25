"""Generate L01 SVG wireframes, editable Draw.io pages and example UI data.

Uses only the Python standard library and the existing HI01 constants.
Run from any directory: python scripts/generate_l01_wireframes.py
"""
from __future__ import annotations

import json
import math
import sys
import xml.etree.ElementTree as ET
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.config import constants as C

OUT = ROOT / "docs" / "Lam" / "wireframes"
WIDTH, HEIGHT = 1600, 1120
INK, MUTED, BORDER = "#183735", "#61736f", "#d6e0dc"
TEAL, TINT, BG, WHITE = "#147d6c", "#e7f3ee", "#f4f7f5", "#ffffff"
AMBER, RED = "#a36514", "#b54741"


class Scene:
    def __init__(self, slug, title):
        self.slug, self.title, self.items = slug, title, []

    def box(self, x, y, w, h, fill=WHITE, stroke=BORDER, radius=12):
        self.items.append(("rect", x, y, w, h, fill, stroke, radius))

    def text(self, x, y, value, size=15, color=INK, bold=False):
        self.items.append(("text", x, y, str(value), size, color, bold))

    def line(self, x1, y1, x2, y2, color=BORDER, width=1):
        self.items.append(("line", x1, y1, x2, y2, color, width))

    def circle(self, x, y, r, fill, stroke="none"):
        self.items.append(("circle", x, y, r, fill, stroke))

    def lines(self, x, y, values, size=14, color=MUTED, step=23):
        for index, value in enumerate(values):
            self.text(x, y + index * step, value, size, color)

    def pill(self, x, y, w, label, fill=TINT, color=TEAL):
        self.box(x, y, w, 30, fill, fill, 15)
        self.text(x + 12, y + 20, label, 12, color, True)

    def button(self, x, y, w, label, disabled=False):
        fill = "#edf0ee" if disabled else TEAL
        self.box(x, y, w, 42, fill, fill, 8)
        self.text(x + 15, y + 27, label, 14, MUTED if disabled else WHITE, True)

    def panel(self, x, y, w, h, title, tag=None):
        self.box(x, y, w, h)
        self.text(x + 22, y + 34, title, 19, bold=True)
        if tag:
            self.text(x + 22, y + 58, tag, 12, MUTED)

    def input(self, x, y, w, value):
        self.box(x, y, w, 45, BG, BORDER, 7)
        self.text(x + 14, y + 29, value, 15)

    def stat(self, x, title, value, detail):
        self.box(x, 196, 304, 110)
        self.text(x + 20, 224, title, 13, MUTED)
        self.text(x + 20, 262, value, 29, bold=True)
        self.text(x + 20, 286, detail, 12, MUTED)

    def shell(self, active, subtitle, role):
        self.box(0, 0, WIDTH, HEIGHT, BG, BG, 0)
        self.box(0, 0, 244, HEIGHT, WHITE, BORDER, 0)
        self.box(24, 30, 42, 42, TEAL, TEAL, 10)
        self.text(33, 58, "DL", 20, WHITE, True)
        self.text(80, 52, "LENDING", 17, bold=True)
        self.text(80, 71, "IS355.R11", 12, MUTED)
        self.text(24, 125, "KHÔNG GIAN LÀM VIỆC", 11, MUTED, True)
        nav = ["Lending Dashboard", "Borrowing Console", "IPFS Document Hub", "Analytics & Demo"]
        for index, label in enumerate(nav):
            y = 150 + index * 58
            if index == active:
                self.box(16, y, 212, 46, TINT, TINT, 8)
            self.text(29, y + 29, str(index + 1).zfill(2), 12, TEAL if index == active else MUTED, True)
            self.text(59, y + 29, label, 14, TEAL if index == active else INK, index == active)
        self.line(24, 428, 220, 428)
        self.lines(24, 460, ["L01 · Thiết kế của Lâm", "Giai đoạn 1", "Khung desktop 1600 px"], 12)
        self.pill(24, 990, 190, "DỮ LIỆU MINH HỌA")
        self.lines(24, 1044, ["Các nút là bản vẽ.", "Chưa kết nối giao dịch."], 12)
        self.text(280, 35, "DEFI LENDING / L01", 12, TEAL, True)
        self.text(280, 78, self.title, 30, bold=True)
        self.text(280, 104, subtitle, 14, MUTED)
        self.pill(1190, 40, 150, "Local · 31337")
        self.pill(1350, 40, 216, role)
        self.box(280, 130, 1286, 42, TINT, TINT, 8)
        self.text(296, 157, "WIREFRAME · Snapshot minh họa theo HI01 · APR on-chain / APY quy đổi tham khảo", 13, TEAL)
        self.line(280, 1075, 1566, 1075)
        self.text(280, 1100, "L01 / H01 + HI01 đã có · API bổ sung chờ xác nhận Q05 · Xem docs/Lam/ui_wireframes.md", 12, MUTED)

    def svg(self):
        parts = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="1120" viewBox="0 0 1600 1120" role="img" aria-labelledby="title desc">',
            "<title id=\"title\">" + escape(self.title) + " — L01</title>",
            '<desc id="desc">Bản vẽ giao diện của Lâm. Dữ liệu minh họa; không phải ứng dụng hoặc kết quả giao dịch thật.</desc>',
            '<g font-family="Arial, Segoe UI, sans-serif">',
        ]
        for item in self.items:
            kind, *a = item
            if kind == "rect":
                x, y, w, h, fill, stroke, r = a
                parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}" stroke="{stroke}"/>')
            elif kind == "text":
                x, y, value, size, color, bold = a
                parts.append(f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" font-weight="{700 if bold else 400}">{escape(value)}</text>')
            elif kind == "line":
                x1, y1, x2, y2, color, width = a
                parts.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{width}" stroke-linecap="round"/>')
            elif kind == "circle":
                x, y, r, fill, stroke = a
                parts.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{fill}" stroke="{stroke}"/>')
        parts.extend(["</g>", "</svg>", ""])
        return "\n".join(parts)

    def drawio_page(self, parent):
        diagram = ET.SubElement(parent, "diagram", id=self.slug, name=self.title)
        model = ET.SubElement(diagram, "mxGraphModel", dx="1600", dy="1120", grid="1", gridSize="10", page="1", pageScale="1", pageWidth="1600", pageHeight="1120", math="0", shadow="0")
        root = ET.SubElement(model, "root")
        ET.SubElement(root, "mxCell", id="0")
        ET.SubElement(root, "mxCell", id="1", parent="0")
        for index, item in enumerate(self.items, 2):
            kind, *a = item
            attrs = {"id": str(index), "parent": "1"}
            if kind == "line":
                x1, y1, x2, y2, color, width = a
                attrs.update(edge="1", value="", style=f"endArrow=none;startArrow=none;strokeColor={color};strokeWidth={width};")
                cell = ET.SubElement(root, "mxCell", attrs)
                geom = ET.SubElement(cell, "mxGeometry", {"relative": "1", "as": "geometry"})
                ET.SubElement(geom, "mxPoint", {"x": str(x1), "y": str(y1), "as": "sourcePoint"})
                ET.SubElement(geom, "mxPoint", {"x": str(x2), "y": str(y2), "as": "targetPoint"})
                continue
            if kind == "rect":
                x, y, w, h, fill, stroke, r = a
                attrs.update(value="", style=f"rounded={int(r > 0)};arcSize=12;fillColor={fill};strokeColor={stroke};")
            elif kind == "circle":
                cx, cy, r, fill, stroke = a
                x, y, w, h = cx-r, cy-r, r*2, r*2
                attrs.update(value="", style=f"ellipse;fillColor={fill};strokeColor={stroke};")
            else:
                x, baseline, value, size, color, bold = a
                y, w, h = baseline-size, min(1580-x, max(30, len(value)*size*0.75+16)), size+10
                attrs.update(value=value, style=f"text;html=0;whiteSpace=wrap;overflow=visible;align=left;verticalAlign=top;spacing=0;fontFamily=Arial;fontSize={size};fontColor={color};fontStyle={int(bold)};")
            attrs["vertex"] = "1"
            cell = ET.SubElement(root, "mxCell", attrs)
            ET.SubElement(cell, "mxGeometry", {"x": str(x), "y": str(y), "width": str(w), "height": str(h), "as": "geometry"})


def lending():
    s = Scene("01-lending-dashboard", "Lending Dashboard")
    s.shell(0, "Thanh khoản Pool, lãi tiền gửi và quyền sở hữu vị thế cho vay.", "Lender · 0x7099…79C8")
    s.stat(280, "SUPPLY APY · THAM KHẢO", "5.1267%", "APR on-chain: 5.00% / năm")
    s.stat(608, "TỔNG GỬI VÀO POOL", "1,000.00", "MyUSDT · Tổng vay: 500.00")
    s.stat(936, "THANH KHOẢN KHẢ DỤNG", "500.00", "MyUSDT · Lấy từ số dư Pool thực tế")
    s.stat(1264, "LÃI CỦA TÔI", "0.000000", "MyUSDT · Cập nhật theo timestamp")
    s.panel(280, 330, 800, 334, "Gửi & rút MyUSDT", "Số dư ví minh họa: 1,000.00 MyUSDT (đã lấy thêm faucet)")
    s.text(302, 423, "GỬI TIỀN", 13, TEAL, True)
    s.input(302, 439, 345, "1,000.00 MyUSDT")
    s.lines(302, 514, ["Cấp quyền đúng lượng trước khi gửi.", "Bạn nhận LendingPositionNFT."], 13)
    s.button(302, 582, 345, "Xem trước giao dịch gửi")
    s.text(688, 423, "RÚT TIỀN · VỊ THẾ #1", 13, bold=True)
    s.input(688, 439, 368, "600.00 MyUSDT")
    s.lines(688, 514, ["Quyền rút: 1,000.00 · Pool rỗi: 500.00", "Số tiền vượt thanh khoản khả dụng."], 13, RED)
    s.button(688, 582, 368, "Rút tiền · Chưa hợp lệ", True)
    s.panel(1104, 330, 462, 334, "Xem trước khi ký", "Chỉ mở MetaMask sau khi kiểm tra lại dữ liệu")
    s.lines(1126, 423, [
        "Hành động: approve → depositLender",
        "Số lượng: 1,000.00 MyUSDT",
        "MyUSDT: 0x5FbD…0aa3 · Pool: chờ HI02",
        "Phí gas: ước lượng từ RPC trước khi ký",
        "APR hiện tại: 5.00% · Sau gửi: tính lại",
        "Chặn ký nếu chưa có địa chỉ/code Pool.",
    ], 13, step=28)
    s.panel(280, 688, 1286, 190, "Lending Position NFT", "Chủ NFT hiện tại có quyền rút gốc + lãi của vị thế")
    for x, label in [(302, "VỊ THẾ"), (510, "GỐC / LÃI"), (855, "CHỦ HIỆN TẠI"), (1290, "HÀNH ĐỘNG")]:
        s.text(x, 778, label, 12, MUTED, True)
    s.line(302, 791, 1544, 791)
    s.text(302, 824, "#1 · Đang hoạt động", 14)
    s.text(510, 824, "1,000.00 / 0.000000 MyUSDT", 14)
    s.text(855, 824, "0x7099…79C8 (ví của bạn)", 14)
    s.button(1290, 800, 252, "Chuyển nhượng NFT")
    s.panel(280, 902, 1286, 150, "Trạng thái dùng chung")
    s.lines(302, 971, [
        "Chưa kết nối: xem số liệu công khai; nút ghi chuyển thành Kết nối ví. Sai mạng: yêu cầu chuyển mạng.",
        "Luồng ký: Xem trước → Chờ ký → Đang xác nhận → Thành công / Thất bại. Approve và gửi có trạng thái riêng.",
        "Sau chuyển NFT: làm mới ownerOf; ví cũ mất quyền rút, ví nhận thấy gốc và lãi của vị thế.",
    ], 13, step=27)
    return s


def borrowing():
    s = Scene("02-borrowing-console", "Borrowing Console")
    s.shell(1, "Quản lý tài sản thế chấp, khoản vay và mức an toàn.", "Borrower · 0x3C44…93BC")
    s.stat(280, "TÀI SẢN THẾ CHẤP", "1,000.00", "MyUSDT · CollateralNFT #7")
    s.stat(608, "TỔNG DƯ NỢ", "500.00", "MyUSDT · Gốc 500 / Lãi 0")
    s.stat(936, "CÓ THỂ VAY THÊM", "200.00", "Trần tổng nợ: 700.00 · LTV ≤ 70%")
    s.stat(1264, "BORROW APR · ON-CHAIN", "10.00%", "APY quy đổi tham khảo: 10.5156%")
    s.panel(280, 330, 402, 376, "Tài sản & biên nhận", "Token / CollateralNFT")
    s.lines(302, 425, [
        "NFT #7 · Định giá: 1,000.00 MyUSDT",
        "Biên nhận #1 · Đang khóa · Không chuyển",
        "DebtToken: 500.00 · Không chuyển",
    ], 13, step=28)
    s.pill(302, 500, 126, "Token", BG, MUTED)
    s.pill(440, 500, 218, "CollateralNFT")
    s.input(302, 545, 210, "Token ID #7")
    s.button(526, 546, 132, "Thế chấp", True)
    s.text(302, 605, "Có vị thế đang khóa: chặn thế chấp mới.", 12, MUTED)
    s.button(302, 622, 356, "Rút thế chấp · Còn dư nợ", True)
    s.text(302, 689, "Trả hết nợ: mở khóa và tất toán biên nhận.", 12, MUTED)
    s.panel(706, 330, 432, 376, "Vay thêm / Trả nợ")
    s.text(728, 405, "VAY THÊM · TỐI ĐA 200.00", 13, TEAL, True)
    s.input(728, 422, 388, "100.00 MyUSDT")
    s.line(738, 493, 1105, 493, BORDER, 6)
    s.line(738, 493, 922, 493, TEAL, 6)
    s.circle(922, 493, 8, TEAL)
    s.text(728, 522, "LTV sau vay: 60% · HF sau vay: 1.33", 13, AMBER)
    s.button(728, 540, 388, "Tạo hồ sơ & xem trước khoản vay")
    s.text(728, 619, "TỔNG CẦN TRẢ HIỆN TẠI: 500.00", 13, bold=True)
    s.button(728, 639, 388, "Xem trước giao dịch trả nợ")
    s.panel(1162, 330, 404, 376, "Health Factor", "Hiện tại: SAFE · Sau vay thêm cần kiểm tra lại")
    cx, cy, r = 1364, 555, 118
    for start, end, color in [(0, 0.4, RED), (0.4, 0.6, AMBER), (0.6, 1, TEAL)]:
        points = [(cx + r*math.cos(math.pi*(1-t)), cy-r*math.sin(math.pi*(1-t))) for t in [start+(end-start)*i/20 for i in range(21)]]
        for a, b in zip(points, points[1:]):
            s.line(*a, *b, color, 9)
    angle = math.pi*(1-1.6/2.5)
    s.line(cx, cy, cx+82*math.cos(angle), cy-82*math.sin(angle), INK, 3)
    s.circle(cx, cy, 6, INK)
    s.text(1322, 608, "1.60", 32, TEAL, True)
    s.text(1184, 652, "Đỏ < 1 · Vàng [1, 1.5) · Xanh ≥ 1.5", 13)
    s.text(1184, 680, "Không có dư nợ: ∞ · Không thanh lý", 13, MUTED)
    s.panel(280, 730, 858, 170, "Xem trước giao dịch vay")
    s.lines(302, 796, [
        "Vay thêm 100.00 → nợ dự kiến 600.00 → mint thêm 100.00 DebtToken.",
        "APR hiện tại 10.00%; sau vay dự kiến 11.00% (Pool U = 60%).",
        "Pool: từ registry HI02 · Gas: ước lượng trước khi ký · Lãi dự tính: ghi rõ kỳ hạn.",
        "PDF + CID có trước giao dịch vay; txHash chỉ gắn sau receipt thành công.",
    ], 13, step=26)
    s.panel(1162, 730, 404, 170, "Thanh lý khoản vay")
    s.text(1184, 796, "Ví thực hiện cần đủ token và allowance.", 13)
    s.button(1184, 817, 358, "Thanh lý · HF hiện tại ≥ 1", True)
    s.text(1184, 883, "HF = 1.00 vẫn chặn; HF < 1 mới cho ký.", 12, RED)
    s.panel(280, 924, 1286, 128, "Các trạng thái phải có")
    s.lines(302, 990, [
        "Không có thế chấp → chặn vay · Vượt LTV 70% / thiếu thanh khoản → chặn · CID chưa sẵn sàng → chặn.",
        "HF < 1: banner đỏ, cho ví đủ điều kiện ký liquidate(); không có cơ chế tự thanh lý khi chỉ mở trang.",
    ], 13, step=28)
    return s


def documents():
    s = Scene("03-ipfs-document-hub", "IPFS Document & Credit Hub")
    s.shell(2, "Tra cứu hồ sơ, kiểm tra quyền và tải tài liệu theo CID.", "Borrower · 0x3C44…93BC")
    s.panel(280, 196, 850, 380, "Hồ sơ của tôi & dữ liệu công khai", "Bộ lọc: Tất cả / Loan Agreement / Credit Report / Audit Logs")
    for x, text in [(302, "HỒ SƠ"), (602, "ĐỊNH DẠNG"), (735, "QUYỀN"), (957, "THAO TÁC")]:
        s.text(x, 292, text, 12, MUTED, True)
    rows = [
        ("Loan Agreement #1", "PDF", "Riêng tư · Của tôi", "Xem / Tải"),
        ("Credit Report", "JSON", "Riêng tư · Của tôi", "Xem / Tải"),
        ("Audit Logs tháng mẫu", "JSON", "Công khai", "Xem / Tải"),
    ]
    for i, row in enumerate(rows):
        y = 335 + 66*i
        s.line(302, y-23, 1107, y-23)
        for x, val in zip([302, 602, 735, 957], row):
            s.text(x, y, val, 14)
    s.lines(302, 531, ["CID: lấy từ backend / on-chain khi có dữ liệu thật.", "Không hiển thị hồ sơ riêng tư của ví khác trong danh sách."], 13)
    s.panel(1154, 196, 412, 380, "Tra cứu / Retrieve theo CID")
    s.input(1176, 274, 368, "Nhập CID hợp lệ")
    s.text(1176, 352, "Loại hồ sơ: tự nhận diện từ metadata", 13)
    s.button(1176, 377, 368, "Kiểm tra quyền & tải tài liệu")
    s.lines(1176, 459, [
        "1. Kiểm tra CID và phiên đăng nhập",
        "2. Backend xác minh chủ hồ sơ / Admin",
        "3. Nhận nội dung được phép truy cập",
        "4. Kiểm tra hash và mở / tải file",
    ], 13, step=28)
    s.panel(280, 600, 850, 260, "Chi tiết Loan Agreement #1", "Chỉ hiện sau khi truy cập được phép")
    s.lines(302, 698, [
        "Ví chủ hồ sơ: 0x3C44…93BC · Khoản vay: #1 · Số tiền: 500.00 MyUSDT",
        "CID / SHA-256: lấy từ tài liệu Q03 khi được tạo.",
        "Trước vay: trạng thái Chờ giao dịch; trường txHash chưa có.",
        "Sau receipt thành công: hiển thị txHash và liên kết explorer nếu là Sepolia.",
        "Các ví không được cấp quyền không nhận nội dung giải mã hoặc khóa.",
    ], 13, step=28)
    s.panel(1154, 600, 412, 260, "Trạng thái truy cập")
    s.lines(1176, 681, [
        "401 · Cần kết nối ví và ký đăng nhập",
        "403 · Bạn không có quyền xem hồ sơ",
        "Đang tải · Lỗi gateway · Thử lại",
        "Sai hash · Dừng mở tài liệu",
        "Không có hồ sơ · Hiển thị trạng thái rỗng",
    ], 13, step=30)
    s.panel(280, 884, 1286, 168, "Phân quyền trên giao diện")
    s.lines(302, 953, [
        "Khách / Lender: xem Audit Logs công khai. Borrower: thêm hồ sơ của chính mình. Admin: theo quyền backend cấp.",
        "Ký đăng nhập là ký thông điệp, không tốn gas. Thay đổi ví hoặc mạng sẽ xóa phiên và làm mới danh sách.",
        "Biết CID không đồng nghĩa được đọc bản giải mã. Nút Retrieve vẫn kiểm tra quyền ở backend.",
    ], 13, step=28)
    return s


def analytics():
    s = Scene("04-analytics-demo", "Analytics & Demo Control")
    s.shell(3, "Biểu đồ tổng hợp và bảng điều khiển kịch bản demo local.", "Admin · 0xf39F…2266")
    s.panel(280, 196, 770, 380, "Biến động lãi suất theo tháng", "SIMULATED · 6 tháng minh họa · Đơn vị % / năm (APR)")
    s.line(344, 493, 1007, 493)
    s.line(344, 302, 344, 493)
    for tick, y in [("15%", 306), ("10%", 370), ("5%", 434), ("0%", 498)]:
        s.text(297, y, tick, 12, MUTED)
        s.line(344, y-4, 1007, y-4)
    months, borrow, supply = ["T1", "T2", "T3", "T4", "T5", "T6"], [5, 7.5, 10, 12, 7.5, 10], [0, 1.87, 5, 8.4, 1.87, 5]
    for values, color in [(borrow, TEAL), (supply, "#5e6fbc")]:
        points = [(360+i*125, 490-value*12.4) for i, value in enumerate(values)]
        for a, b in zip(points, points[1:]):
            s.line(*a, *b, color, 3)
        for x, y in points:
            s.circle(x, y, 4, color)
    for i, month in enumerate(months):
        s.text(350+i*125, 521, month, 12, MUTED)
    s.text(347, 554, "Borrow APR", 12, TEAL, True)
    s.text(510, 554, "Supply APR", 12, "#5e6fbc", True)
    s.text(668, 554, "Dữ liệu thật: InterestRateUpdated", 12, MUTED)
    s.panel(1074, 196, 492, 380, "Cơ cấu tài sản ví Borrower", "Snapshot minh họa · Quy đổi cùng đơn vị MyUSDT")
    s.text(1096, 309, "MyUSDT khả dụng", 14)
    s.box(1096, 329, 438, 32, BG, BG, 5)
    s.box(1096, 329, 263, 32, TEAL, TEAL, 5)
    s.text(1096, 391, "1,500.00 MyUSDT · 60% tài sản", 14, TEAL, True)
    s.text(1096, 427, "Thế chấp khóa: 1,000.00 · 40%", 14)
    s.text(1096, 463, "Nợ / DebtToken: 500.00 · Hiển thị riêng", 14, RED)
    s.lines(1096, 507, ["NFT #7 tính theo giá oracle; không cộng số NFT", "với số token. DebtToken không tính vào tài sản."], 12)
    s.panel(280, 600, 1286, 240, "Điều khiển demo", "Tua thời gian / điều chỉnh oracle chỉ dành cho Local 31337 và đúng quyền")
    for x, title, line1, line2, action in [
        (302, "01 · FAUCET", "Nhận tối đa 1,000 MyUSDT/lần.", "Bất kỳ ví đã kết nối có thể nhận.", "Xem trước faucet"),
        (725, "02 · TUA 60 NGÀY", "Tăng 5,184,000 giây trên Hardhat.", "Admin local; sau đó mine block.", "Tua thời gian local"),
        (1148, "03 · GIẢM GIÁ 40%", "Oracle multiplier = 6,000 BPS.", "Admin UI và owner oracle hợp lệ.", "Xem trước đổi giá"),
    ]:
        s.text(x, 698, title, 13, TEAL, True)
        s.lines(x, 732, [line1, line2], 12)
        s.button(x, 782, 385, action)
    s.panel(280, 864, 1286, 188, "Kịch bản demo & kết quả dự kiến")
    s.lines(302, 934, [
        "Lender gửi 1,000 → Borrower thế chấp 1,000, vay 500 → Tua 60 ngày → Trả nợ → Lender rút vốn.",
        "Lãi dự kiến 60 ngày: 8.219178 MyUSDT; khoản trả 508.219178; tổng quyền rút 1,008.219178 (theo HI01).",
        "Demo thanh lý riêng: giữ nợ 500, giảm định giá từ 1,000 xuống 600 → HF 0.96 → ví liquidator approve rồi ký.",
        "Sepolia: ẩn/vô hiệu hóa tua thời gian và mock giá. Thiếu RPC / quyền / contract: chặn thao tác tương ứng.",
    ], 13, step=27)
    return s


def examples():
    supplied, borrowed, collateral = 1000*C.WAD, 500*C.WAD, 1000*C.WAD
    utilization = C.calculate_utilization_bps(borrowed, supplied)
    apr = C.calculate_borrow_apr_bps(utilization)
    supply_apr = C.calculate_supply_apr_bps(apr, utilization)
    def amount(value):
        return {"amount_wad": str(value), "amount_display": C.wad_to_decimal_str(value)}
    manifest = json.loads((ROOT / "deployments/localhost.json").read_text(encoding="utf-8"))
    return {
        "status": "DESIGN_EXAMPLE_NOT_IMPLEMENTED_API",
        "task": "L01",
        "data_kind": "SIMULATED",
        "network": {"name": "local", "chain_id": 31337, "myusdt_address": manifest["contracts"]["MyUSDT"]["address"], "lending_pool_address": None},
        "pool": {
            "total_supplied": amount(supplied), "total_borrowed": amount(borrowed),
            "available_liquidity": amount(500*C.WAD), "utilization_bps": utilization,
            "borrow_apr_bps": apr, "borrow_apr_percent": C.apr_bps_to_percent(apr), "borrow_apy_percent": C.apr_bps_to_apy_percent(apr),
            "supply_apr_bps": supply_apr, "supply_apr_percent": C.apr_bps_to_percent(supply_apr), "supply_apy_percent": C.apr_bps_to_apy_percent(supply_apr),
        },
        "lender_positions": [{
            "position_id": "1", "owner": manifest["contracts"]["MyUSDT"]["testAccounts"][1]["address"],
            "principal": amount(supplied), "earned_interest": amount(0),
            "claimable": amount(supplied), "active": True,
        }],
        "loan": {
            "borrower": manifest["contracts"]["MyUSDT"]["testAccounts"][2]["address"],
            "is_nft_collateral": True, "collateral_token_id": "7", "receipt_id": "1", "receipt_active": True,
            "debt_token_balance": amount(borrowed),
            "collateral_value": amount(collateral), "principal": amount(borrowed), "accrued_interest": amount(0),
            "total_debt": amount(borrowed), "max_total_debt": amount(C.calculate_max_borrow(collateral)),
            "remaining_ltv_capacity": amount(200*C.WAD), "available_to_borrow": amount(200*C.WAD),
            "health": C.format_health_factor_for_api(C.calculate_health_factor(collateral, borrowed)),
            "agreement_cid": None, "transaction_hash": None,
        },
        "borrow_preview": {"amount": amount(100*C.WAD), "resulting_debt": amount(600*C.WAD), "resulting_health": C.format_health_factor_for_api(C.calculate_health_factor(collateral, 600*C.WAD)), "resulting_borrow_apr_bps": C.calculate_borrow_apr_bps(6000), "estimated_gas": None, "gas_price_wei": None, "unsigned_tx": None, "submit_enabled": False, "blocked_reason": "CONTRACT_NOT_DEPLOYED"},
        "health_scenarios": [
            {"label": label, "collateral_value": amount(cv), "total_debt": amount(debt), **C.format_health_factor_for_api(C.calculate_health_factor(cv, debt))}
            for label, cv, debt in [
                ("SAFE", 1000*C.WAD, 500*C.WAD),
                ("WARNING", 1000*C.WAD, 700*C.WAD),
                ("EXACT_HF_1", 1000*C.WAD, 800*C.WAD),
                ("LIQUIDATABLE", 600*C.WAD, 500*C.WAD),
                ("NO_DEBT", 1000*C.WAD, 0),
            ]
        ],
        "demo_60_days": {"elapsed_seconds": 60*86400, "interest": amount(C.calculate_simple_interest(borrowed, apr, 60*86400)), "repayment": amount(borrowed+C.calculate_simple_interest(borrowed, apr, 60*86400))},
        "document_examples": [
            {"kind": "LOAN_AGREEMENT", "format": "PDF", "visibility": "PRIVATE", "cid": None, "owner": "CURRENT_BORROWER", "can_retrieve_plaintext": "AFTER_SERVER_AUTHORIZATION"},
            {"kind": "CREDIT_REPORT", "format": "JSON", "visibility": "PRIVATE", "encrypted": True, "cid": None, "owner": "CURRENT_BORROWER", "can_retrieve_plaintext": "AFTER_SERVER_AUTHORIZATION"},
            {"kind": "AUDIT_LOGS", "format": "JSON", "visibility": "PUBLIC", "cid": None, "data_kind": "SIMULATED"},
        ],
        "wallet_events": ["accountsChanged", "chainChanged", "disconnect"],
        "transaction_states": ["IDLE", "VALIDATING", "AWAITING_SIGNATURE", "PENDING", "CONFIRMED", "REJECTED", "REVERTED", "UNKNOWN"],
    }


def main():
    required = ["docs/Hieu/smart_contract_spec.md", "docs/Hung/h01_myusdt_handoff.md", "contracts/tokens/MyUSDT.sol", "contracts/interfaces/ILendingPool.sol", "contracts/interfaces/IPriceOracle.sol", "contracts/interfaces/ILendingPositionNFT.sol", "deployments/abi/MyUSDT.json", "deployments/localhost.json"]
    missing = [name for name in required if not (ROOT/name).is_file()]
    if missing:
        raise SystemExit("Missing H01/HI01 handoff files; stop L01: " + ", ".join(missing))
    OUT.mkdir(parents=True, exist_ok=True)
    scenes = [lending(), borrowing(), documents(), analytics()]
    mxfile = ET.Element("mxfile", host="app.diagrams.net", type="device", version="24.7.17")
    for scene in scenes:
        (OUT/(scene.slug+".svg")).write_text(scene.svg(), encoding="utf-8")
        scene.drawio_page(mxfile)
    ET.indent(mxfile, space="  ")
    ET.ElementTree(mxfile).write(OUT/"l01-ui-wireframes.drawio", encoding="utf-8", xml_declaration=True)
    (OUT/"l01-ui-examples.json").write_text(json.dumps(examples(), ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print("Generated 4 SVG screens, 4 editable Draw.io pages and L01 JSON examples.")


if __name__ == "__main__":
    main()
