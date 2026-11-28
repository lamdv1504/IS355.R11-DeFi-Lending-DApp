"use client";
import { useState, type FormEvent } from "react";
import { Coins, FileKey2, ShieldCheck } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { useWallet } from "@/components/wallet-provider";
import { useLiveData } from "@/hooks/use-live-data";
import { HealthFactorGauge } from "@/components/health-factor-gauge";
import { LiveActivity, LiveModeNotice, DemoToolbar, ReadStatus, array, obj, wad, money, integer, percentage, canTransact, LiveHelp } from "@/components/live-common";
import { parseAmount, WAD } from "@/lib/wad";
import { address, type Operation } from "@/lib/wallet-transactions";
import { walletError } from "@/lib/wallet-client";

export default function LiveBorrowingConsole() {
  const { state, client } = useWallet();
  const pool = useLiveData("/api/pool");
  const snapshot = useLiveData(state.account ? "/api/accounts/" + state.account + "/snapshot" : null);
  const loanRead = useLiveData(state.account ? "/api/accounts/" + state.account + "/loan" : null);
  const loan = obj(snapshot.data?.loan_position), risk = obj(snapshot.data?.risk), balances = obj(snapshot.data?.balances);
  const debt = wad(risk.total_debt), collateral = wad(risk.collateral_value), principal = wad(loan.principal);
  const hfRaw = integer(risk.health_factor_wad);
  const hf = debt === "0" ? null : hfRaw ? BigInt(hfRaw) : undefined;
  const capacity = wad(obj(loanRead.data?.borrowing_capacity).available_to_borrow);
  const nfts = array(balances.collateral_nfts);
  const [kind, setKind] = useState<"collateral" | "borrow" | "repay" | "withdraw">("borrow");
  const [asset, setAsset] = useState<"nft" | "token">("nft");
  const [tokenId, setTokenId] = useState("");
  const [amount, setAmount] = useState("500");
  const [description, setDescription] = useState("");
  const [repayAll, setRepayAll] = useState(true);
  const [target, setTarget] = useState("");
  const [help, setHelp] = useState(false);
  const [error, setError] = useState("");
  const validTarget = /^0x[0-9a-fA-F]{40}$/.test(target.trim());
  const targetRead = useLiveData(validTarget ? "/api/accounts/" + target.trim() + "/loan" : null);
  const targetRisk = obj(targetRead.data?.risk), targetDebt = wad(targetRisk.total_debt), targetHf = integer(targetRisk.health_factor_wad);
  const liquidatable = targetDebt !== null && BigInt(targetDebt)>0n && !!targetHf && BigInt(targetHf)<WAD;
  const chosenNft = tokenId || integer(nfts[0]?.token_id);
  const ready = canTransact(state);
  const prepare = async (event: FormEvent) => {
    event.preventDefault(); setError("");
    try {
      let operation: Operation;
      if (kind === "collateral") {
        if (asset === "nft" && !chosenNft) throw new Error("Ví chưa có NFT phù hợp. Chọn token ERC-20 hoặc nhận NFT đã được bàn giao.");
        operation = { action: "DEPOSIT_COLLATERAL", args: { is_nft: asset==="nft", collateral_amount_or_token_id: asset==="nft" ? chosenNft : parseAmount(amount).toString() } };
      } else if (kind === "borrow") {
        if (!description.trim()) throw new Error("Nhập mô tả tài sản để tạo PDF thỏa thuận vay.");
        const value = parseAmount(amount);
        if (capacity !== null && value>BigInt(capacity)) throw new Error("Khoản vay vượt hạn mức hiện tại. Làm mới số liệu rồi thử lại.");
        operation = { action: "BORROW", args: { amount_wad: value.toString() }, assetDescription: description.trim() };
      } else if (kind === "repay") operation = { action: "REPAY", args: { amount_wad: repayAll ? "1" : parseAmount(amount).toString() }, repayAll };
      else operation = { action: "WITHDRAW_COLLATERAL", args: {} };
      await client.prepare(operation);
    } catch (e) { setError(walletError(e)); }
  };
  const blocked = !ready || (kind==="borrow" && (loan.active !== true || capacity === "0")) || (kind==="collateral" && loan.active === true) ||
    (kind==="withdraw" && (loan.active !== true || debt !== "0")) || (kind==="repay" && (!debt || debt==="0"));
  return <AppShell section="borrowing" account="" choices={[]} ready onAccountChange={() => {}} onHelp={() => setHelp(true)}>
    <main id="main-content" className="wrap borrowing-console live-console">
      <section className="page-heading"><div><div className="heading-label"><span />BORROWING CONSOLE</div><h1>Vay thế chấp MyUSDT<span className="heading-dot">.</span></h1><p>Tài sản, nợ và Health Factor đọc từ mạng đã chọn.</p></div></section>
      <LiveModeNotice /><ReadStatus {...(state.account ? snapshot : pool)} />
      <section className="kpi-grid" aria-label="Số liệu khoản vay từ API"><article className="kpi-card"><div className="kpi-top"><span>Tài sản thế chấp</span><FileKey2 size={19}/></div><div className="kpi-value">{money(collateral,2)}</div><div className="kpi-foot">Định giá MyUSDT</div></article><article className="kpi-card"><div className="kpi-top"><span>Tổng dư nợ</span><Coins size={19}/></div><div className="kpi-value">{money(debt,4)}</div><div className="kpi-foot">Gốc {money(principal,2)} + lãi</div></article><article className="kpi-card"><div className="kpi-top"><span>Còn có thể vay</span><ShieldCheck size={19}/></div><div className="kpi-value">{money(capacity,4)}</div><div className="kpi-foot">Theo LTV và thanh khoản Pool</div></article><article className="kpi-card"><div className="kpi-top"><span>MyUSDT trong ví</span><Coins size={19}/></div><div className="kpi-value">{money(wad(balances.myusdt),2)}</div><div className="kpi-foot">Số dư on-chain</div></article></section>
      <div className="overview-grid">
        <section className="panel live-form-panel" id="collateral" aria-labelledby="live-borrow-form"><h2 id="live-borrow-form">Quản lý khoản vay</h2><div className="live-tabs" role="group" aria-label="Loại thao tác khoản vay">{([["collateral","Thế chấp"],["borrow","Vay"],["repay","Trả nợ"],["withdraw","Rút tài sản"]] as const).map(([value,label]) => <button key={value} aria-pressed={kind===value} onClick={() => {setKind(value);setError("");}}>{label}</button>)}</div>
          <form onSubmit={prepare}>
            {kind==="collateral" && <><div className="field"><label htmlFor="live-collateral-kind">Loại tài sản</label><select id="live-collateral-kind" value={asset} onChange={(e) => setAsset(e.target.value as "nft"|"token")}><option value="nft">CollateralNFT đang sở hữu</option><option value="token">Token ERC-20 MyUSDT</option></select></div>{asset==="nft" && <div className="field"><label htmlFor="live-collateral-nft">Mã NFT thuộc ví</label><select id="live-collateral-nft" required value={chosenNft} onChange={(e) => setTokenId(e.target.value)}><option value="">Chọn NFT</option>{nfts.map((nft) => <option key={integer(nft.token_id)} value={integer(nft.token_id)}>NFT #{integer(nft.token_id)} · {money(wad(nft.valuation),2)} MyUSDT</option>)}</select><p className="field-hint">Danh sách lấy từ ví đang kết nối; không sử dụng mã NFT cố định.</p></div>}</>}
            {kind==="repay" && <label className="live-checkbox"><input type="checkbox" checked={repayAll} onChange={(e) => setRepayAll(e.target.checked)} />Trả hết — đọc lại nợ trước khi chuẩn bị</label>}
            {(kind==="borrow" || (kind==="repay"&&!repayAll) || (kind==="collateral"&&asset==="token")) && <div className="field"><label htmlFor="live-borrow-amount">Số MyUSDT</label><input id="live-borrow-amount" inputMode="decimal" required value={amount} onChange={(e) => setAmount(e.target.value)} /></div>}
            {kind==="borrow" && <div className="field"><label htmlFor="live-asset-description">Mô tả tài sản trong thỏa thuận vay</label><input id="live-asset-description" maxLength={500} required value={description} onChange={(e) => setDescription(e.target.value)} /><p className="field-hint">PDF được tạo và mã hóa trước giao dịch; CID chỉ được gắn với txHash sau khi backend xác nhận borrow thành công.</p></div>}
            {kind==="repay"&&repayAll && <p className="field-hint">Khoản chuẩn bị có đệm 0,01 MyUSDT cho lãi phát sinh. Contract chỉ thu nợ thực tế; tất toán tự mở khóa tài sản.</p>}
            {kind==="withdraw" && <p className="field-hint">Chỉ rút riêng khi chưa có nợ nhưng tài sản vẫn khóa. Trả hết nợ đã tự trả tài sản theo contract.</p>}
            {kind==="collateral"&&loan.active===true && <p className="field-hint">Đang có tài sản khóa. Tất toán hoặc rút vị thế hiện tại trước.</p>}
            {kind==="borrow"&&loan.active!==true && <p className="field-hint">Khóa tài sản thế chấp trước khi vay.</p>}
            {error && <p className="form-error" role="alert">{error}</p>}{!state.session && <p className="field-hint">Kết nối MetaMask và ký xác thực ở thanh trên để tiếp tục.</p>}
            <button className="button primary full" disabled={blocked}>Xem trước giao dịch</button>
            <p className="field-hint">Nếu cần cấp quyền, ký riêng bước approve rồi chuẩn bị lại thao tác chính để ước lượng gas thật.</p>
          </form>
          {client.getSnapshot().agreementCid && <p className="field-hint live-cid">CID vừa tạo (chưa thay thế xác nhận khoản vay): <code>{state.agreementCid}</code></p>}
        </section>
        <section className="panel live-health" aria-labelledby="live-health-title"><div className="panel-head"><h2 id="live-health-title">Health Factor</h2><ShieldCheck size={20}/></div>{hf!==undefined ? <HealthFactorGauge value={hf}/> : <p className="live-empty">Kết nối ví và đọc khoản vay để hiển thị Health Factor.</p>}
          {hf!==undefined&&hf!==null&&hf<WAD && <p className="form-error" role="alert">HF &lt; 1: khoản vay đủ điều kiện thanh lý. Giảm giá không tự gửi giao dịch thanh lý.</p>}
          <dl className="wallet-quote"><div><dt>Vốn gốc</dt><dd>{money(principal)} MyUSDT</dd></div><div><dt>Lãi tích lũy</dt><dd>{money(wad(obj(snapshot.data?.interest).accrued),8)} MyUSDT</dd></div><div><dt>Borrow APR</dt><dd>{percentage(obj(obj(obj(snapshot.data?.interest).rates).borrow_apr).percent)}</dd></div><div><dt>Thanh khoản Pool</dt><dd>{money(wad(pool.data?.available_liquidity))} MyUSDT</dd></div><div><dt>Tài sản đang khóa</dt><dd>{!snapshot.data ? "Chưa có dữ liệu" : loan.active===true ? loan.is_nft_collateral ? "NFT #" + integer(loan.collateral_token_id) : "ERC-20 MyUSDT" : "Chưa có vị thế"}</dd></div></dl>
          {typeof loan.ipfs_agreement_cid==="string"&&loan.ipfs_agreement_cid && <p className="live-cid">CID theo vị thế: <code>{loan.ipfs_agreement_cid}</code></p>}
          <p className="field-hint">HF ≥ 1,5 an toàn; 1 ≤ HF &lt; 1,5 cần theo dõi; chỉ HF &lt; 1 mới được thanh lý. Vay bị giới hạn tổng nợ LTV 70%.</p>
        </section>
      </div>
      <section className="panel live-liquidation" aria-labelledby="live-liquidation-title"><h2 id="live-liquidation-title">Thanh lý bằng giao dịch riêng</h2><form onSubmit={(e) => {e.preventDefault();setError("");void (async()=>{try {await client.prepare({action:"LIQUIDATE",args:{borrower_address:address(target.trim())}});} catch(error){setError(walletError(error));}})();}}><div className="field"><label htmlFor="live-liquidation-target">Ví người vay cần kiểm tra</label><input id="live-liquidation-target" autoComplete="off" required value={target} onChange={(e)=>setTarget(e.target.value)}/></div>{validTarget&&<ReadStatus {...targetRead}/>}<p className="field-hint">Dư nợ: {money(targetDebt)} MyUSDT · {validTarget ? liquidatable ? "HF dưới 1, có thể chuẩn bị thanh lý." : "Chưa đủ điều kiện hoặc đang chờ dữ liệu." : "Nhập ví để đọc trạng thái."}</p><button className="button secondary" disabled={!ready||!liquidatable}>Xem trước thanh lý</button></form><p className="field-hint">Người thanh lý cần MyUSDT và allowance. NFT thế chấp có thể được chuyển toàn bộ; xem báo giá và xác nhận trong MetaMask.</p></section>
      <DemoToolbar/><LiveActivity id="borrow-activity"/><footer className="app-footer"><span>IS355 · Vay thế chấp MyUSDT</span><span>{state.network} · Ký tại ví người dùng</span></footer>
    </main><LiveHelp open={help} onClose={()=>setHelp(false)}/>
  </AppShell>;
}
