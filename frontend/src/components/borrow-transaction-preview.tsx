"use client";

import { useEffect, useId, useRef, useState } from "react";
import { ArrowRight, Check, CircleAlert, Fuel, ShieldCheck, X } from "lucide-react";
import { actionLabel, approvalAmount, BORROW_WALLETS, collateralValue, currentBorrowApr, formatHealthFactor, gasIllustration, healthFactor, ltvBps, prepareBorrowTransaction, referenceApy, totalDebt, YEAR_SECONDS, type BorrowState, type TransactionAction } from "@/lib/borrowing-demo";
import { amountLabel, exactAmount, parseAmount, shortAddress, WAD } from "@/lib/lending-demo";

const pct = (n: number) => new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 2 }).format(n);
interface PreviewProps {
  state: BorrowState; action: TransactionAction; gwei: string;
  onGweiChange?: (value: string) => void; compact?: boolean;
}
export function TransactionFacts({ state, action, gwei, onGweiChange, compact = false }: PreviewProps) {
  const hintId = useId();
  let view: ReturnType<typeof prepareBorrowTransaction> | undefined;
  let error = "";
  try { view = prepareBorrowTransaction(state, action, gwei); }
  catch (e) { error = e instanceof Error ? e.message : "Không thể chuẩn bị giao dịch."; }
  let gasError = "";
  try { gasIllustration(action.kind, gwei); } catch (e) { gasError = e instanceof Error ? e.message : "Giá gas không hợp lệ."; }
  const after = view?.after;
  const futureInterest = after ? BigInt(after.loan.principalWad) * (WAD * BigInt(currentBorrowApr(after)) * 30n * 86400n / (YEAR_SECONDS * 10000n)) / WAD : 0n;
  return <div className="transaction-facts">
    {onGweiChange && <div className="gas-assumption"><label htmlFor={hintId + "-gwei"}>Giá gas giả định</label><div><input id={hintId + "-gwei"} value={gwei} onChange={(e) => onGweiChange(e.target.value)} inputMode="decimal" autoComplete="off" aria-invalid={!!gasError} aria-describedby={gasError ? hintId + "-gas-error" : hintId} /><span>gwei</span></div></div>}
    {onGweiChange && gasError && <p className="form-error" role="alert" id={hintId + "-gas-error"}>{gasError}</p>}
    <dl className="preview-rows">
      {!compact && <div><dt>Thao tác</dt><dd>{actionLabel[action.kind]}</dd></div>}
      {!compact && <div><dt>Ví thực hiện</dt><dd>{shortAddress(BORROW_WALLETS.find((w) => w.id === action.actor)!.address)}</dd></div>}
      {action.kind === "borrow" && <div><dt>DebtToken dự kiến mint</dt><dd>{view ? amountLabel(BigInt(after!.loan.principalWad) - BigInt(state.loan.principalWad), 6) : "—"}</dd></div>}
      {view && view.payment > 0n && <div><dt>MyUSDT dự kiến chi</dt><dd>{amountLabel(view.payment, 8)}</dd></div>}
      {after && !["approve", "approve-nft"].includes(action.kind) && <>
        <div><dt>Tổng nợ sau thao tác</dt><dd>{amountLabel(totalDebt(after), 8)} <small>MyUSDT</small></dd></div>
        <div><dt>LTV sau thao tác</dt><dd>{pct(Number(ltvBps(after)) / 100)}%</dd></div>
        <div><dt>HF sau thao tác</dt><dd>{formatHealthFactor(healthFactor(collateralValue(after), totalDebt(after)))}</dd></div>
      </>}
      {!compact && <div><dt>Borrow APR hiện tại</dt><dd>{pct(currentBorrowApr(state) / 100)}% / năm</dd></div>}
      {after && <div><dt>Borrow APR sau thao tác</dt><dd>{pct(currentBorrowApr(after) / 100)}% / năm</dd></div>}
      <div><dt>APY tham khảo sau thao tác</dt><dd>{after ? pct(referenceApy(currentBorrowApr(after))) : "—"}%</dd></div>
      {after && <div><dt>Lãi tăng thêm sau 30 ngày</dt><dd>{amountLabel(futureInterest, 8)} <small>MyUSDT</small></dd></div>}
      <div className="preview-gas"><dt><Fuel size={15} />Phí gas minh họa</dt><dd>{view ? view.gas.feeEth : "—"} <small>ETH</small></dd></div>
      {!compact && view && <><div><dt>Gas units / giá gas</dt><dd>{view.gas.units.toLocaleString("vi-VN")} / {gwei} <small>gwei</small></dd></div><div><dt>Giới hạn gas (+20%)</dt><dd>{view.gas.gasLimit.toLocaleString("vi-VN")}</dd></div><div><dt>Phí tối đa theo giả định</dt><dd>{view.gas.maximumEth} <small>ETH</small></dd></div></>}
    </dl>
    {compact && view && <details className="gas-details"><summary>Chi tiết phí gas và giả định</summary><dl className="preview-rows"><div><dt>Gas units / giá gas</dt><dd>{view.gas.units.toLocaleString("vi-VN")} / {gwei} gwei</dd></div><div><dt>Giới hạn gas (+20%)</dt><dd>{view.gas.gasLimit.toLocaleString("vi-VN")}</dd></div><div><dt>Phí tối đa theo giả định</dt><dd>{view.gas.maximumEth} ETH</dd></div></dl></details>}
    <p id={hintId} className="quote-source">Gas tính từ tham số mô phỏng, chưa lấy estimateGas từ RPC. Không trừ ETH và không mở MetaMask.</p>
    <p className="quote-source">APR dùng tính lãi theo giây. APY tham khảo giả định tái đầu tư hằng ngày, không phải cách khoản vay tích lãi. Dự phóng 30 ngày giả định APR giữ nguyên.</p>
    {error && (!onGweiChange || error !== gasError) && <p className="form-error" role="alert">{error}</p>}
  </div>;
}
interface ControlsProps extends PreviewProps {
  ready: boolean;
  onReview: (action: TransactionAction) => void;
}
export function TransactionPreview({ state, action, gwei, onGweiChange, ready, onReview }: ControlsProps) {
  let view: ReturnType<typeof prepareBorrowTransaction> | undefined;
  try { view = prepareBorrowTransaction(state, action, gwei); } catch { /* TransactionFacts explains the validation error. */ }
  const blocked = !view || !ready;
  return <section className="transaction-preview" aria-labelledby="preview-heading">
    <div className="preview-heading"><ShieldCheck size={20} /><div><h3 id="preview-heading">Xem trước giao dịch</h3><p>Kiểm tra phí và sức khỏe khoản vay.</p></div></div>
    <TransactionFacts state={state} action={action} gwei={gwei} onGweiChange={onGweiChange} compact />
    {view?.needsApproval && <div className="approval-step"><p>Cần cấp quyền chi MyUSDT trước. Hạn mức hiển thị gồm dư địa nhỏ cho lãi phát sinh.</p><button className="button secondary full" disabled={blocked} onClick={() => onReview({ kind: "approve", actor: action.actor, amount: exactAmount(approvalAmount(view.payment)) })}>Xem trước cấp quyền</button></div>}
    {view?.needsNftApproval && <button className="button secondary full" disabled={blocked} onClick={() => onReview({ kind: "approve-nft", actor: action.actor })}>Xem trước cấp quyền NFT</button>}
    <button className="button primary full" disabled={blocked || view?.needsApproval || view?.needsNftApproval} onClick={() => onReview(action)}>{action.kind === "borrow" ? "Xem trước khoản vay" : "Xem trước trả nợ"}<ArrowRight size={17} /></button>
  </section>;
}
interface ReviewProps extends PreviewProps { onClose: () => void; onConfirm: (action: TransactionAction) => void }
export function BorrowReviewDialog({ state, action, gwei, onClose, onConfirm }: ReviewProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const [error, setError] = useState("");
  useEffect(() => { const dialog = ref.current; dialog?.showModal(); return () => { if (dialog?.open) dialog.close(); }; }, []);
  function confirm() {
    try { onConfirm(action); onClose(); }
    catch (e) { setError(e instanceof Error ? e.message : "Chưa thực hiện được thao tác."); }
  }
  let valid = false;
  try { const view = prepareBorrowTransaction(state, action, gwei); valid = !view.needsApproval && !view.needsNftApproval; } catch { /* Rendered below. */ }
  return <dialog ref={ref} className="action-dialog borrow-review" aria-labelledby="review-title" onCancel={onClose} onClose={(e) => { if (!e.currentTarget.open) onClose(); }}>
    <div className="dialog-top"><span className="dialog-symbol"><ShieldCheck /></span><button className="icon-button" aria-label="Đóng xem trước" onClick={onClose}><X size={20} /></button></div>
    <h2 id="review-title">{actionLabel[action.kind]}</h2><p className="dialog-description">Xác nhận thao tác trên dữ liệu mô phỏng.</p>
    {action.kind === "approve" && <p className="approval-summary">Hạn mức cấp quyền: <strong>{amountLabel(parseAmount(action.amount), 6)} MyUSDT</strong></p>}
    <TransactionFacts state={state} action={action} gwei={gwei} />
    {action.kind === "liquidate" && <p className="liquidation-disclosure"><CircleAlert size={18} />Ví thanh lý trả toàn bộ nợ. {state.loan.kind === "nft" ? "Toàn bộ NFT #7 chuyển sang ví thanh lý." : "Token bị thu giữ tối đa theo nợ cộng thưởng 5%; phần còn lại trả cho người vay."}</p>}
    {error && <p role="alert" className="form-error">{error}</p>}
    <p className="simulation-note"><Check size={16} />Chỉ mô phỏng, không gửi giao dịch blockchain.</p>
    <div className="dialog-actions"><button className="button secondary" onClick={onClose}>Quay lại</button><button className="button primary" disabled={!valid} onClick={confirm}>Xác nhận mô phỏng</button></div>
  </dialog>;
}
export function BorrowInfoDialog({ kind, onClose, onReset }: { kind: "help" | "reset"; onClose: () => void; onReset: (empty: boolean) => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => { const d = ref.current; d?.showModal(); return () => { if (d?.open) d.close(); }; }, []);
  return <dialog ref={ref} className="action-dialog" aria-labelledby="borrow-info-title" onCancel={onClose} onClose={(e) => { if (!e.currentTarget.open) onClose(); }}>
    <div className="dialog-top"><span className="dialog-symbol"><ShieldCheck /></span><button className="icon-button" aria-label="Đóng hộp thoại" onClick={onClose}><X size={20} /></button></div>
    <h2 id="borrow-info-title">{kind === "help" ? "Cách hoạt động" : "Đặt lại mô phỏng?"}</h2>
    <div className="help-copy">{kind === "help" ? <>
      <p>Thế chấp Token hoặc NFT, sau đó vay MyUSDT trong giới hạn 70% giá trị tài sản. Tổng nợ gồm gốc và lãi phát sinh.</p>
      <h3>Đọc Health Factor</h3><p>HF từ 1,5: an toàn. Từ 1 đến dưới 1,5: cần theo dõi. Dưới 1: đủ điều kiện thanh lý. Không có nợ: HF vô hạn.</p>
      <h3>Thanh lý cần xác nhận</h3><p>Giảm giá không tự thanh lý khoản vay. Chọn ví thanh lý, cấp quyền chi MyUSDT rồi kiểm tra và xác nhận riêng.</p>
      <p>Tất cả số liệu, gas, cấp quyền và thao tác ở đây đều mô phỏng trên trình duyệt. Không ký ví thật hoặc tạo CID/txHash. Phiên mô phỏng này tách riêng màn hình cho vay.</p>
      <button className="button primary full" onClick={onClose}>Đã hiểu</button>
    </> : <><p>Thay toàn bộ dữ liệu L03 hiện tại bằng một trong hai kịch bản. Dữ liệu màn hình cho vay L02 được giữ nguyên.</p><button className="button primary full" onClick={() => { onReset(false); onClose(); }}>Bắt đầu với khoản vay 500</button><button className="button secondary full" onClick={() => { onReset(true); onClose(); }}>Bắt đầu chưa thế chấp</button></>}</div>
  </dialog>;
}
