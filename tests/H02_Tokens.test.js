const { expect } = require("chai");
const { ethers, artifacts } = require("hardhat");
const { loadFixture, time } = require("@nomicfoundation/hardhat-network-helpers");

describe("H02 - collateral, receipts, debt and lending positions", function () {
  const wad = (value) => ethers.parseUnits(String(value), 18);
  const uri = "ipfs://test-fixture/asset-1.json";

  async function unboundFixture() {
    const [owner, borrower, lenderA, lenderB, operator] = await ethers.getSigners();
    const collateral = await ethers.deployContract("CollateralNFT");
    const receipt = await ethers.deployContract("CollateralReceiptNFT");
    const debt = await ethers.deployContract("DebtToken");
    const position = await ethers.deployContract("LendingPositionNFT");
    const caller = await ethers.deployContract("H02TokenCaller");
    await Promise.all([collateral, receipt, debt, position, caller].map((c) => c.waitForDeployment()));
    return { owner, borrower, lenderA, lenderB, operator, collateral, receipt, debt, position, caller };
  }

  async function boundFixture() {
    const ctx = await unboundFixture();
    for (const token of [ctx.receipt, ctx.debt, ctx.position]) {
      await token.setLendingPool(await ctx.caller.getAddress());
    }
    return ctx;
  }

  async function asPool(ctx, token, method, args = []) {
    return ctx.caller.execute(await token.getAddress(), token.interface.encodeFunctionData(method, args));
  }

  for (const name of ["receipt", "debt", "position"]) {
    describe(name + " one-time Pool binding", function () {
      it("starts unbound with the deployer as configuration owner", async function () {
        const ctx = await loadFixture(unboundFixture);
        expect(await ctx[name].lendingPool()).to.equal(ethers.ZeroAddress);
        expect(await ctx[name].owner()).to.equal(ctx.owner.address);
      });
      it("allows the owner to bind a deployed contract", async function () {
        const ctx = await loadFixture(unboundFixture);
        const address = await ctx.caller.getAddress();
        await expect(ctx[name].setLendingPool(address)).to.emit(ctx[name], "LendingPoolConfigured").withArgs(address);
        expect(await ctx[name].lendingPool()).to.equal(address);
      });
      it("rejects configuration by a borrower", async function () {
        const ctx = await loadFixture(unboundFixture);
        await expect(ctx[name].connect(ctx.borrower).setLendingPool(await ctx.caller.getAddress()))
          .to.be.revertedWithCustomError(ctx[name], "OwnableUnauthorizedAccount").withArgs(ctx.borrower.address);
      });
      it("rejects zero and EOA addresses", async function () {
        const ctx = await loadFixture(unboundFixture);
        for (const invalid of [ethers.ZeroAddress, ctx.owner.address]) {
          await expect(ctx[name].setLendingPool(invalid))
            .to.be.revertedWithCustomError(ctx[name], "InvalidPool").withArgs(invalid);
        }
      });
      it("rejects rebinding even by the owner", async function () {
        const ctx = await loadFixture(boundFixture);
        await expect(ctx[name].setLendingPool(await ctx.collateral.getAddress()))
          .to.be.revertedWithCustomError(ctx[name], "PoolAlreadyConfigured").withArgs(await ctx.caller.getAddress());
        expect(await ctx[name].lendingPool()).to.equal(await ctx.caller.getAddress());
      });
    });
  }

  describe("canonical HI01 interfaces", function () {
    for (const [name, interfaceName] of [
      ["collateral", "ICollateralNFT"], ["receipt", "ICollateralReceiptNFT"],
      ["debt", "IDebtToken"], ["position", "ILendingPositionNFT"],
    ]) {
      it(name + " preserves all canonical functions and event signatures", async function () {
        const ctx = await loadFixture(boundFixture);
        const canonical = new ethers.Interface((await artifacts.readArtifact(interfaceName)).abi);
        for (const fragment of canonical.fragments) {
          if (fragment.type === "function") {
            expect(ctx[name].interface.getFunction(fragment.format("sighash")).selector)
              .to.equal(canonical.getFunction(fragment.format("sighash")).selector);
          } else if (fragment.type === "event") {
            expect(ctx[name].interface.getEvent(fragment.format("sighash")).topicHash)
              .to.equal(canonical.getEvent(fragment.format("sighash")).topicHash);
          }
        }
      });
    }
    for (const name of ["collateral", "receipt", "position"]) {
      it(name + " advertises ERC165, ERC721 and metadata", async function () {
        const ctx = await loadFixture(boundFixture);
        for (const id of ["0x01ffc9a7", "0x80ac58cd", "0x5b5e139f"]) {
          expect(await ctx[name].supportsInterface(id)).to.equal(true);
        }
        expect(await ctx[name].supportsInterface("0xffffffff")).to.equal(false);
      });
    }
  });

  describe("CollateralNFT", function () {
    it("mints an underlying asset with owner, WAD valuation and URI", async function () {
      const { collateral, borrower } = await loadFixture(boundFixture);
      await expect(collateral.mintCollateral(borrower.address, wad(1000), uri))
        .to.emit(collateral, "CollateralMinted").withArgs(1n, borrower.address, wad(1000), uri);
      expect(await collateral.ownerOf(1)).to.equal(borrower.address);
      expect(await collateral.valuation(1)).to.equal(wad(1000));
      expect(await collateral.tokenURI(1)).to.equal(uri);
      expect(await collateral.supportsInterface("0x49064906")).to.equal(true);
    });
    it("prevents a borrower from minting an asset", async function () {
      const { collateral, borrower } = await loadFixture(boundFixture);
      await expect(collateral.connect(borrower).mintCollateral(borrower.address, wad(1000), uri))
        .to.be.revertedWithCustomError(collateral, "OwnableUnauthorizedAccount");
    });
    it("validates mint recipient, initial valuation and metadata", async function () {
      const { collateral, borrower } = await loadFixture(boundFixture);
      await expect(collateral.mintCollateral(ethers.ZeroAddress, wad(1000), uri))
        .to.be.revertedWithCustomError(collateral, "ERC721InvalidReceiver");
      await expect(collateral.mintCollateral(borrower.address, 0, uri))
        .to.be.revertedWithCustomError(collateral, "ZeroValuation");
      await expect(collateral.mintCollateral(borrower.address, wad(1000), ""))
        .to.be.revertedWithCustomError(collateral, "EmptyTokenURI");
    });
    it("only allows the owner to change valuation and permits a zero impairment value", async function () {
      const { collateral, borrower } = await loadFixture(boundFixture);
      await collateral.mintCollateral(borrower.address, wad(1000), uri);
      await expect(collateral.connect(borrower).setValuation(1, wad(900)))
        .to.be.revertedWithCustomError(collateral, "OwnableUnauthorizedAccount");
      await expect(collateral.setValuation(1, 0))
        .to.emit(collateral, "CollateralValuationUpdated").withArgs(1n, wad(1000), 0n);
      expect(await collateral.valuation(1)).to.equal(0n);
    });
    it("rejects valuation reads/writes for nonexistent tokens", async function () {
      const { collateral } = await loadFixture(boundFixture);
      await expect(collateral.valuation(99)).to.be.revertedWithCustomError(collateral, "ERC721NonexistentToken");
      await expect(collateral.setValuation(99, wad(1000))).to.be.revertedWithCustomError(collateral, "ERC721NonexistentToken");
    });
    it("can be freely transferred before custody", async function () {
      const { collateral, borrower, lenderA } = await loadFixture(boundFixture);
      await collateral.mintCollateral(borrower.address, wad(1000), uri);
      await collateral.connect(borrower).transferFrom(borrower.address, lenderA.address, 1);
      expect(await collateral.ownerOf(1)).to.equal(lenderA.address);
      expect(await collateral.valuation(1)).to.equal(wad(1000));
      expect(await collateral.tokenURI(1)).to.equal(uri);
    });
    it("rejects recovery by the former owner or operator after custody transfer", async function () {
      const ctx = await loadFixture(boundFixture);
      await ctx.collateral.mintCollateral(ctx.borrower.address, wad(1000), uri);
      await ctx.collateral.connect(ctx.borrower).approve(ctx.operator.address, 1);
      const custody = await ctx.caller.getAddress();
      await ctx.collateral.connect(ctx.borrower)["safeTransferFrom(address,address,uint256)"](ctx.borrower.address, custody, 1);
      expect(await ctx.collateral.getApproved(1)).to.equal(ethers.ZeroAddress);
      for (const signer of [ctx.borrower, ctx.operator, ctx.owner]) {
        await expect(ctx.collateral.connect(signer).transferFrom(custody, ctx.borrower.address, 1))
          .to.be.revertedWithCustomError(ctx.collateral, "ERC721InsufficientApproval");
      }
      expect(await ctx.collateral.ownerOf(1)).to.equal(custody);
    });
    it("rolls back a mint rejected by a non-receiver contract", async function () {
      const { collateral, debt, borrower } = await loadFixture(boundFixture);
      await expect(collateral.mintCollateral(await debt.getAddress(), wad(1000), uri))
        .to.be.revertedWithCustomError(collateral, "ERC721InvalidReceiver");
      await collateral.mintCollateral(borrower.address, wad(1000), uri);
      expect(await collateral.ownerOf(1)).to.equal(borrower.address);
    });
  });

  describe("DebtToken", function () {
    it("starts with 18 decimals and no supply", async function () {
      const { debt } = await loadFixture(boundFixture);
      expect(await debt.decimals()).to.equal(18n);
      expect(await debt.totalSupply()).to.equal(0n);
    });
    it("rejects mint/burn by the deployer and borrowers", async function () {
      const ctx = await loadFixture(boundFixture);
      for (const signer of [ctx.owner, ctx.borrower]) {
        await expect(ctx.debt.connect(signer).mint(ctx.borrower.address, wad(500)))
          .to.be.revertedWithCustomError(ctx.debt, "UnauthorizedPool").withArgs(signer.address);
        await expect(ctx.debt.connect(signer).burn(ctx.borrower.address, wad(500)))
          .to.be.revertedWithCustomError(ctx.debt, "UnauthorizedPool").withArgs(signer.address);
      }
    });
    it("mints exactly the principal and burns partial/full repayments through onlyPool", async function () {
      const ctx = await loadFixture(boundFixture);
      await expect(asPool(ctx, ctx.debt, "mint", [ctx.borrower.address, wad(500)]))
        .to.emit(ctx.debt, "DebtMinted").withArgs(ctx.borrower.address, wad(500));
      expect(await ctx.debt.balanceOf(ctx.borrower.address)).to.equal(wad(500));
      await expect(asPool(ctx, ctx.debt, "burn", [ctx.borrower.address, wad(200)]))
        .to.emit(ctx.debt, "DebtBurned").withArgs(ctx.borrower.address, wad(200));
      expect(await ctx.debt.balanceOf(ctx.borrower.address)).to.equal(wad(300));
      await asPool(ctx, ctx.debt, "burn", [ctx.borrower.address, wad(300)]);
      expect(await ctx.debt.balanceOf(ctx.borrower.address)).to.equal(0n);
      expect(await ctx.debt.totalSupply()).to.equal(0n);
    });
    it("rejects zero amounts and invalid accounts", async function () {
      const ctx = await loadFixture(boundFixture);
      for (const method of ["mint", "burn"]) {
        await expect(asPool(ctx, ctx.debt, method, [ctx.borrower.address, 0]))
          .to.be.revertedWithCustomError(ctx.debt, "ZeroDebtAmount");
      }
      await expect(asPool(ctx, ctx.debt, "mint", [ethers.ZeroAddress, 1]))
        .to.be.revertedWithCustomError(ctx.debt, "ERC20InvalidReceiver");
      await expect(asPool(ctx, ctx.debt, "burn", [ethers.ZeroAddress, 1]))
        .to.be.revertedWithCustomError(ctx.debt, "ERC20InvalidSender");
    });
    it("rejects excess burn without changing the debt", async function () {
      const ctx = await loadFixture(boundFixture);
      await asPool(ctx, ctx.debt, "mint", [ctx.borrower.address, wad(500)]);
      await expect(asPool(ctx, ctx.debt, "burn", [ctx.borrower.address, wad(501)]))
        .to.be.revertedWithCustomError(ctx.debt, "ERC20InsufficientBalance");
      expect(await ctx.debt.balanceOf(ctx.borrower.address)).to.equal(wad(500));
    });
    it("rejects transfer and transferFrom even with infinite allowance or zero amount", async function () {
      const ctx = await loadFixture(boundFixture);
      await asPool(ctx, ctx.debt, "mint", [ctx.borrower.address, wad(500)]);
      await ctx.debt.connect(ctx.borrower).approve(ctx.operator.address, ethers.MaxUint256);
      for (const amount of [0n, wad(1)]) {
        await expect(ctx.debt.connect(ctx.borrower).transfer(ctx.lenderA.address, amount))
          .to.be.revertedWithCustomError(ctx.debt, "DebtNonTransferable");
        await expect(ctx.debt.connect(ctx.operator).transferFrom(ctx.borrower.address, ctx.lenderA.address, amount))
          .to.be.revertedWithCustomError(ctx.debt, "DebtNonTransferable");
      }
      expect(await ctx.debt.balanceOf(ctx.borrower.address)).to.equal(wad(500));
      expect(await ctx.debt.allowance(ctx.borrower.address, ctx.operator.address)).to.equal(ethers.MaxUint256);
    });
    it("cannot mint before the Pool is bound", async function () {
      const ctx = await loadFixture(unboundFixture);
      await expect(asPool(ctx, ctx.debt, "mint", [ctx.borrower.address, wad(500)]))
        .to.be.revertedWithCustomError(ctx.debt, "UnauthorizedPool");
    });
  });

  describe("CollateralReceiptNFT", function () {
    it("records the borrower, asset type/id and deposit timestamp", async function () {
      const ctx = await loadFixture(boundFixture);
      await expect(asPool(ctx, ctx.receipt, "mintReceipt", [ctx.borrower.address, true, 7]))
        .to.emit(ctx.receipt, "ReceiptMinted").withArgs(1n, ctx.borrower.address, true, 7n);
      const info = await ctx.receipt.getReceiptInfo(1);
      expect(info.borrower).to.equal(ctx.borrower.address);
      expect(info.isNFT).to.equal(true);
      expect(info.assetIdOrAmount).to.equal(7n);
      expect(info.depositedAt).to.equal(BigInt(await time.latest()));
      expect(info.active).to.equal(true);
      expect(await ctx.receipt.activeReceiptOf(ctx.borrower.address)).to.equal(1n);
    });
    it("rejects user/admin minting and settlement", async function () {
      const ctx = await loadFixture(boundFixture);
      for (const signer of [ctx.owner, ctx.borrower]) {
        await expect(ctx.receipt.connect(signer).mintReceipt(ctx.borrower.address, true, 1))
          .to.be.revertedWithCustomError(ctx.receipt, "UnauthorizedPool");
        await expect(ctx.receipt.connect(signer).settleReceipt(1, false))
          .to.be.revertedWithCustomError(ctx.receipt, "UnauthorizedPool");
      }
    });
    it("accepts positive ERC20 collateral amounts and NFT token ID zero", async function () {
      const ctx = await loadFixture(boundFixture);
      await asPool(ctx, ctx.receipt, "mintReceipt", [ctx.borrower.address, false, wad(1000)]);
      expect((await ctx.receipt.getReceiptInfo(1)).assetIdOrAmount).to.equal(wad(1000));
      await asPool(ctx, ctx.receipt, "mintReceipt", [ctx.lenderA.address, true, 0]);
      expect((await ctx.receipt.getReceiptInfo(2)).assetIdOrAmount).to.equal(0n);
    });
    it("rejects zero borrowers, empty token collateral and duplicate active receipts", async function () {
      const ctx = await loadFixture(boundFixture);
      await expect(asPool(ctx, ctx.receipt, "mintReceipt", [ethers.ZeroAddress, true, 1]))
        .to.be.revertedWithCustomError(ctx.receipt, "ERC721InvalidReceiver");
      await expect(asPool(ctx, ctx.receipt, "mintReceipt", [ctx.borrower.address, false, 0]))
        .to.be.revertedWithCustomError(ctx.receipt, "ZeroCollateralAmount");
      await asPool(ctx, ctx.receipt, "mintReceipt", [ctx.borrower.address, true, 1]);
      await expect(asPool(ctx, ctx.receipt, "mintReceipt", [ctx.borrower.address, true, 2]))
        .to.be.revertedWithCustomError(ctx.receipt, "ActiveReceiptExists").withArgs(ctx.borrower.address);
    });
    it("blocks owner transfers, both safe-transfer overloads and approved operators", async function () {
      const ctx = await loadFixture(boundFixture);
      await asPool(ctx, ctx.receipt, "mintReceipt", [ctx.borrower.address, true, 1]);
      await ctx.receipt.connect(ctx.borrower).approve(ctx.operator.address, 1);
      await ctx.receipt.connect(ctx.borrower).setApprovalForAll(ctx.operator.address, true);
      for (const signer of [ctx.borrower, ctx.operator]) {
        await expect(ctx.receipt.connect(signer).transferFrom(ctx.borrower.address, ctx.lenderA.address, 1))
          .to.be.revertedWithCustomError(ctx.receipt, "ReceiptNonTransferable");
        await expect(ctx.receipt.connect(signer)["safeTransferFrom(address,address,uint256)"](ctx.borrower.address, ctx.lenderA.address, 1))
          .to.be.revertedWithCustomError(ctx.receipt, "ReceiptNonTransferable");
        await expect(ctx.receipt.connect(signer)["safeTransferFrom(address,address,uint256,bytes)"](ctx.borrower.address, ctx.lenderA.address, 1, "0x"))
          .to.be.revertedWithCustomError(ctx.receipt, "ReceiptNonTransferable");
      }
      expect(await ctx.receipt.ownerOf(1)).to.equal(ctx.borrower.address);
    });
    for (const liquidated of [false, true]) {
      it("burns and preserves inactive history on " + (liquidated ? "liquidation" : "repayment"), async function () {
        const ctx = await loadFixture(boundFixture);
        await asPool(ctx, ctx.receipt, "mintReceipt", [ctx.borrower.address, true, 7]);
        await expect(asPool(ctx, ctx.receipt, "settleReceipt", [1, liquidated]))
          .to.emit(ctx.receipt, "ReceiptSettled").withArgs(1n, ctx.borrower.address, liquidated);
        await expect(ctx.receipt.ownerOf(1)).to.be.revertedWithCustomError(ctx.receipt, "ERC721NonexistentToken");
        const info = await ctx.receipt.getReceiptInfo(1);
        expect(info.active).to.equal(false);
        expect(info.assetIdOrAmount).to.equal(7n);
        expect(await ctx.receipt.activeReceiptOf(ctx.borrower.address)).to.equal(0n);
        await asPool(ctx, ctx.receipt, "mintReceipt", [ctx.borrower.address, true, 8]);
        expect(await ctx.receipt.ownerOf(2)).to.equal(ctx.borrower.address);
      });
    }
    it("rejects unknown and already-settled receipts", async function () {
      const ctx = await loadFixture(boundFixture);
      await expect(ctx.receipt.getReceiptInfo(99)).to.be.revertedWithCustomError(ctx.receipt, "ReceiptNotFound");
      await expect(asPool(ctx, ctx.receipt, "settleReceipt", [99, false]))
        .to.be.revertedWithCustomError(ctx.receipt, "ReceiptNotFound");
      await asPool(ctx, ctx.receipt, "mintReceipt", [ctx.borrower.address, true, 1]);
      await asPool(ctx, ctx.receipt, "settleReceipt", [1, false]);
      await expect(asPool(ctx, ctx.receipt, "settleReceipt", [1, false]))
        .to.be.revertedWithCustomError(ctx.receipt, "ReceiptAlreadySettled");
    });
    it("rolls back active receipt state if a recipient contract rejects safe mint", async function () {
      const ctx = await loadFixture(boundFixture);
      const badRecipient = await ctx.debt.getAddress();
      await expect(asPool(ctx, ctx.receipt, "mintReceipt", [badRecipient, true, 7]))
        .to.be.revertedWithCustomError(ctx.receipt, "ERC721InvalidReceiver");
      expect(await ctx.receipt.activeReceiptOf(badRecipient)).to.equal(0n);
      await asPool(ctx, ctx.receipt, "mintReceipt", [ctx.borrower.address, true, 7]);
      expect(await ctx.receipt.ownerOf(1)).to.equal(ctx.borrower.address);
    });
  });

  describe("LendingPositionNFT", function () {
    it("only allows the Pool to mint and burn positions", async function () {
      const ctx = await loadFixture(boundFixture);
      for (const signer of [ctx.owner, ctx.lenderA]) {
        await expect(ctx.position.connect(signer).mintPosition(ctx.lenderA.address, wad(1000)))
          .to.be.revertedWithCustomError(ctx.position, "UnauthorizedPool");
        await expect(ctx.position.connect(signer).burnPosition(1))
          .to.be.revertedWithCustomError(ctx.position, "UnauthorizedPool");
      }
    });
    it("mints sequential position IDs with the exact initial principal event", async function () {
      const ctx = await loadFixture(boundFixture);
      await expect(asPool(ctx, ctx.position, "mintPosition", [ctx.lenderA.address, wad(1000)]))
        .to.emit(ctx.position, "PositionMinted").withArgs(1n, ctx.lenderA.address, wad(1000));
      await asPool(ctx, ctx.position, "mintPosition", [ctx.lenderA.address, wad(500)]);
      expect(await ctx.position.ownerOf(1)).to.equal(ctx.lenderA.address);
      expect(await ctx.position.ownerOf(2)).to.equal(ctx.lenderA.address);
    });
    it("moves ownerOf from Lender A to B and clears the previous approval", async function () {
      const ctx = await loadFixture(boundFixture);
      await asPool(ctx, ctx.position, "mintPosition", [ctx.lenderA.address, wad(1000)]);
      await ctx.position.connect(ctx.lenderA).approve(ctx.operator.address, 1);
      await expect(ctx.position.connect(ctx.lenderA).transferFrom(ctx.lenderA.address, ctx.lenderB.address, 1))
        .to.emit(ctx.position, "Transfer").withArgs(ctx.lenderA.address, ctx.lenderB.address, 1n);
      expect(await ctx.position.ownerOf(1)).to.equal(ctx.lenderB.address);
      expect(await ctx.position.getApproved(1)).to.equal(ethers.ZeroAddress);
      await expect(ctx.position.connect(ctx.lenderA).transferFrom(ctx.lenderB.address, ctx.lenderA.address, 1))
        .to.be.revertedWithCustomError(ctx.position, "ERC721InsufficientApproval");
    });
    it("supports safeTransferFrom and the receiving contract check", async function () {
      const ctx = await loadFixture(boundFixture);
      await asPool(ctx, ctx.position, "mintPosition", [ctx.lenderA.address, wad(1000)]);
      await expect(ctx.position.connect(ctx.lenderA)["safeTransferFrom(address,address,uint256)"](ctx.lenderA.address, await ctx.debt.getAddress(), 1))
        .to.be.revertedWithCustomError(ctx.position, "ERC721InvalidReceiver");
      await ctx.position.connect(ctx.lenderA)["safeTransferFrom(address,address,uint256)"](ctx.lenderA.address, ctx.lenderB.address, 1);
      expect(await ctx.position.ownerOf(1)).to.equal(ctx.lenderB.address);
    });
    it("burns for the current owner after a transfer, not the original lender", async function () {
      const ctx = await loadFixture(boundFixture);
      await asPool(ctx, ctx.position, "mintPosition", [ctx.lenderA.address, wad(1000)]);
      await ctx.position.connect(ctx.lenderA).transferFrom(ctx.lenderA.address, ctx.lenderB.address, 1);
      await expect(asPool(ctx, ctx.position, "burnPosition", [1]))
        .to.emit(ctx.position, "PositionBurned").withArgs(1n, ctx.lenderB.address);
      await expect(ctx.position.ownerOf(1)).to.be.revertedWithCustomError(ctx.position, "ERC721NonexistentToken");
      await expect(asPool(ctx, ctx.position, "burnPosition", [1]))
        .to.be.revertedWithCustomError(ctx.position, "ERC721NonexistentToken");
    });
    it("rejects zero principal, zero recipients and unauthorized transfers", async function () {
      const ctx = await loadFixture(boundFixture);
      await expect(asPool(ctx, ctx.position, "mintPosition", [ctx.lenderA.address, 0]))
        .to.be.revertedWithCustomError(ctx.position, "ZeroPositionAmount");
      await expect(asPool(ctx, ctx.position, "mintPosition", [ethers.ZeroAddress, wad(1000)]))
        .to.be.revertedWithCustomError(ctx.position, "ERC721InvalidReceiver");
      await asPool(ctx, ctx.position, "mintPosition", [ctx.lenderA.address, wad(1000)]);
      await expect(ctx.position.connect(ctx.borrower).transferFrom(ctx.lenderA.address, ctx.lenderB.address, 1))
        .to.be.revertedWithCustomError(ctx.position, "ERC721InsufficientApproval");
    });
  });
});
