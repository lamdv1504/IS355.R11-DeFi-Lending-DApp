import type { Metadata } from "next";
import Link from "next/link";
import { ArrowLeft, FileQuestion, Leaf } from "lucide-react";

export const metadata: Metadata = {
  title: "Không tìm thấy trang | DeFi Lending",
  description: "Đường dẫn không tồn tại. Quay lại dashboard cho vay MyUSDT.",
};

export default function NotFound() {
  return (
    <div className="not-found-shell">
      <a className="skip-link" href="#not-found-content">Đến nội dung chính</a>
      <header className="not-found-header">
        <Link className="brand" href="/">
          <span className="brand-mark"><Leaf size={23} strokeWidth={2.3} /></span>
          <span>DeFi<span className="brand-light"> Lending</span></span>
        </Link>
      </header>
      <main id="not-found-content" className="not-found-main">
        <div className="not-found-content">
          <span className="not-found-icon"><FileQuestion size={32} aria-hidden="true" /></span>
          <p className="not-found-code">Lỗi 404</p>
          <h1>Không tìm thấy trang.</h1>
          <p>Đường dẫn này không tồn tại trong ứng dụng. Bạn có thể quay lại trang cho vay MyUSDT để tiếp tục.</p>
          <Link className="button primary" href="/"><ArrowLeft size={18} />Về trang cho vay</Link>
        </div>
      </main>
    </div>
  );
}
