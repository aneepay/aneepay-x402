"""x402 wire-v2 schemas (vendored duplicate).

This module intentionally duplicates the public wire contract served by the
AneePay facilitator at aneepay.com. The SDK must stay self-contained, so the
contract is pinned by a unit test instead of a shared package — see
``tests/test_wire_contract.py``.

Pin: x402 specification v2.
Python fields are snake_case; the wire representation is camelCase. Wire names
are declared as ``serialization_alias``/``validation_alias`` (never ``alias``)
so that type checkers keep seeing the python field names in ``__init__``:
``PaymentRequirements(pay_to=...)`` is the python spelling, ``"payTo"`` is the
wire spelling, and both are accepted on input. Serialize with :func:`to_wire`.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

X402_VERSION = 2
SCHEME_EXACT = "exact"
ASSET_TRANSFER_METHOD_EIP3009 = "eip3009"
ASSET_TRANSFER_METHOD_PERMIT2 = "permit2"

X402Version = Literal[2]

HEADER_PAYMENT_REQUIRED = "PAYMENT-REQUIRED"
HEADER_PAYMENT_SIGNATURE = "PAYMENT-SIGNATURE"
HEADER_PAYMENT_RESPONSE = "PAYMENT-RESPONSE"


class _WireModel(BaseModel):
    """Base for wire objects: camelCase aliases, reject unknown fields."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class ResourceInfo(_WireModel):
    """Information about the protected resource (``PaymentRequired.resource``).

    Attributes:
        url: URL of the protected resource.
        description: Human-readable resource description.
        mime_type: MIME type of the expected response.
        service_name: Service name (printable ASCII, up to 32 chars).
        tags: Topic tags (up to 5, each up to 32 chars).
        icon_url: Absolute URL of the service icon (up to 2048 chars).
    """

    url: str
    description: str | None = None
    mime_type: str | None = Field(
        default=None,
        serialization_alias="mimeType",
        validation_alias="mimeType",
    )
    service_name: str | None = Field(
        default=None,
        serialization_alias="serviceName",
        validation_alias="serviceName",
        max_length=32,
    )
    tags: list[str] | None = Field(default=None, max_length=5)
    icon_url: str | None = Field(
        default=None,
        serialization_alias="iconUrl",
        validation_alias="iconUrl",
        max_length=2048,
    )


class Extension(_WireModel):
    """Value of an ``extensions`` entry (identifier -> {info, schema}).

    Attributes:
        info: Extension data provided by the server.
        schema_: JSON Schema describing ``info``.
    """

    info: dict[str, Any]
    schema_: dict[str, Any] = Field(..., serialization_alias="schema", validation_alias="schema")


class PaymentRequirementsExtra(_WireModel):
    """Scheme-specific keys of ``PaymentRequirements.extra`` (eip3009).

    Attributes:
        name: EIP-712 token domain name (required for eip3009).
        version: EIP-712 token domain version (required for eip3009).
        asset_transfer_method: Asset transfer method, defaults to ``eip3009``.
    """

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    name: str | None = None
    version: str | None = None
    asset_transfer_method: str = Field(
        default=ASSET_TRANSFER_METHOD_EIP3009,
        serialization_alias="assetTransferMethod",
        validation_alias="assetTransferMethod",
    )


class PaymentRequirements(_WireModel):
    """Payment requirements (``PaymentRequired.accepts[]``, ``PaymentPayload.accepted``).

    Attributes:
        scheme: Scheme identifier (``exact`` for us).
        network: Network in CAIP-2 form (``eip155:<chainId>``).
        amount: Amount in token atomic units (string).
        asset: Token contract address.
        pay_to: Recipient address (per-merchant gateway clone).
        max_timeout_seconds: Maximum time allowed for payment.
        extra: Additional scheme-specific data (name/version/...).
    """

    scheme: str
    network: str
    amount: str
    asset: str
    pay_to: str = Field(..., serialization_alias="payTo", validation_alias="payTo")
    max_timeout_seconds: int = Field(
        ...,
        serialization_alias="maxTimeoutSeconds",
        validation_alias="maxTimeoutSeconds",
    )
    extra: PaymentRequirementsExtra = Field(default_factory=PaymentRequirementsExtra)


class PaymentRequired(_WireModel):
    """Body of ``402`` — payment options accepted by the resource server.

    Attributes:
        x402_version: Protocol version (always 2).
        error: Human-readable reason for requiring payment.
        resource: Information about the protected resource.
        accepts: List of accepted payment options.
        extensions: Protocol extension data.
    """

    x402_version: X402Version = Field(
        default=X402_VERSION,
        serialization_alias="x402Version",
        validation_alias="x402Version",
    )
    error: str | None = None
    resource: ResourceInfo
    accepts: list[PaymentRequirements]
    extensions: dict[str, Extension] = Field(default_factory=dict)


