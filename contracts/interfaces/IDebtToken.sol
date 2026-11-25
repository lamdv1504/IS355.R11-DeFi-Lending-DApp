// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";

/// @title IDebtToken - Non-transferable ERC-20 tracking borrower principal debt on-chain (H02/HI02).
/// @dev Decimals MUST be 18 (matching MyUSDT). Standard `transfer` and `transferFrom` MUST revert.
///      Only `LendingPool` (`onlyPool`) may call `mint` and `burn`.
interface IDebtToken is IERC20 {
    event DebtMinted(address indexed borrower, uint256 amount);
    event DebtBurned(address indexed borrower, uint256 amount);

    /// @notice Mints debt tokens to `borrower` upon `borrow()`. Callable only by `LendingPool`.
    function mint(address borrower, uint256 amount) external;

    /// @notice Burns debt tokens from `borrower` upon `repay()` or `liquidate()`. Callable only by `LendingPool`.
    function burn(address borrower, uint256 amount) external;

    /// @notice Returns the configured LendingPool address authorized to mint/burn.
    function lendingPool() external view returns (address);
}
