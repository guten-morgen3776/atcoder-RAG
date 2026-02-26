"""Gemini（google-genai）でキーワード・要約を抽出。"""
import json
import time

from google import genai
from google.genai import types

from src.config import get_gemini_api_key

GEMINI_MODEL = "gemini-2.5-flash-lite"


def extract_keywords_and_summary(
    problem_statement_ja: str,
    editorial_text: str | None,
) -> dict | None:
    """問題文と解説（あれば）から RAG 用の構造化データを抽出する。"""
    api_key = get_gemini_api_key()
    client = genai.Client(api_key=api_key)

    if editorial_text:
        context_msg = "以下の「問題文」と「公式解説」を読み込んでください。"
    else:
        context_msg = (
            "以下の「問題文」を読み込んでください。"
            "公式解説はありませんが、制約や条件から想定される解法を推論してください。"
        )

    editorial_block = editorial_text if editorial_text else "（なし）"
    prompt = f"""
あなたは競技プログラミングの熟練者です。
{context_msg}

以下の要件に従い、RAGシステムでの検索に最適化されたJSON形式で出力してください。

【抽出・推論要件】
1. algorithms: 必要なアルゴリズムやデータ構造の配列（例: ["幅優先探索", "累積和", "動的計画法"]）
2. keywords: 問題のシチュエーションや制約を表すキーワードの配列（例: ["木構造", "スライム", "最小値の最大化", "N<=10^5"]）
3. time_complexity: 想定解法の計算量（例: "O(N log N)", "O(N)"）
4. summary: ユーザーが「曖昧な記憶（自然言語）」で検索した時にヒットしやすいような、問題の概要と解法の簡潔な要約（200文字程度）

【出力形式】
必ず次のキーのみを持つJSONオブジェクトにしてください: algorithms, keywords, time_complexity, summary

【データ】
--- 問題文 ---
{problem_statement_ja[:30000]}

--- 公式解説 ---
{editorial_block[:30000]}
"""

    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                ),
            )
            text = response.text
            if not text or not text.strip():
                return None
            result = json.loads(text.strip())
            # キー名を設計どおりに統一（complexity -> time_complexity）
            if "complexity" in result and "time_complexity" not in result:
                result["time_complexity"] = result.pop("complexity")
            if not all(k in result for k in ("algorithms", "keywords", "time_complexity", "summary")):
                return None
            return result
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                print(f"\n[Rate limit] 429/RESOURCE_EXHAUSTED. Waiting 60s before retry (attempt {attempt + 1}/3)...")
                time.sleep(60)
                continue
            print(f"\n[CRITICAL LLM ERROR] {type(e).__name__}: {e}")
            return None
    print("\n[CRITICAL LLM ERROR] Max retries (3) exceeded.")
    return None
