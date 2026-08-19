"""`I2b` — a structural edit must stay INEXPRESSIBLE in the protocol.

The library does not merge lines, split lines, or move text between them.
That prohibition is enforced at runtime in several places and well guarded —
`I2a` — but ``docs/promises.md`` graded THIS row **aucune**, and precisely:
"adding a ``MergeLines`` makes no test fail". A rule enforced only at runtime
is a rule someone can route around by adding a case; a rule the vocabulary
cannot express is one nobody has to remember.

**This file does not decide the union may never grow.** It decides that
growing it is a DELIBERATE act rather than a side effect — the same shape
``test_public_api_snapshot`` gives the public surface, and for the same
reason. A new member arrives with this test red, and whoever turns it green
has to say, in a diff someone reviews, what the new operation does to line
integrity.

**Why a pinned list rather than a rule about names.** "No member may be
called ``MergeLines``" guards a spelling. The thing to guard is the shape of
what an operation can say: today an op names ONE line and replaces text
inside it, so no value of any field can address two lines at once. A member
that broke that would not necessarily be named after a merge.
"""

from __future__ import annotations

import typing

import pytest

from saknussemm.core.editing import EditOp, ReplaceLine, ReplaceSpan

#: The union, as it stands. Two members, both scoped to a single line.
_DECLARED = (ReplaceLine, ReplaceSpan)


def _union_members() -> tuple[type, ...]:
    """The concrete classes ``EditOp`` admits, through its annotation."""
    annotated_args = typing.get_args(EditOp)
    union = annotated_args[0]
    return typing.get_args(union)


#: The properties below run over what the union ACTUALLY admits, not over
#: the pinned list. Measured: parametrising on the pin let a `MergeLines`
#: fail only the pin, so the properties never met the member they exist to
#: judge — and the pin is the one assertion a hurried author edits first.
_MEMBERS = _union_members()


def test_the_union_has_exactly_the_two_members_it_declares() -> None:
    """The pin. Red is the point: it is how a third member gets discussed.

    If you are reading this because you added one, the question to answer in
    your PR is not "may I add it" but what it does to the three invariants
    below — every op names exactly one line, carries text, and cannot address
    a second line by any value of any field.
    """
    assert set(_union_members()) == set(_DECLARED), (
        f"the EditOp union changed: {_union_members()}. Adding an operation "
        "is allowed; adding one silently is not — say in your PR what it "
        "does to line integrity."
    )


@pytest.mark.parametrize("member", _MEMBERS)
def test_every_operation_names_exactly_one_line(member: type) -> None:
    """The property the union exists to hold.

    ``line_id`` singular, and no field that could name a second line. An
    operation that took ``line_ids`` — or a ``target_line_id`` beside its
    own — could express "take this text from here to there", which is the
    one thing this library refuses to do.
    """
    fields = member.model_fields
    assert "line_id" in fields, f"{member.__name__} does not name a line"
    # ANY other field mentioning a line, not merely a plural one. Measured:
    # a `MergeLines` carrying `with_line_id` slipped past a rule that only
    # looked for names ending in "s", which is a rule about spelling rather
    # than about what the operation can say.
    others = [name for name in fields if name != "line_id" and "line" in name.lower()]
    assert not others, f"{member.__name__} can address more than one line: {others}"


@pytest.mark.parametrize("member", _MEMBERS)
def test_every_operation_carries_replacement_text(member: type) -> None:
    """An op says what a line should read, never what to DO to it.

    A member with no text — ``DeleteLine``, ``MergeWithNext`` — would be a
    structural instruction, and the protocol has no way to apply one. The
    absence of that vocabulary is the invariant, not a missing feature.
    """
    assert "text" in member.model_fields, (
        f"{member.__name__} carries no replacement text, so it is an "
        "instruction rather than a proposed reading"
    )


def test_the_discriminator_is_the_op_name() -> None:
    """A member without a distinct ``op`` tag cannot be told apart on the wire.

    Two operations sharing a tag would deserialise into whichever the union
    tries first — silently, and differently depending on declaration order.
    """
    tags = {member.model_fields["op"].default for member in _MEMBERS}
    assert len(tags) == len(_MEMBERS), f"two operations share a tag: {tags}"
    assert all(isinstance(tag, str) and tag for tag in tags)
