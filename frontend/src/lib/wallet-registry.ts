import type { DeploymentRegistry } from "./wallet-transactions.ts";
const allowed: Record<string, string[]> = {
  MyUSDT: ["approve", "faucet"], CollateralNFT: ["approve"],
  LendingPositionNFT: ["safeTransferFrom"],
  LendingPool: ["depositLender", "withdrawLender", "depositCollateral", "withdrawCollateral", "borrow", "repay", "liquidate"],
  PriceOracle: ["setPriceMultiplierBps"],
};
/** Keep public addresses and the canonical signing functions; no bytecode or key config goes to the browser. */
export function walletRegistry(input: DeploymentRegistry, blocks: Record<"local" | "sepolia", number>): DeploymentRegistry {
  const result: DeploymentRegistry = { contracts: {}, networks: { local: { chainId: 31337, contracts: {} }, sepolia: { chainId: 11155111, contracts: {} } } };
  for (const [name, functions] of Object.entries(allowed)) {
    const source = input.contracts[name];
    if (!Array.isArray(source?.abi)) throw new Error("Thiếu ABI bàn giao " + name);
    const abi = source.abi.filter((entry) => typeof entry === "object" && entry !== null && "type" in entry && entry.type === "function" && "name" in entry && functions.includes(String(entry.name)));
    result.contracts[name] = { address: source.address, abi };
    for (const network of ["local", "sepolia"] as const) {
      const deployed = input.networks[network];
      if (!deployed?.contracts[name]?.address) throw new Error("Thiếu địa chỉ " + name + " trên " + network);
      if (!Number.isSafeInteger(blocks[network]) || blocks[network] < 0) throw new Error("Thiếu block bắt đầu từ bàn giao Q06.");
      result.networks[network].chainId = deployed.chainId;
      result.networks[network].fromBlock = blocks[network];
      result.networks[network].contracts[name] = { address: deployed.contracts[name].address };
    }
  }
  return result;
}
