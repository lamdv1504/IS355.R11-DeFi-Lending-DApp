import test from "node:test";
import assert from "node:assert/strict";
import { WAD } from "../src/lib/lending-demo.ts";
import { applyBorrowAction, borrowCheckpoint, borrowingCapacity, capacityLabel, collateralValue, createBorrowDemo, currentBorrowApr, formatHealthFactor, gasIllustration, healthFactor, prepareBorrowTransaction, referenceApy, restoreBorrowDemo, riskStatus, totalDebt, YEAR_SECONDS, type BorrowState } from "../src/lib/borrowing-demo.ts";

const now = 1700000000000;
const day = 86400000;
const approve = (state: BorrowState, actor: "borrower" | "liquidator", amount = "2000", at = now) =>
  applyBorrowAction(state, { kind: "approve", actor, amount }, at);

test("HI05 HF uses BPS/WAD, zero debt is infinite and boundaries are exact", () => {
  assert.equal(healthFactor(1000n * WAD, 500n * WAD), 16n * WAD / 10n);
  assert.equal(healthFactor(625n * WAD, 500n * WAD), WAD);
  assert.equal(healthFactor(1000n * WAD, 0n), null);
  assert.equal(riskStatus(null), "safe");
  assert.equal(riskStatus(WAD - 1n), "danger");
  assert.equal(riskStatus(WAD), "warning");
  assert.equal(riskStatus(15n * WAD / 10n - 1n), "warning");
  assert.equal(riskStatus(15n * WAD / 10n), "safe");
  assert.equal(formatHealthFactor(WAD - 1n), "0,9999");
  assert.equal(formatHealthFactor(null), "∞");
});

test("seed matches L01 1000 collateral / 500 debt and exposes 200 remaining capacity", () => {
  const s = createBorrowDemo(now);
  assert.equal(collateralValue(s), 1000n * WAD);
  assert.equal(totalDebt(s), 500n * WAD);
  assert.equal(borrowingCapacity(s), 200n * WAD);
  assert.equal(currentBorrowApr(s), 1000);
  assert.ok(Math.abs(referenceApy(1000) - 10.5156) < .0001);
});

test("LTV cap includes accrued interest and validates manual amounts down to one wei", () => {
  const initial = createBorrowDemo(now);
  assert.throws(() => applyBorrowAction(initial, { kind: "borrow", actor: "borrower", amount: "200.000000000000000001" }, now), /70%/);
  const advanced = borrowCheckpoint(initial, now + day);
  assert.ok(borrowingCapacity(advanced) < 200n * WAD);
  assert.throws(() => applyBorrowAction(initial, { kind: "borrow", actor: "borrower", amount: "200" }, now + day), /70%/);
  const next = applyBorrowAction(initial, { kind: "borrow", actor: "borrower", amount: "200" }, now);
  assert.equal(next.loan.principalWad, String(700n * WAD));
  assert.equal(next.poolCashWad, String(300n * WAD));
  assert.equal(next.wallets.borrower.balanceWad, String(1700n * WAD));
  assert.equal(currentBorrowApr(next), 1200);
});

test("pool liquidity is checked separately from total supplied", () => {
  const initial = { ...createBorrowDemo(now), poolCashWad: String(20n * WAD) };
  assert.equal(borrowingCapacity(initial), 20n * WAD);
  assert.throws(() => applyBorrowAction(initial, { kind: "borrow", actor: "borrower", amount: "21" }, now), /thanh khoản/);
});

