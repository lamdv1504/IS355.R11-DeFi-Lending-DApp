/** Zero-dependency fixed-point WAD / decimal helpers shared across L02, L03, and L04. */
export const WAD = 10n ** 18n;

export function formatUnitsDecimal(raw: string | bigint, decimals = 18): string {
  const value = typeof raw === "bigint" ? raw : BigInt(raw);
  const negative = value < 0n;
  const abs = negative ? -value : value;
  const base = 10n ** BigInt(decimals);
  const whole = abs / base;
  const frac = (abs % base).toString().padStart(decimals, "0").replace(/0+$/, "");
  return (negative ? "-" : "") + whole.toString() + "." + (frac || "0");
}

export function parseUnitsDecimal(value: string, decimals = 18): bigint {
  const [wholePart, fracPart = ""] = value.split(".");
  const padded = fracPart.padEnd(decimals, "0").slice(0, decimals);
  return BigInt(wholePart) * 10n ** BigInt(decimals) + BigInt(padded || "0");
}

export function parseAmount(value: string): bigint {
  const normalized = value.trim().replace(",", ".");
  if (!/^\d+(\.\d{1,18})?$/.test(normalized)) {
    throw new Error("Nhập số dương, tối đa 18 chữ số thập phân. Không dùng dấu phân cách hàng nghìn.");
  }
  const amount = parseUnitsDecimal(normalized, 18);
  if (amount <= 0n) throw new Error("Số tiền phải lớn hơn 0.");
  return amount;
}

export function amountLabel(raw: string | bigint, decimals = 4): string {
  return new Intl.NumberFormat("vi-VN", { maximumFractionDigits: decimals }).format(
    Number(formatUnitsDecimal(raw, 18))
  );
}

export function exactAmount(raw: string | bigint): string {
  return formatUnitsDecimal(raw, 18);
}

export function shortAddress(address: string): string {
  return address.slice(0, 6) + "…" + address.slice(-4);
}

export function sameAddress(a: string, b: string): boolean {
  return a.toLowerCase() === b.toLowerCase();
}

export function rates(supplied: string, borrowed: string) {
  const supply = BigInt(supplied);
  const demand = BigInt(borrowed);
  const raw = supply === 0n ? 0n : demand * 10000n / supply;
  const utilizationBps = Number(raw > 10000n ? 10000n : raw);
  const borrowAprBps = 500 + Math.floor(utilizationBps * 1000 / 10000);
  const supplyAprBps = Math.floor(borrowAprBps * utilizationBps / 10000);
  const supplyApy = (Math.pow(1 + supplyAprBps / 10000 / 365, 365) - 1) * 100;
  return { utilizationBps, borrowAprBps, supplyAprBps, supplyApy };
}
