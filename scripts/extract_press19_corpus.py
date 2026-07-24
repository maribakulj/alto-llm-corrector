"""Extract a clean-text calibration corpus from a paired ALTO GT dataset.

The QE calibration for 19th-c. press (``scripts/fit_qe_calibration.py``)
needs CLEAN target-register text, one line per line. Until now it ran on
an 18-line hand-written pastiche, which is why the shipped constants are
marked PROVISIONAL. This derives the same kind of file from a REAL
ground-truth corpus (e.g. the BNL 19th-c. Luxembourg press GT: paired
``NNNN.xml`` ALTO + ``NNNN.png``), so the fit sees genuine period press.

Four filters, each for a measured reason (counts below are for the BNL
37-page set, 522 lines):

* **language** — the corpus is BILINGUAL (Luxembourg press: 312 French /
  140 German / 70 undecided lines; 23 French-dominant pages vs 12 German).
  Calibrating a FRENCH model (CamemBERT) on German text would inflate its
  surprisal on clean input and corrupt the Platt midpoint, so lines are
  kept only when they show the requested language's evidence. Detection is
  a dependency-free function-word score plus orthographic markers
  (``äöüß``, and the ``⸗`` Fraktur double hyphen) — the core's own
  no-heavy-deps rule applied to tooling.
* **hyphenation** — 127 lines are hyphen-unit members: their text is a
  word fragment (``D'un jugement contradic-``). A masked LM scoring a
  truncated word measures the truncation, not the language, so both parts
  are dropped rather than joined (joining would fabricate a line the OCR
  never had — the library never merges lines, and neither does its
  tooling).
* **length** — very short lines (``sie.``, ``Wiltz;``, ``Quart.``) carry
  almost no linguistic signal to be surprised by.
* **digits** — stock quotes and tables (``April 30⅙ bez.``, ``19694 74``)
  are register noise for a language model.

The GT text is used VERBATIM: no normalisation, no modernisation. Period
orthography is never an error (ROADMAP rule 3), and the calibration must
see exactly what the scorer will see at runtime. Note the extracted units
are OCR *lines*, not sentences — which is the right shape here, because
the QE scorer scores lines at runtime too.

Usage::

    python scripts/extract_press19_corpus.py \\
        --corpus /path/to/"37 GT BNL" --lang fr --out scripts/data/press19_bnl.txt
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "packages" / "corrigenda" / "src"))

from corrigenda.core.schemas import HyphenRole  # noqa: E402
from corrigenda.formats.alto.parser import build_document_manifest  # noqa: E402

#: Function words that betray the language of a line. Deliberately small
#: and high-frequency: the goal is a robust per-line vote, not full
#: language identification.
FRENCH_MARKERS = frozenset(
    """le la les de des du et à en un une qui que dans pour sur est ont été
    aux par ne pas plus au ce cette il elle nous vous leur son sa ses avec
    sans sous entre ainsi mais où dont tout tous cet nos vos""".split()
)
GERMAN_MARKERS = frozenset(
    """der die das und den dem des ist nicht werden auch sich von zu mit
    für ein eine im am dass es er sie wir haben wird sein oder aber nach
    bei über durch nur noch wie zur zum""".split()
)
#: Characters that appear in German/Fraktur print but not in French.
GERMAN_CHARS = "äöüßÄÖÜ⸗"

_STRIP = ".,;:!?»«()[]{}'’\"„“-–—"


def language_of(text: str) -> str:
    """Return ``"fr"``, ``"de"`` or ``"?"`` for one line.

    A function-word vote, with German orthographic markers weighted (they
    are decisive: no French word carries ``ß`` or ``ä``). ``"?"`` means no
    evidence either way — a short or name-only line — and callers should
    treat it as unusable rather than guess.
    """
    words = [w.strip(_STRIP).lower() for w in text.split()]
    french = sum(1 for w in words if w in FRENCH_MARKERS)
    german = sum(1 for w in words if w in GERMAN_MARKERS)
    german += 2 * sum(1 for c in text if c in GERMAN_CHARS)
    if french > german:
        return "fr"
    if german > french:
        return "de"
    return "?"


def digit_ratio(text: str) -> float:
    return sum(c.isdigit() for c in text) / len(text) if text else 0.0


def extract_lines(
    corpus_dir: Path,
    *,
    lang: str = "fr",
    min_words: int = 5,
    max_digit_ratio: float = 0.2,
) -> tuple[list[str], dict[str, int]]:
    """Return ``(kept_lines, rejection_counts)`` for every ``*.xml`` in
    ``corpus_dir``, applying the four documented filters."""
    kept: list[str] = []
    stats = {
        "total": 0,
        "hyphen_part": 0,
        "wrong_language": 0,
        "too_short": 0,
        "digit_heavy": 0,
        "kept": 0,
    }
    for xml in sorted(corpus_dir.glob("*.xml")):
        doc = build_document_manifest([(xml, xml.name)])
        for page in doc.pages:
            for line in page.lines:
                stats["total"] += 1
                text = line.ocr_text.strip()
                if line.hyphen_role is not HyphenRole.NONE:
                    stats["hyphen_part"] += 1
                    continue
                if len(text.split()) < min_words:
                    stats["too_short"] += 1
                    continue
                if digit_ratio(text) > max_digit_ratio:
                    stats["digit_heavy"] += 1
                    continue
                if language_of(text) != lang:
                    stats["wrong_language"] += 1
                    continue
                kept.append(text)
                stats["kept"] += 1
    return kept, stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--corpus",
        type=Path,
        required=True,
        help="directory of ALTO ground-truth *.xml (paired scans optional)",
    )
    parser.add_argument("--lang", default="fr", choices=["fr", "de"])
    parser.add_argument("--min-words", type=int, default=5)
    parser.add_argument("--max-digit-ratio", type=float, default=0.2)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    lines, stats = extract_lines(
        args.corpus,
        lang=args.lang,
        min_words=args.min_words,
        max_digit_ratio=args.max_digit_ratio,
    )
    if not lines:
        raise SystemExit(f"no usable {args.lang} lines under {args.corpus}")

    payload = "\n".join(lines) + "\n"
    if args.out:
        args.out.write_text(payload, encoding="utf-8")
        print(f"wrote {len(lines)} lines to {args.out}")
    else:
        sys.stdout.write(payload)
    for key, value in stats.items():
        print(f"  {key}: {value}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
