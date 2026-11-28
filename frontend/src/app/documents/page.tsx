import type { Metadata } from "next";
import DocumentHub from "@/components/document-hub";
import "../hub.css";
export const metadata: Metadata = { title: "Hồ sơ IPFS | DeFi Lending", description: "Tra cứu hồ sơ vay, báo cáo tín dụng và nhật ký lãi suất qua CID, với quyền truy cập được kiểm tra tại backend." };
export default function DocumentsPage() { return <DocumentHub />; }
