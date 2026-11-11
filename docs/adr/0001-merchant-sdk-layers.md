# 0001. Merchant SDK x402: two layers — protocol core and framework integrations

- **Status:** Accepted
- **Date:** 2026-11-11
- **Related:** [0002](0002-settlement-replay-idempotency.md), [0003](0003-bootstrap-and-configuration.md), [0004](0004-wire-contract-vendoring.md), [0005](0005-error-model-and-observability.md), [0006](0006-versioning-and-support.md), [0007](0007-security-and-trust-model.md)

## Context

The merchant's resource server installs the `aneepay-x402` SDK — a separate package and
repository (PyPI, MIT) that has no dependencies outside its own distribution. AneePay
(aneepay.com) owns the facilitator wire contract; the SDK vendors the public schemas and
pins them with a contract test. This ADR lives in the SDK repository: it defines the
package's layer boundaries and its public contract. Wire decisions are made by AneePay
and are not reopened here.

**1. Today's SDK surface is protocol-level, not application-level.** In `0.1.0` it is
1,036 lines across 7 modules and more than 30 names in `__all__`: schemas, codecs for
`PAYMENT-*` headers, `build_*` builders, the facilitator HTTP client, and
`require_payment` — a Starlette middleware factory. Integration requires the merchant to
know:

- that `payTo` is the address of their per-merchant gateway clone, not their own wallet;
- the network in CAIP-2 form (`eip155:137`), not "Polygon";
- the token `decimals` and the **token's EIP-712 domain** (`name`/`version`) — otherwise
  client signatures will not verify;
- that the offer must be built, cached, and matched to a path manually:
  `OFFERS = {"/v1/report": build_payment_required(...)}`, and `require_payment` does not
  filter routes. The README states it plainly: *"Route filtering is your job"*.

This is protocol knowledge, not the merchant's task. The merchant's task is "charge for
this endpoint/tool".

**2. The gap is not code quality; it is the absence of a second layer.** The SDK's
`draft.md` in this repository (the `0.1 → Beta` path) lists core blockers: only `accepts[0]`, string
comparison of amounts (`"010000" != "10000"`), `extra="forbid"` on inbound schemas, a
facilitator client created per request with no retries or circuit breaker, no replay
guard, `FacilitatorError` text leaking to the client, no observability. All of these are
fixed in the core. A facade built on top of an unfixed core would cement them into the
public API.

**3. The facilitator already exposes everything the merchant should not need to know.**
`GET /x402/merchant` returns, for each supported network, `payTo`, `asset`, `decimals`,
and the EIP-712 `extra {name, version, assetTransferMethod}`; `GET /x402/supported`
returns `kinds`/`signers`. Therefore `account_id` alone is enough to start: everything
else is derived from the public facilitator API at aneepay.com rather than copied from
documentation.

**4. The public promise has already been made.** The public x402 documentation at
aneepay.com describes the flow and names the `aneepay-x402` Python SDK as its
implementation. The SDK README's 41 KB, including a separate "Behaviour and caveats"
section, is the price of not having a facade layer.

## Decision

### 1. One distribution, two layers

| Layer | Location | Audience | Stability |
| --- | --- | --- | --- |
| **core** | `x402_sdk` (`schemas`, `requirements`, codecs, `client`, `require_payment`) | advanced: custom plumbing, non-Starlette stacks, wire debugging | public, changes under semver |
| **framework** | `x402_sdk.fastapi` (extra `[fastapi]`), later `x402_sdk.mcp` (extra `[mcp]`) | API/MCP server owner | **entry point and primary contract** |

Not separate packages. Reasons: one version and one release, one contract test for the
wire schemas, and no possibility of schema drift between the "core" and the "plugin".
FastAPI and the MCP SDK are optional dependencies; `starlette` is already in core.

### 2. What counts as the public contract

- **framework** — what we promise not to break: names, signatures, behaviour (payment,
  error codes, headers). Any change is minor/major under semver plus a
  `CHANGELOG.md` entry.
- **core** — public, but `advanced`: primitives for those building their own plumbing. It
  may change earlier and more aggressively, but not silently.
- `require_payment` **is not removed before 1.0**; after that it gets a deprecation cycle
  rather than an abrupt removal.
