# 0007. Security and trust model

- **Status:** Accepted
- **Date:** 2026-11-11
- **Related:** [0001](0001-merchant-sdk-layers.md), [0002](0002-settlement-replay-idempotency.md), [0003](0003-bootstrap-and-configuration.md), [0005](0005-error-model-and-observability.md)

## Context

The SDK handles payment authorizations and talks to the AneePay facilitator, but
it never holds private keys and never signs transactions. That reduces the
blast radius, but it does not remove the attack surface:

- `PAYMENT-SIGNATURE` is attacker-controlled input;
- a replay can buy the same resource twice;
- a misconfigured `payTo` sends money to the wrong recipient;
- an operator-controlled facilitator URL can become an SSRF vector;
- an oversized or malformed header can exhaust memory or CPU;
- upstream error text can leak topology;
- a dependency compromise can execute inside the merchant's process.

The trust boundaries must be explicit, especially because `account_id` is an
identifier, not a credential.

## Decision

### 1. Trust boundaries

| Component | Trust level | Consequences |
| --- | --- | --- |
| Merchant application | trusted | runs the SDK in-process; owns its access control and secrets |
| Client / agent / wallet | untrusted | every header and payload is validated |
| AneePay facilitator | trusted for verify/settle | responses are validated; error text is not trusted for display |
| Replay store | trusted, but may be unavailable | fail closed when it cannot reserve |
| `account_id` | public identifier | never treated as authentication or a secret |

The SDK does not custody funds, hold private keys, or sign. Those remain the
wallet's and the facilitator's responsibility.

### 2. Transport security

- `facilitator_url` must use `https://` in production.
- `http://` is accepted only for loopback hosts (`localhost`, `127.0.0.1`,
  `::1`) in tests. There is no global "disable TLS verification" flag.
- TLS certificate verification is always on.
- Redirects are disabled for facilitator calls. The SDK talks only to the
  configured base URL plus the fixed `/x402/*` paths.
- The URL must not contain userinfo (`user:password@`), a query string, or a
  fragment. Custom path overrides must start with `/`, must not contain `..`,
  and must not contain a scheme or host.
- Timeouts are mandatory and apply to connect, read, write, and pool.

### 3. Input validation

`PAYMENT-SIGNATURE` is untrusted:

- maximum decoded size: 16 KiB (configurable only downward by the application);
- strict base64 decoding; reject invalid padding and non-canonical input;
- JSON must be an object with the expected x402 v2 shape; reject duplicate
  security-relevant keys where the parser exposes them;
- multiple `PAYMENT-SIGNATURE` header values are rejected, not merged;
- `x402Version` must be `2`; `scheme` must be `exact`;
- `network`, `asset`, `payTo`, and `amount` must match the server offer;
- addresses are compared case-insensitively and must be valid, non-zero
  addresses;
- `amount` and `authorization.value` must be equal and must be a canonical
  integer string in atomic units; reject signs, whitespace, scientific notation,
  and leading zero ambiguity where it changes the value;
- `authorization.to` must equal the configured `payTo`;
- `validAfter` and `validBefore` must be integers; reject a window that is
  already expired or not yet valid, allowing a small clock skew (60 seconds);
- `validBefore` must not exceed the configured `max_timeout_seconds` plus skew;
  a client cannot ask for an unbounded authorization window.

The facilitator performs the cryptographic verification. The SDK's local checks
are defense in depth, not a replacement for `/verify`.

### 4. Replay and resource exhaustion

- Replay protection follows ADR 0002: atomic reservation, shared store in
  production, fail closed when the store is unavailable.
- The in-memory store is bounded (TTL plus a maximum entry count) so a flood of
  distinct payments cannot grow memory without limit.
- Request bodies and headers are bounded before expensive parsing.
- The SDK does not perform on-chain RPC calls, so it does not add an RPC
  amplification vector.
- Rate limiting is the merchant's edge/application responsibility. The SDK
  documents recommended limits; it does not silently implement a global one.

### 5. SSRF and URL handling

- The facilitator URL comes only from operator configuration, never from a
  request header, query parameter, or payment payload.
- The URL scheme, host, port, and path are validated before use.
- Redirects are disabled, so a compromised facilitator cannot redirect the SDK
  to an arbitrary internal host.
