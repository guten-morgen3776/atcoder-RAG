"""Streamlit エントリ: 検索設定・検索実行・結果カード表示。"""
import streamlit as st

from src import load_config
from src.config import DEFAULT_DB_PATH
from src.embedding_db import get_chroma_client
from src.embedding_db import COLLECTION_NAME
from src.retriever import run_search


def _check_db_available() -> bool:
    """ChromaDB が存在し、コレクションに1件以上入っているか。"""
    try:
        client = get_chroma_client(DEFAULT_DB_PATH)
        coll = client.get_collection(name=COLLECTION_NAME)
        return coll.count() > 0
    except Exception:
        return False


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

    with st.sidebar:
        st.subheader("検索設定")
        use_ai_expand = st.checkbox("AI クエリ拡張", value=True)
        diff_filter_on = st.checkbox("Difficulty で絞り込む", value=True)
        min_diff = st.number_input("Difficulty 最小値", value=300, step=50)
        max_diff = st.number_input("Difficulty 最大値", value=700, step=50)
        top_k = st.number_input("検索件数（トップK）", value=5, min_value=1, max_value=20, step=1)

    st.title("AtCoder 過去問 類似検索")
    query = st.text_input("検索キーワード", placeholder="例: ダイクストラ 最短経路")
    if st.button("検索"):
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


if __name__ == "__main__":
    main()
