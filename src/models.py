"""共通データ型: ProblemMeta, IntermediateProblem, GeminiExtract."""
from typing import TypedDict


class ProblemMeta(TypedDict):
    """AtCoder Problems API 取得後の1問分メタデータ."""

    id: str
    contest_id: str
    problem_index: str
    title: str
    url: str
    difficulty: int | None


class GeminiExtract(TypedDict):
    """LLM 抽出結果（algorithms, keywords, time_complexity, summary）. """

    algorithms: list[str]
    keywords: list[str]
    time_complexity: str
    summary: str


class IntermediateProblem(TypedDict, total=False):
    """中間JSON 1問分。data/raw/{problem_id}.json のスキーマ."""

    id: str
    title: str
    url: str
    difficulty: int | None
    problem_statement_ja: str
    has_official_editorial: bool
    editorial_text: str | None
    gemini_extract: GeminiExtract | None
