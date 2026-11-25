// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";

/// @dev One-time binding resolves H02 tokens -> HI02 Pool deployment ordering.
abstract contract PoolControlled is Ownable {
    address private _lendingPool;

    error UnauthorizedPool(address caller);
    error InvalidPool(address candidate);
    error PoolAlreadyConfigured(address pool);

    event LendingPoolConfigured(address indexed pool);

    constructor() Ownable(msg.sender) {}

    modifier onlyPool() {
        if (msg.sender != _lendingPool) revert UnauthorizedPool(msg.sender);
        _;
    }

    function lendingPool() public view virtual returns (address) {
        return _lendingPool;
    }

    /// @notice Owner binds the deployed HI02 Pool once; EOAs and rebinding are rejected.
    function setLendingPool(address pool) external onlyOwner {
        if (_lendingPool != address(0)) revert PoolAlreadyConfigured(_lendingPool);
        if (pool == address(0) || pool.code.length == 0) revert InvalidPool(pool);
        _lendingPool = pool;
        emit LendingPoolConfigured(pool);
    }
}
