"use client";

import { useState } from "react";
import { Activity as ActivityIcon, ArrowDownLeft, ArrowRightLeft, ArrowUpFromLine, BadgePercent, CircleHelp, Coins, FileKey2, Plus, RotateCcw, Search, ShieldCheck, Wallet, X } from "lucide-react";
import { ActionDialog, type DialogKind } from "@/components/action-dialog";
import { AppShell } from "@/components/app-shell";
import { InterestChart } from "@/components/interest-chart";
import { useLendingDemo } from "@/hooks/use-lending-demo";
import { ACCOUNTS, amountLabel, checkpoint, createDemo, ownedPositions, rates, shortAddress, withdrawLimit, type DemoAction } from "@/lib/lending-demo";

const percent = (value: number, digits = 2) => new Intl.NumberFormat("vi-VN", { maximumFractionDigits: digits }).format(value);
const names = { supply: "Gửi MyUSDT", withdraw: "Rút MyUSDT", transfer: "Chuyển NFT", faucet: "Nhận MyUSDT thử nghiệm" };

export default function LendingDashboard() {
  const { state, now, notice, setNotice, transact, reset } = useLendingDemo();
  const [actor, setActor] = useState<string>(ACCOUNTS[0].address);
  const [dialog, setDialog] = useState<{ kind: DialogKind; positionId?: string } | null>(null);
  const [query, setQuery] = useState("");
  const snapshot = state ? checkpoint(state, now) : createDemo(0);
  const poolRates = rates(snapshot.totalSuppliedWad, snapshot.totalBorrowedWad);
  const mine = ownedPositions(snapshot, actor);
  const principal = mine.reduce((sum, p) => sum + BigInt(p.principalWad), 0n);
  const interest = mine.reduce((sum, p) => sum + BigInt(p.interestWad), 0n);
  const filtered = mine.filter((p) => p.id.includes(query.trim().replace(/^#/, "")));
  const ready = !!state;
  const value = (raw: string | bigint, decimals = 4) => ready ? amountLabel(raw, decimals) : "—";
  function open(kind: DialogKind, positionId?: string) { setDialog({ kind, positionId }); }
  function submit(action: DemoAction) {
    transact(action);
    setNotice(names[action.kind] + " thành công trong mô phỏng. Không có giao dịch blockchain.");
  }
  return <><AppShell section="lending" account={actor} choices={ACCOUNTS.map((a) => ({ value: a.address, name: a.name.slice(-1), address: a.address }))} ready={ready} onAccountChange={(value) => { setActor(value); setQuery(""); setNotice(""); }} onHelp={() => open("help")}>
      <main id="main-content" className="wrap">
        <section id="overview" className="page-heading" aria-labelledby="page-title"><div><div className="heading-label"><span />CHO VAY MYUSDT</div><h1 id="page-title">Tổng quan cho vay<span className="heading-dot">.</span></h1><p>Theo dõi tiền gửi, tiền lãi và các vị thế của bạn.</p></div><div className="heading-actions"><button className="button secondary" disabled={!ready || mine.length === 0} onClick={() => open("withdraw")}><ArrowUpFromLine size={18} />Rút tiền</button><button className="button primary" disabled={!ready} onClick={() => open("supply")}><Plus size={19} />Gửi tiền</button></div></section>
        <div className="demo-notice"><span className="demo-label">MÔ PHỎNG</span><p>Dữ liệu thử nghiệm trong trình duyệt. Chưa kết nối ví thật hoặc gửi giao dịch blockchain.</p><button aria-label="Tìm hiểu chế độ mô phỏng" className="icon-button" disabled={!ready} onClick={() => open("help")}><CircleHelp size={18} /></button></div>
        {notice && <div className="status-message" role="status"><ShieldCheck size={19} /><p>{notice}</p><button className="icon-button" aria-label="Đóng thông báo" onClick={() => setNotice("")}><X size={18} /></button></div>}
        <section className="kpi-grid" aria-label="Số liệu cho vay">
          <article className="kpi-card kpi-featured"><div className="kpi-top"><span>Supply APY</span><BadgePercent size={20} /></div><div className="kpi-value">{ready ? percent(poolRates.supplyApy) : "—"}<span>%</span></div><div className="kpi-foot"><span className="small-dot" />APR {ready ? percent(poolRates.supplyAprBps / 100) : "—"}% / năm</div></article>
          <article className="kpi-card"><div className="kpi-top"><span>Tổng vốn gửi trong Pool</span><Coins size={20} /></div><div className="kpi-value">{value(snapshot.totalSuppliedWad, 2)}</div><div className="kpi-foot">MyUSDT <span className="kpi-caption">· toàn bộ người gửi</span></div></article>
          <article className="kpi-card"><div className="kpi-top"><span>Vốn gốc của bạn</span><Wallet size={20} /></div><div className="kpi-value">{value(principal, 2)}</div><div className="kpi-foot">MyUSDT <span className="kpi-caption">· {ready ? mine.length : "—"} NFT vị thế</span></div></article>
          <article className="kpi-card"><div className="kpi-top"><span>Lãi đã tích lũy</span><ActivityIcon size={20} /></div><div className="kpi-value interest-value">{value(interest, 8)}</div><div className="kpi-foot"><span className="small-dot" />MyUSDT · cập nhật mỗi giây</div></article>
        </section>
        <div className="overview-grid">{ready ? <InterestChart principal={principal.toString()} aprBps={poolRates.supplyAprBps} /> : <section className="panel chart-placeholder" aria-busy="true"><h2>Dự phóng tiền lãi</h2><p>Đang tải dữ liệu mô phỏng…</p></section>}
          <section className="panel liquidity-panel" aria-labelledby="liquidity-title"><div className="panel-head"><h2 id="liquidity-title">Thanh khoản Pool</h2><span className="icon-tile"><ArrowRightLeft size={19} /></span></div><p className="metric-label">KHẢ DỤNG ĐỂ RÚT</p><div className="liquidity-value">{value(snapshot.availableLiquidityWad, 2)}<span>MyUSDT</span></div><div className="utilization-label"><span>Tỷ lệ sử dụng</span><strong>{ready ? percent(poolRates.utilizationBps / 100) : "—"}%</strong></div><div className="utilization-track" role="meter" aria-label="Tỷ lệ sử dụng Pool" aria-valuemin={0} aria-valuemax={100} aria-valuenow={poolRates.utilizationBps / 100}><span style={{ width: poolRates.utilizationBps / 100 + "%" }} /></div><div className="pool-detail"><span><i className="legend-borrowed" />Đang được vay</span><strong>{value(snapshot.totalBorrowedWad, 2)} <small>MyUSDT</small></strong></div><div className="pool-detail"><span><i className="legend-available" />Còn khả dụng</span><strong>{value(snapshot.availableLiquidityWad, 2)} <small>MyUSDT</small></strong></div><p className="liquidity-note"><ShieldCheck size={17} />Rút tối đa theo quyền lợi NFT và thanh khoản thực có của Pool.</p></section>
        </div>
        <section className="panel positions-panel" id="positions" aria-labelledby="positions-title"><div className="panel-head positions-head"><div><h2 id="positions-title">NFT vị thế của bạn <span className="count-badge">{ready ? mine.length : "—"}</span></h2><p>Mỗi NFT là quyền sở hữu vốn gốc và tiền lãi.</p></div><div className="search-field"><label htmlFor="position-search">Tìm NFT theo mã</label><div className="search-input"><Search size={18} /><input id="position-search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Tìm mã NFT…" type="search" disabled={!ready} /></div></div></div>
          {!ready ? <p className="empty-state" aria-busy="true">Đang tải vị thế…</p> : filtered.length === 0 ? <div className="empty-state"><FileKey2 size={30} /><h3>{mine.length ? "Không tìm thấy NFT" : "Ví này chưa có vị thế cho vay"}</h3><p>{mine.length ? "Thử tìm bằng mã NFT khác." : "Gửi MyUSDT để nhận NFT vị thế, hoặc chuyển NFT từ ví trải nghiệm còn lại."}</p>{mine.length ? <button className="button secondary" onClick={() => setQuery("")}>Xóa tìm kiếm</button> : <button className="button secondary" onClick={() => open("supply")}>Tạo vị thế đầu tiên</button>}</div> :
          <div className="table-scroll"><table><thead><tr><th>NFT vị thế</th><th>Vốn gốc</th><th>Lãi tích lũy</th><th>Có thể rút</th><th className="align-right">Thao tác</th></tr></thead><tbody>{filtered.map((p) => <tr key={p.id}><td><div className="nft-identity"><span className="nft-icon"><FileKey2 size={22} /></span><div><strong>Position #{p.id}</strong><span>{shortAddress(p.owner)}</span></div></div></td><td data-label="Vốn gốc"><strong>{amountLabel(p.principalWad, 4)}</strong><small>MyUSDT</small></td><td data-label="Lãi tích lũy"><strong className="amount-accent">{amountLabel(p.interestWad, 8)}</strong><small>MyUSDT</small></td><td data-label="Có thể rút"><strong>{amountLabel(withdrawLimit(snapshot, p), 4)}</strong><small>MyUSDT</small></td><td className="row-actions"><button className="row-button" onClick={() => open("transfer", p.id)} aria-label={"Chuyển NFT #" + p.id}><ArrowRightLeft size={16} />Chuyển</button><button className="row-button" onClick={() => open("withdraw", p.id)} disabled={withdrawLimit(snapshot, p) === 0n} aria-label={"Rút từ NFT #" + p.id}><ArrowUpFromLine size={16} />Rút</button></td></tr>)}</tbody></table></div>}
          <div className="table-foot"><span><ShieldCheck size={15} />Chỉ ví sở hữu NFT hiện tại có quyền rút tiền.</span><span>LendingPositionNFT · ERC-721</span></div>
        </section>
        <div className="lower-grid"><section className="panel activity-panel" id="activity" aria-labelledby="activity-title"><div className="panel-head"><h2 id="activity-title">Hoạt động gần đây</h2><span className="muted-label">Trong mô phỏng</span></div>{snapshot.activity.filter((a) => a.actor === actor || a.recipient === actor).length === 0 ? <div className="activity-empty"><ActivityIcon size={21} /><p>Chưa có thao tác nào từ ví này.<span>Lần gửi, rút hoặc chuyển NFT sẽ xuất hiện tại đây.</span></p></div> : <ul className="activity-list">{snapshot.activity.filter((a) => a.actor === actor || a.recipient === actor).slice(0, 5).map((a) => <li key={a.id}><span className="activity-icon">{a.kind === "transfer" ? <ArrowRightLeft size={19} /> : <ArrowDownLeft size={19} />}</span><div><strong>{names[a.kind]}{a.positionId ? " · #" + a.positionId : ""}</strong><span>{new Date(a.at).toLocaleString("vi-VN", { hour: "2-digit", minute: "2-digit", day: "2-digit", month: "2-digit" })}{a.recipient ? " → " + shortAddress(a.recipient) : ""}</span></div><strong className="activity-amount">{amountLabel(a.amountWad, 4)}<small>MyUSDT · mô phỏng</small></strong></li>)}</ul>}</section>
          <section className="panel demo-wallet" aria-labelledby="wallet-title"><div className="panel-head"><h2 id="wallet-title">Ví trải nghiệm {actor === ACCOUNTS[0].address ? "A" : "B"}</h2><Wallet size={20} /></div><p>Số dư dùng để thử gửi tiền</p><strong className="demo-balance">{value(snapshot.balances[actor], 2)}<small>MyUSDT</small></strong><button className="button secondary full" disabled={!ready} onClick={() => submit({ kind: "faucet", actor })}><Plus size={17} />Nhận 1.000 MyUSDT</button><p className="wallet-hint">Token mô phỏng, không có giá trị thực.</p></section></div>
        <footer className="app-footer"><span>DeFi Lending · Lãi suất thay đổi theo Pool.</span><button className="text-button" disabled={!ready} onClick={() => open("reset")}><RotateCcw size={15} />Đặt lại mô phỏng</button></footer>
      </main>
    </AppShell>
    {dialog && state && <ActionDialog key={dialog.kind + (dialog.positionId ?? "")} {...dialog} state={snapshot} actor={actor} onClose={() => setDialog(null)} onSubmit={submit} onReset={reset} />}
  </>;
}
