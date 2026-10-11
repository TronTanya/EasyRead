"""Тесты анализатора EasyRead."""

from __future__ import annotations

import pytest

from analyzer import (
    MAX_TEXT_CHARS,
    ReplacementEntry,
    analyze_text,
    calculate_simplicity_score,
    compare_metrics,
    decode_upload,
    extract_words,
    find_formal_expressions,
    is_blank,
    segment_sentences,
)


DICT = [
    ReplacementEntry("в целях", "для"),
    ReplacementEntry("в случае если", "если"),
    ReplacementEntry("на текущий момент", "сейчас"),
    ReplacementEntry("осуществлять проверку", "проверять"),
]


def test_empty_and_whitespace():
    assert is_blank("")
    assert is_blank("   \n\t  ")
    empty = analyze_text("   ", dictionary=DICT)
    assert empty.word_count == 0
    assert empty.sentence_count == 0
    assert empty.score.score is None


def test_russian_word_count():
    text = "Кот сидит на ковре и смотрит в окно."
    result = analyze_text(text, dictionary=DICT)
    assert result.word_count == 8
    assert len(extract_words(text)) == 8


def test_mixed_russian_latin_and_numbers():
    text = "Модель BERT-base даёт F1 = 0.91 на корпусе."
    words = [w.text for w in extract_words(text)]
    assert "Модель" in words
    assert "BERT-base" in words
    assert "корпусе" in words


def test_sentence_segmentation_abbreviations():
    text = "Мы живём в г. Москве. Это столица."
    spans = segment_sentences(text)
    assert len(spans) == 2
    assert "г. Москве" in spans[0].text


def test_initials_and_decimals():
    text = "Работу выполнил И. А. Иванов. Значение равно 3.14 единиц."
    spans = segment_sentences(text)
    assert len(spans) == 2
    assert "И. А. Иванов" in spans[0].text
    assert "3.14" in spans[1].text


def test_long_word_threshold():
    text = "Электроэнцефалография помогает врачу."
    # В слове 21 буква: при пороге 21 оно не считается длинным (> порога).
    soft = analyze_text(text, long_word_threshold=21, dictionary=DICT)
    hard = analyze_text(text, long_word_threshold=12, dictionary=DICT)
    assert soft.long_word_count == 0
    assert hard.long_word_count >= 1


def test_formal_expression_matching():
    text = "В целях контроля в случае если нужно действовать."
    hits = find_formal_expressions(text, DICT)
    originals = {entry.original for _, entry in hits}
    assert "в целях" in originals
    assert "в случае если" in originals


def test_score_bounds_and_formula():
    empty = calculate_simplicity_score(0, 0, 0, 0)
    assert empty.score is None

    perfect = calculate_simplicity_score(10, 0, 0, 50)
    assert perfect.score == 100.0

    heavy = calculate_simplicity_score(40, 30, 10, 50)
    assert heavy.score is not None
    assert 0.0 <= heavy.score <= 100.0
    assert heavy.sentence_penalty == 40.0
    assert heavy.long_word_penalty == 40.0


def test_score_penalties_documented_example():
    # avg=17 → penalty 2*(17-12)=10; long%=5 → 10; formal 1/100 words → 4
    breakdown = calculate_simplicity_score(17, 5, 1, 100)
    assert breakdown.sentence_penalty == 10.0
    assert breakdown.long_word_penalty == 10.0
    assert breakdown.formal_penalty == 4.0
    assert breakdown.score == 76.0


def test_known_counts_algorithm_check():
    text = "Одно. Два слова. Три слова здесь."
    result = analyze_text(text, dictionary=DICT)
    assert result.sentence_count == 3
    assert result.word_count == 6


def test_oversized_text():
    text = "а" * (MAX_TEXT_CHARS + 1)
    with pytest.raises(ValueError, match="лимит"):
        analyze_text(text, dictionary=DICT)


def test_invalid_utf8_and_oversized_upload():
    with pytest.raises(ValueError, match="UTF-8"):
        decode_upload(b"\xff\xfe\xfd")
    with pytest.raises(ValueError, match="лимит"):
        decode_upload(b"a" * (1_048_576 + 1))


def test_comparison_same_settings():
    text = "В целях проверки текст остаётся коротким."
    a = analyze_text(text, long_word_threshold=12, dictionary=DICT)
    b = analyze_text(text, long_word_threshold=12, dictionary=DICT)
    cmp_ = compare_metrics(a, b)
    assert cmp_["word_count"]["delta"] == 0
    assert cmp_["simplicity_index"]["delta"] == 0


def test_recommendations_not_duplicated():
    text = "В целях работы в целях учёта."
    result = analyze_text(text, dictionary=DICT)
    keys = [
        (i.kind, i.span.start, i.span.end, i.span.text.casefold())
        for i in result.recommendations
    ]
    assert len(keys) == len(set(keys))


def test_source_offsets_match_original():
    text = "Префикс. Длинноепредложениеслово здесь."
    result = analyze_text(text, long_word_threshold=12, dictionary=DICT)
    for issue in result.issues:
        assert text[issue.span.start : issue.span.end] == issue.span.text
