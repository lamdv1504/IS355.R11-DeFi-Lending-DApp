import type { Metadata } from "next";
import AnalyticsDashboard from "@/components/analytics-dashboard";
import "../hub.css";
export const metadata: Metadata = { title: "Phân tích lãi suất & số dư | DeFi Lending", description: "Biểu đồ APY gửi/vay theo tháng và số dư ví MyUSDT, thế chấp, nợ gốc, lãi tích lũy với nguồn dữ liệu rõ ràng." };
export default function AnalyticsPage() { return <AnalyticsDashboard />; }
