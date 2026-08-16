#!/usr/bin/env python3
"""Smoke check that the lidenbrock public API is importable.

Single source of truth shared between three CI/release contexts so the
import lists never drift apart again (roadmap L5 / B6):

  - ``.github/workflows/ci.yml`` (lidenbrock-build job)
  - ``.github/workflows/publish-lidenbrock.yml``
  - ``scripts/release-lidenbrock.sh``

When the public surface changes (a symbol added to or removed from
``lidenbrock.__all__``), edit THIS file. The three contexts above
invoke it as a script and inherit any change automatically.

Exit status:
  - 0 if every symbol in ``lidenbrock.__all__`` resolves to a non-None object.
  - non-zero on import error or missing symbol (raises directly — let
    the traceback surface so an operator sees what broke).
"""

from __future__ import annotations

import sys


def main() -> int:
    import lidenbrock

    # The contract is `lidenbrock.__all__`: every name listed there MUST
    # be importable from the top-level package. Iterating the list
    # avoids the maintenance burden of restating the names below.
    missing: list[str] = []
    none_valued: list[str] = []
    for name in lidenbrock.__all__:
        if not hasattr(lidenbrock, name):
            missing.append(name)
            continue
        if getattr(lidenbrock, name) is None:
            none_valued.append(name)

    if missing or none_valued:
        print(
            f"lidenbrock smoke FAILED for version {lidenbrock.__version__}",
            file=sys.stderr,
        )
        if missing:
            print(f"  missing attributes: {missing}", file=sys.stderr)
        if none_valued:
            print(f"  attributes resolved to None: {none_valued}", file=sys.stderr)
        return 1

    print(
        f"smoke ok: lidenbrock {lidenbrock.__version__} "
        f"({len(lidenbrock.__all__)} public symbols)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
