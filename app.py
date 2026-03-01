"""Streamlit エントリ: 検索設定・検索実行・結果カード表示。"""
import streamlit as st

from src import load_config
from src.config import DEFAULT_DB_PATH
from src.embedding_db import COLLECTION_NAME
from src.embedding_db import get_chroma_client
from src.embedding_db import get_db_status
from src.problem_id import build_problem_id
from src.retriever import run_search
from src.retriever import search_similar_problems_by_id


def _check_db_available() -> bool:
    """ChromaDB が存在し、コレクションに1件以上入っているか。"""
    try:
        client = get_chroma_client(DEFAULT_DB_PATH)
        coll = client.get_collection(name=COLLECTION_NAME)
        return coll.count() > 0
    except Exception:
        return False


def _format_algorithms_keywords_with_highlight(
    algorithms_keywords: str,
    common_algorithms: list[str],
    common_keywords: list[str],
) -> str:
    """共通タグを太字でハイライトした表示用文字列を返す。"""
    terms = sorted(set(common_algorithms + common_keywords), key=len, reverse=True)
    display = algorithms_keywords
    for term in terms:
        if term:
            display = display.replace(term, f"**{term}**")
    return display


def main() -> None:
    st.set_page_config(page_title="AtCoder-RAG 検索", layout="wide")
    try:
        load_config()
    except ValueError as e:
        st.error(str(e))
        st.stop()

    if not _check_db_available():
        st.warning("DB がありません。先に run_batch で DB を構築してください。")
        st.stop()

    client = get_chroma_client(DEFAULT_DB_PATH)
    coll = client.get_collection(name=COLLECTION_NAME)
    db_status = get_db_status(coll)

    st.title("AtCoder-RAG")
    st.caption(
        f"現在の収録データ: {db_status['range_text']} (計 {db_status['count']} 問) ／ "
        f"収録大問: {', '.join(db_status['problem_indices']) or '—'}"
    )
    st.divider()

    tab_kw, tab_similar = st.tabs(["キーワードから検索", "問題番号から類題検索"])

    with tab_kw:
        with st.sidebar:
            st.subheader("検索設定")
            use_ai_expand = st.checkbox("AI クエリ拡張", value=True)
            diff_filter_on = st.checkbox("Difficulty で絞り込む", value=True)
            min_diff = st.number_input("Difficulty 最小値", value=300, step=50)
            max_diff = st.number_input("Difficulty 最大値", value=700, step=50)
            top_k = st.number_input("検索件数（トップK）", value=5, min_value=1, max_value=20, step=1)

        query = st.text_input("検索キーワード", placeholder="例: ダイクストラ 最短経路", key="kw_query")
        if st.button("検索", key="kw_btn"):
            if not (query or "").strip():
                st.info("キーワードを入力してください。")
            else:
                with st.spinner("検索中..."):
                    results = run_search(
                        query=query.strip(),
                        use_ai_expand=use_ai_expand,
                        diff_filter_on=diff_filter_on,
                        min_diff=int(min_diff),
                        max_diff=int(max_diff),
                        top_k=int(top_k),
                    )
                if not results:
                    st.info("該当する問題はありませんでした。")
                else:
                    for r in results:
                        with st.container():
                            st.markdown(f"### {r['title']}")
                            st.markdown(f"**URL:** [{r['url']}]({r['url']})")
                            diff = r.get("difficulty")
                            st.markdown(f"**Difficulty:** {diff if diff is not None else '—'}")
                            st.markdown(f"**アルゴリズム・キーワード:** {r['algorithms_keywords']}")
                            st.caption(f"類似度（距離）: {r.get('distance', '—')}")
                            st.divider()

    with tab_similar:
        st.subheader("問題を指定して類題を探す")
        contest_type = st.selectbox("コンテスト種別", ["ABC", "ARC", "AGC"], key="sim_contest_type")
        contest_number = st.number_input("コンテスト番号", value=126, min_value=1, step=1, key="sim_contest_num")
        problem_index = st.radio(
            "問題（大問）",
            options=["A", "B", "C", "D", "E", "F", "G", "Ex"],
            horizontal=True,
            key="sim_index",
        )
        diff_filter_on_sim = st.checkbox("Difficulty で絞り込む", value=True, key="sim_diff_on")
        min_diff_sim = st.number_input("Difficulty 最小値", value=300, step=50, key="sim_min_diff")
        max_diff_sim = st.number_input("Difficulty 最大値", value=700, step=50, key="sim_max_diff")
        top_k_sim = st.number_input(
            "検索件数（トップK）",
            value=5,
            min_value=1,
            max_value=20,
            step=1,
            key="sim_topk",
        )
        if st.button("この問題の類題を探す", key="sim_btn"):
            problem_id = build_problem_id(contest_type, int(contest_number), problem_index)
            with st.spinner("類題を検索中..."):
                results = search_similar_problems_by_id(
                    problem_id=problem_id,
                    top_k=int(top_k_sim),
                    diff_filter_on=diff_filter_on_sim,
                    min_diff=int(min_diff_sim),
                    max_diff=int(max_diff_sim),
                )
            if not results:
                st.warning(
                    f"問題 **{problem_id}** は収録されていないか、類題がありません。"
                    " 収録大問・コンテスト範囲をご確認ください。"
                )
            else:
                st.success(f"基準問題: **{problem_id}** の類題 {len(results)} 件")
                for r in results:
                    with st.container():
                        st.markdown(f"### {r['title']}")
                        st.markdown(f"**URL:** [{r['url']}]({r['url']})")
                        diff = r.get("difficulty")
                        st.markdown(f"**Difficulty:** {diff if diff is not None else '—'}")
                        common_alg = r.get("common_algorithms") or []
                        common_kw = r.get("common_keywords") or []
                        ak_display = _format_algorithms_keywords_with_highlight(
                            r["algorithms_keywords"],
                            common_alg,
                            common_kw,
                        )
                        st.markdown(f"**アルゴリズム・キーワード:** {ak_display}")
                        st.caption(f"類似度（距離）: {r.get('distance', '—')}")
                        st.divider()


if __name__ == "__main__":
    main()
