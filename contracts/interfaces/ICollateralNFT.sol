// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {IERC721} from "@openzeppelin/contracts/token/ERC721/IERC721.sol";

/// @title ICollateralNFT - Underlying tokenized collateral asset (ERC-721, H02).
/// @notice Represents real-world or high-value digital assets pledged into LendingPool.
/// @dev All valuations MUST be expressed in MyUSDT WAD (18 decimals, 1 MyUSDT = 1e18).
interface ICollateralNFT is IERC721 {
    event CollateralMinted(
        uint256 indexed tokenId,
        address indexed owner,
        uint256 valuationWad,
        string tokenURI
    );

    event CollateralValuationUpdated(
        uint256 indexed tokenId,
        uint256 oldValuationWad,
        uint256 newValuationWad
    );

    /// @notice Mints a new tokenized collateral NFT with a baseline valuation in MyUSDT WAD (1e18).
    function mintCollateral(
        address to,
        uint256 valuationWad,
        string calldata uri
    ) external returns (uint256 tokenId);

    /// @notice Returns the baseline valuation of `tokenId` in MyUSDT WAD (1e18).
    function valuation(uint256 tokenId) external view returns (uint256);

    /// @notice Updates baseline valuation (restricted to contract owner / authorized updater).
    function setValuation(uint256 tokenId, uint256 newValuationWad) external;
}
