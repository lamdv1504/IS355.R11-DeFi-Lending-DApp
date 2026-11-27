"use client";

import { useState } from "react";
import { Activity, ArrowDownToLine, ArrowRight, BadgePercent, CircleAlert, CircleHelp, Clock3, FileKey2, Layers, LockKeyhole, Plus, RotateCcw, ShieldCheck, Wallet, X } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { BorrowInfoDialog, BorrowReviewDialog, TransactionPreview } from "@/components/borrow-transaction-preview";
import { HealthFactorGauge } from "@/components/health-factor-gauge";
import { useBorrowingDemo } from "@/hooks/use-borrowing-demo";
import { actionLabel, approvalAmount, BORROW_WALLETS, borrowingCapacity, capacityLabel, collateralValue, currentBorrowApr, formatHealthFactor, healthFactor, ltvBps, prepareBorrowTransaction, referenceApy, riskStatus, totalDebt, type BorrowAction, type BorrowActor, type CollateralKind, type TransactionAction } from "@/lib/borrowing-demo";
import { amountLabel, exactAmount, parseAmount, shortAddress, WAD } from "@/lib/lending-demo";

const pct = (n: number) => new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 2 }).format(n);
const statusText = { safe: "Khoản vay đang an toàn", warning: "Khoản vay sắp chạm ngưỡng thanh lý", danger: "Đủ điều kiện thanh lý" };
const actors = BORROW_WALLETS.map((a) => ({ value: a.id, name: a.id === "borrower" ? "Người vay" : "Thanh lý", address: a.address }));

