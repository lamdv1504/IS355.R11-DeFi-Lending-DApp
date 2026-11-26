const fs = require("node:fs");
const path = require("node:path");

const HI02_CONTRACTS = ["LendingPool"];
const HI02_INTERFACES = ["ILendingPool"];

async function exportHI02(hre) {
  const exported = {};
  for (const name of [...HI02_CONTRACTS, ...HI02_INTERFACES]) {
    const artifact = await hre.artifacts.readArtifact(name);
    const relativePath = HI02_INTERFACES.includes(name)
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
  exportHI02(require("hardhat"))
    .then((exported) => console.table(exported))
    .catch((error) => {
      console.error(error);
      process.exitCode = 1;
    });
}

module.exports = { HI02_CONTRACTS, HI02_INTERFACES, exportHI02 };
