// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import {Math} from "@openzeppelin/contracts/utils/math/Math.sol";

import {IPriceOracle} from "../interfaces/IPriceOracle.sol";
import {ICollateralNFT} from "../interfaces/ICollateralNFT.sol";
import {ProtocolConstants} from "../libraries/ProtocolConstants.sol";

/// @title MockPriceOracle - Test-only IPriceOracle double for HI03 dynamic LTV constraint tests.
/// @dev Production `contracts/PriceOracle.sol` is implemented in HI05.
contract MockPriceOracle is IPriceOracle, Ownable {
    ICollateralNFT public immutable collateralNFT;

    uint256 private _collateralTokenPriceWad;
    uint256 private _priceMultiplierBps;
    mapping(uint256 => uint256) private _nftValuationOverrides;
    mapping(uint256 => bool) private _hasNftOverride;

    bytes32 public constant COLLATERAL_TOKEN_KEY = keccak256("COLLATERAL_TOKEN");

    constructor(address _collateralNFT) Ownable(msg.sender) {
        collateralNFT = ICollateralNFT(_collateralNFT);
        _collateralTokenPriceWad = ProtocolConstants.DEFAULT_COLLATERAL_TOKEN_PRICE_WAD;
        _priceMultiplierBps = ProtocolConstants.DEFAULT_PRICE_MULTIPLIER_BPS;
    }

    function getCollateralTokenPrice() external view override returns (uint256) {
        return Math.mulDiv(_collateralTokenPriceWad, _priceMultiplierBps, ProtocolConstants.BPS);
    }

    function getCollateralNFTValuation(uint256 tokenId) external view override returns (uint256) {
        uint256 baseValuation = _hasNftOverride[tokenId]
            ? _nftValuationOverrides[tokenId]
            : collateralNFT.valuation(tokenId);
        return Math.mulDiv(baseValuation, _priceMultiplierBps, ProtocolConstants.BPS);
    }

    function priceMultiplierBps() external view override returns (uint256) {
        return _priceMultiplierBps;
    }

    function setCollateralTokenPrice(uint256 newPriceWad) external override onlyOwner {
        uint256 oldPrice = _collateralTokenPriceWad;
        _collateralTokenPriceWad = newPriceWad;
        emit PriceUpdated(COLLATERAL_TOKEN_KEY, oldPrice, newPriceWad, block.timestamp);
    }

    function setCollateralNFTValuation(uint256 tokenId, uint256 newValuationWad) external override onlyOwner {
        uint256 oldValuation = _hasNftOverride[tokenId]
            ? _nftValuationOverrides[tokenId]
            : collateralNFT.valuation(tokenId);
        _nftValuationOverrides[tokenId] = newValuationWad;
        _hasNftOverride[tokenId] = true;
        emit PriceUpdated(bytes32(tokenId), oldValuation, newValuationWad, block.timestamp);
    }

    function setPriceMultiplierBps(uint256 newMultiplierBps) external override onlyOwner {
        uint256 oldMultiplier = _priceMultiplierBps;
        _priceMultiplierBps = newMultiplierBps;
        emit PriceMultiplierUpdated(oldMultiplier, newMultiplierBps, block.timestamp);
    }
}
