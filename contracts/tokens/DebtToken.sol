// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {IDebtToken} from "../interfaces/IDebtToken.sol";
import {PoolControlled} from "./base/PoolControlled.sol";

/// @notice Tracks principal only; interest accounting remains in LendingPool (HI02/HI04).
contract DebtToken is ERC20, PoolControlled, IDebtToken {
    error ZeroDebtAmount();
    error DebtNonTransferable();

    constructor() ERC20("Lending Debt", "DEBT") {}

    function lendingPool() public view override(PoolControlled, IDebtToken) returns (address) {
        return super.lendingPool();
    }

    function mint(address borrower, uint256 amount) external override onlyPool {
        if (amount == 0) revert ZeroDebtAmount();
        _mint(borrower, amount);
        emit DebtMinted(borrower, amount);
    }

    function burn(address borrower, uint256 amount) external override onlyPool {
        if (amount == 0) revert ZeroDebtAmount();
        _burn(borrower, amount);
        emit DebtBurned(borrower, amount);
    }

    function transfer(address, uint256) public pure override(ERC20, IERC20) returns (bool) {
        revert DebtNonTransferable();
    }

    function transferFrom(address, address, uint256) public pure override(ERC20, IERC20) returns (bool) {
        revert DebtNonTransferable();
    }

    function _update(address from, address to, uint256 amount) internal override {
        if (from != address(0) && to != address(0)) revert DebtNonTransferable();
        super._update(from, to, amount);
    }
}
