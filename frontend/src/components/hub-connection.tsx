"use client";
import { useState } from "react";
import { Settings2 } from "lucide-react";
import { apiBase, type HubConnection } from "@/lib/ipfs-hub";
import { useWallet } from "@/components/wallet-provider";

export const DEFAULT_CONNECTION: HubConnection = { mode: "sample", baseUrl: process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000", token: "" };
export function HubConnectionPanel({ value, onChange }: { value: HubConnection; onChange: (value: HubConnection) => void }) {
  const { state } = useWallet();
  const [open, setOpen] = useState(false);
  const [baseUrl, setBaseUrl] = useState(value.baseUrl);
  const [error, setError] = useState("");
  return <div className="hub-connection">
    <div className="hub-source-bar"><span><span className="small-dot" />{value.mode === "sample" ? "Mẫu cục bộ · SIMULATED" : state.network + " · " + (state.session ? "Phiên ví dùng chung" : "Khách · chưa ký xác thực")}</span><button className="text-button" aria-expanded={open} aria-controls="connection-panel" onClick={() => setOpen(!open)}><Settings2 size={17} />Đổi nguồn dữ liệu</button></div>
    {open && <form id="connection-panel" className="connection-panel" onSubmit={(event) => { event.preventDefault(); try { onChange({ mode: "api", baseUrl: apiBase(baseUrl), token: "" }); setError(""); setOpen(false); } catch (e) { setError(e instanceof Error ? e.message : "Địa chỉ không hợp lệ."); } }}>
      <div className="hub-section-heading"><div><h2>Kết nối backend</h2><p>Kết nối MetaMask và ký xác thực ở thanh trên để xem hồ sơ riêng tư. Phiên dùng chung cho cả bốn màn hình.</p></div></div>
      <div className="field"><label htmlFor="api-origin">Địa chỉ API</label><input id="api-origin" type="url" required value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} /></div>
      <p className="hub-note">Đổi API xóa phiên cũ. Không nhập khóa riêng, seed phrase hoặc token thủ công.</p>
      {error && <p className="form-error" role="alert">{error}</p>}
      <div className="hub-inline-actions"><button type="submit" className="button primary">Áp dụng kết nối</button><button type="button" className="button secondary" onClick={() => { onChange({ ...DEFAULT_CONNECTION }); setOpen(false); setError(""); }}>Dùng hồ sơ mẫu</button></div>
    </form>}
  </div>;
}