test("HI04 cumulative index settles old APR before borrow, then changes only future interest", () => {
  const initial = createBorrowDemo(now);
  const firstIndexDelta = WAD * 1000n * 86400n / (YEAR_SECONDS * 10000n);
  const expectedOldInterest = 500n * WAD * firstIndexDelta / WAD;
  const next = applyBorrowAction(initial, { kind: "borrow", actor: "borrower", amount: "100" }, now + day);
  assert.equal(BigInt(next.loan.interestWad), expectedOldInterest);
  assert.equal(next.borrowIndexWad, String(WAD + firstIndexDelta));
  const projected = borrowCheckpoint(next, now + 2 * day);
  const newDelta = WAD * 1100n * 86400n / (YEAR_SECONDS * 10000n);
  assert.equal(BigInt(projected.loan.interestWad), expectedOldInterest + 600n * WAD * newDelta / WAD);
  assert.equal(initial.loan.interestWad, "0");
});

test("approvals, price changes and time travel do not mutate pool interest indices", () => {
  const initial = createBorrowDemo(now);
  let s = approve(initial, "borrower", "1000", now + day);
  s = applyBorrowAction(s, { kind: "price", multiplierBps: 8000 }, now + 2 * day);
  s = applyBorrowAction(s, { kind: "advance", seconds: 30 * 86400 }, now + 2 * day);
  assert.equal(s.borrowIndexWad, initial.borrowIndexWad);
  assert.equal(s.loan.interestWad, "0");
  assert.equal(s.indexAt, initial.indexAt);
  const current = borrowCheckpoint(s, now + 2 * day);
  assert.ok(BigInt(current.loan.interestWad) > 4n * WAD);
  assert.doesNotThrow(() => restoreBorrowDemo(JSON.stringify(s), now + 2 * day));
});

test("price decrease changes risk without automatically liquidating or transferring NFT", () => {
  const initial = createBorrowDemo(now);
  const yellow = applyBorrowAction(initial, { kind: "price", multiplierBps: 8000 }, now);
  assert.equal(riskStatus(healthFactor(collateralValue(yellow), totalDebt(yellow))), "warning");
  const red = applyBorrowAction(yellow, { kind: "price", multiplierBps: 6000 }, now);
  assert.equal(healthFactor(collateralValue(red), totalDebt(red)), 96n * WAD / 100n);
  assert.equal(red.loan.principalWad, String(500n * WAD));
  assert.equal(red.loan.active, true);
  assert.equal(red.nftOwner, "pool");
});

test("HF exactly one blocks liquidation; one wei below is not rounded up by UI", () => {
  let exact = applyBorrowAction(createBorrowDemo(now), { kind: "price", multiplierBps: 6250 }, now);
  exact = approve(exact, "liquidator");
  assert.throws(() => applyBorrowAction(exact, { kind: "liquidate", actor: "liquidator" }, now), /HF = 1/);
  assert.equal(exact.loan.active, true);
});

test("repayment needs separate allowance and pays accrued interest before burning principal", () => {
  const initial = createBorrowDemo(now);
  assert.throws(() => applyBorrowAction(initial, { kind: "repay", actor: "borrower", amount: "1", full: false }, now), /cấp quyền/);
  const approved = approve(initial, "borrower", "1000", now + 30 * day);
  const before = borrowCheckpoint(approved, now + 30 * day);
  const next = applyBorrowAction(approved, { kind: "repay", actor: "borrower", amount: "10", full: false }, now + 30 * day);
  assert.equal(next.loan.interestWad, "0");
  assert.equal(BigInt(next.loan.principalWad), 500n * WAD - (10n * WAD - BigInt(before.loan.interestWad)));
  assert.equal(BigInt(next.poolCashWad), BigInt(before.poolCashWad) + 10n * WAD);
});

test("repay all recomputes latest debt, settles receipt and returns NFT", () => {
  const approved = approve(createBorrowDemo(now), "borrower", "1000");
  const current = borrowCheckpoint(approved, now + 30 * day);
  const next = applyBorrowAction(approved, { kind: "repay", actor: "borrower", amount: "1", full: true }, now + 30 * day);
  assert.equal(totalDebt(next), 0n);
  assert.equal(next.loan.active, false);
  assert.equal(next.loan.receiptStatus, "settled");
  assert.equal(next.nftOwner, "borrower");
  assert.equal(next.poolBorrowedWad, "0");
  assert.equal(BigInt(next.wallets.borrower.balanceWad), 1500n * WAD - totalDebt(current));
});

