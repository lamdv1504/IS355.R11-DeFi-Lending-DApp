const fs = require("node:fs");
const path = require("node:path");
const hre = require("hardhat");
const { exportHI02 } = require("./export_hi02");

const POOL_BOUND_TOKENS = ["DebtToken", "CollateralReceiptNFT", "LendingPositionNFT"];

async function main() {
  if (hre.network.name !== "localhost") {
    throw new Error("HI02 deployment requires --network localhost; Sepolia rollout belongs to Q06.");
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
    throw new Error("Chain ID mismatch between localhost RPC, hardhat config, and manifests.");
  }

  const requiredNames = ["MyUSDT", "CollateralNFT", ...POOL_BOUND_TOKENS];
  const addresses = {};
  for (const name of requiredNames) {
    const addr = registry.local.contracts[name]?.address;
    if (!hre.ethers.isAddress(addr) || (await hre.ethers.provider.getCode(addr)) === "0x") {
      throw new Error(
        `Missing deployed ${name} on localhost. Run \`npm run deploy:myusdt\` and \`npm run deploy:h02\` first.`
      );
    }
    addresses[name] = addr;
  }

  const [deployer] = await hre.ethers.getSigners();
  const abiPaths = await exportHI02(hre);

  // Deploy LendingPool with priceOracle = ZeroAddress (bound later in HI05)
  const pool = await hre.ethers.deployContract(
    "LendingPool",
    [
      addresses.MyUSDT,
      addresses.MyUSDT, // Default ERC-20 collateral token (segregated via totalTokenCollateralLocked)
      addresses.CollateralNFT,
      addresses.CollateralReceiptNFT,
      addresses.DebtToken,
      addresses.LendingPositionNFT,
      hre.ethers.ZeroAddress,
    ],
    deployer
  );
  await pool.waitForDeployment();
  const deployReceipt = await pool.deploymentTransaction().wait();
  const poolAddress = await pool.getAddress();

  // Bind H02 PoolControlled tokens once to LendingPool
  const bindTxHashes = {};
  for (const name of POOL_BOUND_TOKENS) {
    const token = await hre.ethers.getContractAt(name, addresses[name], deployer);
    const currentPool = await token.lendingPool();
    if (currentPool !== hre.ethers.ZeroAddress) {
      throw new Error(
        `${name} is already bound to ${currentPool}. Restart local node and redeploy H01 + H02 before deploying a fresh LendingPool.`
      );
    }
    const tx = await token.setLendingPool(poolAddress);
    const receipt = await tx.wait();
    if ((await token.lendingPool()) !== poolAddress) {
      throw new Error(`Pool binding verification failed for ${name}`);
    }
    bindTxHashes[name] = receipt.hash;

    if (manifest.contracts[name]) {
      manifest.contracts[name].status = "BOUND_TO_POOL";
      manifest.contracts[name].lendingPool = poolAddress;
      manifest.contracts[name].bindTxHash = receipt.hash;
    }
  }

  // Verify LendingPool getters point to exact H01/H02 addresses
  if (
    (await pool.myUSDT()) !== addresses.MyUSDT ||
    (await pool.collateralNFT()) !== addresses.CollateralNFT ||
    (await pool.collateralReceiptNFT()) !== addresses.CollateralReceiptNFT ||
    (await pool.debtToken()) !== addresses.DebtToken ||
    (await pool.lendingPositionNFT()) !== addresses.LendingPositionNFT
  ) {
    throw new Error("LendingPool getter address mismatch after deployment.");
  }

  manifest.contracts.LendingPool = {
    address: poolAddress,
    txHash: deployReceipt.hash,
    blockNumber: deployReceipt.blockNumber,
    deployer: deployer.address,
    abiPath: abiPaths.LendingPool,
    interfaceAbiPath: abiPaths.ILendingPool,
    status: "DEPLOYED_AND_BOUND",
    boundTokens: bindTxHashes,
    priceOracle: hre.ethers.ZeroAddress,
  };
  manifest.deployedAt = new Date().toISOString();

  registry.local.contracts.LendingPool = {
    ...registry.local.contracts.LendingPool,
    address: poolAddress,
    abiPath: abiPaths.LendingPool,
    txHash: deployReceipt.hash,
  };

  fs.writeFileSync(manifestPath, JSON.stringify(manifest, null, 2) + "\n", "utf8");
  fs.writeFileSync(registryPath, JSON.stringify(registry, null, 2) + "\n", "utf8");

  console.table([
    { name: "LendingPool", address: poolAddress, status: "DEPLOYED_AND_BOUND" },
    ...POOL_BOUND_TOKENS.map((name) => ({
      name,
      address: addresses[name],
      status: "BOUND_TO_POOL",
    })),
  ]);
  console.log("Exported deployments/abi/LendingPool.json and deployments/abi/interfaces/ILendingPool.json.");
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
