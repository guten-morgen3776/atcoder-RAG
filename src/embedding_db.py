"""ChromaDB 用 Embedding 関数と DB 操作。google-genai, 戻り値は [e.values for e in response.embeddings]。"""
import re
from typing import Any

import chromadb
from google import genai
from google.genai import types

from src.config import get_gemini_api_key

COLLECTION_NAME = "atcoder_problems"
EMBEDDING_MODEL = "gemini-embedding-001"
# Gemini Embedding API は1リクエストあたり最大100件まで
EMBEDDING_BATCH_SIZE = 100


class GeminiChromaEmbeddingFunction(chromadb.EmbeddingFunction):
    """ChromaDB 用。google-genai で embedding-001, task_type=RETRIEVAL_DOCUMENT。"""

    def __init__(self, api_key: str | None = None):
        key = api_key or get_gemini_api_key()
        self.client = genai.Client(api_key=key)

    def __call__(self, input: list[str]) -> list[list[float]]:
        if not input:
            return []
        result: list[list[float]] = []
        for i in range(0, len(input), EMBEDDING_BATCH_SIZE):
            batch = input[i : i + EMBEDDING_BATCH_SIZE]
            response = self.client.models.embed_content(
                model=EMBEDDING_MODEL,
                contents=batch,
                config=types.EmbedContentConfig(
                    task_type="RETRIEVAL_DOCUMENT",
                    title="AtCoder Problem",
                ),
            )
            result.extend([e.values for e in response.embeddings])
        return result


def embed_query_for_search(text: str, api_key: str | None = None) -> list[float]:
    """検索クエリ用のベクトルを1件だけ返す。task_type=RETRIEVAL_QUERY を指定。"""
    if not text or not text.strip():
        return []
    key = api_key or get_gemini_api_key()
    client = genai.Client(api_key=key)
    response = client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=[text.strip()],
        config=types.EmbedContentConfig(
            task_type="RETRIEVAL_QUERY",
        ),
    )
    if not response.embeddings:
        return []
    return list(response.embeddings[0].values)


def get_chroma_client(path: str) -> chromadb.PersistentClient:
    """ChromaDB の PersistentClient を返す。"""
    return chromadb.PersistentClient(path=path)


def get_existing_ids(collection: chromadb.Collection) -> set[str]:
    """既存のドキュメント id 一覧を返す（差分更新用）。"""
    data = collection.get(include=[])
    return set(data["ids"])


# 問題インデックスの表示順（A, B, C, D, E, F, G, Ex）
_PROBLEM_INDEX_ORDER = ("a", "b", "c", "d", "e", "f", "g", "ex")


def get_db_status(collection: chromadb.Collection) -> dict[str, Any]:
    """
    UI 用に収録データの件数・コンテスト範囲・収録大問を返す。

    Returns:
        count: 収録問題数
        range_text: 例 "ABC126 〜 ABC350"（複数種別の場合は "ABC126 〜 ABC350, ARC100 〜 ARC120" など）
        problem_indices: 収録されている大問のリスト（例: ["C", "D", "E", "F"]）、表示用に大文字でソート済み
    """
    data = collection.get(include=[])
    ids = data["ids"] or []
    count = len(ids)

    # id は "abc126_c" 形式 → contest_id "abc126", index "c"
    contest_nums: dict[str, list[int]] = {}  # prefix -> [num, ...]
    indices_set: set[str] = set()

    for pid in ids:
        if not pid or "_" not in pid:
            continue
        last_underscore = pid.rfind("_")
        contest_id = pid[:last_underscore]
        idx = pid[last_underscore + 1 :].lower()
        indices_set.add(idx)
        # contest_id を prefix + number に分解（abc126 -> abc, 126）
        m = re.match(r"^([a-z]+)(\d+)$", contest_id)
        if m:
            prefix, num_str = m.group(1), m.group(2)
            contest_nums.setdefault(prefix, []).append(int(num_str))

    range_parts = []
    for prefix in sorted(contest_nums.keys()):
        nums = contest_nums[prefix]
        if not nums:
            continue
        label = prefix.upper()
        range_parts.append(f"{label}{min(nums)} 〜 {label}{max(nums)}")
    range_text = ", ".join(range_parts) if range_parts else "—"

    # 大問を A,B,C,D,E,F,G,Ex の順でソート
    ordered = [x for x in _PROBLEM_INDEX_ORDER if x in indices_set]
    problem_indices = [s.upper() for s in ordered]

    return {
        "count": count,
        "range_text": range_text,
        "problem_indices": problem_indices,
    }


def _metadata_row(title: str, url: str, difficulty: int | None) -> dict[str, Any]:
    """Chroma はメタデータ値に str/int/float/bool のみ許可。None は str に変換。"""
    return {
        "title": title,
        "url": url,
        "difficulty": str(difficulty) if difficulty is not None else "",
    }


def upsert_problems(
    collection: chromadb.Collection,
    ids: list[str],
    documents: list[str],
    metadatas: list[dict[str, Any]],
) -> None:
    """指定 id / documents / metadatas で upsert する。"""
    # Chroma 用にメタデータの difficulty を str 化
    normalized = []
    for m in metadatas:
        d = m.get("difficulty")
        normalized.append({
            "title": m.get("title", ""),
            "url": m.get("url", ""),
            "difficulty": str(d) if d is not None else "",
        })
    collection.upsert(ids=ids, documents=documents, metadatas=normalized)


def build_combined_text(item: dict) -> str:
    """中間データ1件からベクトル化用の結合テキストを組み立てる。"""
    g = item.get("gemini_extract") or {}
    algorithms = g.get("algorithms") or []
    keywords = g.get("keywords") or []
    summary = g.get("summary") or ""
    return (
        f"タイトル: {item.get('title', '')}\n"
        f"アルゴリズム: {', '.join(algorithms)}\n"
        f"キーワード: {', '.join(keywords)}\n"
        f"要約: {summary}"
    )
