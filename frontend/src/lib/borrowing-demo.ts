import { amountLabel, formatUnitsDecimal, parseAmount, parseUnitsDecimal, rates, WAD } from "./wad.ts";

export const BORROW_STORAGE_KEY = "defi-borrowing-l03-v1";
export const DEFAULT_COLLATERAL_NFT_ID = "2";
export const BORROW_WALLETS = [
  { id: "borrower", name: "Ví người vay", address: "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC" },
  { id: "liquidator", name: "Ví thanh lý", address: "0x15d34AAf54267DB7D7c367839AAf71A00a2C6A65" },
] as const;
export type BorrowActor = typeof BORROW_WALLETS[number]["id"];
export type CollateralKind = "nft" | "token";
export const YEAR_SECONDS = 31536000n;
const MAX_OFFSET = Number(YEAR_SECONDS) * 10;
const minimum = (a: bigint, b: bigint) => a < b ? a : b;
const positivePart = (n: bigint) => n > 0n ? n : 0n;
export interface BorrowLoan {
  active: boolean;
  kind: CollateralKind;
  collateralUnitsWad: string;
  principalWad: string;
  interestWad: string;
  indexSnapshotWad: string;
  receiptId: string | null;
  receiptStatus: "none" | "active" | "settled" | "liquidated";
}
export interface BorrowState {
  version: 1;
  indexAt: number;
  offsetSeconds: number;
  borrowIndexWad: string;
  poolSuppliedWad: string;
  poolBorrowedWad: string;
  poolCashWad: string;
  priceBps: number;
  wallets: Record<BorrowActor, { balanceWad: string; allowanceWad: string }>;
  nftTokenId?: string;
  nftOwner: BorrowActor | "pool";
  nftApproved: boolean;
  loan: BorrowLoan;
  nextReceiptId: string;
  sequence: number;
  activity: { id: number; label: string; at: number }[];
}
export type BorrowAction =
  | { kind: "approve"; actor: BorrowActor; amount: string }
  | { kind: "approve-nft"; actor: BorrowActor }
  | { kind: "deposit"; actor: BorrowActor; asset: CollateralKind; amount: string }
  | { kind: "borrow"; actor: BorrowActor; amount: string }
  | { kind: "repay"; actor: BorrowActor; amount: string; full: boolean }
  | { kind: "withdraw"; actor: BorrowActor }
  | { kind: "liquidate"; actor: BorrowActor }
  | { kind: "price"; multiplierBps: number }
  | { kind: "advance"; seconds: number }
  | { kind: "faucet"; actor: BorrowActor };
export type TransactionAction = Exclude<BorrowAction, { kind: "price" | "advance" | "faucet" }>;