export default function BorrowingConsole() {
  const { state, snapshot, ready, notice, setNotice, transact, reset } = useBorrowingDemo();
  const [actor, setActor] = useState<BorrowActor>("borrower");
  const [tab, setTab] = useState<"borrow" | "repay">("borrow");
  const [borrowAmount, setBorrowAmount] = useState("100");
  const [repayAmount, setRepayAmount] = useState("100");
  const [fullRepay, setFullRepay] = useState(false);
  const [asset, setAsset] = useState<CollateralKind>("nft");
  const [collateralAmount, setCollateralAmount] = useState("1000");
  const [gwei, setGwei] = useState("2");
  const [review, setReview] = useState<TransactionAction | null>(null);
  const [info, setInfo] = useState<"help" | "reset" | null>(null);
  const loan = snapshot.loan;
  const debt = totalDebt(snapshot);
  const value = collateralValue(snapshot);
  const hf = healthFactor(value, debt);
  const risk = riskStatus(hf);
  const capacity = borrowingCapacity(snapshot);
  const suggestedCapacity = debt === 0n ? capacity : capacity > WAD / 100n ? capacity - WAD / 100n : capacity / 2n;
  const borrowerSelected = actor === "borrower";
  const apr = currentBorrowApr(snapshot);
  const isBorrow = tab === "borrow";
  const draft: TransactionAction = isBorrow
    ? { kind: "borrow", actor, amount: borrowAmount }
    : { kind: "repay", actor, amount: repayAmount, full: fullRepay };
  const amount = isBorrow ? borrowAmount : fullRepay ? exactAmount(debt) : repayAmount;
  let candidate = 0n;
  let amountError = "";
  try { candidate = parseAmount(amount); }
  catch (e) { amountError = e instanceof Error ? e.message : "Số tiền không hợp lệ."; }
  if (isBorrow && loan.active && candidate > capacity) amountError = "Số tiền vượt hạn mức theo tổng nợ hoặc thanh khoản Pool.";
  const currentLtv = Number(ltvBps(snapshot));
  const candidateLtv = Number(ltvBps(snapshot, isBorrow ? candidate : 0n));
  const minSlider = Math.min(7000, currentLtv);
  const maxSlider = Math.max(minSlider, Math.min(7000, Number(value === 0n ? 0n : (debt + capacity) * 10000n / value)));
  const canLiquidate = ready && hf !== null && hf < WAD && loan.active;
  const liquidationNeedsApproval = debt > BigInt(snapshot.wallets.liquidator.allowanceWad);
  const liquidationAffordable = debt <= BigInt(snapshot.wallets.liquidator.balanceWad);
  const label = (wad: bigint | string, digits = 4) => ready ? amountLabel(wad, digits) : "—";
  function act(action: BorrowAction) {
    try {
      transact(action);
      const message = "kind" in action && action.kind in actionLabel ? actionLabel[action.kind as TransactionAction["kind"]] + " thành công trong mô phỏng." : "Đã cập nhật dữ liệu mô phỏng.";
      setNotice(message);
    } catch (e) { setNotice(e instanceof Error ? e.message : "Không thực hiện được thao tác."); }
  }
  function confirm(action: TransactionAction) {
    transact(action);
    setNotice(actionLabel[action.kind] + " thành công trong mô phỏng. Không có giao dịch blockchain.");
  }
  function reviewFromKeyboard() {
    if (!ready || !borrowerSelected || amountError) return;
    try {
      const quote = prepareBorrowTransaction(snapshot, draft, gwei);
      if (quote.needsApproval || quote.needsNftApproval) { setNotice("Cần cấp quyền trước khi xác nhận. Xem bước cấp quyền bên dưới."); return; }
      setReview(draft);
    } catch (e) { setNotice(e instanceof Error ? e.message : "Chưa chuẩn bị được giao dịch."); }
  }
  const collateralPayment = (() => { try { return asset === "token" ? parseAmount(collateralAmount) : 0n; } catch { return 0n; } })();
  const collateralApproved = asset === "nft" ? snapshot.nftApproved : collateralPayment > 0n && collateralPayment <= BigInt(snapshot.wallets.borrower.allowanceWad);
  const collateralOwned = asset !== "nft" || snapshot.nftOwner === "borrower";
  const activeWallet = snapshot.wallets[actor];

  return <>
    <AppShell section="borrowing" account={actor} choices={actors} ready={ready} onAccountChange={(choice) => { setActor(choice as BorrowActor); setNotice(""); }} onHelp={() => setInfo("help")}>
      <main id="main-content" className="wrap borrowing-console">
        <section className="page-heading" aria-labelledby="borrow-title">
          <div><div className="heading-label"><span />BORROWING CONSOLE</div><h1 id="borrow-title">Vay thế chấp MyUSDT<span className="heading-dot">.</span></h1><p>Quản lý tài sản, khoản vay và mức độ an toàn của bạn.</p></div>
          <button className="button secondary" disabled={!ready} onClick={() => setInfo("help")}><CircleHelp size={18} />Hướng dẫn</button>
        </section>
        <div className="demo-notice"><span className="demo-label">MÔ PHỎNG</span><p>Dữ liệu thử nghiệm trong trình duyệt. Không ký ví, không gửi giao dịch hoặc tạo CID thật.</p></div>
        {notice && <div className="status-message" role="status"><ShieldCheck size={19} /><p>{notice}</p><button className="icon-button" aria-label="Đóng thông báo" onClick={() => setNotice("")}><X size={18} /></button></div>}
        {ready && <div className={"risk-banner risk-" + risk} role="status"><span className="risk-symbol">{risk === "safe" ? <ShieldCheck size={22} /> : <CircleAlert size={22} />}</span><div><strong>{debt === 0n ? "Không có dư nợ" : statusText[risk]}</strong><p>{debt === 0n ? "Tài sản không có rủi ro thanh lý do nợ. Bạn có thể khóa tài sản để tạo khoản vay." : risk === "safe" ? "Tiếp tục theo dõi giá tài sản và tiền lãi phát sinh." : risk === "warning" ? "Vui lòng trả bớt nợ để cải thiện HF. Muốn thay tài sản thế chấp, hãy tất toán vị thế trước." : "HF dưới 1. Thanh lý cần ví đủ MyUSDT, cấp quyền và xác nhận riêng; không tự diễn ra khi giảm giá."}</p></div><span className="risk-badge">HF {formatHealthFactor(hf)}</span></div>}
        <section className="kpi-grid" aria-label="Tổng quan khoản vay">
          <article className="kpi-card"><div className="kpi-top"><span>Giá trị thế chấp</span><LockKeyhole size={20} /></div><div className="kpi-value">{label(value, 2)}</div><div className="kpi-foot">MyUSDT · theo giá mô phỏng</div></article>
          <article className="kpi-card kpi-featured"><div className="kpi-top"><span>Tổng nợ hiện tại</span><Layers size={20} /></div><div className="kpi-value">{label(debt, 2)}</div><div className="kpi-foot">Gốc + lãi · MyUSDT</div></article>
          <article className="kpi-card"><div className="kpi-top"><span>Có thể vay thêm</span><Wallet size={20} /></div><div className="kpi-value">{ready ? capacityLabel(capacity, 4) : "—"}</div><div className="kpi-foot">MyUSDT · LTV tối đa 70%</div></article>
          <article className="kpi-card"><div className="kpi-top"><span>Borrow APR</span><BadgePercent size={20} /></div><div className="kpi-value">{ready ? pct(apr / 100) : "—"}<span>%</span></div><div className="kpi-foot">APY tham khảo {ready ? pct(referenceApy(apr)) : "—"}%</div></article>
        </section>
        <div className="borrowing-grid">
          <div className="borrowing-column">
            <section className="panel collateral-panel" id="collateral" aria-labelledby="collateral-title">
              <div className="panel-head"><h2 id="collateral-title">Tài sản thế chấp</h2><span className="icon-tile"><FileKey2 size={20} /></span></div>
              {!ready ? <p className="borrow-loading" aria-busy="true">Đang tải tài sản…</p> : loan.active ? <>
                <div className="collateral-asset"><span className="collateral-art">{loan.kind === "nft" ? <FileKey2 size={40} /> : <Layers size={40} />}</span><div><p className="asset-type">{loan.kind === "nft" ? "COLLATERAL NFT" : "ERC-20 COLLATERAL"}</p><h3>{loan.kind === "nft" ? "CollateralNFT #7" : amountLabel(loan.collateralUnitsWad) + " MyUSDT"}</h3><span className="locked-tag"><LockKeyhole size={13} />Đang khóa trong Pool</span></div></div>
                <dl className="collateral-facts"><div><dt>Giá trị hiện tại</dt><dd>{label(value, 4)} MyUSDT</dd></div><div><dt>Trần tổng nợ (70%)</dt><dd>{label(value * 7000n / 10000n, 4)} MyUSDT</dd></div><div><dt>Biên nhận thế chấp</dt><dd>Receipt #{loan.receiptId}</dd></div><div><dt>Chủ khoản vay</dt><dd title={BORROW_WALLETS[0].address}>{shortAddress(BORROW_WALLETS[0].address)}</dd></div></dl>
                <p className="collateral-hint">Biên nhận và DebtToken không chuyển nhượng. Rút thế chấp khi tổng nợ bằng 0; trả hết nợ sẽ tự mở khóa.</p>
                {debt === 0n && <button className="button secondary full" disabled={!borrowerSelected} onClick={() => setReview({ kind: "withdraw", actor })}><ArrowDownToLine size={17} />Xem trước rút thế chấp</button>}
              </> : <>
                <p className="collateral-hint">{loan.receiptStatus === "liquidated" ? "Vị thế trước đã thanh lý. NFT #7 hiện thuộc ví thanh lý." : loan.receiptStatus === "settled" ? "Đã tất toán và mở khóa tài sản. Bạn có thể tạo vị thế mới." : "Chọn tài sản và cấp quyền trước khi khóa vào Pool."}</p>
                <div className="asset-switch" role="group" aria-label="Loại tài sản thế chấp"><button aria-pressed={asset === "nft"} onClick={() => setAsset("nft")}>Collateral NFT</button><button aria-pressed={asset === "token"} onClick={() => setAsset("token")}>Token MyUSDT</button></div>
                {asset === "token" ? <div className="field"><label htmlFor="collateral-amount">Số MyUSDT thế chấp</label><input id="collateral-amount" value={collateralAmount} inputMode="decimal" onChange={(e) => setCollateralAmount(e.target.value)} disabled={!borrowerSelected} /></div> : <p className="nft-choice"><FileKey2 size={20} />NFT #7 · giá gốc 1.000 MyUSDT<span>{collateralOwned ? "Thuộc ví người vay" : "Không thuộc ví người vay"}</span></p>}
                <div className="collateral-buttons"><button className="button secondary full" disabled={!borrowerSelected || !collateralOwned || collateralApproved || (asset === "token" && collateralPayment === 0n)} onClick={() => setReview(asset === "nft" ? { kind: "approve-nft", actor } : { kind: "approve", actor, amount: exactAmount(collateralPayment) })}>{collateralApproved ? "Đã cấp quyền" : "1. Xem trước cấp quyền"}</button><button className="button primary full" disabled={!borrowerSelected || !collateralOwned || !collateralApproved} onClick={() => setReview({ kind: "deposit", actor, asset, amount: collateralAmount })}>2. Xem trước thế chấp<ArrowRight size={17} /></button></div>
              </>}
            </section>
            <section className="panel health-panel" aria-labelledby="health-title">
              <div className="panel-head"><h2 id="health-title">Sức khỏe khoản vay</h2><span className="muted-label">Health Factor</span></div>
              {ready ? <HealthFactorGauge value={hf} /> : <p className="borrow-loading" aria-busy="true">Đang tải Health Factor…</p>}
              <div className="health-legend"><span><i className="risk-dot danger" />Dưới 1</span><span><i className="risk-dot warning" />{ "1 đến <1,5" }</span><span><i className="risk-dot safe" />Từ 1,5</span></div>
              <p className="health-formula">HF = giá trị thế chấp × 80% ÷ tổng nợ. Không có nợ: ∞. HF = 1 vẫn chặn thanh lý.</p>
              <div className="liquidation-control"><strong>Thử thanh lý bằng ví riêng</strong><p>Chọn “Ví thanh lý” ở đầu trang. Không có giao dịch tự động khi HF giảm.</p>
                {canLiquidate && actor === "liquidator" && liquidationNeedsApproval && <button className="button secondary full" disabled={!liquidationAffordable} onClick={() => setReview({ kind: "approve", actor, amount: exactAmount(approvalAmount(debt)) })}>Xem trước cấp quyền thanh lý</button>}
                <button className="button secondary full liquidation-button" disabled={!canLiquidate || actor !== "liquidator" || liquidationNeedsApproval || !liquidationAffordable} onClick={() => setReview({ kind: "liquidate", actor })}>Xem trước thanh lý</button>
                {canLiquidate && actor === "liquidator" && !liquidationAffordable && <p className="form-error">Ví thanh lý chưa đủ MyUSDT để trả toàn bộ nợ.</p>}
              </div>
            </section>
          </div>
          <section className="panel loan-panel" id="loan" aria-labelledby="loan-title">
            <div className="panel-head"><h2 id="loan-title">Quản lý khoản vay</h2><span className="loan-standard">DebtToken · không chuyển nhượng</span></div>
            <div className="loan-balances"><div><span>DebtToken / nợ gốc</span><strong>{label(loan.principalWad, 4)} <small>MyUSDT</small></strong></div><div><span>Lãi phát sinh</span><strong>{label(loan.interestWad, 8)} <small>MyUSDT</small></strong></div></div>
            <div className="loan-tabs" role="tablist" aria-label="Thao tác khoản vay"><button role="tab" id="borrow-tab" aria-selected={isBorrow} aria-controls="loan-form" tabIndex={isBorrow ? 0 : -1} onClick={() => setTab("borrow")} onKeyDown={(e) => { if (e.key === "ArrowRight" || e.key === "ArrowLeft") { e.preventDefault(); setTab("repay"); document.getElementById("repay-tab")?.focus(); } }}>Vay thêm</button><button role="tab" id="repay-tab" aria-selected={!isBorrow} aria-controls="loan-form" tabIndex={!isBorrow ? 0 : -1} onClick={() => setTab("repay")} onKeyDown={(e) => { if (e.key === "ArrowRight" || e.key === "ArrowLeft") { e.preventDefault(); setTab("borrow"); document.getElementById("borrow-tab")?.focus(); } }}>Trả nợ</button></div>
            <div id="loan-form" role="tabpanel" aria-labelledby={isBorrow ? "borrow-tab" : "repay-tab"} className="loan-form">
              {!borrowerSelected && <p className="borrow-role-note">Đang dùng ví thanh lý. Chọn ví người vay để thế chấp, vay hoặc trả nợ.</p>}
              <div className="field"><label htmlFor="loan-amount">{isBorrow ? "Số MyUSDT vay thêm" : "Số MyUSDT trả nợ"}</label><div className="amount-input"><input id="loan-amount" onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); reviewFromKeyboard(); } }} value={amount} inputMode="decimal" autoComplete="off" disabled={!ready || !borrowerSelected || (!isBorrow && fullRepay)} aria-invalid={ready && !!amountError} aria-describedby={amountError ? "loan-amount-error" : "loan-amount-hint"} onChange={(e) => isBorrow ? setBorrowAmount(e.target.value) : setRepayAmount(e.target.value)} /><button disabled={!ready || !borrowerSelected || (isBorrow ? capacity === 0n : debt === 0n)} onClick={() => { if (isBorrow) setBorrowAmount(exactAmount(suggestedCapacity)); else setFullRepay(true); }}>{isBorrow ? "Tối đa" : "Trả hết"}</button></div>
                <p className="field-hint" id="loan-amount-hint">{isBorrow ? "Có thể vay thêm: " + (ready ? capacityLabel(capacity, 8) : "—") : "Tổng nợ hiện tại: " + label(debt, 8)} MyUSDT</p>
                {ready && amountError && <p className="form-error" id="loan-amount-error" role="alert">{amountError}</p>}
              </div>
              {isBorrow ? <div className="ltv-control"><div className="ltv-caption"><label htmlFor="borrow-ltv">LTV dự kiến</label><strong>{ready ? pct(candidateLtv / 100) : "—"}%<span> / trần 70%</span></strong></div><input id="borrow-ltv" type="range" min={minSlider} max={maxSlider} step={1} value={Math.min(maxSlider, Math.max(minSlider, candidateLtv))} disabled={!ready || !borrowerSelected || !loan.active || capacity === 0n || maxSlider === minSlider} aria-valuetext={"LTV dự kiến " + pct(candidateLtv / 100) + "%, trần 70%"} onChange={(e) => { const desired = value * BigInt(e.target.value) / 10000n - debt; const next = desired < 0n ? 0n : desired > suggestedCapacity ? suggestedCapacity : desired; setBorrowAmount(exactAmount(next)); }} /><div className="ltv-scale"><span>Hiện tại {ready ? pct(currentLtv / 100) : "—"}%</span><span>Tối đa 70%</span></div><p>Hạn mức tính cả lãi. Nút tối đa giữ dư địa nhỏ cho lãi phát sinh trong lúc xem trước.</p></div> : <div className="repay-options"><label><input type="checkbox" checked={fullRepay} disabled={!ready || !borrowerSelected || debt === 0n} onChange={(e) => setFullRepay(e.target.checked)} />Trả hết nợ tại thời điểm xác nhận</label><p>Trả lãi trước, rồi trừ nợ gốc. Trả hết sẽ burn DebtToken và mở khóa tài sản trong mô phỏng.</p></div>}
              <div className="pool-available"><span>Thanh khoản Pool khả dụng</span><strong>{label(snapshot.poolCashWad, 4)} MyUSDT</strong></div>
            </div>
            {ready ? <TransactionPreview state={snapshot} action={draft} gwei={gwei} onGweiChange={setGwei} ready={ready && borrowerSelected && !amountError} onReview={setReview} /> : <p className="borrow-loading" aria-busy="true">Đang tải phần xem trước…</p>}
          </section>
        </div>
        <section className="panel borrowing-scenarios" aria-labelledby="scenarios-title">
          <div><div className="heading-label"><span />KỊCH BẢN THỬ NGHIỆM</div><h2 id="scenarios-title">Quan sát rủi ro khi giá thay đổi</h2><p>Các nút chỉ đổi dữ liệu mô phỏng trên trình duyệt, không cập nhật Oracle hoặc tua blockchain thật.</p></div>
          <div className="scenario-controls"><div><span className="scenario-label">Giá so với ban đầu</span><div className="scenario-buttons" role="group" aria-label="Kịch bản giá tài sản">{[10000, 8000, 6000].map((bps) => <button key={bps} aria-pressed={snapshot.priceBps === bps} disabled={!ready} onClick={() => act({ kind: "price", multiplierBps: bps })}>{bps / 100}%</button>)}</div></div><div><span className="scenario-label">Lãi theo thời gian</span><button className="button secondary" disabled={!ready} onClick={() => act({ kind: "advance", seconds: 30 * 86400 })}><Clock3 size={17} />Thêm 30 ngày</button><small>Đã tăng {snapshot.offsetSeconds / 86400} ngày</small></div></div>
        </section>
        <div className="borrow-lower-grid">
          <section className="panel activity-panel" id="borrow-activity" aria-labelledby="borrow-activity-title"><div className="panel-head"><h2 id="borrow-activity-title">Hoạt động khoản vay</h2><span className="muted-label">Trong mô phỏng</span></div>{snapshot.activity.length ? <ul className="borrow-activity-list">{snapshot.activity.slice(0, 6).map((event) => <li key={event.id}><Activity size={17} /><strong>{event.label}</strong><time dateTime={new Date(event.at * 1000).toISOString()}>{new Date(event.at * 1000).toLocaleString("vi-VN", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}</time></li>)}</ul> : <div className="activity-empty"><Activity size={22} /><p>Chưa có thao tác.<span>Giao dịch và thay đổi kịch bản sẽ xuất hiện tại đây.</span></p></div>}</section>
          <section className="panel demo-wallet"><div className="panel-head"><h2>{borrowerSelected ? "Ví người vay" : "Ví thanh lý"}</h2><Wallet size={20} /></div><p>{shortAddress(BORROW_WALLETS.find((a) => a.id === actor)!.address)}</p><strong className="demo-balance">{label(activeWallet.balanceWad, 4)}<small>MyUSDT</small></strong><button className="button secondary full" disabled={!ready} onClick={() => act({ kind: "faucet", actor })}><Plus size={17} />Nhận 1.000 MyUSDT</button><p className="wallet-hint">Token thử nghiệm, không có giá trị thực.</p></section>
        </div>
        <footer className="app-footer"><span>DeFi Lending · APR tính lãi theo giây · Gas mô phỏng.</span><button className="text-button" disabled={!ready} onClick={() => setInfo("reset")}><RotateCcw size={15} />Đặt lại mô phỏng L03</button></footer>
      </main>
    </AppShell>
    {review && state && <BorrowReviewDialog key={review.kind} state={snapshot} action={review} gwei={gwei} onClose={() => setReview(null)} onConfirm={confirm} />}
    {info && <BorrowInfoDialog kind={info} onClose={() => setInfo(null)} onReset={(empty) => { reset(empty); setBorrowAmount("100"); setRepayAmount("100"); setFullRepay(false); setTab("borrow"); }} />}
  </>;
}
