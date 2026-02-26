"""ChromaDB 用 Embedding 関数と DB 操作。google-genai, 戻り値は [e.values for e in response.embeddings]。"""
from typing import Any

import chromadb
from google import genai
from google.genai import types

from src.config import get_gemini_api_key

COLLECTION_NAME = "atcoder_problems"
EMBEDDING_MODEL = "gemini-embedding-001"


class GeminiChromaEmbeddingFunction(chromadb.EmbeddingFunction):
    """ChromaDB 用。google-genai で embedding-001, task_type=RETRIEVAL_DOCUMENT。"""

    def __init__(self, api_key: str | None = None):
        key = api_key or get_gemini_api_key()
        self.client = genai.Client(api_key=key)

    def __call__(self, input: list[str]) -> list[list[float]]:
        if not input:
            return []
        response = self.client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=input,
            config=types.EmbedContentConfig(
                task_type="RETRIEVAL_DOCUMENT",
                title="AtCoder Problem",
            ),
        )
        return [e.values for e in response.embeddings]


def get_chroma_client(path: str) -> chromadb.PersistentClient:
    """ChromaDB の PersistentClient を返す。"""
    return chromadb.PersistentClient(path=path)


def get_existing_ids(collection: chromadb.Collection) -> set[str]:
    """既存のドキュメント id 一覧を返す（差分更新用）。"""
    data = collection.get(include=[])
    return set(data["ids"])


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