export function createBorrowDemo(nowMs = Date.now(), empty = false): BorrowState {
  const principal = empty ? 0n : 500n * WAD;
  return {
    version: 1, indexAt: Math.floor(nowMs / 1000), offsetSeconds: 0,
    borrowIndexWad: WAD.toString(), poolSuppliedWad: (1000n * WAD).toString(),
    poolBorrowedWad: principal.toString(), poolCashWad: (1000n * WAD - principal).toString(),
    priceBps: 10000, nextReceiptId: empty ? "1" : "2", sequence: 0, activity: [],
    wallets: {
      borrower: { balanceWad: ((empty ? 1000n : 1500n) * WAD).toString(), allowanceWad: "0" },
      liquidator: { balanceWad: (2000n * WAD).toString(), allowanceWad: "0" },
    },
    nftTokenId: DEFAULT_COLLATERAL_NFT_ID,
    nftOwner: empty ? "borrower" : "pool", nftApproved: false,
    loan: { active: !empty, kind: "nft", collateralUnitsWad: "0", principalWad: principal.toString(),
      interestWad: "0", indexSnapshotWad: WAD.toString(), receiptId: empty ? null : "1",
      receiptStatus: empty ? "none" : "active" },
  };
}
export function currentBorrowApr(state: BorrowState) {
  return rates(state.poolSuppliedWad, state.poolBorrowedWad).borrowAprBps;
}
export function borrowCheckpoint(state: BorrowState, nowMs: number): BorrowState {
  const at = Math.max(state.indexAt, Math.floor(nowMs / 1000) + state.offsetSeconds);
  const deltaIndex = WAD * BigInt(currentBorrowApr(state)) * BigInt(at - state.indexAt) / (YEAR_SECONDS * 10000n);
  const index = BigInt(state.borrowIndexWad) + deltaIndex;
  const loan = state.loan;
  const earned = BigInt(loan.principalWad) * (index - BigInt(loan.indexSnapshotWad)) / WAD;
  return { ...state, indexAt: at, borrowIndexWad: index.toString(),
    loan: { ...loan, interestWad: (BigInt(loan.interestWad) + earned).toString(), indexSnapshotWad: index.toString() } };
}
export function totalDebt(state: BorrowState) {
  return BigInt(state.loan.principalWad) + BigInt(state.loan.interestWad);
}
export function collateralValue(state: BorrowState) {
  if (!state.loan.active) return 0n;
  const base = state.loan.kind === "nft" ? 1000n * WAD : BigInt(state.loan.collateralUnitsWad);
  return base * BigInt(state.priceBps) / 10000n;
}
export function healthFactor(value: bigint, debt: bigint): bigint | null {
  return debt === 0n ? null : value * 8000n * WAD / (debt * 10000n);
}
export function riskStatus(hf: bigint | null): "safe" | "warning" | "danger" {
  if (hf === null || hf >= 15n * WAD / 10n) return "safe";
  return hf >= WAD ? "warning" : "danger";
}
export function formatHealthFactor(hf: bigint | null): string {
  if (hf === null) return "∞";
  // Floor the display: 0.99999 must not be shown as 1.0000 while liquidatable.
  const scaled = hf * 10000n / WAD;
  return (scaled / 10000n).toString() + "," + (scaled % 10000n).toString().padStart(4, "0");
}
export function borrowingCapacity(state: BorrowState) {
  return minimum(positivePart(collateralValue(state) * 7000n / 10000n - totalDebt(state)), BigInt(state.poolCashWad));
}
export function ltvBps(state: BorrowState, extra = 0n) {
  const value = collateralValue(state);
  return value === 0n ? 0n : (totalDebt(state) + extra) * 10000n / value;
}
export function referenceApy(aprBps: number) { return (Math.pow(1 + aprBps / 10000 / 365, 365) - 1) * 100; }
export function approvalAmount(wad: bigint) {
  // A small, explicit buffer avoids a full repayment becoming stale while interest accrues.
  const cent = WAD / 100n;
  return ((wad + cent - 1n) / cent + 1n) * cent;
}
export function actionPayment(state: BorrowState, action: TransactionAction): bigint {
  if (action.kind === "repay") return action.full ? totalDebt(state) : minimum(parseAmount(action.amount), totalDebt(state));
  if (action.kind === "liquidate") return totalDebt(state);
  if (action.kind === "deposit" && action.asset === "token") return parseAmount(action.amount);
  return 0n;
}
export const actionLabel: Record<TransactionAction["kind"], string> = {
  approve: "Cấp quyền chi MyUSDT", "approve-nft": "Cấp quyền CollateralNFT",
  deposit: "Khóa tài sản thế chấp", borrow: "Vay MyUSDT", repay: "Trả nợ MyUSDT",
  withdraw: "Rút tài sản thế chấp", liquidate: "Thanh lý khoản vay",
};

