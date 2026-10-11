"""EasyRead — анализ читаемости и понятности русского текста."""

from __future__ import annotations

import json
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

from analyzer import (
    DEFAULT_LONG_SENTENCE_WORDS,
    DEFAULT_LONG_WORD_THRESHOLD,
    MAX_TEXT_CHARS,
    MAX_UPLOAD_BYTES,
    AnalysisResult,
    analyze_text,
    compare_metrics,
    decode_upload,
    is_blank,
    load_replacements,
)
from reporting import (
    build_html_report,
    escape_html,
    highlight_text,
    recommendations_as_dicts,
)
from suggestions import apply_replacement, list_suggestions

CONTENT_DIR = Path(__file__).resolve().parent / "content"
EXAMPLES_PATH = CONTENT_DIR / "examples.json"

st.set_page_config(
    page_title="EasyRead",
    page_icon=None,
    layout="centered",
    initial_sidebar_state="collapsed",
)


def inject_styles() -> None:
    st.markdown(
        """
        <style>
          .block-container {
            max-width: 1100px;
            padding-top: 1.5rem;
            padding-bottom: 3rem;
          }
          h1, h2, h3 { letter-spacing: -0.01em; }
          .er-sub {
            color: #667085;
            font-size: 1.05rem;
            margin-top: -0.4rem;
            margin-bottom: 0.6rem;
          }
          .er-desc {
            color: #667085;
            margin-bottom: 1.2rem;
          }
          .er-panel {
            background: #FFFFFF;
            border: 1px solid #E4E7EC;
            border-radius: 6px;
            padding: 1rem 1.1rem;
            margin-bottom: 0.8rem;
          }
          .er-metric-label {
            color: #667085;
            font-size: 0.85rem;
            margin-bottom: 0.15rem;
          }
          .er-metric-value {
            color: #202733;
            font-size: 1.35rem;
            font-weight: 600;
          }
          .er-read {
            font-size: 16px;
            line-height: 1.7;
            white-space: pre-wrap;
            word-wrap: break-word;
            color: #202733;
          }
          mark.hl-sentence {
            background: #FFF4CE;
            color: inherit;
            padding: 0 2px;
            border-radius: 2px;
          }
          mark.hl-word {
            background: #E8F1EE;
            color: inherit;
            padding: 0 2px;
            border-radius: 2px;
          }
          mark.hl-formal {
            background: #F2E8FF;
            color: inherit;
            padding: 0 2px;
            border-radius: 2px;
          }
          span.hl-label {
            display: inline-block;
            margin-left: 4px;
            font-size: 0.7rem;
            color: #667085;
            vertical-align: super;
          }
          .er-note {
            color: #667085;
            font-size: 0.92rem;
            border-left: 3px solid #2F6B57;
            padding-left: 0.75rem;
            margin: 0.8rem 0 1rem;
          }
          .er-legend span {
            display: inline-block;
            margin-right: 1rem;
            font-size: 0.9rem;
            color: #667085;
          }
          .er-legend i {
            display: inline-block;
            width: 12px;
            height: 12px;
            border-radius: 2px;
            margin-right: 4px;
            vertical-align: -1px;
          }
          div[data-testid="stTabs"] button {
            font-size: 0.95rem;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


@st.cache_data(show_spinner=False)
def get_examples() -> dict:
    return json.loads(EXAMPLES_PATH.read_text(encoding="utf-8"))


@st.cache_data(show_spinner=False)
def get_dictionary():
    return load_replacements()


def init_state() -> None:
    defaults = {
        "source_text": "",
        "edited_text": "",
        "analysis": None,
        "edited_analysis": None,
        "long_word_threshold": DEFAULT_LONG_WORD_THRESHOLD,
        "show_suggestions": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


# Колбэки выполняются до перерисовки, поэтому могут менять значения виджетов с ключами.
def _set_source_text(text: str) -> None:
    st.session_state.source_text = text
    st.session_state.analysis = None
    st.session_state.edited_analysis = None
    st.session_state.edited_text = ""
    st.session_state.show_suggestions = False


def _set_edited_text(text: str) -> None:
    st.session_state.edited_text = text


def _show_suggestions() -> None:
    st.session_state.show_suggestions = True


def _on_check() -> None:
    text = st.session_state.source_text
    if is_blank(text):
        st.session_state.analysis = None
        st.session_state.analysis_error = "Введите текст или загрузите файл UTF-8 (.txt)."
        return
    try:
        result = analyze_text(
            text,
            long_word_threshold=int(st.session_state.long_word_threshold),
            long_sentence_words=DEFAULT_LONG_SENTENCE_WORDS,
            dictionary=get_dictionary(),
        )
    except ValueError as exc:
        st.session_state.analysis = None
        st.session_state.analysis_error = str(exc)
        return
    st.session_state.analysis = result
    if is_blank(st.session_state.edited_text):
        st.session_state.edited_text = result.text


def _apply_suggestion(start: int, end: int, original: str, replacement: str) -> None:
    text = st.session_state.edited_text
    if text[start:end] != original:
        st.session_state.apply_error = (
            "Текст изменился, подсказка устарела. Список замен обновлён."
        )
        return
    st.session_state.edited_text = apply_replacement(text, start, end, replacement)


def metric_card(label: str, value: str) -> None:
    st.markdown(
        f'<div class="er-panel"><div class="er-metric-label">{escape_html(label)}</div>'
        f'<div class="er-metric-value">{escape_html(value)}</div></div>',
        unsafe_allow_html=True,
    )


def run_analysis(text: str) -> AnalysisResult | None:
    if is_blank(text):
        st.warning("Введите текст или загрузите файл UTF-8 (.txt).")
        return None
    try:
        return analyze_text(
            text,
            long_word_threshold=int(st.session_state.long_word_threshold),
            long_sentence_words=DEFAULT_LONG_SENTENCE_WORDS,
            dictionary=get_dictionary(),
        )
    except ValueError as exc:
        st.error(str(exc))
        return None


def render_score(analysis: AnalysisResult) -> None:
    score = analysis.score
    if score.score is None:
        st.info("Для пустого текста индекс не рассчитывается.")
        return

    c1, c2 = st.columns([1, 2])
    with c1:
        metric_card("Условный индекс простоты", f"{score.score:.1f} / 100")
    with c2:
        st.markdown(
            f"""
            <div class="er-panel">
              <div class="er-metric-label">Вклад штрафов</div>
              <div style="color:#202733; font-size:0.95rem;">
                База: {score.base:.0f}<br>
                − длина предложений: {score.sentence_penalty:.1f}<br>
                − длинные слова: {score.long_word_penalty:.1f}<br>
                − формальные выражения: {score.formal_penalty:.1f}
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    st.markdown(
        '<p class="er-note">Это учебный показатель на основе простых правил, '
        "а не валидированная оценка понимания текста.</p>",
        unsafe_allow_html=True,
    )


def render_metrics_row(analysis: AnalysisResult) -> None:
    cols = st.columns(4)
    values = [
        ("Слов", str(analysis.word_count)),
        ("Предложений", str(analysis.sentence_count)),
        ("Слов в предложении (ср.)", f"{analysis.average_words_per_sentence:.2f}"),
        ("Макс. длина предложения", str(analysis.max_sentence_words)),
    ]
    for col, (label, value) in zip(cols, values):
        with col:
            metric_card(label, value)

    cols2 = st.columns(3)
    extra = [
        (
            "Длинные слова",
            f"{analysis.long_word_count} ({analysis.long_word_percent:.1f}%)",
        ),
        ("Формальные выражения", str(analysis.formal_expression_count)),
        (
            "Порог длинного слова",
            f"> {analysis.long_word_threshold} букв",
        ),
    ]
    for col, (label, value) in zip(cols2, extra):
        with col:
            metric_card(label, value)


def tab_analysis() -> None:
    st.subheader("Ввод текста")
    examples = get_examples()
    example_labels = {
        key: data["label"] for key, data in examples.items()
    }
    def on_example_change() -> None:
        chosen = st.session_state.example_choice
        if chosen in examples:
            _set_source_text(examples[chosen]["text"])

    st.selectbox(
        "Демонстрационный пример",
        options=["— не выбран —"] + list(example_labels.keys()),
        format_func=lambda k: example_labels.get(k, k),
        key="example_choice",
        on_change=on_example_change,
    )

    uploaded = st.file_uploader(
        "Загрузить файл .txt (UTF-8, до 1 МБ)",
        type=["txt"],
        accept_multiple_files=False,
    )
    if uploaded is not None:
        file_id = f"{uploaded.name}:{uploaded.size}"
        if st.session_state.get("_upload_id") != file_id:
            raw = uploaded.getvalue()
            try:
                decoded = decode_upload(raw, max_bytes=MAX_UPLOAD_BYTES)
                if len(decoded) > MAX_TEXT_CHARS:
                    st.error(
                        f"Текст превышает лимит {MAX_TEXT_CHARS} символов "
                        f"(сейчас {len(decoded)})."
                    )
                else:
                    st.session_state._upload_id = file_id
                    _set_source_text(decoded)
                    st.rerun()
            except ValueError as exc:
                st.error(str(exc))

    st.text_area(
        "Текст для анализа",
        height=220,
        placeholder="Вставьте русский текст…",
        help=f"Не более {MAX_TEXT_CHARS} символов. Исходный текст сохраняется без изменений.",
        key="source_text",
    )

    st.slider(
        "Порог длинного слова (букв)",
        min_value=8,
        max_value=20,
        key="long_word_threshold",
        help=(
            "Слово считается длинным, если число букв больше порога. "
            "Длина — лишь грубый индикатор и не делает слово автоматически трудным."
        ),
    )

    st.button("Проверить текст", type="primary", on_click=_on_check)

    error = st.session_state.pop("analysis_error", None)
    if error:
        st.warning(error)

    analysis: AnalysisResult | None = st.session_state.analysis
    if analysis is None:
        st.markdown(
            '<p class="er-desc">Нажмите «Проверить текст», чтобы увидеть метрики '
            "и подсветку.</p>",
            unsafe_allow_html=True,
        )
        return

    st.subheader("Результаты анализа")
    render_score(analysis)
    render_metrics_row(analysis)

    st.markdown(
        """
        <div class="er-legend er-panel">
          <span><i style="background:#FFF4CE"></i>Длинное предложение</span>
          <span><i style="background:#E8F1EE"></i>Длинное слово</span>
          <span><i style="background:#F2E8FF"></i>Формальное выражение</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div class="er-panel er-read">{highlight_text(analysis.text, analysis.issues)}</div>',
        unsafe_allow_html=True,
    )

    st.caption(
        "Подсветка использует метки рядом с фрагментами. "
        "Пользовательский текст экранируется и не интерпретируется как HTML."
    )

    st.subheader("Рекомендации")
    rows = recommendations_as_dicts(analysis.recommendations)
    if not rows:
        st.write("Замечаний по текущим правилам не найдено.")
    else:
        for row in rows:
            with st.container():
                st.markdown(f"**{row['kind']}** — `{row['fragment']}`")
                st.write(row["explanation"])
                st.write(row["action"])
                st.divider()

    st.subheader("Упрощённая версия")
    st.markdown(
        '<p class="er-note">Проверьте, что после редактирования сохранились '
        "смысл, факты и важные термины. Подстановки из словаря — не генеративный "
        "ИИ-переписыватель.</p>",
        unsafe_allow_html=True,
    )

    b1, b2 = st.columns(2)
    with b1:
        st.button(
            "Скопировать исходный текст",
            on_click=_set_edited_text,
            args=(analysis.text,),
        )
    with b2:
        st.button("Предложить замены", on_click=_show_suggestions)

    st.text_area(
        "Упрощённая версия",
        height=220,
        key="edited_text",
    )

    apply_error = st.session_state.pop("apply_error", None)
    if apply_error:
        st.error(apply_error)

    if st.session_state.show_suggestions:
        suggestions = list_suggestions(
            st.session_state.edited_text, dictionary=get_dictionary()
        )
        if not suggestions:
            st.info("Для текущей упрощённой версии подходящих замен не найдено.")
        else:
            st.write("Контекстные предложения (применяются только по вашему подтверждению):")
            for idx, item in enumerate(suggestions):
                cols = st.columns([3, 2, 1])
                with cols[0]:
                    st.write(f"«{item.original}» → «{item.replacement}»")
                with cols[1]:
                    st.caption(item.note or "Контекстная подсказка.")
                with cols[2]:
                    st.button(
                        "Применить",
                        key=f"apply_{idx}_{item.span.start}",
                        on_click=_apply_suggestion,
                        args=(item.span.start, item.span.end, item.original, item.replacement),
                    )

    if not is_blank(st.session_state.edited_text):
        edited_result = run_analysis(st.session_state.edited_text)
        if edited_result is not None:
            st.session_state.edited_analysis = edited_result

    st.subheader("Скачать")
    c1, c2 = st.columns(2)
    with c1:
        st.download_button(
            "Скачать упрощённый текст (.txt)",
            data=st.session_state.edited_text.encode("utf-8"),
            file_name="easyread_edited.txt",
            mime="text/plain; charset=utf-8",
            disabled=is_blank(st.session_state.edited_text),
        )
    with c2:
        report = build_html_report(
            analysis,
            st.session_state.edited_analysis
            if st.session_state.edited_analysis
            and not is_blank(getattr(st.session_state.edited_analysis, "text", ""))
            else None,
        )
        st.download_button(
            "Скачать HTML-отчёт",
            data=report.encode("utf-8"),
            file_name="easyread_report.html",
            mime="text/html; charset=utf-8",
        )


def tab_comparison() -> None:
    st.subheader("Сравнение исходной и упрощённой версий")
    original: AnalysisResult | None = st.session_state.analysis
    if original is None:
        st.info("Сначала выполните анализ на вкладке «Анализ текста».")
        return

    edited_text = st.session_state.edited_text
    if is_blank(edited_text):
        st.warning("Упрощённая версия пуста. Скопируйте исходный текст или отредактируйте его.")
        return

    edited = analyze_text(
        edited_text,
        long_word_threshold=original.long_word_threshold,
        long_sentence_words=original.long_sentence_words,
        dictionary=get_dictionary(),
    )
    st.session_state.edited_analysis = edited
    comparison = compare_metrics(original, edited)

    rows = [
        ("Число слов", "word_count", "", 0),
        ("Число предложений", "sentence_count", "", 0),
        ("Средняя длина предложения", "average_words_per_sentence", " слов", 2),
        ("Доля длинных слов", "long_word_percent", " %", 2),
        ("Формальные выражения", "formal_expression_count", "", 0),
        ("Условный индекс простоты", "simplicity_index", "", 1),
    ]

    table_data = []
    for label, key, unit, digits in rows:
        item = comparison[key]
        o, e, d = item["original"], item["edited"], item["delta"]

        def fmt(v, digits=digits, unit=unit):
            if v is None:
                return "—"
            if digits == 0:
                return f"{int(v)}{unit}"
            return f"{float(v):.{digits}f}{unit}"

        table_data.append(
            {
                "Показатель": label,
                "Исходный": fmt(o),
                "Упрощённый": fmt(e),
                "Изменение": fmt(d) if d is not None else "—",
            }
        )

    st.table(table_data)

    o_score = original.score.score
    e_score = edited.score.score
    if o_score is not None and e_score is not None:
        fig = go.Figure(
            data=[
                go.Bar(
                    x=["Исходный текст", "Упрощённая версия"],
                    y=[o_score, e_score],
                    marker_color=["#667085", "#2F6B57"],
                    text=[f"{o_score:.1f}", f"{e_score:.1f}"],
                    textposition="outside",
                )
            ]
        )
        fig.update_layout(
            title="Условный индекс простоты",
            yaxis=dict(range=[0, 100], title="Баллы"),
            xaxis_title="",
            height=380,
            margin=dict(l=40, r=20, t=50, b=40),
            plot_bgcolor="#FFFFFF",
            paper_bgcolor="#FFFFFF",
            font=dict(color="#202733"),
        )
        st.plotly_chart(fig, width="stretch")
    else:
        st.info("Индекс не рассчитан для одной из версий (пустой текст).")

    st.markdown(
        '<p class="er-note">Более высокий учебный балл не доказывает лучшее '
        "понимание текста и не гарантирует сохранность смысла.</p>",
        unsafe_allow_html=True,
    )


def tab_about() -> None:
    st.subheader("О проекте EasyRead")
    st.markdown(
        """
**Назначение.** EasyRead помогает автору учебного текста заметить длинные
предложения, потенциально громоздкие слова и формальные обороты, а затем
подготовить более понятную редакцию и сравнить две версии.

**Для кого.** Студенты и преподаватели, готовящие тексты для обучения,
презентаций и научных конференций.

**Правила анализа.**
- длинное предложение — более 20 слов;
- длинное слово — больше настраиваемого порога букв (по умолчанию 12);
- формальные выражения — по открытому словарю замен;
- «Условный индекс простоты» — прозрачная эвристика 0–100.

**Технологии.** Python 3.11+, Streamlit, Plotly, стандартная библиотека Python, pytest.

**Практическая польза.** Быстрый просмотр «узких мест» текста, объяснимые
рекомендации, ручное редактирование с контекстными подсказками, выгрузка отчёта.

**Ограничения.**
- правила не заменяют экспертную редакторскую правку;
- длина слова не равна сложности;
- словарь замен не обеспечивает полный семантический перепис;
- индекс — учебный, не валидированная метрика понимания;
- сегментация предложений может ошибаться на редких сокращениях.

**Гипотеза исследования.**
«Выделение длинных предложений и формальных выражений может помочь автору
подготовить более понятный учебный текст.»
        """
    )


def main() -> None:
    init_state()
    inject_styles()

    st.title("EasyRead")
    st.markdown(
        '<p class="er-sub">Анализ читаемости и понятности текста</p>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<p class="er-desc">Найдите длинные предложения, сложные слова и '
        "выражения, которые можно сделать понятнее.</p>",
        unsafe_allow_html=True,
    )

    tab1, tab2, tab3 = st.tabs(["Анализ текста", "Сравнение", "О проекте"])
    with tab1:
        tab_analysis()
    with tab2:
        tab_comparison()
    with tab3:
        tab_about()


if __name__ == "__main__":
    main()
