"""Тесты подсказок и применения замен."""

from __future__ import annotations

import pytest

from analyzer import ReplacementEntry
from suggestions import (
    apply_replacement,
    apply_replacement_by_text,
    list_suggestions,
)


DICT = [
    ReplacementEntry("в целях", "для", "note"),
    ReplacementEntry("на текущий момент", "сейчас"),
    ReplacementEntry("осуществлять проверку", "проверять"),
]


def test_replacement_boundaries_do_not_match_inside_words():
    text = "нецели в целях работы"
    suggestions = list_suggestions(text, dictionary=DICT)
    originals = [s.original.casefold() for s in suggestions]
    assert "в целях" in originals
    assert all("нецели" not in s.original.casefold() for s in suggestions)


def test_preserve_untouched_text():
    text = "А. В целях теста — конец!"
    suggestions = list_suggestions(text, dictionary=DICT)
    assert suggestions
    s = suggestions[0]
    edited = apply_replacement(text, s.span.start, s.span.end, s.replacement)
    assert edited.startswith("А. ")
    assert edited.endswith(" — конец!")
    assert "в целях" not in edited.casefold()
    assert "для" in edited.casefold()


def test_capitalization_preserved():
    text = "В целях проверки."
    suggestions = list_suggestions(text, dictionary=DICT)
    assert suggestions
    s = suggestions[0]
    edited = apply_replacement(text, s.span.start, s.span.end, s.replacement)
    assert edited.startswith("Для ")


def test_recalculation_after_edits():
    text = "В целях А и на текущий момент Б."
    first = list_suggestions(text, dictionary=DICT)
    assert len(first) >= 2
    s0 = first[0]
    edited = apply_replacement(text, s0.span.start, s0.span.end, s0.replacement)
    second = list_suggestions(edited, dictionary=DICT)
    # После замены смещения пересчитаны относительно нового текста
    for item in second:
        assert edited[item.span.start : item.span.end] == item.original
    assert all(s.original.casefold() != "в целях" for s in second)


def test_apply_by_text_occurrence():
    text = "в целях один и в целях два"
    edited = apply_replacement_by_text(text, "в целях", "для", occurrence=1)
    assert edited == "в целях один и для два"


def test_invalid_offsets():
    with pytest.raises(ValueError):
        apply_replacement("текст", 3, 1, "x")
