"""Контекстные подсказки замен формальных выражений."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from analyzer import ReplacementEntry, TextSpan, find_formal_expressions, load_replacements


@dataclass(frozen=True)
class ReplacementSuggestion:
    """Одна предложенная замена с явным действием применения."""

    span: TextSpan
    original: str
    replacement: str
    note: str
    entry: ReplacementEntry


def list_suggestions(
    text: str,
    dictionary: Sequence[ReplacementEntry] | None = None,
) -> list[ReplacementSuggestion]:
    """Собрать актуальные подсказки для текущего текста."""
    if dictionary is None:
        dictionary = load_replacements()
    hits = find_formal_expressions(text, dictionary)
    suggestions: list[ReplacementSuggestion] = []
    for span, entry in hits:
        suggestions.append(
            ReplacementSuggestion(
                span=span,
                original=span.text,
                replacement=_match_capitalization(span.text, entry.replacement),
                note=entry.note,
                entry=entry,
            )
        )
    return suggestions


def _match_capitalization(source: str, replacement: str) -> str:
    """Сохранить регистр начала фрагмента, где это практично."""
    if not source or not replacement:
        return replacement
    if source.isupper() and len(source) > 1:
        return replacement.upper()
    if source[0].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def apply_replacement(
    text: str,
    start: int,
    end: int,
    replacement: str,
) -> str:
    """
    Применить одну одобренную пользователем замену по смещениям.

    Сохраняет окружающий текст без изменений. Пунктуация вне диапазона
    [start:end] не затрагивается.
    """
    if start < 0 or end > len(text) or start > end:
        raise ValueError("Некорректные смещения для замены.")
    actual = text[start:end]
    if not actual:
        raise ValueError("Пустой фрагмент для замены.")
    # Проверяем, что диапазон всё ещё соответствует ожидаемому слову/обороту
    # (защита от устаревших смещений после ручного редактирования).
    return text[:start] + replacement + text[end:]


def apply_replacement_by_text(
    text: str,
    original_fragment: str,
    replacement: str,
    *,
    occurrence: int = 0,
) -> str:
    """
    Применить замену по тексту фрагмента (для случаев, когда смещения устарели).

    occurrence — индекс вхождения с нуля среди регистронезависимых совпадений.
    """
    pattern = re.compile(re.escape(original_fragment), flags=re.IGNORECASE)
    matches = list(pattern.finditer(text))
    if occurrence < 0 or occurrence >= len(matches):
        raise ValueError("Указанное вхождение выражения не найдено.")
    match = matches[occurrence]
    adapted = _match_capitalization(match.group(0), replacement)
    return text[: match.start()] + adapted + text[match.end() :]


def reload_dictionary(path: Path | None = None) -> list[ReplacementEntry]:
    """Перезагрузить словарь замен."""
    return load_replacements(path)
