// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {IERC721Receiver} from "@openzeppelin/contracts/token/ERC721/IERC721Receiver.sol";
import {ILendingPool} from "../interfaces/ILendingPool.sol";
import {IMyUSDT} from "../interfaces/IMyUSDT.sol";

/// @title ReentrantAttacker - Test mock proving ReentrancyGuard protects LendingPool callbacks (HI02).
contract ReentrantAttacker is IERC721Receiver {
    enum AttackTarget {
        NONE,
        REENTER_DEPOSIT_LENDER,
        REENTER_DEPOSIT_COLLATERAL,
        REENTER_BORROW,
        REENTER_REPAY
    }

    ILendingPool public immutable pool;
    IMyUSDT public immutable myUSDT;
    AttackTarget public attackTarget;
    bool public reentrancyAttempted;
    bool public reentrancyBlocked;

    constructor(address _pool, address _myUSDT) {
        pool = ILendingPool(_pool);
        myUSDT = IMyUSDT(_myUSDT);
    }

    function attackDepositLender(uint256 amount) external {
        attackTarget = AttackTarget.REENTER_DEPOSIT_LENDER;
        reentrancyAttempted = false;
        reentrancyBlocked = false;
        myUSDT.approve(address(pool), amount * 2);
        pool.depositLender(amount);
    }

    function attackDepositCollateralToken(uint256 amount) external {
        attackTarget = AttackTarget.REENTER_DEPOSIT_COLLATERAL;
        reentrancyAttempted = false;
        reentrancyBlocked = false;
        myUSDT.approve(address(pool), amount * 2);
        pool.depositCollateral(amount, false);
    }

    function attackBorrowDuringCollateralMint(uint256 amount) external {
        attackTarget = AttackTarget.REENTER_BORROW;
        reentrancyAttempted = false;
        reentrancyBlocked = false;
        myUSDT.approve(address(pool), amount);
        pool.depositCollateral(amount, false);
    }

    function setupAndAttackRepayWithNFT(
        address collateralNFTAddr,
        uint256 tokenId,
        uint256 borrowAmount,
        string calldata cid
    ) external {
        attackTarget = AttackTarget.NONE;
        (bool ok, ) = collateralNFTAddr.call(
            abi.encodeWithSignature("approve(address,uint256)", address(pool), tokenId)
        );
        require(ok, "approve failed");
        pool.depositCollateral(tokenId, true);
        pool.borrow(borrowAmount, cid);

        // Now trigger repay which calls safeTransferFrom(pool -> attacker) -> onERC721Received
        attackTarget = AttackTarget.REENTER_REPAY;
        reentrancyAttempted = false;
        reentrancyBlocked = false;
        uint256 debt = pool.getTotalDebt(address(this));
        myUSDT.approve(address(pool), debt + 1e18);
        pool.repay(debt + 1e18);
    }

    function onERC721Received(
        address,
        address,
        uint256,
        bytes calldata
    ) external override returns (bytes4) {
        if (attackTarget != AttackTarget.NONE && !reentrancyAttempted) {
            reentrancyAttempted = true;
            if (attackTarget == AttackTarget.REENTER_DEPOSIT_LENDER) {
                try pool.depositLender(1e18) {
                    reentrancyBlocked = false;
                } catch {
                    reentrancyBlocked = true;
                }
            } else if (attackTarget == AttackTarget.REENTER_DEPOSIT_COLLATERAL) {
                try pool.depositCollateral(1e18, false) {
                    reentrancyBlocked = false;
                } catch {
                    reentrancyBlocked = true;
                }
            } else if (attackTarget == AttackTarget.REENTER_BORROW) {
                try pool.borrow(1e18, "bafyReentrancyCid") {
                    reentrancyBlocked = false;
                } catch {
                    reentrancyBlocked = true;
                }
            } else if (attackTarget == AttackTarget.REENTER_REPAY) {
                try pool.repay(1e18) {
                    reentrancyBlocked = false;
                } catch {
                    reentrancyBlocked = true;
                }
            }
        }
        return IERC721Receiver.onERC721Received.selector;
    }
}
