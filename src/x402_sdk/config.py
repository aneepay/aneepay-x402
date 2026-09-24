"""Merchant-side SDK configuration.

The config describes *what* to charge (price per resource) and *where* the
facilitator is; it never contains private keys. The recipient is the
per-merchant gateway clone address (``pay_to``) — the SDK performs no on-chain
or keccak arithmetic.
"""

from __future__ import annotations

from uuid import UUID  # noqa: TC003 (pydantic needs the runtime type)

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["PaymentConfig", "TokenConfig"]

_ADDRESS_PATTERN = r"^0x[a-fA-F0-9]{40}$"
_NETWORK_PATTERN = r"^eip155:\d+$"


class TokenConfig(BaseModel):
    """ERC-20 token metadata needed to build payment requirements.

    Attributes:
        address: Token contract address.
        decimals: Token decimals (USDC/USDT 6, DAI 18).
        name: EIP-712 domain name advertised to clients (e.g. ``USD Coin``).
        version: EIP-712 domain version advertised to clients.
    """

    model_config = ConfigDict(extra="forbid")

    address: str = Field(..., pattern=_ADDRESS_PATTERN)
    decimals: int = Field(default=6, ge=0, le=36)
    name: str = Field(..., min_length=1)
    version: str = Field(default="2", min_length=1)


class PaymentConfig(BaseModel):
    """Configuration of an AneePay x402 resource server.

    Attributes:
        facilitator_url: Base URL of the AneePay facilitator (e.g. ``https://api.aneepay.com``).
        account_id: AneePay account id (merchant) used for the ``X-Account-Id`` header.
        network: Network in CAIP-2 form (``eip155:<chainId>``).
        pay_to: Per-merchant gateway clone address (payment recipient).
        token: Token metadata.
        resource_url: Default URL of the protected resource.
        description: Default human-readable resource description.
        mime_type: Default MIME type of the expected response.
        max_timeout_seconds: Default maximum time allowed for payment.
        verify_path: Facilitator verify endpoint path.
        settle_path: Facilitator settle endpoint path.
        request_timeout_seconds: HTTP timeout for facilitator calls.
    """

    model_config = ConfigDict(extra="forbid")

    facilitator_url: str = Field(..., min_length=1)
    account_id: UUID
    network: str = Field(..., pattern=_NETWORK_PATTERN)
    pay_to: str = Field(..., pattern=_ADDRESS_PATTERN)
    token: TokenConfig
    resource_url: str | None = None
    description: str | None = None
    mime_type: str = "application/json"
    max_timeout_seconds: int = Field(default=60, ge=1)
    supported_path: str = "/x402/supported"
    verify_path: str = "/x402/verify"
    settle_path: str = "/x402/settle"
    request_timeout_seconds: float = Field(default=10.0, gt=0)

    @property
    def supported_url(self) -> str:
        """Absolute facilitator ``/x402/supported`` URL."""
        return self.facilitator_url.rstrip("/") + self.supported_path

    @property
    def verify_url(self) -> str:
        """Absolute facilitator ``/x402/verify`` URL."""
        return self.facilitator_url.rstrip("/") + self.verify_path

    @property
    def settle_url(self) -> str:
        """Absolute facilitator ``/x402/settle`` URL."""
        return self.facilitator_url.rstrip("/") + self.settle_path
