# 0005. Error model, HTTP responses and observability

- **Status:** Accepted
- **Date:** 2026-11-11
- **Related:** [0001](0001-merchant-sdk-layers.md), [0002](0002-settlement-replay-idempotency.md), [0003](0003-bootstrap-and-configuration.md), [0007](0007-security-and-trust-model.md)

## Context

In `0.1.0` the SDK returns `402` for both "payment required" and "the facilitator
is down", and it puts the raw `FacilitatorError` text into the `error` field. That
leaks upstream topology to the client, makes an outage look like a payment
problem, and gives the merchant no structured way to observe what happened.

Payments need three different signals:

- the client must know whether to sign a new payment, wait, or fix the request;
- the merchant must know whether money moved and whether an incident needs
  attention;
- an operator must be able to correlate a client report with a log line without
  exposing internals.

The `402` response has a protocol-defined body (`PaymentRequired`), so a generic
RFC 7807 body cannot replace it. Other errors have no such constraint.

## Decision

### 1. Error taxonomy

Public SDK exceptions are part of the API:

- `X402Error` — base class;
- `ConfigError` — invalid configuration or startup data;
- `AmountError` — a price cannot be represented exactly in token units;
- `PaymentError` — the client payment is malformed or does not match the offer;
- `ReplayError(PaymentError)` — the payment was already used or is in flight;
- `FacilitatorError` — transport, HTTP, or protocol failure while calling the
  facilitator;
- `SettlementError(X402Error)` — verification passed but settlement was rejected.

Internal exceptions must be translated at the boundary. A raw upstream body,
traceback, URL, or header must never reach the client.

### 2. HTTP response mapping

| Situation | Status | Body | Notes |
| --- | --- | --- | --- |
| No `PAYMENT-SIGNATURE` | `402` | x402 `PaymentRequired` | `PAYMENT-REQUIRED` header; `error` is a safe code |
| Malformed or mismatched payment | `402` | x402 `PaymentRequired` | `error="payment_invalid"` |
| Verification returned `isValid=false` | `402` | x402 `PaymentRequired` | safe mapped reason |
| Replay / payment in flight | `402` | x402 `PaymentRequired` | `error="payment_already_used"` or `payment_in_progress` |
| Handler returned an error | handler status | handler body | `/settle` is not called |
| Settlement rejected (`success=false`) | `402` | x402 `PaymentRequired` | `error="settlement_failed"`; paid content is not returned |
| Facilitator unavailable after retries | `503` | RFC 7807 | `Retry-After`; never `402` |
| Settlement transport failure | `503` | RFC 7807 | `Retry-After`; paid content is not returned |
| Unexpected SDK bug | `500` | RFC 7807 | generic `internal_error`; trace id only |
| Configuration/startup failure | no response | exception | application must not start |

The `402` body stays x402-compatible: `x402Version`, `error`, `resource`,
`accepts`, `extensions`. The `PAYMENT-REQUIRED` header is always present. RFC 7807
is used for `5xx` responses and for errors that are not part of the x402 payment
handshake. This split is intentional and documented; a problem+json body on `402`
would break x402 clients.

### 3. Stable error codes

`error` in a `402` and `code` in a problem document use stable, machine-readable
values:

- `payment_required`
- `payment_invalid`
- `payment_already_used`
- `payment_in_progress`
- `settlement_failed`
- `facilitator_unavailable`
- `configuration_error`
- `internal_error`

`detail` is for humans and must not be parsed by clients. Unknown upstream
reasons map to `payment_invalid` or `settlement_failed`; the raw value is logged,
not returned.

### 4. Problem details

For `5xx` responses:

```json
{
  "type": "https://aneepay.com/problems/facilitator-unavailable",
  "title": "Payment facilitator unavailable",
  "status": 503,
  "detail": "The payment facilitator did not respond in time.",
  "instance": "/v1/report",
  "code": "facilitator_unavailable",
  "trace_id": "3f2c...",
  "retry_after": 5
}
```

Rules:

- `type` is a stable URI under `https://aneepay.com/problems/`;
- `title` is short and generic;
- `detail` is safe for the client and contains no upstream URL, body, header,
  account id, or stack trace;
- `instance` is the request path;
- `trace_id` is the correlation id from the request or a generated one;
- `retry_after` is present when the client should retry.

### 5. Sanitization

- `FacilitatorError` text is logged at `WARNING`/`ERROR` with the trace id and
  never copied into a response.
