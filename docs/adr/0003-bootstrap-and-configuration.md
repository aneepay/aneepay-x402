# 0003. Bootstrap and configuration contract

- **Status:** Accepted
- **Date:** 2026-11-11
- **Related:** [0001](0001-merchant-sdk-layers.md), [0002](0002-settlement-replay-idempotency.md), [0004](0004-wire-contract-vendoring.md), [0007](0007-security-and-trust-model.md)

## Context

In `0.1.0` every merchant has to provide the full protocol configuration by hand:
the facilitator URL, `account_id`, CAIP-2 network, `payTo`, token address,
decimals, and EIP-712 `name`/`version`. That knowledge belongs to the protocol,
not to the merchant.

The AneePay facilitator already exposes the missing data:

- `GET /x402/merchant` returns, for the account in `X-Account-Id`, the
  `payTo`, `asset`, `decimals`, and EIP-712 `extra` for every serviceable
  network;
- `GET /x402/supported` returns the supported `kinds` (`x402Version`, `scheme`,
  `network`) and `signers`.

`account_id` is an identifier, not a credential. `X-Account-Id` is not
authentication; the merchant's own backend is responsible for access control.
The SDK must not present it as a secret.

The SDK also has hard lifecycle constraints:

- importing the package must not perform network I/O;
- a configuration error must fail application startup, not the first payment;
- tests must work fully offline;
- the FastAPI layer needs the facilitator data before the first request, but
  route interception must be installed before routes are registered.

## Decision

### 1. Two constructors, one object

```python
from x402_sdk.fastapi import X402

x402 = X402.from_aneepay(account_id="2f1c2a3b-6f3d-4f7a-9b21-0a6b3f5d1c90")
```

- `X402.from_aneepay(...)` performs **no I/O** and no network calls. It validates
  local arguments and returns a bootstrap-capable object. The name describes the
  source of the configuration, not the moment of the request.
- `X402.from_config(...)` is the explicit offline path. It accepts a complete
  `PaymentConfig` (or equivalent keyword arguments) and never calls the
  facilitator. It is the supported path for tests, air-gapped deployments, and
  consumers that already know the wire values.
- Both constructors return the same `X402` type and install the same framework
  behaviour.

### 2. Startup lifecycle

- `x402.lifespan` is an async context-manager factory (`async def lifespan(app)`)
  compatible with `FastAPI(lifespan=x402.lifespan)`. It fetches `/x402/merchant` and
  `/x402/supported`, validates them, creates the single process-wide
  `httpx.AsyncClient`, initializes the replay store, yields, and closes
  everything on exit.
- A custom lifespan calls `await x402.startup()` and `await x402.shutdown()`.
- `from_aneepay` without a startup hook is an invalid deployment: paid routes
  must fail with `503` and a clear log entry rather than lazily bootstrapping on
  the first request.
- Startup failures raise `ConfigError` with an actionable message: unknown
  account, no serviceable networks, requested network absent, unsupported
  scheme, or facilitator unreachable. The application must not start.
- `install(app)` performs **no I/O**. It must be called before any route is
  registered on that application. If routes already exist and the route class
  cannot be applied, `install` raises `ConfigError`; it never silently wraps only
  part of the application.
- Mounted sub-applications have their own router. Each mounted app that serves
  paid routes must call `install` on itself; the parent `install` does not
  propagate into mounts. This limitation is documented.

### 3. Bootstrap data and validation

`/x402/merchant` is the source of merchant-specific wire values:

- `accountId` must match the configured `account_id`;
- the response must contain at least one network;
- each network provides `network`, `payTo`, `asset`, `decimals`, and
  `extra {name, version, assetTransferMethod}`;
- `payTo` must be a valid non-zero address;
- `assetTransferMethod` must be `eip3009` in `0.2`;
- `decimals` must be in the token's valid range and must match the amount
  conversion.

`/x402/supported` is the capability check:

- `x402Version` must be `2` and `scheme` must be `exact`;
- `network` is matched as a CAIP-2 pattern (`eip155:*` is a wildcard), not by
  exact string equality;
- at least one supported kind must match the selected merchant network;
- `signers`, if present, is advisory in `0.2`; the SDK does not pin a signer
  address because the facilitator may rotate it.

### 4. Network selection

`/x402/merchant` can return several networks. The SDK does not guess.

- `network="eip155:137"` selects that network; if it is absent, startup fails
  with the list of available networks.
- If `network` is omitted and exactly one network is returned, that network is
  used.
- If `network` is omitted and several networks are returned, startup fails with
  `ConfigError` and the list of choices.

In `0.2` one `X402` instance serves one network and one accepted requirement per
paid route. Multi-network offers require `accepts[]` support in the core and are
out of scope (ADR 0001).

### 5. Configuration surface

