# 0002. Settlement, replay protection and idempotency

- **Status:** Accepted
- **Date:** 2026-11-11
- **Related:** [0001](0001-merchant-sdk-layers.md), [0005](0005-error-model-and-observability.md)

## Context

The x402 `exact` scheme works in three steps: the client signs an EIP-3009
authorization, the resource server verifies it with the facilitator, and the
facilitator settles it on-chain. Each step can fail independently:

- the handler can fail after a successful verification;
- `/settle` can time out after the transaction was broadcast;
- the client can retry the same `PAYMENT-SIGNATURE`;
- several workers can process the same payment concurrently;
- the facilitator can be unavailable while the merchant still has to answer the
  client.

The SDK is the merchant's last line of defense around money. It must not turn a
transient upstream failure into a second charge, must not serve paid content
without a successful settlement, and must not rely on in-process state that does
not exist across workers.

The facilitator settles idempotently for the same payment: the payment identity
is deterministic from `(network, payer, EIP-3009 nonce)`, and the token enforces
nonce uniqueness on-chain. The SDK uses the same identity for its own retries and
replay protection.

## Decision

### 1. Verify → handler → settle is the only supported order

In `0.2` the SDK supports exactly one settlement order:

1. verify the payment with the facilitator;
2. run the handler;
3. settle the payment;
4. attach `PAYMENT-RESPONSE` and return the handler response.

Rules:

- If the handler returns an error, `/settle` is **not** called and the handler
  response is returned unchanged.
- If settlement fails, the handler body is **not** returned to the client.
- Handler side effects must be idempotent or compensable by the merchant. The SDK
  cannot roll back an on-chain transfer or undo arbitrary application work.
- `settle_before_execute` is **not offered** in `0.2`. The `exact` scheme moves
  funds immediately and has no on-chain refund path; charging before the service
  is delivered creates an unacceptable failure mode. It can be reconsidered only
  together with a compensation/refund mechanism, or with a different scheme such
  as `upto` or escrow.

### 2. Payment identity and idempotent settlement

- The SDK exposes a stable `payment_id` derived from `(network, payer, nonce)` —
  the same identity the facilitator uses. It is not a random request id.
- A settlement retry reuses the **same** signed payload and the same
  `payment_id`. The SDK never rebuilds the authorization, changes the nonce, or
  asks the client to sign again because `/settle` timed out.
- Retries are allowed only for transport errors, timeouts, `429`, and `5xx`.
  `4xx` responses and `isValid=false` are definitive and are not retried.
- If the facilitator reports that the payment was already settled, the SDK treats
  it as success when it refers to the same `payment_id`.
- If the outcome remains unknown after the retry budget, the SDK returns `503`
  and logs the unresolved settlement. It does not execute the handler again.

### 3. Replay guard

Replay protection is enabled by default for every paid route.

- **Key:** `payment_id`, not the bare nonce. A nonce is unique per
  `(network, payer)`, not globally.
- **Store:** a `ReplayStore` protocol with atomic `reserve`, `mark_settled`,
  `release`, and `close` operations. The reservation must be atomic (`SET NX` or
  equivalent).
- **States:** `in_flight`, `settled`, `failed`.
- **Concurrent duplicate:** the second request is rejected with the replay error
  from ADR 0005 before `/verify` and before the handler runs.
- **Successful settlement:** the key remains until the authorization expires
  (`validBefore` plus clock skew), with a minimum TTL of
  `max_timeout_seconds + 5 minutes`.
- **Definitive invalid payment:** the reservation is released only after the
  facilitator rejects the payment; a new client attempt will use a new nonce.
- **Store unavailable:** fail closed with `503`. A payment must not proceed
  without replay protection in production.

The default in-memory store is for tests and single-process development only.
Production deployments with more than one worker **must** configure a shared
store (for example, Redis). The documentation and startup logs must state this
explicitly; an in-process dictionary is not replay protection across workers.

### 4. Facilitator failures and retries

- Retry on connection errors, timeouts, `429`, `502`, `503`, and `504`.
- Do not retry `400`, `401`, `403`, `404`, or `422`; these indicate a
  configuration, payload, or contract error.
- Use exponential backoff with jitter: three attempts by default, bounded by the
  per-request budget. Respect `Retry-After` when present.
- When the facilitator is unavailable after retries, return `503` with
  `Retry-After`; never `402`. A `402` tells the client to sign and pay again,
  which is wrong for an outage.
- Use one `httpx.AsyncClient` per process, created in the lifespan and closed on
  shutdown. Timeouts are explicit; redirects are disabled.
- A process-local circuit breaker per facilitator host opens after repeated
  failures and allows a single half-open probe. The breaker is an optimization,
  not a correctness mechanism; the replay store and facilitator idempotency are
  the correctness mechanisms.

### 5. Concurrency

- Two workers can race before either has settled. The shared atomic reservation
  is what prevents both from serving and settling; facilitator idempotency is the
  second line of defense.
- The SDK must not use a check-then-act sequence on the replay store.
- A second request that observes `in_flight` is rejected, not queued
  indefinitely.

## Alternatives

- **Default to settle-before-execute** — rejected: it charges for work that may
  never happen, with no on-chain rollback.
- **Rely only on the on-chain nonce** — rejected: the nonce prevents a second
  settlement, but not a second execution before settlement.
- **Key the replay guard by nonce only** — rejected: collisions across networks
  and payers.
- **Use an in-memory store in production** — rejected: it silently stops working
  behind multiple workers.
- **No retries** — rejected: a transient timeout becomes a failed payment.
- **Retry settlement with a new nonce** — rejected: that is a new payment and
  requires a new client signature.
- **Return paid content when settlement fails** — rejected: it gives away the
  resource and loses the merchant's money.

## Consequences

- (+) Failed settlement never returns paid content.
- (+) Transient facilitator failures become `503` and can be retried safely.
- (+) Replay protection works across workers when a shared store is configured.
- (+) Settlement retries do not double-charge.
- (−) The merchant must configure a shared store for production.
- (−) A handler can have side effects without a successful settlement; the
  merchant must make those effects idempotent or compensable.
- (−) Retries add latency when the facilitator is degraded.
- (−) Prepaid/expensive-operation pricing needs a different scheme or a separate
  compensation design.

## Acceptance criteria

1. Handler error → no `/settle` call and the original response is returned.
2. Settlement failure → no paid content and a safe payment error.
3. Settlement timeout → retry with the same `payment_id`, no handler re-run.
4. Duplicate `PAYMENT-SIGNATURE` → one execution and one settlement.
5. Two concurrent requests with the same payment → one wins, one is rejected.
6. Multi-worker test with a shared store → no double settlement.
7. Facilitator outage → `503` with `Retry-After`, never `402`.
8. Replay key TTL covers `validBefore` plus skew.

## Review triggers

1. The facilitator adds a refund, void, or settlement-status operation.
2. The `exact` scheme is replaced or supplemented by `upto`/escrow.
3. A merchant needs to charge before execution for a non-compensable operation.
4. The replay store becomes a meaningful operational bottleneck.
