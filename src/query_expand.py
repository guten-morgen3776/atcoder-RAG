"""検索クエリのLLM拡張。曖昧なキーワードからアルゴリズム・専門用語を列挙する。"""
from google import genai
from google.genai import types

from src.config import get_gemini_api_key

GEMINI_MODEL = "gemini-2.5-flash"

SYSTEM_PROMPT = """ユーザーから競技プログラミング（AtCoder）の問題を探すための曖昧な検索キーワードが与えられます。
この検索語句から、関連性の高い「アルゴリズム名」「データ構造」「解法に関連する専門用語」を5〜10個程度予測し、スペース区切りで出力してください。
文章による解説や要約は一切含めず、キーワードのみを出力してください。"""


def expand_query_with_llm(query: str, api_key: str | None = None) -> str:
    """曖昧な検索語句から、アルゴリズム・キーワードのみをスペース区切りで生成する。失敗時は元の query を返す。"""
    if not query or not query.strip():
        return query or ""
    key = api_key or get_gemini_api_key()
    client = genai.Client(api_key=key)
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=f"{SYSTEM_PROMPT}\n\n検索キーワード: {query.strip()}",
            config=types.GenerateContentConfig(
                temperature=0.0,
            ),
        )
        text = (response.text or "").strip()
        if text:
            return " ".join(text.split())
        return query.strip()
    except Exception:
        return query.strip()
