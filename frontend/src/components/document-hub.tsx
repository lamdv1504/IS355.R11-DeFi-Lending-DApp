"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { ArrowDownToLine, ArrowUpRight, Check, Copy, FileJson, FileKey2, FileText, LockKeyhole, Plus, RefreshCw, Search, ShieldCheck, X } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { DEFAULT_CONNECTION, HubConnectionPanel } from "@/components/hub-connection";
import { apiRequest, assertHash, auditEntries, creditReportView, DOCUMENT_LABELS, downloadDocument, errorMessage, HubError, listDocuments, normalizeCid, parseMetadata, retrieveDocument, retrieveSample, type DocumentMetadata, type DocumentType, type HubConnection, type RetrievedDocument } from "@/lib/ipfs-hub";
import { parseAmount, shortAddress } from "@/lib/wad";
import samples from "@/data/l04-samples.json";

const sampleDocuments = samples.documents.map(parseMetadata);
const sampleRows = auditEntries(samples.audit);
type Filter = "ALL" | DocumentType;
const FILTERS: [Filter, string][] = [["ALL", "Tất cả"], ["LOAN_AGREEMENT", "Thỏa thuận vay"], ["CREDIT_REPORT", "Tín dụng"], ["AUDIT_LOGS", "Nhật ký"]];