- Proxy environment variables are not read implicitly; the application may pass
  an `httpx.AsyncClient` with its own proxy policy.
- The SDK never fetches URLs from `PaymentRequired.resource`, extension data, or
  client input.

### 6. Error and secret handling

- Error responses follow ADR 0005: no upstream URL, response body, header,
  stack trace, or account data.
- `PAYMENT-SIGNATURE`, the authorization, and signatures are treated as
  sensitive until settled. They are never logged.
- `account_id` is an identifier, but logs still minimize it; it is not a secret
  and must not be presented as one.
- The replay store contains no private data; keys are payment identifiers and
  nonces, not secrets.
- Debug mode must not exist as a public switch that dumps raw requests.

### 7. Dependency and supply-chain security

- Runtime dependencies are limited to `httpx`, `pydantic`, and `starlette`
  (plus optional `fastapi`/`mcp` extras).
- No dependency may execute arbitrary code at import time or add an undisclosed
  post-install script.
- Development dependencies are locked; runtime dependencies use tested ranges.
- Dependabot or an equivalent update process is enabled.
- CI runs a dependency audit and a secret scan.
- Releases use PyPI trusted publishing where available, build from a clean
  checkout, and publish a wheel and sdist that were tested as installed
  artifacts.
- No `eval`, `exec`, `pickle`, or dynamic import of untrusted strings.

### 8. Data handling

- The SDK stores only replay keys and short-lived operational state.
- Payer addresses are public blockchain data, but logs should still avoid
  unnecessary linkage.
- The merchant owns retention, webhook payloads, and back-office records.
- The SDK does not send payment data anywhere except the configured facilitator.

### 9. Out of scope

- Smart-contract security and the gateway clone implementation.
- Custody, key management, and wallet compromise.
- Facilitator infrastructure compromise.
- DDoS protection at the edge.
- Merchant application authentication and authorization.
- MCP-specific threats until the MCP layer gets its own ADR.

## Alternatives

- **Trust the client's `accepted` object** — rejected: the client controls it;
  it must match the server offer.
- **Use `account_id` as authentication** — rejected: it is an identifier and is
  not secret.
- **Allow plaintext HTTP for convenience** — rejected: it exposes payment
  authorizations to the network.
- **Follow redirects** — rejected: it turns the facilitator URL into an SSRF
  pivot.
- **Store raw headers for debugging** — rejected: signatures and authorization
  data are sensitive.
- **Implement rate limiting inside the SDK** — rejected: it belongs to the edge
  or the application and would be process-local anyway.
- **Depend on a large web framework at import time** — rejected: it increases
  the attack and conflict surface for core users.

## Consequences

- (+) The attack surface stays small and explicit.
- (+) Replay, wrong-recipient, SSRF, and header-flood attacks have documented
  mitigations.
- (+) Client-visible errors cannot leak facilitator topology.
- (+) The package remains usable without custody or key material.
- (−) Production requires HTTPS and a shared replay store.
- (−) The 16 KiB header limit may reject unusual clients; it is documented.
- (−) The SDK cannot protect against a compromised facilitator or a malicious
  merchant application.
- (−) Rate limiting and edge protection remain the merchant's responsibility.

## Acceptance criteria

1. A non-HTTPS facilitator URL is rejected except for loopback test hosts.
2. Redirects are disabled and tested.
3. Oversized, malformed, or duplicate `PAYMENT-SIGNATURE` headers are rejected.
4. Expired, not-yet-valid, or over-long authorizations are rejected.
5. Wrong `payTo`, `asset`, `network`, or amount is rejected before `/verify`.
6. A replay is rejected before the handler runs.
7. An unavailable replay store fails closed with `503`.
8. Error responses and logs contain no signature or upstream body.
9. Dependency audit and secret scan run in CI.
10. The README documents the trust boundaries and the lack of custody.

## Review triggers

1. The facilitator introduces authentication beyond `X-Account-Id`.
2. A new scheme (`upto`, Permit2, escrow) changes the authorization model.
3. The MCP layer ships and exposes tool-call data.
4. A security incident or dependency advisory affects the runtime.
5. A merchant asks the SDK to hold keys or sign transactions.
