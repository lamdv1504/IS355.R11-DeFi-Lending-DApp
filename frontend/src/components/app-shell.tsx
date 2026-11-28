"use client";

import Link from "next/link";
import { useWallet, WalletToolbar } from "@/components/wallet-provider";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Activity, CircleHelp, ExternalLink, FileKey2, Landmark, LayoutDashboard, Leaf, Menu, ShieldCheck, Wallet, X } from "lucide-react";
import { shortAddress } from "@/lib/wad";

export interface DemoWalletChoice { value: string; name: string; address: string }
interface Props {
  section: "lending" | "borrowing" | "documents" | "analytics";
  statusLabel?: string;
  account: string;
  choices: DemoWalletChoice[];
  ready: boolean;
  onAccountChange: (value: string) => void;
  onHelp: () => void;
  children: ReactNode;
}
export function AppShell({ section, account, choices, ready, onAccountChange, onHelp, children, statusLabel }: Props) {
  const { state: walletState } = useWallet();
  const [menuOpen, setMenuOpen] = useState(false);
  const navigation = useRef<HTMLElement>(null);
  useEffect(() => {
    if (!menuOpen) return;
    const previous = document.activeElement as HTMLElement | null;
    const drawer = navigation.current;
    const nodes = () => Array.from(drawer?.querySelectorAll<HTMLElement>('a[href], button:not(:disabled)') ?? []);
    drawer?.querySelector<HTMLElement>("button")?.focus();
    const keydown = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); setMenuOpen(false); }
      if (event.key !== "Tab") return;
      const first = nodes()[0], last = nodes().at(-1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    };
    const resize = () => { if (window.innerWidth > 850) setMenuOpen(false); };
    drawer?.addEventListener("keydown", keydown); window.addEventListener("resize", resize);
    return () => { drawer?.removeEventListener("keydown", keydown); window.removeEventListener("resize", resize); previous?.focus(); };
  }, [menuOpen]);
  const lending = section === "lending";
  const borrowing = section === "borrowing";
  const hub = section === "documents" || section === "analytics";
  const sectionName = { lending: "Cho vay", borrowing: "Đi vay", documents: "Hồ sơ IPFS", analytics: "Phân tích" }[section];
  const close = () => setMenuOpen(false);
  return <div className={"app-shell" + (borrowing ? " borrowing-shell" : "") + (hub ? " hub-shell" : "") + (walletState.mode === "live" ? " live-shell" : "")}>
    <a className="skip-link" href="#main-content">Đến nội dung chính</a>
    {menuOpen && <button className="sidebar-backdrop" aria-label="Đóng điều hướng" onClick={close} />}
    <aside ref={navigation} style={{ overflowY: "auto" }} className={"sidebar " + (menuOpen ? "is-open" : "")} aria-label="Điều hướng ứng dụng">
      <Link className="brand" href="/" prefetch={false} onClick={close}><span className="brand-mark"><Leaf size={23} strokeWidth={2.3} /></span><span>DeFi<span className="brand-light"> Lending</span></span></Link>
      <button className="icon-button drawer-close" onClick={close} aria-label="Đóng điều hướng"><X size={20} /></button>
      <div className="workspace-label">KHÔNG GIAN TÀI SẢN</div>
      <nav className="main-nav">
        <Link href="/" prefetch={false} aria-current={lending ? "page" : undefined} onClick={close}><LayoutDashboard size={20} />Tổng quan</Link>
        <Link href="/borrow/" prefetch={false} aria-current={borrowing ? "page" : undefined} onClick={close}><Landmark size={20} />Vay thế chấp</Link>
        <Link href="/documents/" prefetch={false} aria-current={section === "documents" ? "page" : undefined} onClick={close}><FileKey2 size={20} />Hồ sơ IPFS</Link>
        <Link href="/analytics/" prefetch={false} aria-current={section === "analytics" ? "page" : undefined} onClick={close}><Activity size={20} />Phân tích</Link>
        {!hub && <a href={lending ? "#positions" : "#collateral"} onClick={close}><FileKey2 size={20} />{lending ? "NFT vị thế" : "Tài sản thế chấp"}</a>}
        {!hub && <a href={lending ? "#activity" : "#borrow-activity"} onClick={close}><Activity size={20} />Hoạt động</a>}
      </nav>
      <div className="sidebar-bottom"><div className="sidebar-note"><ShieldCheck size={22} /><p>{hub ? <>CID định danh file.<br />Phiên ví cấp quyền xem.</> : lending ? <>Quyền lợi nằm<br />trong NFT của bạn.</> : <>Chủ động theo dõi<br />sức khỏe khoản vay.</>}</p><span>{hub ? "Hồ sơ riêng tư chỉ trả bản rõ sau khi backend kiểm tra quyền." : lending ? "Chuyển NFT để chuyển quyền sở hữu vị thế cho vay." : "Giữ LTV trong hạn mức và theo dõi cảnh báo Health Factor."}</span></div><button className="help-button" disabled={!ready} onClick={() => { close(); onHelp(); }}><CircleHelp size={19} />Cách hoạt động<ExternalLink size={15} /></button><div className="sidebar-foot">IS355 · DeFi Lending DApp</div></div>
    </aside>
    <div className="workspace" inert={menuOpen || undefined}>
      <header className="topbar"><div className="topbar-left"><button className="icon-button mobile-menu" aria-label={menuOpen ? "Đóng điều hướng" : "Mở điều hướng"} aria-expanded={menuOpen} onClick={() => setMenuOpen(!menuOpen)}>{menuOpen ? <X size={22} /> : <Menu size={22} />}</button><span className="breadcrumb">Ứng dụng <span>/</span><strong>{sectionName}</strong></span></div><div className="topbar-right">{walletState.mode === "sample" && <>{choices.length > 0 && <span className="network-tag"><span />{statusLabel || "Local · mô phỏng"}</span>}{choices.length > 0 ? <div className="wallet-control"><Wallet size={18} /><label htmlFor="active-wallet">Ví demo</label><select id="active-wallet" value={account} onChange={(e) => onAccountChange(e.target.value)} disabled={!ready}>{choices.map((a) => <option key={a.value} value={a.value}>{a.name} · {shortAddress(a.address)}</option>)}</select></div> : <span className="hub-session-label"><ShieldCheck size={18} />{statusLabel || "Chỉ đọc"}</span>}</>}<WalletToolbar /></div></header>
      {children}
      <noscript><p className="noscript-message">Bật JavaScript để sử dụng dashboard DeFi Lending và kết nối MetaMask.</p></noscript>
    </div>
  </div>;
}
