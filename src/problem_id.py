"""問題 ID の組み立て（コンテスト種別・番号・大問から problem_id を生成）。"""


def build_problem_id(contest_type: str, contest_number: int, problem_index: str) -> str:
    """
    入力から ChromaDB / AtCoder で用いる problem_id を組み立てる。

    形式: {contest_type_lower}{contest_number}_{problem_index_lower}
    例: ("ABC", 126, "C") -> "abc126_c"

    Args:
        contest_type: コンテスト種別（例: "ABC", "ARC", "AGC"）
        contest_number: コンテスト番号（例: 126）
        problem_index: 問題インデックス（例: "A", "C", "Ex"）

    Returns:
        一意の problem_id 文字列。
    """
    c = (contest_type or "").strip().lower()
    idx = (problem_index or "").strip().lower()
    return f"{c}{contest_number}_{idx}"
