"""Async HTTP client for the AneePay x402 facilitator.

The client only talks to the facilitator (``/x402/supported``, ``/x402/verify``,
``/x402/settle``); it never touches the chain and holds no private keys. Wrap it
in ``async with`` or call :meth:`aclose` to release the underlying connection
pool when the client owns it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx

from x402_sdk.exceptions import FacilitatorError
from x402_sdk.schemas import (
    PaymentRequest,
    SettleResponse,
    SupportedResponse,
    VerifyResponse,
    to_wire,
)

if TYPE_CHECKING:
    from types import TracebackType

    from x402_sdk.config import PaymentConfig

__all__ = ["X402FacilitatorClient"]

_ACCOUNT_HEADER = "X-Account-Id"
_HTTP_CLIENT_ERROR = 400


class X402FacilitatorClient:
    """Thin async wrapper over the facilitator HTTP API.

    Attributes:
        config: Merchant configuration with facilitator URLs and the account id.
    """

    def __init__(self, config: PaymentConfig, client: httpx.AsyncClient | None = None) -> None:
        """Create a client.

        Args:
            config: Merchant SDK configuration.
            client: Optional pre-built ``httpx.AsyncClient`` (e.g. with a mock
                transport). When omitted the client creates and owns one.
        """
        self.config = config
        self._client = client
        self._owns_client = client is None

    @property
    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.config.request_timeout_seconds)
            self._owns_client = True
        return self._client

    async def aclose(self) -> None:
        """Close the underlying HTTP client if this instance owns it."""
        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> X402FacilitatorClient:  # noqa: PYI034 (typing.Self is 3.11+)
        """Enter the async context manager."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Exit the async context manager, closing an owned client."""
        await self.aclose()

    async def supported(self) -> SupportedResponse:
        """Fetch the facilitator's supported schemes/networks.

        Returns:
            Parsed ``/x402/supported`` response.

        Raises:
            FacilitatorError: On transport errors or non-2xx responses.
        """
        response = await self._request("GET", self.config.supported_url)
        return SupportedResponse.model_validate(response.json())

    async def verify(self, request: PaymentRequest) -> VerifyResponse:
        """Ask the facilitator to verify a payment without settling it.

        Args:
            request: Client payload plus the server's payment requirements.

        Returns:
            Parsed ``/x402/verify`` response.

        Raises:
            FacilitatorError: On transport errors or non-2xx responses.
        """
        response = await self._request("POST", self.config.verify_url, json=to_wire(request))
        return VerifyResponse.model_validate(response.json())

    async def settle(self, request: PaymentRequest) -> SettleResponse:
        """Ask the facilitator to settle a verified payment on-chain.

        Args:
            request: Client payload plus the server's payment requirements.

        Returns:
            Parsed ``/x402/settle`` response.

        Raises:
            FacilitatorError: On transport errors or non-2xx responses.
        """
        headers = {_ACCOUNT_HEADER: str(self.config.account_id)}
        response = await self._request("POST", self.config.settle_url, json=to_wire(request), headers=headers)
        return SettleResponse.model_validate(response.json())

    async def _request(
        self,
        method: str,
        url: str,
        *,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        try:
            response = await self._http.request(method, url, json=json, headers=headers)
        except httpx.HTTPError as exc:
            raise FacilitatorError(f"facilitator request to {url} failed: {exc}") from exc
        if response.status_code >= _HTTP_CLIENT_ERROR:
            raise FacilitatorError(f"facilitator at {url} returned HTTP {response.status_code}: {response.text}")
        return response