class Eip3009Authorization(_WireModel):
    """EIP-3009 ``TransferWithAuthorization`` parameters.

    Attributes:
        from_: Payer (client wallet).
        to: Recipient (gateway clone address).
        value: Amount in atomic units (string).
        valid_after: Unix time when the authorization becomes valid.
        valid_before: Unix time when the authorization expires.
        nonce: 32-byte replay-protection nonce (hex string).
    """

    from_: str = Field(..., serialization_alias="from", validation_alias="from")
    to: str
    value: str
    valid_after: str = Field(..., serialization_alias="validAfter", validation_alias="validAfter")
    valid_before: str = Field(..., serialization_alias="validBefore", validation_alias="validBefore")
    nonce: str


class ExactEvmPayload(_WireModel):
    """Scheme-specific ``payload`` for exact/EIP-3009.

    Attributes:
        signature: 65-byte EIP-712 ``transferWithAuthorization`` signature.
        authorization: Authorization parameters.
    """

    signature: str
    authorization: Eip3009Authorization


class PaymentPayload(_WireModel):
    """Payment sent by the client (``PAYMENT-SIGNATURE``).

    Attributes:
        x402_version: Protocol version (always 2).
        resource: Resource information (echo of ``PaymentRequired``).
        accepted: Payment option chosen by the client.
        payload: Scheme-specific signature data (EIP-3009 for us).
        extensions: Protocol extension data (echo of the server).
    """

    x402_version: X402Version = Field(
        default=X402_VERSION,
        serialization_alias="x402Version",
        validation_alias="x402Version",
    )
    resource: ResourceInfo | None = None
    accepted: PaymentRequirements
    payload: ExactEvmPayload
    extensions: dict[str, Extension] = Field(default_factory=dict)


class PaymentRequest(_WireModel):
    """Body of ``POST /x402/verify`` and ``POST /x402/settle`` (structurally identical).

    Attributes:
        x402_version: Protocol version (always 2).
        payment_payload: Payment from the client.
        payment_requirements: Requirements the payment is checked against.
    """

    x402_version: X402Version = Field(
        default=X402_VERSION,
        serialization_alias="x402Version",
        validation_alias="x402Version",
    )
    payment_payload: PaymentPayload = Field(
        ...,
        serialization_alias="paymentPayload",
        validation_alias="paymentPayload",
    )
    payment_requirements: PaymentRequirements = Field(
        ...,
        serialization_alias="paymentRequirements",
        validation_alias="paymentRequirements",
    )


class VerifyRequest(PaymentRequest):
    """``POST /x402/verify`` request."""


class SettleRequest(PaymentRequest):
    """``POST /x402/settle`` request."""


class VerifyResponse(_WireModel):
    """``/x402/verify`` response.

    Attributes:
        is_valid: Whether the payment authorization is valid.
        invalid_reason: Reason for invalidity (``X402ErrorCode`` value).
        payer: Payer wallet address.
        extensions: Protocol extension data.
        extra: Additional scheme-specific data.
    """

    is_valid: bool = Field(..., serialization_alias="isValid", validation_alias="isValid")
    invalid_reason: str | None = Field(
        default=None,
        serialization_alias="invalidReason",
        validation_alias="invalidReason",
    )
    payer: str | None = None
    extensions: dict[str, Extension] = Field(default_factory=dict)
    extra: dict[str, Any] = Field(default_factory=dict)


class SettleResponse(_WireModel):
    """``/x402/settle`` response.

    Attributes:
        success: Whether settlement succeeded.
        error_reason: Error reason (``X402ErrorCode`` value).
        payer: Payer wallet address.
        transaction: Transaction hash (empty when not broadcast; non-empty when pending).
        network: Network in CAIP-2 form.
        amount: Actually settled amount in atomic units.
        extensions: Protocol extension data.
    """

    success: bool
    error_reason: str | None = Field(
        default=None,
        serialization_alias="errorReason",
        validation_alias="errorReason",
    )
    payer: str | None = None
    transaction: str
    network: str
    amount: str | None = None
    extensions: dict[str, Extension] = Field(default_factory=dict)


class SupportedKind(_WireModel):
    """A supported scheme/network combination (``SupportedResponse.kinds[]``).

    Attributes:
        x402_version: Protocol version (always 2).
        scheme: Scheme identifier (``exact``).
        network: Network in CAIP-2 form.
        extra: Additional scheme configuration.
    """

    x402_version: X402Version = Field(
        default=X402_VERSION,
        serialization_alias="x402Version",
        validation_alias="x402Version",
    )
    scheme: str
    network: str
    extra: dict[str, Any] = Field(default_factory=dict)


class SupportedResponse(_WireModel):
    """``GET /x402/supported`` response.

    Attributes:
        kinds: Supported scheme/network combinations.
        extensions: Implemented extension identifiers.
        signers: Mapping of CAIP-2 patterns (e.g. ``eip155:*``) to signer addresses.
    """

    kinds: list[SupportedKind]
    extensions: list[str] = Field(default_factory=list)
    signers: dict[str, list[str]] = Field(default_factory=dict)


def to_wire(model: BaseModel) -> dict[str, Any]:
    """Serialize a wire model to a camelCase, JSON-ready dict.

    Args:
        model: Any pydantic model with camelCase wire names.

    Returns:
        Dict with camelCase keys and ``None`` fields dropped.
    """
    return model.model_dump(by_alias=True, exclude_none=True)
