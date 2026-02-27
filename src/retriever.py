"""検索オーケストレーション: クエリ拡張・ベクトル化・Chroma 取得・Difficulty フィルタ・結果整形。"""
import json
from pathlib import Path

from src.config import DEFAULT_DB_PATH, DEFAULT_RAW_DATA_DIR
from src.embedding_db import (
    COLLECTION_NAME,
    GeminiChromaEmbeddingFunction,
    embed_query_for_search,
    get_chroma_client,
)
from src.models import IntermediateProblem
from src.query_expand import expand_query_with_llm

# Chroma で Difficulty フィルタする件数を確保するため、多めに取得する件数
FETCH_SIZE_WHEN_FILTER = 50


def _parse_difficulty(meta: dict) -> int | None:
    """Chroma メタデータの difficulty（str または空文字）を int に変換。"""
    d = meta.get("difficulty")
    if d is None or d == "":
        return None
    try:
        return int(d)
    except (ValueError, TypeError):
        return None


def _load_raw_json(problem_id: str, raw_data_dir: str) -> IntermediateProblem | None:
    """data/raw/{problem_id}.json を読み込む。"""
    p = Path(raw_data_dir) / f"{problem_id}.json"
    if not p.exists():
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _format_algorithms_keywords(raw: IntermediateProblem | None) -> str:
    """中間 JSON の gemini_extract からアルゴリズム・キーワードを整形して返す。"""
    if not raw:
        return "—"
    g = raw.get("gemini_extract") or {}
    algorithms = g.get("algorithms") or []
    keywords = g.get("keywords") or []
    parts = []
    if algorithms:
        parts.append("アルゴリズム: " + ", ".join(algorithms))
    if keywords:
        parts.append("キーワード: " + ", ".join(keywords))
    return " | ".join(parts) if parts else "—"


def run_search(
    query: str,
    use_ai_expand: bool,
    diff_filter_on: bool,
    min_diff: int,
    max_diff: int,
    top_k: int,
    db_path: str = DEFAULT_DB_PATH,
    raw_data_dir: str = DEFAULT_RAW_DATA_DIR,
) -> list[dict]:
    """
    UI から呼ぶ検索エントリ。クエリ拡張 → ベクトル化 → Chroma 取得 → Difficulty フィルタ（Python側）→ 整形。
    返却リストの各要素: id, title, url, difficulty, algorithms_keywords, distance
    """
    search_text = expand_query_with_llm(query) if use_ai_expand else (query or "").strip()
    if not search_text:
        return []

    query_vector = embed_query_for_search(search_text)
    if not query_vector:
        return []

    client = get_chroma_client(db_path)
    emb_fn = GeminiChromaEmbeddingFunction()
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=emb_fn,
    )

    n_results = FETCH_SIZE_WHEN_FILTER if diff_filter_on else top_k
    result = collection.query(
        query_embeddings=[query_vector],
        n_results=n_results,
        include=["metadatas", "documents", "distances"],
    )

    ids = result["ids"][0] if result["ids"] else []
    metadatas = result["metadatas"][0] if result["metadatas"] else []
    distances = result["distances"][0] if result["distances"] else []

    rows: list[tuple[str, dict, float]] = []
    for i, (pid, meta, dist) in enumerate(zip(ids, metadatas, distances)):
        meta = meta or {}
        diff_val = _parse_difficulty(meta)
        if diff_filter_on:
            if diff_val is None or diff_val < min_diff or diff_val > max_diff:
                continue
        rows.append((pid, meta, dist))

    if diff_filter_on:
        rows = rows[:top_k]
    else:
        rows = rows[:top_k]

    out: list[dict] = []
    for pid, meta, dist in rows:
        raw = _load_raw_json(pid, raw_data_dir)
        out.append({
            "id": pid,
            "title": meta.get("title", "—"),
            "url": meta.get("url", ""),
            "difficulty": _parse_difficulty(meta),
            "algorithms_keywords": _format_algorithms_keywords(raw),
            "distance": dist,
        })
    return out
