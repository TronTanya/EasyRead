"""Детерминированный анализ читаемости русского текста."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

DEFAULT_LONG_WORD_THRESHOLD = 12
DEFAULT_LONG_SENTENCE_WORDS = 20
MAX_TEXT_CHARS = 50_000
MAX_UPLOAD_BYTES = 1_048_576

# Сокращения, после которых точка обычно не заканчивает предложение.
_ABBREVIATIONS = frozenset(
    {
        "г",
        "гг",
        "ул",
        "пр",
        "пер",
        "д",
        "кв",
        "стр",
        "корп",
        "обл",
        "р-н",
        "т",
        "т.е",
        "т.к",
        "т.п",
        "т.д",
        "и.т.д",
        "и.т.п",
        "см",
        "рис",
        "табл",
        "стр",
        "п",
        "пп",
        "ч",
        "гл",
        "др",
        "проч",
        "напр",
        "т.н",
        "им",
        "руб",
        "коп",
        "млн",
        "млрд",
        "тыс",
        "кг",
        "км",
        "см",
        "мм",
        "га",
        "мин",
        "сек",
        "час",
        "св",
        "тов",
        "проф",
        "доц",
        "акад",
        "канд",
        "д-р",
        "г-н",
        "г-жа",
        "евр",
        "н.э",
        "до н.э",
    }
)

_WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё]+(?:-[A-Za-zА-Яа-яЁё]+)*", re.UNICODE)
_LETTER_RE = re.compile(r"[A-Za-zА-Яа-яЁё]", re.UNICODE)


@dataclass(frozen=True)
class TextSpan:
    """Фрагмент исходного текста с смещениями."""

    start: int
    end: int
    text: str


@dataclass(frozen=True)
class Issue:
    """Найденная особенность текста."""

    kind: str
    span: TextSpan
    explanation: str
    action: str
    meta: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ScoreBreakdown:
    """Вклад штрафов в учебный индекс простоты."""

    base: float
    sentence_penalty: float
    long_word_penalty: float
    formal_penalty: float
    score: float | None


@dataclass
class AnalysisResult:
    """Полный результат анализа."""

    text: str
    word_count: int
    sentence_count: int
    average_words_per_sentence: float
    max_sentence_words: int
    long_word_count: int
    long_word_percent: float
    formal_expression_count: int
    long_word_threshold: int
    long_sentence_words: int
    sentences: list[TextSpan]
    words: list[TextSpan]
    issues: list[Issue]
    recommendations: list[Issue]
    score: ScoreBreakdown
    segmentation_notes: list[str]


@dataclass(frozen=True)
class ReplacementEntry:
    original: str
    replacement: str
    note: str = ""


def load_replacements(path: Path | None = None) -> list[ReplacementEntry]:
    """Загрузить словарь формальных выражений."""
    if path is None:
        path = Path(__file__).resolve().parent / "content" / "replacements.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return [
        ReplacementEntry(
            original=item["original"],
            replacement=item["replacement"],
            note=item.get("note", ""),
        )
        for item in data
    ]


def normalize_input(text: str | None) -> str:
    """Вернуть текст без изменений символов; None трактуется как пустая строка."""
    if text is None:
        return ""
    return text


def is_blank(text: str | None) -> bool:
    return not normalize_input(text).strip()


def validate_text_length(text: str, max_chars: int = MAX_TEXT_CHARS) -> None:
    if len(text) > max_chars:
        raise ValueError(
            f"Текст превышает лимит {max_chars} символов "
            f"(сейчас {len(text)})."
        )


def decode_upload(raw: bytes, max_bytes: int = MAX_UPLOAD_BYTES) -> str:
    """Декодировать загруженный файл UTF-8 с проверкой размера."""
    if len(raw) > max_bytes:
        raise ValueError(
            f"Файл превышает лимит {max_bytes} байт "
            f"(сейчас {len(raw)})."
        )
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(
            "Не удалось прочитать файл как UTF-8. "
            "Сохраните текст в кодировке UTF-8 и повторите загрузку."
        ) from exc


def extract_words(text: str) -> list[TextSpan]:
    """Извлечь слова (кириллица/латиница, допускается дефис) со смещениями."""
    return [
        TextSpan(match.start(), match.end(), match.group(0))
        for match in _WORD_RE.finditer(text)
    ]


def letter_count(word: str) -> int:
    return len(_LETTER_RE.findall(word))


def _is_abbreviation_before(text: str, dot_index: int) -> bool:
    """Проверить, относится ли точка к распространённому сокращению."""
    left = text[:dot_index].rstrip()
    if not left:
        return False

    # Инициалы вида «И.» или «И. А.»
    if re.search(r"(?:^|[\s(«\"])[A-Za-zА-Яа-яЁё]\Z", left):
        return True

    # Многоточие / многоточечные сокращения: т.е., т.д., н.э.
    m_multi = re.search(
        r"([A-Za-zА-Яа-яЁё]+(?:\.[A-Za-zА-Яа-яЁё]+)+)\Z",
        left,
        flags=re.IGNORECASE,
    )
    if m_multi:
        token = m_multi.group(1).lower().rstrip(".")
        if token in _ABBREVIATIONS or token.replace(".", "") in {
            a.replace(".", "") for a in _ABBREVIATIONS
        }:
            return True

    m = re.search(r"([A-Za-zА-Яа-яЁё]+(?:-[A-Za-zА-Яа-яЁё]+)*)\Z", left)
    if not m:
        return False
    token = m.group(1).lower()
    return token in _ABBREVIATIONS


def _is_decimal_dot(text: str, dot_index: int) -> bool:
    """Точка между цифрами (например, 3.14) не завершает предложение."""
    if dot_index <= 0 or dot_index >= len(text) - 1:
        return False
    return text[dot_index - 1].isdigit() and text[dot_index + 1].isdigit()


def _is_sentence_ender(text: str, index: int) -> bool:
    ch = text[index]
    if ch not in ".!?…":
        return False
    if ch == "." and (_is_decimal_dot(text, index) or _is_abbreviation_before(text, index)):
        return False
    # Многоточие: считать один конец на всю последовательность точек
    if ch == "." and index + 1 < len(text) and text[index + 1] == ".":
        return False
    return True


def segment_sentences(text: str) -> list[TextSpan]:
    """
    Сегментация предложений с учётом типичных сокращений, инициалов и десятичных чисел.

    Ограничения:
    - редкие или авторские сокращения могут ошибочно завершить предложение;
    - прямая речь и сложные кавычки обрабатываются упрощённо;
    - предложения без финальной пунктуации выделяются до конца текста.
    """
    if not text.strip():
        return []

    spans: list[TextSpan] = []
    start = 0
    i = 0
    n = len(text)

    while i < n:
        if _is_sentence_ender(text, i):
            end = i + 1
            while end < n and text[end] in "\"»')]} ":
                end += 1
            chunk = text[start:end]
            if chunk.strip():
                # Подрезаем ведущие пробелы в span, сохраняя исходные смещения содержимого
                leading = len(chunk) - len(chunk.lstrip())
                trailing = len(chunk) - len(chunk.rstrip())
                s = start + leading
                e = end - trailing
                if s < e:
                    spans.append(TextSpan(s, e, text[s:e]))
            start = end
            i = end
            continue
        i += 1

    if start < n and text[start:].strip():
        chunk = text[start:]
        leading = len(chunk) - len(chunk.lstrip())
        trailing = len(chunk) - len(chunk.rstrip())
        s = start + leading
        e = n - trailing
        if s < e:
            spans.append(TextSpan(s, e, text[s:e]))

    return spans


def find_formal_expressions(
    text: str,
    dictionary: Sequence[ReplacementEntry],
) -> list[tuple[TextSpan, ReplacementEntry]]:
    """Найти вхождения формальных выражений без перекрытий (длинные раньше)."""
    if not text:
        return []

    ordered = sorted(dictionary, key=lambda e: len(e.original), reverse=True)
    occupied = [False] * len(text)
    found: list[tuple[TextSpan, ReplacementEntry]] = []

    for entry in ordered:
        pattern = re.compile(
            r"(?<![A-Za-zА-Яа-яЁё])"
            + re.escape(entry.original)
            + r"(?![A-Za-zА-Яа-яЁё])",
            flags=re.IGNORECASE,
        )
        for match in pattern.finditer(text):
            start, end = match.start(), match.end()
            if any(occupied[start:end]):
                continue
            for idx in range(start, end):
                occupied[idx] = True
            found.append((TextSpan(start, end, text[start:end]), entry))

    found.sort(key=lambda item: item[0].start)
    return found


def calculate_simplicity_score(
    average_words_per_sentence: float,
    long_word_percent: float,
    formal_expression_count: int,
    word_count: int,
) -> ScoreBreakdown:
    """
    Условный индекс простоты (0–100).

    Формула:
    - старт 100;
    - минус min(40, 2 × max(0, средняя длина предложения − 12));
    - минус min(40, 2 × процент длинных слов);
    - минус min(20, 4 × формальных выражений на 100 слов);
    - результат ограничивается диапазоном [0, 100].

    Проценты трактуются как значения от 0 до 100.
    Для пустого текста score = None.
    """
    if word_count <= 0:
        return ScoreBreakdown(100.0, 0.0, 0.0, 0.0, None)

    sentence_penalty = min(40.0, 2.0 * max(0.0, average_words_per_sentence - 12.0))
    long_word_penalty = min(40.0, 2.0 * max(0.0, long_word_percent))
    formal_per_100 = (formal_expression_count / word_count) * 100.0
    formal_penalty = min(20.0, 4.0 * formal_per_100)
    raw = 100.0 - sentence_penalty - long_word_penalty - formal_penalty
    score = max(0.0, min(100.0, raw))
    return ScoreBreakdown(
        base=100.0,
        sentence_penalty=sentence_penalty,
        long_word_penalty=long_word_penalty,
        formal_penalty=formal_penalty,
        score=score,
    )


def _issue_key(issue: Issue) -> tuple[str, int, int, str]:
    return (issue.kind, issue.span.start, issue.span.end, issue.span.text.casefold())


def build_recommendations(issues: Iterable[Issue]) -> list[Issue]:
    """Убрать дубликаты рекомендаций, сохраняя порядок."""
    seen: set[tuple[str, int, int, str]] = set()
    result: list[Issue] = []
    for issue in issues:
        key = _issue_key(issue)
        if key in seen:
            continue
        seen.add(key)
        result.append(issue)
    return result


def analyze_text(
    text: str,
    *,
    long_word_threshold: int = DEFAULT_LONG_WORD_THRESHOLD,
    long_sentence_words: int = DEFAULT_LONG_SENTENCE_WORDS,
    dictionary: Sequence[ReplacementEntry] | None = None,
) -> AnalysisResult:
    """Выполнить полный анализ текста."""
    text = normalize_input(text)
    validate_text_length(text)

    if dictionary is None:
        dictionary = load_replacements()

    words = extract_words(text)
    sentences = segment_sentences(text)
    word_count = len(words)
    sentence_count = len(sentences)

    words_per_sentence = [
        len(extract_words(span.text)) for span in sentences
    ]
    average = (
        sum(words_per_sentence) / sentence_count if sentence_count else 0.0
    )
    max_sentence = max(words_per_sentence) if words_per_sentence else 0

    long_words = [w for w in words if letter_count(w.text) > long_word_threshold]
    long_word_count = len(long_words)
    long_word_percent = (
        (long_word_count / word_count) * 100.0 if word_count else 0.0
    )

    formal_hits = find_formal_expressions(text, dictionary)
    formal_count = len(formal_hits)

    issues: list[Issue] = []

    for span, count in zip(sentences, words_per_sentence):
        if count > long_sentence_words:
            issues.append(
                Issue(
                    kind="long_sentence",
                    span=span,
                    explanation=(
                        f"Предложение содержит {count} слов "
                        f"(порог — {long_sentence_words})."
                    ),
                    action=(
                        "Рассмотрите возможность разделить его на два "
                        "или больше предложений, если смысл это допускает."
                    ),
                    meta={"word_count": count},
                )
            )

    for span in long_words:
        issues.append(
            Issue(
                kind="long_word",
                span=span,
                explanation=(
                    f"Слово длиннее установленного порога "
                    f"({long_word_threshold} букв). "
                    "Длина — лишь грубый индикатор и сама по себе "
                    "не делает слово трудным."
                ),
                action=(
                    "Проверьте, знакомо ли оно вашей аудитории. "
                    "Технические термины не нужно заменять только из‑за длины."
                ),
                meta={"letters": letter_count(span.text)},
            )
        )

    for span, entry in formal_hits:
        issues.append(
            Issue(
                kind="formal_expression",
                span=span,
                explanation=(
                    f"Выражение «{span.text}» встречается в словаре "
                    f"формальных оборотов. Возможная замена: «{entry.replacement}»."
                ),
                action=(
                    f"Можно заменить на «{entry.replacement}», "
                    "если смысл сохраняется. Это контекстная подсказка, "
                    "а не универсально верная замена."
                ),
                meta={
                    "replacement": entry.replacement,
                    "note": entry.note,
                },
            )
        )

    recommendations = build_recommendations(issues)
    score = calculate_simplicity_score(
        average, long_word_percent, formal_count, word_count
    )

    notes = [
        "Сегментация предложений учитывает распространённые сокращения "
        "(г., ул., т.е., т.д. и др.), инициалы и десятичные числа.",
        "Редкие сокращения, сложная прямая речь и нестандартная пунктуация "
        "могут приводить к ошибкам границ предложений.",
        "Длина слова — условный признак; длинный термин может быть уместен.",
        "Подстановки из словаря — контекстные подсказки, а не полный "
        "семантический переписыватель текста.",
    ]

    return AnalysisResult(
        text=text,
        word_count=word_count,
        sentence_count=sentence_count,
        average_words_per_sentence=average,
        max_sentence_words=max_sentence,
        long_word_count=long_word_count,
        long_word_percent=long_word_percent,
        formal_expression_count=formal_count,
        long_word_threshold=long_word_threshold,
        long_sentence_words=long_sentence_words,
        sentences=sentences,
        words=words,
        issues=issues,
        recommendations=recommendations,
        score=score,
        segmentation_notes=notes,
    )


def compare_metrics(
    original: AnalysisResult,
    edited: AnalysisResult,
) -> dict[str, dict[str, float | int | None]]:
    """Сравнить метрики двух анализов с одинаковыми настройками."""
    def pair(a: float | int | None, b: float | int | None) -> dict[str, float | int | None]:
        delta: float | int | None
        if a is None or b is None:
            delta = None
        else:
            delta = b - a  # type: ignore[operator]
        return {"original": a, "edited": b, "delta": delta}

    return {
        "word_count": pair(original.word_count, edited.word_count),
        "sentence_count": pair(original.sentence_count, edited.sentence_count),
        "average_words_per_sentence": pair(
            original.average_words_per_sentence,
            edited.average_words_per_sentence,
        ),
        "long_word_percent": pair(
            original.long_word_percent, edited.long_word_percent
        ),
        "formal_expression_count": pair(
            original.formal_expression_count,
            edited.formal_expression_count,
        ),
        "simplicity_index": pair(original.score.score, edited.score.score),
    }
