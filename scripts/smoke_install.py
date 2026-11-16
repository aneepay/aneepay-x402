"""Installation smoke test for a built artifact (wheel or sdist).

Run this with the interpreter of a **clean** environment that installed only
``dist/*.whl`` or ``dist/*.tar.gz`` — never from the project checkout. It proves
that the artifact is complete on its own: imports resolve, ``py.typed`` ships, the
public surface is importable, the amount/offer/header path works without network,
and the runtime metadata does not leak development dependencies.

Usage:
    python scripts/smoke_install.py --expected-version 0.1.1
"""

from __future__ import annotations

import argparse
import base64
import importlib.resources
import sys
from importlib.metadata import requires
from importlib.util import find_spec
from uuid import UUID

import x402_sdk
from x402_sdk import (
    PaymentConfig,
    TokenConfig,
    build_payment_required,
    build_resource_info,
    decode_payment_signature_header,
    encode_payment_required_header,
    require_payment,
)

ARTIFACT_NAME = "aneepay-x402"
_RUNTIME_PACKAGES = ("httpx", "pydantic", "starlette")


def require(condition: bool, message: str) -> None:
    """Abort the smoke test with ``message`` when ``condition`` is false."""
    if not condition:
        raise SystemExit(f"smoke install failed: {message}")


def check_public_surface() -> None:
    """Every name in ``__all__`` must be importable and not ``None``."""
    missing = sorted(name for name in x402_sdk.__all__ if getattr(x402_sdk, name, None) is None)
    require(not missing, f"public names missing from the installed package: {missing}")


def check_typed_marker() -> None:
    """The wheel must ship ``py.typed`` (PEP 561)."""
    marker = importlib.resources.files("x402_sdk").joinpath("py.typed")
    require(marker.is_file(), "py.typed is missing from the installed package")


def check_metadata_has_no_dev_dependencies() -> None:
    """Runtime requirements must not include test/lint tooling."""
    declared = requires(ARTIFACT_NAME)
    require(declared is not None, "installed distribution declares no requirements")
    runtime = [line for line in declared if "extra ==" not in line]
    leaked = sorted(line for line in runtime if any(tool in line for tool in ("pytest", "ruff", "pyright")))
    require(not leaked, f"development dependencies leaked into runtime metadata: {leaked}")


def check_runtime_dependencies_import() -> None:
    """Every declared runtime dependency must be importable in the clean env."""
    unavailable = [name for name in _RUNTIME_PACKAGES if find_spec(name) is None]
    require(not unavailable, f"runtime dependencies are not importable: {unavailable}")


def check_offline_payment_flow() -> None:
    """Build an offer and round-trip a header with no facilitator involved."""
    config = PaymentConfig(
        facilitator_url="http://facilitator.test",
        account_id=UUID("00000000-0000-4000-8000-000000000001"),
        network="eip155:31337",
        pay_to="0x" + "ab" * 20,
        token=TokenConfig(address="0x" + "cd" * 20, decimals=6, name="USD Coin"),
    )
    offer = build_payment_required(
        config,
        price="0.01",
        resource=build_resource_info(config, resource_url="http://merchant.test/premium"),
    )
    require(offer.accepts[0].amount == "10000", f"unexpected atomic amount: {offer.accepts[0].amount}")

    header = encode_payment_required_header(offer)
    decoded = base64.b64decode(header)
    require(b'"x402Version":2' in decoded, "PAYMENT-REQUIRED header is not compact wire JSON")

    # A malformed client header must fail as an SDK error, not a raw ValueError.
    try:
        decode_payment_signature_header("not-base64")
    except x402_sdk.PaymentError:
        pass
    else:
        raise SystemExit("smoke install failed: malformed PAYMENT-SIGNATURE did not raise PaymentError")

    require(callable(require_payment), "require_payment is not callable")


def main(argv: list[str] | None = None) -> int:
    """Run every smoke check and report the installed artifact."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-version", required=True, help="version read from __init__.py")
    args = parser.parse_args(argv)

    require(
        x402_sdk.__version__ == args.expected_version,
        f"installed __version__ {x402_sdk.__version__} != expected {args.expected_version}",
    )
    check_public_surface()
    check_typed_marker()
    check_metadata_has_no_dev_dependencies()
    check_runtime_dependencies_import()
    check_offline_payment_flow()

    sys.stdout.write(
        f"smoke install ok: {ARTIFACT_NAME} {x402_sdk.__version__} ({', '.join(_RUNTIME_PACKAGES)} importable)\n",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
