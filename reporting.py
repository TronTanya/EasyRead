"""Формирование отчётов и безопасная HTML-разметка."""

from __future__ import annotations

import html
from datetime import datetime
from typing import Iterable, Sequence

from analyzer import AnalysisResult, Issue, TextSpan


KIND_LABELS = {
    "long_sentence": "Длинное предложение",
    "long_word": "Длинное слово",
    "formal_expression": "Формальное выражение",
}


def escape_html(value: str | None) -> str:
    """Экранировать пользовательский текст для HTML."""
    return html.escape("" if value is None else value, quote=True)


def _span_sort_key(span: TextSpan) -> tuple[int, int]:
    return (span.start, span.end)


def highlight_text(text: str, issues: Sequence[Issue]) -> str:
    """
    Подсветить проблемные фрагменты с текстовыми метками.

    Пользовательский текст всегда экранируется. Перекрывающиеся интервалы
    разрешаются приоритетом: formal_expression > long_sentence > long_word.
    """
    if not text:
        return ""

    priority = {
        "formal_expression": 3,
        "long_sentence": 2,
        "long_word": 1,
    }
    # Выбираем непересекающиеся интервалы с наибольшим приоритетом
    candidates = sorted(
        issues,
        key=lambda i: (-priority.get(i.kind, 0), i.span.start, -(i.span.end - i.span.start)),
    )
    selected: list[Issue] = []
    occupied: list[tuple[int, int]] = []
    for issue in candidates:
        s, e = issue.span.start, issue.span.end
        if s < 0 or e > len(text) or s >= e:
            continue
        if any(not (e <= a or s >= b) for a, b in occupied):
            continue
        occupied.append((s, e))
        selected.append(issue)

    selected.sort(key=lambda i: i.span.start)
    parts: list[str] = []
    cursor = 0
    for issue in selected:
        s, e = issue.span.start, issue.span.end
        if cursor < s:
            parts.append(escape_html(text[cursor:s]))
        label = KIND_LABELS.get(issue.kind, issue.kind)
        css = {
            "long_sentence": "hl-sentence",
            "long_word": "hl-word",
            "formal_expression": "hl-formal",
        }.get(issue.kind, "hl-other")
        fragment = escape_html(text[s:e])
        parts.append(
            f'<mark class="{css}" title="{escape_html(label)}">'
            f"{fragment}"
            f'<span class="hl-label">{escape_html(label)}</span>'
            f"</mark>"
        )
        cursor = e
    if cursor < len(text):
        parts.append(escape_html(text[cursor:]))
    return "".join(parts)


def _fmt_score(score: float | None) -> str:
    if score is None:
        return "—"
    return f"{score:.1f}"


def _fmt_float(value: float) -> str:
    return f"{value:.2f}"