- The README quickstart shows **only** the framework layer; core is documented in a
  separate "Advanced" section.

### 3. Shape of the framework layer (FastAPI)

```python
from fastapi import FastAPI
from x402_sdk.fastapi import X402

x402 = X402.from_aneepay(account_id="2f1c2a3b-6f3d-4f7a-9b21-0a6b3f5d1c90")
app = FastAPI(lifespan=x402.lifespan)
x402.install(app)

@app.get("/v1/report")
@x402.paid("0.05")
async def report(): ...
```

The layer's mandatory minimum:

- `from_aneepay(...)` — declares bootstrapping from `/x402/merchant` and validation
  against `/x402/supported`; the actual fetch happens in the lifespan, never on import
  (ADR 0003). Configuration errors fail startup with a clear message.
- `from_config(...)` — fully offline path for tests and deployments that already know
  the wire values (ADR 0003).
- `install(app)` / `X402Route` — route-level interception, installed before routes are
  registered; no I/O (ADR 0003).
- `paid("0.05")` next to the route: `per="request"` only in `0.2`, `price=lambda
  request: ...` for dynamic pricing; metered pricing is deferred (ADR 0003).
- OpenAPI: `402` plus `x-payment-info` on a paid route; the price list is exposed at
  `/.well-known/x402` (ADR 0003).
- `on_settled(event)` — typed settlement hook; `on_event(event)` covers the whole
  payment lifecycle (ADR 0005).

### 4. Implementation rules mandatory for any framework layer

1. **No matching against `request.url.path`.** The price is bound to the route object:
   `{id}` parameters, prefixes, and mounted applications must work. HTTP middleware cannot
   see `request.scope["route"]` (routing happens inside `call_next`), so the FastAPI layer
   is built on an `APIRoute` wrapper. Mounted sub-apps need their own `install` (ADR 0003).
2. **One `httpx.AsyncClient` per process**, created in the lifespan and closed on shutdown.
   A client per request is forbidden (ADR 0002).
3. **Facilitator unavailable → `503` + `Retry-After`, not `402`.** `402` means "pay" and
   provokes another signature/payment attempt (ADR 0005).
4. **Settlement order is explicit.** In `0.2` the only supported order is verify →
   handler → settle; `settle_before_execute` is not offered until a compensation/refund
   path exists (ADR 0002).
5. **A failed settle does not return paid content.** The client receives a payment error;
   the handler body is discarded.
6. **The replay guard is on by default**, with a pluggable store (in-memory / Redis); the
   key is the deterministic `payment_id` from `(network, payer, nonce)`, not the bare
   nonce (ADR 0002).
7. **Amounts are compared as integers/`Decimal`**, not as strings.
8. **Strictness is asymmetric**: SDK-generated outbound models are `extra="forbid"`;
   forwarded client payloads preserve unknown fields; facilitator responses use
   `extra="ignore"` (ADR 0004).
9. **Errors are sanitized**: facilitator text does not reach the client. `402` keeps the
   x402 `PaymentRequired` body; other errors use RFC 7807 (ADR 0005).
10. **No network calls on import.** Only in the lifespan/startup; `install` performs no
    I/O (ADR 0003).

### 5. What must not be hidden behind defaults

The facade must not create the illusion that monetary semantics "will sort themselves out".
The following remain explicit: settlement order (fixed to verify → handler → settle in
`0.2`), replay/idempotency and its store, timeouts and retries, behaviour when the
facilitator is unavailable, and typed exceptions. Defaults are documented, but not
irreversible.

### 6. Delivery order

1. **`0.2.0`, core only** — the fixes from `draft.md`: `extra="ignore"`, numeric amount
   comparison, retries/backoff, `503` when the facilitator is unavailable, replay, an
   error sanitizer, and a type gate in CI.
2. **FastAPI framework layer** on top of the fixed core.
3. **MCP** — only after that, and only when MCP is unblocked. This ADR **does not reopen**
   MCP: it only reserves the layer's shape (`x402_sdk.mcp`, extra `[mcp]`) and requires the
   public MCP transport specification to be vendored before work begins.

### 7. Ownership of the wire contract does not change

