"""問題文・解説のスクレイピング。AtCoder への全リクエスト前に time.sleep(2)、ヘッダーに Accept-Language: ja。"""
import time

import requests
from bs4 import BeautifulSoup

from src.config import get_headers
from src.models import ProblemMeta

ATCODER_SLEEP_SEC = 2


def fetch_problem_statement(url: str) -> str:
    """問題ページを取得し、#task-statement span.lang-ja のテキストを抽出する。"""
    time.sleep(ATCODER_SLEEP_SEC)
    res = requests.get(url, headers=get_headers())
    res.raise_for_status()
    soup = BeautifulSoup(res.text, "html.parser")
    task_statement = soup.select_one("#task-statement span.lang-ja")
    if task_statement:
        return task_statement.get_text(separator="\n", strip=True)
    return ""


def get_official_editorial_text(contest_id: str, problem_id: str) -> str | None:
    """解説一覧ページにアクセスし、公式HTML解説があれば本文を返す。PDF・外部のみなら None。"""
    editorial_list_url = (
        f"https://atcoder.jp/contests/{contest_id}/tasks/{problem_id}/editorial"
    )
    time.sleep(ATCODER_SLEEP_SEC)
    res = requests.get(editorial_list_url, headers=get_headers())
    if res.status_code != 200:
        return None

    soup = BeautifulSoup(res.text, "html.parser")
    editorial_url = None

    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        if href.endswith("/editorial"):
            continue
        if "/editorial/" in href:
            parent_text = a_tag.parent.get_text() if a_tag.parent else ""
            if "公式" in parent_text or "Official" in parent_text:
                editorial_url = href
                break

    if not editorial_url:
        return None

    if editorial_url.startswith("/"):
        editorial_url = "https://atcoder.jp" + editorial_url

    time.sleep(ATCODER_SLEEP_SEC)
    ed_res = requests.get(editorial_url, headers=get_headers())
    ed_res.raise_for_status()
    ed_soup = BeautifulSoup(ed_res.text, "html.parser")
    main_content = ed_soup.find("div", id="main-container")
    if main_content:
        return main_content.get_text(separator="\n", strip=True)
    return None


def scrape_one_problem(meta: ProblemMeta) -> tuple[str, str | None]:
    """1問分のスクレイピング: 問題文取得 → sleep(2) → 解説取得。"""
    problem_statement = fetch_problem_statement(meta["url"])
    editorial_text = get_official_editorial_text(meta["contest_id"], meta["id"])
    return problem_statement, editorial_text
