// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {IERC721Receiver} from "@openzeppelin/contracts/token/ERC721/IERC721Receiver.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import {Math} from "@openzeppelin/contracts/utils/math/Math.sol";

import {ILendingPool} from "./interfaces/ILendingPool.sol";
import {IMyUSDT} from "./interfaces/IMyUSDT.sol";
import {ICollateralNFT} from "./interfaces/ICollateralNFT.sol";
import {ICollateralReceiptNFT} from "./interfaces/ICollateralReceiptNFT.sol";
import {IDebtToken} from "./interfaces/IDebtToken.sol";
import {ILendingPositionNFT} from "./interfaces/ILendingPositionNFT.sol";
import {IPriceOracle} from "./interfaces/IPriceOracle.sol";
import {ProtocolConstants} from "./libraries/ProtocolConstants.sol";
import {ProtocolMath} from "./libraries/ProtocolMath.sol";

/// @title LendingPool - Core DeFi Credit & Lending Contract (HI02/HI03/HI04/HI05).
/// @notice Implements lender deposits/withdrawals via transferable LendingPositionNFT,
///         ERC-20 & CollateralNFT custody via soulbound CollateralReceiptNFT,
///         DebtToken principal tracking, LTV <= 70%, real-balance liquidity checks,
///         non-retroactive timestamp interest accrual, and Health Factor liquidation.
contract LendingPool is ILendingPool, ReentrancyGuard, Ownable, IERC721Receiver {
    using SafeERC20 for IERC20;
    using SafeERC20 for IMyUSDT;

    // -------------------------------------------------------------------------
    // Immutable Token & NFT Dependencies (H01 & H02)
    // -------------------------------------------------------------------------

    IMyUSDT public immutable myUSDT;
    IERC20 public immutable collateralToken;
    ICollateralNFT public immutable collateralNFT;
    ICollateralReceiptNFT public immutable collateralReceiptNFT;
    IDebtToken public immutable debtToken;
    ILendingPositionNFT public immutable lendingPositionNFT;

    /// @notice Optional PriceOracle (address(0) falls back to CollateralNFT.valuation & 1:1 token price until HI05).
    IPriceOracle public priceOracle;

    // -------------------------------------------------------------------------
    // Pool & Position State
    // -------------------------------------------------------------------------

    PoolInfo private _pool;

    /// @notice Total ERC-20 collateral currently locked inside the pool (segregated from lender liquidity).
    uint256 public totalTokenCollateralLocked;

    mapping(uint256 => LenderPosition) private _lenderPositions;
    mapping(address => LoanPosition) private _loanPositions;

    // -------------------------------------------------------------------------
    // Additional Security Errors & Admin Events
    // -------------------------------------------------------------------------

    error UnauthorizedNFTTransfer(address token, address operator);

    event PriceOracleUpdated(address indexed oldOracle, address indexed newOracle);
    event ReservedLiquidityUpdated(uint256 oldReserved, uint256 newReserved);

    // -------------------------------------------------------------------------
    // Constructor & Admin Configuration
    // -------------------------------------------------------------------------

    constructor(
        address _myUSDT,
        address _collateralToken,
        address _collateralNFT,
        address _collateralReceiptNFT,
        address _debtToken,
        address _lendingPositionNFT,
        address _priceOracle
    ) Ownable(msg.sender) {
        if (
            _myUSDT == address(0) ||
            _collateralToken == address(0) ||
            _collateralNFT == address(0) ||
            _collateralReceiptNFT == address(0) ||
            _debtToken == address(0) ||
            _lendingPositionNFT == address(0)
        ) {
            revert InvalidAddress();
        }

        myUSDT = IMyUSDT(_myUSDT);
        collateralToken = IERC20(_collateralToken);
        collateralNFT = ICollateralNFT(_collateralNFT);
        collateralReceiptNFT = ICollateralReceiptNFT(_collateralReceiptNFT);
        debtToken = IDebtToken(_debtToken);
        lendingPositionNFT = ILendingPositionNFT(_lendingPositionNFT);

        if (_priceOracle != address(0)) {
            priceOracle = IPriceOracle(_priceOracle);
        }

        _pool = PoolInfo({
            totalSupplied: 0,
            totalBorrowed: 0,
            reservedLiquidity: 0,
            borrowIndex: ProtocolConstants.INITIAL_INDEX_WAD,
            supplyIndex: ProtocolConstants.INITIAL_INDEX_WAD,
            borrowAprBps: ProtocolConstants.BASE_BORROW_APR_BPS,
            supplyAprBps: 0,
            utilizationBps: 0,
            lastAccrualTimestamp: block.timestamp
        });
    }

    /// @notice Configures or updates the PriceOracle address (used when binding HI05 PriceOracle).
    function setPriceOracle(address newOracle) external onlyOwner {
        if (newOracle == address(0)) revert InvalidAddress();
        address oldOracle = address(priceOracle);
        priceOracle = IPriceOracle(newOracle);
        emit PriceOracleUpdated(oldOracle, newOracle);
    }

    /// @notice Optionally reserves liquidity buffer against withdrawals (default 0 in MVP).
    function setReservedLiquidity(uint256 newReservedLiquidity) external onlyOwner {
        uint256 oldReserved = _pool.reservedLiquidity;
        _pool.reservedLiquidity = newReservedLiquidity;
        emit ReservedLiquidityUpdated(oldReserved, newReservedLiquidity);
    }

    /// @notice Accepts CollateralNFT transfers ONLY when initiated by this pool inside `depositCollateral`.
    function onERC721Received(
        address operator,
        address,
        uint256,
        bytes calldata
    ) external view override returns (bytes4) {
        if (msg.sender != address(collateralNFT) || operator != address(this)) {
            revert UnauthorizedNFTTransfer(msg.sender, operator);
        }
        return IERC721Receiver.onERC721Received.selector;
    }

    // -------------------------------------------------------------------------
    // Core Write Functions (HI02 / HI03 / HI04 / HI05)
    // -------------------------------------------------------------------------

    /// @inheritdoc ILendingPool
    function depositLender(uint256 amount) external override nonReentrant returns (uint256 positionId) {
        if (amount == 0) revert ZeroAmount();

        _accruePoolInterest();

        myUSDT.safeTransferFrom(msg.sender, address(this), amount);

        _pool.totalSupplied += amount;
        _updateInterestRates();

        uint256 currentSupplyIndex = _pool.supplyIndex;
        positionId = lendingPositionNFT.mintPosition(msg.sender, amount);

        _lenderPositions[positionId] = LenderPosition({
            positionId: positionId,
            principal: amount,
            supplyIndexSnapshot: currentSupplyIndex,
            accruedInterest: 0,
            depositedAt: block.timestamp,
            active: true
        });

        emit LenderDeposited(msg.sender, positionId, amount, block.timestamp);
    }

    /// @inheritdoc ILendingPool
    function withdrawLender(uint256 positionId, uint256 amount) external override nonReentrant {
        if (amount == 0) revert ZeroAmount();

        LenderPosition storage pos = _lenderPositions[positionId];
        if (!pos.active) revert PositionNotFound(positionId);

        // Always authorize against the CURRENT NFT owner (supports LendingPositionNFT transfer A -> B)
        address currentOwner = lendingPositionNFT.ownerOf(positionId);
        if (currentOwner != msg.sender) revert NotPositionOwner(positionId, msg.sender);

        _accruePoolInterest();
        _checkpointLenderPosition(pos);

        uint256 claimable = pos.principal + pos.accruedInterest;
        if (amount > claimable) revert InsufficientClaimableBalance(amount, claimable);

        uint256 available = getAvailableLiquidity();
        if (amount > available) revert InsufficientPoolLiquidity(amount, available);

        // Pay accrued interest first, then principal (prevents double-claiming across transfers)
        uint256 interestWithdrawn = amount > pos.accruedInterest ? pos.accruedInterest : amount;
        uint256 principalWithdrawn = amount - interestWithdrawn;

        pos.accruedInterest -= interestWithdrawn;
        pos.principal -= principalWithdrawn;
        _pool.totalSupplied -= principalWithdrawn;

        bool fullyWithdrawn = pos.principal == 0 && pos.accruedInterest == 0;
        if (fullyWithdrawn) {
            pos.active = false;
        }

        _updateInterestRates();

        if (fullyWithdrawn) {
            lendingPositionNFT.burnPosition(positionId);
        }

        myUSDT.safeTransfer(msg.sender, amount);

        emit LenderWithdrawn(msg.sender, positionId, principalWithdrawn, interestWithdrawn, block.timestamp);
    }

    /// @inheritdoc ILendingPool
    function depositCollateral(
        uint256 amountOrTokenId,
        bool isNFT
    ) external override nonReentrant returns (uint256 receiptId) {
        LoanPosition storage loan = _loanPositions[msg.sender];
        if (loan.active) revert CollateralAlreadyLocked(msg.sender);

        _accruePoolInterest();

        uint256 valuationWad;
        if (isNFT) {
            valuationWad = _getNFTValuation(amountOrTokenId);
            collateralNFT.safeTransferFrom(msg.sender, address(this), amountOrTokenId);

            // Set storage BEFORE mintReceipt safeMint callback (CEI + nonReentrant)
            loan.borrower = msg.sender;
            loan.isNFTCollateral = true;
            loan.collateralAmount = 0;
            loan.collateralTokenId = amountOrTokenId;
            loan.principal = 0;
            loan.borrowIndexSnapshot = _pool.borrowIndex;
            loan.accruedInterest = 0;
            loan.startTimestamp = 0;
            loan.lastInterestUpdate = block.timestamp;
            loan.ipfsAgreementCid = "";
            loan.active = true;

            receiptId = collateralReceiptNFT.mintReceipt(msg.sender, true, amountOrTokenId);
            loan.receiptTokenId = receiptId;
        } else {
            if (amountOrTokenId == 0) revert ZeroAmount();

            collateralToken.safeTransferFrom(msg.sender, address(this), amountOrTokenId);
            totalTokenCollateralLocked += amountOrTokenId;
            valuationWad = _getTokenCollateralValue(amountOrTokenId);

            loan.borrower = msg.sender;
            loan.isNFTCollateral = false;
            loan.collateralAmount = amountOrTokenId;
            loan.collateralTokenId = 0;
            loan.principal = 0;
            loan.borrowIndexSnapshot = _pool.borrowIndex;
            loan.accruedInterest = 0;
            loan.startTimestamp = 0;
            loan.lastInterestUpdate = block.timestamp;
            loan.ipfsAgreementCid = "";
            loan.active = true;

            receiptId = collateralReceiptNFT.mintReceipt(msg.sender, false, amountOrTokenId);
            loan.receiptTokenId = receiptId;
        }

        emit CollateralDeposited(
            msg.sender,
            isNFT,
            amountOrTokenId,
            receiptId,
            valuationWad,
            block.timestamp
        );
    }

    /// @inheritdoc ILendingPool
    function withdrawCollateral() external override nonReentrant {
        LoanPosition storage loan = _loanPositions[msg.sender];
        if (!loan.active) revert NoActiveCollateral(msg.sender);

        _accruePoolInterest();
        _checkpointBorrowerLoan(loan);

        uint256 totalDebt = loan.principal + loan.accruedInterest;
        if (totalDebt > 0) revert OutstandingDebtExists(totalDebt);

        _releaseCollateralAndSettleReceipt(loan, msg.sender);
    }

    /// @inheritdoc ILendingPool
    function borrow(uint256 amount, string calldata agreementCid) external override nonReentrant {
        if (amount == 0) revert ZeroAmount();
        if (bytes(agreementCid).length == 0) revert EmptyAgreementCid();

        LoanPosition storage loan = _loanPositions[msg.sender];
        if (!loan.active) revert NoActiveCollateral(msg.sender);

        _accruePoolInterest();
        _checkpointBorrowerLoan(loan);

        uint256 maxBorrowable = getMaxBorrowable(msg.sender);
        uint256 requestedTotalDebt = loan.principal + loan.accruedInterest + amount;
        if (requestedTotalDebt > maxBorrowable) {
            revert ExceedsMaxLTV(requestedTotalDebt, maxBorrowable);
        }

        uint256 available = getAvailableLiquidity();
        if (amount > available) {
            revert InsufficientPoolLiquidity(amount, available);
        }

        if (loan.startTimestamp == 0) {
            loan.startTimestamp = block.timestamp;
        }
        loan.principal += amount;
        loan.ipfsAgreementCid = agreementCid;
        loan.lastInterestUpdate = block.timestamp;
        _pool.totalBorrowed += amount;

        _updateInterestRates();

        debtToken.mint(msg.sender, amount);
        myUSDT.safeTransfer(msg.sender, amount);

        emit LoanBorrowed(
            msg.sender,
            amount,
            loan.principal,
            _pool.borrowAprBps,
            agreementCid,
            block.timestamp
        );
    }

    /// @inheritdoc ILendingPool
    function repay(uint256 amount) external override nonReentrant {
        if (amount == 0) revert ZeroAmount();

        LoanPosition storage loan = _loanPositions[msg.sender];
        if (!loan.active) revert NoActiveCollateral(msg.sender);

        _accruePoolInterest();
        _checkpointBorrowerLoan(loan);

        uint256 totalDebt = loan.principal + loan.accruedInterest;
        if (totalDebt == 0) revert ZeroAmount();

        // Cap payment at exact totalDebt so MetaMask users passing a slight buffer never overpay
        uint256 actualPayment = amount > totalDebt ? totalDebt : amount;
        uint256 interestPaid = actualPayment > loan.accruedInterest ? loan.accruedInterest : actualPayment;
        uint256 principalPaid = actualPayment - interestPaid;

        myUSDT.safeTransferFrom(msg.sender, address(this), actualPayment);

        loan.accruedInterest -= interestPaid;
        loan.principal -= principalPaid;
        loan.lastInterestUpdate = block.timestamp;
        _pool.totalBorrowed -= principalPaid;

        uint256 remainingDebt = loan.principal + loan.accruedInterest;

        _updateInterestRates();

        if (principalPaid > 0) {
            debtToken.burn(msg.sender, principalPaid);
        }

        emit LoanRepaid(
            msg.sender,
            actualPayment,
            interestPaid,
            principalPaid,
            remainingDebt,
            block.timestamp
        );

        // Automatically unlock collateral and settle receipt once debt reaches 0 (HI02 step 5)
        if (remainingDebt == 0) {
            _releaseCollateralAndSettleReceipt(loan, msg.sender);
        }
    }

    /// @inheritdoc ILendingPool
    function liquidate(address borrower) external override nonReentrant {
        LoanPosition storage loan = _loanPositions[borrower];
        if (!loan.active) revert NoActiveCollateral(borrower);

        _accruePoolInterest();
        _checkpointBorrowerLoan(loan);

        uint256 totalDebt = loan.principal + loan.accruedInterest;
        uint256 collateralValue = getCollateralValue(borrower);
        uint256 hfBefore = ProtocolMath.calculateHealthFactor(collateralValue, totalDebt);
        if (!ProtocolMath.isLiquidatable(hfBefore)) {
            revert HealthFactorSafe(hfBefore);
        }

        myUSDT.safeTransferFrom(msg.sender, address(this), totalDebt);

        uint256 principalToBurn = loan.principal;
        bool isNFT = loan.isNFTCollateral;
        uint256 tokenId = loan.collateralTokenId;
        uint256 tokenAmount = loan.collateralAmount;
        uint256 receiptId = loan.receiptTokenId;

        _pool.totalBorrowed -= principalToBurn;
        delete _loanPositions[borrower];

        _updateInterestRates();

        if (principalToBurn > 0) {
            debtToken.burn(borrower, principalToBurn);
        }

        uint256 collateralSeizedWad;
        if (isNFT) {
            collateralSeizedWad = collateralValue;
            collateralNFT.safeTransferFrom(address(this), msg.sender, tokenId);
        } else {
            collateralSeizedWad = ProtocolMath.calculateLiquidationSeizeValue(totalDebt, collateralValue);
            uint256 tokenPrice = _getCollateralTokenPrice();
            uint256 seizeTokenAmount = tokenPrice > 0
                ? Math.mulDiv(collateralSeizedWad, ProtocolConstants.WAD, tokenPrice)
                : tokenAmount;
            if (seizeTokenAmount > tokenAmount) {
                seizeTokenAmount = tokenAmount;
            }

            totalTokenCollateralLocked -= tokenAmount;
            collateralToken.safeTransfer(msg.sender, seizeTokenAmount);
            if (tokenAmount > seizeTokenAmount) {
                collateralToken.safeTransfer(borrower, tokenAmount - seizeTokenAmount);
            }
        }

        collateralReceiptNFT.settleReceipt(receiptId, true);

        emit LoanLiquidated(
            borrower,
            msg.sender,
            totalDebt,
            collateralSeizedWad,
            hfBefore,
            block.timestamp
        );
    }

    // -------------------------------------------------------------------------
    // View Functions (Real-Time Preview Including Uncheckpointed Interest)
    // -------------------------------------------------------------------------

    /// @inheritdoc ILendingPool
    function getPoolInfo() external view override returns (PoolInfo memory info) {
        info = _pool;
        (uint256 nextBorrowIdx, uint256 nextSupplyIdx) = _previewIndices();
        info.borrowIndex = nextBorrowIdx;
        info.supplyIndex = nextSupplyIdx;
    }

    /// @inheritdoc ILendingPool
    function getAvailableLiquidity() public view override returns (uint256) {
        uint256 poolBalance = myUSDT.balanceOf(address(this));
        uint256 locked = _pool.reservedLiquidity;
        // Segregate ERC-20 collateral when collateralToken == myUSDT so lender withdrawals never touch collateral
        if (address(collateralToken) == address(myUSDT)) {
            locked += totalTokenCollateralLocked;
        }
        return poolBalance > locked ? poolBalance - locked : 0;
    }

    /// @inheritdoc ILendingPool
    function getCollateralValue(address borrower) public view override returns (uint256) {
        LoanPosition storage loan = _loanPositions[borrower];
        if (!loan.active) return 0;
        if (loan.isNFTCollateral) {
            return _getNFTValuation(loan.collateralTokenId);
        }
        return _getTokenCollateralValue(loan.collateralAmount);
    }

    /// @inheritdoc ILendingPool
    function getMaxBorrowable(address borrower) public view override returns (uint256) {
        return ProtocolMath.calculateMaxBorrow(getCollateralValue(borrower));
    }

    /// @inheritdoc ILendingPool
    function calculateAccruedInterest(address borrower) public view override returns (uint256) {
        LoanPosition storage loan = _loanPositions[borrower];
        if (!loan.active) return 0;
        if (loan.principal == 0) return loan.accruedInterest;

        (uint256 currentBorrowIndex, ) = _previewIndices();
        uint256 snapshot = loan.borrowIndexSnapshot == 0
            ? ProtocolConstants.INITIAL_INDEX_WAD
            : loan.borrowIndexSnapshot;
        if (currentBorrowIndex <= snapshot) return loan.accruedInterest;

        uint256 pendingInterest = Math.mulDiv(
            loan.principal,
            currentBorrowIndex - snapshot,
            ProtocolConstants.WAD
        );
        return loan.accruedInterest + pendingInterest;
    }

    /// @inheritdoc ILendingPool
    function getTotalDebt(address borrower) public view override returns (uint256) {
        LoanPosition storage loan = _loanPositions[borrower];
        if (!loan.active) return 0;
        return loan.principal + calculateAccruedInterest(borrower);
    }

    /// @inheritdoc ILendingPool
    function getHealthFactor(address borrower) external view override returns (uint256) {
        return ProtocolMath.calculateHealthFactor(getCollateralValue(borrower), getTotalDebt(borrower));
    }

    /// @inheritdoc ILendingPool
    function getLenderEarnedInterest(uint256 positionId) public view override returns (uint256) {
        LenderPosition storage pos = _lenderPositions[positionId];
        if (!pos.active) return 0;
        if (pos.principal == 0) return pos.accruedInterest;

        (, uint256 currentSupplyIndex) = _previewIndices();
        uint256 snapshot = pos.supplyIndexSnapshot == 0
            ? ProtocolConstants.INITIAL_INDEX_WAD
            : pos.supplyIndexSnapshot;
        if (currentSupplyIndex <= snapshot) return pos.accruedInterest;

        uint256 pendingEarned = Math.mulDiv(
            pos.principal,
            currentSupplyIndex - snapshot,
            ProtocolConstants.WAD
        );
        return pos.accruedInterest + pendingEarned;
    }

    /// @inheritdoc ILendingPool
    function getLenderClaimableBalance(uint256 positionId) external view override returns (uint256) {
        LenderPosition storage pos = _lenderPositions[positionId];
        if (!pos.active) return 0;
        return pos.principal + getLenderEarnedInterest(positionId);
    }

    /// @inheritdoc ILendingPool
    function getLoanPosition(address borrower) external view override returns (LoanPosition memory) {
        return _loanPositions[borrower];
    }

    /// @inheritdoc ILendingPool
    function getLenderPosition(uint256 positionId) external view override returns (LenderPosition memory) {
        return _lenderPositions[positionId];
    }

    // -------------------------------------------------------------------------
    // Internal Accounting & Collateral Helpers
    // -------------------------------------------------------------------------

    function _previewIndices() internal view returns (uint256 nextBorrowIndex, uint256 nextSupplyIndex) {
        uint256 deltaTime = block.timestamp > _pool.lastAccrualTimestamp
            ? block.timestamp - _pool.lastAccrualTimestamp
            : 0;
        nextBorrowIndex = ProtocolMath.calculateNextIndex(
            _pool.borrowIndex,
            _pool.borrowAprBps,
            deltaTime
        );
        nextSupplyIndex = ProtocolMath.calculateNextIndex(
            _pool.supplyIndex,
            _pool.supplyAprBps,
            deltaTime
        );
    }

    function _accruePoolInterest() internal {
        uint256 deltaTime = block.timestamp > _pool.lastAccrualTimestamp
            ? block.timestamp - _pool.lastAccrualTimestamp
            : 0;
        if (deltaTime > 0) {
            _pool.borrowIndex = ProtocolMath.calculateNextIndex(
                _pool.borrowIndex,
                _pool.borrowAprBps,
                deltaTime
            );
            _pool.supplyIndex = ProtocolMath.calculateNextIndex(
                _pool.supplyIndex,
                _pool.supplyAprBps,
                deltaTime
            );
            _pool.lastAccrualTimestamp = block.timestamp;
        }
    }

    function _updateInterestRates() internal {
        uint256 utilizationBps = ProtocolMath.calculateUtilizationBps(
            _pool.totalBorrowed,
            _pool.totalSupplied
        );
        uint256 borrowAprBps = ProtocolMath.calculateBorrowAprBps(utilizationBps);
        uint256 supplyAprBps = ProtocolMath.calculateSupplyAprBps(borrowAprBps, utilizationBps);

        _pool.utilizationBps = utilizationBps;
        _pool.borrowAprBps = borrowAprBps;
        _pool.supplyAprBps = supplyAprBps;

        emit InterestRateUpdated(
            block.timestamp,
            borrowAprBps,
            supplyAprBps,
            utilizationBps,
            _pool.totalSupplied,
            _pool.totalBorrowed
        );
    }

    function _checkpointBorrowerLoan(LoanPosition storage loan) internal {
        if (loan.principal > 0 && _pool.borrowIndex > loan.borrowIndexSnapshot) {
            uint256 pending = Math.mulDiv(
                loan.principal,
                _pool.borrowIndex - loan.borrowIndexSnapshot,
                ProtocolConstants.WAD
            );
            loan.accruedInterest += pending;
        }
        loan.borrowIndexSnapshot = _pool.borrowIndex;
        loan.lastInterestUpdate = block.timestamp;
    }

    function _checkpointLenderPosition(LenderPosition storage pos) internal {
        if (pos.principal > 0 && _pool.supplyIndex > pos.supplyIndexSnapshot) {
            uint256 pending = Math.mulDiv(
                pos.principal,
                _pool.supplyIndex - pos.supplyIndexSnapshot,
                ProtocolConstants.WAD
            );
            pos.accruedInterest += pending;
        }
        pos.supplyIndexSnapshot = _pool.supplyIndex;
    }

    function _releaseCollateralAndSettleReceipt(
        LoanPosition storage loan,
        address borrower
    ) internal {
        bool isNFT = loan.isNFTCollateral;
        uint256 assetIdOrAmount = isNFT ? loan.collateralTokenId : loan.collateralAmount;
        uint256 receiptId = loan.receiptTokenId;

        // Clear state before external calls (CEI)
        delete _loanPositions[borrower];

        if (isNFT) {
            collateralNFT.safeTransferFrom(address(this), borrower, assetIdOrAmount);
        } else {
            totalTokenCollateralLocked -= assetIdOrAmount;
            collateralToken.safeTransfer(borrower, assetIdOrAmount);
        }

        collateralReceiptNFT.settleReceipt(receiptId, false);

        emit CollateralWithdrawn(borrower, isNFT, assetIdOrAmount, receiptId, block.timestamp);
    }

    function _getCollateralTokenPrice() internal view returns (uint256) {
        if (address(priceOracle) != address(0)) {
            return priceOracle.getCollateralTokenPrice();
        }
        return ProtocolConstants.DEFAULT_COLLATERAL_TOKEN_PRICE_WAD;
    }

    function _getTokenCollateralValue(uint256 tokenAmountWad) internal view returns (uint256) {
        return Math.mulDiv(tokenAmountWad, _getCollateralTokenPrice(), ProtocolConstants.WAD);
    }

    function _getNFTValuation(uint256 tokenId) internal view returns (uint256) {
        if (address(priceOracle) != address(0)) {
            return priceOracle.getCollateralNFTValuation(tokenId);
        }
        return collateralNFT.valuation(tokenId);
    }
}
