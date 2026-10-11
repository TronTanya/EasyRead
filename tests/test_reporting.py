"""Тесты отчётов и HTML-экранирования."""

from __future__ import annotations

from analyzer import ReplacementEntry, analyze_text
from reporting import build_html_report, escape_html, highlight_text


DICT = [
    ReplacementEntry("в целях", "для"),
]


def test_html_escaping():
    raw = '<script>alert("x")</script> & "кавычки"'
    escaped = escape_html(raw)
    assert "<script>" not in escaped
    assert "&lt;script&gt;" in escaped
    assert "&amp;" in escaped
    assert "&quot;" in escaped


def test_highlight_escapes_user_text():
    text = "Текст <b>важный</b> и сверхдлинноесловоабв."
    result = analyze_text(text, long_word_threshold=12, dictionary=DICT)
    html = highlight_text(result.text, result.issues)
    assert "<b>важный</b>" not in html
    assert "&lt;b&gt;важный&lt;/b&gt;" in html


def test_standalone_report_generation():
    original = analyze_text(
        "В целях демонстрации это достаточно длинное предложение, "
        "чтобы проверить отчёт и рекомендации для автора текста.",
        dictionary=DICT,
    )
    edited = analyze_text(
        "Для демонстрации короткое предложение. Есть ещё одно.",
        dictionary=DICT,
    )
    report = build_html_report(original, edited)
    assert report.startswith("<!DOCTYPE html>")
    assert "EasyRead" in report
    assert "Условный индекс простоты" in report
    assert "учебный показатель" in report
    assert "<script>" not in original.text or "&lt;script&gt;" in report
    assert "Настройки анализа" in report
    assert "Метрики упрощённой версии" in report
    # Автономность: есть встроенные стили, нет внешних скриптов сервера
    assert "<style>" in report
    assert "streamlit" not in report.lower()


def test_report_escapes_injected_html_in_text():
    text = 'Фраза <img src=x onerror=alert(1)> и "тест".'
    original = analyze_text(text, dictionary=DICT)
    report = build_html_report(original)
    assert "<img src=x" not in report
    assert "&lt;img" in report
