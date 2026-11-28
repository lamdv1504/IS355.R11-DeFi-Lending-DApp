"use client";
import { useState } from "react";
import { Settings2 } from "lucide-react";
import { apiBase, type HubConnection } from "@/lib/ipfs-hub";

export const DEFAULT_CONNECTION: HubConnection = { mode: "sample", baseUrl: process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000", token: "" };
export function HubConnectionPanel({ value, onChange }: { value: HubConnection; onChange: (value: HubConnection) => void }) {
  const [open, setOpen] = useState(false);
  const [baseUrl, setBaseUrl] = useState(value.baseUrl);
  const [token, setToken] = useState("");
  const [error, setError] = useState("");
  return <div className="hub-connection">
    <div className="hub-source-bar"><span><span className="small-dot" />{value.mode === "sample" ? "Mẫu cục bộ · SIMULATED" : "Backend · kiểm tra quyền tại máy chủ"}</span><button className="text-button" aria-expanded={open} aria-controls="connection-panel" onClick={() => setOpen(!open)}><Settings2 size={17} />Đổi nguồn dữ liệu</button></div>
    {open && <form id="connection-panel" className="connection-panel" onSubmit={(event) => { event.preventDefault(); try { onChange({ mode: "api", baseUrl: apiBase(baseUrl), token }); setToken(""); setError(""); setOpen(false); } catch (e) { setError(e instanceof Error ? e.message : "Địa chỉ không hợp lệ."); } }}>
      <div className="hub-section-heading"><div><h2>Kết nối backend</h2><p>Dùng phiên ví đã ký xác thực để truy cập hồ sơ riêng tư.</p></div></div>
      <div className="connection-fields"><div className="field"><label htmlFor="api-origin">Địa chỉ API</label><input id="api-origin" type="url" required value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} /></div><div className="field"><label htmlFor="api-token">Token phiên ví (để trống với khách)</label><input id="api-token" type="password" autoComplete="off" value={token} onChange={(e) => setToken(e.target.value)} aria-describedby="token-note" /></div></div>
      <p id="token-note" className="hub-note">Token chỉ giữ trong bộ nhớ của trang, không lưu vào trình duyệt. Không nhập khóa riêng hoặc seed phrase.</p>
      {error && <p className="form-error" role="alert">{error}</p>}
      <div className="hub-inline-actions"><button type="submit" className="button primary">Áp dụng kết nối</button><button type="button" className="button secondary" onClick={() => { onChange({ ...DEFAULT_CONNECTION }); setToken(""); setOpen(false); setError(""); }}>Dùng hồ sơ mẫu</button></div>
    </form>}
  </div>;
}
