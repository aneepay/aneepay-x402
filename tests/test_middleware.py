"""Unit tests for :func:`x402_sdk.middleware.require_payment`."""

from __future__ import annotations

import base64
import json
from typing import Any

import pytest
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response

from tests.conftest import PAY_TO, build_payload, encode_signature_header
from x402_sdk import (
    ConfigError,
    FacilitatorError,
    PaymentConfig,
    build_payment_required,
    build_requirements,
)
from x402_sdk.middleware import require_payment
from x402_sdk.schemas import (
    HEADER_PAYMENT_REQUIRED,
    HEADER_PAYMENT_RESPONSE,
    HEADER_PAYMENT_SIGNATURE,
    PaymentRequest,
    PaymentRequired,
    SettleResponse,
    VerifyResponse,
)


class FakeFacilitator:
    """In-memory stand-in for :class:`X402FacilitatorClient`."""

    def __init__(
        self,
        *,
        verify_result: VerifyResponse | None = None,
        settle_result: SettleResponse | None = None,
        verify_error: Exception | None = None,
    ) -> None:
        self.verify_result = verify_result or VerifyResponse(is_valid=True, payer="0x" + "11" * 20)
        self.settle_result = settle_result or SettleResponse(
            success=True,
            transaction="0xabc",
            network="eip155:31337",
        )
        self.verify_error = verify_error
        self.verify_calls: list[PaymentRequest] = []
        self.settle_calls: list[PaymentRequest] = []

    async def verify(self, request: PaymentRequest) -> VerifyResponse:
        self.verify_calls.append(request)
        if self.verify_error is not None:
            raise self.verify_error
        return self.verify_result

    async def settle(self, request: PaymentRequest) -> SettleResponse:
        self.settle_calls.append(request)
        return self.settle_result


def make_request(signature: str | None = None) -> Request:
    headers = []
    if signature is not None:
        headers.append((HEADER_PAYMENT_SIGNATURE.lower().encode(), signature.encode()))
    scope: dict[str, Any] = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/api/resource",
        "raw_path": b"/api/resource",
        "query_string": b"",
        "headers": headers,
        "server": ("merchant.test", 80),
        "client": ("client.test", 12345),
    }
    return Request(scope)


async def call_next_ok(_request: Request) -> Response:
    return PlainTextResponse("paid content")


async def call_next_error(_request: Request) -> Response:
    return PlainTextResponse("nope", status_code=404)


def decode(payload: str) -> dict[str, Any]:
    return json.loads(base64.b64decode(payload))


def build_middleware(config: PaymentConfig, facilitator: FakeFacilitator):
    payment_required = build_payment_required(config, price="1")
    return require_payment(config, payment_required, client=facilitator)


async def test_missing_signature_returns_402_with_header(config: PaymentConfig) -> None:
    facilitator = FakeFacilitator()
    middleware = build_middleware(config, facilitator)

    response = await middleware(make_request(), call_next_ok)

    assert response.status_code == 402
    advertised = decode(response.headers[HEADER_PAYMENT_REQUIRED])
    assert advertised["x402Version"] == 2
    assert advertised["accepts"][0]["amount"] == "1000000"
    assert advertised["accepts"][0]["payTo"] == PAY_TO
    assert facilitator.verify_calls == []


async def test_valid_payment_runs_resource_and_settles(config: PaymentConfig) -> None:
    requirements = build_requirements(config, price="1")
    facilitator = FakeFacilitator()
    middleware = build_middleware(config, facilitator)

    response = await middleware(make_request(encode_signature_header(build_payload(requirements))), call_next_ok)

    assert response.status_code == 200
    assert response.body == b"paid content"
    assert len(facilitator.verify_calls) == 1
    assert len(facilitator.settle_calls) == 1
    settled = decode(response.headers[HEADER_PAYMENT_RESPONSE])
    assert settled["success"] is True
    assert settled["transaction"] == "0xabc"


async def test_malformed_signature_returns_402(config: PaymentConfig) -> None:
    facilitator = FakeFacilitator()
    middleware = build_middleware(config, facilitator)

    response = await middleware(make_request("not-base64!!"), call_next_ok)

    assert response.status_code == 402
    assert facilitator.verify_calls == []


async def test_invalid_verification_returns_402(config: PaymentConfig) -> None:
    requirements = build_requirements(config, price="1")
    facilitator = FakeFacilitator(
        verify_result=VerifyResponse(is_valid=False, invalid_reason="invalid_exact_evm_payload_signature")
    )
    middleware = build_middleware(config, facilitator)

    response = await middleware(make_request(encode_signature_header(build_payload(requirements))), call_next_ok)

    assert response.status_code == 402
    assert decode(response.headers[HEADER_PAYMENT_REQUIRED])["error"] == "invalid_exact_evm_payload_signature"
    assert facilitator.settle_calls == []


async def test_recipient_mismatch_returns_402_without_verify(config: PaymentConfig) -> None:
    requirements = build_requirements(config, price="1")
    facilitator = FakeFacilitator()
    middleware = build_middleware(config, facilitator)
    payload = build_payload(requirements, to="0x" + "99" * 20)

    response = await middleware(make_request(encode_signature_header(payload)), call_next_ok)

    assert response.status_code == 402
    assert facilitator.verify_calls == []


async def test_value_mismatch_returns_402_without_verify(config: PaymentConfig) -> None:
    requirements = build_requirements(config, price="1")
    facilitator = FakeFacilitator()
    middleware = build_middleware(config, facilitator)
    payload = build_payload(requirements, value="1")

    response = await middleware(make_request(encode_signature_header(payload)), call_next_ok)

    assert response.status_code == 402
    assert facilitator.verify_calls == []


async def test_downstream_error_skips_settlement(config: PaymentConfig) -> None:
    requirements = build_requirements(config, price="1")
    facilitator = FakeFacilitator()
    middleware = build_middleware(config, facilitator)

    response = await middleware(make_request(encode_signature_header(build_payload(requirements))), call_next_error)

    assert response.status_code == 404
    assert len(facilitator.verify_calls) == 1
    assert facilitator.settle_calls == []
    assert HEADER_PAYMENT_RESPONSE not in response.headers


async def test_settlement_failure_returns_402(config: PaymentConfig) -> None:
    requirements = build_requirements(config, price="1")
    facilitator = FakeFacilitator(
        settle_result=SettleResponse(
            success=False,
            error_reason="unexpected_settle_error",
            transaction="",
            network="eip155:31337",
        )
    )
    middleware = build_middleware(config, facilitator)

    response = await middleware(make_request(encode_signature_header(build_payload(requirements))), call_next_ok)

    assert response.status_code == 402
    assert decode(response.headers[HEADER_PAYMENT_REQUIRED])["error"] == "unexpected_settle_error"


async def test_facilitator_error_returns_402(config: PaymentConfig) -> None:
    requirements = build_requirements(config, price="1")
    facilitator = FakeFacilitator(verify_error=FacilitatorError("facilitator down"))
    middleware = build_middleware(config, facilitator)

    response = await middleware(make_request(encode_signature_header(build_payload(requirements))), call_next_ok)

    assert response.status_code == 402
    assert "facilitator down" in decode(response.headers[HEADER_PAYMENT_REQUIRED])["error"]


def test_empty_accepts_raises_config_error(config: PaymentConfig) -> None:
    empty = PaymentRequired(error="nope", resource=build_payment_required(config, price="1").resource, accepts=[])

    with pytest.raises(ConfigError):
        require_payment(config, empty, client=FakeFacilitator())
