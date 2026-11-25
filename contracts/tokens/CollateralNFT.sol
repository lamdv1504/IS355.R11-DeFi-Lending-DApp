// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {ERC721} from "@openzeppelin/contracts/token/ERC721/ERC721.sol";
import {ERC721URIStorage} from "@openzeppelin/contracts/token/ERC721/extensions/ERC721URIStorage.sol";
import {IERC165} from "@openzeppelin/contracts/utils/introspection/IERC165.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import {ICollateralNFT} from "../interfaces/ICollateralNFT.sol";

/// @notice Underlying collateral asset. Pool custody uses normal ERC-721 transfers.
contract CollateralNFT is ERC721URIStorage, Ownable, ICollateralNFT {
    uint256 private _nextTokenId = 1;
    mapping(uint256 => uint256) private _valuations;

    error ZeroValuation();
    error EmptyTokenURI();

    constructor() ERC721("Collateral Asset", "COLL") Ownable(msg.sender) {}

    function mintCollateral(address to, uint256 valuationWad, string calldata uri)
        external override onlyOwner returns (uint256 tokenId)
    {
        if (valuationWad == 0) revert ZeroValuation();
        if (bytes(uri).length == 0) revert EmptyTokenURI();
        tokenId = _nextTokenId++;
        _valuations[tokenId] = valuationWad;
        _setTokenURI(tokenId, uri);
        _safeMint(to, tokenId);
        emit CollateralMinted(tokenId, to, valuationWad, uri);
    }

    function valuation(uint256 tokenId) external view override returns (uint256) {
        _requireOwned(tokenId);
        return _valuations[tokenId];
    }

    /// @dev Zero is allowed to represent a fully impaired asset.
    function setValuation(uint256 tokenId, uint256 newValuationWad) external override onlyOwner {
        _requireOwned(tokenId);
        uint256 oldValuationWad = _valuations[tokenId];
        _valuations[tokenId] = newValuationWad;
        emit CollateralValuationUpdated(tokenId, oldValuationWad, newValuationWad);
    }

    function supportsInterface(bytes4 interfaceId)
        public view override(ERC721URIStorage, IERC165) returns (bool)
    {
        return interfaceId == type(ICollateralNFT).interfaceId || super.supportsInterface(interfaceId);
    }
}
