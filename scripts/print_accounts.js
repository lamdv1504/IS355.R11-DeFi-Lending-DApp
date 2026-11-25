const hre = require("hardhat");

const SUGGESTED_ROLES = [
  "Account #0 - Deployer / Admin / System Seed",
  "Account #1 - Lender A (Nạp 1000 MyUSDT trong kịch bản Demo)",
  "Account #2 - Borrower A (Thế chấp & Vay 500 MyUSDT trong kịch bản Demo)",
  "Account #3 - Lender B (Nhận chuyển nhượng LendingPositionNFT)",
  "Account #4 - Liquidator / Keeper (Gọi liquidate() khi HF < 1.0)",
  "Account #5 - Borrower B (Test không có quyền xem Credit Report của ví khác)",
  "Account #6 - Ví test thành viên Hùng",
  "Account #7 - Ví test thành viên Hiếu",
  "Account #8 - Ví test thành viên Quân",
  "Account #9 - Ví test thành viên Lâm",
];

async function main() {
  const signers = await hre.ethers.getSigners();
  const network = await hre.ethers.provider.getNetwork();

  console.log("================================================================================");
  console.log(`Network: ${hre.network.name} | Chain ID: ${network.chainId.toString()}`);
  console.log("LƯU Ý: Danh sách ví dưới đây CHỈ dùng trên mạng Local (Chain ID 31337)!");
  console.log("================================================================================");

  for (let i = 0; i < Math.min(signers.length, 10); i++) {
    const address = await signers[i].getAddress();
    const balanceWei = await hre.ethers.provider.getBalance(address);
    const balanceEth = hre.ethers.formatEther(balanceWei);
    const role = SUGGESTED_ROLES[i] || `Account #${i}`;
    console.log(`[${i}] ${address} | Balance: ${balanceEth} ETH | ${role}`);
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
