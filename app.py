import csv
import io
import json
import random
import uuid
from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(
    page_title="VocabMaster - 英単語学習アプリ",
    page_icon="📘",
    layout="wide",
)

EIKEN_JSON_PATH = Path(__file__).with_name("eiken04.json")

FALLBACK_WORDS = [
    {
        "id": "w-1",
        "word": "Ubiquitous",
        "pos": "",
        "phonetic": "",
        "meaning": "至る所にある、遍在する",
        "example": "Smartphones have become ubiquitous in modern daily life.",
        "exampleJa": "スマートフォンは現代の日常生活において至る所に見られるようになった。",
        "mastered": False,
    },
]


def normalize_word_item(item: dict, idx: int = 0) -> dict | None:
    word = str(item.get("word") or item.get("term") or item.get("en") or "").strip()
    meaning = str(item.get("meaning") or item.get("definition") or item.get("ja") or "").strip()
    if not word or not meaning:
        return None

    example = str(
        item.get("sentence")
        or item.get("example")
        or item.get("text")
        or ""
    ).strip()
    example_ja = str(
        item.get("translation")
        or item.get("exampleJa")
        or item.get("example_ja")
        or ""
    ).strip()

    return {
        "id": str(item.get("id") or f"w-{idx}-{uuid.uuid4().hex[:6]}"),
        "word": word,
        "pos": str(item.get("pos") or "").strip(),
        "phonetic": str(item.get("phonetic") or "").strip(),
        "meaning": meaning,
        "example": example,
        "exampleJa": example_ja,
        "mastered": bool(item.get("mastered", False)),
    }


