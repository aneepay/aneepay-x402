# aneepay-x402

Merchant-side SDK for the [x402](https://x402.org) exact scheme (EVM) on top of the
AneePay facilitator.

The package lets an HTTP resource server charge for an endpoint: it advertises a
`402 Payment Required` offer, verifies the client's EIP-3009 authorization with the
facilitator, serves the resource and settles the payment.

> Status: alpha. Wire version: x402 **v2 only**. API may change before 1.0.

## Install

```bash
pip install aneepay-x402
```

## Usage (planned API)

```python
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from x402_sdk import PaymentConfig, require_payment

payments = PaymentConfig(
    facilitator_url="http://localhost:8080",
    account_id="<account-uuid>",
    network="eip155:31337",
    pay_to="0x<gateway-clone-address>",
)


async def premium(request):
    return JSONResponse({"data": "..."})


app = Starlette(
    routes=[Route("/premium", require_payment(premium, payments, price="0.01"))],
)
```

`require_payment` relies only on Starlette primitives, so it also works as a FastAPI
dependency.

## Layout

```text
x402_python/
├── pyproject.toml
├── LICENSE
├── README.md
├── src/x402_sdk/
│   ├── __init__.py
│   ├── config.py         # endpoint/offer configuration
│   ├── requirements.py   # PaymentRequired builder, price -> atomic amount
│   ├── client.py         # httpx client for /x402/verify and /x402/settle
│   └── middleware.py     # require_payment(...)
└── tests/
```

## Development

```bash
uv sync --extra dev
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

This package is self-contained: it must not import from the rest of the monorepo
(`fastapi/src`, `django/`). The wire schemas are duplicated here on purpose and
guarded by a contract test.

## License

MIT — see [LICENSE](LICENSE).
