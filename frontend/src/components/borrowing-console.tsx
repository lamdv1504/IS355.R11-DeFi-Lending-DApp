"use client";
import dynamic from "next/dynamic";
import { useWallet } from "@/components/wallet-provider";
import LiveBorrowingConsole from "./live-borrowing-console";
const SampleBorrowingConsole = dynamic(() => import("./sample-borrowing-console"), { ssr: false, loading: () => <p className="live-empty" role="status">Đang tải dữ liệu mẫu…</p> });
export default function Page() { const wallet = useWallet(); return wallet.state.mode === "live" ? <LiveBorrowingConsole key={wallet.scopeKey}/> : <SampleBorrowingConsole/>; }