export function applyBorrowAction(original: BorrowState, action: BorrowAction, nowMs = Date.now()): BorrowState {
  const commitsPool = ["deposit", "borrow", "repay", "withdraw", "liquidate"].includes(action.kind);
  let state = commitsPool ? borrowCheckpoint(original, nowMs) : original;
  const wallets = { borrower: { ...state.wallets.borrower }, liquidator: { ...state.wallets.liquidator } };
  let loan = { ...state.loan };
  let cash = BigInt(state.poolCashWad);
  let borrowed = BigInt(state.poolBorrowedWad);
  let nftOwner = state.nftOwner;
  let nftApproved = state.nftApproved;
  let nextReceiptId = state.nextReceiptId;
  let label: string;
  const release = (liquidated = false) => {
    if (loan.kind === "nft") nftOwner = liquidated ? "liquidator" : "borrower";
    else if (!liquidated) wallets.borrower.balanceWad = (BigInt(wallets.borrower.balanceWad) + BigInt(loan.collateralUnitsWad)).toString();
    loan = { ...loan, active: false, collateralUnitsWad: "0", principalWad: "0", interestWad: "0",
      receiptStatus: liquidated ? "liquidated" : "settled" };
  };
  const spend = (actor: BorrowActor, amount: bigint) => {
    if (amount > BigInt(wallets[actor].balanceWad)) throw new Error("Ví không đủ MyUSDT.");
    if (amount > BigInt(wallets[actor].allowanceWad)) throw new Error("Cần cấp quyền chi MyUSDT trước khi xác nhận.");
    wallets[actor].balanceWad = (BigInt(wallets[actor].balanceWad) - amount).toString();
    wallets[actor].allowanceWad = (BigInt(wallets[actor].allowanceWad) - amount).toString();
  };
  if (action.kind === "price") {
    if (!Number.isInteger(action.multiplierBps) || action.multiplierBps < 1 || action.multiplierBps > 10000) throw new Error("Kịch bản giá không hợp lệ.");
    state = { ...state, priceBps: action.multiplierBps };
    label = "Đổi giá mô phỏng về " + action.multiplierBps / 100 + "%";
  } else if (action.kind === "advance") {
    if (!Number.isSafeInteger(action.seconds) || action.seconds <= 0 || state.offsetSeconds + action.seconds > MAX_OFFSET) throw new Error("Khoảng thời gian mô phỏng không hợp lệ.");
    state = { ...state, offsetSeconds: state.offsetSeconds + action.seconds };
    label = "Tăng thời gian mô phỏng " + action.seconds / 86400 + " ngày";
  } else if (action.kind === "faucet") {
    if (action.actor !== "borrower" && action.actor !== "liquidator") throw new Error("Ví mô phỏng không hợp lệ");
    wallets[action.actor].balanceWad = (BigInt(wallets[action.actor].balanceWad) + 1000n * WAD).toString();
    label = "Nhận 1.000 MyUSDT mô phỏng";
  } else {
    if (action.actor !== "borrower" && action.actor !== "liquidator") throw new Error("Ví mô phỏng không hợp lệ.");
    if (action.actor !== "borrower" && ["deposit", "borrow", "repay", "withdraw", "approve-nft"].includes(action.kind)) throw new Error("Chọn ví người vay để thực hiện thao tác này.");
    label = actionLabel[action.kind] + " · mô phỏng";
    if (action.kind === "approve") {
      wallets[action.actor].allowanceWad = parseAmount(action.amount).toString();
    } else if (action.kind === "approve-nft") {
      const tokenId = state.nftTokenId ?? DEFAULT_COLLATERAL_NFT_ID;
      if (nftOwner !== "borrower") throw new Error("Ví người vay không sở hữu CollateralNFT #" + tokenId + ".");
      nftApproved = true;
    } else if (action.kind === "deposit") {
      if (loan.active) throw new Error("Đã có tài sản khóa. Tất toán hoặc rút trước khi tạo vị thế mới.");
      let units = 0n;
      if (action.asset === "nft") {
        const tokenId = state.nftTokenId ?? DEFAULT_COLLATERAL_NFT_ID;
        if (nftOwner !== "borrower") throw new Error("CollateralNFT #" + tokenId + " không thuộc ví người vay.");
        if (!nftApproved) throw new Error("Cần cấp quyền CollateralNFT #" + tokenId + " trước khi khóa.");
        nftOwner = "pool"; nftApproved = false;
      } else {
        units = parseAmount(action.amount);
        spend("borrower", units);
      }
      loan = { active: true, kind: action.asset, collateralUnitsWad: units.toString(), principalWad: "0",
        interestWad: "0", indexSnapshotWad: state.borrowIndexWad, receiptId: nextReceiptId, receiptStatus: "active" };
      nextReceiptId = (BigInt(nextReceiptId) + 1n).toString();
    } else if (action.kind === "borrow") {
      if (!loan.active) throw new Error("Khóa tài sản thế chấp trước khi vay.");
      const amount = parseAmount(action.amount);
      if (totalDebt(state) + amount > collateralValue(state) * 7000n / 10000n) throw new Error("Tổng nợ gồm gốc và lãi không được vượt 70% giá trị thế chấp.");
      if (amount > cash) throw new Error("Pool không đủ thanh khoản khả dụng.");
      loan.principalWad = (BigInt(loan.principalWad) + amount).toString();
      wallets.borrower.balanceWad = (BigInt(wallets.borrower.balanceWad) + amount).toString();
      cash -= amount; borrowed += amount;
    } else if (action.kind === "repay") {
      if (!loan.active || totalDebt(state) === 0n) throw new Error("Không có dư nợ cần trả.");
      const amount = actionPayment(state, action);
      if (amount <= 0n) throw new Error("Số tiền phải lớn hơn 0.");
      spend("borrower", amount);
      const interestPaid = minimum(amount, BigInt(loan.interestWad));
      const principalPaid = amount - interestPaid;
      loan.interestWad = (BigInt(loan.interestWad) - interestPaid).toString();
      loan.principalWad = (BigInt(loan.principalWad) - principalPaid).toString();
      cash += amount; borrowed -= principalPaid;
      if (BigInt(loan.principalWad) + BigInt(loan.interestWad) === 0n) release();
    } else if (action.kind === "withdraw") {
      if (!loan.active) throw new Error("Không có tài sản đang khóa.");
      if (totalDebt(state) !== 0n) throw new Error("Chỉ rút thế chấp khi tổng nợ bằng 0.");
      release();
    } else {
      const hf = healthFactor(collateralValue(state), totalDebt(state));
      if (action.actor !== "liquidator") throw new Error("Chọn ví thanh lý để thử thao tác.");
      if (!loan.active || hf === null || hf >= WAD) throw new Error("Chỉ thanh lý khi HF nhỏ hơn 1. HF = 1 vẫn bị chặn.");
      const debt = totalDebt(state);
      spend("liquidator", debt);
      cash += debt; borrowed -= BigInt(loan.principalWad);
      if (loan.kind === "token") {
        const units = BigInt(loan.collateralUnitsWad);
        const seizedValue = minimum(collateralValue(state), debt * 10500n / 10000n);
        const unitPrice = WAD * BigInt(state.priceBps) / 10000n;
        const seizedUnits = minimum(units, seizedValue * WAD / unitPrice);
        wallets.liquidator.balanceWad = (BigInt(wallets.liquidator.balanceWad) + seizedUnits).toString();
        wallets.borrower.balanceWad = (BigInt(wallets.borrower.balanceWad) + units - seizedUnits).toString();
      }
      release(true);
    }
  }
  const sequence = state.sequence + 1;
  return { ...state, wallets, loan, nftOwner, nftApproved, nextReceiptId, sequence,
    poolCashWad: cash.toString(), poolBorrowedWad: borrowed.toString(),
    activity: [{ id: sequence, label, at: Math.floor(nowMs / 1000) + state.offsetSeconds }, ...state.activity].slice(0, 40) };
}

