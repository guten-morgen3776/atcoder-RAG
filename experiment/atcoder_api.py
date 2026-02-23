import requests  
import json

def fetch_atcoder_problem_info(target_contest_id="abc340", target_problem_index="C"):
    print("Fetching data from AtCoder Problems API...")
    
    # 1. 問題リストの取得
    problems_url = "https://kenkoooo.com/atcoder/resources/problems.json"
    problems_res = requests.get(problems_url)
    problems_res.raise_for_status()
    problems_data = problems_res.json()
    
    # 2. 難易度(モデル)リストの取得
    models_url = "https://kenkoooo.com/atcoder/resources/problem-models.json"
    models_res = requests.get(models_url)
    models_res.raise_for_status()
    models_data = models_res.json()

    # ターゲット問題の検索
    target_problem = None
    for p in problems_data:
        if p["contest_id"] == target_contest_id and p["problem_index"] == target_problem_index:
            target_problem = p
            break
            
    if not target_problem:
        print("Problem not found.")
        return

    problem_id = target_problem["id"]
    
    # 難易度の取得（存在しない場合もあるので注意）
    difficulty_val = models_data.get(problem_id, {}).get("difficulty", None)

    # URLの構築
    problem_url = f"https://atcoder.jp/contests/{target_contest_id}/tasks/{problem_id}"

    # PoC用のスキーマ形式で出力
    extracted_data = {
        "id": problem_id,
        "title": target_problem["title"],
        "url": problem_url,
        "difficulty": difficulty_val,
    }

    print("\n--- 抽出結果 ---")
    print(json.dumps(extracted_data, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    fetch_atcoder_problem_info()