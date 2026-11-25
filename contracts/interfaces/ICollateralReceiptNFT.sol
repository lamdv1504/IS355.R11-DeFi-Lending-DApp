// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {IERC721} from "@openzeppelin/contracts/token/ERC721/IERC721.sol";

/// @title ICollateralReceiptNFT - Non-transferable receipt NFT minted on `depositCollateral()` (H02/HI02).
/// @notice Distinct from `CollateralNFT` (underlying asset) and `LendingPositionNFT` (lender claim).
/// @dev Only `LendingPool` (`onlyPool`) may mint or settle/burn receipts. Transfers between users
///      are disabled while the collateral is locked so receipts always mirror the borrower's locked position.
interface ICollateralReceiptNFT is IERC721 {
    struct ReceiptInfo {
        address borrower;
        bool isNFT;
        uint256 assetIdOrAmount;
        uint256 depositedAt;
        bool active;
    }

    event ReceiptMinted(
        uint256 indexed receiptId,
        address indexed borrower,
        bool isNFT,
        uint256 assetIdOrAmount
    );

    event ReceiptSettled(uint256 indexed receiptId, address indexed borrower, bool liquidated);

    /// @notice Mints a collateral custody receipt to `borrower`. Callable only by `LendingPool`.
    function mintReceipt(
        address borrower,
        bool isNFT,
        uint256 assetIdOrAmount
    ) external returns (uint256 receiptId);

    /// @notice Burns or marks the receipt settled when debt is fully repaid or liquidated. Callable only by `LendingPool`.
    function settleReceipt(uint256 receiptId, bool liquidated) external;

    /// @notice Returns receipt metadata for UI and audit verification.
    function getReceiptInfo(uint256 receiptId) external view returns (ReceiptInfo memory);

    /// @notice Returns the configured LendingPool address authorized to mint/settle receipts.
    function lendingPool() external view returns (address);
}