- Upstream `invalidReason`/`errorReason` values are mapped through a whitelist.
  Unknown values become the generic code for their category.
- Responses never include the facilitator base URL, response body, request
  headers, `PAYMENT-SIGNATURE`, authorization nonce, or stack traces.
- The `error` field in `PaymentRequired` is a safe code or a short safe message;
  it is not raw upstream text.

### 6. Correlation and logging

- Accept `X-Request-ID` if it is a bounded, safe token; otherwise generate a
  UUID. Propagate it to facilitator calls and include it in logs and problem
  documents.
- Use the standard `logging` module under the `x402_sdk` logger. Do not add a
  logging dependency.
- Structured fields: `event`, `trace_id`, `payment_id`, `route`, `network`,
  `amount`, `asset`, `payer`, `outcome`, `duration_ms`, `attempt`, `status`.
- Never log `PAYMENT-SIGNATURE`, the full authorization, or any signature.
  Payer addresses are public but should still be minimized.
- Levels: `INFO` for lifecycle and successful payments; `WARNING` for expected
  payment failures, replay, and retried facilitator calls; `ERROR` for
  settlement failure after the handler and unexpected bugs.

### 7. Hooks and events

The SDK exposes typed lifecycle events:

- `payment_required`
- `verify_succeeded`
- `verify_failed`
- `settled`
- `settlement_failed`
- `facilitator_error`
- `replay_rejected`

`on_event(event)` is optional, may be sync or async, is awaited, and must not
raise into the response path. Exceptions from hooks are logged and swallowed.
Hooks cannot mutate the payment result or the response.

`on_settled(event)` is a convenience hook for the successful `settled` event. It
fires only after a confirmed settlement, carries `payment_id`, `transaction`,
`payer`, `route`, `price`, `network`, `asset`, and `settled_at`, and may be
deduplicated by the merchant using `payment_id`.

Hooks are best-effort in-process notifications. They are not a delivery
guarantee for webhooks or back-office systems; the merchant must persist and
retry downstream work.

### 8. Metrics

The SDK does not depend on Prometheus or OpenTelemetry. Metrics are derived from
events, or the merchant supplies an adapter. The documented signals are:

- payments required;
- verification outcomes;
- settlement outcomes;
- facilitator errors and retries;
- replay rejections;
- end-to-end latency.

### 9. Health

The SDK does not own the application's health endpoint. It exposes
`x402.ready` (or the equivalent state) so the application can decide whether the
facilitator bootstrap and replay store are initialized. A health check must not
call the facilitator on every probe.

## Alternatives

- **Use RFC 7807 for `402`** — rejected: the x402 protocol defines the
  `PaymentRequired` body; replacing it breaks clients.
- **Return upstream error text** — rejected: leaks topology and is unstable.
- **Return `402` when the facilitator is down** — rejected: it makes the client
  sign and pay again for an outage.
- **Add OpenTelemetry as a hard dependency** — rejected for `0.2`: it increases
  install surface; events and a logging adapter are enough.
- **Fire-and-forget hooks** — rejected: settlement notifications would be lost
  silently; hooks are awaited with error isolation.
- **Log full headers for debugging** — rejected: signatures and account data
  must not be logged.

## Consequences

- (+) Clients can distinguish "pay", "retry later", and "fix the request".
- (+) Upstream failures no longer leak into client-visible messages.
- (+) Merchants get correlation ids and typed events without a metrics
  dependency.
- (+) The `402` response remains x402-compatible.
- (−) Two response formats (`402` x402 body and RFC 7807 for `5xx`) must be
  documented and tested.
- (−) Slow hooks add latency to the response path.
- (−) The merchant must deduplicate downstream effects by `payment_id`.

## Acceptance criteria

1. Every row in the HTTP mapping table has a test.
2. `402` responses preserve the x402 `PaymentRequired` body and header.
3. `503` responses include `Retry-After` and a problem document.
4. `FacilitatorError` text never appears in a response.
5. Unknown upstream reasons map to a stable code and are logged.
6. `X-Request-ID` is propagated or generated and appears in logs/problem
   documents.
7. Hook exceptions do not change the response.
8. Logs contain no `PAYMENT-SIGNATURE` or signature material.
9. Metrics can be derived from the documented events without an extra
   dependency.

## Review triggers

1. The x402 specification defines a standard error body for `402`.
2. A merchant requires OpenTelemetry or a metrics endpoint from the SDK.
3. Hooks become a delivery mechanism for webhooks rather than notifications.
4. A new failure mode appears that does not fit the mapping table.
