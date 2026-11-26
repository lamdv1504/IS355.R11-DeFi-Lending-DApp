"""ReportLab PDF template for Decentralized Loan Agreements (H03 -> Q03 handoff).

Generates a structured, professional PDF Loan Agreement containing:
- Agreement ID, Nonce, UTC & UTC+7 timestamps, Network & Chain ID
- Borrower Wallet Address & Wallet Auth Session Status
- Collateral Asset Details (ERC-20 / CollateralNFT, Valuation in MyUSDT WAD & display)
- Loan Terms (Principal, Max LTV 70%, Liquidation Threshold 80%, Liquidation Bonus 5%)
- Clear distinction between on-chain simple APR and daily-compounded reference APY
- Pre-borrow txHash notice (NEVER embeds a fabricated txHash before borrow() confirmation)
"""

from __future__ import annotations

import io
import unicodedata
from pathlib import Path
from typing import Dict, Tuple

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from src.documents.schemas import LoanAgreementPayload
from src.ipfs.cid_utils import compute_cid_v1, sha256_bytes

_FONT_CANDIDATES: Tuple[Tuple[str, str, str], ...] = (
    ("DeFiSans", r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\arialbd.ttf"),
    ("DeFiSans", r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\segoeuib.ttf"),
    ("DeFiSans", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
)


def _select_fonts() -> Tuple[str, str, bool]:
    """Register a Unicode TTF font pair when readable, else fall back cleanly to Helvetica."""
    registered = set(pdfmetrics.getRegisteredFontNames())
    if "DeFiSans" in registered and "DeFiSans-Bold" in registered:
        return "DeFiSans", "DeFiSans-Bold", True

    for family, regular_path, bold_path in _FONT_CANDIDATES:
        reg = Path(regular_path)
        bold = Path(bold_path)
        try:
            if reg.is_file() and bold.is_file():
                pdfmetrics.registerFont(TTFont(family, str(reg)))
                pdfmetrics.registerFont(TTFont(f"{family}-Bold", str(bold)))
                return family, f"{family}-Bold", True
        except Exception:
            continue
    return "Helvetica", "Helvetica-Bold", False


def _safe_text(text: str, unicode_ready: bool) -> str:
    """Keep full Vietnamese diacritics when a Unicode font is loaded; fold cleanly for Helvetica."""
    if unicode_ready:
        return text
    replaced = text.replace("Đ", "D").replace("đ", "d")
    normalized = unicodedata.normalize("NFKD", replaced)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def render_loan_agreement_pdf(payload: LoanAgreementPayload) -> bytes:
    """Render ``LoanAgreementPayload`` into a ReportLab PDF document (bytes)."""
    font_regular, font_bold, unicode_ready = _select_fonts()
    t = lambda s: _safe_text(s, unicode_ready)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=f"DeFi Loan Agreement - {payload.agreement_id}",
        author="IS355.R11 DeFi Lending DApp",
        subject="Decentralized Loan Agreement for IPFS Archival (H03/Q03)",
        invariant=1,
    )

    styles = getSampleStyleSheet()
    navy = colors.HexColor("#0F2942")
    slate = colors.HexColor("#334155")
    border_color = colors.HexColor("#CBD5E1")
    bg_tint = colors.HexColor("#F1F5F9")
    warn_bg = colors.HexColor("#FEF3C7")
    warn_border = colors.HexColor("#D97706")

    title_style = ParagraphStyle(
        "AgreementTitle",
        parent=styles["Title"],
        fontName=font_bold,
        fontSize=15,
        leading=20,
        textColor=navy,
        spaceAfter=4,
    )
    subtitle_style = ParagraphStyle(
        "AgreementSubtitle",
        parent=styles["Normal"],
        fontName=font_regular,
        fontSize=9.5,
        leading=13,
        textColor=slate,
        alignment=1,
        spaceAfter=10,
    )
    heading_style = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        fontName=font_bold,
        fontSize=11,
        leading=14,
        textColor=navy,
        spaceBefore=10,
        spaceAfter=5,
    )
    body_style = ParagraphStyle(
        "BodyTextCustom",
        parent=styles["Normal"],
        fontName=font_regular,
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#0F172A"),
    )
    cell_label_style = ParagraphStyle(
        "CellLabel",
        parent=body_style,
        fontName=font_bold,
        fontSize=8.5,
        leading=11.5,
        textColor=navy,
    )
    cell_value_style = ParagraphStyle(
        "CellValue",
        parent=body_style,
        fontName=font_regular,
        fontSize=8.5,
        leading=11.5,
    )

    story = [
        Paragraph(t("THỎA THUẬN VAY VỐN PHI TẬP TRUNG (DEFI LOAN AGREEMENT)"), title_style),
        Paragraph(
            t("IS355.R11 – Hệ thống Tín dụng & Cho vay Phi tập trung | Tài liệu lưu trữ IPFS (Tiêu chí 3)"),
            subtitle_style,
        ),
    ]

    if payload.data_kind == "SIMULATED":
        banner_table = Table(
            [
                [
                    Paragraph(
                        t(
                            "<b>MẪU MÔ PHỎNG (SIMULATED SAMPLE TEMPLATE – H03):</b> "
                            "Dữ liệu minh họa phục vụ kiểm thử cấu trúc PDF/IPFS và bàn giao cho Q03; "
                            "không đại diện cho giao dịch vay thật trên chuỗi."
                        ),
                        body_style,
                    )
                ]
            ],
            colWidths=[174 * mm],
        )
        banner_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), warn_bg),
                    ("BOX", (0, 0), (-1, -1), 0.8, warn_border),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        story.extend([banner_table, Spacer(1, 6)])

    def _kv_table(rows: list[tuple[str, str]]) -> Table:
        table_data = [
            [Paragraph(t(label), cell_label_style), Paragraph(t(value), cell_value_style)]
            for label, value in rows
        ]
        tbl = Table(table_data, colWidths=[56 * mm, 118 * mm])
        tbl.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, -1), bg_tint),
                    ("GRID", (0, 0), (-1, -1), 0.5, border_color),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        return tbl

    # Section 1: Metadata & Identity
    story.append(Paragraph(t("1. THÔNG TIN ĐỊNH DANH THỎA THUẬN & NGƯỜI VAY"), heading_style))
    story.append(
        _kv_table(
            [
                ("Mã thỏa thuận (Agreement ID)", payload.agreement_id),
                ("Agreement Nonce", payload.agreement_nonce),
                ("Thời gian khởi tạo (UTC+7)", f"{payload.created_at_vn} ({payload.created_at_utc})"),
                ("Mạng Blockchain / Chain ID", f"{payload.network} (Chain ID: {payload.chain_id})"),
                (
                    "Địa chỉ LendingPool",
                    payload.lending_pool_address or "PENDING_DEPLOYMENT (Chưa triển khai ở giai đoạn H03)",
                ),
                ("Địa chỉ ví Người vay (Borrower)", payload.borrower_wallet),
                ("Phân loại quyền truy cập", f"{payload.visibility} (AES-256-GCM trước khi đẩy IPFS)"),
            ]
        )
    )

    # Section 2: Collateral
    col = payload.collateral
    story.append(Paragraph(t("2. TÀI SẢN THẾ CHẤP SỐ HÓA (COLLATERAL)"), heading_style))
    story.append(
        _kv_table(
            [
                ("Loại tài sản thế chấp", col.asset_type),
                ("Mã tài sản / Số lượng", col.asset_id_or_amount),
                ("Biên nhận thế chấp (Receipt NFT)", col.receipt_token_id or "Chờ cấp phát khi depositCollateral()"),
                ("Định giá hiện tại (MyUSDT)", f"{col.valuation_display} MyUSDT (WAD: {col.valuation_wad})"),
                ("Mô tả tài sản", col.asset_description),
            ]
        )
    )

    # Section 3: Economic Loan Terms (APR vs APY strictly separated!)
    terms = payload.loan_terms
    story.append(Paragraph(t("3. ĐIỀU KHOẢN KHOẢN VAY, LTV & LÃI SUẤT (APR / APY)"), heading_style))
    story.append(
        _kv_table(
            [
                ("Số tiền vay gốc (Principal)", f"{terms.principal_display} MyUSDT (WAD: {terms.principal_wad})"),
                (
                    "Tỷ lệ LTV khoản vay / Trần LTV",
                    f"{terms.requested_ltv_bps / 100:.2f}% / Tối đa {terms.max_ltv_bps / 100:.2f}% ({terms.max_ltv_bps} BPS)",
                ),
                (
                    "Ngưỡng thanh lý / Thưởng thanh lý",
                    f"{terms.liquidation_threshold_bps / 100:.2f}% ({terms.liquidation_threshold_bps} BPS) / "
                    f"Thưởng {terms.liquidation_bonus_bps / 100:.2f}% ({terms.liquidation_bonus_bps} BPS)",
                ),
                (
                    "Lãi suất vay On-chain (APR đơn)",
                    f"{terms.borrow_apr_percent:.2f}% / năm ({terms.borrow_apr_bps} BPS – tính theo block.timestamp)",
                ),
                (
                    "Lãi suất quy đổi tham khảo (APY)",
                    f"{terms.borrow_apy_percent:.4f}% / năm (quy đổi lãi kép theo ngày n=365, chỉ tham khảo)",
                ),
                ("Cơ sở tính lãi", terms.interest_accrual_basis),
            ]
        )
    )

    # Section 4: Smart Contract & Financial Inclusion Clauses
    story.append(Paragraph(t("4. CAM KẾT THỰC THI SMART CONTRACT & THANH LÝ"), heading_style))
    for clause in payload.legal_clauses:
        story.append(Paragraph(t(clause), body_style))
        story.append(Spacer(1, 3))

    # Section 5: Verification & Post-Confirm TxHash Reconciliation Block
    story.append(Paragraph(t("5. XÁC THỰC CHỮ KÝ VÍ & ĐỐI CHIẾU GIAO DỊCH ON-CHAIN"), heading_style))
    tx_display = (
        payload.tx_hash
        if payload.tx_hash
        else "PENDING_ON_CHAIN_CONFIRMATION (PDF sinh trước khi ký borrow(); đối chiếu CID <-> Loan <-> TxHash sau receipt)"
    )
    story.append(
        _kv_table(
            [
                ("Trạng thái thỏa thuận", payload.status),
                ("Xác thực chữ ký ví (Session Auth)", payload.wallet_auth_signature or "PENDING_WALLET_SIGNATURE"),
                ("Transaction Hash (borrow)", tx_display),
                ("Lưu ý bảo mật", "Hệ thống không lưu Private Key MetaMask; khóa giải mã IPFS không nằm trong PDF hoặc CID."),
            ]
        )
    )

    doc.build(story)
    return buffer.getvalue()


def save_loan_agreement_pdf(
    payload: LoanAgreementPayload,
    output_path: str | Path,
) -> Dict[str, object]:
    """Render and save a Loan Agreement PDF to ``output_path``, returning hashes & CIDv1."""
    pdf_bytes = render_loan_agreement_pdf(payload)
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(pdf_bytes)
    return {
        "path": str(target),
        "size_bytes": len(pdf_bytes),
        "sha256": sha256_bytes(pdf_bytes),
        "cid_v1_plaintext": compute_cid_v1(pdf_bytes),
    }

