const { expect } = require("chai");
const { ethers } = require("hardhat");
const { loadFixture } = require("@nomicfoundation/hardhat-network-helpers");

describe("MyUSDT (H01)", function () {
  const units = (amount) => ethers.parseUnits(String(amount), 18);
  const initialSupply = units(1_000_000);
  const faucetLimit = units(1_000);

  async function deployFixture() {
    const [deployer, lender, borrower, spender] = await ethers.getSigners();
    const token = await ethers.deployContract("MyUSDT");
    await token.waitForDeployment();
    return { token, deployer, lender, borrower, spender };
  }

  describe("deployment", function () {
    it("sets the token name, symbol and 18 decimals", async function () {
      const { token } = await loadFixture(deployFixture);
      expect(await token.name()).to.equal("MyUSDT");
      expect(await token.symbol()).to.equal("MyUSDT");
      expect(await token.decimals()).to.equal(18n);
    });

    it("assigns ownership and the initial 1,000,000 tokens to the deployer", async function () {
      const { token, deployer, lender } = await loadFixture(deployFixture);
      expect(await token.owner()).to.equal(deployer.address);
      expect(await token.INITIAL_SUPPLY()).to.equal(initialSupply);
      expect(await token.totalSupply()).to.equal(initialSupply);
      expect(await token.balanceOf(deployer.address)).to.equal(initialSupply);
      expect(await token.balanceOf(lender.address)).to.equal(0n);
      await expect(token.deploymentTransaction())
        .to.emit(token, "Transfer")
        .withArgs(ethers.ZeroAddress, deployer.address, initialSupply);
    });

    it("allows only the owner to transfer ownership", async function () {
      const { token, deployer, lender } = await loadFixture(deployFixture);
      await expect(token.connect(lender).transferOwnership(lender.address))
        .to.be.revertedWithCustomError(token, "OwnableUnauthorizedAccount")
        .withArgs(lender.address);
      await expect(token.transferOwnership(lender.address))
        .to.emit(token, "OwnershipTransferred")
        .withArgs(deployer.address, lender.address);
      expect(await token.owner()).to.equal(lender.address);
    });
  });

  describe("faucet", function () {
    it("allows a non-owner to mint test tokens to another account", async function () {
      const { token, lender, borrower } = await loadFixture(deployFixture);
      const tx = await token.connect(lender).faucet(borrower.address, units(500));
      await expect(tx).to.emit(token, "Transfer")
        .withArgs(ethers.ZeroAddress, borrower.address, units(500));
      await expect(tx).to.emit(token, "FaucetUsed")
        .withArgs(lender.address, borrower.address, units(500));
      expect(await token.balanceOf(borrower.address)).to.equal(units(500));
      expect(await token.totalSupply()).to.equal(initialSupply + units(500));
    });

    it("accepts one base unit", async function () {
      const { token, lender } = await loadFixture(deployFixture);
      await token.faucet(lender.address, 1n);
      expect(await token.balanceOf(lender.address)).to.equal(1n);
    });

    it("accepts exactly 1,000 MyUSDT per call", async function () {
      const { token, lender } = await loadFixture(deployFixture);
      expect(await token.MAX_FAUCET_AMOUNT()).to.equal(faucetLimit);
      await token.connect(lender).faucet(lender.address, faucetLimit);
      expect(await token.balanceOf(lender.address)).to.equal(faucetLimit);
    });

    for (const [label, amount] of [
      ["zero", 0n],
      ["one base unit over the limit", faucetLimit + 1n],
      ["the largest uint256", ethers.MaxUint256],
    ]) {
      it("rejects " + label + " without changing supply", async function () {
        const { token, lender } = await loadFixture(deployFixture);
        await expect(token.faucet(lender.address, amount))
          .to.be.revertedWithCustomError(token, "InvalidFaucetAmount")
          .withArgs(amount);
        expect(await token.totalSupply()).to.equal(initialSupply);
        expect(await token.balanceOf(lender.address)).to.equal(0n);
      });
    }

    it("rejects the zero recipient", async function () {
      const { token } = await loadFixture(deployFixture);
      await expect(token.faucet(ethers.ZeroAddress, 1n))
        .to.be.revertedWithCustomError(token, "ERC20InvalidReceiver")
        .withArgs(ethers.ZeroAddress);
    });

    it("applies the limit to each call and allows repeat requests", async function () {
      const { token, lender } = await loadFixture(deployFixture);
      await token.faucet(lender.address, faucetLimit);
      await token.faucet(lender.address, faucetLimit);
      expect(await token.balanceOf(lender.address)).to.equal(2n * faucetLimit);
      expect(await token.totalSupply()).to.equal(initialSupply + 2n * faucetLimit);
    });
  });

  describe("ERC-20 transfers and allowances", function () {
    it("transfers exact amounts and emits Transfer", async function () {
      const { token, deployer, lender } = await loadFixture(deployFixture);
      const amount = units("12.34567890123456789");
      await expect(token.transfer(lender.address, amount))
        .to.emit(token, "Transfer")
        .withArgs(deployer.address, lender.address, amount);
      expect(await token.balanceOf(deployer.address)).to.equal(initialSupply - amount);
      expect(await token.balanceOf(lender.address)).to.equal(amount);
      expect(await token.totalSupply()).to.equal(initialSupply);
    });

    it("rejects transfers exceeding the sender's balance", async function () {
      const { token, lender, borrower } = await loadFixture(deployFixture);
      await expect(token.connect(lender).transfer(borrower.address, 1n))
        .to.be.revertedWithCustomError(token, "ERC20InsufficientBalance")
        .withArgs(lender.address, 0n, 1n);
    });

    it("rejects transfers to the zero address", async function () {
      const { token } = await loadFixture(deployFixture);
      await expect(token.transfer(ethers.ZeroAddress, 1n))
        .to.be.revertedWithCustomError(token, "ERC20InvalidReceiver")
        .withArgs(ethers.ZeroAddress);
    });

    it("sets allowance and emits Approval", async function () {
      const { token, deployer, spender } = await loadFixture(deployFixture);
      await expect(token.approve(spender.address, units(1000)))
        .to.emit(token, "Approval")
        .withArgs(deployer.address, spender.address, units(1000));
      expect(await token.allowance(deployer.address, spender.address)).to.equal(units(1000));
    });

    it("rejects approval of the zero spender", async function () {
      const { token } = await loadFixture(deployFixture);
      await expect(token.approve(ethers.ZeroAddress, 1n))
        .to.be.revertedWithCustomError(token, "ERC20InvalidSpender")
        .withArgs(ethers.ZeroAddress);
    });

    it("spends only part of the allowance with transferFrom", async function () {
      const { token, deployer, spender, borrower } = await loadFixture(deployFixture);
      await token.approve(spender.address, units(1000));
      await expect(token.connect(spender).transferFrom(deployer.address, borrower.address, units(400)))
        .to.emit(token, "Transfer")
        .withArgs(deployer.address, borrower.address, units(400));
      expect(await token.allowance(deployer.address, spender.address)).to.equal(units(600));
      expect(await token.balanceOf(borrower.address)).to.equal(units(400));
      expect(await token.balanceOf(deployer.address)).to.equal(initialSupply - units(400));
    });

    it("rejects transferFrom without approval", async function () {
      const { token, deployer, spender, borrower } = await loadFixture(deployFixture);
      await expect(token.connect(spender).transferFrom(deployer.address, borrower.address, 1n))
        .to.be.revertedWithCustomError(token, "ERC20InsufficientAllowance")
        .withArgs(spender.address, 0n, 1n);
    });

    it("rejects spending beyond allowance without changing balances or allowance", async function () {
      const { token, deployer, spender, borrower } = await loadFixture(deployFixture);
      await token.approve(spender.address, units(500));
      await expect(token.connect(spender).transferFrom(deployer.address, borrower.address, units(501)))
        .to.be.revertedWithCustomError(token, "ERC20InsufficientAllowance")
        .withArgs(spender.address, units(500), units(501));
      expect(await token.balanceOf(deployer.address)).to.equal(initialSupply);
      expect(await token.balanceOf(borrower.address)).to.equal(0n);
      expect(await token.allowance(deployer.address, spender.address)).to.equal(units(500));
    });

    it("lets an account revoke an allowance", async function () {
      const { token, deployer, spender, borrower } = await loadFixture(deployFixture);
      await token.approve(spender.address, units(1000));
      await token.approve(spender.address, 0n);
      await expect(token.connect(spender).transferFrom(deployer.address, borrower.address, 1n))
        .to.be.revertedWithCustomError(token, "ERC20InsufficientAllowance")
        .withArgs(spender.address, 0n, 1n);
    });

    it("preserves infinite allowance when transferring", async function () {
      const { token, deployer, spender, borrower } = await loadFixture(deployFixture);
      await token.approve(spender.address, ethers.MaxUint256);
      await token.connect(spender).transferFrom(deployer.address, borrower.address, units(500));
      expect(await token.allowance(deployer.address, spender.address)).to.equal(ethers.MaxUint256);
      expect(await token.balanceOf(borrower.address)).to.equal(units(500));
    });

    it("rejects transferFrom when balance is insufficient even with approval", async function () {
      const { token, lender, spender, borrower } = await loadFixture(deployFixture);
      await token.connect(lender).approve(spender.address, units(1000));
      await expect(token.connect(spender).transferFrom(lender.address, borrower.address, units(1000)))
        .to.be.revertedWithCustomError(token, "ERC20InsufficientBalance")
        .withArgs(lender.address, 0n, units(1000));
      expect(await token.allowance(lender.address, spender.address)).to.equal(units(1000));
    });

    it("supports the H01 1,000-token funding flow through approve and transferFrom", async function () {
      const { token, lender, spender } = await loadFixture(deployFixture);
      // A signer exercises the spender interface; actual LendingPool integration is HI02.
      await token.connect(lender).faucet(lender.address, units(1000));
      await token.connect(lender).approve(spender.address, units(1000));
      await token.connect(spender).transferFrom(lender.address, spender.address, units(1000));
      expect(await token.balanceOf(lender.address)).to.equal(0n);
      expect(await token.balanceOf(spender.address)).to.equal(units(1000));
      expect(await token.allowance(lender.address, spender.address)).to.equal(0n);
      expect(await token.totalSupply()).to.equal(initialSupply + units(1000));
    });
  });
});