export default function DocumentHub() {
  const [connection, setConnection] = useState<HubConnection>(DEFAULT_CONNECTION);
  const [documents, setDocuments] = useState<DocumentMetadata[]>(sampleDocuments);
  const [filter, setFilter] = useState<Filter>("ALL");
  const [cid, setCid] = useState("");
  const [selected, setSelected] = useState<RetrievedDocument | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [listing, setListing] = useState(false);
  const [help, setHelp] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [createType, setCreateType] = useState<DocumentType>("LOAN_AGREEMENT");
  const [principal, setPrincipal] = useState("500");
  const [description, setDescription] = useState("");
  const [wallet, setWallet] = useState("");
  const [fromBlock, setFromBlock] = useState("0");
  const request = useRef<AbortController | null>(null);
  const listRequest = useRef<AbortController | null>(null);
  const details = useRef<HTMLElement | null>(null);
  const helpRef = useRef<HTMLDialogElement | null>(null);
  useEffect(() => {
    if (help) helpRef.current?.showModal(); else helpRef.current?.close();
  }, [help]);
  useEffect(() => {
    const controller = new AbortController();
    listRequest.current = controller;
    const task = setTimeout(async () => {
      setListing(true);
      try {
        const items = connection.mode === "sample" ? sampleDocuments : await listDocuments(connection, controller.signal);
        if (!controller.signal.aborted) setDocuments(items);
      } catch (e) { if (!controller.signal.aborted) { setDocuments([]); setError(errorMessage(e)); } }
      finally { if (!controller.signal.aborted) setListing(false); }
    }, 0);
    return () => { clearTimeout(task); controller.abort(); request.current?.abort(); };
  }, [connection]);
  const changeConnection = (value: HubConnection) => {
    request.current?.abort(); listRequest.current?.abort();
    setSelected(null); setDocuments([]); setError(""); setNotice(""); setCid(""); setBusy(false); setCreateOpen(false); setConnection(value);
  };
  const refresh = async () => {
    listRequest.current?.abort();
    const controller = new AbortController(); listRequest.current = controller;
    setListing(true); setError("");
    try {
      const items = connection.mode === "sample" ? sampleDocuments : await listDocuments(connection, controller.signal);
      if (!controller.signal.aborted) setDocuments(items);
    } catch (e) { if (!controller.signal.aborted) setError(errorMessage(e)); }
    finally { if (!controller.signal.aborted) setListing(false); }
  };
  const retrieve = async (input: string) => {
    request.current?.abort();
    const controller = new AbortController(); request.current = controller;
    setBusy(true); setSelected(null); setError(""); setNotice("");
    try {
      const normalized = normalizeCid(input);
      setCid(normalized);
      const doc = connection.mode === "sample"
        ? await retrieveSample(normalized, sampleDocuments, controller.signal)
        : await retrieveDocument(connection, normalized, documents.find((d) => d.cid === normalized), controller.signal);
      if (!controller.signal.aborted) { setSelected(doc); details.current?.focus({ preventScroll: true }); }
    } catch (e) { if (!controller.signal.aborted) setError(errorMessage(e)); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  };
  const copyCid = async (value: string) => {
    try { await navigator.clipboard.writeText(value); setNotice("Đã sao chép CID."); }
    catch { setNotice("Trình duyệt chưa cho sao chép. Bạn có thể chọn và copy CID trong ô tra cứu."); setCid(value); }
  };
  const downloadCiphertext = async (item: DocumentMetadata) => {
    request.current?.abort();
    const controller = new AbortController(); request.current = controller;
    setBusy(true); setError("");
    try {
      const path = item.document_type === "LOAN_AGREEMENT" ? "loan_agreement" : "credit_report";
      const response = await fetch("/l04/" + path + "_sample.encrypted.json", { signal: controller.signal, cache: "no-store" });
      if (!response.ok) throw new HubError(response.status, "Không tải được bản mã mẫu.");
      const bytes = new Uint8Array(await response.arrayBuffer());
      await assertHash(bytes, item.ciphertext_sha256 || "");
      if (!controller.signal.aborted) {
        downloadDocument({ cid: item.cid, bytes, contentType: "application/json", filename: path + ".encrypted.json", sourceSha256: item.ciphertext_sha256!, downloadSha256: item.ciphertext_sha256!, verification: "browser" });
        setNotice("Đã tải bản mã AES-256-GCM và đối chiếu SHA-256. File không chứa khóa hoặc bản rõ.");
      }
    } catch (e) { if (!controller.signal.aborted) setError(errorMessage(e)); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  };
  const createDocument = async (event: FormEvent) => {
    event.preventDefault();
    request.current?.abort();
    const controller = new AbortController(); request.current = controller;
    setBusy(true); setSelected(null); setError(""); setNotice("");
    try {
      if (connection.mode !== "api") throw new Error("Chọn backend và phiên đã xác thực để tạo, mã hóa và lưu hồ sơ IPFS.");
      const block = Number(fromBlock);
      if (!Number.isSafeInteger(block) || block < 0 || !/^\d+$/.test(fromBlock)) throw new Error("Block bắt đầu phải là số nguyên không âm.");
      let path = "/api/ipfs/audit-logs";
      let body: Record<string, unknown> = { from_block: block, to_block: "latest", seed_simulated_months: 6 };
      if (createType === "LOAN_AGREEMENT") {
        const amount = parseAmount(principal);
        if (amount <= 0n || !description.trim()) throw new Error("Nhập số tiền vay dương và mô tả tài sản thế chấp.");
        path = "/api/ipfs/create-agreement"; body = { principal_wad: amount.toString(), asset_description: description.trim() };
      } else if (createType === "CREDIT_REPORT") {
        if (!/^0x[0-9a-fA-F]{40}$/.test(wallet.trim())) throw new Error("Địa chỉ ví phải có 0x và 40 ký tự hex.");
        path = "/api/ipfs/credit-report/" + wallet.trim(); body = { from_block: block, to_block: "latest" };
      }
      const result = await (await apiRequest(connection, path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal: controller.signal })).json();
      const createdCid = normalizeCid(createType === "AUDIT_LOGS" ? result.json?.cid : result.cid);
      if (controller.signal.aborted) return;
      setCid(createdCid); setNotice("Backend đã tạo và lưu hồ sơ IPFS. CID: " + createdCid); setCreateOpen(false);
      try {
        const items = await listDocuments(connection, controller.signal);
        if (!controller.signal.aborted) setDocuments(items);
      } catch { if (!controller.signal.aborted) setError("Hồ sơ đã được tạo, nhưng chưa làm mới được danh mục. Bấm Làm mới để thử lại."); }
    } catch (e) { if (!controller.signal.aborted) setError(errorMessage(e)); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  };
  const chosenMetadata = documents.find((d) => d.cid === cid) || sampleDocuments.find((d) => connection.mode === "sample" && d.cid === cid);
  const json = selected?.json;
  const credit = json?.document_type === "CREDIT_REPORT" ? creditReportView(json) : null;
  const rows = json?.document_type === "AUDIT_LOGS" ? (() => { try { return auditEntries(json); } catch { return []; } })() : connection.mode === "sample" ? sampleRows : [];
  return <AppShell section="documents" account="" choices={[]} ready onAccountChange={() => {}} onHelp={() => setHelp(true)} statusLabel={connection.mode === "sample" ? "Mẫu · SIMULATED" : connection.token ? "Có token phiên" : "Khách · chưa xác thực"}>
    <main id="main-content" className="hub-main">
      <div className="page-heading hub-heading" data-enter><div><div className="heading-label"><span />HỒ SƠ & CHỨNG CỨ</div><h1>Hồ sơ IPFS<span className="heading-dot">.</span></h1><p>Ba loại hồ sơ. Một mã CID để tra cứu và đối chiếu.</p></div><button className="button secondary" onClick={() => setCreateOpen(!createOpen)} aria-expanded={createOpen} disabled={busy}><Plus size={18} />Tạo & lưu IPFS</button></div>
      <HubConnectionPanel value={connection} onChange={changeConnection} />
      {createOpen && <section className="panel hub-create" aria-labelledby="create-heading"><h2 id="create-heading">Tạo hồ sơ và lưu IPFS</h2><p className="hub-note">Backend sinh file theo dữ liệu blockchain; PDF và Credit Report được mã hóa trước khi lưu. Nhật ký chỉ Admin được xuất bản.</p>
        <form onSubmit={createDocument}><div className="connection-fields"><div className="field"><label htmlFor="create-kind">Loại hồ sơ</label><select id="create-kind" value={createType} onChange={(e) => setCreateType(e.target.value as DocumentType)}>{Object.entries(DOCUMENT_LABELS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></div>
        {createType === "LOAN_AGREEMENT" ? <><div className="field"><label htmlFor="principal">Khoản vay dự kiến (MyUSDT)</label><input id="principal" inputMode="decimal" required value={principal} onChange={(e) => setPrincipal(e.target.value)} /></div><div className="field"><label htmlFor="asset-description">Mô tả tài sản thế chấp</label><input id="asset-description" maxLength={500} required value={description} onChange={(e) => setDescription(e.target.value)} /></div></> : <>{createType === "CREDIT_REPORT" && <div className="field"><label htmlFor="report-wallet">Ví chủ báo cáo</label><input id="report-wallet" required value={wallet} onChange={(e) => setWallet(e.target.value)} /></div>}<div className="field"><label htmlFor="from-block">Block bắt đầu quét sự kiện</label><input id="from-block" inputMode="numeric" required value={fromBlock} onChange={(e) => setFromBlock(e.target.value)} /></div></>}</div>
        <div className="hub-inline-actions"><button className="button primary" disabled={busy || connection.mode === "sample"}>{busy ? "Đang gửi…" : "Tạo và lưu hồ sơ"}</button><button type="button" className="button secondary" onClick={() => setCreateOpen(false)}>Đóng biểu mẫu</button></div>{connection.mode === "sample" && <p className="hub-note">Đổi nguồn sang Backend để tạo file và nhận CID thật từ dịch vụ IPFS.</p>}</form></section>}
      <form className="panel cid-search" onSubmit={(e) => { e.preventDefault(); void retrieve(cid); }} aria-label="Tra cứu hồ sơ qua CID">
        <label htmlFor="cid-input">Tra cứu CID</label><div className="cid-search-line"><Search size={20} /><input id="cid-input" value={cid} onChange={(e) => { request.current?.abort(); setBusy(false); setCid(e.target.value); setSelected(null); setError(""); }} autoComplete="off" spellCheck={false} placeholder="Dán CID hoặc ipfs://CID" required aria-invalid={!!error} aria-describedby={error ? "hub-error" : "cid-help"} /><button className="button primary" disabled={busy}>{busy ? "Đang truy xuất…" : "Tra cứu hồ sơ"}<ArrowUpRight size={17} /></button></div><p id="cid-help" className="hub-note">Nhật ký công khai có thể đọc tự do. Hồ sơ riêng tư cần phiên ví có quyền tại backend.</p>
      </form>
      {error && <div id="hub-error" className="hub-alert error" role="alert"><LockKeyhole size={20} /><p>{error}</p><button className="icon-button" aria-label="Đóng thông báo lỗi" onClick={() => setError("")}><X size={18} /></button></div>}
      {notice && <div className="hub-alert" role="status"><Check size={20} /><p>{notice}</p><button className="icon-button" aria-label="Đóng thông báo" onClick={() => setNotice("")}><X size={18} /></button></div>}
      <div className="hub-document-grid">
        <section className="panel hub-library" aria-labelledby="library-title"><div className="hub-section-heading"><div><p className="eyebrow">DANH MỤC HỒ SƠ</p><h2 id="library-title">{connection.mode === "sample" ? "Bộ hồ sơ minh họa" : "Hồ sơ được phép xem"}</h2></div><button className="icon-button" aria-label="Làm mới danh mục" disabled={listing} onClick={() => void refresh()}><RefreshCw size={18} /></button></div>
          <div className="hub-filters" role="group" aria-label="Lọc loại hồ sơ">{FILTERS.map(([value, label]) => <button key={value} aria-pressed={filter === value} onClick={() => setFilter(value)}>{label}</button>)}</div>
          <div aria-busy={listing} className="hub-document-list">{documents.filter((doc) => filter === "ALL" || doc.document_type === filter).map((doc) => <article className={"hub-document-row" + (cid === doc.cid ? " is-selected" : "")} key={doc.cid}>
            <div className="hub-doc-top"><span className="hub-file-icon">{doc.document_type === "LOAN_AGREEMENT" ? <FileText size={23} /> : <FileJson size={23} />}</span><div><h3>{DOCUMENT_LABELS[doc.document_type]}</h3><span className="hub-muted">{doc.content_type === "application/pdf" ? "PDF" : doc.content_type.includes("csv") ? "CSV" : "JSON"} · {doc.visibility === "PRIVATE" ? "Riêng tư · AES-256-GCM" : "Công khai"}</span></div><span className="hub-lock">{doc.visibility === "PRIVATE" ? <LockKeyhole size={17} /> : <ShieldCheck size={17} />}</span></div>
            <code className="hub-cid">{doc.cid}</code><div className="hub-doc-actions"><button className="text-button" onClick={() => void retrieve(doc.cid)} disabled={busy}>Xem hồ sơ<ArrowUpRight size={15} /></button><button className="icon-button" aria-label={"Sao chép CID " + DOCUMENT_LABELS[doc.document_type]} onClick={() => void copyCid(doc.cid)}><Copy size={17} /></button></div>
          </article>)}{listing && <p className="hub-empty" role="status">Đang tải danh mục từ backend…</p>}{!listing && !documents.some((d) => filter === "ALL" || d.document_type === filter) && <p className="hub-empty">Chưa có hồ sơ thuộc loại này trong quyền xem của phiên hiện tại.</p>}</div>
        </section>
        <section className="panel hub-preview" ref={details} tabIndex={-1} aria-labelledby="preview-title"><div className="hub-section-heading"><div><p className="eyebrow">TRUY XUẤT & TOÀN VẸN</p><h2 id="preview-title">{selected ? "Hồ sơ đã truy xuất" : "Chi tiết hồ sơ"}</h2></div><FileKey2 size={22} /></div>
          {chosenMetadata && <dl className="hub-metadata"><div><dt>Loại hồ sơ</dt><dd>{DOCUMENT_LABELS[chosenMetadata.document_type]}</dd></div><div><dt>Quyền truy cập</dt><dd>{chosenMetadata.visibility === "PRIVATE" ? "Chính chủ / Admin" : "Công khai"}</dd></div>{chosenMetadata.owner_wallet && <div><dt>Ví chủ hồ sơ</dt><dd title={chosenMetadata.owner_wallet}>{shortAddress(chosenMetadata.owner_wallet)}</dd></div>}<div><dt>SHA-256 bản gốc</dt><dd><code>{chosenMetadata.plaintext_sha256}</code></dd></div></dl>}
          {selected ? <><div className="hub-integrity"><ShieldCheck size={20} /><span>{selected.verification === "browser" ? "SHA-256 khớp tại trình duyệt" : "SHA-256 bản gốc do backend xác minh"}</span></div>
            {credit && <div className="hub-credit-summary"><span>Điểm tín dụng tham khảo · {credit.tier}</span><strong>{credit.score}<small>/ 850</small></strong><p>{String(json?.data_kind ?? "")} · {credit.summary.total_loans} khoản vay · {credit.summary.repaid_on_time_count} lần trả đúng hạn · {credit.summary.liquidation_count} lần thanh lý</p><ul className="hub-credit-history">{credit.loans.map((loan) => <li key={loan.loan_id}><strong>{loan.loan_id}</strong><span>{loan.status}</span><p>Gốc {loan.principal_display} · Đã trả {loan.repaid_display} MyUSDT</p></li>)}</ul></div>}
            {selected.contentType === "application/pdf" ? <div className="hub-pdf-summary"><FileText size={42} /><h3>Thỏa thuận vay PDF</h3><p>{selected.bytes.length.toLocaleString("vi-VN")} byte · bản rõ sau kiểm tra quyền.</p></div> : <pre className="hub-json" aria-label="Nội dung hồ sơ JSON hoặc CSV" tabIndex={0}>{new TextDecoder().decode(selected.bytes)}</pre>}
            <button className="button primary full" onClick={() => downloadDocument(selected)}><ArrowDownToLine size={18} />{selected.contentType === "application/pdf" ? "Tải về PDF từ IPFS" : "Tải hồ sơ JSON / CSV"}</button>
            {selected.verification === "backend" && <p className="hub-note">JSON tải về được xuất lại từ nội dung API, có hash file riêng: <code>{selected.downloadSha256}</code></p>}
          </> : <div className="hub-preview-empty"><div className="hub-vault"><LockKeyhole size={38} /></div><h3>{busy ? "Đang kiểm tra hồ sơ" : "Chọn hồ sơ hoặc dán CID"}</h3><p>File riêng tư chỉ hiển thị sau khi máy chủ kiểm tra phiên ví và quyền sở hữu. CID không cấp quyền giải mã.</p><div className="hub-access-steps"><span><span>01</span>Tra cứu CID</span><span><span>02</span>Kiểm tra quyền</span><span><span>03</span>Đối chiếu hash</span></div></div>}
          {connection.mode === "sample" && chosenMetadata?.visibility === "PRIVATE" && <button className="button secondary full" disabled={busy} onClick={() => void downloadCiphertext(chosenMetadata)}><ArrowDownToLine size={18} />Tải bản mã mẫu</button>}
        </section>
      </div>
      <section className="panel hub-audit" aria-labelledby="audit-title"><div className="hub-section-heading"><div><p className="eyebrow">AUDIT LOGS · KHÔNG CHỨA PII</p><h2 id="audit-title">Nhật ký lãi suất hàng tháng</h2></div><Link className="text-button" href="/analytics/" prefetch={false}>Mở biểu đồ<ArrowUpRight size={17} /></Link></div>
        {rows.length ? <div className="hub-table-scroll" tabIndex={0} role="region" aria-label="Bảng số liệu hồ sơ"><table><caption className="sr-only">Lãi suất vay/gửi theo tháng, phân biệt nguồn mô phỏng và on-chain</caption><thead><tr><th>Kỳ</th><th>APY gửi</th><th>APY vay</th><th>Sử dụng vốn</th><th>Nguồn</th></tr></thead><tbody>{rows.map((row) => <tr key={row.period}><td data-label="Kỳ">{row.period}</td><td data-label="APY gửi">{row.supply_apy_percent.toLocaleString("vi-VN")}%</td><td data-label="APY vay">{row.borrow_apy_percent.toLocaleString("vi-VN")}%</td><td data-label="Sử dụng vốn">{row.utilization_percent.toLocaleString("vi-VN")}%</td><td data-label="Nguồn"><span className="hub-provenance">{row.data_kind}</span></td></tr>)}</tbody></table></div> : <p className="hub-empty">Truy xuất một Audit Logs JSON để xem dữ liệu từng tháng.</p>}
        <p className="hub-note">APY ghép lãi hằng ngày chỉ để tham khảo; hợp đồng tính lãi đơn theo APR/timestamp. Nguồn cục bộ chưa ghim lên gateway công khai.</p>
      </section>
      <footer className="app-footer"><span>IS355 · Hồ sơ IPFS & quyền truy cập</span><span>{connection.mode === "sample" ? "SIMULATED · H03 local store" : "Nguồn: Q05 backend"}</span></footer>
    </main>
    <dialog className="action-dialog" ref={helpRef} onCancel={() => setHelp(false)} onClose={() => setHelp(false)}><div className="dialog-top"><ShieldCheck size={25} /><button className="icon-button" aria-label="Đóng hướng dẫn" onClick={() => setHelp(false)}><X size={20} /></button></div><h2>Quyền xem hồ sơ</h2><div className="help-copy"><p>Loan Agreement và Credit Report được mã hóa AES-256-GCM. Khách chưa xác thực nhận 401; ví khác hoặc Lender nhận 403; chính chủ và Admin được truy xuất qua backend.</p><p>Nhật ký lãi suất chỉ có số liệu tổng hợp công khai. Bộ mẫu không cấp quyền giả lập để xem bản rõ; nút tải bản mã giúp kiểm tra dữ liệu lưu trên IPFS.</p><button className="button primary full" onClick={() => setHelp(false)}>Đã hiểu cách tra cứu</button></div></dialog>
  </AppShell>;
}
