"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowDownToLine, ArrowUpFromLine, Check, Send, X } from "lucide-react";
import { ACCOUNTS, amountLabel, applyDemoAction, exactAmount, ownedPositions, shortAddress, withdrawLimit, type DemoAction, type DemoState } from "@/lib/lending-demo";

export type DialogKind = "supply" | "withdraw" | "transfer" | "reset" | "help";
interface Props {
  kind: DialogKind;
  state: DemoState;
  actor: string;
  positionId?: string;
  onClose: () => void;
  onSubmit: (action: DemoAction) => void;
  onReset: () => void;
}
export function ActionDialog({ kind, state, actor, positionId, onClose, onSubmit, onReset }: Props) {
  const ref = useRef<HTMLDialogElement>(null);
  const [amount, setAmount] = useState("");
  const [recipient, setRecipient] = useState("");
  const [selected, setSelected] = useState(positionId ?? ownedPositions(state, actor)[0]?.id ?? "");
  const [error, setError] = useState("");
  const [review, setReview] = useState(false);
  const live = state;
  const positions = ownedPositions(live, actor);
  const position = positions.find((p) => p.id === selected);
  const maximum = kind === "supply" ? BigInt(live.balances[actor]) : position ? withdrawLimit(live, position) : 0n;
  const titles = { supply: "Gửi MyUSDT", withdraw: "Rút MyUSDT", transfer: "Chuyển NFT vị thế", reset: "Đặt lại dữ liệu?", help: "Cách hoạt động" };
  useEffect(() => {
    const dialog = ref.current;
    dialog?.showModal();
    return () => { if (dialog?.open) dialog.close(); };
  }, []);
  function buildAction(): DemoAction {
    if (kind === "supply") return { kind, actor, amount };
    if (kind === "withdraw") return { kind, actor, amount, positionId: selected };
    return { kind: "transfer", actor, recipient: recipient.trim(), positionId: selected };
  }
  function submit(event: React.SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      const action = buildAction();
      applyDemoAction(state, action, Date.now());
      if (!review) { setReview(true); setError(""); return; }
      onSubmit(action); onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Chưa thực hiện được thao tác. Vui lòng thử lại.");
      setReview(false);
    }
  }
  return <dialog ref={ref} className="action-dialog" aria-labelledby="dialog-title" onClose={(event) => { if (!event.currentTarget.open) onClose(); }} onCancel={onClose}>
    <div className="dialog-top"><span className="dialog-symbol">{kind === "supply" ? <ArrowDownToLine /> : kind === "withdraw" ? <ArrowUpFromLine /> : <Send />}</span><button type="button" className="icon-button" onClick={onClose} aria-label="Đóng hộp thoại"><X size={20} /></button></div>
    <h2 id="dialog-title">{titles[kind]}</h2>
    {kind === "help" ? <div className="help-copy">
      <p>Đây là bản mô phỏng trên trình duyệt. Chưa kết nối ví thật, API hoặc LendingPool; các thao tác không gửi giao dịch blockchain.</p>
      <h3>Lãi suất và tiền lãi</h3><p>APR dùng để tính lãi trên vốn gốc theo thời gian. APY tham khảo giả định tái đầu tư hằng ngày. Lãi suất thay đổi theo tỷ lệ sử dụng Pool.</p>
      <h3>Rút tiền và chuyển NFT</h3><p>Chỉ chủ sở hữu hiện tại được rút. Số tiền rút không vượt quyền lợi của NFT và thanh khoản khả dụng. Chuyển NFT sẽ chuyển cả vốn gốc và lãi cho ví nhận.</p>
      <p>Chuyển sang ví trải nghiệm B để kiểm tra NFT được nhận. Dữ liệu được lưu trong trình duyệt này.</p>
      <button className="button primary full" onClick={onClose}>Đã hiểu</button>
    </div> : kind === "reset" ? <div className="help-copy"><p>Tất cả lần gửi, rút và chuyển NFT trong phiên mô phỏng này sẽ được thay bằng dữ liệu ban đầu.</p><div className="dialog-actions"><button className="button secondary" onClick={onClose}>Giữ dữ liệu</button><button className="button primary" onClick={() => { onReset(); onClose(); }}>Đặt lại mô phỏng</button></div></div> :
    <form onSubmit={submit} noValidate>
      <p className="dialog-description">{review ? "Kiểm tra thông tin trước khi xác nhận." : kind === "transfer" ? "Ví nhận sẽ sở hữu toàn bộ vốn gốc và lãi của NFT." : kind === "supply" ? "Mỗi lần gửi tạo một NFT ghi nhận vị thế mới." : "Rút từ NFT do ví hiện tại sở hữu."}</p>
      <div className="wallet-line"><span>Ví thực hiện</span><strong>{shortAddress(actor)}</strong></div>
      {kind !== "supply" && <div className="field"><label htmlFor="position-select">NFT vị thế</label><select id="position-select" value={selected} disabled={review} onChange={(e) => { setSelected(e.target.value); setAmount(""); setError(""); }}>
        {positions.map((p) => <option key={p.id} value={p.id}>NFT #{p.id} · {amountLabel(BigInt(p.principalWad) + BigInt(p.interestWad))} MyUSDT</option>)}
      </select></div>}
      {kind === "transfer" ? <div className="field"><label htmlFor="recipient">Địa chỉ ví nhận</label><input id="recipient" value={recipient} onChange={(e) => { setRecipient(e.target.value); setError(""); }} placeholder="0x…" autoComplete="off" spellCheck={false} disabled={review} aria-invalid={!!error} aria-describedby={error ? "action-error" : "transfer-hint"} />
        <p id="transfer-hint" className="field-hint">Hãy kiểm tra kỹ địa chỉ. Chuyển NFT đồng nghĩa chuyển quyền rút.</p>
        {!review && <button className="text-button" type="button" onClick={() => setRecipient(ACCOUNTS.find((a) => a.address !== actor)!.address)}>Dùng địa chỉ ví trải nghiệm {actor === ACCOUNTS[0].address ? "B" : "A"}</button>}
      </div> : <div className="field"><label htmlFor="amount">Số tiền MyUSDT</label><div className="amount-input"><input id="amount" value={amount} onChange={(e) => { setAmount(e.target.value); setError(""); }} inputMode="decimal" placeholder="0,00" autoComplete="off" disabled={review} aria-invalid={!!error} aria-describedby={error ? "action-error" : "amount-hint"} /><button type="button" disabled={review || maximum === 0n} onClick={() => { setAmount(exactAmount(maximum)); setError(""); }}>Tối đa</button></div>
        <p id="amount-hint" className="field-hint">{kind === "supply" ? "Số dư ví: " : "Có thể rút lúc này: "}{amountLabel(maximum, 8)} MyUSDT</p>
      </div>}
      {kind === "withdraw" && <div className="soft-note">Thanh khoản Pool: <strong>{amountLabel(live.availableLiquidityWad)} MyUSDT</strong>. Khi rút hết quyền lợi, NFT được đóng.</div>}
      {error && <p id="action-error" role="alert" className="form-error">{error}</p>}
      <p className="simulation-note"><Check size={16} /> Chỉ mô phỏng, không sử dụng tiền thật.</p>
      <div className="dialog-actions">{review && <button type="button" className="button secondary" onClick={() => setReview(false)}>Chỉnh sửa</button>}<button className="button primary" type="submit" disabled={kind !== "supply" && !position}>{review ? "Xác nhận mô phỏng" : "Kiểm tra thông tin"}</button></div>
    </form>}
  </dialog>;
}
