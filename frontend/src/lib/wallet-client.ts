import { hexlify, toUtf8Bytes, verifyMessage } from "ethers";
import { apiBase, apiRequest, HubError, normalizeCid, type HubConnection } from "./ipfs-hub.ts";
import { CHAINS, address, expectedCall, object, same, uint, validatePrepared, type DeploymentRegistry, type NetworkId, type Operation, type Prepared } from "./wallet-transactions.ts";

export interface Eip1193Provider {
  request(args: { method: string; params?: unknown[] | Record<string, unknown> }): Promise<unknown>;
  on?(event: string, listener: (value: unknown) => void): void;
  removeListener?(event: string, listener: (value: unknown) => void): void;
}
export interface WalletSession { token: string; account: string; chainId: number; expiresAt: number; roles: string[] }
export interface TxRecord {
  hash: string; intentId: string; apiOrigin: string; network: NetworkId; account: string; action: Operation["action"]; cid?: string; amountWad?: string;
  status: "pending" | "confirmed" | "failed"; blockNumber?: number;
}
export interface WalletState {
  mode: "live" | "sample"; baseUrl: string; network: NetworkId; account: string; chainId: number | null;
  session: WalletSession | null; epoch: number; revision: number; busy: boolean;
  phase: "idle" | "connecting" | "authenticating" | "preparing" | "review" | "signing" | "confirming";
  quote: Prepared | null; records: TxRecord[]; agreementCid: string; error: string; notice: string;
}
interface Options {
  registry: DeploymentRegistry; getProvider: () => Eip1193Provider | null;
  domain: () => string; baseUrl?: string; fetcher?: typeof fetch; now?: () => number;
  pause?: (ms: number) => Promise<void>; receiptAttempts?: number;
}
class ChangedContext extends Error { constructor() { super("Ví, mạng hoặc phiên đã thay đổi. Hãy chuẩn bị lại thao tác."); } }
export function walletError(error: unknown): string {
  const code = error && typeof error === "object" ? (error as { code?: unknown }).code : undefined;
  if (code === 4001 || code === "ACTION_REJECTED") return "Bạn đã từ chối yêu cầu trong MetaMask.";
  if (code === -32002) return "MetaMask đang chờ một yêu cầu khác. Mở tiện ích để xử lý trước.";
  if (code === 4902) return "MetaMask chưa có mạng này. Thêm mạng phù hợp rồi thử lại.";
  if (error instanceof HubError) {
    if (error.status === 401) return "Phiên ví chưa hợp lệ hoặc đã hết hạn. Ký xác thực lại.";
    if (error.status === 403) return "Không có quyền thực hiện thao tác với ví hoặc mạng này.";
    if (error.status === 503) return "Backend, contract hoặc RPC chưa sẵn sàng.";
  }
  return error instanceof Error ? error.message : "Không thực hiện được yêu cầu.";
}
export class WalletClient {
  private state: WalletState;
  private listeners = new Set<() => void>();
  private provider: Eip1193Provider | null = null;
  private controllers = new Set<AbortController>();
  private locked = false;
  private options: Options;
  private initialization = 0;
  private now: () => number;
  private fetcher: typeof fetch;
  private pause: (ms: number) => Promise<void>;
  private accountsListener = (value: unknown) => {
    const accounts = Array.isArray(value) ? value : [];
    try { this.identity(typeof accounts[0] === "string" ? accounts[0] : "", this.state.chainId); } catch { this.identity("", this.state.chainId); }
  };
  private chainListener = (value: unknown) => { try { this.identity(this.state.account, Number(uint(value))); } catch { this.identity("", null); } };
  private disconnectListener = () => this.identity("", null);

