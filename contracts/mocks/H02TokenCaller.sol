// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {ERC721Holder} from "@openzeppelin/contracts/token/ERC721/utils/ERC721Holder.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";

/// @dev TEST ONLY: forwards token calls and accepts NFTs. No lending, debt or payout logic.
///      Never export/deploy/register this as the production LendingPool.
contract H02TokenCaller is ERC721Holder, Ownable {
    constructor() Ownable(msg.sender) {}

    function execute(address target, bytes calldata data) external onlyOwner returns (bytes memory) {
        (bool ok, bytes memory result) = target.call(data);
        if (!ok) {
            assembly ("memory-safe") {
                revert(add(result, 32), mload(result))
            }
        }
        return result;
    }
}
