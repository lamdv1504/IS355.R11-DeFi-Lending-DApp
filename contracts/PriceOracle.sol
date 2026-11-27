// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import {Math} from "@openzeppelin/contracts/utils/math/Math.sol";

import {IPriceOracle} from "./interfaces/IPriceOracle.sol";
import {ICollateralNFT} from "./interfaces/ICollateralNFT.sol";
import {ProtocolConstants} from "./libraries/ProtocolConstants.sol";

/// @title PriceOracle - Authorized Collateral Valuation & Local Demo Price-Drop Oracle (HI05).
/// @notice Provides MyUSDT WAD (1e18) valuations for ERC-20 collateral tokens and `CollateralNFT`
///         assets, applying an owner-controlled global market multiplier (`priceMultiplierBps`,
///         default 10_000 = 100%, e.g. 6_000 = -40% drop to trigger Health Factor < 1.0).
/// @dev Strictly enforces `onlyOwner` on every state-mutating price function so unauthorized
///      wallets can never manipulate valuations or force illegitimate liquidations.
///      Simulated price drops are intended for local Hardhat demos & automated tests only.
contract PriceOracle is IPriceOracle, Ownable {
    /// @notice Asset identifier key used in `PriceUpdated` events for ERC-20 collateral token.
    bytes32 public constant COLLATERAL_TOKEN_KEY = keccak256("COLLATERAL_TOKEN");

    /// @notice Upper sanity bound for global price multiplier (50_000 BPS = 500%).
    uint256 public constant MAX_MULTIPLIER_BPS = 50_000;

    /// @notice Canonical `CollateralNFT` contract whose base `valuation(tokenId)` is read by default.
    ICollateralNFT public immutable collateralNFT;

    /// @notice Unscaled base price of 1 unit of ERC-20 collateral token in MyUSDT WAD (default 1e18).
    uint256 public collateralTokenBasePriceWad;

    /// @notice Global market price multiplier in BPS (10_000 = 100%, 6_000 = 60% / -40% crash).
    uint256 private _priceMultiplierBps;

    /// @notice Optional per-tokenId base valuation override in MyUSDT WAD (before multiplier).
    mapping(uint256 => uint256) private _nftValuationOverrides;
    mapping(uint256 => bool) private _hasNftOverride;

    error InvalidAddress();
    error InvalidMultiplierBps(uint256 providedBps, uint256 maxBps);

    constructor(address _collateralNFT) Ownable(msg.sender) {
        if (_collateralNFT == address(0)) revert InvalidAddress();
        collateralNFT = ICollateralNFT(_collateralNFT);
        collateralTokenBasePriceWad = ProtocolConstants.DEFAULT_COLLATERAL_TOKEN_PRICE_WAD;
        _priceMultiplierBps = ProtocolConstants.DEFAULT_PRICE_MULTIPLIER_BPS;
    }

    // -------------------------------------------------------------------------
    // View Functions (IPriceOracle)
    // -------------------------------------------------------------------------

    /// @inheritdoc IPriceOracle
    function getCollateralTokenPrice() public view override returns (uint256) {
        return Math.mulDiv(collateralTokenBasePriceWad, _priceMultiplierBps, ProtocolConstants.BPS);
    }

    /// @inheritdoc IPriceOracle
    function getCollateralNFTValuation(uint256 tokenId) external view override returns (uint256) {
        uint256 baseValuation = getNFTBaseValuation(tokenId);
        return Math.mulDiv(baseValuation, _priceMultiplierBps, ProtocolConstants.BPS);
    }

    /// @inheritdoc IPriceOracle
    function priceMultiplierBps() external view override returns (uint256) {
        return _priceMultiplierBps;
    }

    /// @notice Returns true if `tokenId` currently uses an explicit oracle valuation override.
    function hasNFTValuationOverride(uint256 tokenId) external view returns (bool) {
        return _hasNftOverride[tokenId];
    }

    /// @notice Returns the unscaled base valuation (WAD) of `tokenId` before `priceMultiplierBps`.
    function getNFTBaseValuation(uint256 tokenId) public view returns (uint256) {
        if (_hasNftOverride[tokenId]) {
            return _nftValuationOverrides[tokenId];
        }
        return collateralNFT.valuation(tokenId);
    }

    // -------------------------------------------------------------------------
    // Owner-Restricted Price Management (HI05 Security Guard)
    // -------------------------------------------------------------------------

    /// @inheritdoc IPriceOracle
    function setCollateralTokenPrice(uint256 newPriceWad) external override onlyOwner {
        uint256 oldEffectivePrice = getCollateralTokenPrice();
        collateralTokenBasePriceWad = newPriceWad;
        uint256 newEffectivePrice = getCollateralTokenPrice();
        emit PriceUpdated(COLLATERAL_TOKEN_KEY, oldEffectivePrice, newEffectivePrice, block.timestamp);
    }

    /// @inheritdoc IPriceOracle
    function setCollateralNFTValuation(
        uint256 tokenId,
        uint256 newValuationWad
    ) external override onlyOwner {
        uint256 oldEffective = Math.mulDiv(
            getNFTBaseValuation(tokenId),
            _priceMultiplierBps,
            ProtocolConstants.BPS
        );
        _nftValuationOverrides[tokenId] = newValuationWad;
        _hasNftOverride[tokenId] = true;
        uint256 newEffective = Math.mulDiv(
            newValuationWad,
            _priceMultiplierBps,
            ProtocolConstants.BPS
        );
        emit PriceUpdated(bytes32(tokenId), oldEffective, newEffective, block.timestamp);
    }

    /// @notice Clears a per-tokenId override so valuation falls back to `CollateralNFT.valuation(tokenId)`.
    function clearCollateralNFTValuationOverride(uint256 tokenId) external onlyOwner {
        uint256 oldEffective = Math.mulDiv(
            getNFTBaseValuation(tokenId),
            _priceMultiplierBps,
            ProtocolConstants.BPS
        );
        delete _nftValuationOverrides[tokenId];
        delete _hasNftOverride[tokenId];
        uint256 newEffective = Math.mulDiv(
            collateralNFT.valuation(tokenId),
            _priceMultiplierBps,
            ProtocolConstants.BPS
        );
        emit PriceUpdated(bytes32(tokenId), oldEffective, newEffective, block.timestamp);
    }

    /// @inheritdoc IPriceOracle
    function setPriceMultiplierBps(uint256 newMultiplierBps) external override onlyOwner {
        if (newMultiplierBps > MAX_MULTIPLIER_BPS) {
            revert InvalidMultiplierBps(newMultiplierBps, MAX_MULTIPLIER_BPS);
        }
        uint256 oldMultiplier = _priceMultiplierBps;
        uint256 oldEffectiveTokenPrice = getCollateralTokenPrice();

        _priceMultiplierBps = newMultiplierBps;
        uint256 newEffectiveTokenPrice = getCollateralTokenPrice();

        emit PriceMultiplierUpdated(oldMultiplier, newMultiplierBps, block.timestamp);
        emit PriceUpdated(
            COLLATERAL_TOKEN_KEY,
            oldEffectiveTokenPrice,
            newEffectiveTokenPrice,
            block.timestamp
        );
    }

    /// @notice Resets token base price (1e18) and global multiplier (10_000 BPS) after a local demo.
    function resetDemoPrices() external onlyOwner {
        uint256 oldMultiplier = _priceMultiplierBps;
        uint256 oldEffectiveTokenPrice = getCollateralTokenPrice();

        collateralTokenBasePriceWad = ProtocolConstants.DEFAULT_COLLATERAL_TOKEN_PRICE_WAD;
        _priceMultiplierBps = ProtocolConstants.DEFAULT_PRICE_MULTIPLIER_BPS;

        uint256 newEffectiveTokenPrice = getCollateralTokenPrice();
        emit PriceMultiplierUpdated(oldMultiplier, _priceMultiplierBps, block.timestamp);
        emit PriceUpdated(
            COLLATERAL_TOKEN_KEY,
            oldEffectiveTokenPrice,
            newEffectiveTokenPrice,
            block.timestamp
        );
    }
}
