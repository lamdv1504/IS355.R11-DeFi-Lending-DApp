import type { Metadata } from "next";
import localFont from "next/font/local";
import "./globals.css";

const manrope = localFont({ src: "./fonts/Manrope-Variable.ttf", variable: "--font-manrope", weight: "200 800", display: "swap" });
export const metadata: Metadata = {
  title: "Cho vay MyUSDT | DeFi Lending",
  description: "Dashboard mô phỏng cho vay MyUSDT: theo dõi lãi suất, vốn gửi, thanh khoản và NFT vị thế.",
  robots: { index: false, follow: false },
  other: { "page-type": "software", "site-kind": "software" },
};
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="vi" data-type="software" className={manrope.variable}><body>{children}</body></html>;
}
