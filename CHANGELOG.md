# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
During `0.x`, a **minor** release may break the public API (with a migration note);
a **patch** release never does. See
[ADR 0006](docs/adr/0006-versioning-and-support.md).

## [Unreleased]

## [0.1.1] - 2026-11-16

Engineering gates only: the library behaves exactly as `0.1.0` did, and the wire
contract test is unchanged.

### Added

- `CHANGELOG.md` following Keep a Changelog, with a maintained `Unreleased`
  section (ADR 0006 §9).
- Strict `pyright` type checking of `src/x402_sdk/**` in CI and in the release
  workflow (ADR 0006 §8).
- Coverage gate: `pytest-cov` with a 90% floor for the shipped modules. `uv run
  pytest` now always reports coverage, so local runs match CI.
- Dependency-bounds matrix in CI: the lowest supported versions of every
  dependency and the latest allowed versions are both tested.
- Clean wheel and sdist installation smoke tests in `publish.yml`, before the
  upload — the installed package is imported and its public surface exercised
  from the built artifacts, not from the checkout.
- `tests/test_deprecation.py`: enforces that the public API emits no
  `DeprecationWarning` and that deprecation warnings are errors in the suite
  (infrastructure for the ADR 0006 §5 policy).

### Changed

- Wire schemas declare camelCase names as `serialization_alias` /
  `validation_alias` instead of `alias`, so type checkers see the python field
  names in model constructors while the wire format stays camelCase. No wire
  output change; the contract test is untouched.
- `build_requirements` passes a `PaymentRequirementsExtra` instance instead of a
  plain dict; the serialized requirements are identical.
- Dev extra lower bounds raised to a combination that resolves:
  `pytest>=8.2` and `pytest-asyncio>=0.24` (pytest-asyncio `0.23.x` requires
  `pytest<8`, so the previous floor could not be installed together).
- Release workflow and quality workflow share the pinned uv version and run the
  same gates.
- `__version__` is `0.1.1`.

### Fixed

- `ruff format --check` drift in the ADR 0001 / ADR 0003 Python code samples.

## [0.1.0]

Initial public release: x402 wire v2 (`exact` scheme, EVM), `PaymentConfig`,
offer builders, header codecs, `require_payment` middleware, and the facilitator
client.

[Unreleased]: https://github.com/aneepay/aneepay-x402/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/aneepay/aneepay-x402/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/aneepay/aneepay-x402/releases/tag/v0.1.0
