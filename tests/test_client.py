"""Tests for the facilitator HTTP client (httpx MockTransport, no network)."""

from __future__ import annotations

import json

import httpx
import pytest

from tests.conftest import ACCOUNT_ID, build_payload
from x402_sdk import (
    FacilitatorError,
    PaymentConfig,
    X402FacilitatorClient,
    build_payment_request,
    build_requirements,
)
from x402_sdk.schemas import SettleResponse, SupportedResponse, VerifyResponse


def build_client(config: PaymentConfig, handler: httpx.MockTransport) -> X402FacilitatorClient:
    return X402FacilitatorClient(config, client=httpx.AsyncClient(transport=handler))


async def test_supported_returns_parsed_response(config: PaymentConfig) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/x402/supported"
        return httpx.Response(200, json={"kinds": [], "extensions": [], "signers": {}})

    client = build_client(config, httpx.MockTransport(handler))
    result = await client.supported()
    assert isinstance(result, SupportedResponse)
    await client.aclose()


async def test_verify_posts_wire_request(config: PaymentConfig) -> None:
    requirements = build_requirements(config, price="1")
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"isValid": True, "payer": "0x" + "11" * 20})

    client = build_client(config, httpx.MockTransport(handler))
    result = await client.verify(build_payment_request(build_payload(requirements), requirements))
    assert isinstance(result, VerifyResponse)
    assert result.is_valid is True
    body = seen["body"]
    assert isinstance(body, dict)
    assert body["x402Version"] == 2
    assert set(body) == {"x402Version", "paymentPayload", "paymentRequirements"}
    assert body["paymentRequirements"]["amount"] == "1000000"
    await client.aclose()


async def test_settle_sends_account_header(config: PaymentConfig) -> None:
    requirements = build_requirements(config, price="1")
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["account"] = request.headers["X-Account-Id"]
        return httpx.Response(200, json={"success": True, "transaction": "0xabc", "network": "eip155:31337"})

    client = build_client(config, httpx.MockTransport(handler))
    result = await client.settle(build_payment_request(build_payload(requirements), requirements))
    assert isinstance(result, SettleResponse)
    assert result.transaction == "0xabc"
    assert seen["account"] == ACCOUNT_ID
    await client.aclose()


async def test_http_error_raises_facilitator_error(config: PaymentConfig) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text="bad request")

    client = build_client(config, httpx.MockTransport(handler))
    with pytest.raises(FacilitatorError):
        await client.supported()


async def test_transport_error_raises_facilitator_error(config: PaymentConfig) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    client = build_client(config, httpx.MockTransport(handler))
    with pytest.raises(FacilitatorError):
        await client.supported()


async def test_context_manager_closes_owned_client(config: PaymentConfig) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"kinds": [], "extensions": [], "signers": {}})

    transport = httpx.MockTransport(handler)
    async with X402FacilitatorClient(config, client=httpx.AsyncClient(transport=transport)) as client:
        await client.supported()
