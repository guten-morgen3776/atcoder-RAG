"""定数・.env 読み込み・AtCoder 用共通ヘッダー."""
import os
from pathlib import Path

from dotenv import load_dotenv

# プロジェクトルートで .env を探す（run_batch からも src からも動く）
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path)

# AtCoder Problems API
PROBLEMS_JSON_URL = "https://kenkoooo.com/atcoder/resources/problems.json"
PROBLEM_MODELS_URL = "https://kenkoooo.com/atcoder/resources/problem-models.json"

# ChromaDB デフォルト保存先
DEFAULT_DB_PATH = "./atcoder_rag_db"

# 中間JSON 保存先
DEFAULT_RAW_DATA_DIR = "data/raw"

# ログ・レポート保存先
DEFAULT_LOG_DIR = "logs"
DEFAULT_REPORT_FILENAME = "report.jsonl"
DEFAULT_UPDATE_REPORT_FILENAME = "update_report.jsonl"


def load_config() -> None:
    """`.env` を読み込み、API キー等を検証する。未設定なら ValueError."""
    load_dotenv(_env_path)
    key = os.environ.get("GEMINI_API_KEY")
    if not key or not key.strip():
        raise ValueError(".env に GEMINI_API_KEY が設定されていません。")


def get_headers() -> dict[str, str]:
    """AtCoder 用の共通ヘッダー（User-Agent, Accept-Language: ja）を返す。"""
    return {
        "User-Agent": "AtCoder-RAG-Pipeline/1.0",
        "Accept-Language": "ja,ja-JP;q=0.9,en-US;q=0.8,en;q=0.7",
    }


def get_gemini_api_key() -> str:
    """環境変数 GEMINI_API_KEY を返す。load_config() 後に使用すること。"""
    key = os.environ.get("GEMINI_API_KEY")
    if not key or not key.strip():
        raise ValueError("GEMINI_API_KEY が設定されていません。")
    return key.strip()

