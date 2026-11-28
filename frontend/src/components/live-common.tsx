"use client";
import { useEffect, useId, useRef, useState } from "react";
import { RefreshCw, ShieldCheck, ArrowUpRight, X } from "lucide-react";
import { useWallet } from "@/components/wallet-provider";
import { walletError } from "@/lib/wallet-client";
import { ACTION_NAMES, CHAINS, explorerTx, type Operation } from "@/lib/wallet-transactions";
import { amountLabel } from "@/lib/wad";

export function obj(value: unknown): Record<string, unknown> { return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {}; }
export function array(value: unknown): Record<string, unknown>[] { return Array.isArray(value) ? value.map(obj) : []; }
export function wad(value: unknown): string | null {
  const raw = obj(value).wad;
  return typeof raw === "string" && /^\d{1,78}$/.test(raw) ? raw : null;
}
export function money(value: string | bigint | null, decimals = 4) { return value === null ? "—" : amountLabel(value, decimals); }
export function integer(value: unknown): string {
  if (typeof value === "number" && Number.isSafeInteger(value) && value >= 0) return String(value);
  if (typeof value === "string" && /^\d+$/.test(value)) return value;
  return "";
}
export function percentage(value: unknown) { return typeof value === "number" && Number.isFinite(value) ? value.toLocaleString("vi-VN", { maximumFractionDigits: 4 }) + "%" : "—"; }
export function canTransact(state: ReturnType<typeof useWallet>["state"]) {
  return !state.busy && !!state.session && state.chainId === CHAINS[state.network];
}
export function ReadStatus({ loading, error, data }: { loading: boolean; error: string; data: Record<string, unknown> | null }) {
  const { client } = useWallet();
  return <div className={"live-read-status" + (error ? " error" : "")}>{loading ? <p role="status">Đang đọc dữ liệu backend…</p> : error ? <p role="alert">{error}{data ? " · Đang hiển thị lần đọc trước." : ""}</p> : <p><ShieldCheck size={16} />{data ? "Block #" + String(data.block_number ?? "—") + " · Làm mới mỗi 10 giây" : "Kết nối ví để đọc dữ liệu tài khoản."}</p>}<button className="icon-button" aria-label="Làm mới dữ liệu" onClick={() => client.refresh()}><RefreshCw size={18} /></button></div>;
}
export function LiveModeNotice() {
  const { state } = useWallet();
  return <div className="live-mode-notice"><span className="demo-label">KẾT NỐI THẬT</span><p>{state.network === "local" ? "Hardhat local · chain 31337" : "Sepolia · chain 11155111"} · Giao dịch chỉ được gửi sau khi bạn xác nhận trong MetaMask.</p>{!state.account && <p>Kết nối ví để xem vị thế và ký xác thực để thực hiện thao tác.</p>}{state.account && !state.session && <p>Ví đã kết nối; ký xác thực ở thanh trên để tiếp tục.</p>}</div>;
}
export function DemoToolbar() {
  const { client, state } = useWallet();
  const [error, setError] = useState("");
  const ready = canTransact(state), adminLocal = ready && state.network === "local" && state.session!.roles.includes("ADMIN");
  const prepare = (op: Operation) => { setError(""); void client.prepare(op).catch((e) => setError(walletError(e))); };
  return <section className="panel live-demo" aria-labelledby="live-demo-title"><div><p className="eyebrow">CÔNG CỤ THỬ NGHIỆM</p><h2 id="live-demo-title">Thao tác demo trên mạng đã chọn</h2></div><div className="live-demo-buttons">
    <button className="button secondary" disabled={!ready} onClick={() => prepare({ action: "FAUCET_MYUSDT", args: { amount_wad: (1000n * 10n ** 18n).toString() } })}>Nhận 1.000 MyUSDT</button>
    {[30,60].map((days) => <button key={days} className="button secondary" disabled={!adminLocal} onClick={() => { setError(""); void client.advanceTime(days as 30 | 60).catch((e) => setError(walletError(e))); }}>Tua {days} ngày</button>)}
    <button className="button secondary" disabled={!adminLocal} onClick={() => prepare({ action: "MOCK_ORACLE_MULTIPLIER", args: { multiplier_bps: 6000 } })}>Giá Oracle về 60%</button>
    <button className="button secondary" disabled={!adminLocal} onClick={() => prepare({ action: "MOCK_ORACLE_MULTIPLIER", args: { multiplier_bps: 10000 } })}>Giá Oracle 100%</button>
    </div><p className="field-hint">Faucet và đổi giá là giao dịch cần ký. Tua thời gian là RPC Hardhat có quyền Admin. Tua thời gian/đổi giá chỉ bật cho Admin trên local.</p>{error && <p className="form-error" role="alert">{error}</p>}</section>;
}
export function LiveActivity({ id = "activity" }: { id?: string }) {
  const { state, client } = useWallet();
  const records = state.records.filter((r) => r.network === state.network && r.account.toLowerCase() === state.account.toLowerCase()).slice().reverse();
  return <section className="panel live-activity" id={id} aria-labelledby={id + "-title"}><h2 id={id + "-title"}>Giao dịch trong phiên</h2>{records.length ? <ul className="live-tx-list">{records.map((r) => <li key={r.hash}><div><strong>{r.status === "confirmed" ? "Backend đã xác nhận" : r.status === "failed" ? "Giao dịch revert" : "Đã gửi · chờ đối chiếu"}</strong><span>{ACTION_NAMES[r.action]} · {r.network}{r.blockNumber !== undefined ? " · block #" + r.blockNumber : ""}</span><code>{r.hash}</code>{r.cid && <p>CID: <code>{r.cid}</code></p>}</div>{explorerTx(r.network,r.hash) && <a className="text-button" href={explorerTx(r.network,r.hash)!} target="_blank" rel="noreferrer">Xem giao dịch<ArrowUpRight size={16} /></a>}{r.status === "pending" && <button className="text-button" disabled={state.busy || !state.session} onClick={() => { void client.retryConfirmation(r.hash).catch(() => {}); }}>Kiểm tra lại</button>}</li>)}</ul> : <p className="live-empty">Chưa có giao dịch nào được gửi trong phiên này.</p>}</section>;
}

export function LiveHelp({ open, onClose }: { open: boolean; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const id = useId();
  useEffect(() => { if (open) dialog.current?.showModal(); else dialog.current?.close(); }, [open]);
  return <dialog ref={dialog} className="action-dialog" aria-labelledby={id} onCancel={onClose}><div className="dialog-top"><ShieldCheck size={24}/><button className="icon-button" aria-label="Đóng hướng dẫn" onClick={onClose}><X size={20}/></button></div><h2 id={id}>Ký ví và xác nhận giao dịch</h2><div className="help-copy"><p>Kết nối MetaMask, chọn Local hoặc Sepolia rồi ký challenge xác thực. Chữ ký xác thực không phải giao dịch và không cần gas.</p><p>Nhập thao tác để đọc báo giá từ Web3.py. Cấp quyền token/NFT và thao tác chính là hai giao dịch cần ký riêng. Chỉ ghi nhận thành công sau receipt và đối chiếu của backend.</p><p>Khi vay, PDF được tạo trước; CID chỉ được gắn với giao dịch sau xác nhận. Nếu đã có hash nhưng chưa đối chiếu được, dùng Kiểm tra lại để tránh gửi thêm giao dịch.</p><button className="button primary full" onClick={onClose}>Đã hiểu cách ký</button></div></dialog>;
}
