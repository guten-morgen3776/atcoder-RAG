import requests
from bs4 import BeautifulSoup

def scrape_official_editorial(contest_id, problem_id):
    editorial_list_url = f"https://atcoder.jp/contests/{contest_id}/tasks/{problem_id}/editorial"
    print(f"--- ターゲット解説一覧: {editorial_list_url} ---")
    
    # 【修正点1】 日本語ページを強制するために Accept-Language を追加
    headers = {
        "User-Agent": "AtCoder-RAG-PoC/1.2",
        "Accept-Language": "ja,ja-JP;q=0.9,en-US;q=0.8,en;q=0.7"
    }
    res = requests.get(editorial_list_url, headers=headers)
    
    if res.status_code != 200:
        print("【結果】解説一覧ページが存在しません。スキップします。")
        return None

    soup = BeautifulSoup(res.text, "html.parser")

    editorial_url = None
    
    # 【修正点2】 より強固な検索ロジック
    # href に '/editorial/' を含む全ての <a> タグを調べる
    for a_tag in soup.find_all('a', href=True):
        href = a_tag['href']
        
        # 「解説一覧ページ自身」へのリンクは除外
        if href.endswith('/editorial'):
            continue
            
        if '/editorial/' in href:
            # <a>タグの親要素（<li> や <div> など）のテキスト全体を取得
            parent_text = a_tag.parent.get_text()
            # その行に「公式」か「Official」が含まれていれば、間違いなく公式解説！
            if '公式' in parent_text or 'Official' in parent_text:
                editorial_url = href
                break
    
    if not editorial_url:
        print("【結果】公式のHTML解説が見つかりません（外部ブログやPDFのみ）。スキップします。")
        return None

    # 相対パスなら絶対パスに変換
    if editorial_url.startswith('/'):
        editorial_url = "https://atcoder.jp" + editorial_url

    print(f"【結果】公式解説ページを発見: {editorial_url}")

    # 4. 公式解説本文の取得
    print("解説本文を取得中...")
    ed_res = requests.get(editorial_url, headers=headers)
    ed_soup = BeautifulSoup(ed_res.text, "html.parser")
    
    # 本文エリアの抽出（不要なヘッダー・フッターを除外）
    main_content = ed_soup.find("div", id="main-container")
    
    if main_content:
        text = main_content.get_text(separator="\n", strip=True)
        print("\n=== 解説本文 (冒頭500文字) ===")
        print(text[:500] + "...")
        return text
    else:
        print("本文のコンテナが見つかりませんでした。")
        return None

if __name__ == "__main__":
    # 実験1: 最新の問題 (ABC445 C)
    print("【Case 1: 調査してくれた最新の問題 (ABC445 C)】")
    scrape_official_editorial("abc445", "abc445_c")

    print("\n\n" + "="*50 + "\n\n")

    # 実験2: 古い問題 (ABC100 C) - 公式HTMLがない想定
    print("【Case 2: 古い問題 (ABC100 C)】")
    scrape_official_editorial("abc100", "abc100_c")