import { getAddress, isAddress, ZeroAddress } from "ethers";
import { amountLabel, exactAmount, parseAmount, rates, sameAddress, shortAddress, WAD } from "./wad.ts";

export { amountLabel, exactAmount, parseAmount, rates, sameAddress, shortAddress, WAD };
const YEAR_MS = 365n * 24n * 60n * 60n * 1000n;
const INTEREST_DENOMINATOR = 10000n * YEAR_MS;
export const STORAGE_KEY = "defi-lending-l02-v1";
export const ACCOUNTS = [
  { name: "Ví trải nghiệm A", address: "0x70997970C51812dc3A010C7d01b50e0d17dc79C8" },
  { name: "Ví trải nghiệm B", address: "0x90F79bf6EB2c4f870365E785982E1f101E93b906" },
] as const;

export interface Position {
  id: string;
  owner: string;
  principalWad: string;
  interestWad: string;
  remainder: string;
  openedAt: number;
}
export interface Activity {
  id: string;
  kind: "supply" | "withdraw" | "transfer" | "faucet";
  actor: string;
  amountWad: string;
  positionId?: string;
  recipient?: string;
  at: number;
}
export interface DemoState {
  version: 1;
  checkpointAt: number;
  nextId: string;
  totalSuppliedWad: string;
  totalBorrowedWad: string;
  availableLiquidityWad: string;
  balances: Record<string, string>;
  positions: Position[];
  activity: Activity[];
}
export type DemoAction =
  | { kind: "supply"; actor: string; amount: string }
  | { kind: "withdraw"; actor: string; amount: string; positionId: string }
  | { kind: "transfer"; actor: string; recipient: string; positionId: string }
  | { kind: "faucet"; actor: string };

export function createDemo(now = Date.now()): DemoState {
  return {
    version: 1, checkpointAt: now, nextId: "2",
    totalSuppliedWad: (1000n * WAD).toString(),
    totalBorrowedWad: (500n * WAD).toString(),
    availableLiquidityWad: (500n * WAD).toString(),
    balances: { [ACCOUNTS[0].address]: (2500n * WAD).toString(), [ACCOUNTS[1].address]: (1800n * WAD).toString() },
    positions: [{ id: "1", owner: ACCOUNTS[0].address, principalWad: (1000n * WAD).toString(), interestWad: "0", remainder: "0", openedAt: now }],
    activity: [],
  };
}

export function checkpoint(state: DemoState, now: number): DemoState {
  const at = Math.max(state.checkpointAt, now);
  const elapsed = BigInt(Math.trunc(at - state.checkpointAt));
  const apr = BigInt(rates(state.totalSuppliedWad, state.totalBorrowedWad).supplyAprBps);
  return {
    ...state, checkpointAt: at,
    positions: state.positions.map((position) => {
      const numerator = BigInt(position.principalWad) * apr * elapsed + BigInt(position.remainder);
      return { ...position,
        interestWad: (BigInt(position.interestWad) + numerator / INTEREST_DENOMINATOR).toString(),
        remainder: (numerator % INTEREST_DENOMINATOR).toString(),
      };
    }),
  };
}
export function ownedPositions(state: DemoState, actor: string) {
  return state.positions.filter((p) => sameAddress(p.owner, actor));
}
export function claimable(position: Position) {
  return BigInt(position.principalWad) + BigInt(position.interestWad);
}
export function withdrawLimit(state: DemoState, position: Position) {
  const claim = claimable(position);
  const cash = BigInt(state.availableLiquidityWad);
  return claim < cash ? claim : cash;
}

