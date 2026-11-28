/** L04 adapters: the backend is the authority for private document access. */
export type DocumentType = "LOAN_AGREEMENT" | "CREDIT_REPORT" | "AUDIT_LOGS";
export interface DocumentMetadata {
  cid: string; document_type: DocumentType; visibility: "PUBLIC" | "PRIVATE";
  encrypted: boolean; owner_wallet?: string | null; filename: string;
  content_type: string; plaintext_sha256: string; ciphertext_sha256?: string | null;
}
export interface HubConnection { mode: "sample" | "api"; baseUrl: string; token: string }
export interface AuditEntry {
  period: string; data_kind: "SIMULATED" | "ON_CHAIN";
  borrow_apy_percent: number; supply_apy_percent: number;
  borrow_apr_percent: number; supply_apr_percent: number; utilization_percent: number;
}
export interface RetrievedDocument {
  cid: string; bytes: Uint8Array; contentType: string; filename: string;
  sourceSha256: string; downloadSha256: string; verification: "browser" | "backend";
  json?: Record<string, unknown>;
}
export interface RateAnalyticsSnapshot {
  network: string;
  chainId: number;
  blockNumber: number;
  asOfTimestamp: number;
  series: AuditEntry[];
}
export interface WalletSnapshotResult {
  walletAddress: string;
  network: string | null;
  chainId: number | null;
  blockNumber: number | null;
  asOfTimestamp: number | null;
  rows: ReturnType<typeof walletChartData>;
}
export const DOCUMENT_LABELS: Record<DocumentType, string> = {
  LOAN_AGREEMENT: "Thỏa thuận vay", CREDIT_REPORT: "Báo cáo tín dụng", AUDIT_LOGS: "Nhật ký lãi suất",
};
export class HubError extends Error {
  readonly status: number;
  constructor(status: number, message: string) { super(message); this.name = "HubError"; this.status = status; }
}
export function errorMessage(error: unknown) {
  if (error instanceof HubError) {
    if (error.status === 401) return "Vui lòng kết nối và ký xác thực ví. Phiên hiện tại chưa được xác thực hoặc đã hết hạn.";
    if (error.status === 403) return "Không có quyền truy cập. Ví hiện tại không được phép xem hồ sơ này.";
    if (error.status === 404) return "Không tìm thấy CID trong danh mục của nguồn dữ liệu hiện tại.";
    if (error.status === 503) return "Backend hoặc dịch vụ blockchain/IPFS chưa sẵn sàng.";
  }
  return error instanceof Error ? error.message : "Không thực hiện được yêu cầu.";
}
function cidBytes(cid: string): Uint8Array {
  if (/^Qm[1-9A-HJ-NP-Za-km-z]{44}$/.test(cid)) {
    const alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";
    let value = 0n;
    for (const char of cid) value = value * 58n + BigInt(alphabet.indexOf(char));
    const hex = value.toString(16).padStart(68, "0");
    return Uint8Array.from(hex.match(/../g)!, (b) => parseInt(b, 16));
  }
  if (!/^b[a-z2-7]{10,120}$/.test(cid)) throw new HubError(422, "CID không hợp lệ. Dùng CIDv0 hoặc CIDv1 base32, không kèm đường dẫn con.");
  const alphabet = "abcdefghijklmnopqrstuvwxyz234567";
  let buffer = 0, bits = 0;
  const bytes: number[] = [];
  for (const char of cid.slice(1)) {
    buffer = (buffer << 5) | alphabet.indexOf(char); bits += 5;
    if (bits >= 8) { bits -= 8; bytes.push((buffer >>> bits) & 255); }
    buffer &= (1 << bits) - 1;
  }
  if (buffer !== 0) throw new HubError(422, "CID base32 có phần đệm không hợp lệ.");
  return Uint8Array.from(bytes);
}
export function normalizeCid(input: string) {
  let cid = input.trim();
  if (cid.startsWith("ipfs://")) cid = cid.slice(7);
  else if (/^https?:\/\//.test(cid)) {
    const url = new URL(cid);
    const match = /^\/ipfs\/([^/]+)\/?$/.exec(url.pathname);
    if (!match || url.search || url.hash || url.username || url.password) throw new HubError(422, "Link phải trỏ trực tiếp tới /ipfs/CID.");
    cid = match[1];
  }
  cid = cid.replace(/\/$/, "");
  const bytes = cidBytes(cid);
  const v0 = cid.startsWith("Qm");
  const supported = v0 ? bytes.length === 34 && bytes[0] === 18 && bytes[1] === 32
    : bytes.length === 36 && bytes[0] === 1 && [0x55, 0x70, 0x71].includes(bytes[1]) && bytes[2] === 18 && bytes[3] === 32;
  if (!supported) throw new HubError(422, "CID cần dùng SHA2-256 và codec raw, dag-pb hoặc dag-cbor.");
  return cid;
}
export function apiBase(value: string) {
  const url = new URL(value.trim());
  if (url.username || url.password || url.search || url.hash || url.pathname !== "/") throw new Error("Địa chỉ API phải là origin, ví dụ http://127.0.0.1:8000.");
  if (url.protocol !== "https:" && !(url.protocol === "http:" && ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname))) throw new Error("Dùng HTTPS hoặc HTTP localhost để bảo vệ phiên ví.");
  return url.origin;
}
export async function sha256(bytes: Uint8Array) {
  const hash = await crypto.subtle.digest("SHA-256", Uint8Array.from(bytes).buffer);
  return Array.from(new Uint8Array(hash), (v) => v.toString(16).padStart(2, "0")).join("");
}
export async function assertHash(bytes: Uint8Array, expected: string) {
  if (!/^[0-9a-f]{64}$/i.test(expected) || await sha256(bytes) !== expected.toLowerCase()) throw new HubError(409, "SHA-256 không khớp. Đã chặn xem và tải tài liệu.");
}
export function parseMetadata(value: unknown): DocumentMetadata {
  if (!value || typeof value !== "object") throw new Error("Metadata hồ sơ không hợp lệ.");
  const item = value as DocumentMetadata;
  normalizeCid(item.cid);
  if (!Object.hasOwn(DOCUMENT_LABELS, item.document_type) || !["PUBLIC", "PRIVATE"].includes(item.visibility) ||
      typeof item.filename !== "string" || typeof item.content_type !== "string" || !/^[0-9a-f]{64}$/i.test(item.plaintext_sha256)) throw new Error("Metadata hồ sơ thiếu loại, định dạng hoặc SHA-256.");
  if (item.document_type !== "AUDIT_LOGS" && (item.visibility !== "PRIVATE" || !item.encrypted)) throw new Error("Hồ sơ riêng tư phải được mã hóa.");
  return item;
}
type Fetcher = typeof fetch;
export async function apiRequest(connection: HubConnection, path: string, init: RequestInit = {}, fetcher: Fetcher = fetch) {
  const headers = new Headers(init.headers);
  if (connection.token.trim()) headers.set("Authorization", "Bearer " + connection.token.trim());
  // No wallet/role from a selector is sent as proof of authorization.
  let response: Response;
  try { response = await fetcher(apiBase(connection.baseUrl) + path, { ...init, headers, cache: "no-store", credentials: "omit", redirect: "error" }); }
  catch (error) {
    if (error instanceof Error && error.name === "AbortError") throw error;
    throw new Error("Không kết nối được API. Kiểm tra địa chỉ, CORS và trạng thái backend.");
  }
  if (!response.ok) {
    let detail = "";
    try { const data = await response.json(); detail = typeof data.detail === "string" ? data.detail : ""; } catch {}
    throw new HubError(response.status, detail || "API trả lỗi " + response.status + ".");
  }
  return response;
}
export async function listDocuments(connection: HubConnection, signal?: AbortSignal, fetcher: Fetcher = fetch) {
  const body = await (await apiRequest(connection, "/api/ipfs/documents", { signal }, fetcher)).json();
  if (!Array.isArray(body.documents)) throw new Error("API không trả danh sách hồ sơ hợp lệ.");
  return body.documents.map(parseMetadata) as DocumentMetadata[];
}
export async function decodeDocument(response: Response, cid: string, metadata?: DocumentMetadata): Promise<RetrievedDocument> {
  const bytes = new Uint8Array(await response.arrayBuffer());
  const contentType = (response.headers.get("Content-Type") || metadata?.content_type || "application/octet-stream").split(";")[0];
  const headerHash = response.headers.get("X-Content-SHA256");
  if (headerHash && metadata && headerHash !== metadata.plaintext_sha256) throw new HubError(409, "Hash của API khác metadata đã chọn.");
  const sourceHash = headerHash || metadata?.plaintext_sha256;
  if (contentType === "application/json") {
    let wrapper: Record<string, unknown>;
    try { wrapper = JSON.parse(new TextDecoder().decode(bytes)); } catch { throw new Error("API trả JSON không hợp lệ."); }
    if (wrapper.cid !== cid || !wrapper.content || typeof wrapper.content !== "object" ||
        typeof wrapper.sha256 !== "string" || !/^[0-9a-f]{64}$/i.test(wrapper.sha256)) throw new Error("Response JSON không khớp CID hoặc thiếu hash.");
    if (sourceHash && sourceHash !== wrapper.sha256) throw new HubError(409, "Hash JSON không khớp metadata.");
    // Q05 wraps parsed JSON, so the original IPFS byte serialization is unavailable.
    // The backend verifies the original hash; a downloaded JSON export has its own hash.
    if ((wrapper.content as Record<string, unknown>).document_type === "CREDIT_REPORT") creditReportView(wrapper.content as Record<string, unknown>);
    const exported = new TextEncoder().encode(JSON.stringify(wrapper.content, null, 2) + "\n");
    return { cid, bytes: exported, contentType, filename: metadata?.filename || "ipfs-document.json",
      sourceSha256: wrapper.sha256, downloadSha256: await sha256(exported), verification: "backend", json: wrapper.content as Record<string, unknown> };
  }
  if (!sourceHash) throw new HubError(409, "Thiếu SHA-256 để đối chiếu. Làm mới danh mục hồ sơ rồi thử lại.");
  await assertHash(bytes, sourceHash);
  return { cid, bytes, contentType, filename: metadata?.filename || (contentType === "application/pdf" ? "loan-agreement.pdf" : "audit-logs.csv"),
    sourceSha256: sourceHash, downloadSha256: sourceHash, verification: "browser" };
}
export async function retrieveDocument(connection: HubConnection, input: string, metadata?: DocumentMetadata, signal?: AbortSignal, fetcher: Fetcher = fetch) {
  const cid = normalizeCid(input);
  return decodeDocument(await apiRequest(connection, "/api/ipfs/documents/" + encodeURIComponent(cid) + "/retrieve", { signal }, fetcher), cid, metadata);
}
export async function retrieveSample(input: string, documents: DocumentMetadata[], signal?: AbortSignal, fetcher: Fetcher = fetch): Promise<RetrievedDocument> {
  const cid = normalizeCid(input);
  const item = documents.find((d) => d.cid === cid);
  if (!item) throw new HubError(404, "CID không có trong bộ mẫu.");
  // Private plaintext is never copied into the frontend or retrieved from a public gateway.
  if (item.visibility !== "PUBLIC") throw new HubError(401, "Hồ sơ riêng tư cần phiên backend.");
  const response = await fetcher("/l04/audit_logs_sample.json", { signal, cache: "no-store" });
  if (!response.ok) throw new HubError(response.status, "Không tải được mẫu công khai.");
  const bytes = new Uint8Array(await response.arrayBuffer());
  await assertHash(bytes, item.plaintext_sha256);
  return { cid, bytes, contentType: "application/json", filename: item.filename, sourceSha256: item.plaintext_sha256,
    downloadSha256: item.plaintext_sha256, verification: "browser", json: JSON.parse(new TextDecoder().decode(bytes)) };
}
export function auditEntries(value: unknown): AuditEntry[] {
  if (!value || typeof value !== "object" || !Array.isArray((value as { entries?: unknown }).entries)) throw new Error("Hồ sơ không chứa các kỳ nhật ký lãi suất.");
  const rows = (value as { entries: AuditEntry[] }).entries;
  const periods = new Set<string>();
  for (const row of rows) {
    if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(row.period) || periods.has(row.period) || !["SIMULATED", "ON_CHAIN"].includes(row.data_kind) ||
        [row.borrow_apy_percent, row.supply_apy_percent, row.borrow_apr_percent, row.supply_apr_percent, row.utilization_percent].some((n) => !Number.isFinite(n) || n < 0)) throw new Error("Nhật ký có kỳ, nguồn hoặc số liệu không hợp lệ.");
    periods.add(row.period);
  }
  return [...rows].sort((a, b) => a.period.localeCompare(b.period));
}
export function ratesChartData(rows: AuditEntry[]) {
  return rows.map((row) => ({ ...row,
    sampleSupply: row.data_kind === "SIMULATED" ? row.supply_apy_percent : null,
    sampleBorrow: row.data_kind === "SIMULATED" ? row.borrow_apy_percent : null,
    chainSupply: row.data_kind === "ON_CHAIN" ? row.supply_apy_percent : null,
    chainBorrow: row.data_kind === "ON_CHAIN" ? row.borrow_apy_percent : null,
  }));
}
export function walletChartData(values: { myusdt: string; collateral: string; debt: string; interest: string }) {
  const labels = { myusdt: "MyUSDT khả dụng", collateral: "Thế chấp (định giá)", debt: "Nợ gốc / DebtToken", interest: "Lãi vay tích lũy" };
  return (Object.keys(labels) as (keyof typeof labels)[]).map((key) => {
    if (!/^\d{1,78}$/.test(values[key])) throw new Error("Số dư WAD không hợp lệ.");
    return { key, name: labels[key], wad: values[key], amount: Number(BigInt(values[key]) / 10n ** 12n) / 1e6 };
  });
}
export async function fetchRateAnalytics(
  connection: HubConnection,
  seedSimulatedMonths = 6,
  signal?: AbortSignal,
  fetcher: Fetcher = fetch
): Promise<RateAnalyticsSnapshot> {
  const months = Math.max(0, Math.min(120, Math.trunc(seedSimulatedMonths)));
  const response = await apiRequest(
    connection,
    "/api/analytics/rates?seed_simulated_months=" + months,
    { signal },
    fetcher
  );
  const body = (await response.json()) as Record<string, unknown>;
  const series = auditEntries({ entries: body.series });
  return {
    network: typeof body.network === "string" ? body.network : "local",
    chainId: Number(body.chain_id ?? 0),
    blockNumber: Number(body.block_number ?? 0),
    asOfTimestamp: Number(body.as_of_timestamp ?? 0),
    series,
  };
}
export async function fetchWalletSnapshot(
  connection: HubConnection,
  address: string,
  signal?: AbortSignal,
  fetcher: Fetcher = fetch
): Promise<WalletSnapshotResult> {
  const trimmed = address.trim();
  if (!/^0x[0-9a-fA-F]{40}$/.test(trimmed)) {
    throw new Error("Nhập địa chỉ ví gồm 0x và 40 ký tự hex.");
  }
  try {
    const response = await apiRequest(
      connection,
      "/api/accounts/" + trimmed + "/snapshot",
      { signal },
      fetcher
    );
    const body = (await response.json()) as {
      wallet_address?: string;
      network?: string;
      chain_id?: number;
      block_number?: number;
      as_of_timestamp?: number;
      balances?: { myusdt?: { wad?: string }; debt_token?: { wad?: string } };
      risk?: { collateral_value?: { wad?: string } };
      interest?: { accrued?: { wad?: string } };
    };
    return {
      walletAddress: body.wallet_address || trimmed,
      network: typeof body.network === "string" ? body.network : null,
      chainId: typeof body.chain_id === "number" ? body.chain_id : null,
      blockNumber: typeof body.block_number === "number" ? body.block_number : null,
      asOfTimestamp: typeof body.as_of_timestamp === "number" ? body.as_of_timestamp : null,
      rows: walletChartData({
        myusdt: body.balances?.myusdt?.wad as string,
        collateral: body.risk?.collateral_value?.wad as string,
        debt: body.balances?.debt_token?.wad as string,
        interest: body.interest?.accrued?.wad as string,
      }),
    };
  } catch (error) {
    if (!(error instanceof HubError && error.status === 404)) throw error;
    const [balanceResponse, loanResponse] = await Promise.all([
      apiRequest(connection, "/api/accounts/" + trimmed + "/balances", { signal }, fetcher),
      apiRequest(connection, "/api/accounts/" + trimmed + "/loan", { signal }, fetcher),
    ]);
    const balanceBody = await balanceResponse.json();
    const loanBody = await loanResponse.json();
    return {
      walletAddress: loanBody.wallet_address || trimmed,
      network: typeof loanBody.network === "string" ? loanBody.network : null,
      chainId: typeof loanBody.chain_id === "number" ? loanBody.chain_id : null,
      blockNumber: typeof loanBody.block_number === "number" ? loanBody.block_number : null,
      asOfTimestamp: typeof loanBody.as_of_timestamp === "number" ? loanBody.as_of_timestamp : null,
      rows: walletChartData({
        myusdt: balanceBody.balances?.myusdt?.wad,
        collateral: loanBody.risk?.collateral_value?.wad,
        debt: balanceBody.balances?.debt_token?.wad,
        interest: loanBody.interest?.accrued?.wad,
      }),
    };
  }
}
export function safeFilename(value: string) { return value.replace(/[^\p{L}\p{N}._-]+/gu, "_").slice(0, 100) || "ipfs-document"; }
export function downloadDocument(doc: RetrievedDocument) {
  const url = URL.createObjectURL(new Blob([Uint8Array.from(doc.bytes).buffer], { type: doc.contentType }));
  const anchor = document.createElement("a");
  anchor.href = url; anchor.download = safeFilename(doc.filename); anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function creditReportView(value: Record<string, unknown>) {
  const score = value.credit_score as { score?: number; tier?: string } | undefined;
  const summary = value.summary as { total_loans?: number; repaid_on_time_count?: number; liquidation_count?: number } | undefined;
  const loans = value.loans as { loan_id: string; principal_display: string; repaid_display: string; status: string }[] | undefined;
  if (value.document_type !== "CREDIT_REPORT" || !Number.isInteger(score?.score) || score!.score! < 300 || score!.score! > 850 ||
      !summary || [summary.total_loans, summary.repaid_on_time_count, summary.liquidation_count].some((n) => !Number.isSafeInteger(n) || n! < 0) ||
      !Array.isArray(loans) || loans.some((l) => !l || typeof l.loan_id !== "string" || typeof l.status !== "string" ||
        !/^\d+(\.\d+)?$/.test(l.principal_display) || !/^\d+(\.\d+)?$/.test(l.repaid_display))) throw new Error("Báo cáo tín dụng không khớp schema H03/Q04.");
  return { score: score!.score!, tier: score?.tier || "", summary, loans };
}
