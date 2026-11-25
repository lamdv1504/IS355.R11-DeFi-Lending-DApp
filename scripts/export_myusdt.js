const fs = require("node:fs");
const path = require("node:path");

const MYUSDT_ARTIFACT_PATH = "deployments/abi/MyUSDT.json";

async function exportMyUSDT(hre) {
  const artifact = await hre.artifacts.readArtifact("MyUSDT");
  const outputPath = path.join(hre.config.paths.root, MYUSDT_ARTIFACT_PATH);
  fs.mkdirSync(path.dirname(outputPath), { recursive: true });
  fs.writeFileSync(outputPath, JSON.stringify(artifact, null, 2) + "\n", "utf8");
  return MYUSDT_ARTIFACT_PATH;
}

if (require.main === module) {
  exportMyUSDT(require("hardhat"))
    .then((outputPath) => console.log("Exported ABI and bytecode: " + outputPath))
    .catch((error) => {
      console.error(error);
      process.exitCode = 1;
    });
}

module.exports = { exportMyUSDT, MYUSDT_ARTIFACT_PATH };