`PaymentConfig` remains the explicit, serializable configuration object. It
contains no private keys and no API secrets.

Required values:

- `facilitator_url` — default `https://api.aneepay.com`, overridable;
- `account_id` — merchant UUID, sent as `X-Account-Id`;
- `network` — CAIP-2;
- `pay_to` — per-merchant gateway clone address;
- `token` — address, decimals, EIP-712 name/version.

Operational values:

- request timeouts and retry budget;
- replay store (default in-memory, shared required in production);
- `on_event`/`on_settled` hooks (ADR 0005);
- OpenAPI and `/.well-known/x402` toggles;
- `max_timeout_seconds` for the payment authorization.

Rules:

- The library does not read environment variables implicitly. The application
  composes configuration and passes it in; this keeps tests deterministic and
  prevents accidental secrets in process state.
- Floats are not accepted for prices. Use `Decimal`, `int`, or a decimal string.
- Unknown configuration keys are rejected.
- `from_config` does not call `/x402/supported`; the caller is responsible for
  wire compatibility. It still validates addresses, network format, decimals,
  and price conversion locally.

### 6. Route declaration

`x402.install(app)` sets the route class for paid routes. `@x402.paid("0.05")`
attaches the price to the route object, not to a URL string.

```python
app = FastAPI(lifespan=x402.lifespan)
x402.install(app)

@app.get("/v1/report")
@x402.paid("0.05")
async def report(): ...
```

- `per="request"` is the only pricing mode in `0.2`. Metered (`per="token"`)
  pricing is not compatible with the `exact` scheme, where the amount is fixed in
  the client's signature before the handler runs. It requires `upto` or a
  separate metering design and is out of scope.
- `price` accepts `Decimal`, `int`, or a decimal string. A callable receives the
  request and returns one of those types; exceptions become configuration
  errors before verification.
- Path parameters, router prefixes, and mounted applications must work. A
  mounted app needs its own `install` (see above).
- A free route must not be wrapped and must not require a payment header.

### 7. OpenAPI and `/.well-known/x402`

- Every paid route documents `402` and an `x-payment-info` extension containing
  network, asset, `payTo`, price, and resource metadata. No secrets are included.
- `/.well-known/x402` lists the paid resources of the running application:
  path, price, network, asset, `payTo`, description, and MIME type.
- Both are generated from the registered paid routes, not hand-maintained.
- The shape is part of the public contract and is covered by tests.

## Alternatives

- **Perform the bootstrap call at import time** — rejected: breaks serverless
  cold starts, offline tests, and the no-I/O-on-import rule.
- **Lazy bootstrap on the first paid request** — rejected: a configuration error
  becomes a production payment failure.
- **Pick the first network silently** — rejected: the merchant can charge on the
  wrong chain.
- **Read environment variables in the library** — rejected: hidden global state
  and accidental secret handling.
- **Require all values in `from_aneepay` too** — rejected: it removes the main
  benefit of the layer.
- **Support multiple networks in one instance** — rejected for `0.2`: the core
  still enforces `accepts[0]`; pretending otherwise would produce misleading
  offers.
- **Wrap mounted apps from the parent** — rejected: Starlette mounts have their
  own routers; implicit propagation would be fragile.

## Consequences

- (+) A merchant can start with `account_id` plus a facilitator URL.
- (+) `payTo`, token decimals, and the EIP-712 domain are no longer copied by
  hand.
- (+) Configuration errors fail at startup with a useful message.
- (+) Offline tests and air-gapped deployments use `from_config`.
- (−) The application depends on the facilitator at startup; `from_config` is
  the escape hatch.
- (−) A facilitator-side change to `payTo`, token, or domain requires a process
  restart in `0.2`; there is no background refresh.
- (−) One network per instance and one accepted requirement per route.
- (−) `install` order and mounted-app installation are user-visible constraints.

## Acceptance criteria

1. `from_aneepay` performs no network I/O; the fetch happens in the lifespan.
2. Startup fails with `ConfigError` for an unknown account, no networks, a
   missing requested network, or an unsupported scheme.
3. `from_config` works without any network and is covered by tests.
4. Wildcard `eip155:*` in `/x402/supported` is accepted for a concrete
   `eip155:<chainId>`.
5. Omitting `network` with multiple networks fails with a list of choices.
6. `install` after route registration fails loudly.
7. Mounted sub-apps require their own `install`; this is documented and tested
   with a free route.
8. OpenAPI and `/.well-known/x402` list paid routes and contain no secrets.
9. `per="token"` is rejected with a clear `ConfigError` in `0.2`.

## Review triggers

1. The core supports `accepts[]` with more than one requirement.
2. The facilitator exposes a refresh or versioned merchant-configuration
   endpoint.
3. `account_id` becomes an authenticated principal rather than an identifier.
4. The framework layer adds ASGI frameworks other than FastAPI.