const SIMULATED_GAS: Record<TransactionAction["kind"], number> = {
  approve: 50000, "approve-nft": 50000, deposit: 145000, borrow: 180000, repay: 160000, withdraw: 100000, liquidate: 230000,
};
export function gasIllustration(kind: TransactionAction["kind"], gwei = "2") {
  const input = gwei.trim().replace(",", ".");
  if (!/^\d{1,5}(\.\d{1,9})?$/.test(input)) throw new Error("Giá gas cần là số dương, tối đa 9 chữ số thập phân.");
  const gasPriceWei = parseUnitsDecimal(input, 9);
  if (gasPriceWei <= 0n || gasPriceWei > 10000n * 10n ** 9n) throw new Error("Giá gas mô phỏng phải lớn hơn 0 và không quá 10.000 gwei.");
  const units = SIMULATED_GAS[kind];
  const gasLimit = Math.ceil(units * 1.2);
  const feeWei = BigInt(units) * gasPriceWei;
  return { kind: "SIMULATED" as const, units, gasLimit, gasPriceWei: gasPriceWei.toString(), feeWei: feeWei.toString(),
    feeEth: formatUnitsDecimal(feeWei, 18), maximumEth: formatUnitsDecimal(BigInt(gasLimit) * gasPriceWei, 18) };
}
export function restoreBorrowDemo(raw: string, nowMs = Date.now()): BorrowState {
  const data: unknown = JSON.parse(raw);
  if (!data || typeof data !== "object") throw new Error("Phiên mô phỏng không hợp lệ.");
  const s = data as BorrowState;
  const uint = (v: unknown) => typeof v === "string" && /^\d{1,78}$/.test(v);
  const fail = () => { throw new Error("Phiên mô phỏng không hợp lệ."); };
  if (s.version !== 1 || !Number.isSafeInteger(s.indexAt) || s.indexAt < 0 ||
      !Number.isSafeInteger(s.offsetSeconds) || s.offsetSeconds < 0 || s.offsetSeconds > MAX_OFFSET ||
      s.indexAt > Math.floor(nowMs / 1000) + s.offsetSeconds || !uint(s.borrowIndexWad) || BigInt(s.borrowIndexWad) < WAD ||
      !uint(s.poolSuppliedWad) || !uint(s.poolBorrowedWad) || !uint(s.poolCashWad) ||
      !Number.isInteger(s.priceBps) || s.priceBps < 1 || s.priceBps > 10000 ||
      (s.nftTokenId !== undefined && !uint(s.nftTokenId)) ||
      (!uint(s.nextReceiptId) || BigInt(s.nextReceiptId) < 1n) || !Number.isSafeInteger(s.sequence) || s.sequence < 0 || !s.loan || !s.wallets) fail();
  for (const who of ["borrower", "liquidator"] as const) {
    if (!s.wallets[who] || !uint(s.wallets[who].balanceWad) || !uint(s.wallets[who].allowanceWad)) fail();
  }
  const l = s.loan;
  if (typeof l.active !== "boolean" || !["nft", "token"].includes(l.kind) ||
      !uint(l.principalWad) || !uint(l.interestWad) || !uint(l.collateralUnitsWad) || !uint(l.indexSnapshotWad) ||
      (BigInt(l.indexSnapshotWad) < WAD || BigInt(l.indexSnapshotWad) > BigInt(s.borrowIndexWad)) || BigInt(l.principalWad) !== BigInt(s.poolBorrowedWad) ||
      !["borrower", "pool", "liquidator"].includes(s.nftOwner) || typeof s.nftApproved !== "boolean" ||
      !["none", "active", "settled", "liquidated"].includes(l.receiptStatus) ||
      (l.receiptId !== null && (!uint(l.receiptId) || BigInt(l.receiptId) < 1n || BigInt(l.receiptId) >= BigInt(s.nextReceiptId)))) fail();
  if (l.active && (l.receiptStatus !== "active" || l.receiptId === null ||
      (l.kind === "nft" ? (s.nftOwner !== "pool" || BigInt(l.collateralUnitsWad) !== 0n) : (BigInt(l.collateralUnitsWad) <= 0n || s.nftOwner === "pool")))) fail();
  if (!l.active && (s.nftOwner === "pool" || totalDebt(s) !== 0n || BigInt(l.collateralUnitsWad) !== 0n || l.receiptStatus === "active")) fail();
  if (!Array.isArray(s.activity) || s.activity.length > 40 || s.activity.some((a) => !a ||
      !Number.isSafeInteger(a.id) || a.id < 1 || a.id > s.sequence || typeof a.label !== "string" ||
      a.label.length > 200 || !Number.isSafeInteger(a.at) || a.at < 0 || a.at > Math.floor(nowMs / 1000) + s.offsetSeconds)) fail();
  return s;
}

