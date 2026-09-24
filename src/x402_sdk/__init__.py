"""AneePay merchant-side x402 SDK (exact scheme, EVM).

The SDK is self-contained and does not import from the AneePay monorepo
applications. Wire-v2 schemas are intentionally duplicated from the facilitator
(`fastapi/`) and guarded by a contract test.
"""

from __future__ import annotations

from x402_sdk.client import X402FacilitatorClient
from x402_sdk.config import PaymentConfig, TokenConfig
from x402_sdk.exceptions import AmountError, ConfigError, FacilitatorError, PaymentError, X402Error
from x402_sdk.middleware import require_payment
from x402_sdk.requirements import (
    build_amount,
    build_payment_request,
    build_payment_required,
    build_requirements,
    build_resource_info,
    decode_payment_signature_header,
    encode_payment_required_header,
    encode_payment_response_header,
    parse_amount,
)
from x402_sdk.schemas import (
    ASSET_TRANSFER_METHOD_EIP3009,
    HEADER_PAYMENT_REQUIRED,
    HEADER_PAYMENT_SIGNATURE,
    SCHEME_EXACT,
    X402_VERSION,
    PaymentPayload,
    PaymentRequired,
    PaymentRequirements,
    SettleResponse,
    VerifyResponse,
    to_wire,
)

__all__ = [
    "ASSET_TRANSFER_METHOD_EIP3009",
    "HEADER_PAYMENT_REQUIRED",
    "HEADER_PAYMENT_SIGNATURE",
    "SCHEME_EXACT",
    "X402_VERSION",
    "AmountError",
    "ConfigError",
    "FacilitatorError",
    "PaymentConfig",
    "PaymentError",
    "PaymentPayload",
    "PaymentRequired",
    "PaymentRequirements",
    "SettleResponse",
    "TokenConfig",
    "VerifyResponse",
    "X402Error",
    "X402FacilitatorClient",
    "__version__",
    "build_amount",
    "build_payment_request",
    "build_payment_required",
    "build_requirements",
    "build_resource_info",
    "decode_payment_signature_header",
    "encode_payment_required_header",
    "encode_payment_response_header",
    "parse_amount",
    "require_payment",
    "to_wire",
]

__version__ = "0.1.0"
