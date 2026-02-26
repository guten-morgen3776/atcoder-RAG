import google.generativeai as genai
import json
import os
from dotenv import load_dotenv

# 準備: 環境変数に GEMINI_API_KEY を設定するか、直接文字列で指定してください
# APIキーがないと動きません
# .envファイルから環境変数を読み込む
load_dotenv()

# 環境変数からAPIキーを取得
GOOGLE_API_KEY = os.environ.get("GEMINI_API_KEY")

# APIキーが取得できなかった場合のエラーハンドリング
if not GOOGLE_API_KEY:
    raise ValueError(".envファイルに GEMINI_API_KEY が設定されていません！")

genai.configure(api_key=GOOGLE_API_KEY)

# モデルの初期化 (2.5 Flashが使える環境なら 'gemini-2.5-flash' に変更推奨)
model = genai.GenerativeModel('gemini-1.5-flash')

def extract_keywords_with_gemini(problem_text, editorial_text=""):
    print("Gemini APIにデータを送信中...")

    # 解説の有無でプロンプトの文脈を少し変える
    if editorial_text:
        context_msg = "以下の「問題文」と「公式解説」を読み込んでください。"
    else:
        context_msg = "以下の「問題文」を読み込んでください。公式解説はありませんが、制約や条件から想定される解法を推論してください。"

    # プロンプトの設計
    # RAGで検索に引っかかりやすくするための「自然言語の要約」と「タグ」を両方作らせる
    prompt = f"""
    あなたは競技プログラミングの熟練者です。
    {context_msg}
    
    以下の要件に従い、RAGシステムでの検索に最適化されたJSON形式で出力してください。
    
    【抽出・推論要件】
    1. algorithms: 必要なアルゴリズムやデータ構造の配列（例: ["幅優先探索", "累積和", "動的計画法"]）
    2. keywords: 問題のシチュエーションや制約を表すキーワードの配列（例: ["木構造", "スライム", "最小値の最大化", "N<=10^5"]）
    3. complexity: 想定解法の計算量（例: O(N log N), O(N)）
    4. summary: ユーザーが「曖昧な記憶（自然言語）」で検索した時にヒットしやすいような、問題の概要と解法の簡潔な要約（200文字程度）


    【データ】
    --- 問題文 ---
    {problem_text}
    
    --- 公式解説 ---
    {editorial_text}
    """

    # JSON形式での出力を強制する設定
    generation_config = genai.GenerationConfig(
        response_mime_type="application/json"
    )

    try:
        response = model.generate_content(
            prompt,
            generation_config=generation_config
        )
        # JSON文字列を辞書型に変換
        result_json = json.loads(response.text)
        
        print("\n=== Gemini 抽出結果 ===")
        print(json.dumps(result_json, indent=2, ensure_ascii=False))
        return result_json
        
    except Exception as e:
        print(f"Gemini API エラー: {e}")
        return None

if __name__ == "__main__":
    # 【実験1】解説ありパターン (先ほどのABC445 Cのテキストを一部想定)
    print("【Case 1: 解説ありパターン】")
    test_problem_445 = r"""
配点 :
300
点
問題文
マス
1,
マス
2,\ldots,
マス
N
の
N
個のマスが
1
列に並んでいます。
マス
i
には整数
A _ i (i\le A_  i\le N)
が書かれています。
s=1,2,\ldots,N
のそれぞれについて、以下の問題を解いてください。
はじめ、マス
s
に駒を置く。「駒が置かれているマスに書かれている整数を
x
として、駒をマス
x
に移動させる」という操作を
10 ^ {100}
回行った後、駒が置かれているマスの番号を出力する。
制約
1\le N\le5\times10 ^ 5
i\le A _ i\le N\ (1\le i\le N)
入力はすべて整数
入力
入力は以下の形式で標準入力から与えられる。
N
A _ 1
A _ 2
\ldots
A _ N
出力
s=1,2,\ldots,N
に対する答えを、この順に空白を区切りとして一行に出力せよ。
入力例 1
7
2 4 7 5 5 6 7
出力例 1
5 5 7 5 5 6 7
s=1
のとき、駒は以下の図のように移動します。
駒がマス
5
に置かれているとき、操作...
    """
    test_editorial_445 = r"""
解説
by
MMNMM
一度 \(A _ i=i\) であるようなマス \(i\) に到達したらそこから移動することはありません。
そのようなマスに到達するまでは駒を毎回 \(1\) マス以上進めることになりますが、マス \(i\) からはじめて駒を毎回進めることはたかだか \(N-i\) 回しかできません。
\(N\leq10 ^ {100}\) なので、「\(10 ^ {100}\) 回操作を行う」ということは、「駒が進めなくなるまで操作を行う」と言い換えてよいです。
よって、次のようなアルゴリズムは正しい答えを出力します。
\(i=1,2,\ldots,N\) の順に、以下の手順を行う。
\(\operatorname{ans}\leftarrow i\) と初期化する。
\(\operatorname{ans}\neq A _ {\operatorname{ans}}\) である限り、\(\operatorname{ans}\leftarrow A _ {\operatorname{ans}}\) と更新する。
\(\operatorname{ans}\) を出力する。
このアルゴリズムの 2. の繰り返しは、それぞれの \(i\) で最悪 \(N-i\) 回行われます。
よって、このアルゴリズムの最悪時間計算量は \(\Theta(N ^ 2)\) となっており、このアルゴリズムを実装して提出しても実行時間制限を超過してしまいます。
ここで、答えの列 \((\operatorname{ans} _ 1,\operatorname{ans} _ 2,\ldots,\operatorname{ans} _ N)\) を後ろから求めることにすると、後ろの計算結果を利用できるようになります。
\(i=N,N-1,\ldots,2,1\) の順に、以下の手順を行う。
\(\operatorname{ans} _ i\leftarrow i\) と初期化する。
\(\opera...

    """
    extract_keywords_with_gemini(test_problem_445, test_editorial_445)

    print("\n" + "="*50 + "\n")

    # 【実験2】解説なしパターン (先ほどのABC100 Cのテキストを一部想定)
    print("【Case 2: 解説なしパターン】")
    test_problem_100 = r"""
AtCoder Beginner Contest 100 の開催にともなって, AtCoder 社では長さ
N
の数列
a =
{
a_1, a_2, a_3, ..., a_N
} が飾られることになった.
社員のすぬけ君は, この数列で遊んでみようと思った.
具体的には, 以下の操作をできるだけ多くの回数繰り返そうと思った.
1 \leq i \leq N
を満たす全ての
i
に対して, それぞれ「
a_i
の値を
2
で割る」「
a_i
の値を
3
倍する」のどちらかを行う.  
ただし, 全ての
i
に対して
3
倍することはできず, 操作後の
a_i
の値は整数でなければならない.
最大で何回の操作が可能か, 求めなさい.
制約
N
は
1
以上
10 \ 000
以下の整数
a_i
は
1
以上
1 \ 000 \ 000 \ 000
以下の整数
入力
入力は以下の形式で標準入力から与えられる.
N
a_1
a_2
a_3
...
a_N
出力
すぬけ君が行える最大の操作回数を出力しなさい.
入力例 1
3
5 2 4
出力例 1
3
最初,...
    """
    test_editorial_100 = "" # 解説なし
    extract_keywords_with_gemini(test_problem_100, test_editorial_100)