const fs = require("node:fs");
const path = require("node:path");
const hre = require("hardhat");
const { exportMyUSDT } = require("./export_myusdt");

const ROLES = [
  "Deployer / Admin / System Seed",
  "Lender A",
  "Borrower A",
  "Lender B",
  "Liquidator / Keeper",
  "Borrower B",
  "Hung",
  "Hieu",
  "Quan",
  "Lam",
];

async function main() {
  if (hre.network.name !== "localhost") {
    throw new Error("H01 deployment requires --network localhost (Q01). Sepolia deployment belongs to Q06.");
  }

  const network = await hre.ethers.provider.getNetwork();
  if (network.chainId !== BigInt(hre.config.networks.localhost.chainId)) {
    throw new Error("RPC chain ID does not match the Q01 localhost configuration.");
  }
  const signers = await hre.ethers.getSigners();
  if (signers.length < ROLES.length) {
    throw new Error("Q01 must provide all 10 local test accounts before H01 deployment.");
  }

  // Read the Q01 handoff files before sending transactions; preserve other contracts.
  const deploymentPath = path.join(hre.config.paths.root, "deployments/localhost.json");
  const registryPath = path.join(hre.config.paths.root, "backend/config/contracts.json");
  const deployment = JSON.parse(fs.readFileSync(deploymentPath, "utf8"));
  const registry = JSON.parse(fs.readFileSync(registryPath, "utf8"));
  if (
    deployment.chainId !== Number(network.chainId) ||
    registry.local.chainId !== Number(network.chainId)
  ) {
    throw new Error("Q01 deployment/registry chain IDs do not match the connected local node.");
  }
  const abiPath = await exportMyUSDT(hre);

  const [deployer] = signers;
  const token = await hre.ethers.deployContract("MyUSDT", [], deployer);
  await token.waitForDeployment();
  const receipt = await token.deploymentTransaction().wait();
  const address = await token.getAddress();
  const faucetAmount = await token.MAX_FAUCET_AMOUNT();
  const decimals = Number(await token.decimals());

  const testAccounts = [];
  for (let index = 0; index < ROLES.length; index++) {
    const accountAddress = await signers[index].getAddress();
    let seedTxHash = null;
    if (index > 0) {
      const seedReceipt = await (await token.faucet(accountAddress, faucetAmount)).wait();
      seedTxHash = seedReceipt.hash;
    }
    const balance = await token.balanceOf(accountAddress);
    testAccounts.push({
      index,
      role: ROLES[index],
      address: accountAddress,
      balance: balance.toString(),
      balanceMyUSDT: hre.ethers.formatUnits(balance, decimals),
      seedTxHash,
    });
  }

  const tokenDeployment = {
    address,
    txHash: receipt.hash,
    blockNumber: receipt.blockNumber,
    deployer: await deployer.getAddress(),
    abiPath,
    decimals,
    initialSupply: (await token.INITIAL_SUPPLY()).toString(),
    maxFaucetAmount: faucetAmount.toString(),
    totalSupplyAfterSeed: (await token.totalSupply()).toString(),
    testAccounts,
  };
  deployment.deployedAt = new Date().toISOString();
  deployment.contracts.MyUSDT = tokenDeployment;
  registry.local.contracts.MyUSDT = {
    ...registry.local.contracts.MyUSDT,
    address,
    abiPath,
    txHash: receipt.hash,
  };
  fs.writeFileSync(deploymentPath, JSON.stringify(deployment, null, 2) + "\n", "utf8");
  fs.writeFileSync(registryPath, JSON.stringify(registry, null, 2) + "\n", "utf8");

  console.log("MyUSDT deployed on localhost (Chain ID " + network.chainId + "): " + address);
  console.log("Deployment transaction: " + receipt.hash);
  console.log("ABI and bytecode: " + abiPath);
  console.table(testAccounts.map(({ index, role, address, balanceMyUSDT }) => ({
    index, role, address, balanceMyUSDT,
  })));
  console.log("Saved deployments/localhost.json and backend/config/contracts.json.");
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
