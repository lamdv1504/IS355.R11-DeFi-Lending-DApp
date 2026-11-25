const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const hre = require("hardhat");
const { H02_NAMES } = require("./export_h02");

async function main() {
  if (hre.network.name !== "localhost") throw new Error("Verify H02 using --network localhost.");
  const root = hre.config.paths.root;
  const manifest = JSON.parse(fs.readFileSync(path.join(root, "deployments/localhost.json"), "utf8"));
  const registry = JSON.parse(fs.readFileSync(path.join(root, "backend/config/contracts.json"), "utf8"));
  const chainId = Number((await hre.ethers.provider.getNetwork()).chainId);
  assert.equal(chainId, manifest.chainId);
  assert.equal(chainId, registry.local.chainId);
  assert.equal(registry.local.contracts.LendingPool.address, "", "HI02 is not part of this unbound H02 verification.");
  const contracts = {};
  for (const name of ["MyUSDT", ...H02_NAMES]) {
    const entry = manifest.contracts[name];
    assert.equal(registry.local.contracts[name].address, entry.address);
    assert.equal(registry.local.contracts[name].abiPath, entry.abiPath);
    const artifact = JSON.parse(fs.readFileSync(path.join(root, entry.abiPath), "utf8"));
    assert.deepEqual(artifact, await hre.artifacts.readArtifact(name));
    const code = await hre.ethers.provider.getCode(entry.address);
    assert.notEqual(code, "0x");
    assert.equal(code, artifact.deployedBytecode);
    const receipt = await hre.ethers.provider.getTransactionReceipt(entry.txHash);
    assert.equal(receipt.status, 1);
    assert.equal(receipt.contractAddress, entry.address);
    assert.equal(receipt.blockNumber, entry.blockNumber);
    const token = await hre.ethers.getContractAt(name, entry.address);
    assert.equal(await token.owner(), entry.owner || entry.deployer);
    if (name !== "MyUSDT" && name !== "CollateralNFT") {
      assert.equal(await token.lendingPool(), hre.ethers.ZeroAddress);
      assert.equal(entry.status, "AWAITING_HI02_POOL");
    }
    if (name === "DebtToken") {
      assert.equal(await token.decimals(), 18n);
      assert.equal(await token.totalSupply(), 0n);
    }
    contracts[name] = {
      address: entry.address, txHash: entry.txHash, blockNumber: receipt.blockNumber,
      runtimeCodeHash: hre.ethers.keccak256(code), abiMatchesBuild: true, owner: await token.owner(),
      ...(name !== "MyUSDT" && name !== "CollateralNFT" ? { lendingPool: await token.lendingPool() } : {}),
    };
  }
  const myusdt = await hre.ethers.getContractAt("MyUSDT", manifest.contracts.MyUSDT.address);
  for (const account of manifest.contracts.MyUSDT.testAccounts) {
    assert.equal(await myusdt.balanceOf(account.address), BigInt(account.balance));
  }
  const canonicalFunctions = {
    ICollateralNFT: ["mintCollateral(address,uint256,string)", "valuation(uint256)", "setValuation(uint256,uint256)"],
    ICollateralReceiptNFT: ["mintReceipt(address,bool,uint256)", "settleReceipt(uint256,bool)", "getReceiptInfo(uint256)", "lendingPool()"],
    ILendingPositionNFT: ["mintPosition(address,uint256)", "burnPosition(uint256)", "lendingPool()"],
  };
  for (const [interfaceName, functions] of Object.entries(canonicalFunctions)) {
    const artifact = JSON.parse(fs.readFileSync(path.join(root, "deployments/abi/interfaces/" + interfaceName + ".json"), "utf8"));
    assert.deepEqual(artifact, await hre.artifacts.readArtifact(interfaceName));
    const id = functions.reduce((value, signature) => value ^ BigInt(hre.ethers.id(signature).slice(0, 10)), 0n);
    const tokenName = interfaceName.slice(1);
    const token = await hre.ethers.getContractAt(tokenName, manifest.contracts[tokenName].address);
    assert.equal(await token.supportsInterface(hre.ethers.toBeHex(id, 4)), true);
  }
  const debtInterface = JSON.parse(fs.readFileSync(path.join(root, "deployments/abi/interfaces/IDebtToken.json"), "utf8"));
  assert.deepEqual(debtInterface, await hre.artifacts.readArtifact("IDebtToken"));
  const report = {
    network: "localhost", chainId, checkedAt: new Date().toISOString(),
    openzeppelinVersion: require("@openzeppelin/contracts/package.json").version,
    contracts, checkedTestWallets: manifest.contracts.MyUSDT.testAccounts.length,
    canonicalInterfaceArtifacts: 4,
    status: "LOCAL_TOKEN_DEPLOYMENTS_VERIFIED_AWAITING_HI02",
    pending: ["Deploy actual HI02 LendingPool and bind each token once.", "Verify debt-aware collateral release and principal/interest payouts with HI02/HI03."],
  };
  const output = path.join(root, "reports/h02_local_verification.json");
  fs.writeFileSync(output, JSON.stringify(report, null, 2) + "\n", "utf8");
  console.log("PASS: 5 deployed bytecodes/receipts, 4 interface exports, ERC165 IDs, registry, ownership and 10 MyUSDT wallets.");
  console.log("Saved reports/h02_local_verification.json; H02 tokens remain unbound for HI02.");
}

main().catch((error) => { console.error(error); process.exitCode = 1; });
