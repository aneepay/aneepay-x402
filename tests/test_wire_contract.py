"""Wire-v2 contract tests: pin the camelCase JSON shapes the facilitator expects.

These schemas are intentionally duplicated from the AneePay facilitator
(`fastapi/src/x402/schemas.py`, see ADR 0006); a deliberate drift must fail here.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from tests.conftest import PAY_TO, TOKEN_ADDRESS, build_payload
from x402_sdk import (
    ASSET_TRANSFER_METHOD_EIP3009,
    HEADER_PAYMENT_REQUIRED,
    HEADER_PAYMENT_SIGNATURE,
    SCHEME_EXACT,
    X402_VERSION,
    SettleResponse,
    VerifyResponse,
    build_requirements,
    to_wire,
)
from x402_sdk.schemas import PaymentPayload, PaymentRequired, PaymentRequirements, ResourceInfo


def test_protocol_constants() -> None:
    assert X402_VERSION == 2
    assert SCHEME_EXACT == "exact"
    assert ASSET_TRANSFER_METHOD_EIP3009 == "eip3009"
    assert HEADER_PAYMENT_REQUIRED == "PAYMENT-REQUIRED"
    assert HEADER_PAYMENT_SIGNATURE == "PAYMENT-SIGNATURE"


def test_payment_requirements_wire_shape(config) -> None:
    requirements = build_requirements(config, price="1")

    assert to_wire(requirements) == {
        "scheme": "exact",
        "network": "eip155:31337",
        "amount": "1000000",
        "asset": TOKEN_ADDRESS,
        "payTo": PAY_TO,
        "maxTimeoutSeconds": 60,
        "extra": {"name": "USD Coin", "version": "2", "assetTransferMethod": "eip3009"},
    }


def test_payment_required_wire_shape(config) -> None:
    required = PaymentRequired(
        error="payment required",
        resource=ResourceInfo(url="http://merchant.test/api/resource", description="d", mime_type="application/json"),
        accepts=[build_requirements(config, price="1")],
    )

    wire = to_wire(required)
    assert wire["x402Version"] == 2
    assert wire["error"] == "payment required"
    assert wire["resource"] == {
        "url": "http://merchant.test/api/resource",
        "description": "d",
        "mimeType": "application/json",
    }
    assert set(wire) == {"x402Version", "error", "resource", "accepts", "extensions"}


def test_payment_payload_wire_shape(config) -> None:
    requirements = build_requirements(config, price="1")
    payload = build_payload(requirements)

    wire = to_wire(payload)
    assert set(wire) == {"x402Version", "accepted", "payload", "extensions"}
    assert wire["x402Version"] == 2
    assert wire["payload"]["signature"].startswith("0x")
    authorization = wire["payload"]["authorization"]
    assert set(authorization) == {"from", "to", "value", "validAfter", "validBefore", "nonce"}
    assert authorization["to"] == PAY_TO
    assert authorization["value"] == "1000000"


def test_verify_response_wire_shape() -> None:
    assert to_wire(VerifyResponse(is_valid=False, invalid_reason="invalid_scheme")) == {
        "isValid": False,
        "invalidReason": "invalid_scheme",
        "extensions": {},
        "extra": {},
    }


def test_settle_response_wire_shape() -> None:
    response = SettleResponse(success=True, transaction="0xabc", network="eip155:31337", amount="1000000")

    assert to_wire(response) == {
        "success": True,
        "transaction": "0xabc",
        "network": "eip155:31337",
        "amount": "1000000",
        "extensions": {},
    }


def test_payment_requirements_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        PaymentRequirements.model_validate(
            {
                "scheme": "exact",
                "network": "eip155:31337",
                "amount": "1000000",
                "asset": TOKEN_ADDRESS,
                "payTo": PAY_TO,
                "maxTimeoutSeconds": 60,
                "unexpected": True,
            }
        )


def test_payment_payload_model_validate_from_wire(config) -> None:
    requirements = build_requirements(config, price="1")
    payload = build_payload(requirements)

    restored = PaymentPayload.model_validate(to_wire(payload))

    assert restored == payload
