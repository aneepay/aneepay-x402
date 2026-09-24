"""Build x402 payment requirements and PaymentRequired responses.

Prices are expressed as human money (``"0.01"``), while the wire uses atomic
token units. :func:`build_amount` is the single conversion point and rejects
prices that cannot be represented exactly with the token decimals.
"""

from __future__ import annotations

import base64
import binascii
import json
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from x402_sdk.exceptions import AmountError, ConfigError, PaymentError
from x402_sdk.schemas import (
    HEADER_PAYMENT_REQUIRED,
    HEADER_PAYMENT_SIGNATURE,
    PaymentPayload,
    PaymentRequest,
    PaymentRequired,
    PaymentRequirements,
    ResourceInfo,
    to_wire,
)

if TYPE_CHECKING:
    from x402_sdk.config import PaymentConfig
    from x402_sdk.schemas import SettleResponse

__all__ = [
    "HEADER_PAYMENT_REQUIRED",
    "HEADER_PAYMENT_SIGNATURE",
    "build_amount",
    "build_payment_request",
    "build_payment_required",
    "build_requirements",
    "build_resource_info",
    "decode_payment_signature_header",
    "encode_payment_required_header",
    "encode_payment_response_header",
    "parse_amount",
]

_MONEY = Decimal | int | str


def build_amount(price: _MONEY, decimals: int) -> str:
    """Convert a human price into the token's smallest atomic unit.

    Args:
        price: Amount of money (e.g. ``"0.01"``, ``Decimal("1")``, ``5``).
        decimals: Token decimals used for scaling.

    Returns:
        Atomic amount as a decimal string (wire ``amount``).

    Raises:
        AmountError: If ``price`` is negative, non-numeric, or has more
            precision than the token supports.
    """
    try:
        value = Decimal(str(price))
    except (InvalidOperation, ValueError) as exc:
        raise AmountError(f"price {price!r} is not a valid decimal number") from exc
    if value < 0:
        raise AmountError(f"price {price!r} must not be negative")
    scaled = value.scaleb(decimals)
    integral = scaled.to_integral_value()
    if scaled != integral:
        raise AmountError(f"price {price!r} has more precision than {decimals} decimals allow")
    return str(int(integral))


def parse_amount(amount: str, decimals: int) -> Decimal:
    """Inverse of :func:`build_amount`: atomic string -> human price.

    Args:
        amount: Atomic amount as a string.
        decimals: Token decimals.

    Returns:
        The amount as ``Decimal`` money.

    Raises:
        AmountError: If ``amount`` is not a valid integer string.
    """
    try:
        value = Decimal(amount)
    except (InvalidOperation, ValueError) as exc:
        raise AmountError(f"amount {amount!r} is not a valid decimal number") from exc
    return value.scaleb(-decimals)


def build_requirements(
    config: PaymentConfig,
    *,
    price: _MONEY,
    max_timeout_seconds: int | None = None,
) -> PaymentRequirements:
    """Build wire payment requirements for one resource from the config.

    Args:
        config: Merchant SDK configuration.
        price: Human price for the resource.
        max_timeout_seconds: Per-offer override of the config default.

    Returns:
        A wire-v2 :class:`~x402_sdk.schemas.PaymentRequirements`.
    """
    return PaymentRequirements(
        scheme="exact",
        network=config.network,
        amount=build_amount(price, config.token.decimals),
        asset=config.token.address,
        pay_to=config.pay_to,
        max_timeout_seconds=max_timeout_seconds if max_timeout_seconds is not None else config.max_timeout_seconds,
        extra={
            "name": config.token.name,
            "version": config.token.version,
        },
    )


def build_resource_info(
    config: PaymentConfig,
    *,
    resource_url: str | None = None,
    description: str | None = None,
    mime_type: str | None = None,
) -> ResourceInfo:
    """Build the ``PaymentRequired.resource`` descriptor from the config.

    Args:
        config: Merchant SDK configuration.
        resource_url: Resource URL; falls back to ``config.resource_url``.
        description: Resource description; falls back to ``config.description``.
        mime_type: Resource MIME type; falls back to ``config.mime_type``.

    Returns:
        A wire-v2 :class:`~x402_sdk.schemas.ResourceInfo`.

    Raises:
        ConfigError: If no resource URL is available.
    """
    resolved_url = resource_url if resource_url is not None else config.resource_url
    if not resolved_url:
        raise ConfigError("resource_url is required to build PaymentRequired")
    return ResourceInfo(
        url=resolved_url,
        description=description if description is not None else config.description,
        mime_type=mime_type if mime_type is not None else config.mime_type,
    )


def build_payment_required(
    config: PaymentConfig,
    *,
    price: _MONEY,
    resource: ResourceInfo | None = None,
    error: str | None = None,
    max_timeout_seconds: int | None = None,
) -> PaymentRequired:
    """Build the wire ``402`` body advertised to clients.

    Args:
        config: Merchant SDK configuration.
        price: Human price for the resource.
        resource: Resource descriptor; defaults to :func:`build_resource_info`.
        error: Human-readable reason for requiring payment.
        max_timeout_seconds: Per-offer override of the config default.

    Returns:
        A wire-v2 :class:`~x402_sdk.schemas.PaymentRequired`.
    """
    return PaymentRequired(
        error=error,
        resource=resource if resource is not None else build_resource_info(config),
        accepts=[build_requirements(config, price=price, max_timeout_seconds=max_timeout_seconds)],
    )


def build_payment_request(
    payment_payload: PaymentPayload,
    payment_requirements: PaymentRequirements,
) -> PaymentRequest:
    """Combine a client payload with server requirements into a facilitator request.

    Args:
        payment_payload: Payment decoded from the ``PAYMENT-SIGNATURE`` header.
        payment_requirements: Requirements the payment belongs to.

    Returns:
        Wire-v2 request body for ``/x402/verify`` and ``/x402/settle``.
    """
    return PaymentRequest(payment_payload=payment_payload, payment_requirements=payment_requirements)


def encode_payment_required_header(required: PaymentRequired) -> str:
    """Base64-encode a :class:`PaymentRequired` for the ``PAYMENT-REQUIRED`` header.

    Args:
        required: The 402 body to advertise.

    Returns:
        Base64 (standard, ASCII) string of the compact JSON body.
    """
    body = json.dumps(to_wire(required), separators=(",", ":")).encode()
    return base64.b64encode(body).decode()


def decode_payment_signature_header(value: str) -> PaymentPayload:
    """Decode the ``PAYMENT-SIGNATURE`` header into a :class:`PaymentPayload`.

    Args:
        value: Base64-encoded JSON payment payload sent by the client.

    Returns:
        The validated payment payload.

    Raises:
        PaymentError: If the header is not valid base64/JSON or fails validation.
    """
    try:
        raw: Any = json.loads(base64.b64decode(value, validate=True))
    except (binascii.Error, ValueError) as exc:
        raise PaymentError("PAYMENT-SIGNATURE header is not valid base64-encoded JSON") from exc
    try:
        return PaymentPayload.model_validate(raw)
    except ValidationError as exc:
        raise PaymentError("PAYMENT-SIGNATURE header does not match the x402 v2 payload schema") from exc


def encode_payment_response_header(response: SettleResponse) -> str:
    """Base64-encode a settlement response for the ``PAYMENT-RESPONSE`` header.

    Args:
        response: The settlement result returned by the facilitator.

    Returns:
        Base64 (standard, ASCII) string of the compact JSON body.
    """
    body = json.dumps(to_wire(response), separators=(",", ":")).encode()
    return base64.b64encode(body).decode()
