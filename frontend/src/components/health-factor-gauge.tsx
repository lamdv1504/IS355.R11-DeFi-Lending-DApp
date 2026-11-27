import { useId } from "react";
import { formatHealthFactor, riskStatus } from "@/lib/borrowing-demo";
import { WAD } from "@/lib/lending-demo";

const statusNames = { safe: "An toàn", warning: "Cần theo dõi", danger: "Đủ điều kiện thanh lý" };
function arc(from: number, to: number) {
  const point = (value: number) => {
    const angle = Math.PI - value / 3 * Math.PI;
    return [140 + 112 * Math.cos(angle), 132 - 112 * Math.sin(angle)];
  };
  const [x1, y1] = point(from), [x2, y2] = point(to);
  return "M " + x1 + " " + y1 + " A 112 112 0 0 1 " + x2 + " " + y2;
}
export function HealthFactorGauge({ value }: { value: bigint | null }) {
  const id = useId();
  const status = riskStatus(value);
  const visible = value === null ? 3 : Math.min(3, Number(value * 10000n / WAD) / 10000);
  const angle = Math.PI - visible / 3 * Math.PI;
  return <div className={"hf-gauge hf-" + status}>
    <svg viewBox="0 0 280 164" role="img" aria-labelledby={id + "-title " + id + "-desc"}>
      <title id={id + "-title"}>Health Factor {formatHealthFactor(value)} — {statusNames[status]}</title>
      <desc id={id + "-desc"}>Đỏ khi nhỏ hơn 1; vàng từ 1 đến dưới 1,5; xanh từ 1,5. Không có dư nợ được hiển thị là vô hạn.</desc>
      <path d={arc(0, 1)} className="gauge-danger" /><path d={arc(1.03, 1.5)} className="gauge-warning" /><path d={arc(1.53, 3)} className="gauge-safe" />
      <line x1="140" y1="132" x2={140 + 86 * Math.cos(angle)} y2={132 - 86 * Math.sin(angle)} className="gauge-needle" />
      <circle cx="140" cy="132" r="7" fill="currentColor" />
      <text x="20" y="160">0</text><text x="74" y="26">1</text><text x="138" y="12">1,5</text><text x="248" y="160">3+</text>
    </svg>
    <div className="hf-reading"><strong>{formatHealthFactor(value)}</strong><span>{value === null ? "Không có dư nợ" : statusNames[status]}</span></div>
  </div>;
}