  constructor(options: Options) {
    this.options = options;
    this.now = options.now || Date.now; this.fetcher = options.fetcher || fetch;
    this.pause = options.pause || ((ms) => new Promise((resolve) => setTimeout(resolve, ms)));
    this.state = { mode: "live", baseUrl: apiBase(options.baseUrl || "http://127.0.0.1:8000"), network: "local",
      account: "", chainId: null, session: null, epoch: 0, revision: 0, busy: false, phase: "idle",
      quote: null, records: [], agreementCid: "", error: "", notice: "" };
  }
  getSnapshot = () => this.state;
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener); }; };
  private emit(next: Partial<WalletState>) { this.state = { ...this.state, ...next }; this.listeners.forEach((listener) => listener()); }
  private invalidate(patch: Partial<WalletState> = {}) {
    this.controllers.forEach((c) => c.abort()); this.controllers.clear();
    this.emit({ session: null, quote: null, agreementCid: "", error: "", notice: "", epoch: this.state.epoch + 1,
      phase: this.locked ? this.state.phase : "idle", ...patch });
  }
  private identity(account: string, chainId: number | null) {
    const normalized = account ? address(account) : "";
    const network: NetworkId = chainId === CHAINS.sepolia ? "sepolia" : chainId === CHAINS.local ? "local" : this.state.network;
    if (normalized === this.state.account && chainId === this.state.chainId && network === this.state.network) return;
    this.invalidate({ account: normalized, chainId, network, notice: "Đã cập nhật ví/mạng. Phiên và báo giá cũ được xóa." });
  }
  private getProvider() {
    if (this.provider) return this.provider;
    const provider = this.options.getProvider();
    if (!provider) throw new Error("Chưa phát hiện MetaMask. Mở trang bằng trình duyệt có tiện ích MetaMask.");
    this.provider = provider;
    provider.on?.("accountsChanged", this.accountsListener);
    provider.on?.("chainChanged", this.chainListener);
    provider.on?.("disconnect", this.disconnectListener);
    return provider;
  }
  async initialize() {
    const job = ++this.initialization, epoch = this.state.epoch;
    try {
      const provider = this.getProvider();
      const [accounts, chain] = await Promise.all([provider.request({ method: "eth_accounts" }), provider.request({ method: "eth_chainId" })]);
      if (job === this.initialization && epoch === this.state.epoch && Array.isArray(accounts) && typeof accounts[0] === "string") this.identity(accounts[0], Number(uint(chain)));
    } catch { /* Connecting remains an explicit user action when MetaMask is absent or locked. */ }
  }
  dispose() {
    this.initialization++;
    this.controllers.forEach((c) => c.abort());
    this.provider?.removeListener?.("accountsChanged", this.accountsListener);
    this.provider?.removeListener?.("chainChanged", this.chainListener);
    this.provider?.removeListener?.("disconnect", this.disconnectListener);
    this.provider = null;
  }
  setMode(mode: WalletState["mode"]) { if (mode !== this.state.mode) this.invalidate({ mode }); }
  configure(baseUrl: string) { const origin = apiBase(baseUrl); if (origin !== this.state.baseUrl) this.invalidate({ baseUrl: origin }); }
  disconnect() { this.invalidate({ account: "", chainId: null, notice: "Đã ngắt phiên ứng dụng. Tài khoản trong MetaMask được giữ nguyên." }); }
  dismissError() { this.emit({ error: "" }); }
  dismissNotice() { this.emit({ notice: "" }); }
  cancelQuote() { if (!this.locked) this.emit({ quote: null, phase: "idle" }); }
  refresh() { this.emit({ revision: this.state.revision + 1 }); }
  expire() {
    if (this.state.session && this.state.session.expiresAt * 1000 <= this.now()) this.invalidate({ notice: "Phiên xác thực đã hết hạn. Ký lại để tiếp tục." });
  }
  private guard(epoch: number) { if (this.state.epoch !== epoch || this.state.mode !== "live") throw new ChangedContext(); }
  private connected() {
    if (this.state.mode !== "live") throw new Error("Chuyển sang chế độ kết nối thật để gửi giao dịch.");
    if (!this.state.account) throw new Error("Kết nối MetaMask trước.");
    if (this.state.chainId !== CHAINS[this.state.network]) throw new Error("Ví đang ở mạng không được hỗ trợ. Chọn Local hoặc Sepolia.");
    return { account: this.state.account, network: this.state.network, epoch: this.state.epoch };
  }
  private authorized() {
    this.expire(); const identity = this.connected(), session = this.state.session;
    if (!session || !same(session.account, identity.account) || session.chainId !== CHAINS[identity.network]) throw new HubError(401, "Cần ký xác thực ví.");
    return identity;
  }
  private async checkWallet(account: string, network: NetworkId) {
    const provider = this.getProvider();
    const [accounts, chain] = await Promise.all([provider.request({ method: "eth_accounts" }), provider.request({ method: "eth_chainId" })]);
    const wallet = Array.isArray(accounts) && typeof accounts[0] === "string" ? accounts[0] : "";
    const chainId = Number(uint(chain));
    if (!wallet || !same(wallet, account) || chainId !== CHAINS[network]) {
      this.identity(wallet, chainId); throw new ChangedContext();
    }
    return provider;
  }
  private async run<T>(phase: WalletState["phase"], operation: () => Promise<T>): Promise<T> {
    if (this.locked) throw new Error("Đang xử lý yêu cầu ví trước đó.");
    this.locked = true; const epoch = this.state.epoch;
    this.emit({ busy: true, phase, error: "" });
    try { return await operation(); }
    catch (error) { if (epoch === this.state.epoch) this.emit({ error: walletError(error), quote: null }); throw error; }
    finally { this.locked = false; this.emit({ busy: false, phase: this.state.quote ? "review" : "idle" }); }
  }
  async connect() {
    return this.run("connecting", async () => {
      const provider = this.getProvider(), accounts = await provider.request({ method: "eth_requestAccounts" });
      const chainId = Number(uint(await provider.request({ method: "eth_chainId" })));
      if (!Array.isArray(accounts) || typeof accounts[0] !== "string") throw new Error("MetaMask chưa cung cấp tài khoản.");
      this.identity(accounts[0], chainId);
    });
  }
  async switchNetwork(network: NetworkId) {
    return this.run("connecting", async () => {
      const provider = this.getProvider();
      try { await provider.request({ method: "wallet_switchEthereumChain", params: [{ chainId: "0x" + CHAINS[network].toString(16) }] }); }
      catch (error) {
        if (network !== "local" || !(error && typeof error === "object" && (error as { code?: number }).code === 4902)) throw error;
        await provider.request({ method: "wallet_addEthereumChain", params: [{ chainId: "0x7a69", chainName: "Hardhat Local", nativeCurrency: { name: "Ether", symbol: "ETH", decimals: 18 }, rpcUrls: ["http://127.0.0.1:8545"] }] });
        await provider.request({ method: "wallet_switchEthereumChain", params: [{ chainId: "0x7a69" }] });
      }
      const accounts = await provider.request({ method: "eth_accounts" });
      this.identity(Array.isArray(accounts) && typeof accounts[0] === "string" ? accounts[0] : "", Number(uint(await provider.request({ method: "eth_chainId" }))));
    });
  }
  getStartBlock() { return this.options.registry.networks[this.state.network].fromBlock ?? 0; }
  clearSession() { if (this.state.session) this.invalidate({ notice: "Phiên không còn hợp lệ. Ký xác thực lại." }); }
  private connection(token = this.state.session?.token || ""): HubConnection {
    return { mode: "api", baseUrl: this.state.baseUrl, token, network: this.state.network, fromBlock: this.getStartBlock() };
  }
  async json(path: string, init: RequestInit = {}, token?: string): Promise<Record<string, unknown>> {
    const epoch = this.state.epoch, network = this.state.network, controller = new AbortController();
    const url = new URL(path, this.state.baseUrl); url.searchParams.set("network", network);
    this.controllers.add(controller);
    const cancel = () => controller.abort();
    init.signal?.addEventListener("abort", cancel, { once: true });
    if (init.signal?.aborted) cancel();
    const timeout = setTimeout(cancel, 45_000);
    try {
      const response = await apiRequest(this.connection(token), url.pathname + url.search, { ...init, signal: controller.signal }, this.fetcher);
      const body = object(await response.json()); this.guard(epoch); return body;
    } catch (error) {
      if (error instanceof HubError && error.status === 401 && epoch === this.state.epoch && this.state.session) this.invalidate({ notice: "Phiên không còn hợp lệ. Ký xác thực lại." });
      throw error;
    } finally { clearTimeout(timeout); init.signal?.removeEventListener("abort", cancel); this.controllers.delete(controller); }
  }
  private post(path: string, body: unknown, token?: string) { return this.json(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }, token); }
  async authenticate() {
    return this.run("authenticating", async () => {
      const { account, network, epoch } = this.connected();
      const provider = await this.checkWallet(account, network); this.guard(epoch);
      const domain = this.options.domain();
      const challenge = await this.post("/api/auth/nonce", { wallet_address: account, chain_id: CHAINS[network], domain }, "");
      if (!same(challenge.wallet_address, account) || uint(challenge.chain_id) !== BigInt(CHAINS[network]) ||
          challenge.domain !== domain || typeof challenge.message !== "string" || typeof challenge.nonce !== "string" ||
          Number(challenge.expires_at) * 1000 <= this.now()) throw new Error("Challenge xác thực không khớp ví, mạng hoặc domain.");
      await this.checkWallet(account, network); this.guard(epoch);
      const signature = await provider.request({ method: "personal_sign", params: [hexlify(toUtf8Bytes(challenge.message)), account] });
      this.guard(epoch); await this.checkWallet(account, network); this.guard(epoch);
      if (typeof signature !== "string" || !same(verifyMessage(challenge.message, signature), account)) throw new Error("Chữ ký không thuộc ví hiện tại.");
      const body = await this.post("/api/auth/verify", { wallet_address: account, chain_id: CHAINS[network], domain, nonce: challenge.nonce, signature }, "");
      if (!same(body.wallet_address, account) || uint(body.chain_id) !== BigInt(CHAINS[network]) || typeof body.access_token !== "string" ||
          !body.access_token || body.token_type !== "bearer" || !Array.isArray(body.roles) || body.roles.some((r) => !["BORROWER", "LENDER", "ADMIN"].includes(String(r))) ||
          !Number.isSafeInteger(body.expires_at) || Number(body.expires_at) * 1000 <= this.now()) throw new Error("Phiên backend không khớp ví/mạng hiện tại.");
      this.guard(epoch);
      this.invalidate({ session: { token: body.access_token, account, chainId: CHAINS[network], expiresAt: Number(body.expires_at), roles: body.roles as string[] },
        notice: "Đã xác thực chữ ký ví. Phiên chỉ giữ trong bộ nhớ.", quote: null, agreementCid: "" });
    });
  }
  async prepare(original: Operation) {
    return this.run("preparing", async () => {
      const { account, network, epoch } = this.authorized();
      if (this.state.records.some((r) => r.status === "pending" && r.network === network && same(r.account, account))) throw new Error("Có giao dịch đã gửi chưa được đối chiếu. Kiểm tra lại trước khi gửi thêm.");
      await this.checkWallet(account, network); this.guard(epoch);
      const operation: Operation = { ...original, args: { ...original.args } };
      this.emit({ quote: null });
      if (operation.action === "MOCK_ORACLE_MULTIPLIER" && (network !== "local" || !this.state.session?.roles.includes("ADMIN"))) throw new Error("Đổi giá chỉ dành cho Admin trên local.");
      if (operation.action === "REPAY" && operation.repayAll) {
        const loan = await this.json("/api/accounts/" + account + "/loan");
        const debt = uint(object(object(loan.risk).total_debt).wad);
        if (!debt) throw new Error("Ví không có dư nợ để tất toán.");
        operation.args.amount_wad = (debt + 10n ** 16n).toString();
      }
      if (operation.action === "BORROW") {
        // Generate/encrypt/pin first; no fake transaction hash is added to the PDF.
        const agreement = await this.post("/api/ipfs/create-agreement", { principal_wad: operation.args.amount_wad, asset_description: operation.assetDescription?.trim(), network });
        if (agreement.status !== "PRE_BORROW_UNSIGNED" || agreement.tx_hash !== null) throw new Error("Agreement phải được tạo trước giao dịch và chưa có txHash.");
        operation.args.agreement_cid = normalizeCid(String(agreement.cid));
        this.emit({ agreementCid: String(agreement.cid) });
      }
      expectedCall(this.options.registry, network, account, operation);
      const body = await this.post("/api/transactions/prepare", { account, network, chain_id: CHAINS[network], action: operation.action, args: operation.args, duration_seconds: 30 * 86400 });
      this.guard(epoch); await this.checkWallet(account, network); this.guard(epoch);
      const quote = validatePrepared(body, this.options.registry, network, account, operation, epoch, this.now());
      this.emit({ quote }); return quote;
    });
  }
  async prepareApproval() {
    const quote = this.state.quote;
    if (!quote?.approvalRequired) throw new Error("Không có bước cấp quyền đang chờ.");
    if (quote.allowance.token_id !== undefined && quote.allowance.token_id !== null) {
      return this.prepare({ action: "APPROVE_COLLATERAL_NFT", args: { token_id: uint(quote.allowance.token_id).toString() } });
    }
    const needed = uint(quote.allowance.amount_wad);
    // A visible bounded buffer prevents accrued interest from forcing an approval loop.
    const growingDebt = quote.operation.action === "REPAY" || quote.operation.action === "LIQUIDATE";
    const amount = growingDebt ? needed + needed / 10000n + 10n ** 16n : needed;
    return this.prepare({ action: "APPROVE_MYUSDT", args: { amount_wad: amount.toString() } });
  }
  async send() {
    const quote = this.state.quote;
    if (!quote || quote.approvalRequired) throw new Error("Chuẩn bị giao dịch và hoàn tất cấp quyền trước.");
    return this.run("signing", async () => {
      const { account, network, epoch } = this.authorized();
      if (quote.epoch !== epoch || quote.network !== network || !same(quote.account, account) || this.now() - quote.quotedAt > 120_000) throw new Error("Báo giá đã cũ hoặc ví/mạng đã đổi. Chuẩn bị lại trước khi ký.");
      const provider = await this.checkWallet(account, network); this.guard(epoch);
      const origin = this.state.baseUrl;
      // Revalidate the saved payload immediately before the wallet prompt.
      const expected = expectedCall(this.options.registry, network, account, quote.operation);
      if (!same(quote.tx.from, account) || !same(quote.tx.to, expected.to) || quote.tx.data !== expected.data || uint(quote.tx.value) !== 0n || uint(quote.tx.chainId) !== BigInt(CHAINS[network]) || uint(quote.tx.gas) !== uint(quote.gas.gas_limit) || uint(quote.tx.gasPrice) !== uint(quote.gas.gas_price_wei)) throw new Error("Payload đã thay đổi. Đã chặn gửi.");
      this.emit({ quote: null });
      const rawHash = await provider.request({ method: "eth_sendTransaction", params: [quote.tx] });
      if (typeof rawHash !== "string" || !/^0x[0-9a-fA-F]{64}$/.test(rawHash)) throw new Error("MetaMask không trả transaction hash hợp lệ.");
      const record: TxRecord = { hash: rawHash, intentId: quote.intentId, apiOrigin: origin, network, account, action: quote.operation.action, cid: quote.cid, amountWad: typeof quote.operation.args.amount_wad === "string" ? quote.operation.args.amount_wad : undefined, status: "pending" };
      this.emit({ records: [...this.state.records, record], notice: "Đã gửi giao dịch; đang chờ xác nhận, chưa ghi nhận thành công." });
      if (this.state.epoch !== epoch) return;
      this.emit({ phase: "confirming" });
      await this.confirmRecord(record, epoch);
    });
  }
  private updateRecord(hash: string, patch: Partial<TxRecord>) { this.emit({ records: this.state.records.map((r) => r.hash === hash ? { ...r, ...patch } : r) }); }
  private async confirmRecord(record: TxRecord, epoch: number) {
    if (record.apiOrigin !== this.state.baseUrl) throw new Error("Đổi lại API đã chuẩn bị giao dịch: " + record.apiOrigin);
    const provider = await this.checkWallet(record.account, record.network); this.guard(epoch);
    for (let attempt = 0; attempt < (this.options.receiptAttempts || 60); attempt++) {
      this.guard(epoch); this.authorized();
      const raw = await provider.request({ method: "eth_getTransactionReceipt", params: [record.hash] }); this.guard(epoch);
      if (raw) {
        const receipt = object(raw);
        if (receipt.transactionHash && String(receipt.transactionHash).toLowerCase() !== record.hash.toLowerCase()) throw new Error("Receipt không khớp hash đã gửi.");
        if (uint(receipt.status) !== 1n) {
          this.updateRecord(record.hash, { status: "failed" }); this.emit({notice: "Giao dịch bị revert, không ghi nhận thành công."}); this.refresh();
          throw new Error("Giao dịch đã vào block nhưng bị revert. Không ghi nhận thành công.");
        }
        await this.checkWallet(record.account, record.network); this.guard(epoch);
        const confirmed = await this.post("/api/transactions/confirm", { intent_id: record.intentId, tx_hash: record.hash, network: record.network, chain_id: CHAINS[record.network] });
        if (uint(confirmed.status) !== 1n || String(confirmed.tx_hash).toLowerCase() !== record.hash.toLowerCase()) throw new Error("Backend chưa xác nhận đúng giao dịch.");
        if (record.action === "BORROW") {
          const binding = object(confirmed.loan_binding);
          if (binding.agreement_cid !== record.cid || !same(binding.borrower_wallet, record.account) || binding.network !== record.network || uint(binding.chain_id) !== BigInt(CHAINS[record.network]) || String(binding.tx_hash).toLowerCase() !== record.hash.toLowerCase() || String(binding.principal_wad) !== record.amountWad) throw new Error("CID chưa được đối chiếu đúng khoản vay.");
        }
        this.guard(epoch); this.updateRecord(record.hash, { status: "confirmed", blockNumber: Number(uint(confirmed.block_number)) });
        this.emit({ notice: "Giao dịch đã được backend xác nhận.", revision: this.state.revision + 1 }); return;
      }
      await this.pause(1500);
    }
    this.emit({ notice: "Đã có hash nhưng chưa đối chiếu xong. Dùng Kiểm tra lại; không gửi lại giao dịch." });
  }
  async retryConfirmation(hash: string) {
    return this.run("confirming", async () => {
      const { account, network, epoch } = this.authorized();
      const record = this.state.records.find((r) => r.hash === hash && r.status === "pending");
      if (!record || record.network !== network || !same(record.account, account)) throw new Error("Chọn đúng ví và mạng của giao dịch đã gửi.");
      await this.confirmRecord(record, epoch);
    });
  }
  async advanceTime(days: 30 | 60) {
    return this.run("preparing", async () => {
      const { network, epoch } = this.authorized();
      if (network !== "local" || !this.state.session?.roles.includes("ADMIN")) throw new Error("Chỉ Admin trên local được tua thời gian.");
      await this.checkWallet(this.state.account, network); this.guard(epoch);
      await this.post("/api/demo/time", { seconds: days * 86400, network, chain_id: CHAINS.local });
      this.guard(epoch); this.emit({ notice: "Đã tua thời gian Hardhat " + days + " ngày.", revision: this.state.revision + 1 });
    });
  }
}
