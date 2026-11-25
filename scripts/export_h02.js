const fs = require("node:fs");
const path = require("node:path");

const H02_NAMES = ["CollateralNFT", "CollateralReceiptNFT", "DebtToken", "LendingPositionNFT"];
const H02_INTERFACES = ["ICollateralNFT", "ICollateralReceiptNFT", "IDebtToken", "ILendingPositionNFT"];

async function exportH02(hre) {
  const exported = {};
  for (const name of [...H02_NAMES, ...H02_INTERFACES]) {
    const artifact = await hre.artifacts.readArtifact(name);
    const relativePath = H02_INTERFACES.includes(name)
      ? "deployments/abi/interfaces/" + name + ".json"
      : "deployments/abi/" + name + ".json";
    const output = path.join(hre.config.paths.root, relativePath);
    fs.mkdirSync(path.dirname(output), { recursive: true });
    fs.writeFileSync(output, JSON.stringify(artifact, null, 2) + "\n", "utf8");
    exported[name] = relativePath;
  }
  return exported;
}

if (require.main === module) {
  exportH02(require("hardhat"))
    .then((exported) => console.table(exported))
    .catch((error) => { console.error(error); process.exitCode = 1; });
}

module.exports = { H02_NAMES, exportH02 };
