"""A corrected line is ONE line, and both gates have to believe it.

``str.splitlines`` breaks on far more than ``\n`` and ``\r``: U+2028,
U+2029, ``\x0b``, ``\x0c``, ``\x85``, ``\x1c``-``\x1e``. A gate that
rejects only the two obvious ones lets the others through into an ALTO
``CONTENT`` attribute, where a single physical line silently becomes two
for every consumer that splits on lines.

There are two such gates and they are twins — the producer-response
validator and ``editing``'s ``replace_line``. Testing one and not the other
is how the pair drifts, so they are checked side by side over the same
separator list, with the acceptance case that keeps the rejection honest.
"""

from __future__ import annotations

import pytest


_SEPARATORS = [" ", " ", "\x0b", "\x0c", "\x85", "\x1c", "\x1d", "\x1e"]


@pytest.mark.parametrize("sep", _SEPARATORS)
def test_f10_validator_rejects_unicode_line_separators(sep: str):
    from saknussemm.core.validator import validate_llm_response
    from saknussemm.errors import ValidationError

    raw = {"lines": [{"line_id": "l1", "corrected_text": f"hello{sep}world"}]}
    with pytest.raises(ValidationError):
        validate_llm_response(raw, ["l1"], None, {"l1": "hello world"})


@pytest.mark.parametrize("sep", _SEPARATORS)
def test_f10_editing_rejects_unicode_line_separators(sep: str):
    from saknussemm.core.editing import (
        EditScript,
        ReplaceLine,
        apply_edit_script,
    )

    script = EditScript(ops=[ReplaceLine(line_id="l1", text=f"hello{sep}world")])
    res = apply_edit_script(script, {"l1": "hello world"})
    # A fully-rejected line is ABSENT from text_by_id (keeps prior text).
    assert "l1" not in res.text_by_id, "op must be rejected"
    assert res.rejected and res.rejected[0].reason == "e3_newline"


def test_f10_plain_text_still_accepted():
    from saknussemm.core.validator import validate_llm_response

    raw = {"lines": [{"line_id": "l1", "corrected_text": "héllo wörld"}]}
    resp = validate_llm_response(raw, ["l1"], None, {"l1": "hello world"})
    assert resp.lines[0].corrected_text == "héllo wörld"
