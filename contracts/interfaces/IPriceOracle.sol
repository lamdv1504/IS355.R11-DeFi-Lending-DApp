// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title IPriceOracle - Collateral valuation & price-drop simulation oracle (HI01/HI05).
/// @notice All returned valuations are expressed in MyUSDT WAD (18 decimals).
/// @dev On local Hardhat, the authorized owner can adjust prices/multipliers to demonstrate
///      Health Factor warnings and `liquidate()`. Write functions MUST be restricted (`onlyOwner`).
interface IPriceOracle {
    event PriceUpdated(
        bytes32 indexed assetKey,
        uint256 oldPriceWad,
        uint256 newPriceWad,
        uint256 timestamp
    );

    event PriceMultiplierUpdated(
        uint256 oldMultiplierBps,
        uint256 newMultiplierBps,
        uint256 timestamp
    );

    /// @notice Returns the current price of 1 unit of ERC-20 collateral token in MyUSDT WAD (1e18).
    function getCollateralTokenPrice() external view returns (uint256);

    /// @notice Returns the effective market value of a `CollateralNFT` tokenId in MyUSDT WAD (1e18).
    function getCollateralNFTValuation(uint256 tokenId) external view returns (uint256);

    /// @notice Returns the global demo price multiplier in BPS (default 10_000 = 100%, 6_000 = -40%).
    function priceMultiplierBps() external view returns (uint256);

    /// @notice Updates ERC-20 collateral price (WAD). Restricted to oracle owner.
    function setCollateralTokenPrice(uint256 newPriceWad) external;

    /// @notice Sets a specific override valuation for a `CollateralNFT` tokenId (WAD). Restricted to oracle owner.
    function setCollateralNFTValuation(uint256 tokenId, uint256 newValuationWad) external;

    /// @notice Updates global market price multiplier in BPS (e.g., 6000 simulates a 40% drop). Restricted to oracle owner.
    function setPriceMultiplierBps(uint256 newMultiplierBps) external;
}