test("repayment above total debt is capped like LendingPool", () => {
  const initial = approve(createBorrowDemo(now), "borrower", "1000");
  const next = applyBorrowAction(initial, { kind: "repay", actor: "borrower", amount: "999", full: false }, now);
  assert.equal(next.wallets.borrower.balanceWad, String(1000n * WAD));
  assert.equal(next.wallets.borrower.allowanceWad, String(500n * WAD));
  assert.equal(next.loan.active, false);
});

test("NFT deposit and manual collateral withdrawal require ownership, approval and zero debt", () => {
  const empty = createBorrowDemo(now, true);
  assert.throws(() => applyBorrowAction(empty, { kind: "deposit", actor: "borrower", asset: "nft", amount: "" }, now), /cấp quyền/);
  const approved = applyBorrowAction(empty, { kind: "approve-nft", actor: "borrower" }, now);
  const locked = applyBorrowAction(approved, { kind: "deposit", actor: "borrower", asset: "nft", amount: "" }, now);
  assert.equal(locked.nftOwner, "pool");
  assert.equal(locked.loan.receiptId, "1");
  assert.throws(() => applyBorrowAction(createBorrowDemo(now), { kind: "withdraw", actor: "borrower" }, now), /tổng nợ/);
  const released = applyBorrowAction(locked, { kind: "withdraw", actor: "borrower" }, now);
  assert.equal(released.nftOwner, "borrower");
  assert.equal(released.loan.receiptStatus, "settled");
});

test("NFT liquidation transfers whole NFT, burns debt and cannot execute twice", () => {
  let s = applyBorrowAction(createBorrowDemo(now), { kind: "price", multiplierBps: 6000 }, now);
  assert.throws(() => applyBorrowAction(s, { kind: "liquidate", actor: "liquidator" }, now), /cấp quyền/);
  s = approve(s, "liquidator");
  const next = applyBorrowAction(s, { kind: "liquidate", actor: "liquidator" }, now);
  assert.equal(next.nftOwner, "liquidator");
  assert.equal(next.wallets.liquidator.balanceWad, String(1500n * WAD));
  assert.equal(next.loan.receiptStatus, "liquidated");
  assert.equal(next.poolCashWad, String(1000n * WAD));
  assert.equal(next.poolBorrowedWad, "0");
  assert.throws(() => applyBorrowAction(next, { kind: "liquidate", actor: "liquidator" }, now));
  assert.throws(() => applyBorrowAction(next, { kind: "approve-nft", actor: "borrower" }, now), /không sở hữu/);
});

test("ERC20 liquidation applies the 5% bonus cap and refunds unseized tokens", () => {
  let s = approve(createBorrowDemo(now, true), "borrower", "1000");
  s = applyBorrowAction(s, { kind: "deposit", actor: "borrower", asset: "token", amount: "1000" }, now);
  assert.equal(s.poolCashWad, String(1000n * WAD)); // locked collateral is not free liquidity
  s = applyBorrowAction(s, { kind: "borrow", actor: "borrower", amount: "500" }, now);
  s = applyBorrowAction(s, { kind: "price", multiplierBps: 6000 }, now);
  s = approve(s, "liquidator");
  const next = applyBorrowAction(s, { kind: "liquidate", actor: "liquidator" }, now);
  assert.equal(next.wallets.liquidator.balanceWad, String((2000n - 500n + 875n) * WAD));
  assert.equal(next.wallets.borrower.balanceWad, String((500n + 125n) * WAD));
  assert.equal(next.loan.collateralUnitsWad, "0");
  assert.equal(next.loan.receiptStatus, "liquidated");
});

