"use client";
import { useState, type FormEvent } from "react";
import { Coins, Wallet, BadgePercent, Activity, Plus } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { useWallet } from "@/components/wallet-provider";
import dynamic from "next/dynamic";
import { useLiveData } from "@/hooks/use-live-data";
import { LiveActivity, LiveModeNotice, DemoToolbar, ReadStatus, array, obj, wad, money, integer, percentage, canTransact, LiveHelp } from "@/components/live-common";
import { exactAmount, parseAmount } from "@/lib/wad";
import { address, same, type Operation } from "@/lib/wallet-transactions";
import { walletError } from "@/lib/wallet-client";

const InterestChart = dynamic(() => import("@/components/interest-chart").then((module) => module.InterestChart), { ssr: false, loading: () => <p className="live-empty" role="status">Đang tải biểu đồ dự phóng…</p> });

export default function LiveLendingDashboard() {
  const { state, client } = useWallet();
  const pool = useLiveData("/api/pool");
  const positions = useLiveData(state.account ? "/api/accounts/" + state.account + "/lending-positions" : null);
  const wallet = useLiveData(state.account ? "/api/accounts/" + state.account + "/snapshot" : null);
  const entries = array(positions.data?.positions).filter((p) => p.owner && same(p.owner, state.account));
  const poolInfo = obj(pool.data?.pool), rates = obj(pool.data?.interest_rates);
  const principal = state.account && positions.data ? entries.reduce((n,p) => n + BigInt(wad(p.principal) || "0"), 0n) : null;
  const earned = state.account && positions.data ? entries.reduce((n,p) => n + BigInt(wad(p.earned_interest) || "0"), 0n) : null;
  const [kind, setKind] = useState<"supply" | "withdraw" | "transfer">("supply");
  const [amount, setAmount] = useState("1000");
  const [positionId, setPositionId] = useState("");
  const [recipient, setRecipient] = useState("");
  const [error, setError] = useState("");
  const [help, setHelp] = useState(false);
  const selectedId = positionId || integer(entries[0]?.position_id);
  const selected = entries.find((p) => integer(p.position_id) === selectedId);
  const maxWithdraw = selected ? wad(selected.max_withdrawable) : null;
  const ready = canTransact(state);
  const prepare = async (event: FormEvent) => {
    event.preventDefault(); setError("");
    try {
      let operation: Operation;
      if (kind === "supply") operation = { action: "DEPOSIT_LENDER", args: { amount_wad: parseAmount(amount).toString() } };
      else if (kind === "withdraw") {
        if (!selectedId) throw new Error("Chọn NFT vị thế thuộc ví hiện tại.");
        const value = parseAmount(amount);
        if (maxWithdraw !== null && value > BigInt(maxWithdraw)) throw new Error("Số rút vượt quyền lợi/tiền khả dụng hiện tại. Làm mới và nhập lại.");
        operation = { action: "WITHDRAW_LENDER", args: { position_id: selectedId, amount_wad: value.toString() } };
      } else {
        if (!selectedId) throw new Error("Chọn NFT vị thế.");
        const to = address(recipient); if (same(to,state.account)) throw new Error("Nhập ví nhận khác ví hiện tại.");
        operation = { action: "TRANSFER_LENDING_POSITION_NFT", args: { position_id: selectedId, recipient_address: to } };
      }
      await client.prepare(operation);
    } catch (e) { setError(walletError(e)); }
  };
  return <AppShell section="lending" account="" choices={[]} ready onAccountChange={() => {}} onHelp={() => setHelp(true)}>
    <main id="main-content" className="wrap live-console">
      <section className="page-heading"><div><div className="heading-label"><span />CHO VAY MYUSDT</div><h1>Tổng quan cho vay<span className="heading-dot">.</span></h1><p>Vốn, lãi và NFT vị thế từ mạng đang kết nối.</p></div><button className="button secondary" onClick={() => { setKind("supply"); document.getElementById("lending-operation")?.focus(); }}><Plus size={18} />Gửi tiền</button></section>
      <LiveModeNotice /><ReadStatus {...pool} />
      <section className="kpi-grid" aria-label="Số liệu cho vay từ API">
        <article className="kpi-card kpi-featured"><div className="kpi-top"><span>Supply APY tham khảo</span><BadgePercent size={20} /></div><div className="kpi-value">{percentage(obj(rates.supply_apy_reference).percent)}</div><div className="kpi-foot">APR {percentage(obj(rates.supply_apr).percent)} / năm</div></article>
        <article className="kpi-card"><div className="kpi-top"><span>Tổng vốn gửi Pool</span><Coins size={20} /></div><div className="kpi-value">{money(wad(poolInfo.total_supplied),2)}</div><div className="kpi-foot">MyUSDT · toàn Pool</div></article>
        <article className="kpi-card"><div className="kpi-top"><span>Vốn gốc của bạn</span><Wallet size={20} /></div><div className="kpi-value">{money(principal,2)}</div><div className="kpi-foot">{state.account && positions.data ? entries.length : "—"} NFT vị thế</div></article>
        <article className="kpi-card"><div className="kpi-top"><span>Lãi đã tích lũy</span><Activity size={20} /></div><div className="kpi-value interest-value">{money(earned,8)}</div><div className="kpi-foot">MyUSDT · đọc từ contract</div></article>
      </section>
      <div className="overview-grid">
        <section className="panel live-form-panel" aria-labelledby="lending-form-title"><div className="panel-head"><h2 id="lending-form-title">Giao dịch cho vay</h2><span className="rate-tag">Khả dụng {money(wad(pool.data?.available_liquidity),2)} MyUSDT</span></div>
          <div className="live-tabs" role="group" aria-label="Loại thao tác cho vay">{([["supply","Gửi"],["withdraw","Rút"],["transfer","Chuyển NFT"]] as const).map(([value,label]) => <button key={value} aria-pressed={kind===value} onClick={() => {setKind(value);setError("");}}>{label}</button>)}</div>
          <form id="lending-operation" tabIndex={-1} onSubmit={prepare}>
            {kind !== "supply" && <div className="field"><label htmlFor="live-position">NFT vị thế</label><select id="live-position" required value={selectedId} onChange={(e) => setPositionId(e.target.value)}><option value="">Chọn vị thế</option>{entries.map((p) => <option key={integer(p.position_id)} value={integer(p.position_id)}>NFT #{integer(p.position_id)} · {money(wad(p.claimable_balance),4)} MyUSDT</option>)}</select></div>}
            {kind === "transfer" ? <div className="field"><label htmlFor="live-recipient">Ví nhận quyền vốn gốc và lãi</label><input id="live-recipient" autoComplete="off" required value={recipient} onChange={(e) => setRecipient(e.target.value)} /></div> : <div className="field"><label htmlFor="live-lend-amount">Số MyUSDT {kind === "supply" ? "gửi" : "rút"}</label><input id="live-lend-amount" inputMode="decimal" required value={amount} onChange={(e) => setAmount(e.target.value)} /><p className="field-hint">{kind === "withdraw" ? <>Rút tối đa theo API: {money(maxWithdraw)} MyUSDT. <button type="button" className="text-button" disabled={!maxWithdraw || maxWithdraw==="0"} onClick={() => setAmount(exactAmount(maxWithdraw!))}>Dùng mức tối đa</button></> : <>Số dư MyUSDT: {money(wad(obj(wallet.data?.balances).myusdt))}.</>}</p></div>}
            {error && <p className="form-error" role="alert">{error}</p>}
            {!state.session && <p className="field-hint">Kết nối MetaMask và ký xác thực để chuẩn bị giao dịch.</p>}
            <button className="button primary full" disabled={!ready || (kind!=="supply"&&!selectedId)}>Xem trước giao dịch</button>
            <p className="field-hint">Cấp quyền và thao tác chính là hai giao dịch riêng. Sau khi cấp quyền được xác nhận, chuẩn bị lại thao tác chính để lấy gas mới.</p>
          </form>
        </section>
        <section className="panel liquidity-panel" aria-labelledby="live-liquidity-title"><h2 id="live-liquidity-title">Thanh khoản và lãi suất</h2><p className="metric-label">KHẢ DỤNG ĐỂ RÚT</p><div className="liquidity-value">{money(wad(pool.data?.available_liquidity),2)}<span>MyUSDT</span></div><div className="pool-detail"><span>Đang được vay</span><strong>{money(wad(poolInfo.total_borrowed),2)} MyUSDT</strong></div><div className="pool-detail"><span>Utilization</span><strong>{percentage(obj(rates.utilization).percent)}</strong></div><div className="pool-detail"><span>Borrow APR</span><strong>{percentage(obj(rates.borrow_apr).percent)}</strong></div><p className="liquidity-note">APR tính lãi đơn theo giây; APY chỉ là quy đổi ghép lãi hằng ngày để tham khảo.</p></section>
      </div>
      {principal !== null && typeof obj(rates.supply_apr).bps === "number" && <InterestChart principal={principal.toString()} aprBps={Number(obj(rates.supply_apr).bps)} />}
      <section className="panel positions-panel" id="positions" aria-labelledby="live-positions-title"><div className="panel-head positions-head"><div><h2 id="live-positions-title">NFT vị thế của bạn</h2><p>Quyền hưởng vốn và lãi theo chủ sở hữu hiện tại.</p></div></div><ReadStatus {...positions} />
        {entries.length ? <div className="table-scroll"><table><thead><tr><th>NFT</th><th>Vốn gốc</th><th>Lãi</th><th>Rút tối đa</th><th>Thao tác</th></tr></thead><tbody>{entries.map((p) => <tr key={integer(p.position_id)}><td data-label="NFT">#{integer(p.position_id)}</td><td data-label="Vốn gốc">{money(wad(p.principal))}</td><td data-label="Lãi">{money(wad(p.earned_interest),8)}</td><td data-label="Rút tối đa">{money(wad(p.max_withdrawable))}</td><td className="row-actions"><button className="row-button" onClick={() => {setPositionId(integer(p.position_id));setKind("withdraw");}}>Rút</button><button className="row-button" onClick={() => {setPositionId(integer(p.position_id));setKind("transfer");}}>Chuyển</button></td></tr>)}</tbody></table></div> : <p className="live-empty">{state.account ? "Chưa có vị thế cho vay trong lần đọc hiện tại." : "Kết nối ví để xem các NFT thuộc sở hữu của bạn."}</p>}
      </section>
      <DemoToolbar /><LiveActivity /><footer className="app-footer"><span>IS355 · Cho vay MyUSDT</span><span>{state.network} · Ký tại ví người dùng</span></footer>
    </main>
    <LiveHelp open={help} onClose={() => setHelp(false)}/>
  </AppShell>;
}
