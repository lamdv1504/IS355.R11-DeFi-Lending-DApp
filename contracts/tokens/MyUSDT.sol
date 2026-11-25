// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";

/// @title MyUSDT - simulated stablecoin for the lending demo (H01).
/// @dev Uses ERC20's standard 18 decimals, approve, allowance and transferFrom.
contract MyUSDT is ERC20, Ownable {
    uint256 public constant INITIAL_SUPPLY = 1_000_000 * 10 ** 18;
    uint256 public constant MAX_FAUCET_AMOUNT = 1_000 * 10 ** 18;

    error InvalidFaucetAmount(uint256 amount);

    event FaucetUsed(address indexed caller, address indexed to, uint256 amount);

    constructor() ERC20("MyUSDT", "MyUSDT") Ownable(msg.sender) {
        _mint(msg.sender, INITIAL_SUPPLY);
    }

    /// @notice Anyone may mint up to 1,000 MyUSDT per call for testing.
    /// @dev This is a per-call limit; repeated calls can increase total supply.
    /// @param to Recipient of the test tokens; cannot be the zero address.
    /// @param amount Amount in base units (1 MyUSDT = 10**18).
    function faucet(address to, uint256 amount) external {
        if (amount == 0 || amount > MAX_FAUCET_AMOUNT) {
            revert InvalidFaucetAmount(amount);
        }
        _mint(to, amount);
        emit FaucetUsed(msg.sender, to, amount);
    }
}
