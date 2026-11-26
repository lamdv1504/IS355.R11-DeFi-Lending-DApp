import assert from "node:assert/strict";
import test from "node:test";
import { ACCOUNTS, WAD, applyDemoAction, checkpoint, claimable, createDemo, parseAmount, rates, restoreDemo, withdrawLimit } from "../src/lib/lending-demo.ts";

const A = ACCOUNTS[0].address;
const B = ACCOUNTS[1].address;
const start = 1700000000000;
const day = 86400000;

test("HI01 sample: U 50%, borrow APR 10%, supply APR 5%, APY reference", () => {
  const r = rates(String(1000n * WAD), String(500n * WAD));
  assert.equal(r.utilizationBps, 5000);
  assert.equal(r.borrowAprBps, 1000);
  assert.equal(r.supplyAprBps, 500);
  assert.ok(Math.abs(r.supplyApy - 5.1267) < .0001);
  assert.equal(rates("0", "0").supplyAprBps, 0);
  assert.equal(rates("1", "100").utilizationBps, 10000);
});

test("amount parsing is exact to 18 decimals and accepts Vietnamese comma", () => {
  assert.equal(parseAmount("1,000000000000000001"), WAD + 1n);
  assert.equal(parseAmount(" 0.1 "), WAD / 10n);
  for (const bad of ["0", "-1", "1e3", "1.000,00", "1,000.00", "NaN", ".5", "0.0000000000000000001", ""]) {
    assert.throws(() => parseAmount(bad));
  }
});

test("supply mints a position and conserves wallet/pool cash; reject overspending", () => {
  const initial = createDemo(start);
  const next = applyDemoAction(initial, { kind: "supply", actor: B, amount: "250" }, start);
  assert.equal(next.positions[1].id, "2");
  assert.equal(next.positions[1].owner, B);
  assert.equal(next.totalSuppliedWad, String(1250n * WAD));
  assert.equal(next.availableLiquidityWad, String(750n * WAD));
  assert.equal(next.balances[B], String(1550n * WAD));
  assert.equal(initial.positions.length, 1);
  assert.throws(() => applyDemoAction(initial, { kind: "supply", actor: B, amount: "1800.1" }, start), /số dư/);
});

test("checkpoint uses old APR before a deposit and preserves fractional carry", () => {
  const initial = createDemo(start);
  const expectedOld = 1000n * WAD * 500n / (10000n * 365n);
  const next = applyDemoAction(initial, { kind: "supply", actor: B, amount: "1000" }, start + day);
  assert.equal(next.positions[0].interestWad, String(expectedOld));
  assert.equal(next.positions[1].interestWad, "0");
  const r = rates(next.totalSuppliedWad, next.totalBorrowedWad);
  const after = checkpoint(next, start + 2 * day);
  assert.ok(BigInt(after.positions[0].interestWad) > expectedOld);
  assert.equal(r.supplyAprBps, 187);
  const twice = checkpoint(checkpoint(initial, start + 12345), start + day);
  const once = checkpoint(initial, start + day);
  assert.deepEqual(twice.positions, once.positions);
  assert.deepEqual(checkpoint(once, start), once);
});

test("withdrawal validates available cash separately from total supplied and claim", () => {
  const initial = createDemo(start);
  assert.equal(withdrawLimit(initial, initial.positions[0]), 500n * WAD);
  assert.throws(() => applyDemoAction(initial, { kind: "withdraw", actor: A, positionId: "1", amount: "500.000000000000000001" }, start), /thanh khoản/);
  assert.throws(() => applyDemoAction(initial, { kind: "withdraw", actor: A, positionId: "1", amount: "1001" }, start), /quyền rút/);
  const next = applyDemoAction(initial, { kind: "withdraw", actor: A, positionId: "1", amount: "500" }, start);
  assert.equal(next.availableLiquidityWad, "0");
  assert.equal(next.totalSuppliedWad, String(500n * WAD));
  assert.equal(next.balances[A], String(3000n * WAD));
});

test("transfer retains accrued claim, rejects old owner, allows new owner to withdraw", () => {
  const initial = checkpoint(createDemo(start), start + day);
  const transferred = applyDemoAction(initial, { kind: "transfer", actor: A, positionId: "1", recipient: B }, start + day);
  assert.equal(transferred.positions[0].owner, B);
  assert.equal(claimable(transferred.positions[0]), claimable(initial.positions[0]));
  assert.throws(() => applyDemoAction(transferred, { kind: "withdraw", actor: A, positionId: "1", amount: "1" }, start + day), /không sở hữu/);
  const next = applyDemoAction(transferred, { kind: "withdraw", actor: B, positionId: "1", amount: "1" }, start + day);
  assert.equal(next.balances[B], String(1801n * WAD));
  assert.equal(claimable(next.positions[0]), claimable(initial.positions[0]) - WAD);
  for (const recipient of [A, "0x0000000000000000000000000000000000000000", "not-an-address"]) {
    assert.throws(() => applyDemoAction(initial, { kind: "transfer", actor: A, positionId: "1", recipient }, start + day));
  }
});

test("full withdrawal closes NFT; balances never underflow", () => {
  const state = applyDemoAction(createDemo(start), { kind: "supply", actor: B, amount: "100" }, start);
  const next = applyDemoAction(state, { kind: "withdraw", actor: B, positionId: "2", amount: "100" }, start);
  assert.equal(next.positions.length, 1);
  assert.equal(next.positions[0].id, "1");
  assert.equal(next.availableLiquidityWad, String(500n * WAD));
  assert.throws(() => applyDemoAction(next, { kind: "withdraw", actor: B, positionId: "2", amount: "1" }, start), /không sở hữu/);
});

test("stored state round trips and rejects corrupt versions, money and ownership", () => {
  const original = createDemo(start);
  assert.deepEqual(restoreDemo(JSON.stringify(original), start), original);
  const changes = [
    { ...original, version: 2 },
    { ...original, totalSuppliedWad: "-1" },
    { ...original, checkpointAt: start + 1 },
    { ...original, balances: {} },
    { ...original, positions: [{ ...original.positions[0], owner: "bad" }] },
    { ...original, positions: [] },
    { ...original, activity: [{ kind: "withdraw", amountWad: "bad" }] },
  ];
  for (const bad of changes) assert.throws(() => restoreDemo(JSON.stringify(bad), start));
});

test("faucet is a 1000 MyUSDT demo credit and does not inflate pool TVL", () => {
  const initial = createDemo(start);
  const next = applyDemoAction(initial, { kind: "faucet", actor: A }, start);
  assert.equal(BigInt(next.balances[A]) - BigInt(initial.balances[A]), 1000n * WAD);
  assert.equal(next.totalSuppliedWad, initial.totalSuppliedWad);
});
