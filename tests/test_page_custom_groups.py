"""PAGE ``custom`` groups: what is dropped, and what is copied verbatim.

The ``custom`` attribute is a microformat holding several groups, and a
correction invalidates only some of them. Offset-anchored groups
(``textStyle {offset:…; length:…}``) point at character ranges in the OLD
text and are dropped once it changes; everything else must survive.

"Survive" means the SOURCE SLICE, byte for byte — not a re-emission with
tidy spacing. Transkribus writes ``readingOrder {index:0;}`` with a space
and other exporters write it without, and a reconstruction that normalises
silently rewrites a file it was asked not to touch.
"""

from __future__ import annotations

from lidenbrock.formats.page._custom import strip_offset_groups


def test_strip_offset_groups_unit():
    assert strip_offset_groups("readingOrder {index:0;}") == (
        "readingOrder {index:0;}",
        0,
    )
    assert strip_offset_groups(
        "readingOrder {index:2;} textStyle {offset:5; length:3;}"
    ) == ("readingOrder {index:2;}", 1)
    assert strip_offset_groups("textStyle {offset:0; length:4;}") == ("", 1)


def test_f12_kept_group_spacing_preserved_verbatim():
    from lidenbrock.formats.page._custom import strip_offset_groups

    new, removed = strip_offset_groups(
        "readingOrder{index:0;} textStyle {offset:0;length:3;}"
    )
    assert removed == 1
    assert new == "readingOrder{index:0;}", new  # no space injected


def test_f12_inter_group_source_text_preserved_between_kept_groups():
    from lidenbrock.formats.page._custom import strip_offset_groups

    new, removed = strip_offset_groups(
        "readingOrder {index:0;}  structure {type:heading;} textStyle {offset:1;}"
    )
    assert removed == 1
    # The double space between the two KEPT groups is source text.
    assert new == "readingOrder {index:0;}  structure {type:heading;}", new


def test_f12_nothing_removed_is_byte_identity():
    from lidenbrock.formats.page._custom import strip_offset_groups

    src = "readingOrder{index:0;}   structure {type:heading;}"
    assert strip_offset_groups(src) == (src, 0)


def test_f12_all_groups_removed_yields_empty():
    from lidenbrock.formats.page._custom import strip_offset_groups

    assert strip_offset_groups("textStyle {offset:0;length:3;}") == ("", 1)


def test_f12_canonical_transkribus_spacing_unchanged():
    from lidenbrock.formats.page._custom import strip_offset_groups

    new, removed = strip_offset_groups(
        "readingOrder {index:0;} textStyle {offset:12;length:5;}"
    )
    assert (new, removed) == ("readingOrder {index:0;}", 1)
