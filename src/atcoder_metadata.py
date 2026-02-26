"""AtCoder Problems API からメタデータ取得。"""
import requests

from src.config import PROBLEM_MODELS_URL, PROBLEMS_JSON_URL
from src.models import ProblemMeta


def fetch_problems_and_models() -> tuple[list[dict], dict]:
    """problems.json と problem-models.json を取得する。"""
    problems_res = requests.get(PROBLEMS_JSON_URL)
    problems_res.raise_for_status()
    problems_data = problems_res.json()

    models_res = requests.get(PROBLEM_MODELS_URL)
    models_res.raise_for_status()
    models_data = models_res.json()

    return problems_data, models_data


def _index_in_range(problem_index: str, start_index: str, end_index: str) -> bool:
    """問題インデックスが start_index 以上 end_index 以下か。A,B,...,Z の順。"""
    a = problem_index.upper()
    s = start_index.upper()
    e = end_index.upper()
    return len(a) == 1 and len(s) == 1 and len(e) == 1 and s <= a <= e


def list_problems_in_range(
    contest_id: str,
    start_index: str,
    end_index: str,
) -> list[ProblemMeta]:
    """指定コンテストの指定インデックス範囲（例: C〜F）の問題メタデータを列挙する。"""
    problems_data, models_data = fetch_problems_and_models()
    cid = contest_id.lower()
    result: list[ProblemMeta] = []

    for p in problems_data:
        if p.get("contest_id") != cid:
            continue
        idx = p.get("problem_index", "")
        if not _index_in_range(idx, start_index, end_index):
            continue
        problem_id = p["id"]
        difficulty = models_data.get(problem_id, {}).get("difficulty")
        url = f"https://atcoder.jp/contests/{cid}/tasks/{problem_id}"
        result.append(
            ProblemMeta(
                id=problem_id,
                contest_id=cid,
                problem_index=idx,
                title=p["title"],
                url=url,
                difficulty=difficulty,
            )
        )

    return result
