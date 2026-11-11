# 0004. Wire contract ownership, vendoring and contract tests

- **Status:** Accepted
- **Date:** 2026-11-11
- **Related:** [0001](0001-merchant-sdk-layers.md), [0003](0003-bootstrap-and-configuration.md), [0006](0006-versioning-and-support.md)

## Context

`aneepay-x402` is an open, self-contained package. It must not import code from
AneePay's services, and it must remain installable and testable on its own. At
the same time, it speaks the x402 v2 wire contract served by the AneePay
facilitator at aneepay.com.

The schemas are therefore vendored: `x402_sdk.schemas` is a deliberate copy of
the public wire shapes, with camelCase aliases on the wire and snake_case fields
in Python. A copy can drift. Without a pin, a facilitator-side change either
breaks production silently or forces every merchant to upgrade immediately.

A second tension is strictness. `extra="forbid"` catches typos and accidental
protocol changes, but it also means that a new, additive facilitator field breaks
every paid request in production. A payment SDK must be strict about what it
sends and tolerant about what it receives.

## Decision

### 1. Source of truth and ownership

- The x402 v2 specification and the public AneePay facilitator API at
  aneepay.com are the source of truth for the wire contract.
- AneePay owns the wire contract. The SDK does not add protocol fields and does
  not reinterpret the protocol in the framework layer.
- The SDK supports **v2 only** in `0.2`. A v1 adapter is a separate decision and
  is not implemented; accepting v1 would double the schema and test surface.
- Protocol extensions are carried through the existing `extensions` map. A
  framework-layer feature must not invent a new top-level wire field.

### 2. Vendored schemas

- `x402_sdk.schemas` is the only wire model layer. It has no imports from
  AneePay services and no generated code at import time.
- Python fields are snake_case; wire aliases are camelCase. `to_wire()` is the
  single serialization point and drops `None` values.
- Constants such as `X402_VERSION = 2`, `SCHEME_EXACT = "exact"`, and the
  `PAYMENT-*` header names live next to the schemas.
- The package ships `py.typed`; the public models and helpers are exported from
  `x402_sdk.__all__`.

### 3. Strictness policy

The policy is asymmetric:

| Direction | Policy |
| --- | --- |
| SDK-generated outbound objects | `extra="forbid"` — a typo must fail before the request leaves the process |
| Client-originated objects that are forwarded | preserve unknown fields — never drop data the facilitator may need |
| Facilitator responses | `extra="ignore"` — an additive field must not break a payment |

Implementation rules:

- Models used in `PAYMENT-SIGNATURE` and forwarded to `/verify` or `/settle`
  must preserve unknown keys, either with `extra="allow"` or by forwarding the
  original decoded JSON alongside the model.
- Models parsed from facilitator responses must ignore unknown keys.
- `PaymentRequirements.extra` is scheme data and stays open; the SDK does not
  strip keys it does not recognize.
- A model must not silently coerce a wrong type. In particular, amounts are
  strings of integer atomic units, never floats.

### 4. Contract tests

`tests/test_wire_contract.py` is the pin. It is not an ordinary unit test; a
failure means the wire contract changed.

It must cover:

- exact camelCase keys and aliases for every public model;
- required and optional fields;
- literal values `x402Version == 2` and `scheme == "exact"`;
- header names `PAYMENT-REQUIRED`, `PAYMENT-SIGNATURE`, `PAYMENT-RESPONSE`;
- base64 encoding/decoding of headers, including malformed input;
- amount as a decimal string in atomic units;
- success and failure shapes for `/verify` and `/settle`;
- `to_wire()` output: aliases, dropped `None`, no unexpected keys;
- additive unknown fields: preserved when forwarded, ignored in responses;
- golden fixtures for `/x402/merchant` and `/x402/supported`.

A schema change and its contract-test update land in the same change. The test
must not be weakened to make an incompatible change pass.

### 5. Updating the snapshot

- **Additive facilitator change** (new optional response field): the SDK should
  keep working without a release because responses ignore unknown fields. The
  snapshot and fixtures are updated in the next release.
- **Additive client field** that must reach the facilitator: the forwarded
  payload must preserve it; no SDK release is required for pass-through.
- **Breaking change** (renamed/removed field, changed meaning, new required
  field): requires a new major version, or for `0.x`, a minor with an explicit
  migration note. There is no silent break.
- **Protocol version change:** `X402_VERSION` changes only with a new wire
  version. v1 and v2 are not mixed in one code path.

The update is a reviewed, manual change: the vendored diff, the contract test,
and the changelog are reviewed together. There is no automatic import from any
external repository.

### 6. Seam test against the published artifact

The integration seam is tested against the **built artifact**, not the source
tree:

1. build the wheel and sdist;
2. install the wheel in a clean environment;
3. run the 402 → verify → handler → settle → `PAYMENT-RESPONSE` flow using only
   the public API;
4. repeat for the sdist;
5. run the contract test against the installed package.

The seam test proves that what consumers install from PyPI is what was tested.
It must not import from the source checkout or rely on editable installs.

### 7. Documentation

- The wire reference in the README is generated from the same models where
  practical; otherwise it is reviewed with the contract test.
- Every public wire model has a docstring describing its wire keys and whether
  unknown keys are preserved or ignored.
- A failure mode caused by an additive field is a bug in the SDK, not in the
  facilitator.

## Alternatives

- **Import a shared schema package from AneePay** — rejected: the open package
  would depend on a non-public source, breaking installability and the
  self-contained guarantee.
- **Generate schemas automatically from the specification** — deferred: the
  tooling is not mature enough for a stable public package; manual vendoring
  plus contract tests is predictable.
- **Use `extra="forbid"` everywhere** — rejected: an additive facilitator field
  would break production payments.
- **Use `extra="allow"` everywhere** — rejected: it hides typos in
  SDK-generated requests and weakens the outbound contract.
- **Support v1 and v2 simultaneously** — rejected for `0.2`: it doubles the
  matrix and there is no confirmed v1 consumer.
- **Test only the source tree** — rejected: packaging errors and missing files
  would reach PyPI undetected.

## Consequences

- (+) The SDK stays installable without any dependency on AneePay services.
- (+) Additive facilitator fields do not break merchants.
- (+) Drift is caught by a focused contract test.
- (+) The published artifact is tested as consumers receive it.
- (−) The schema snapshot is maintained manually.
- (−) A breaking wire change still requires an SDK release and a migration note.
- (−) Unknown-field handling is more nuanced than a single Pydantic setting and
  must be tested per model.

## Acceptance criteria

1. Every public wire model is covered by the contract test.
2. Additive unknown fields are preserved on forwarded payloads and ignored on
   responses.
3. `to_wire()` output is exact for success and failure fixtures.
4. Malformed base64, wrong version, wrong scheme, and unknown required fields
   produce clear errors.
5. The wheel and sdist seam tests pass in a clean environment.
6. No module in `x402_sdk` imports from AneePay services; every non-standard
   import is a public PyPI package declared in `pyproject.toml`.
7. The README wire reference matches the models.

## Review triggers

1. x402 publishes a new wire version.
2. The facilitator introduces a breaking schema change.
3. Automatic schema generation becomes mature enough to replace manual
   vendoring.
4. A consumer needs v1 compatibility.
5. Additive changes become frequent enough that the release cadence hurts.