export function prepareBorrowTransaction(state: BorrowState, action: TransactionAction, gwei = "2") {
  const payment = actionPayment(state, action);
  const needsApproval = payment > BigInt(state.wallets[action.actor].allowanceWad);
  const needsNftApproval = action.kind === "deposit" && action.asset === "nft" && !state.nftApproved;
  // Quotation only: calculate the resulting state assuming the separate approval step succeeds.
  // The actual action still validates the real allowance and ownership again.
  const quotationState: BorrowState = { ...state, nftApproved: needsNftApproval || state.nftApproved,
    wallets: { borrower: { ...state.wallets.borrower }, liquidator: { ...state.wallets.liquidator } } };
  if (needsApproval) quotationState.wallets[action.actor].allowanceWad = payment.toString();
  const after = applyBorrowAction(quotationState, action, (state.indexAt - state.offsetSeconds) * 1000);
  return { after, payment, needsApproval, needsNftApproval, gas: gasIllustration(action.kind, gwei) };
}

export function capacityLabel(value: bigint, decimals = 4): string {
  if (!Number.isInteger(decimals) || decimals < 0 || decimals > 18) throw new Error("Invalid decimal precision");
  const unit = 10n ** BigInt(18 - decimals);
  return amountLabel(value / unit * unit, decimals);
}
