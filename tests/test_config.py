"""Tests for merchant configuration models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from x402_sdk import PaymentConfig, TokenConfig

ACCOUNT_ID = "00000000-0000-4000-8000-000000000001"
PAY_TO = "0x" + "ab" * 20
TOKEN = "0x" + "cd" * 20


def build_config(**overrides: object) -> PaymentConfig:
    values: dict[str, object] = {
        "facilitator_url": "http://facilitator.test",
        "account_id": ACCOUNT_ID,
        "network": "eip155:31337",
        "pay_to": PAY_TO,
        "token": TokenConfig(address=TOKEN, name="USD Coin"),
    }
    values.update(overrides)
    return PaymentConfig(**values)


def test_config_fixture_is_valid(config: PaymentConfig) -> None:
    assert config.network == "eip155:31337"
    assert config.token.decimals == 6
    assert str(config.account_id) == ACCOUNT_ID


@pytest.mark.parametrize(
    ("facilitator_url", "expected"),
    [
        ("http://facilitator.test", "http://facilitator.test/x402/verify"),
        ("http://facilitator.test/", "http://facilitator.test/x402/verify"),
    ],
)
def test_verify_url_normalizes_trailing_slash(facilitator_url: str, expected: str) -> None:
    assert build_config(facilitator_url=facilitator_url).verify_url == expected


def test_settle_and_supported_urls() -> None:
    config = build_config()
    assert config.settle_url == "http://facilitator.test/x402/settle"
    assert config.supported_url == "http://facilitator.test/x402/supported"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("pay_to", "0x123"),
        ("network", "31337"),
        ("network", "eip155:abc"),
        ("facilitator_url", ""),
    ],
)
def test_invalid_fields_rejected(field: str, value: str) -> None:
    with pytest.raises(ValidationError):
        build_config(**{field: value})


def test_unknown_field_rejected() -> None:
    with pytest.raises(ValidationError):
        build_config(unknown=True)


def test_token_decimals_bounds() -> None:
    TokenConfig(address=TOKEN, name="X", decimals=0)
    TokenConfig(address=TOKEN, name="X", decimals=36)
    with pytest.raises(ValidationError):
        TokenConfig(address=TOKEN, name="X", decimals=37)
