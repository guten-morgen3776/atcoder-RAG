from google import genai
from google.genai import types
import chromadb
import os
import json
from dotenv import load_dotenv

# .env読み込み
load_dotenv()
GOOGLE_API_KEY = os.environ.get("GEMINI_API_KEY")

if not GOOGLE_API_KEY:
    raise ValueError("GEMINI_API_KEYが設定されていません")

# --- 1. Gemini Embedding 関数の定義 ---
# --- 1. 新しいSDKを使ったEmbedding関数の定義 ---
class GeminiEmbeddingFunction(chromadb.EmbeddingFunction):
    def __init__(self, api_key):
        # 新しいクライアントの初期化
        self.client = genai.Client(api_key=api_key)
        
    def __call__(self, input: list[str]) -> list[list[float]]:
        # 新しいSDKの記法でEmbeddingを呼び出す
        response = self.client.models.embed_content(
            model='gemini-embedding-001',
            contents=input,
            config=types.EmbedContentConfig(
                task_type="RETRIEVAL_DOCUMENT",
                title="AtCoder Problem"
            )
        )
        return [e.values for e in response.embeddings]

# --- 2. データの準備（先ほどの実験結果） ---
# 本来はファイルから読み込みますが、実験なのでここに書きます
mock_data = [
    {
        "id": "abc445_c",
        "title": "C - Sugoroku Destination",
        "url": "https://atcoder.jp/contests/abc445/tasks/abc445_c",
        "difficulty": 500, # 仮
        "gemini_output": {
            "algorithms": ["動的計画法", "メモ化再帰", "固定点探索"],
            "keywords": ["マス目", "数列", "長期シミュレーション", "後ろからのDP", "N<=5e5", "A_i>=i", "繰り返し操作"],
            "complexity": "O(N)",
            "summary": "N個のマスがあり、各マスiにはA_iが書かれ、駒をiからA_iへ移動する操作を10^100回行う。各開始マスsに対し最終到達点を求める。A_i >= iより必ず固定点A_k=kに到達する。愚直なシミュレーションはO(N^2)で間に合わないため、後ろのマスから動的計画法で計算する。"
        }
    },
    {
        "id": "abc100_c",
        "title": "C - *3 or /2",
        "url": "https://atcoder.jp/contests/abc100/tasks/abc100_c",
        "difficulty": 623,
        "gemini_output": {
            "algorithms": ["素因数分解", "算術", "貪欲法"],
            "keywords": ["数列", "操作回数最大化", "2の因数", "偶数判定", "N<=10^4", "a_i<=10^9", "全て3倍は不可"],
            "complexity": "O(N log A_max)",
            "summary": "長さNの数列aが与えられ、各要素を2で割る（偶数の場合）か3倍する操作を全要素に行う1ラウンドを最大何回繰り返せるかを問う。ただし、全ての要素を3倍する選択は禁止される。この制約により、各ラウンドでは必ず少なくとも1つの偶数を2で割る必要がある。3倍操作は2の因数に影響しないため、最大操作回数は数列の各要素が持つ2の因数の総和となる。"
        }
    }
]

def setup_database():
    print("--- データベース構築開始 ---")
    
    # ChromaDBのクライアント初期化（カレントディレクトリに保存）
    client = chromadb.PersistentClient(path="./atcoder_rag_db")
    
    # Embedding関数の準備
    emb_fn = GeminiEmbeddingFunction(api_key=GOOGLE_API_KEY)
    
    # コレクション（テーブルのようなもの）の作成
    # get_or_create なので再実行してもエラーになりません
    collection = client.get_or_create_collection(
        name="atcoder_problems",
        embedding_function=emb_fn
    )

    # データをChromaDB用のリストに変換
    ids = []
    documents = [] # ベクトル化されるテキスト
    metadatas = [] # 検索結果に表示する付帯情報

    for item in mock_data:
        ids.append(item["id"])
        
        # 【重要】ベクトル化するテキストを作成
        # アルゴリズム、キーワード、要約を全部つなげて1つの文章にする
        combined_text = f"""
        タイトル: {item['title']}
        アルゴリズム: {', '.join(item['gemini_output']['algorithms'])}
        キーワード: {', '.join(item['gemini_output']['keywords'])}
        要約: {item['gemini_output']['summary']}
        """
        documents.append(combined_text)
        
        # UI表示用に必要なメタデータ
        metadatas.append({
            "title": item["title"],
            "url": item["url"],
            "difficulty": item["difficulty"]
        })

    # DBにUpsert（あれば更新、なければ挿入）
    collection.upsert(
        ids=ids,
        documents=documents,
        metadatas=metadatas
    )
    
    print(f"完了: {len(ids)}件のデータを保存しました。")
    return collection

def search_test(collection, query_text):
    print(f"\n--- 検索テスト: 「{query_text}」 ---")
    
    # クエリも同じモデルでベクトル化して検索
    results = collection.query(
        query_texts=[query_text],
        n_results=1 # トップ1件を取得
    )
    
    # 結果表示
    if results['ids']:
        top_id = results['ids'][0][0]
        top_meta = results['metadatas'][0][0]
        distance = results['distances'][0][0] # 距離（近いほど0に近い）
        
        print(f"Hit ID: {top_id}")
        print(f"Title:  {top_meta['title']}")
        print(f"URL:    {top_meta['url']}")
        print(f"Score:  {distance:.4f}") # ChromaのデフォルトはL2距離
    else:
        print("ヒットなし")

if __name__ == "__main__":
    # DB構築
    col = setup_database()
    
    # 実験: ユーザーが入力しそうな「曖昧な検索クエリ」
    
    # Case 1: ABC100 C を狙った検索
    # 「2で割る」という操作や「3倍」というキーワードが含まれる
    search_test(col, "数字を2で割り続ける操作の回数を求める問題")
    
    # Case 2: ABC445 C を狙った検索
    # 「後ろから」や「シミュレーション」といったニュアンス
    search_test(col, "巨大な回数の操作をするけど、後ろから考えればいいやつ")
    
    # Case 3: 全く関係ないクエリ（どちらに近いか？）
    search_test(col, "グラフの最短経路問題")