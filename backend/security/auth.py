"""EIP-191 wallet authentication and short-lived HMAC bearer sessions."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import secrets
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Iterable, Mapping

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from eth_account import Account
from eth_account.messages import encode_defunct
from web3 import Web3

from backend.config.settings import AppSettings, settings
from src.ipfs.rbac import AccessContext, Role


class AuthenticationError(ValueError):
    """Raised when a nonce, wallet signature, or session token is invalid."""


class AuthenticationConfigurationError(RuntimeError):
    """Raised when the session signing secret is not configured securely."""


@dataclass(frozen=True)
class _NonceRecord:
    wallet_address: str
    chain_id: int
    domain: str
    message: str
    expires_at: int


class WalletAuthManager:
    """Issue one-use challenges and verify signatures without handling user keys."""

    def __init__(
        self,
        secret: str,
        *,
        domain: str,
        allowed_chain_ids: Iterable[int],
        admin_wallets: Iterable[str] = (),
        lender_wallets: Iterable[str] = (),
        nonce_ttl_seconds: int = 300,
        session_ttl_seconds: int = 3600,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not isinstance(secret, str) or len(secret.encode("utf-8")) < 32:
            raise AuthenticationConfigurationError(
                "AUTH_TOKEN_SECRET must contain at least 32 bytes."
            )
        if not domain.strip():
            raise AuthenticationConfigurationError("AUTH_DOMAIN must not be empty.")
        if nonce_ttl_seconds <= 0 or session_ttl_seconds <= 0:
            raise AuthenticationConfigurationError("Authentication TTLs must be positive.")
        self._secret = secret.encode("utf-8")
        self.domain = domain.strip()
        self.allowed_chain_ids = frozenset(int(chain_id) for chain_id in allowed_chain_ids)
        try:
            self._admin_wallets = self._normalize_wallets(admin_wallets)
            self._lender_wallets = self._normalize_wallets(lender_wallets)
        except AuthenticationError as exc:
            raise AuthenticationConfigurationError(
                "ADMIN_WALLETS and LENDER_WALLETS must contain valid Ethereum addresses."
            ) from exc
        self.nonce_ttl_seconds = nonce_ttl_seconds
        self.session_ttl_seconds = session_ttl_seconds
        self._clock = clock
        self._nonces: dict[str, _NonceRecord] = {}
        self._lock = threading.Lock()

    @classmethod
    def from_settings(cls, config: AppSettings = settings) -> "WalletAuthManager":
        return cls(
            config.auth_token_secret,
            domain=config.auth_domain,
            allowed_chain_ids=(
                config.local_network.chain_id,
                config.sepolia_network.chain_id,
            ),
            admin_wallets=config.admin_wallets,
            lender_wallets=config.lender_wallets,
            nonce_ttl_seconds=config.auth_nonce_ttl_seconds,
            session_ttl_seconds=config.auth_session_ttl_seconds,
        )

    def issue_nonce(
        self, wallet_address: str, chain_id: int, domain: str | None = None
    ) -> dict[str, object]:
        wallet = self._checksum_wallet(wallet_address)
        if isinstance(chain_id, bool) or int(chain_id) not in self.allowed_chain_ids:
            raise AuthenticationError("Unsupported chain_id.")
        requested_domain = self.domain if domain is None else domain.strip()
        if requested_domain != self.domain:
            raise AuthenticationError("Domain does not match the configured API domain.")
        now = int(self._clock())
        expires_at = now + self.nonce_ttl_seconds
        nonce = secrets.token_urlsafe(24)
        message = (
            f"{self.domain} requests a wallet signature for DeFi Lending DApp.\n"
            f"Address: {wallet}\n"
            f"Chain ID: {int(chain_id)}\n"
            f"Nonce: {nonce}\n"
            f"Issued At: {datetime.fromtimestamp(now, timezone.utc).isoformat()}\n"
            f"Expiration Time: {datetime.fromtimestamp(expires_at, timezone.utc).isoformat()}"
        )
        record = _NonceRecord(
            wallet_address=wallet,
            chain_id=int(chain_id),
            domain=self.domain,
            message=message,
            expires_at=expires_at,
        )
        with self._lock:
            self._nonces = {
                key: value
                for key, value in self._nonces.items()
                if value.expires_at > now
            }
            self._nonces[nonce] = record
        return {
            "nonce": nonce,
            "message": message,
            "domain": self.domain,
            "chain_id": int(chain_id),
            "wallet_address": wallet,
            "expires_at": expires_at,
        }

    def verify_signature(
        self,
        wallet_address: str,
        chain_id: int,
        nonce: str,
        signature: str,
        domain: str | None = None,
    ) -> dict[str, object]:
        wallet = self._checksum_wallet(wallet_address)
        requested_domain = self.domain if domain is None else domain.strip()
        now = int(self._clock())
        with self._lock:
            record = self._nonces.get(nonce)
        if record is None or record.expires_at <= now:
            raise AuthenticationError("Nonce is missing, expired, or already used.")
        if (
            record.wallet_address != wallet
            or record.chain_id != int(chain_id)
            or record.domain != requested_domain
        ):
            raise AuthenticationError("Nonce challenge does not match wallet, chain, or domain.")
        if requested_domain != self.domain:
            raise AuthenticationError("Domain does not match the configured API domain.")
        if not isinstance(signature, str) or not signature.startswith("0x"):
            raise AuthenticationError("A valid EIP-191 signature is required.")
        try:
            recovered = Account.recover_message(
                encode_defunct(text=record.message), signature=signature
            )
        except (TypeError, ValueError, binascii.Error) as exc:
            raise AuthenticationError("Wallet signature is invalid.") from exc
        if self._checksum_wallet(recovered) != wallet:
            raise AuthenticationError("Wallet signature does not match the requested address.")

        with self._lock:
            current = self._nonces.get(nonce)
            if current != record:
                raise AuthenticationError("Nonce has already been used.")
            del self._nonces[nonce]
        roles = self.roles_for(wallet)
        session_id = secrets.token_urlsafe(18)
        issued_at = now
        expires_at = issued_at + self.session_ttl_seconds
        token = self._encode_session(
            {
                "sub": wallet,
                "chain_id": int(chain_id),
                "roles": sorted(role.value for role in roles),
                "sid": session_id,
                "iat": issued_at,
                "exp": expires_at,
            }
        )
        return {
            "access_token": token,
            "token_type": "bearer",
            "expires_in": self.session_ttl_seconds,
            "expires_at": expires_at,
            "wallet_address": wallet,
            "chain_id": int(chain_id),
            "roles": sorted(role.value for role in roles),
        }

    def verify_session(self, token: str) -> AccessContext:
        try:
            encoded_payload, encoded_signature = token.split(".", 1)
            payload_bytes = self._b64decode(encoded_payload)
            supplied_signature = self._b64decode(encoded_signature)
            expected_signature = hmac.new(
                self._secret, encoded_payload.encode("ascii"), hashlib.sha256
            ).digest()
            if not hmac.compare_digest(supplied_signature, expected_signature):
                raise AuthenticationError("Bearer token signature is invalid.")
            payload = json.loads(payload_bytes)
            wallet = self._checksum_wallet(payload["sub"])
            expires_at = int(payload["exp"])
            chain_id = int(payload["chain_id"])
            session_id = str(payload["sid"])
            role_names = payload["roles"]
            if expires_at <= int(self._clock()):
                raise AuthenticationError("Bearer token has expired.")
            if chain_id not in self.allowed_chain_ids or not isinstance(role_names, list):
                raise AuthenticationError("Bearer token claims are invalid.")
            roles = frozenset(Role(role_name) for role_name in role_names)
            if not roles or Role.GUEST in roles:
                raise AuthenticationError("Bearer token roles are invalid.")
            if roles != self.roles_for(wallet):
                raise AuthenticationError("Bearer token role claims are invalid.")
        except AuthenticationError:
            raise
        except (
            ValueError,
            TypeError,
            KeyError,
            json.JSONDecodeError,
            binascii.Error,
        ) as exc:
            raise AuthenticationError("Bearer token is malformed.") from exc
        return AccessContext.for_wallet(
            wallet, roles, session_id=session_id, chain_id=chain_id
        )

    def roles_for(self, wallet_address: str) -> frozenset[Role]:
        wallet = self._checksum_wallet(wallet_address).lower()
        if wallet in self._admin_wallets:
            return frozenset({Role.ADMIN})
        if wallet in self._lender_wallets:
            return frozenset({Role.LENDER})
        return frozenset({Role.BORROWER})

    def _encode_session(self, payload: Mapping[str, object]) -> str:
        payload_part = self._b64encode(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        )
        signature = hmac.new(
            self._secret, payload_part.encode("ascii"), hashlib.sha256
        ).digest()
        return f"{payload_part}.{self._b64encode(signature)}"

    @staticmethod
    def _b64encode(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")

    @staticmethod
    def _b64decode(value: str) -> bytes:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))

    @staticmethod
    def _checksum_wallet(address: str) -> str:
        if not isinstance(address, str) or not Web3.is_address(address):
            raise AuthenticationError("Invalid wallet address.")
        return Web3.to_checksum_address(address)

    @classmethod
    def _normalize_wallets(cls, wallets: Iterable[str]) -> frozenset[str]:
        return frozenset(cls._checksum_wallet(wallet).lower() for wallet in wallets)


_bearer = HTTPBearer(auto_error=False)


def get_auth_manager(request: Request) -> WalletAuthManager:
    manager = getattr(request.app.state, "auth_manager", None)
    if manager is not None:
        return manager
    try:
        manager = WalletAuthManager.from_settings()
    except AuthenticationConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    request.app.state.auth_manager = manager
    return manager


def get_current_context(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    auth_manager: WalletAuthManager = Depends(get_auth_manager),
) -> AccessContext:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="A bearer session token is required.")
    try:
        return auth_manager.verify_session(credentials.credentials)
    except AuthenticationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


def get_optional_context(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> AccessContext:
    if credentials is None:
        return AccessContext.guest()
    auth_manager = get_auth_manager(request)
    try:
        return auth_manager.verify_session(credentials.credentials)
    except AuthenticationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


def require_roles(*allowed_roles: Role) -> Callable[..., AccessContext]:
    def dependency(context: AccessContext = Depends(get_current_context)) -> AccessContext:
        if not context.roles.intersection(allowed_roles):
            raise HTTPException(status_code=403, detail="Wallet role is not permitted.")
        return context

    return dependency