The framework layer adds no protocol fields: any wire change is made by AneePay and
reflected in an updated vendored snapshot. The SDK continues to vendor the schemas and pin
them with a contract test. The precedent is the seam test that runs against the
**published** version of the package.

### 8. Testing the layer

- Unit tests — offline: `httpx.MockTransport` for the facilitator, `TestClient`/ASGI for
  routes; no database or network.
- Seam tests — against the published version of the package: 402 → verify → handler →
  settle → `PAYMENT-RESPONSE`.
- Required scenarios: no payment; invalid payment; facilitator unavailable (`503`);
  handler returned an error (settle is not called); settle failed (body is not returned);
  repeated `PAYMENT-SIGNATURE` (replay); dynamic pricing and path parameters.

## Alternatives

- **Keep one flat API** — rejected: the entry barrier remains, every merchant writes their
  own dispatch, behaviour diverges, and bugs multiply.
- **A separate `aneepay-x402-fastapi` package** — rejected: two versions and two releases,
  duplicated schemas, and inevitable version skew between the core and the plugin.
- **Merge the SDK into the facilitator service** — rejected: the SDK is deliberately
  self-contained, has an independent release cycle and external consumers; the facilitator
  owns only the wire contract.
- **Hide everything behind one call with no settings** — rejected: monetary semantics
  (settlement order, idempotency, failure behaviour) must be explicit.
- **Remove `require_payment` immediately** — rejected: it breaks `0.1.0` consumers and cuts
  off non-Starlette stacks that need the primitives.
- **Ship the MCP plugin together with FastAPI** — rejected: MCP remains deferred, the
  client-side risk (whether mainstream clients can pay) is unresolved, and two new layers
  at once double the test surface.

## Consequences

- (+) There is now an entry point for "monetize an endpoint" rather than "assemble wire
  messages": the quickstart is config plus a decorator.
- (+) `from_aneepay` removes contract addresses and the EIP-712 domain from integration —
  the most common cause of "the signature does not verify".
- (+) Core remains available: non-Starlette stacks and debugging are not cut off.
- (+) One package — one version, one contract test, no possibility of schema skew.
- (−) Two entry points require documentation discipline (quickstart — framework only, core
  — "Advanced"), otherwise users land in the primitives again.
- (−) The startup bootstrap is a network call: without fail-fast behaviour and an
  offline `from_config`, we get "the application does not start without the facilitator".
- (−) The CI matrix grows: FastAPI/Starlette versions and extra dependencies.
- (−) The public surface grows; before 1.0 this is manageable, but `CHANGELOG.md` and
  semver become mandatory rather than "as it happens".
- (−) Risk of "magic": the more defaults there are, the more important section 5 becomes —
  otherwise the merchant does not understand when and why they were charged.

## Acceptance criteria (Definition of Done for the framework layer)

1. The README quickstart is no more than five lines, with no base64, headers, or `OFFERS`
   dictionary.
2. `account_id` plus the default (or explicit) facilitator URL is enough to start;
   `payTo`, network, token, and EIP-712 domain come from `/x402/merchant` and are
   validated against `/x402/supported`.
3. The price is declared on the route; path parameters, router prefixes, and mounted
   applications work (each mounted app is installed explicitly).
4. The paid route is visible in OpenAPI (`402` + `x-payment-info`), and
   `/.well-known/x402` exists.
5. All scenarios from section 8, "Testing the layer", are covered; the seam test runs
   against the published version.
6. `require_payment` continues to work unchanged; core primitives are exported and
   documented.

## Out of scope

- The MCP transport and a client-side payer SDK (separate decisions; MCP is deferred).
- Multi-option offers (`accepts[]` with more than one entry) — a core fix, not a facade
  concern.
- Metered (`per="token"`) pricing: the `exact` scheme fixes the amount in the client's
  signature before the handler runs; metering needs `upto` or a separate design.
- Key storage, a custodial wallet, billing/subscriptions, and a dashboard.
- SDKs in other languages (TS/Go) and a catalog of paid tools.

## Review triggers

1. An external consumer appears that needs a framework layer other than FastAPI.
2. The `0.2.0` core fixes turn out to be incompatible with the facade's shape (which means
   the core/framework boundary was defined incorrectly).
3. MCP is unblocked — then this ADR is extended with a section on `x402_sdk.mcp` rather
   than rewritten.
