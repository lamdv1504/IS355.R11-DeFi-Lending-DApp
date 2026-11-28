"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ArrowUpRight, RefreshCw, ShieldCheck, X } from "lucide-react";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { AppShell } from "@/components/app-shell";
import { DEFAULT_CONNECTION, HubConnectionPanel } from "@/components/hub-connection";
import { auditEntries, errorMessage, fetchRateAnalytics, fetchWalletSnapshot, listDocuments, ratesChartData, retrieveDocument, walletChartData, type AuditEntry, type DocumentMetadata, type HubConnection } from "@/lib/ipfs-hub";
import { BORROW_STORAGE_KEY, BORROW_WALLETS, borrowCheckpoint, collateralValue, createBorrowDemo, restoreBorrowDemo, type BorrowActor } from "@/lib/borrowing-demo";
import { amountLabel } from "@/lib/wad";
import samples from "@/data/l04-samples.json";

const SAMPLE_ROWS = auditEntries(samples.audit);
const SAMPLE_AUDIT = samples.documents.find((d) => d.document_type === "AUDIT_LOGS")!;
const LIVE_RATES_OPTION = "__api_rates__";
const COLORS = ["#245bd6", "#8baddf", "#bd541d", "#52627b"];
const tooltipStyle = { borderRadius: 8, border: "1px solid var(--line)", color: "var(--ink)", background: "white", boxShadow: "none", fontSize: 14 };
type WalletRows = ReturnType<typeof walletChartData>;
function demoWallet(actor: BorrowActor, now = 0, stored = true): WalletRows {
  let state = createBorrowDemo(now);
  if (stored && typeof window !== "undefined") {
    try { const saved = localStorage.getItem(BORROW_STORAGE_KEY); state = saved ? borrowCheckpoint(restoreBorrowDemo(saved), now) : createBorrowDemo(now); }
    catch { state = createBorrowDemo(now); }
  }
  return walletChartData({ myusdt: state.wallets[actor].balanceWad,
    collateral: actor === "borrower" ? collateralValue(state).toString() : "0",
    debt: actor === "borrower" ? state.loan.principalWad : "0",
    interest: actor === "borrower" ? state.loan.interestWad : "0" });
}
export default function AnalyticsDashboard() {
  const [connection, setConnection] = useState<HubConnection>(DEFAULT_CONNECTION);
  const [actor, setActor] = useState<BorrowActor>("borrower");
  const [rows, setRows] = useState<AuditEntry[]>(SAMPLE_ROWS);
  const [months, setMonths] = useState(6);
  const [walletRows, setWalletRows] = useState<WalletRows>(() => demoWallet("borrower", 0, false));
  const [walletAddress, setWalletAddress] = useState<string>(BORROW_WALLETS[0].address);
  const [loadedWallet, setLoadedWallet] = useState("");
  const [walletBlock, setWalletBlock] = useState<number | null>(null);
  const [auditDocuments, setAuditDocuments] = useState<DocumentMetadata[]>([]);
  const [auditCid, setAuditCid] = useState(SAMPLE_AUDIT.cid);
  const [ratesMeta, setRatesMeta] = useState<{ network: string; blockNumber: number } | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [help, setHelp] = useState(false);
  const request = useRef<AbortController | null>(null);
  const helpRef = useRef<HTMLDialogElement>(null);
  useEffect(() => { if (help) helpRef.current?.showModal(); else helpRef.current?.close(); }, [help]);
  useEffect(() => {
    if (connection.mode !== "sample") return;
    const update = () => setWalletRows(demoWallet(actor, Date.now()));
    const initial = setTimeout(update, 0);
    const ticker = setInterval(update, 3000);
    return () => { clearTimeout(initial); clearInterval(ticker); };
  }, [connection.mode, actor]);
  useEffect(() => () => request.current?.abort(), []);
  const loadRatesSource = async (next: HubConnection, target?: DocumentMetadata | "live") => {
    request.current?.abort();
    const controller = new AbortController(); request.current = controller;
    setBusy(true); setError(""); setRows([]); setRatesMeta(null);
    try {
      const items = target && target !== "live"
        ? auditDocuments
        : await listDocuments(next, controller.signal)
            .then((docs) => docs.filter((d) => d.document_type === "AUDIT_LOGS" && d.content_type === "application/json"))
            .catch(() => [] as DocumentMetadata[]);
      if (controller.signal.aborted) return;
      setAuditDocuments(items);
      if (target && target !== "live") {
        setAuditCid(target.cid);
        const result = await retrieveDocument(next, target.cid, target, controller.signal);
        const entries = auditEntries(result.json);
        if (!controller.signal.aborted) setRows(entries);
        return;
      }
      setAuditCid(LIVE_RATES_OPTION);
      const snapshot = await fetchRateAnalytics(next, 12, controller.signal);
      if (!controller.signal.aborted) {
        setRows(snapshot.series);
        setRatesMeta({ network: snapshot.network, blockNumber: snapshot.blockNumber });
      }
    } catch (e) { if (!controller.signal.aborted) setError(errorMessage(e)); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  };
  const changeConnection = (next: HubConnection) => {
    request.current?.abort(); setBusy(false); setError(""); setWalletRows([]); setLoadedWallet(""); setWalletBlock(null); setAuditDocuments([]); setRatesMeta(null); setConnection(next);
    if (next.mode === "sample") { setRows(SAMPLE_ROWS); setAuditCid(SAMPLE_AUDIT.cid); }
    else void loadRatesSource(next, "live");
  };
  const loadWallet = async () => {
    request.current?.abort();
    const controller = new AbortController(); request.current = controller;
    setBusy(true); setError(""); setWalletRows([]); setLoadedWallet(""); setWalletBlock(null);
    try {
      const snapshot = await fetchWalletSnapshot(connection, walletAddress, controller.signal);
      if (!controller.signal.aborted) {
        setWalletRows(snapshot.rows);
        setLoadedWallet(snapshot.walletAddress);
        setWalletBlock(snapshot.blockNumber);
      }
    } catch (e) { if (!controller.signal.aborted) setError(errorMessage(e)); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  };
  const displayed = rows.slice(-months);
  const chartRows = ratesChartData(displayed);
  return <AppShell section="analytics" account={actor} choices={connection.mode === "sample" ? BORROW_WALLETS.map((w) => ({ value: w.id, name: w.name, address: w.address })) : []} ready onAccountChange={(id) => setActor(id as BorrowActor)} onHelp={() => setHelp(true)} statusLabel={connection.mode === "sample" ? "Phân tích · SIMULATED" : "Số liệu từ backend"}>
    <main id="main-content" className="hub-main">
      <div className="page-heading hub-heading" data-enter><div><div className="heading-label"><span />LÃI SUẤT & SỐ DƯ</div><h1>Phân tích tài sản<span className="heading-dot">.</span></h1><p>Theo dõi APY gửi/vay và bốn thành phần số dư ví.</p></div><Link className="button secondary" href="/documents/" prefetch={false}>Tra cứu hồ sơ IPFS<ArrowUpRight size={18} /></Link></div>
      <HubConnectionPanel value={connection} onChange={changeConnection} />
      {error && <div className="hub-alert error" role="alert"><ShieldCheck size={20} /><p>{error}</p><button className="icon-button" aria-label="Đóng thông báo lỗi" onClick={() => setError("")}><X size={18} /></button></div>}
      <div className="analytics-grid">
        <section className="panel analytics-panel" aria-labelledby="rates-title"><div className="hub-section-heading"><div><p className="eyebrow">NHẬT KÝ THEO THÁNG</p><h2 id="rates-title">Biến động APY gửi & vay</h2></div><div className="hub-filters" role="group" aria-label="Số tháng hiển thị">{[3, 6, 12].map((n) => <button key={n} aria-pressed={months === n} onClick={() => setMonths(n)}>{n} tháng</button>)}</div></div>
          {connection.mode === "api" && <div className="analytics-wallet"><div className="field"><label htmlFor="audit-cid-select">Nguồn chuỗi lãi suất theo tháng</label><select id="audit-cid-select" value={auditCid} disabled={busy} onChange={(e) => { if (e.target.value === LIVE_RATES_OPTION) { void loadRatesSource(connection, "live"); return; } const item = auditDocuments.find((d) => d.cid === e.target.value); if (item) void loadRatesSource(connection, item); }}><option value={LIVE_RATES_OPTION}>API /api/analytics/rates (trực tiếp)</option>{auditDocuments.map((d) => <option key={d.cid} value={d.cid}>IPFS CID · {d.cid.slice(0, 18)}…{d.cid.slice(-6)}</option>)}</select></div><button className="button secondary" disabled={busy} onClick={() => { const current = auditDocuments.find((d) => d.cid === auditCid); void loadRatesSource(connection, current || "live"); }}><RefreshCw size={17} />Làm mới số liệu</button></div>}
          {chartRows.length ? <div className="analytics-chart" role="img" aria-label={"Biểu đồ cột APY gửi và vay của " + chartRows.length + " tháng. Cột nhạt là dữ liệu mô phỏng; cột đậm là dữ liệu on-chain. Bảng số liệu chi tiết ở bên dưới."}>
            <ResponsiveContainer width="100%" height="100%" initialDimension={{ width: 800, height: 320 }}><BarChart data={chartRows} margin={{ left: -18, right: 20, top: 18, bottom: 0 }} accessibilityLayer>
              <CartesianGrid vertical={false} stroke="var(--line)" strokeDasharray="3 5" /><XAxis dataKey="period" tick={{ fill: "var(--muted)", fontSize: 12 }} tickLine={false} axisLine={false} minTickGap={24} /><YAxis tickFormatter={(v) => v + "%"} tick={{ fill: "var(--muted)", fontSize: 12 }} tickLine={false} axisLine={false} width={62} /><Tooltip contentStyle={tooltipStyle} formatter={(v, name) => [Number(v).toLocaleString("vi-VN", { maximumFractionDigits: 4 }) + "%", name]} labelFormatter={(label) => { const row = displayed.find((r) => r.period === label); return String(label) + " · " + row?.data_kind; }} />
              <Bar dataKey="sampleSupply" stackId="supply" name="APY gửi · SIMULATED" fill="#bfd2fb" stroke="#245bd6" strokeDasharray="3 2" maxBarSize={32} isAnimationActive={false} /><Bar dataKey="sampleBorrow" stackId="borrow" name="APY vay · SIMULATED" fill="#f3c9ad" stroke="#a84616" strokeDasharray="3 2" maxBarSize={32} isAnimationActive={false} />
              <Bar dataKey="chainSupply" stackId="supply" name="APY gửi · ON_CHAIN" fill="#245bd6" maxBarSize={32} isAnimationActive={false} /><Bar dataKey="chainBorrow" stackId="borrow" name="APY vay · ON_CHAIN" fill="#a84616" maxBarSize={32} isAnimationActive={false} />
            </BarChart></ResponsiveContainer></div> : <p className="hub-empty">{busy ? "Đang tải nhật ký…" : "Chưa có dữ liệu nhật ký để vẽ biểu đồ."}</p>}
          <div className="analytics-legend"><span><i />APY gửi</span><span><i className="borrow" />APY vay</span><span><i className="sample" />SIMULATED</span><span>Cột đậm: ON_CHAIN</span></div>
          <p className="hub-note">{auditCid === LIVE_RATES_OPTION ? <>Nguồn: <code>GET /api/analytics/rates</code>{ratesMeta ? ` (${ratesMeta.network} · block #${ratesMeta.blockNumber})` : ""}.</> : <>Nguồn CID: <code>{auditCid || "Chưa chọn"}</code>.</>} Mỗi kỳ giữ nhãn nguồn riêng; dữ liệu mẫu không được trình bày như số liệu on-chain.</p>
          <details className="hub-data-details"><summary>Xem bảng số liệu APY</summary><div className="hub-table-scroll" tabIndex={0} role="region" aria-label="Bảng số liệu hồ sơ"><table><caption className="sr-only">APY gửi và vay theo tháng cùng nguồn dữ liệu</caption><thead><tr><th>Kỳ</th><th>APY gửi</th><th>APY vay</th><th>Nguồn</th></tr></thead><tbody>{displayed.map((r) => <tr key={r.period}><td data-label="Kỳ">{r.period}</td><td data-label="APY gửi">{r.supply_apy_percent.toLocaleString("vi-VN")}%</td><td data-label="APY vay">{r.borrow_apy_percent.toLocaleString("vi-VN")}%</td><td data-label="Nguồn">{r.data_kind}</td></tr>)}</tbody></table></div></details>
        </section>
        <section className="panel analytics-panel" aria-labelledby="wallet-title"><div className="hub-section-heading"><div><p className="eyebrow">ĐƠN VỊ ĐỊNH GIÁ: MYUSDT</p><h2 id="wallet-title">Thành phần số dư ví</h2></div><span className="hub-provenance">{connection.mode === "sample" ? "SIMULATED" : "BACKEND READ"}</span></div>
          {connection.mode === "api" ? <form className="analytics-wallet" onSubmit={(e) => { e.preventDefault(); void loadWallet(); }}><div className="field"><label htmlFor="analytics-wallet">Địa chỉ ví</label><input id="analytics-wallet" required value={walletAddress} onChange={(e) => { request.current?.abort(); setBusy(false); setWalletAddress(e.target.value); setWalletRows([]); setLoadedWallet(""); setWalletBlock(null); }} /></div><button className="button secondary" disabled={busy}>Đọc số dư ví</button></form> : <p className="hub-note">Đọc phiên Borrowing Console L03 trong trình duyệt. Đổi ví demo ở thanh trên để so sánh; cập nhật mỗi 3 giây.</p>}
          {walletRows.length ? <><div className="analytics-chart" role="img" aria-label="Bốn thanh so sánh MyUSDT khả dụng, giá trị thế chấp, nợ gốc DebtToken và lãi vay tích lũy. Nợ là nghĩa vụ phải trả, không cộng vào tổng tài sản.">
            <ResponsiveContainer width="100%" height="100%" initialDimension={{ width: 800, height: 320 }}><BarChart data={walletRows} layout="vertical" margin={{ left: 0, right: 20, top: 8, bottom: 8 }} accessibilityLayer>
              <CartesianGrid horizontal={false} stroke="var(--line)" strokeDasharray="3 5" /><XAxis type="number" tickCount={3} tick={{ fill: "var(--muted)", fontSize: 12 }} tickFormatter={(v) => Number(v).toLocaleString("vi-VN", { notation: "compact" })} tickLine={false} axisLine={false} /><YAxis type="category" dataKey="key" width={86} tickFormatter={(v) => ({ myusdt: "MyUSDT", collateral: "Thế chấp", debt: "Nợ gốc", interest: "Lãi vay" } as Record<string, string>)[v as string] || v} tick={{ fill: "var(--muted)", fontSize: 12 }} tickLine={false} axisLine={false} /><Tooltip contentStyle={tooltipStyle} labelFormatter={(_v, payload) => payload?.[0]?.payload?.name || ""} formatter={(_v, _name, context) => [amountLabel(context.payload.wad, 6) + " MyUSDT", "Giá trị"]} /><Bar dataKey="amount" name="MyUSDT" maxBarSize={38} isAnimationActive={false}>{walletRows.map((r, i) => <Cell key={r.key} fill={COLORS[i]} />)}</Bar>
            </BarChart></ResponsiveContainer></div><dl className="analytics-values">{walletRows.map((r) => <div key={r.key}><dt>{r.name}</dt><dd title={amountLabel(r.wad, 18)}>{amountLabel(r.wad, 4)}</dd></div>)}</dl></> : <p className="hub-empty">{busy ? "Đang đọc số dư…" : "Nhập địa chỉ ví rồi đọc số dư từ backend."}</p>}
          <p className="hub-note">{loadedWallet && <>Ví: <code>{loadedWallet}</code>{walletBlock !== null ? ` (block #${walletBlock})` : ""}. </>}Nợ gốc và lãi vay là nghĩa vụ phải trả, không cộng vào tổng tài sản. NFT thế chấp hiển thị theo định giá MyUSDT, không phải số lượng NFT.</p>
        </section>
      </div>
      <section className="panel analytics-method" aria-labelledby="method-title"><h2 id="method-title">APR, APY và nguồn dữ liệu</h2><p className="hub-note">APR dùng tính lãi đơn theo giây trên hợp đồng. APY trong nhật ký là mức quy đổi ghép lãi hằng ngày để tham khảo. Biểu đồ dùng số thực để vẽ; số dư gốc vẫn lưu và hiển thị từ WAD nguyên.</p></section>
      <footer className="app-footer"><span>IS355 · Phân tích DeFi Lending</span><Link className="text-button" href="/borrow/" prefetch={false}>Mở Borrowing Console<ArrowUpRight size={17} /></Link></footer>
    </main>
    <dialog ref={helpRef} className="action-dialog" onCancel={() => setHelp(false)} onClose={() => setHelp(false)}><div className="dialog-top"><ShieldCheck size={25} /><button className="icon-button" aria-label="Đóng hướng dẫn" onClick={() => setHelp(false)}><X size={20} /></button></div><h2>Đọc biểu đồ tài sản</h2><div className="help-copy"><p>Cột nhạt có viền đứt thể hiện SIMULATED, cột đậm thể hiện ON_CHAIN. Khi đổi nguồn sang backend, biểu đồ đọc trực tiếp chuỗi tháng từ <code>GET /api/analytics/rates</code> (hoặc CID Audit Logs đã phát hành) và không dùng lại số liệu mẫu nếu truy vấn lỗi.</p><p>Biểu đồ ví dùng bốn thanh độc lập vì tài sản và nợ không phải các phần của cùng một tổng, đồng thời đọc đồng bộ qua <code>GET /api/accounts/&#123;address&#125;/snapshot</code> kèm số block.</p><button className="button primary full" onClick={() => setHelp(false)}>Đã hiểu biểu đồ</button></div></dialog>
  </AppShell>;
}
