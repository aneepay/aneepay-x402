"""Tests for price conversion and PaymentRequired builders."""

from __future__ import annotations

import base64
import json
from decimal import Decimal

import pytest

from tests.conftest import build_payload, encode_signature_header
from x402_sdk import (
    AmountError,
    ConfigError,
    PaymentConfig,
    PaymentError,
    build_amount,
    build_payment_request,
    build_payment_required,
    build_requirements,
    build_resource_info,
    decode_payment_signature_header,
    encode_payment_required_header,
    encode_payment_response_header,
    parse_amount,
    to_wire,
)
from x402_sdk.schemas import SettleResponse


def test_build_amount_scales_by_decimals() -> None:
    assert build_amount("0.01", 6) == "10000"
    assert build_amount(1, 6) == "1000000"
    assert build_amount(Decimal("1.5"), 6) == "1500000"
    assert build_amount("1", 18) == "1000000000000000000"


@pytest.mark.parametrize("price", ["-1", "0.0000001", "abc", ""])
def test_build_amount_rejects_invalid_prices(price: str) -> None:
    with pytest.raises(AmountError):
        build_amount(price, 6)


def test_parse_amount_is_inverse_of_build_amount() -> None:
    assert parse_amount("10000", 6) == Decimal("0.01")


def test_build_requirements_uses_config(config: PaymentConfig) -> None:
    requirements = build_requirements(config, price="1")
    assert requirements.scheme == "exact"
    assert requirements.network == config.network
    assert requirements.amount == "1000000"
    assert requirements.asset == config.token.address
    assert requirements.pay_to == config.pay_to
    assert requirements.max_timeout_seconds == config.max_timeout_seconds
    assert requirements.extra.name == "USD Coin"
    assert requirements.extra.version == "2"


def test_build_resource_info_falls_back_to_config(config: PaymentConfig) -> None:
    resource = build_resource_info(config)
    assert resource.url == config.resource_url
    assert resource.mime_type == config.mime_type


def test_build_resource_info_requires_url(config: PaymentConfig) -> None:
    without_url = config.model_copy(update={"resource_url": None})
    with pytest.raises(ConfigError):
        build_resource_info(without_url)


def test_build_payment_required(config: PaymentConfig) -> None:
    required = build_payment_required(config, price="1", error="payment required")
    assert required.x402_version == 2
    assert required.error == "payment required"
    assert required.resource.url == config.resource_url
    assert len(required.accepts) == 1


def test_build_payment_request(config: PaymentConfig) -> None:
    requirements = build_requirements(config, price="1")
    request = build_payment_request(build_payload(requirements), requirements)
    assert request.payment_requirements.pay_to == requirements.pay_to
    assert request.payment_payload.accepted.amount == "1000000"


def test_encode_payment_required_header_roundtrip(config: PaymentConfig) -> None:
    required = build_payment_required(config, price="1")
    decoded = json.loads(base64.b64decode(encode_payment_required_header(required)))
    assert decoded == to_wire(required)


def test_decode_payment_signature_header_roundtrip(config: PaymentConfig) -> None:
    requirements = build_requirements(config, price="1")
    payload = build_payload(requirements)
    decoded = decode_payment_signature_header(encode_signature_header(payload))
    assert decoded.payload.signature == payload.payload.signature
    assert decoded.accepted.pay_to == requirements.pay_to


@pytest.mark.parametrize("header", ["not-base64!!", ""])
def test_decode_payment_signature_header_rejects_bad_base64(header: str) -> None:
    with pytest.raises(PaymentError):
        decode_payment_signature_header(header)


def test_decode_payment_signature_header_rejects_bad_schema() -> None:
    header = base64.b64encode(b'{"x402Version":2}').decode()
    with pytest.raises(PaymentError):
        decode_payment_signature_header(header)


def test_encode_payment_response_header_roundtrip() -> None:
    response = SettleResponse(success=True, transaction="0xabc", network="eip155:31337")
    decoded = json.loads(base64.b64decode(encode_payment_response_header(response)))
    assert decoded == to_wire(response)
