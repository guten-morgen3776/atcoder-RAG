import requests
from bs4 import BeautifulSoup
import time

def scrape_atcoder_problem(url):
    print(f"Target URL: {url}")
    
    # 1. HTMLの取得
    headers = {"User-Agent": "AtCoder-RAG-PoC/1.0"}
    res = requests.get(url, headers=headers)
    res.raise_for_status()
    soup = BeautifulSoup(res.text, "html.parser")

    # 2. 問題文の抽出 (日本語部分のみを狙い撃ち)
    # id="task-statement" 内の span.lang-ja を探す
    task_statement = soup.select_one("#task-statement span.lang-ja")
    
    if task_statement:
        # テキストのみ抽出（数式はLaTeX形式のまま残ることが多いのでLLMには好都合）
        raw_text = task_statement.get_text(separator="\n", strip=True)
        print("\n=== 問題文 (冒頭1000文字) ===")
        print(raw_text[:1000] + "...")
    else:
        print("日本語の問題文が見つかりませんでした。")
        raw_text = ""

    # 3. 解説リンクを探す
    # <a>タグの中で、hrefに "editorial" を含む、またはテキストが "解説" のものを探す
    editorial_link = None
    for a in soup.find_all("a", href=True):
        if "editorial" in a['href'] or "解説" in a.text:
            editorial_link = a['href']
            # 相対パスなら絶対パスに変換
            if editorial_link.startswith("/"):
                editorial_link = "https://atcoder.jp" + editorial_link
            break
    
    print("\n=== 解説リンク情報 ===")
    if editorial_link:
        print(f"Found URL: {editorial_link}")
        
        # リンク先がPDFかHTMLか判定してみる
        if editorial_link.endswith(".pdf"):
            print("Type: PDF (今回はスキップ対象)")
        else:
            print("Type: HTML (クローリング対象候補)")
            
            # 【実験】解説ページの中身を少し覗いてみる
            try:
                time.sleep(1) # マナーとしてウェイト
                ed_res = requests.get(editorial_link, headers=headers)
                ed_soup = BeautifulSoup(ed_res.text, "html.parser")
                
                # 解説ページは構造がバラバラだが、タイトルなどを表示してみる
                title = ed_soup.title.text if ed_soup.title else "No Title"
                print(f"Page Title: {title}")
                print("※ ここが「解説一覧」の場合は、さらにリンクを辿る処理が必要です")
            except Exception as e:
                print(f"解説ページ取得エラー: {e}")
    else:
        print("解説リンクが見つかりませんでした。")

    return raw_text, editorial_link

if __name__ == "__main__":
    # 実験1: 最近の問題 (ABC445 C) -> HTML解説のはず
    print("--- Case 1: Recent Problem ---")
    scrape_atcoder_problem("https://atcoder.jp/contests/abc445/tasks/abc445_c")
    # 実験2: 少し古い問題 (ABC100 C) -> PDF解説の可能性が高い
    print("\n\n--- Case 2: Older Problem ---")
    scrape_atcoder_problem("https://atcoder.jp/contests/abc100/tasks/abc100_c")