test("insufficient liquidator balance blocks settlement and preserves original state", () => {
  let s = applyBorrowAction(createBorrowDemo(now), { kind: "price", multiplierBps: 6000 }, now);
  s = approve(s, "liquidator");
  s.wallets.liquidator.balanceWad = String(499n * WAD);
  assert.throws(() => applyBorrowAction(s, { kind: "liquidate", actor: "liquidator" }, now), /không đủ/);
  assert.equal(s.loan.active, true);
  assert.equal(s.nftOwner, "pool");
});

test("quotation exposes approvals without mutating them; execution still rejects missing allowance", () => {
  const s = createBorrowDemo(now);
  const action = { kind: "repay" as const, actor: "borrower" as const, amount: "100", full: false };
  const preview = prepareBorrowTransaction(s, action);
  assert.equal(preview.needsApproval, true);
  assert.equal(totalDebt(preview.after), 400n * WAD);
  assert.equal(s.wallets.borrower.allowanceWad, "0");
  assert.throws(() => applyBorrowAction(s, action, now), /cấp quyền/);
});

test("gas illustration distinguishes units, gwei and ETH with an explicit 20% limit", () => {
  const gas = gasIllustration("borrow", "2");
  assert.equal(gas.kind, "SIMULATED");
  assert.equal(gas.units, 180000);
  assert.equal(gas.gasLimit, 216000);
  assert.equal(gas.feeEth, "0.00036");
  assert.equal(gas.maximumEth, "0.000432");
  assert.equal(gasIllustration("borrow", "0,5").feeEth, "0.00009");
  for (const bad of ["0", "-1", "1e3", "0.0000000001", "10001", ""]) assert.throws(() => gasIllustration("borrow", bad));
});

test("persisted borrowing state validates schema, index, balances and debt consistency", () => {
  const original = createBorrowDemo(now);
  assert.deepEqual(restoreBorrowDemo(JSON.stringify(original), now), original);
  for (const s of [
    { ...original, version: 2 }, { ...original, poolBorrowedWad: "1" },
    { ...original, indexAt: now }, { ...original, priceBps: 0 },
    { ...original, wallets: {} }, { ...original, loan: { ...original.loan, indexSnapshotWad: "0" } },
    { ...original, activity: [{ id: 1, label: "bad", at: 1 }] },
  ]) assert.throws(() => restoreBorrowDemo(JSON.stringify(s), now));
});

test("faucet changes selected demo balance only; no pool/debt inflation", () => {
  const original = createBorrowDemo(now);
  const next = applyBorrowAction(original, { kind: "faucet", actor: "liquidator" }, now);
  assert.equal(next.wallets.liquidator.balanceWad, String(3000n * WAD));
  assert.equal(next.poolCashWad, original.poolCashWad);
  assert.equal(next.loan.principalWad, original.loan.principalWad);
});

test("stored collateral ownership and receipt IDs must remain internally consistent", () => {
  const original = createBorrowDemo(now);
  const broken = [
    { ...original, nextReceiptId: "0" },
    { ...original, loan: { ...original.loan, receiptId: "0" } },
    { ...original, loan: { ...original.loan, collateralUnitsWad: "1" } },
    { ...createBorrowDemo(now, true), nftOwner: "pool" },
  ];
  for (const data of broken) assert.throws(() => restoreBorrowDemo(JSON.stringify(data), now));
  const paid = applyBorrowAction(approve(original, "borrower"), { kind: "repay", actor: "borrower", amount: "500", full: true }, now);
  assert.deepEqual(restoreBorrowDemo(JSON.stringify(paid), now), paid);
});

test("visible borrowing capacity is floored so it never suggests an inadmissible rounded maximum", () => {
  assert.equal(capacityLabel(200n * WAD - 1n, 4), "199,9999");
  assert.equal(capacityLabel(200n * WAD, 4), "200");
  assert.equal(capacityLabel(1n, 8), "0");
});
