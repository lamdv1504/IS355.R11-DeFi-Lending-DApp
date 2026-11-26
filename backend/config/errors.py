"""Canonical Solidity Custom Error registry & Vietnamese decoder (HI03).

Shared handoff module for Quân (Q02 Web3.py / Q05 FastAPI) and Lâm (L02/L03/L05 Frontend)
so every on-chain revert from `LendingPool`, `MyUSDT`, and H02 Token/NFT contracts decodes
into a deterministic error code, HTTP status, structured WAD fields, and clear Vietnamese UI message.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Callable, Dict, Optional, Tuple

from eth_abi import decode as abi_decode
from web3 import Web3

from backend.config.constants import WAD, wad_to_decimal_str

HEX_DATA_PATTERN = re.compile(r"0x[0-9a-fA-F]{8,}")


@dataclass(frozen=True)
class ContractErrorSpec:
    """Metadata and formatter for a single Solidity custom error."""

    code: str
    signature: str
    arg_types: Tuple[str, ...]
    arg_names: Tuple[str, ...]
    http_status: int
    default_message_vi: str
    formatter_vi: Optional[Callable[[Dict[str, Any]], str]] = None

    @property
    def selector(self) -> str:
        return "0x" + Web3.keccak(text=self.signature)[:4].hex()


@dataclass(frozen=True)
class DecodedContractError:
    """Normalized revert error payload ready for FastAPI JSON responses & React alerts."""

    code: str
    selector: Optional[str]
    http_status: int
    message_vi: str
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "selector": self.selector,
            "http_status": self.http_status,
            "message_vi": self.message_vi,
            "details": self.details,
        }


def _fmt_myusdt(wad_value: int) -> str:
    """Format MyUSDT WAD with 4 decimals normally, preserving full precision for sub-0.0001 WAD dust."""
    if wad_value == 0:
        return "0.0000"
    rounded = wad_to_decimal_str(wad_value, precision=4)
    # Preserve exact precision when value is non-zero dust (< 0.0001) or has sub-0.0001 remainder
    if wad_value % (10**14) != 0:
        exact = format(Decimal(wad_value) / Decimal(WAD), "f").rstrip("0").rstrip(".")
        return exact
    return rounded


def _fmt_hf(hf_wad: int) -> str:
    if hf_wad >= (1 << 255):
        return "∞"
    return wad_to_decimal_str(hf_wad, precision=4)


def _fmt_exceeds_max_ltv(d: Dict[str, Any]) -> str:
    req = _fmt_myusdt(int(d["requestedDebtWad"]))
    cap = _fmt_myusdt(int(d["maxBorrowableWad"]))
    return (
        f"Vượt trần tỷ lệ thế chấp tối đa 70% LTV: tổng nợ yêu cầu {req} MyUSDT "
        f"vượt hạn mức tối đa cho phép {cap} MyUSDT."
    )


def _fmt_insufficient_liquidity(d: Dict[str, Any]) -> str:
    req = _fmt_myusdt(int(d["requestedWad"]))
    avail = _fmt_myusdt(int(d["availableLiquidityWad"]))
    return (
        f"Pool không đủ thanh khoản rỗi: yêu cầu {req} MyUSDT "
        f"nhưng số dư khả dụng thực tế hiện chỉ còn {avail} MyUSDT."
    )


def _fmt_insufficient_claimable(d: Dict[str, Any]) -> str:
    req = _fmt_myusdt(int(d["requestedWad"]))
    claim = _fmt_myusdt(int(d["claimableWad"]))
    return (
        f"Số tiền rút vượt quyền lợi của vị thế NFT: yêu cầu {req} MyUSDT "
        f"nhưng gốc + lãi được hưởng hiện tại là {claim} MyUSDT."
    )


def _fmt_not_position_owner(d: Dict[str, Any]) -> str:
    return (
        f"Ví {d['caller']} không phải chủ sở hữu hiện tại của LendingPositionNFT #{d['positionId']}. "
        "Chỉ chủ sở hữu hiện tại của NFT mới có quyền rút gốc và lãi."
    )


def _fmt_position_not_found(d: Dict[str, Any]) -> str:
    return f"Vị thế cho vay LendingPositionNFT #{d['positionId']} không tồn tại hoặc đã tất toán hoàn toàn."


def _fmt_outstanding_debt(d: Dict[str, Any]) -> str:
    rem = _fmt_myusdt(int(d["remainingDebtWad"]))
    return (
        f"Không thể rút tài sản thế chấp khi vẫn còn dư nợ {rem} MyUSDT. "
        "Vui lòng tất toán toàn bộ gốc và lãi trước khi rút."
    )


def _fmt_health_factor_safe(d: Dict[str, Any]) -> str:
    hf = _fmt_hf(int(d["currentHealthFactorWad"]))
    return f"Khoản vay vẫn an toàn (Health Factor = {hf} >= 1.00), chưa đủ điều kiện thanh lý."


def _fmt_erc20_balance(d: Dict[str, Any]) -> str:
    bal = _fmt_myusdt(int(d["balance"]))
    needed = _fmt_myusdt(int(d["needed"]))
    return f"Số dư token trong ví không đủ: hiện có {bal} MyUSDT nhưng cần {needed} MyUSDT."


def _fmt_erc20_allowance(d: Dict[str, Any]) -> str:
    allow = _fmt_myusdt(int(d["allowance"]))
    needed = _fmt_myusdt(int(d["needed"]))
    return (
        f"Hạn mức ủy quyền (allowance) chưa đủ: đã duyệt {allow} MyUSDT nhưng cần {needed} MyUSDT. "
        "Vui lòng ký giao dịch approve() trước."
    )


# Canonical catalog covering all LendingPool (HI02/HI03/HI04/HI05) & H01/H02 custom errors
CONTRACT_ERROR_CATALOG: Tuple[ContractErrorSpec, ...] = (
    # --- ILendingPool core errors ---
    ContractErrorSpec(
        code="ZeroAmount",
        signature="ZeroAmount()",
        arg_types=(),
        arg_names=(),
        http_status=400,
        default_message_vi="Số tiền giao dịch phải lớn hơn 0.",
    ),
    ContractErrorSpec(
        code="InvalidAddress",
        signature="InvalidAddress()",
        arg_types=(),
        arg_names=(),
        http_status=400,
        default_message_vi="Địa chỉ hợp đồng hoặc ví không hợp lệ (không được là địa chỉ zero).",
    ),
    ContractErrorSpec(
        code="PositionNotFound",
        signature="PositionNotFound(uint256)",
        arg_types=("uint256",),
        arg_names=("positionId",),
        http_status=404,
        default_message_vi="Không tìm thấy vị thế cho vay hoặc vị thế đã tất toán.",
        formatter_vi=_fmt_position_not_found,
    ),
    ContractErrorSpec(
        code="NotPositionOwner",
        signature="NotPositionOwner(uint256,address)",
        arg_types=("uint256", "address"),
        arg_names=("positionId", "caller"),
        http_status=403,
        default_message_vi="Ví hiện tại không sở hữu LendingPositionNFT này.",
        formatter_vi=_fmt_not_position_owner,
    ),
    ContractErrorSpec(
        code="NoActiveCollateral",
        signature="NoActiveCollateral(address)",
        arg_types=("address",),
        arg_names=("borrower",),
        http_status=400,
        default_message_vi="Ví chưa có tài sản thế chấp đang khóa trong Pool.",
    ),
    ContractErrorSpec(
        code="CollateralAlreadyLocked",
        signature="CollateralAlreadyLocked(address)",
        arg_types=("address",),
        arg_names=("borrower",),
        http_status=409,
        default_message_vi="Ví đã có tài sản thế chấp đang hoạt động trong Pool; vui lòng tất toán trước khi thế chấp mới.",
    ),
    ContractErrorSpec(
        code="ExceedsMaxLTV",
        signature="ExceedsMaxLTV(uint256,uint256)",
        arg_types=("uint256", "uint256"),
        arg_names=("requestedDebtWad", "maxBorrowableWad"),
        http_status=400,
        default_message_vi="Số tiền vay vượt trần tỷ lệ thế chấp tối đa 70% LTV.",
        formatter_vi=_fmt_exceeds_max_ltv,
    ),
    ContractErrorSpec(
        code="InsufficientPoolLiquidity",
        signature="InsufficientPoolLiquidity(uint256,uint256)",
        arg_types=("uint256", "uint256"),
        arg_names=("requestedWad", "availableLiquidityWad"),
        http_status=409,
        default_message_vi="Pool không đủ thanh khoản rỗi để thực hiện giao dịch.",
        formatter_vi=_fmt_insufficient_liquidity,
    ),
    ContractErrorSpec(
        code="InsufficientClaimableBalance",
        signature="InsufficientClaimableBalance(uint256,uint256)",
        arg_types=("uint256", "uint256"),
        arg_names=("requestedWad", "claimableWad"),
        http_status=400,
        default_message_vi="Số tiền rút vượt quyền lợi (gốc + lãi) của vị thế NFT.",
        formatter_vi=_fmt_insufficient_claimable,
    ),
    ContractErrorSpec(
        code="OutstandingDebtExists",
        signature="OutstandingDebtExists(uint256)",
        arg_types=("uint256",),
        arg_names=("remainingDebtWad",),
        http_status=409,
        default_message_vi="Còn dư nợ chưa tất toán, chưa thể rút tài sản thế chấp.",
        formatter_vi=_fmt_outstanding_debt,
    ),
    ContractErrorSpec(
        code="HealthFactorSafe",
        signature="HealthFactorSafe(uint256)",
        arg_types=("uint256",),
        arg_names=("currentHealthFactorWad",),
        http_status=400,
        default_message_vi="Health Factor vẫn an toàn (>= 1.00), không đủ điều kiện thanh lý.",
        formatter_vi=_fmt_health_factor_safe,
    ),
    ContractErrorSpec(
        code="EmptyAgreementCid",
        signature="EmptyAgreementCid()",
        arg_types=(),
        arg_names=(),
        http_status=400,
        default_message_vi="Thiếu mã IPFS CID của Hợp đồng vay (Loan Agreement PDF).",
    ),
    ContractErrorSpec(
        code="UnauthorizedNFTTransfer",
        signature="UnauthorizedNFTTransfer(address,address)",
        arg_types=("address", "address"),
        arg_names=("token", "operator"),
        http_status=403,
        default_message_vi="Không được chuyển trực tiếp NFT vào Pool; vui lòng gọi hàm depositCollateral().",
    ),
    # --- OpenZeppelin v5 & H02 PoolControlled / Token errors ---
    ContractErrorSpec(
        code="ERC20InsufficientBalance",
        signature="ERC20InsufficientBalance(address,uint256,uint256)",
        arg_types=("address", "uint256", "uint256"),
        arg_names=("sender", "balance", "needed"),
        http_status=400,
        default_message_vi="Số dư MyUSDT trong ví không đủ để thực hiện giao dịch.",
        formatter_vi=_fmt_erc20_balance,
    ),
    ContractErrorSpec(
        code="ERC20InsufficientAllowance",
        signature="ERC20InsufficientAllowance(address,uint256,uint256)",
        arg_types=("address", "uint256", "uint256"),
        arg_names=("spender", "allowance", "needed"),
        http_status=400,
        default_message_vi="Hạn mức approve() cho LendingPool chưa đủ.",
        formatter_vi=_fmt_erc20_allowance,
    ),
    ContractErrorSpec(
        code="OnlyLendingPool",
        signature="OnlyLendingPool(address,address)",
        arg_types=("address", "address"),
        arg_names=("caller", "lendingPool"),
        http_status=403,
        default_message_vi="Thao tác chỉ được phép gọi nội bộ từ hợp đồng LendingPool.",
    ),
    ContractErrorSpec(
        code="ReceiptNonTransferable",
        signature="ReceiptNonTransferable()",
        arg_types=(),
        arg_names=(),
        http_status=403,
        default_message_vi="Biên nhận thế chấp CollateralReceiptNFT là tài sản gắn ví (soulbound), không thể chuyển nhượng.",
    ),
    ContractErrorSpec(
        code="DebtTokenNonTransferable",
        signature="DebtTokenNonTransferable()",
        arg_types=(),
        arg_names=(),
        http_status=403,
        default_message_vi="DebtToken đại diện nghĩa vụ nợ cá nhân, không thể chuyển nhượng sang ví khác.",
    ),
)

ERRORS_BY_SELECTOR: Dict[str, ContractErrorSpec] = {
    spec.selector: spec for spec in CONTRACT_ERROR_CATALOG
}
ERRORS_BY_CODE: Dict[str, ContractErrorSpec] = {
    spec.code: spec for spec in CONTRACT_ERROR_CATALOG
}


def _pick_best_hex_candidate(candidates: list[str]) -> Optional[str]:
    """Prefer hex payloads whose 4-byte selector matches a known Solidity custom error."""
    if not candidates:
        return None
    for candidate in candidates:
        if len(candidate) >= 10 and candidate[:10].lower() in ERRORS_BY_SELECTOR:
            return candidate
    return candidates[0]


def _extract_hex_payload(raw_input: Any) -> Optional[str]:
    """Extract hex revert data from bytes, hex string, or Web3.py exception objects."""
    if raw_input is None:
        return None
    if isinstance(raw_input, (bytes, bytearray)):
        return "0x" + bytes(raw_input).hex()
    if isinstance(raw_input, Exception):
        candidates: list[str] = []
        data_attr = getattr(raw_input, "data", None)
        if isinstance(data_attr, str) and data_attr.startswith("0x") and len(data_attr) >= 10:
            candidates.append(data_attr)
        for arg in getattr(raw_input, "args", ()):
            if isinstance(arg, str):
                candidates.extend(HEX_DATA_PATTERN.findall(arg))
        candidates.extend(HEX_DATA_PATTERN.findall(str(raw_input)))
        return _pick_best_hex_candidate(candidates)
    text = str(raw_input).strip()
    if text.startswith("0x") and len(text) >= 10 and " " not in text:
        return text
    return _pick_best_hex_candidate(HEX_DATA_PATTERN.findall(text))


def decode_contract_error(revert_source: Any) -> DecodedContractError:
    """Decode a Solidity custom error payload or Web3 exception into Vietnamese UI feedback."""
    raw_text = str(revert_source) if revert_source is not None else ""
    hex_payload = _extract_hex_payload(revert_source)

    if hex_payload and len(hex_payload) >= 10:
        selector = hex_payload[:10].lower()
        spec = ERRORS_BY_SELECTOR.get(selector)
        if spec is not None:
            details: Dict[str, Any] = {}
            arg_bytes = bytes.fromhex(hex_payload[10:])
            if spec.arg_types and len(arg_bytes) >= 32 * len(spec.arg_types):
                decoded_values = abi_decode(list(spec.arg_types), arg_bytes)
                for name, arg_type, val in zip(spec.arg_names, spec.arg_types, decoded_values):
                    if arg_type == "address":
                        details[name] = Web3.to_checksum_address(val)
                    elif arg_type.startswith("uint"):
                        details[name] = str(int(val))
                        if name.endswith("Wad") or name in ("balance", "needed", "allowance"):
                            details[f"{name}_display"] = wad_to_decimal_str(int(val), precision=6)
                    else:
                        details[name] = val
                message_vi = spec.formatter_vi(details) if spec.formatter_vi else spec.default_message_vi
            else:
                message_vi = spec.default_message_vi
            return DecodedContractError(
                code=spec.code,
                selector=spec.selector,
                http_status=spec.http_status,
                message_vi=message_vi,
                details=details,
            )

    # Fallback: match custom error name directly when RPC/Hardhat returns error name text
    for code, spec in ERRORS_BY_CODE.items():
        if code in raw_text:
            return DecodedContractError(
                code=spec.code,
                selector=spec.selector,
                http_status=spec.http_status,
                message_vi=spec.default_message_vi,
                details={"raw": raw_text},
            )

    return DecodedContractError(
        code="ContractRevert",
        selector=hex_payload[:10].lower() if hex_payload and len(hex_payload) >= 10 else None,
        http_status=400,
        message_vi="Giao dịch bị Smart Contract từ chối. Vui lòng kiểm tra lại số dư, hạn mức LTV hoặc quyền sở hữu.",
        details={"raw": raw_text} if raw_text else {},
    )


def format_error_for_api(revert_source: Any) -> Dict[str, Any]:
    """Convenience helper returning a JSON-serializable error dict for FastAPI responses."""
    return decode_contract_error(revert_source).to_dict()


__all__ = [
    "CONTRACT_ERROR_CATALOG",
    "ContractErrorSpec",
    "DecodedContractError",
    "ERRORS_BY_CODE",
    "ERRORS_BY_SELECTOR",
    "WAD",
    "decode_contract_error",
    "format_error_for_api",
]
