const fs = require("node:fs");
const path = require("node:path");
const hre = require("hardhat");
const { H02_NAMES, exportH02 } = require("./export_h02");

async function main() {
  if (hre.network.name !== "localhost") {
    throw new Error("H02 deployment requires --network localhost; Sepolia rollout belongs to Q06.");
  }
  const network = await hre.ethers.provider.getNetwork();
  const root = hre.config.paths.root;
  const manifestPath = path.join(root, "deployments/localhost.json");
  const registryPath = path.join(root, "backend/config/contracts.json");
  const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
  const registry = JSON.parse(fs.readFileSync(registryPath, "utf8"));
  if (
    network.chainId !== BigInt(hre.config.networks.localhost.chainId) ||
    network.chainId !== BigInt(manifest.chainId) ||
    network.chainId !== BigInt(registry.local.chainId)
  ) {
    throw new Error("The local RPC, Q01 configuration and deployment files must use the same Chain ID.");
  }
  if (registry.local.contracts.LendingPool.address) {
    throw new Error("A LendingPool is already registered. Coordinate token redeployment with HI02 before replacing its token addresses.");
  }
  const myusdt = registry.local.contracts.MyUSDT.address;
  if (!hre.ethers.isAddress(myusdt) || await hre.ethers.provider.getCode(myusdt) === "0x") {
    throw new Error("Missing H01 deployment on this node. Run npm run deploy:myusdt first.");
  }
  const payment = await hre.ethers.getContractAt("MyUSDT", myusdt);
  if (await payment.decimals() !== 18n) throw new Error("H01 MyUSDT must use 18 decimals.");

  const abiPaths = await exportH02(hre);
  const [deployer] = await hre.ethers.getSigners();
  const rows = [];
  for (const name of H02_NAMES) {
    const token = await hre.ethers.deployContract(name, [], deployer);
    await token.waitForDeployment();
    const receipt = await token.deploymentTransaction().wait();
    const address = await token.getAddress();
    const poolBound = name !== "CollateralNFT";
    const entry = {
      address,
      txHash: receipt.hash,
      blockNumber: receipt.blockNumber,
      abiPath: abiPaths[name],
      owner: await token.owner(),
      status: poolBound ? "AWAITING_HI02_POOL" : "DEPLOYED",
      ...(poolBound ? { lendingPool: await token.lendingPool() } : {}),
    };
    manifest.contracts[name] = entry;
    registry.local.contracts[name] = {
      ...registry.local.contracts[name], address, abiPath: abiPaths[name], txHash: receipt.hash,
    };
    rows.push({ name, address, status: entry.status });
  }
  manifest.deployedAt = new Date().toISOString();
  fs.writeFileSync(manifestPath, JSON.stringify(manifest, null, 2) + "\n", "utf8");
  fs.writeFileSync(registryPath, JSON.stringify(registry, null, 2) + "\n", "utf8");
  console.table(rows);
  console.log("Exported 4 contract artifacts and 4 canonical interface artifacts.");
  console.log("Pool binding is pending HI02. No test caller or substitute LendingPool was deployed.");
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
