"use client";

import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useState } from "react";
import { amountLabel } from "@/lib/wad";

export function InterestChart({ principal, aprBps }: { principal: string; aprBps: number }) {
  const [days, setDays] = useState(30);
  const amount = Number(principal) / 1e18;
  const points = Array.from({ length: 7 }, (_, i) => {
    const day = Math.round(i * days / 6);
    return { day, interest: amount * aprBps / 10000 * day / 365 };
  });
  const projected = points.at(-1)!.interest;
  return <section className="panel interest-panel" aria-labelledby="chart-title">
    <div className="panel-head"><div><p className="eyebrow">ƯỚC TÍNH TỪ VỐN GỐC HIỆN TẠI</p><h2 id="chart-title">Dự phóng tiền lãi</h2></div><div className="period-switch" role="group" aria-label="Khoảng thời gian dự phóng">{[7, 30].map((d) => <button key={d} aria-pressed={days === d} onClick={() => setDays(d)}>{d} ngày</button>)}</div></div>
    <div className="forecast-value"><strong>{new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 4 }).format(projected)}</strong><span>MyUSDT / {days} ngày</span><span className="rate-tag">APR {new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 2 }).format(aprBps / 100)}%</span></div>
    <div className="chart" role="img" aria-label={"Vốn gốc " + amountLabel(principal) + " MyUSDT, dự phóng lãi " + projected.toFixed(4) + " MyUSDT sau " + days + " ngày, giả định APR không đổi."}>
      <ResponsiveContainer width="100%" height="100%" initialDimension={{ width: 600, height: 220 }}>
        <AreaChart data={points} margin={{ left: -10, right: 16, top: 16, bottom: 0 }} accessibilityLayer={false}>
          <CartesianGrid stroke="var(--line)" vertical={false} strokeDasharray="3 5" />
          <XAxis dataKey="day" tickLine={false} axisLine={false} tick={{ fill: "var(--muted)", fontSize: 14 }} tickFormatter={(v) => "Ngày " + v} minTickGap={22} />
          <YAxis tickLine={false} axisLine={false} width={48} tick={{ fill: "var(--muted)", fontSize: 14 }} tickFormatter={(v: number) => v.toFixed(1)} />
          <Tooltip formatter={(v) => [Number(v).toLocaleString("vi-VN", { maximumFractionDigits: 6 }) + " MyUSDT", "Tiền lãi"]} labelFormatter={(v) => "Ngày " + v} contentStyle={{ borderRadius: 12, border: "1px solid var(--line)", color: "var(--ink)", background: "var(--surface)", boxShadow: "none", fontSize: 14 }} />
          <Area type="monotone" dataKey="interest" stroke="var(--accent)" strokeWidth={2.5} fill="var(--soft)" isAnimationActive={false} activeDot={{ r: 5, fill: "var(--accent)", stroke: "white", strokeWidth: 2 }} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
    <p className="chart-note">Giả định APR giữ nguyên, chưa tái đầu tư. Đây là ước tính, không phải lịch sử hay cam kết lợi nhuận.</p>
  </section>;
}
