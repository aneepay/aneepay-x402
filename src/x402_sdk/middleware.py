"""Starlette/FastAPI HTTP middleware enforcing x402 payment.

:func:`require_payment` returns an HTTP middleware compatible with
``@app.middleware("http")`` (FastAPI and Starlette). On a paid request it:

1. returns ``402`` with a ``PAYMENT-REQUIRED`` header when the client sent no
   ``PAYMENT-SIGNATURE`` header (or sent an invalid/foreign one);
2. calls ``POST /x402/verify`` on the facilitator;
3. runs the wrapped resource only for a valid payment (``call_next``);
4. settles via ``POST /x402/settle`` after the resource succeeded and attaches
   the result as a base64 ``PAYMENT-RESPONSE`` header.

Only Starlette primitives are used, so the middleware works in FastAPI and
Starlette alike.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from starlette.responses import JSONResponse

from x402_sdk.client import X402FacilitatorClient
from x402_sdk.exceptions import ConfigError, FacilitatorError, PaymentError
from x402_sdk.requirements import (
    build_payment_request,
    decode_payment_signature_header,
    encode_payment_required_header,
    encode_payment_response_header,
)
from x402_sdk.schemas import (
    HEADER_PAYMENT_REQUIRED,
    HEADER_PAYMENT_RESPONSE,
    HEADER_PAYMENT_SIGNATURE,
    to_wire,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from starlette.requests import Request
    from starlette.responses import Response

    from x402_sdk.config import PaymentConfig
    from x402_sdk.schemas import PaymentPayload, PaymentRequired, PaymentRequirements

__all__ = ["require_payment"]

_PAYMENT_REQUIRED_STATUS = 402
_HTTP_CLIENT_ERROR = 400


@dataclass(frozen=True)
class _Enforcement:
    """Server-side state shared by the middleware closure."""

    config: PaymentConfig
    payment_required: PaymentRequired
    requirements: PaymentRequirements
    client: X402FacilitatorClient | None


def require_payment(
    config: PaymentConfig,
    payment_required: PaymentRequired,
    *,
    client: X402FacilitatorClient | None = None,
) -> Callable[[Request, Callable[[Request], Awaitable[Response]]], Awaitable[Response]]:
    """Build an HTTP middleware enforcing payment for one resource.

    Args:
        config: Merchant SDK configuration.
        payment_required: Wire ``402`` body (built with
            :func:`~x402_sdk.build_payment_required`). Its first accepted
            requirement is enforced and re-sent to the facilitator.
        client: Optional pre-built facilitator client (e.g. with a mock
            transport). When omitted a client is created per request and closed
            afterwards.

    Returns:
        An async ``(request, call_next)`` middleware suitable for
        ``app.middleware("http")``.

    Raises:
        ConfigError: If ``payment_required`` has no accepted requirements.
    """
    if not payment_required.accepts:
        raise ConfigError("payment_required must contain at least one accepted requirement")
    enforcement = _Enforcement(
        config=config,
        payment_required=payment_required,
        requirements=payment_required.accepts[0],
        client=client,
    )

    async def middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        """Enforce x402 payment around the wrapped resource."""
        return await _enforce(request, call_next, enforcement)

    return middleware


async def _enforce(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
    enforcement: _Enforcement,
) -> Response:
    """Reject unpaid requests, otherwise hand off to the settlement flow."""
    signature = request.headers.get(HEADER_PAYMENT_SIGNATURE)
    if not signature:
        return _payment_required_response(enforcement.payment_required)
    try:
        payload = decode_payment_signature_header(signature)
        _validate_payload(payload, enforcement.requirements, enforcement.config)
    except PaymentError as exc:
        return _payment_required_response(enforcement.payment_required, error=str(exc))
    return await _process_payment(request, call_next, enforcement, payload)


async def _process_payment(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
    enforcement: _Enforcement,
    payload: PaymentPayload,
) -> Response:
    """Verify the payment, run the resource, then settle and tag the response."""
    payment_request = build_payment_request(payload, enforcement.requirements)
    owns_client = enforcement.client is None
    active = enforcement.client if enforcement.client is not None else X402FacilitatorClient(enforcement.config)
    try:
        verification = await active.verify(payment_request)
        if not verification.is_valid:
            error = _reason(verification.invalid_reason, "invalid_payment")
            return _payment_required_response(enforcement.payment_required, error=error)

        response = await call_next(request)
        if response.status_code >= _HTTP_CLIENT_ERROR:
            return response

        settlement = await active.settle(payment_request)
        if not settlement.success:
            error = _reason(settlement.error_reason, "settlement_failed")
            return _payment_required_response(enforcement.payment_required, error=error)

        response.headers[HEADER_PAYMENT_RESPONSE] = encode_payment_response_header(settlement)
    except FacilitatorError as exc:
        return _payment_required_response(enforcement.payment_required, error=str(exc))
    else:
        return response
    finally:
        if owns_client:
            await active.aclose()


def _validate_payload(payload: PaymentPayload, requirements: PaymentRequirements, config: PaymentConfig) -> None:
    """Check the client payload against the server requirements before ``/verify``.

    Raises:
        PaymentError: If any field does not match the configured offer.
    """
    accepted = payload.accepted
    checks = {
        "scheme": (accepted.scheme, requirements.scheme),
        "network": (accepted.network, requirements.network),
        "asset": (accepted.asset.lower(), requirements.asset.lower()),
        "payTo": (accepted.pay_to.lower(), requirements.pay_to.lower()),
        "amount": (accepted.amount, requirements.amount),
    }
    for name, (actual, expected) in checks.items():
        if actual != expected:
            raise PaymentError(f"accepted {name} does not match payment requirements")

    authorization = payload.payload.authorization
    if authorization.to.lower() != config.pay_to.lower():
        raise PaymentError("authorization recipient does not match the configured payTo")
    if authorization.value != requirements.amount:
        raise PaymentError("authorization value does not match the required amount")


def _reason(value: str | None, default: str) -> str:
    """Return a non-empty reason, falling back to ``default``."""
    return value or default


def _payment_required_response(payment_required: PaymentRequired, *, error: str | None = None) -> JSONResponse:
    """Build a ``402`` response carrying the ``PAYMENT-REQUIRED`` header."""
    body = payment_required.model_copy(update={"error": error}) if error is not None else payment_required
    return JSONResponse(
        status_code=_PAYMENT_REQUIRED_STATUS,
        content=to_wire(body),
        headers={HEADER_PAYMENT_REQUIRED: encode_payment_required_header(body)},
    )
