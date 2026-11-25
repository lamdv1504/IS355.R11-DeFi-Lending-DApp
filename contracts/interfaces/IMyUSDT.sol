// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";

/// @title IMyUSDT - Interface matching H01 `contracts/tokens/MyUSDT.sol`.
interface IMyUSDT is IERC20 {
    error InvalidFaucetAmount(uint256 amount);

    event FaucetUsed(address indexed caller, address indexed to, uint256 amount);

    function INITIAL_SUPPLY() external view returns (uint256);

    function MAX_FAUCET_AMOUNT() external view returns (uint256);

    function faucet(address to, uint256 amount) external;
}
