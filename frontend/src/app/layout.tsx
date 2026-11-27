import type { Metadata } from "next";
import localFont from "next/font/local";
import "./globals.css";

const beVietnam = localFont({
  src: [
    { path: "./fonts/BeVietnamPro-400.woff", weight: "400", style: "normal" },
    { path: "./fonts/BeVietnamPro-500.woff", weight: "500", style: "normal" },
    { path: "./fonts/BeVietnamPro-600.woff", weight: "600", style: "normal" },
    { path: "./fonts/BeVietnamPro-700.woff", weight: "700", style: "normal" },
  ],
  variable: "--font-be-vietnam",
  display: "swap",
});
export const metadata: Metadata = {
  title: "Cho vay MyUSDT | DeFi Lending",
  description: "Dashboard mô phỏng cho vay MyUSDT: theo dõi lãi suất, vốn gửi, thanh khoản và NFT vị thế.",
  robots: { index: false, follow: false },
  other: { "page-type": "software", "site-kind": "software" },
};
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="vi" data-type="software" className={beVietnam.variable}><body>{children}</body></html>;
}
