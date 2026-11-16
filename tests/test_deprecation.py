"""Deprecation policy gates (ADR 0006 §5).

A deprecation is a process, not an edit: the deprecated name keeps working, emits
``DeprecationWarning`` at the call site, is documented, and has a removal version.
These tests are the infrastructure half of that policy — they make an accidental
or untested deprecation fail CI instead of appearing in a consumer's logs.
"""

from __future__ import annotations

import warnings

import pytest

import x402_sdk


def test_public_surface_emits_no_deprecation_warnings() -> None:
    """Reading the whole public surface must not warn.

    Anything in ``__all__`` is supported API. If an entry starts warning, it has
    to be moved behind an explicit, tested deprecation (README note, changelog
    ``Deprecated`` entry, removal version) rather than removed silently.
    """
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        for name in x402_sdk.__all__:
            getattr(x402_sdk, name)

    deprecated = [f"{w.filename}:{w.lineno}: {w.message}" for w in caught if issubclass(w.category, DeprecationWarning)]
    assert deprecated == [], deprecated


def test_deprecation_warnings_are_errors_in_the_test_suite() -> None:
    """The suite-level warning filter is part of the gate, not a convention.

    ``pyproject.toml`` sets ``error::DeprecationWarning``, so an untested
    deprecation breaks the run instead of scrollback. A deprecated API must be
    wrapped in ``pytest.warns(DeprecationWarning)`` (and documented) to ship.
    """
    with pytest.raises(DeprecationWarning):
        warnings.warn("policy probe: deprecation warnings must be errors", DeprecationWarning, stacklevel=2)
