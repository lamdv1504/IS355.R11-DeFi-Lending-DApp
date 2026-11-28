import type { Metadata } from "next";
import localFont from "next/font/local";
import "./globals.css";
import "./wallet.css";
import { WalletProvider } from "@/components/wallet-provider";
import { walletRegistry } from "@/lib/wallet-registry";
import type { DeploymentRegistry } from "@/lib/wallet-transactions";
import registry from "@/config/contracts.json";
import { readFileSync } from "node:fs";
import path from "node:path";
const sepolia = JSON.parse(readFileSync(path.resolve(process.cwd(), "../deployments/sepolia.json"), "utf-8")) as { contracts: Record<string, { blockNumber: number }> };
const sepoliaStartBlock = Math.min(...Object.values(sepolia.contracts).map((contract) => contract.blockNumber));

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
  description: "DeFi Lending MyUSDT: kết nối MetaMask, cho vay, thế chấp, IPFS và phân tích tài sản trên local/Sepolia.",
  robots: { index: false, follow: false },
  other: { "page-type": "software", "site-kind": "software" },
};
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="vi" data-type="software" className={beVietnam.variable}><body><WalletProvider registry={walletRegistry(registry as unknown as DeploymentRegistry, { local: 0, sepolia: sepoliaStartBlock })}>{children}</WalletProvider></body></html>;
}