export function applyDemoAction(original: DemoState, action: DemoAction, now = Date.now()): DemoState {
  // Settle all positions with the OLD APR before changing pool balances.
  const state = checkpoint(original, now);
  const actor = ACCOUNTS.find((a) => sameAddress(a.address, action.actor))?.address;
  if (!actor) throw new Error("Chọn một ví trải nghiệm hợp lệ.");
  const balances = { ...state.balances };
  let positions = state.positions.map((p) => ({ ...p }));
  let supplied = BigInt(state.totalSuppliedWad);
  let available = BigInt(state.availableLiquidityWad);
  let nextId = state.nextId;
  let amount = 0n;
  let positionId: string | undefined;
  let recipient: string | undefined;

  if (action.kind === "supply") {
    amount = parseAmount(action.amount);
    if (amount > BigInt(balances[actor])) throw new Error("Số tiền vượt số dư MyUSDT của ví.");
    positionId = nextId;
    nextId = (BigInt(nextId) + 1n).toString();
    balances[actor] = (BigInt(balances[actor]) - amount).toString();
    supplied += amount; available += amount;
    positions.push({ id: positionId, owner: actor, principalWad: amount.toString(), interestWad: "0", remainder: "0", openedAt: state.checkpointAt });
  } else if (action.kind === "faucet") {
    amount = 1000n * WAD;
    balances[actor] = (BigInt(balances[actor]) + amount).toString();
  } else {
    positionId = action.positionId;
    const position = positions.find((p) => p.id === positionId);
    if (!position || !sameAddress(position.owner, actor)) throw new Error("Ví hiện tại không sở hữu NFT này.");
    if (action.kind === "withdraw") {
      amount = parseAmount(action.amount);
      if (amount > claimable(position)) throw new Error("Số tiền vượt quyền rút của NFT đã chọn.");
      if (amount > available) throw new Error("Pool không đủ thanh khoản khả dụng cho số tiền này.");
      // Demo settlement: interest first, then principal. Real settlement belongs to L05.
      const interest = BigInt(position.interestWad);
      const paidInterest = amount < interest ? amount : interest;
      const paidPrincipal = amount - paidInterest;
      position.interestWad = (interest - paidInterest).toString();
      position.principalWad = (BigInt(position.principalWad) - paidPrincipal).toString();
      balances[actor] = (BigInt(balances[actor]) + amount).toString();
      supplied -= paidPrincipal; available -= amount;
      if (claimable(position) === 0n) positions = positions.filter((p) => p.id !== positionId);
    } else {
      if (!isAddress(action.recipient)) throw new Error("Địa chỉ ví nhận không hợp lệ hoặc sai checksum.");
      recipient = getAddress(action.recipient);
      if (recipient === ZeroAddress) throw new Error("Không thể chuyển NFT đến địa chỉ zero.");
      if (sameAddress(recipient, actor)) throw new Error("Ví nhận phải khác ví hiện tại.");
      amount = claimable(position);
      position.owner = recipient;
    }
  }
  const event: Activity = {
    id: String(state.checkpointAt) + "-" + String(state.activity.length) + "-" + state.nextId,
    kind: action.kind, actor, amountWad: amount.toString(), positionId, recipient, at: state.checkpointAt,
  };
  return { ...state, nextId, totalSuppliedWad: supplied.toString(), availableLiquidityWad: available.toString(),
    balances, positions, activity: [event, ...state.activity].slice(0, 80) };
}

export function restoreDemo(raw: string, now = Date.now()): DemoState {
  const data: unknown = JSON.parse(raw);
  if (!data || typeof data !== "object") throw new Error("Dữ liệu lưu không hợp lệ.");
  const state = data as DemoState;
  const uint = (v: unknown) => typeof v === "string" && /^\d{1,78}$/.test(v);
  if (state.version !== 1 || !Number.isSafeInteger(state.checkpointAt) || state.checkpointAt < 0 || state.checkpointAt > now ||
      !uint(state.nextId) || BigInt(state.nextId) < 1n || !uint(state.totalSuppliedWad) || !uint(state.totalBorrowedWad) ||
      !uint(state.availableLiquidityWad) || !Array.isArray(state.positions) || state.positions.length > 10000 ||
      !Array.isArray(state.activity) || !state.balances) throw new Error("Dữ liệu lưu không hợp lệ.");
  if (!ACCOUNTS.every((a) => uint(state.balances[a.address]))) throw new Error("Số dư lưu không hợp lệ.");
  const ids = new Set<string>();
  let principal = 0n;
  for (const p of state.positions) {
    if (!uint(p.id) || BigInt(p.id) >= BigInt(state.nextId) || ids.has(p.id) || !isAddress(p.owner) ||
        !uint(p.principalWad) || !uint(p.interestWad) || !uint(p.remainder) ||
        BigInt(p.remainder) >= INTEREST_DENOMINATOR || !Number.isSafeInteger(p.openedAt) ||
        p.openedAt < 0 || p.openedAt > state.checkpointAt || claimable(p) <= 0n) throw new Error("NFT lưu không hợp lệ.");
    ids.add(p.id); principal += BigInt(p.principalWad);
  }
  if (principal !== BigInt(state.totalSuppliedWad)) throw new Error("Tổng vốn gốc lưu không khớp.");
  // Activity is display-only. Reject malformed entries rather than trusting localStorage.
  if (state.activity.length > 80 || state.activity.some((a) => !a || typeof a.id !== "string" ||
      !["supply", "withdraw", "transfer", "faucet"].includes(a.kind) || !isAddress(a.actor) ||
      !uint(a.amountWad) || !Number.isSafeInteger(a.at) || a.at < 0 || a.at > state.checkpointAt ||
      (a.positionId !== undefined && !uint(a.positionId)) || (a.recipient !== undefined && !isAddress(a.recipient)))) {
    throw new Error("Lịch sử lưu không hợp lệ.");
  }
  return state;
}
