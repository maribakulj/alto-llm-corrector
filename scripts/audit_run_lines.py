"""Audit a real run's per-line output for invariant violations the guards cannot see.

`vision_benchmark.py --dump-lines` writes every
``(file, line_id, ocr, output, reference)`` tuple of a run. This reads that
dump and looks for the CLASS of defect rather than its instances — the
things `core.guards.check_line` is structurally blind to, because it
compares characters and has no notion of meaning:

* systematic character substitutions (the model "tidying up" the source);
* text migrating across a line boundary;
* digits, dates and amounts altered;
* negation removed;
* a line replaced by its neighbour's text.

Written after a real 522-line run where the aggregate CER looked excellent
while the model had erased the Fraktur double oblique hyphen U+2E17 on 34
of the 34 lines carrying one, and replaced U+2019 on all 69 occurrences —
together 16.5% of all residual error, and invisible to every guard because
one character in forty does not move a similarity ratio.

**Read the caveat in `--help` before trusting a count.** Several detectors
here have a high false-positive rate BY CONSTRUCTION, and one of them
cannot work at all outside a benchmark: telling a repaired digit from a
falsified one requires the ground truth, and in production there is none.

Usage::

    python scripts/vision_benchmark.py ... --dump-lines lines.json
    python scripts/audit_run_lines.py lines.json
    python scripts/audit_run_lines.py lines.json --config vision --show 8
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

#: French/German negation markers. Losing one inverts a sentence while
#: costing a handful of characters — the cheapest possible semantic
#: corruption, and one no similarity threshold can catch.
_NEG = re.compile(
    r"\bne\b|\bn['’]|\bpas\b|\bjamais\b|\baucun|\bplus\b|\bni\b|\bnicht\b|\bkein",
    re.I,
)
_DIGITS = re.compile(r"\d+")


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def systematic_substitutions(rows: list[dict]) -> list[tuple[str, int, int]]:
    """Characters the reference carries that the model never produced.

    The most valuable check here, and the one a per-line reading misses:
    a substitution applied to EVERY occurrence reads as a rounding error
    line by line and as a policy in aggregate. Returns
    ``(char, lost, ref_lines_carrying_it)`` sorted by loss.
    """
    lost: Counter[str] = Counter()
    carried: Counter[str] = Counter()
    for r in rows:
        out, ref = Counter(r["out"]), Counter(r["ref"])
        for ch, n in (ref - out).items():
            lost[ch] += n
        for ch in set(r["ref"]):
            carried[ch] += 1
    return [(ch, n, carried[ch]) for ch, n in lost.most_common()]


def audit(rows: list[dict]) -> dict[str, list[tuple[dict, str]]]:
    found: dict[str, list[tuple[dict, str]]] = {}

    def add(kind: str, row: dict, detail: str) -> None:
        found.setdefault(kind, []).append((row, detail))

    by_file: dict[str, list[dict]] = {}
    for r in rows:
        by_file.setdefault(r["file"], []).append(r)

    for lines in by_file.values():
        for i, r in enumerate(lines):
            ocr, out, ref = r["ocr"], r["out"], r["ref"]
            if out == ocr:
                continue  # untouched line: nothing to audit

            if levenshtein(out, ref) > levenshtein(ocr, ref):
                add("degraded_vs_gt", r, "output is further from the reference")

            # HIGH FALSE-POSITIVE RATE: real OCR turns letters into digits
            # constantly (`3an` → `Jan`), so most hits are correct repairs.
            # Only the ground truth separates the two — see the caveat.
            if _DIGITS.findall(ocr) != _DIGITS.findall(out):
                add(
                    "digits_changed",
                    r,
                    f"{_DIGITS.findall(ocr)} -> {_DIGITS.findall(out)}",
                )

            if len(_NEG.findall(out)) < len(_NEG.findall(ocr)):
                add("negation_reduced", r, "a negation marker disappeared")

            for off, tag in ((-1, "previous"), (1, "next")):
                j = i + off
                if 0 <= j < len(lines) and lines[j]["ocr"].strip():
                    if out.strip() == lines[j]["ocr"].strip():
                        add("neighbour_copy", r, f"identical to the {tag} line")

            # Boundary migration: a leading/trailing word changed sides while
            # the rest of the line survived. ALSO high false-positive — the
            # model legitimately drops OCR debris (`y`, `|`, `:`) this way.
            wo, wu = ocr.split(), out.split()
            if wo and wu and len(wo) - len(wu) >= 1:
                if wo[0] != wu[0] and ocr.endswith(wu[-1]):
                    add("head_word_lost", r, f"{wo[0]!r} gone")
                if wo[-1] != wu[-1] and ocr.startswith(wu[0]):
                    add("tail_word_lost", r, f"{wo[-1]!r} gone")

            if len(ocr) and len(out) / len(ocr) > 1.5:
                add("length_x1.5", r, f"{len(ocr)} -> {len(out)} chars")

            for ch in out:
                if unicodedata.category(ch) == "Cf":
                    add("invisible_char", r, f"U+{ord(ch):04X}")
                    break
                if ch.isalpha() and "LATIN" not in unicodedata.name(ch, "LATIN"):
                    add("non_latin_letter", r, unicodedata.name(ch, "?"))
                    break
    return found


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("dump", type=Path, help="JSON from --dump-lines")
    ap.add_argument("--config", default="vision", help="which config to audit")
    ap.add_argument("--show", type=int, default=5, help="examples per finding")
    args = ap.parse_args(argv)

    payload = json.loads(args.dump.read_text(encoding="utf-8"))
    if args.config not in payload:
        raise SystemExit(f"no config {args.config!r} — have: {', '.join(payload)}")
    rows = payload[args.config]
    changed = sum(1 for r in rows if r["out"] != r["ocr"])
    print(f"{len(rows)} lines audited, {changed} changed by the model\n")

    print("=== systematic substitutions (reference char never produced) ===")
    for ch, n, carried in systematic_substitutions(rows)[:8]:
        name = unicodedata.name(ch, "?")
        flag = "  <-- ALL of them" if carried and n >= carried else ""
        print(
            f"  {ch!r:>8} U+{ord(ch):04X} lost {n:>4}x, on {carried:>3} ref lines  {name}{flag}"
        )

    found = audit(rows)
    print("\n=== detectors ===")
    for kind in sorted(found, key=lambda k: -len(found[k])):
        print(f"  {kind:<20} {len(found[kind]):>4}")

    for kind in (
        "degraded_vs_gt",
        "negation_reduced",
        "neighbour_copy",
        "non_latin_letter",
        "invisible_char",
    ):
        items = found.get(kind, [])
        if not items:
            continue
        print(f"\n--- {kind} ({len(items)}) ---")
        for r, detail in items[: args.show]:
            print(f"  [{r['file']} {r['line_id']}] {detail}")
            print(f"    OCR : {r['ocr']!r}")
            print(f"    OUT : {r['out']!r}")
            print(f"    GT  : {r['ref']!r}")

    print(
        "\nCAVEAT — `digits_changed`, `head_word_lost` and `tail_word_lost` have a\n"
        "high false-positive rate by construction: real OCR turns letters into\n"
        "digits and prepends debris, so most hits are the model repairing it.\n"
        "Separating a repaired digit from a falsified one needs the ground truth.\n"
        "IN PRODUCTION THERE IS NONE — that class can be flagged for human review,\n"
        "never validated by the system."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
