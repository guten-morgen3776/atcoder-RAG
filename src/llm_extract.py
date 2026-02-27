"""Gemini（google-genai）でキーワード・要約を抽出。"""
import json
import time
from pydantic import BaseModel, Field

from google import genai
from google.genai import types

from src.config import get_gemini_api_key

GEMINI_MODEL = "gemini-2.5-flash"

# ---期待するJSONの構造（スキーマ）を定義 ---
class ExtractionResult(BaseModel):
    algorithms: list[str] = Field(
        description="必要なアルゴリズムやデータ構造の配列（例: ['幅優先探索', '累積和', '動的計画法']）"
    )
    keywords: list[str] = Field(
        description="問題のシチュエーションや制約を表すキーワードの配列（例: ['木構造', 'スライム', '最小値の最大化', 'N<=10^5']）"
    )
    time_complexity: str = Field(
        description="想定解法の計算量（例: 'O(N log N)', 'O(N)'）"
    )
    summary: str = Field(
        description="ユーザーが「曖昧な記憶（自然言語）」で検索した時にヒットしやすいような、問題の概要と解法の簡潔な要約（200文字程度）"
    )

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
    
    # プロンプトから「出力形式」の指定を削除（Pydanticスキーマで強制するため不要になります）
    prompt = f"""
あなたは競技プログラミングの熟練者です。
{context_msg}

RAGシステムでの検索に最適化された情報を抽出してください。

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
                    response_schema=ExtractionResult, # ★ここが超重要：定義したスキーマを渡す
                    temperature=0.0, # ★追加：抽出タスクなので出力を決定論的に近づける
                ),
            )
            text = response.text
            if not text or not text.strip():
                return None
                
            # スキーマで強制されているため、ここでは確実にパース可能なJSONが返ってきます
            result = json.loads(text.strip())
            return result
            
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                print(f"\n[Rate limit] 429/RESOURCE_EXHAUSTED. Waiting 60s before retry (attempt {attempt + 1}/3)...")
                time.sleep(60)
                continue
            
            # JSONDecodeErrorが起きた場合のデバッグ用ログ（Structured Outputsを使えば基本起きません）
            if isinstance(e, json.JSONDecodeError):
                print(f"\n[CRITICAL LLM ERROR] JSON Parse Error: {e}")
                print(f"Raw Output: {text}")
            else:
                print(f"\n[CRITICAL LLM ERROR] {type(e).__name__}: {e}")
                
            return None
            
    print("\n[CRITICAL LLM ERROR] Max retries (3) exceeded.")
    return None
