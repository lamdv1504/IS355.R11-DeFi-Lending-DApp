// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {IERC721} from "@openzeppelin/contracts/token/ERC721/IERC721.sol";

/// @title ILendingPositionNFT - Transferable ERC-721 representing a Lender's claim on Pool principal + interest (H02/HI02/HI03).
/// @notice Transferring this NFT from Lender A to Lender B transfers the exclusive right to call
///         `withdrawLender(positionId, amount)` via `ownerOf(positionId) == msg.sender`.
interface ILendingPositionNFT is IERC721 {
    event PositionMinted(uint256 indexed positionId, address indexed lender, uint256 amountWad);
    event PositionBurned(uint256 indexed positionId, address indexed owner);

    /// @notice Mints a new LendingPositionNFT for `lender`. Callable only by `LendingPool`.
    function mintPosition(address lender, uint256 amountWad) external returns (uint256 positionId);

    /// @notice Burns a fully withdrawn LendingPositionNFT. Callable only by `LendingPool`.
    function burnPosition(uint256 positionId) external;

    /// @notice Returns the configured LendingPool address authorized to mint/burn.
    function lendingPool() external view returns (address);
}