def _issues_rows(issues: Sequence[Issue]) -> str:
    if not issues:
        return "<tr><td colspan='4'>Замечаний не обнаружено.</td></tr>"
    rows: list[str] = []
    for issue in issues:
        rows.append(
            "<tr>"
            f"<td>{escape_html(KIND_LABELS.get(issue.kind, issue.kind))}</td>"
            f"<td><code>{escape_html(issue.span.text)}</code></td>"
            f"<td>{escape_html(issue.explanation)}</td>"
            f"<td>{escape_html(issue.action)}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def _metrics_table(analysis: AnalysisResult, title: str) -> str:
    score = analysis.score
    score_block = "нет данных (пустой текст)"
    if score.score is not None:
        score_block = (
            f"{_fmt_score(score.score)} / 100<br>"
            f"штраф за длину предложений: {_fmt_float(score.sentence_penalty)}; "
            f"штраф за длинные слова: {_fmt_float(score.long_word_penalty)}; "
            f"штраф за формальные выражения: {_fmt_float(score.formal_penalty)}"
        )
    return f"""
    <h3>{escape_html(title)}</h3>
    <table>
      <tr><th>Показатель</th><th>Значение</th></tr>
      <tr><td>Число слов</td><td>{analysis.word_count}</td></tr>
      <tr><td>Число предложений</td><td>{analysis.sentence_count}</td></tr>
      <tr><td>Средняя длина предложения (слов)</td><td>{_fmt_float(analysis.average_words_per_sentence)}</td></tr>
      <tr><td>Максимальная длина предложения (слов)</td><td>{analysis.max_sentence_words}</td></tr>
      <tr><td>Длинные слова (число)</td><td>{analysis.long_word_count}</td></tr>
      <tr><td>Длинные слова (%)</td><td>{_fmt_float(analysis.long_word_percent)}</td></tr>
      <tr><td>Формальные выражения</td><td>{analysis.formal_expression_count}</td></tr>
      <tr><td>Условный индекс простоты</td><td>{score_block}</td></tr>
    </table>
    """


def build_html_report(
    original: AnalysisResult,
    edited: AnalysisResult | None = None,
    *,
    generated_at: datetime | None = None,
) -> str:
    """
    Собрать автономный HTML-отчёт.

    Отчёт открывается в браузере без запущенного сервера.
    Весь пользовательский контент экранируется.
    """
    when = generated_at or datetime.now()
    when_str = when.strftime("%d.%m.%Y %H:%M")

    edited_block = ""
    if edited is not None and edited.text.strip():
        edited_block = _metrics_table(edited, "Метрики упрощённой версии")
        edited_block += f"""
        <h3>Упрощённая версия</h3>
        <pre class="text-block">{escape_html(edited.text)}</pre>
        """

    notes = "".join(f"<li>{escape_html(n)}</li>" for n in original.segmentation_notes)

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <title>EasyRead — отчёт анализа</title>
  <style>
    body {{
      font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
      color: #202733;
      background: #F7F8FA;
      margin: 0;
      padding: 24px;
      line-height: 1.55;
    }}
    main {{
      max-width: 1100px;
      margin: 0 auto;
      background: #FFFFFF;
      border: 1px solid #E4E7EC;
      border-radius: 6px;
      padding: 28px 32px;
    }}
    h1, h2, h3 {{ color: #202733; font-weight: 600; }}
    h1 {{ font-size: 1.6rem; margin-top: 0; }}
    .muted {{ color: #667085; }}
    .accent {{ color: #2F6B57; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin: 12px 0 24px;
      font-size: 0.95rem;
    }}
    th, td {{
      border: 1px solid #E4E7EC;
      padding: 8px 10px;
      text-align: left;
      vertical-align: top;
    }}
    th {{ background: #F7F8FA; }}
    code {{ font-family: ui-monospace, Consolas, monospace; }}
    .text-block {{
      white-space: pre-wrap;
      word-wrap: break-word;
      background: #F7F8FA;
      border: 1px solid #E4E7EC;
      border-radius: 4px;
      padding: 14px 16px;
      font-size: 16px;
      line-height: 1.65;
    }}
    .hl-sentence {{ background: #FFF4CE; }}
    .hl-word {{ background: #E8F1EE; }}
    .hl-formal {{ background: #F2E8FF; }}
    .notice {{
      border-left: 3px solid #2F6B57;
      padding: 8px 12px;
      margin: 16px 0;
      background: #F7F8FA;
    }}
  </style>
</head>
<body>
<main>
  <h1>EasyRead — отчёт анализа</h1>
  <p class="muted">Дата анализа: {escape_html(when_str)}</p>

  <h2>Настройки анализа</h2>
  <ul>
    <li>Порог длинного слова: более {original.long_word_threshold} букв</li>
    <li>Порог длинного предложения: более {original.long_sentence_words} слов</li>
  </ul>

  {_metrics_table(original, "Метрики исходного текста")}

  <h3>Исходный текст с подсветкой</h3>
  <div class="text-block">{highlight_text(original.text, original.issues)}</div>

  <h2>Обнаруженные замечания и рекомендации</h2>
  <table>
    <tr>
      <th>Тип</th>
      <th>Фрагмент</th>
      <th>Пояснение</th>
      <th>Рекомендуемое действие</th>
    </tr>
    {_issues_rows(original.recommendations)}
  </table>

  {edited_block}

  <h2>Формула условного индекса простоты</h2>
  <div class="notice">
    Старт: 100.<br>
    Минус min(40, 2 × max(0, средняя длина предложения − 12)).<br>
    Минус min(40, 2 × процент длинных слов).<br>
    Минус min(20, 4 × число формальных выражений на 100 слов).<br>
    Результат ограничивается диапазоном от 0 до 100.
  </div>
  <p><strong>Это учебный показатель на основе простых правил,
  а не валидированная оценка понимания текста.</strong></p>
  <p class="muted">Показатель не указывает возраст читателя, школьный класс,
  диагноз или сертифицированный уровень читаемости. Более высокий балл
  не доказывает лучшее понимание и сохранность смысла.</p>

  <h2>Ограничения сегментации и анализа</h2>
  <ul>
    {notes}
  </ul>
</main>
</body>
</html>
"""


def recommendations_as_dicts(issues: Iterable[Issue]) -> list[dict[str, str]]:
    """Удобное представление рекомендаций для интерфейса."""
    rows: list[dict[str, str]] = []
    for issue in issues:
        rows.append(
            {
                "fragment": issue.span.text,
                "kind": KIND_LABELS.get(issue.kind, issue.kind),
                "explanation": issue.explanation,
                "action": issue.action,
            }
        )
    return rows
