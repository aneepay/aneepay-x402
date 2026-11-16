# Security Policy

Merchant-side x402 (exact, EVM) payment SDK for the AneePay facilitator. The SDK sits
in the request path of a paid HTTP endpoint and decides whether a request carries a
valid payment authorization, so its parsing and enforcement paths are security
boundaries.

## Supported versions

| Version | Supported          | Notes                                    |
| ------- | ------------------ | ---------------------------------------- |
| 0.1.x   | :white_check_mark: | Alpha. Security fixes only, best effort. |
| < 0.1.0 | :x:                | No fixes.                                |

The project is pre-1.0. The public API is not frozen: minor bumps may change
behaviour, and a fix may ship as a patch release without a deprecation window.

## Reporting a vulnerability

**Do not open a public issue.** Public reports give an attacker a working exploit
before users can upgrade.

Use GitHub private vulnerability reporting:

<https://github.com/aneepay/aneepay-x402/security/advisories/new>

If that form is unavailable, open a regular issue that contains **no exploit details**
and asks the maintainer to enable private reporting.

### What to include

- Affected version (`x402_sdk.__version__`) and Python version.
- Endpoint, route, and the `PaymentConfig` you used (redact the account UUID).
- The `PAYMENT-REQUIRED` / `PAYMENT-SIGNATURE` / `PAYMENT-RESPONSE` payloads, base64
  left encoded.
- Facilitator behaviour: version, URL, and whether `/verify` and `/settle` were reached.
- Impact in money terms if a payment could be settled, replayed, or skipped.

### Response

| Stage             | Target                                              |
| ----------------- | --------------------------------------------------- |
| Acknowledgement   | 72 hours                                            |
| Triage            | 7 days                                              |
| Fix or mitigation | Critical: 7 days. High: 30 days. Otherwise: 90 days |
| Public disclosure | With the fix release, or 90 days after triage       |

A report is confirmed when a released version contains the fix or a documented
mitigation. Credit is offered in the advisory unless you prefer otherwise.

## Scope

In scope:

- `src/x402_sdk/` — header codecs, `extra="forbid"` wire parsing, amount and recipient
  comparison, middleware enforcement order, the 402 response body, error text, and
  client resource handling.
- Anything that lets a request pass `require_payment` without a valid, correctly
  scoped authorization, or lets one authorization settle twice.
- The published `sdist` / `wheel` contents and the publish pipeline (tag/version
  mismatch, artifact substitution, missing integrity checks).

Out of scope:

- The AneePay facilitator service and any other AneePay component.
- Your merchant application, wallet, signer, reverse proxy, or deployment.
- `pay_to` addresses and token domain fields you choose to configure.
- Vulnerabilities that require an attacker to already control the merchant host.

## Known limitations, not vulnerabilities

These are documented in README -> _Behaviour and caveats_ and are accepted design
consequences. A report must show a path that escapes the documented behaviour.

- Settlement happens after your handler; the SDK has no refund or compensation path.
- A handler response with status >= 400 is passed through without settling.
- Only `accepts[0]` is enforced, even when the offer advertises more options.
- `amount` is compared as a string, so a numerically equal but differently formatted
  value is rejected locally.
- `FacilitatorError` text is echoed into the 402 body and header; treat it as
  sensitive and scrub it if your threat model requires.
- An unavailable facilitator produces 402, not 5xx.

## Security invariants

Do not break these in a pull request; each one is a reason a handler must not run
unpaid.

- The SDK never handles private key material. Signing happens in the client wallet.
- `token.name` and `token.version` are signed parameters. Copy them from the token
  contract, do not derive them from user input.
- `pay_to` must come from trusted configuration, never from request data.
- Amounts are built with `build_amount` / `Decimal`, never float arithmetic.
- `X-Account-Id` identifies the merchant account: keep it out of client-visible output.
- The facilitator URL is pinned configuration; serve it over TLS and monitor it.

The full rationale is in README -> _Security notes_.

## Disclosure

No embargo is required, but coordinate fixes: a public issue filed before the fix ships
helps nobody. Do not include working exploits in a PR or issue; send them privately.
