// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {ERC721} from "@openzeppelin/contracts/token/ERC721/ERC721.sol";
import {IERC165} from "@openzeppelin/contracts/utils/introspection/IERC165.sol";
import {ILendingPositionNFT} from "../interfaces/ILendingPositionNFT.sol";
import {PoolControlled} from "./base/PoolControlled.sol";

/// @notice Transferable claim identifier. HI02 pays principal/interest to current ownerOf.
contract LendingPositionNFT is ERC721, PoolControlled, ILendingPositionNFT {
    uint256 private _nextPositionId = 1;

    error ZeroPositionAmount();

    constructor() ERC721("Lending Position", "LPOS") {}

    function lendingPool() public view override(PoolControlled, ILendingPositionNFT) returns (address) {
        return super.lendingPool();
    }

    function mintPosition(address lender, uint256 amountWad)
        external override onlyPool returns (uint256 positionId)
    {
        if (amountWad == 0) revert ZeroPositionAmount();
        positionId = _nextPositionId++;
        _safeMint(lender, positionId);
        emit PositionMinted(positionId, lender, amountWad);
    }

    function burnPosition(uint256 positionId) external override onlyPool {
        address currentOwner = ownerOf(positionId);
        _burn(positionId);
        emit PositionBurned(positionId, currentOwner);
    }

    function supportsInterface(bytes4 interfaceId)
        public view override(ERC721, IERC165) returns (bool)
    {
        return interfaceId == type(ILendingPositionNFT).interfaceId || super.supportsInterface(interfaceId);
    }
}
