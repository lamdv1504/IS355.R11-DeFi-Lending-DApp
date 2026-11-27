import "./borrowing.css";
import type { Metadata } from "next";
import BorrowingConsole from "@/components/borrowing-console";

export const metadata: Metadata = {
  title: "Vay thế chấp MyUSDT | DeFi Lending",
  description: "Borrowing Console mô phỏng: tài sản thế chấp, giới hạn LTV 70%, Health Factor, trả nợ và xem trước phí gas.",
};
export default function BorrowPage() { return <BorrowingConsole />; }
