"use client";
import dynamic from "next/dynamic";
import { useWallet } from "@/components/wallet-provider";
import LiveLendingDashboard from "./live-lending-dashboard";
const SampleLendingDashboard = dynamic(() => import("./sample-lending-dashboard"), { ssr: false, loading: () => <p className="live-empty" role="status">Đang tải dữ liệu mẫu…</p> });
export default function Page() { const wallet = useWallet(); return wallet.state.mode === "live" ? <LiveLendingDashboard key={wallet.scopeKey}/> : <SampleLendingDashboard/>; }
