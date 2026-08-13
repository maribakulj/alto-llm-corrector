"""Calibration-corpus extractor (scripts/extract_press19_corpus.py).

Offline: builds tiny ALTO fixtures in tmp_path rather than needing the real
(uncommitted) ground-truth scans. Pins the four filters that make a
bilingual, hyphen-broken newspaper GT usable as CLEAN calibration text for
one language's model.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from tests._paths import REPO

_REPO_ROOT = REPO
_SCRIPT = _REPO_ROOT / "scripts" / "extract_press19_corpus.py"

_spec = importlib.util.spec_from_file_location("extract_press19_corpus", _SCRIPT)
assert _spec and _spec.loader
ex = importlib.util.module_from_spec(_spec)
sys.modules["extract_press19_corpus"] = ex
_spec.loader.exec_module(ex)


# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------


def test_language_of_french():
    assert ex.language_of("de l’entente de l’Autriche et de la Russie") == "fr"
    assert ex.language_of("On me dit aujourd’hui que tout ce qui s’est") == "fr"


def test_language_of_german():
    assert ex.language_of("Das bischöfliche Ordinariat der Diözese") == "de"
    assert ex.language_of("Genehmigung nachgesucht werde und das ist") == "de"


def test_german_orthography_outweighs_a_stray_french_word():
    """``ä``/``ß``/``⸗`` are decisive — no French word carries them, so a
    line with German spelling is not misread as French because it happens
    to contain 'de' (a German word too)."""
    assert ex.language_of("de Ober⸗Cammandant Athenäum") == "de"


def test_language_of_undecidable_is_neither():
    assert ex.language_of("Pierre Bourgmeyer Fautsch") == "?"


def test_digit_ratio():
    assert ex.digit_ratio("") == 0.0
    assert ex.digit_ratio("19694 74") > 0.5
    assert ex.digit_ratio("le cabinet de Vienne") == 0.0


# ---------------------------------------------------------------------------
# extract_lines — the four filters, on a fixture page
# ---------------------------------------------------------------------------

_ALTO_HEAD = """<?xml version="1.0" encoding="UTF-8"?>
<alto xmlns="http://www.loc.gov/standards/alto/ns-v4#">
  <Description><MeasurementUnit>mm10</MeasurementUnit></Description>
  <Layout>
    <Page ID="P_0001" PHYSICAL_IMG_NR="1"><PrintSpace><TextBlock ID="TB_1">
"""
_ALTO_TAIL = """    </TextBlock></PrintSpace></Page>
  </Layout>
</alto>
"""


def _line_xml(idx: int, text: str, *, vpos: int) -> str:
    strings = []
    hpos = 10
    for word in text.split():
        safe = word.replace("&", "&amp;").replace("<", "&lt;").replace('"', "&quot;")
        strings.append(
            f'<String CONTENT="{safe}" CC="00" HPOS="{hpos}" '
            f'VPOS="{vpos}" WIDTH="40" HEIGHT="20"/>'
        )
        hpos += 50
    body = "<SP/>".join(strings)
    return (
        f'      <TextLine ID="TL_{idx:04d}" HPOS="10" VPOS="{vpos}" '
        f'WIDTH="600" HEIGHT="20">{body}</TextLine>\n'
    )


def _write_alto(path: Path, texts: list[str]) -> Path:
    body = "".join(
        _line_xml(i, t, vpos=100 + 30 * i) for i, t in enumerate(texts, start=1)
    )
    path.write_text(_ALTO_HEAD + body + _ALTO_TAIL, encoding="utf-8")
    return path


def test_extract_keeps_only_target_language(tmp_path: Path):
    _write_alto(
        tmp_path / "0000.xml",
        [
            "de l’entente de l’Autriche et de la Russie ce",
            "Das bischöfliche Ordinariat der Diözese ist heute",
        ],
    )
    kept, stats = ex.extract_lines(tmp_path, lang="fr")
    assert kept == ["de l’entente de l’Autriche et de la Russie ce"]
    assert stats["wrong_language"] == 1
    assert stats["kept"] == 1

    kept_de, _ = ex.extract_lines(tmp_path, lang="de")
    assert kept_de == ["Das bischöfliche Ordinariat der Diözese ist heute"]


def test_extract_drops_short_and_digit_heavy_lines(tmp_path: Path):
    _write_alto(
        tmp_path / "0000.xml",
        [
            "de la",  # too short
            "le cabinet de Vienne 19694 74 30 25 1887",  # digit heavy
            "On me dit aujourd’hui que tout ce qui s’est",  # kept
        ],
    )
    kept, stats = ex.extract_lines(tmp_path, lang="fr")
    assert kept == ["On me dit aujourd’hui que tout ce qui s’est"]
    assert stats["too_short"] == 1
    assert stats["digit_heavy"] == 1


def test_extract_drops_hyphen_unit_members(tmp_path: Path):
    """A hyphen-broken line's text is a word fragment; scoring it would
    measure the truncation, not the language. Both parts go."""
    _write_alto(
        tmp_path / "0000.xml",
        [
            "il a été rendu par le tribunal contradic-",
            "toirement entre les parties de cette ville",
            "On me dit aujourd’hui que tout ce qui s’est",
        ],
    )
    kept, stats = ex.extract_lines(tmp_path, lang="fr")
    assert stats["hyphen_part"] >= 1
    assert not any(line.endswith("-") for line in kept)


def test_stats_account_for_every_line(tmp_path: Path):
    _write_alto(
        tmp_path / "0000.xml",
        [
            "de l’entente de l’Autriche et de la Russie ce",
            "Das bischöfliche Ordinariat der Diözese ist heute",
            "de la",
            "le cabinet 19694 74 30 25 1887 22 11",
        ],
    )
    _, stats = ex.extract_lines(tmp_path, lang="fr")
    accounted = (
        stats["hyphen_part"]
        + stats["wrong_language"]
        + stats["too_short"]
        + stats["digit_heavy"]
        + stats["kept"]
    )
    assert accounted == stats["total"]


def test_text_is_taken_verbatim(tmp_path: Path):
    """Period orthography is never normalised (ROADMAP rule 3): the
    calibration must see exactly what the scorer sees at runtime."""
    text = "qu’il y a de certain c’est que le cabinet de"
    _write_alto(tmp_path / "0000.xml", [text])
    kept, _ = ex.extract_lines(tmp_path, lang="fr")
    assert kept == [text]
