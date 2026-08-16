#!/usr/bin/env python3
"""Smoke check that the saknussemm public API is importable.

Single source of truth shared between three CI/release contexts so the
import lists never drift apart again (roadmap L5 / B6):

  - ``.github/workflows/ci.yml`` (saknussemm-build job)
  - ``.github/workflows/publish-saknussemm.yml``
  - ``scripts/release-saknussemm.sh``

When the public surface changes (a symbol added to or removed from
``saknussemm.__all__``), edit THIS file. The three contexts above
invoke it as a script and inherit any change automatically.

Exit status:
  - 0 if every symbol in ``saknussemm.__all__`` resolves to a non-None object.
  - non-zero on import error or missing symbol (raises directly — let
    the traceback surface so an operator sees what broke).
"""

from __future__ import annotations

import sys


def main() -> int:
    import saknussemm

    # The contract is `saknussemm.__all__`: every name listed there MUST
    # be importable from the top-level package. Iterating the list
    # avoids the maintenance burden of restating the names below.
    missing: list[str] = []
    none_valued: list[str] = []
    for name in saknussemm.__all__:
        if not hasattr(saknussemm, name):
            missing.append(name)
            continue
        if getattr(saknussemm, name) is None:
            none_valued.append(name)

    if missing or none_valued:
        print(
            f"saknussemm smoke FAILED for version {saknussemm.__version__}",
            file=sys.stderr,
        )
        if missing:
            print(f"  missing attributes: {missing}", file=sys.stderr)
        if none_valued:
            print(f"  attributes resolved to None: {none_valued}", file=sys.stderr)
        return 1

    print(
        f"smoke ok: saknussemm {saknussemm.__version__} "
        f"({len(saknussemm.__all__)} public symbols)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