def load_eiken_json_words() -> list[dict]:
    if EIKEN_JSON_PATH.exists():
        try:
            raw = json.loads(EIKEN_JSON_PATH.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                normalized = []
                for idx, entry in enumerate(raw):
                    if isinstance(entry, dict):
                        norm = normalize_word_item(entry, idx)
                        if norm:
                            normalized.append(norm)
                if normalized:
                    return normalized
        except Exception as e:
            st.warning(f"eiken04.json の読み込み中に問題が発生しました: {e}")
    return [dict(w) for w in FALLBACK_WORDS]


def init_state() -> None:
    if "words" not in st.session_state:
        st.session_state.words = load_eiken_json_words()
    if "filter_mode" not in st.session_state:
        st.session_state.filter_mode = "all"
    if "fc_index" not in st.session_state:
        st.session_state.fc_index = 0
    if "fc_flipped" not in st.session_state:
        st.session_state.fc_flipped = False
    if "quiz_question" not in st.session_state:
        st.session_state.quiz_question = None
    if "quiz_options" not in st.session_state:
        st.session_state.quiz_options = []
    if "quiz_answered" not in st.session_state:
        st.session_state.quiz_answered = False
    if "quiz_selected_id" not in st.session_state:
        st.session_state.quiz_selected_id = None
    if "quiz_total" not in st.session_state:
        st.session_state.quiz_total = 0
    if "quiz_correct" not in st.session_state:
        st.session_state.quiz_correct = 0
    if "quiz_streak" not in st.session_state:
        st.session_state.quiz_streak = 0
    if "tts_nonce" not in st.session_state:
        st.session_state.tts_nonce = 0
    if "tts_text" not in st.session_state:
        st.session_state.tts_text = ""


def trigger_speak(text: str) -> None:
    if not text:
        return
    st.session_state.tts_text = text
    st.session_state.tts_nonce += 1


def render_tts_component() -> None:
    if not st.session_state.tts_text:
        return
    payload = json.dumps(st.session_state.tts_text)
    nonce = st.session_state.tts_nonce
    components.html(
        f"""
        <!-- nonce: {nonce} -->
        <script>
        (function() {{
            const text = {payload};
            if ('speechSynthesis' in window) {{
                window.speechSynthesis.cancel();
                const utter = new SpeechSynthesisUtterance(text);
                utter.lang = 'en-US';
                utter.rate = 0.95;
                const voices = window.speechSynthesis.getVoices();
                const enVoice = voices.find(v => v.lang === 'en-US' && v.name.includes('Google'))
                    || voices.find(v => v.lang.startsWith('en-'));
                if (enVoice) utter.voice = enVoice;
                window.speechSynthesis.speak(utter);
            }}
        }})();
        </script>
        """,
        height=0,
    )


def get_filtered_words() -> list[dict]:
    mode = st.session_state.filter_mode
    if mode == "review":
        return [w for w in st.session_state.words if not w.get("mastered")]
    if mode == "mastered":
        return [w for w in st.session_state.words if w.get("mastered")]
    return st.session_state.words


def generate_quiz_question() -> None:
    words = st.session_state.words
    pool = get_filtered_words()
    if len(words) < 4 or not pool:
        st.session_state.quiz_question = None
        st.session_state.quiz_options = []
        st.session_state.quiz_answered = False
        st.session_state.quiz_selected_id = None
        return

    prev_q = st.session_state.quiz_question
    candidates = [w for w in pool if not prev_q or w["id"] != prev_q["id"]] or pool
    target = random.choice(candidates)

    distractors_pool = [w for w in words if w["id"] != target["id"]]
    distractors = random.sample(distractors_pool, k=min(3, len(distractors_pool)))
    options = [target] + distractors
    random.shuffle(options)

    st.session_state.quiz_question = target
    st.session_state.quiz_options = options
    st.session_state.quiz_answered = False
    st.session_state.quiz_selected_id = None


def parse_import_text(raw_text: str) -> tuple[list[dict], str | None]:
    text = raw_text.strip()
    if not text:
        return [], "インポートするデータを入力またはファイル選択してください。"

    parsed: list[dict] = []

    if text.startswith("[") or text.startswith("{"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return [], "JSONの形式が正しくありません。構文を確認してください。"

        if isinstance(data, list):
            for idx, item in enumerate(data):
                if isinstance(item, dict):
                    norm = normalize_word_item(item, idx)
                    if norm:
                        parsed.append(norm)
        elif isinstance(data, dict):
            for idx, (k, v) in enumerate(data.items()):
                if isinstance(v, str):
                    norm = normalize_word_item({"word": k, "meaning": v}, idx)
                elif isinstance(v, dict):
                    norm = normalize_word_item({"word": k, **v}, idx)
                else:
                    norm = None
                if norm:
                    parsed.append(norm)
    else:
        delimiter = "\t" if "\t" in text else ","
        reader = csv.reader(io.StringIO(text), delimiter=delimiter)
        for idx, row in enumerate(reader):
            parts = [p.strip() for p in row]
            if len(parts) >= 2:
                word, meaning = parts[0], parts[1]
                if word and meaning and word.lower() != "word":
                    norm = normalize_word_item(
                        {
                            "word": word,
                            "meaning": meaning,
                            "sentence": parts[2] if len(parts) > 2 else "",
                            "translation": parts[3] if len(parts) > 3 else "",
                        },
                        idx,
                    )
                    if norm:
                        parsed.append(norm)

    if not parsed:
        return [], "有効な単語データが見つかりませんでした。形式を確認してください。"
    return parsed, None


def apply_imported_words(parsed_items: list[dict], mode: str) -> None:
    if mode == "replace":
        st.session_state.words = [
            {
                **item,
                "id": f"custom-{uuid.uuid4().hex[:8]}",
            }
            for item in parsed_items
        ]
    else:
        for item in parsed_items:
            idx = next(
                (i for i, w in enumerate(st.session_state.words) if w["word"].lower() == item["word"].lower()),
                -1,
            )
            if idx != -1:
                existing = st.session_state.words[idx]
                st.session_state.words[idx] = {
                    **existing,
                    "meaning": item["meaning"],
                    "example": item["example"] or existing.get("example", ""),
                    "exampleJa": item["exampleJa"] or existing.get("exampleJa", ""),
                    "pos": item["pos"] or existing.get("pos", ""),
                    "phonetic": item["phonetic"] or existing.get("phonetic", ""),
                }
            else:
                st.session_state.words.insert(
                    0,
                    {
                        **item,
                        "id": f"custom-{uuid.uuid4().hex[:8]}",
                    },
                )
    st.session_state.fc_index = 0
    st.session_state.fc_flipped = False
    generate_quiz_question()


def render_study_toolbar() -> None:
    total = len(st.session_state.words)
    mastered_count = sum(1 for w in st.session_state.words if w.get("mastered"))
    review_count = total - mastered_count
    pct = int((mastered_count / total) * 100) if total > 0 else 0

    col_prog, col_filter = st.columns([3, 2], vertical_alignment="center")
    with col_prog:
        st.markdown(f"**習得状況:** {mastered_count} / {total} 語習得 ({pct}%)")
        st.progress(pct / 100 if total > 0 else 0.0)

    with col_filter:
        filter_labels = {
            "all": f"すべて ({total})",
            "review": f"要復習 ({review_count})",
            "mastered": f"習得済み ({mastered_count})",
        }
        selected = st.radio(
            "フィルター",
            options=["all", "review", "mastered"],
            format_func=lambda k: filter_labels[k],
            horizontal=True,
            key="filter_radio",
            index=["all", "review", "mastered"].index(st.session_state.filter_mode),
        )
        if selected != st.session_state.filter_mode:
            st.session_state.filter_mode = selected
            st.session_state.fc_index = 0
            st.session_state.fc_flipped = False
            generate_quiz_question()
            st.rerun()


def render_flashcard_tab() -> None:
    render_study_toolbar()
    st.divider()

    filtered = get_filtered_words()
    if not filtered:
        st.info("現在選択されているフィルター条件に一致する単語はありません。")
        if st.button("すべての単語を表示する"):
            st.session_state.filter_mode = "all"
            st.session_state.fc_index = 0
            st.session_state.fc_flipped = False
            st.rerun()
        return

    if st.session_state.fc_index >= len(filtered) or st.session_state.fc_index < 0:
        st.session_state.fc_index = 0

    current = filtered[st.session_state.fc_index]

    top_l, top_c, top_r = st.columns([1, 2, 1], vertical_alignment="center")
    with top_l:
        st.caption(f"カード {st.session_state.fc_index + 1} / {len(filtered)}")
    with top_c:
        status_text = "✅ 習得済み" if current.get("mastered") else "🔶 要復習"
        st.markdown(f"<div style='text-align:center;font-weight:700;'>{status_text}</div>", unsafe_allow_html=True)
    with top_r:
        if st.button("🔀 シャッフル", use_container_width=True):
            random.shuffle(st.session_state.words)
            st.session_state.fc_index = 0
            st.session_state.fc_flipped = False
            st.rerun()

    with st.container(border=True):
        pos_str = f"`{current['pos']}` " if current.get("pos") else ""
        phonetic_str = f"<span style='color:#64748b;font-family:monospace;'>{current['phonetic']}</span>" if current.get("phonetic") else ""
        st.markdown(
            f"<div style='text-align:center;padding-top:8px;'>{pos_str}{phonetic_str}</div>"
            f"<h2 style='text-align:center;font-size:2.4rem;margin:8px 0 16px 0;'>{current['word']}</h2>",
            unsafe_allow_html=True,
        )

        b1, b2, b3 = st.columns([1, 1, 1])
        with b1:
            if st.button("🔊 単語を聞く", use_container_width=True):
                trigger_speak(current["word"])
        with b2:
            flip_label = "🙈 意味を隠す" if st.session_state.fc_flipped else "👀 意味を表示"
            if st.button(flip_label, type="primary", use_container_width=True):
                st.session_state.fc_flipped = not st.session_state.fc_flipped
                st.rerun()
        with b3:
            if current.get("example") and st.button("🔊 例文を聞く", use_container_width=True):
                trigger_speak(current["example"])

        if st.session_state.fc_flipped:
            st.divider()
            st.markdown(f"### {current['meaning']}")
            if current.get("example"):
                st.markdown(f"**例文:** {current['example']}")
            if current.get("exampleJa"):
                st.caption(current["exampleJa"])

    nav_l, nav_r = st.columns(2)
    with nav_l:
        if st.button("⬅️ 前へ", use_container_width=True):
            st.session_state.fc_index = (st.session_state.fc_index - 1) % len(filtered)
            st.session_state.fc_flipped = False
            st.rerun()
    with nav_r:
        if st.button("次へ ➡️", use_container_width=True):
            st.session_state.fc_index = (st.session_state.fc_index + 1) % len(filtered)
            st.session_state.fc_flipped = False
            st.rerun()

    act_l, act_r = st.columns(2)
    with act_l:
        if st.button("↩️ もう一度（要復習）", use_container_width=True):
            for w in st.session_state.words:
                if w["id"] == current["id"]:
                    w["mastered"] = False
                    break
            st.session_state.fc_flipped = False
            st.rerun()
    with act_r:
        if st.button("✅ 覚えた（習得済み）", type="primary", use_container_width=True):
            for w in st.session_state.words:
                if w["id"] == current["id"]:
                    w["mastered"] = True
                    break
            st.session_state.fc_flipped = False
            st.rerun()


def render_quiz_tab() -> None:
    render_study_toolbar()
    st.divider()

    if len(st.session_state.words) < 4:
        st.warning("4択クイズを行うには、単語帳に合計4語以上の単語が登録されている必要があります。")
        return

    pool = get_filtered_words()
    if not pool:
        st.info("現在のフィルター条件に一致する出題対象の単語がありません。「すべて」に切り替えてください。")
        return

    if st.session_state.quiz_question is None:
        generate_quiz_question()

    q = st.session_state.quiz_question
    if q is None:
        return

    m1, m2, m3, m4 = st.columns(4)
    acc_str = f"{int((st.session_state.quiz_correct / st.session_state.quiz_total) * 100)}%" if st.session_state.quiz_total > 0 else "- %"
    m1.metric("スコア", f"{st.session_state.quiz_correct} / {st.session_state.quiz_total}")
    m2.metric("正答率", acc_str)
    m3.metric("連続正解", f"{st.session_state.quiz_streak}問")
    with m4:
        st.write("")
        if st.button("🔄 スコアをリセット", use_container_width=True):
            st.session_state.quiz_total = 0
            st.session_state.quiz_correct = 0
            st.session_state.quiz_streak = 0
            generate_quiz_question()
            st.rerun()

    with st.container(border=True):
        st.caption("正しい日本語の意味を選択してください")
        pos_str = f"`{q['pos']}` " if q.get("pos") else ""
        phonetic_str = f"<span style='color:#64748b;font-family:monospace;'>{q['phonetic']}</span>" if q.get("phonetic") else ""
        st.markdown(
            f"<div style='text-align:center;'>{pos_str}{phonetic_str}</div>"
            f"<h2 style='text-align:center;font-size:2.1rem;margin:6px 0 14px 0;'>{q['word']}</h2>",
            unsafe_allow_html=True,
        )
        if st.button("🔊 発音を聞く"):
            trigger_speak(q["word"])

        st.markdown("---")
        for idx, opt in enumerate(st.session_state.quiz_options):
            disabled = st.session_state.quiz_answered
            label = f"{idx + 1}. {opt['meaning']}"
            if st.button(label, key=f"quiz_opt_{q['id']}_{opt['id']}", disabled=disabled, use_container_width=True):
                st.session_state.quiz_answered = True
                st.session_state.quiz_selected_id = opt["id"]
                st.session_state.quiz_total += 1
                if opt["id"] == q["id"]:
                    st.session_state.quiz_correct += 1
                    st.session_state.quiz_streak += 1
                else:
                    st.session_state.quiz_streak = 0
                st.rerun()

        if st.session_state.quiz_answered:
            st.divider()
            is_right = st.session_state.quiz_selected_id == q["id"]
            if is_right:
                st.success("正解です！")
            else:
                st.error(f"不正解（正解: {q['meaning']}）")
            if q.get("example"):
                st.write(f"**例文:** {q['example']}")
                if q.get("exampleJa"):
                    st.caption(q["exampleJa"])
            if st.button("次の問題へ ➡️", type="primary"):
                generate_quiz_question()
                st.rerun()


def render_manage_tab() -> None:
    col_imp, col_bak = st.columns([2, 1])

    with col_imp:
        with st.container(border=True):
            st.subheader("カスタム単語リストのインポート")
            st.caption(
                'JSON配列形式（`[{"word":"...", "meaning":"...", "sentence":"...", "translation":"..."}]`）、'
                'キーバリュー形式（`{"word":"meaning"}`）、またはCSV/TSVを貼り付けるかファイルを選択してください。'
            )

            uploaded = st.file_uploader("JSON / CSV / TXT ファイルを選択", type=["json", "csv", "txt"])
            default_text = ""
            if uploaded is not None:
                default_text = uploaded.getvalue().decode("utf-8", errors="replace")

            raw_text = st.text_area(
                "単語データ入力欄",
                value=default_text,
                height=150,
                placeholder='例:\n[\n  {"word": "Ubiquitous", "meaning": "至る所にある、遍在する", "sentence": "Smartphones have become ubiquitous in modern daily life.", "translation": "スマートフォンは現代の日常生活において至る所に見られるようになった。"}\n]',
            )
            import_mode = st.radio(
                "インポート方式",
                options=["append", "replace"],
                format_func=lambda m: "既存の単語に追加（重複更新）" if m == "append" else "リストを置き換え",
                horizontal=True,
            )
            if st.button("➕ 単語をインポート", type="primary"):
                parsed, err = parse_import_text(raw_text)
                if err:
                    st.error(err)
                else:
                    apply_imported_words(parsed, import_mode)
                    st.success(f"{len(parsed)}語の単語をインポートしました！")
                    st.rerun()

    with col_bak:
        with st.container(border=True):
            st.subheader("データ管理・バックアップ")
            st.caption("学習進捗とカスタム単語をJSONで保存・復元できます。")
            export_json = json.dumps(st.session_state.words, ensure_ascii=False, indent=2)
            st.download_button(
                label="⬇️ 進捗と単語をJSONで書き出し",
                data=export_json,
                file_name="vocabmaster_backup.json",
                mime="application/json",
                use_container_width=True,
            )
            st.write("")
            if st.button("🗑️ eiken04.json の初期データにリセット", use_container_width=True):
                st.session_state.words = load_eiken_json_words()
                st.session_state.fc_index = 0
                st.session_state.fc_flipped = False
                st.session_state.filter_mode = "all"
                st.session_state.quiz_total = 0
                st.session_state.quiz_correct = 0
                st.session_state.quiz_streak = 0
                generate_quiz_question()
                st.success("eiken04.json のデータにリセットしました。")
                st.rerun()

    st.divider()
    st.subheader(f"登録単語一覧 ({len(st.session_state.words)}語)")
    search_q = st.text_input("英単語・意味・例文で検索", placeholder="検索ワードを入力...")

    query = search_q.strip().lower()
    matched = [
        w
        for w in st.session_state.words
        if not query
        or query in w["word"].lower()
        or query in w["meaning"].lower()
        or query in (w.get("example") or "").lower()
        or query in (w.get("exampleJa") or "").lower()
    ]

    if not matched:
        st.info("一致する単語が見つかりませんでした。")
        return

    for item in matched:
        with st.container(border=True):
            c_word, c_info, c_status, c_del = st.columns([2, 4, 1.5, 1], vertical_alignment="center")
            with c_word:
                st.markdown(f"**{item['word']}**")
                meta = " ".join(filter(None, [item.get("pos"), item.get("phonetic")]))
                if meta:
                    st.caption(meta)
            with c_info:
                st.markdown(f"**{item['meaning']}**")
                if item.get("example"):
                    st.caption(item["example"])
                if item.get("exampleJa"):
                    st.caption(item["exampleJa"])
            with c_status:
                is_m = bool(item.get("mastered"))
                btn_txt = "✅ 習得済み" if is_m else "🔶 要復習"
                if st.button(btn_txt, key=f"toggle_{item['id']}", use_container_width=True):
                    item["mastered"] = not is_m
                    st.rerun()
            with c_del:
                if st.button("削除", key=f"del_{item['id']}", use_container_width=True):
                    st.session_state.words = [w for w in st.session_state.words if w["id"] != item["id"]]
                    st.session_state.fc_index = 0
                    generate_quiz_question()
                    st.rerun()


def main() -> None:
    init_state()
    render_tts_component()

    st.title("📘 VocabMaster — パーソナル英単語学習スタジオ")

    tab_fc, tab_quiz, tab_manage = st.tabs(["🗂️ フラッシュカード", "📝 4択クイズ", "🗄️ 単語帳管理"])
    with tab_fc:
        render_flashcard_tab()
    with tab_quiz:
        render_quiz_tab()
    with tab_manage:
        render_manage_tab()


if __name__ == "__main__":
    main()