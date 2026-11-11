# ADR — Architecture Decision Records

Decisions that define the public contract of the `aneepay-x402` package.

| ADR | Decision |
| --- | --- |
| [0001](0001-merchant-sdk-layers.md) | Merchant SDK x402: two layers — protocol core and framework integrations |
| [0002](0002-settlement-replay-idempotency.md) | Settlement, replay protection and idempotency |
| [0003](0003-bootstrap-and-configuration.md) | Bootstrap and configuration contract |
| [0004](0004-wire-contract-vendoring.md) | Wire contract ownership, vendoring and contract tests |
| [0005](0005-error-model-and-observability.md) | Error model, HTTP responses and observability |
| [0006](0006-versioning-and-support.md) | Versioning, support matrix and deprecation |
| [0007](0007-security-and-trust-model.md) | Security and trust model |

MCP is deliberately not an ADR yet: the layer is deferred by ADR 0001, and a
new decision record will be written only when it is unblocked.

The x402 wire contract is owned by AneePay (aneepay.com). This repository vendors the
public schemas and pins them with a contract test.
