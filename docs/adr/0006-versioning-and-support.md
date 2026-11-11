# 0006. Versioning, support matrix and deprecation

- **Status:** Accepted
- **Date:** 2026-11-11
- **Related:** [0001](0001-merchant-sdk-layers.md), [0004](0004-wire-contract-vendoring.md)

## Context

The package is at `0.1.0` with `Development Status :: 3 - Alpha`. It already has
external consumers, a public `__all__`, a `py.typed` marker, and a documented
wire contract. The README describes behaviour, but there is no changelog, no
formal deprecation policy, no lower-bound dependency testing, and an incomplete
Python matrix.

Without explicit rules, `0.x` becomes an excuse for silent breaks, and `1.0`
becomes a marketing label rather than a compatibility promise. The SDK needs a
predictable upgrade story before the framework layer ships.

## Decision

### 1. Semantic versioning

- The package follows SemVer: `MAJOR.MINOR.PATCH`.
- **Public API** is defined by ADR 0001: the framework layer is the primary
  contract; core primitives are public but marked advanced.
- During `0.x`:
  - a **minor** release may contain breaking changes, but they must be listed
    under `Changed`/`Removed` in the changelog with a migration note;
  - a **patch** release never contains a breaking change;
  - a breaking change is never published silently.
- From `1.0` onward, breaking changes require a major release.
- Pre-release identifiers (`0.2.0b1`, `1.0.0rc1`) are used for release
  candidates. Published versions are immutable; a broken release is yanked, not
  overwritten.

### 2. Version source and tagging

- `src/x402_sdk/__init__.py:__version__` is the single source of truth; the
  build backend reads it.
- Git tags use `vX.Y.Z` and match the package version.
- A release is built from a clean checkout, not from a dirty working tree.
- The wheel and sdist are both published; the installed wheel is smoke-tested
  before upload.

### 3. Python support

`0.2.0` moves the supported range to **Python 3.11–3.14**:

- Python 3.10 reached end of life in October 2026 and is not a supported runtime
  for a payment SDK.
- `requires-python` becomes `>=3.11`.
- CI runs the full test suite on 3.11, 3.12, 3.13, and 3.14.
- The classifiers and README are updated in the same release.

Removing 3.10 is a breaking change, which is allowed in a `0.x` minor and is
recorded in the changelog. Keeping an EOL interpreter would force the SDK to
carry compatibility code with no security support.

### 4. Dependency policy

Runtime dependencies are intentionally few:

- `httpx>=0.27,<1`
- `pydantic>=2.6,<3`
- `starlette>=0.37,<1`

Optional extras:

- `fastapi>=0.115,<1` for `x402_sdk.fastapi`
- the MCP SDK range pinned by the MCP layer when it ships

Rules:

- Lower bounds are supported and tested; upper bounds prevent a surprise major
  upgrade.
- The library does not pin exact versions; the application owns the lockfile.
- CI runs at least two combinations: lowest supported versions and latest
  allowed versions.
- Optional dependencies are imported only inside their extra module. A missing
  extra raises an `ImportError` with the install hint (`pip install
  aneepay-x402[fastapi]`), not a bare `ModuleNotFoundError` at package import.
- A dependency major upgrade is a minor release of the SDK, with CI evidence and
  a changelog entry.
- No runtime dependency may add a post-install script or a native build step
  without an explicit decision.

### 5. Deprecation policy

- A public API is deprecated with:
  - a `DeprecationWarning` at the call site;
  - a docstring and README note;
  - a `Deprecated` changelog entry with the replacement;
  - a removal version.
- The deprecation window is at least one minor release and at least 90 days,
  whichever is longer. Security fixes may shorten it with an advisory.
- A deprecated name keeps working during the window; it is not a silent alias
  that changes behavior.
- `require_payment` is not removed before `1.0`. After `1.0`, it gets one minor
  deprecation window and is removed in the next major.
- Renames follow the same rule: the old name remains as a warning-emitting
  alias for at least one minor.

### 6. Support window

- The latest minor receives full fixes.
- The previous minor receives security fixes only.
- Older minors require an upgrade.
- A Python or dependency end-of-life triggers a minor or major release,
  whichever SemVer requires, with a migration note.

### 7. `1.0` criteria

`1.0` is an API-stability promise, not a feature-completeness claim. It requires:

1. the FastAPI framework layer is implemented and covered by the scenario tests
   in ADR 0002 and ADR 0005;
2. at least one external merchant has run it in production for at least one
   month with real settlements;
3. replay protection works with a shared store across workers;
4. the error and HTTP mapping is stable and documented;
5. OpenAPI and `/.well-known/x402` are stable;
6. type checking, linting, coverage, and lowest-bound dependency tests are
   enforced in CI;
7. `CHANGELOG.md`, `SECURITY.md`, and the support policy are published;
8. there are no known critical security issues.

`1.0` does not wait for MCP, multi-network offers, metered pricing, or SDKs in
other languages.

### 8. Release and quality gates

Every release must pass:

- `ruff check` and `ruff format --check`;
- a strict type check (`pyright` or `mypy`) for public modules;
- the full pytest suite, offline;
- the wire contract test;
- the clean-wheel and clean-sdist installation tests;
- the lowest and latest dependency matrices;
- a build check (`twine check` or equivalent);
- a changelog entry.

Recommended coverage floor: 90% for core modules; the framework layer is covered
by end-to-end scenario tests rather than a single line-coverage number.

Security releases use a patch version, a `SECURITY.md` advisory, and a
coordinated disclosure window. The changelog links the advisory without
publishing exploit details before the fix is available.

### 9. Changelog

- `CHANGELOG.md` follows Keep a Changelog and SemVer.
- Sections: `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, `Security`.
- Every public change has an entry, including documentation-only changes that
  affect integration.
- The unreleased section is maintained in the same change as the code; the
  release commit only moves it under the version and date.

## Alternatives

- **Calendar versioning** — rejected: consumers need compatibility semantics,
  not release dates.
- **Keep supporting Python 3.10** — rejected: it is EOL and adds maintenance
  cost with no security support.
- **No upper bounds on dependencies** — rejected: a major dependency release
  would break consumers without an SDK release.
- **Remove deprecated APIs in the next patch** — rejected: it breaks the
  compatibility promise.
- **Declare `1.0` when the feature list is complete** — rejected: `1.0` means
  the public contract is stable; features can follow.
- **Support every minor forever** — rejected: it makes security maintenance
  unbounded.

## Consequences

- (+) Consumers get a predictable upgrade and deprecation story.
- (+) The CI matrix catches drift in Python and dependency versions.
- (+) `1.0` has measurable criteria instead of a date.
- (−) CI is slower and more expensive.
- (−) Dropping Python 3.10 is a breaking change for `0.x` consumers.
- (−) Deprecation windows and changelog discipline add process overhead.
- (−) Supporting only the latest two minors may force upgrades.

## Acceptance criteria

1. `requires-python`, classifiers, and CI matrix agree on Python 3.11–3.14.
2. CI tests the lowest and latest dependency bounds.
3. `CHANGELOG.md` exists and has an `Unreleased` section.
4. A deprecated API emits `DeprecationWarning` in a test.
5. A clean wheel and sdist install and pass the smoke test.
6. The `1.0` checklist is tracked and linked from the README or release notes.
7. No release is cut from a dirty tree or with a mismatched tag.

## Review triggers

1. A new Python minor or a Python EOL date approaches.
2. A runtime dependency publishes a new major.
3. An external consumer needs a longer support window.
4. The `1.0` criteria are met or need revision.
5. MCP or multi-network support changes the public surface.
