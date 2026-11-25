require("@nomicfoundation/hardhat-toolbox");
require("dotenv").config();

const DEFAULT_LOCAL_MNEMONIC =
  process.env.LOCAL_MNEMONIC ||
  "test test test test test test test test test test test junk";

const LOCAL_CHAIN_ID = Number(process.env.LOCAL_CHAIN_ID || 31337);
const LOCAL_RPC_URL = process.env.LOCAL_RPC_URL || "http://127.0.0.1:8545";

const SEPOLIA_RPC_URL =
  process.env.SEPOLIA_RPC_URL || "https://ethereum-sepolia-rpc.publicnode.com";
const SEPOLIA_CHAIN_ID = Number(process.env.SEPOLIA_CHAIN_ID || 11155111);

// Danh sách 10 private key mặc định của Hardhat (tuyệt đối cấm dùng trên Sepolia)
const KNOWN_HARDHAT_KEYS = new Set([
  "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",
  "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d",
  "0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a",
  "0x7c852118294e51e653712a81e05800f419141751be58f605c371e15141b007a6",
  "0x47e179ec197488593b187f80a00eb0da91f1b9d0b13f8733639f19c30a34926a",
  "0x8b3a350cf5c34c9194ca85829a2df0ec3153be0318b5e2d3348e872092edffba",
  "0x92db14e403b83dfe3df233f83dfa3a0d7096f21ca9b0d6d6b8d88b2b4ec1564e",
  "0x4bbbf85ce3377467afe5d46f804f221813b2bb87f24d81f60f1fcdbf7cbf4356",
  "0xdbda1821b80551c9d65939329250298aa3472ba22feea921c0cf5d620ea67b97",
  "0x2a871d0798f97d79848a013d4936a73bf4cc922c825d33c1cf7073dff6d409c6",
]);

function getSepoliaAccounts() {
  const rawKey = (process.env.SEPOLIA_DEPLOYER_PRIVATE_KEY || "").trim();
  if (!rawKey) {
    return [];
  }
  const normalizedKey = rawKey.startsWith("0x") ? rawKey.toLowerCase() : `0x${rawKey.toLowerCase()}`;
  if (KNOWN_HARDHAT_KEYS.has(normalizedKey)) {
    throw new Error(
      "SECURITY BLOCK: Không được sử dụng Private Key mặc định của Hardhat cho mạng Sepolia Testnet!"
    );
  }
  return [normalizedKey];
}

/** @type import('hardhat/config').HardhatUserConfig */
module.exports = {
  solidity: {
    version: "0.8.24",
    settings: {
      optimizer: {
        enabled: true,
        runs: 200,
      },
      evmVersion: "paris",
    },
  },
  defaultNetwork: "hardhat",
  networks: {
    hardhat: {
      chainId: LOCAL_CHAIN_ID,
      accounts: {
        mnemonic: DEFAULT_LOCAL_MNEMONIC,
        path: "m/44'/60'/0'/0",
        initialIndex: 0,
        count: 10,
        accountsBalance: "10000000000000000000000", // 10,000 ETH / ví
      },
    },
    localhost: {
      url: LOCAL_RPC_URL,
      chainId: LOCAL_CHAIN_ID,
      accounts: {
        mnemonic: DEFAULT_LOCAL_MNEMONIC,
        path: "m/44'/60'/0'/0",
        initialIndex: 0,
        count: 10,
      },
    },
    sepolia: {
      url: SEPOLIA_RPC_URL,
      chainId: SEPOLIA_CHAIN_ID,
      accounts: getSepoliaAccounts(),
    },
  },
  gasReporter: {
    enabled: process.env.REPORT_GAS === "true",
    currency: "USD",
  },
  etherscan: {
    apiKey: process.env.ETHERSCAN_API_KEY || "",
  },
  paths: {
    sources: "./contracts",
    tests: "./tests",
    cache: "./cache",
    artifacts: "./artifacts",
  },
};
