// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {ERC721} from "@openzeppelin/contracts/token/ERC721/ERC721.sol";
import {IERC165} from "@openzeppelin/contracts/utils/introspection/IERC165.sol";
import {ICollateralReceiptNFT} from "../interfaces/ICollateralReceiptNFT.sol";
import {PoolControlled} from "./base/PoolControlled.sol";

/// @notice Soulbound custody receipt, distinct from the underlying collateral asset.
contract CollateralReceiptNFT is ERC721, PoolControlled, ICollateralReceiptNFT {
    uint256 private _nextReceiptId = 1;
    mapping(uint256 => ReceiptInfo) private _receipts;
    mapping(address => uint256) public activeReceiptOf;

    error ReceiptNonTransferable();
    error ReceiptNotFound(uint256 receiptId);
    error ReceiptAlreadySettled(uint256 receiptId);
    error ActiveReceiptExists(address borrower);
    error ZeroCollateralAmount();

    constructor() ERC721("Collateral Receipt", "CRECEIPT") {}

    function lendingPool() public view override(PoolControlled, ICollateralReceiptNFT) returns (address) {
        return super.lendingPool();
    }

    function mintReceipt(address borrower, bool isNFT, uint256 assetIdOrAmount)
        external override onlyPool returns (uint256 receiptId)
    {
        if (borrower == address(0)) revert ERC721InvalidReceiver(borrower);
        if (!isNFT && assetIdOrAmount == 0) revert ZeroCollateralAmount();
        if (activeReceiptOf[borrower] != 0) revert ActiveReceiptExists(borrower);
        receiptId = _nextReceiptId++;
        _receipts[receiptId] = ReceiptInfo(borrower, isNFT, assetIdOrAmount, block.timestamp, true);
        activeReceiptOf[borrower] = receiptId;
        _safeMint(borrower, receiptId);
        emit ReceiptMinted(receiptId, borrower, isNFT, assetIdOrAmount);
    }

    /// @dev HI02 must check debt/custody and choose repayment or liquidation BEFORE this call.
    function settleReceipt(uint256 receiptId, bool liquidated) external override onlyPool {
        ReceiptInfo storage info = _receipts[receiptId];
        if (info.borrower == address(0)) revert ReceiptNotFound(receiptId);
        if (!info.active) revert ReceiptAlreadySettled(receiptId);
        info.active = false;
        activeReceiptOf[info.borrower] = 0;
        _burn(receiptId);
        emit ReceiptSettled(receiptId, info.borrower, liquidated);
    }

    /// @notice History remains readable after the ERC-721 receipt has been burned.
    function getReceiptInfo(uint256 receiptId) external view override returns (ReceiptInfo memory) {
        if (_receipts[receiptId].borrower == address(0)) revert ReceiptNotFound(receiptId);
        return _receipts[receiptId];
    }

    function _update(address to, uint256 tokenId, address auth) internal override returns (address) {
        if (_ownerOf(tokenId) != address(0) && to != address(0)) revert ReceiptNonTransferable();
        return super._update(to, tokenId, auth);
    }

    function supportsInterface(bytes4 interfaceId)
        public view override(ERC721, IERC165) returns (bool)
    {
        return interfaceId == type(ICollateralReceiptNFT).interfaceId || super.supportsInterface(interfaceId);
    }
}
