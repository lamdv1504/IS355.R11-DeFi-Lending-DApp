const fs = require("node:fs");
const path = require("node:path");

const HI05_CONTRACTS = ["PriceOracle", "LendingPool"];
const HI05_INTERFACES = ["IPriceOracle", "ILendingPool"];

async function exportHI05(hre) {
  const exported = {};
  for (const name of [...HI05_CONTRACTS, ...HI05_INTERFACES]) {
    const artifact = await hre.artifacts.readArtifact(name);
    const relativePath = HI05_INTERFACES.includes(name)
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
  exportHI05(require("hardhat"))
    .then((exported) => console.table(exported))
    .catch((error) => {
      console.error(error);
      process.exitCode = 1;
    });
}

module.exports = { HI05_CONTRACTS, HI05_INTERFACES, exportHI05 };
