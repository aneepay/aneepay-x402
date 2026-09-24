"""Shared fixtures and builders for SDK unit tests."""

from __future__ import annotations

import base64
import json

import pytest

from x402_sdk import (
    PaymentConfig,
    PaymentPayload,
    PaymentRequirements,
    TokenConfig,
    to_wire,
)
from x402_sdk.schemas import Eip3009Authorization, ExactEvmPayload

FACILITATOR_URL = "http://facilitator.test"
ACCOUNT_ID = "00000000-0000-4000-8000-000000000001"
NETWORK = "eip155:31337"
PAY_TO = "0x" + "ab" * 20
TOKEN_ADDRESS = "0x" + "cd" * 20
PAYER = "0x" + "11" * 20
NONCE = "0x" + "22" * 32
SIGNATURE = "0x" + "33" * 65
AMOUNT = "1000000"


@pytest.fixture
def config() -> PaymentConfig:
    """A fully populated merchant config for tests."""
    return PaymentConfig(
        facilitator_url=FACILITATOR_URL,
        account_id=ACCOUNT_ID,
        network=NETWORK,
        pay_to=PAY_TO,
        token=TokenConfig(address=TOKEN_ADDRESS, decimals=6, name="USD Coin", version="2"),
        resource_url="http://merchant.test/api/resource",
    )


def build_payload(
    requirements: PaymentRequirements,
    *,
    to: str | None = None,
    value: str | None = None,
) -> PaymentPayload:
    """Build a valid-looking client payload matching ``requirements``."""
    authorization = Eip3009Authorization(
        from_=PAYER,
        to=to if to is not None else requirements.pay_to,
        value=value if value is not None else requirements.amount,
        valid_after="0",
        valid_before="99999999999",
        nonce=NONCE,
    )
    return PaymentPayload(
        accepted=requirements,
        payload=ExactEvmPayload(signature=SIGNATURE, authorization=authorization),
    )


def encode_signature_header(payload: PaymentPayload) -> str:
    """Base64-encode a payload as the ``PAYMENT-SIGNATURE`` header value."""
    return base64.b64encode(json.dumps(to_wire(payload), separators=(",", ":")).encode()).decode()
