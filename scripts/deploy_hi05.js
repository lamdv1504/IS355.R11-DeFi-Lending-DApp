const fs = require("node:fs");
const path = require("node:path");
const hre = require("hardhat");
const { exportHI05 } = require("./export_hi05");

async function main() {
  if (hre.network.name !== "localhost") {
    throw new Error("HI05 local deployment requires --network localhost; Sepolia rollout belongs to Q06.");
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

  const collateralNFTAddr = registry.local.contracts.CollateralNFT?.address;
  const lendingPoolAddr = registry.local.contracts.LendingPool?.address;
  for (const [name, addr] of [
    ["CollateralNFT", collateralNFTAddr],
    ["LendingPool", lendingPoolAddr],
  ]) {
    if (!hre.ethers.isAddress(addr) || (await hre.ethers.provider.getCode(addr)) === "0x") {
      throw new Error(
        `Missing deployed ${name} on localhost. Deploy H01 -> H02 -> HI02 before running deploy:hi05.`
      );
    }
  }

  const [deployer] = await hre.ethers.getSigners();
  const abiPaths = await exportHI05(hre);

  // Deploy PriceOracle wired to H02 CollateralNFT
  const oracle = await hre.ethers.deployContract("PriceOracle", [collateralNFTAddr], deployer);
  await oracle.waitForDeployment();
  const deployReceipt = await oracle.deploymentTransaction().wait();
  const oracleAddress = await oracle.getAddress();

  // Bind PriceOracle on LendingPool (owner-only)
  const pool = await hre.ethers.getContractAt("LendingPool", lendingPoolAddr, deployer);
  const bindTx = await pool.setPriceOracle(oracleAddress);
  const bindReceipt = await bindTx.wait();

  if ((await pool.priceOracle()) !== oracleAddress) {
    throw new Error("PriceOracle binding verification failed on LendingPool.");
  }

  const tokenPriceWad = await oracle.getCollateralTokenPrice();
  const multiplierBps = await oracle.priceMultiplierBps();

  manifest.contracts.PriceOracle = {
    address: oracleAddress,
    txHash: deployReceipt.hash,
    blockNumber: deployReceipt.blockNumber,
    deployer: deployer.address,
    owner: await oracle.owner(),
    collateralNFT: collateralNFTAddr,
    abiPath: abiPaths.PriceOracle,
    interfaceAbiPath: abiPaths.IPriceOracle,
    status: "DEPLOYED_AND_BOUND",
    lendingPool: lendingPoolAddr,
    bindTxHash: bindReceipt.hash,
    collateralTokenPriceWad: tokenPriceWad.toString(),
    priceMultiplierBps: multiplierBps.toString(),
  };

  if (manifest.contracts.LendingPool) {
    manifest.contracts.LendingPool.priceOracle = oracleAddress;
    manifest.contracts.LendingPool.priceOracleBindTxHash = bindReceipt.hash;
  }
  manifest.deployedAt = new Date().toISOString();

  registry.local.contracts.PriceOracle = {
    ...registry.local.contracts.PriceOracle,
    address: oracleAddress,
    abiPath: abiPaths.PriceOracle,
    txHash: deployReceipt.hash,
  };

  fs.writeFileSync(manifestPath, JSON.stringify(manifest, null, 2) + "\n", "utf8");
  fs.writeFileSync(registryPath, JSON.stringify(registry, null, 2) + "\n", "utf8");

  console.table([
    {
      name: "PriceOracle",
      address: oracleAddress,
      status: "DEPLOYED_AND_BOUND",
      multiplierBps: multiplierBps.toString(),
    },
    {
      name: "LendingPool",
      address: lendingPoolAddr,
      status: "ORACLE_BOUND",
      multiplierBps: multiplierBps.toString(),
    },
  ]);
  console.log("Exported PriceOracle/IPriceOracle/LendingPool/ILendingPool ABIs and updated manifests.");
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
