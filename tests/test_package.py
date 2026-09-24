"""Smoke tests for the package skeleton."""

from __future__ import annotations

import x402_sdk


def test_version_is_exposed() -> None:
    assert x402_sdk.__version__


def test_package_name() -> None:
    assert x402_sdk.__name__ == "x402_sdk"
