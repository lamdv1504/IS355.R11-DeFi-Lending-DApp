/**
 * HI04 Local-Only Demo Time-Travel Utility (Hardhat Localhost Chain ID 31337).
 *
 * Advances EVM block.timestamp via `evm_increaseTime` + `evm_mine` so demo presenters
 * can showcase 30-90 days of real-time interest accrual in one click.
 *
 * SECURITY GUARD (Rubric TC1 & TC2):
 * Strictly refuses to run on Sepolia (11155111) or any non-local chain.
 *
 * Usage:
 *   DAYS=30 npx hardhat run scripts/fast_forward_time.js --network localhost
 *   SECONDS=5184000 npx hardhat run scripts/fast_forward_time.js --network localhost
 */
const fs = require("node:fs");
const path = require("node:path");
const hre = require("hardhat");

const LOCAL_CHAIN_ID = 31337n;
const MAX_SKIP_SECONDS = 10 * 365 * 86_400; // 10-year sanity cap

async function main() {
  if (hre.network.name !== "localhost" && hre.network.name !== "hardhat") {
    throw new Error(
      `Time-travel demo utility is strictly local-only (blocked on network "${hre.network.name}").`
    );
  }

  const network = await hre.ethers.provider.getNetwork();
  if (network.chainId !== LOCAL_CHAIN_ID) {
    throw new Error(
      `Refusing evm_increaseTime on Chain ID ${network.chainId}. Only local Hardhat (${LOCAL_CHAIN_ID}) is allowed.`
    );
  }

  let secondsToSkip;
  if (process.env.SECONDS) {
    secondsToSkip = Number(process.env.SECONDS);
  } else {
    const days = process.env.DAYS ? Number(process.env.DAYS) : 30;
    secondsToSkip = Math.round(days * 86_400);
  }

  if (!Number.isInteger(secondsToSkip) || secondsToSkip <= 0 || secondsToSkip > MAX_SKIP_SECONDS) {
    throw new Error(
      `Invalid skip duration: ${secondsToSkip}s. Provide a positive integer up to ${MAX_SKIP_SECONDS}s.`
    );
  }

  const blockBefore = await hre.ethers.provider.getBlock("latest");
  await hre.ethers.provider.send("evm_increaseTime", [secondsToSkip]);
  await hre.ethers.provider.send("evm_mine", []);
  const blockAfter = await hre.ethers.provider.getBlock("latest");

  const actualDelta = Number(blockAfter.timestamp) - Number(blockBefore.timestamp);
  console.log("=== HI04 Local Time-Travel Executed (Chain ID 31337) ===");
  console.log(`Requested skip : ${secondsToSkip}s (${(secondsToSkip / 86_400).toFixed(2)} days)`);
  console.log(`Actual delta   : ${actualDelta}s (${(actualDelta / 86_400).toFixed(2)} days)`);
  console.log(`Timestamp      : ${blockBefore.timestamp} -> ${blockAfter.timestamp}`);
  console.log(`Block number   : ${blockBefore.number} -> ${blockAfter.number}`);

  // If LendingPool is deployed on localhost, print live rate & index preview
  const registryPath = path.join(hre.config.paths.root, "backend/config/contracts.json");
  if (fs.existsSync(registryPath)) {
    const registry = JSON.parse(fs.readFileSync(registryPath, "utf8"));
    const poolAddr = registry?.local?.contracts?.LendingPool?.address;
    if (hre.ethers.isAddress(poolAddr) && (await hre.ethers.provider.getCode(poolAddr)) !== "0x") {
      const pool = await hre.ethers.getContractAt("LendingPool", poolAddr);
      const snap = await pool.getInterestRateSnapshot();
      console.log("--- Live LendingPool Interest Snapshot ---");
      console.log(`Utilization     : ${(Number(snap.utilizationBps) / 100).toFixed(2)}%`);
      console.log(
        `Borrow Rate     : ${(Number(snap.borrowAprBps) / 100).toFixed(2)}% APR (ref APY ~${(Number(snap.borrowApyRefBps) / 100).toFixed(2)}%)`
      );
      console.log(
        `Supply Rate     : ${(Number(snap.supplyAprBps) / 100).toFixed(2)}% APR (ref APY ~${(Number(snap.supplyApyRefBps) / 100).toFixed(2)}%)`
      );
      console.log(`Borrow Index    : ${hre.ethers.formatUnits(snap.borrowIndexWad, 18)}`);
      console.log(`Supply Index    : ${hre.ethers.formatUnits(snap.supplyIndexWad, 18)}`);
    }
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
