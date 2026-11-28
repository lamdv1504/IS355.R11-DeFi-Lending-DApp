"use client";
import { createContext, useContext, useEffect, useMemo, useRef, useState, useSyncExternalStore, type ReactNode } from "react";
import Link from "next/link";
import { AlertCircle, Clock, Check, ExternalLink, Settings2, ShieldCheck, Wallet, X } from "lucide-react";
import { WalletClient, type Eip1193Provider, type WalletState } from "@/lib/wallet-client";
import { ACTION_NAMES, CHAINS, explorerTx, type DeploymentRegistry, type NetworkId } from "@/lib/wallet-transactions";
import { shortAddress, formatUnitsDecimal } from "@/lib/wad";
import type { HubConnection } from "@/lib/ipfs-hub";

type Injected = Eip1193Provider & { isMetaMask?: boolean; providers?: Injected[] };
function injected() {
  const ethereum = (window as Window & { ethereum?: Injected }).ethereum;
  return ethereum?.providers?.find((p) => p.isMetaMask) || (ethereum?.isMetaMask ? ethereum : null);
}
interface Context { client: WalletClient; state: WalletState; connection: HubConnection; scopeKey: string }
const WalletContext = createContext<Context | null>(null);
export function useWallet() { const context = useContext(WalletContext); if (!context) throw new Error("Thiếu WalletProvider."); return context; }
export function WalletProvider({ registry, children }: { registry: DeploymentRegistry; children: ReactNode }) {
  const [client] = useState(() => new WalletClient({ registry, getProvider: injected, domain: () => ["127.0.0.1", "[::1]"].includes(window.location.hostname) ? "localhost" : window.location.hostname,
    baseUrl: process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000" }));
  const state = useSyncExternalStore(client.subscribe, client.getSnapshot, client.getSnapshot);
  useEffect(() => {
    void client.initialize();
    const tick = setInterval(() => client.expire(), 1000);
    const focus = () => client.expire(); window.addEventListener("focus", focus);
    return () => { clearInterval(tick); window.removeEventListener("focus", focus); client.dispose(); };
  }, [client]);
  const connection = useMemo<HubConnection>(() => ({ mode: state.mode === "live" ? "api" : "sample", baseUrl: state.baseUrl, token: state.session?.token || "", network: state.network, fromBlock: client.getStartBlock(), onUnauthorized: () => { if (state.session?.token && client.getSnapshot().session?.token === state.session.token) client.clearSession(); } }),
    [client, state.mode, state.baseUrl, state.session, state.network]);
  const context = useMemo(() => ({ client, state, connection, scopeKey: state.epoch + ":" + state.revision }), [client, state, connection]);
  return <WalletContext.Provider value={context}>{children}<WalletReview /><WalletFeedback /></WalletContext.Provider>;
}
export function WalletToolbar() {
  const { client, state } = useWallet();
  const [settings, setSettings] = useState(false);
  const [origin, setOrigin] = useState(state.baseUrl);
  const [error, setError] = useState("");
  const modal = useRef<HTMLDialogElement>(null);
  useEffect(() => { if (settings) modal.current?.showModal(); else modal.current?.close(); }, [settings]);
  const attempt = (work: Promise<unknown>) => { void work.catch(() => {}); };
  return <><div className="wallet-toolbar">
    <button className="wallet-mode" onClick={() => client.setMode(state.mode === "live" ? "sample" : "live")}>{state.mode === "live" ? "Dữ liệu mẫu" : "Kết nối thật"}</button>
    {state.mode === "live" && <>
      <div className="wallet-network-field"><label htmlFor="wallet-network">Mạng</label><select id="wallet-network" className="wallet-network" value={state.network} disabled={state.busy} onChange={(e) => attempt(client.switchNetwork(e.target.value as NetworkId))}><option value="local">Local · 31337</option><option value="sepolia">Sepolia · 11155111</option></select></div>
      {state.account ? <><span className="wallet-account" title={state.account}><Wallet size={16} />{shortAddress(state.account)}</span>{!state.session ? <button className="button primary wallet-sign" disabled={state.busy || state.chainId !== CHAINS[state.network]} onClick={() => attempt(client.authenticate())}>Ký xác thực</button> : <span className="wallet-auth"><ShieldCheck size={16} />{state.session.roles.includes("ADMIN") ? "Admin" : "Đã xác thực"}</span>}<button className="icon-button" aria-label="Ngắt phiên ví" onClick={() => client.disconnect()}><X size={17} /></button></> : <button className="button primary wallet-connect" disabled={state.busy} onClick={() => attempt(client.connect())}><Wallet size={17} />{state.busy ? "Đang kết nối…" : "Kết nối MetaMask"}</button>}
      <button className="icon-button" aria-label="Cài đặt địa chỉ API" onClick={() => { setOrigin(state.baseUrl); setError(""); setSettings(true); }}><Settings2 size={18} /></button>
    </>}
  </div><dialog ref={modal} className="action-dialog wallet-settings" aria-labelledby="wallet-settings-title" onCancel={() => setSettings(false)} onClose={() => setSettings(false)}><div className="dialog-top"><h2 id="wallet-settings-title">Địa chỉ API</h2><button className="icon-button" aria-label="Đóng cài đặt API" onClick={() => setSettings(false)}><X size={20} /></button></div><form onSubmit={(e) => { e.preventDefault(); try { client.configure(origin); setSettings(false); } catch (e) { setError(e instanceof Error ? e.message : "Địa chỉ không hợp lệ."); } }}><div className="field"><label htmlFor="wallet-api-origin">Origin backend Q05</label><input id="wallet-api-origin" type="url" required value={origin} onChange={(e) => setOrigin(e.target.value)} /></div><p className="field-hint">Đổi API sẽ xóa phiên và báo giá cũ. Dùng HTTPS hoặc localhost.</p>{error && <p className="form-error" role="alert">{error}</p>}<button className="button primary full" type="submit">Áp dụng địa chỉ</button></form></dialog></>;
}
function display(value: unknown) { return typeof value === "string" || typeof value === "number" ? String(value) : "—"; }
function money(value: unknown) { try { return formatUnitsDecimal(BigInt(String(value)), 18).replace(".", ","); } catch { return "—"; } }
function WalletReview() {
  const { state, client } = useWallet();
  const modal = useRef<HTMLDialogElement>(null);
  const quote = state.quote;
  useEffect(() => { if (quote) modal.current?.showModal(); else modal.current?.close(); }, [quote]);
  return <dialog ref={modal} className="action-dialog wallet-review" aria-labelledby="wallet-review-title" onCancel={() => client.cancelQuote()}>
    {quote && <><div className="dialog-top"><ShieldCheck size={25} /><button className="icon-button" aria-label="Hủy báo giá" onClick={() => client.cancelQuote()}><X size={20} /></button></div><h2 id="wallet-review-title">{ACTION_NAMES[quote.operation.action]}</h2><p className="dialog-description">Kiểm tra trước khi mở MetaMask. Báo giá có hiệu lực tối đa 2 phút, phí thực tế do giao dịch đã đào quyết định.</p>
      <dl className="wallet-quote"><div><dt>Ví gửi</dt><dd title={quote.account}>{shortAddress(quote.account)}</dd></div><div><dt>Mạng</dt><dd>{quote.network} · {CHAINS[quote.network]}</dd></div><div><dt>Contract nhận</dt><dd><code>{quote.tx.to}</code></dd></div>
      {quote.operation.args.recipient_address && <div><dt>Ví nhận tài sản / NFT</dt><dd><code>{String(quote.operation.args.recipient_address)}</code></dd></div>}
      {quote.operation.args.borrower_address && <div><dt>Ví khoản vay thanh lý</dt><dd><code>{String(quote.operation.args.borrower_address)}</code></dd></div>}
      {quote.operation.args.multiplier_bps !== undefined && <div><dt>Giá Oracle so với gốc</dt><dd>{Number(quote.operation.args.multiplier_bps)/100}%</dd></div>}
      <div><dt>Số tiền / ID</dt><dd>{quote.operation.args.amount_wad ? money(quote.operation.args.amount_wad) + " MyUSDT" : quote.operation.args.collateral_amount_or_token_id ? quote.operation.args.is_nft ? "NFT #" + quote.operation.args.collateral_amount_or_token_id : money(quote.operation.args.collateral_amount_or_token_id) + " MyUSDT" : display(quote.operation.args.position_id ?? quote.operation.args.token_id)}</dd></div>
      <div><dt>Gas ước lượng</dt><dd>{display(quote.gas.estimated_gas)} units</dd></div><div><dt>Giới hạn gas</dt><dd>{display(quote.gas.gas_limit)} units</dd></div><div><dt>Giá gas</dt><dd>{formatUnitsDecimal(String(quote.gas.gas_price_wei), 9)} gwei</dd></div><div><dt>Phí dự kiến</dt><dd>{display(quote.gas.estimated_fee_eth)} ETH</dd></div><div><dt>Phí tối đa theo quote</dt><dd>{display(quote.gas.max_fee_eth)} ETH</dd></div>
      {quote.preview.resulting_borrow_apr_bps !== undefined && <div><dt>APR vay sau thao tác</dt><dd>{Number(quote.preview.resulting_borrow_apr_bps) / 100}% / năm</dd></div>}
      {quote.preview.resulting_supply_apr_bps !== undefined && <div><dt>APR gửi sau thao tác</dt><dd>{Number(quote.preview.resulting_supply_apr_bps) / 100}% / năm</dd></div>}
      {quote.interest && <div><dt>Lãi ước tính 30 ngày</dt><dd>{money((quote.interest.estimated_interest as {wad?: string} | undefined)?.wad)} MyUSDT</dd></div>}
      {quote.preview.resulting_ltv_bps != null && <div><dt>LTV sau thao tác</dt><dd>{Number(quote.preview.resulting_ltv_bps)/100}%</dd></div>}
      {quote.preview.resulting_hf_wad != null && <div><dt>HF sau thao tác</dt><dd>{money(quote.preview.resulting_hf_wad)}</dd></div>}
      {quote.cid && <div><dt>CID PDF trước giao dịch</dt><dd><code>{quote.cid}</code></dd></div>}</dl>
      {quote.approvalRequired ? <><p className="form-error">Cần cấp quyền token/NFT trước khi ước lượng gas và ký thao tác chính.</p><p className="field-hint">Với trả nợ/thanh lý, cấp quyền có phần đệm nhỏ cho lãi phát sinh. Bạn sẽ xem đúng hạn mức ở báo giá cấp quyền tiếp theo.</p><button className="button primary full" onClick={() => { void client.prepareApproval().catch(() => {}); }}>Chuẩn bị cấp quyền</button></> : <button className="button primary full" disabled={state.busy} onClick={() => { void client.send().catch(() => {}); }}>Mở MetaMask để ký</button>}
      <button className="button secondary full" onClick={() => client.cancelQuote()}>Hủy thao tác</button>
    </>}
  </dialog>;
}
function WalletFeedback() {
  const { state, client } = useWallet();
  const mine = state.records.filter((r) => r.account.toLowerCase() === state.account.toLowerCase() && r.network === state.network);
  const pending = mine.find((r) => r.status === "pending");
  const last = mine.at(-1);
  const link = last ? explorerTx(last.network, last.hash) : null;
  if (state.mode !== "live") return null;
  return <div className="wallet-feedback" aria-label="Trạng thái kết nối và giao dịch">
    {state.account && state.chainId !== CHAINS[state.network] && <div className="wallet-toast error" role="alert"><p>MetaMask đang ở chain {state.chainId ?? "chưa xác định"}. Chọn Local hoặc Sepolia để tiếp tục.</p></div>}
    {state.error && <div className="wallet-toast error" role="alert"><p>{state.error}</p><button className="icon-button" aria-label="Đóng lỗi ví" onClick={() => client.dismissError()}><X size={18} /></button></div>}
    {state.busy && <div className="wallet-toast" role="status"><span className="wallet-spinner" /><p>{state.phase === "confirming" ? "Đang chờ receipt và đối chiếu với backend…" : state.phase === "signing" ? "Mở MetaMask để kiểm tra và ký giao dịch…" : state.phase === "authenticating" ? "Đang xác thực chữ ký ví…" : state.phase === "preparing" ? "Đang tạo hồ sơ / chuẩn bị báo giá…" : "Đang kết nối ví…"}</p></div>}
    {state.notice && <div className="wallet-toast" role="status">{last?.status === "failed" ? <AlertCircle size={18}/> : last?.status === "pending" ? <Clock size={18}/> : <Check size={18}/>}<div><p>{state.notice}</p>{last && <p className="wallet-hash">{link ? <a href={link} target="_blank" rel="noreferrer">Xem transaction<ExternalLink size={14} /></a> : <code>{last.hash}</code>}</p>}{last?.status === "confirmed" && last.cid && <p className="wallet-hash"><Link href={"/documents/?cid=" + encodeURIComponent(last.cid)} prefetch={false}>Mở hồ sơ theo CID</Link><code>{last.cid}</code></p>}</div><button className="icon-button" aria-label="Đóng thông báo ví" onClick={() => client.dismissNotice()}><X size={18} /></button></div>}
    {pending && !state.busy && <div className="wallet-toast"><div><p>Giao dịch đã gửi, chưa được đối chiếu: <code>{pending.hash.slice(0, 12)}…</code></p><button className="text-button" disabled={!state.session} onClick={() => { void client.retryConfirmation(pending.hash).catch(() => {}); }}>Kiểm tra lại, không gửi lại</button></div></div>}
  </div>;
}
