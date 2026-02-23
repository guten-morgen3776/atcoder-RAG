# AtCoder RAG ベクトルDB一括構築パイプライン 設計書

本設計書は、`make_DB_plan.md` の大方針に基づき、**特定コンテスト（例: ABC400 の C〜F 問題）を指定して一括でDB化する自動化パイプライン**のモジュール構成・関数仕様・バッチフローを定義する。  
実験コード（`experiment/` 内の `.py`）の処理ロジックとAPIの使い方をベースとし、技術的制約（スクレイピング間隔・言語ヘッダー・SDK・ChromaDB仕様・APIキー管理）を厳守する。

---

## 1. 前提・参照

- **大方針**: `make_DB_plan.md` の 1〜4 節の内容は変更しない。
- **技術制約（必ず守る）**:
  1. **スクレイピングの優しさ**: AtCoder への `requests.get` の**間には必ず `time.sleep(2)` を挟む**。
  2. **言語設定**: 英語ページへリダイレクトされないよう、リクエストヘッダーに **`Accept-Language: ja`**（推奨: `"Accept-Language": "ja,ja-JP;q=0.9,en-US;q=0.8,en;q=0.7"`）を**必ず**含める。
  3. **Gemini SDK**: 古い `google.generativeai` ではなく、**`google-genai`** パッケージを使用する。
  4. **ChromaDB 次元エラー回避**: Embedding 関数の戻り値は、単一リストではなく **`return [e.values for e in response.embeddings]`** のように複数件対応のリスト内包表記とする。
  5. **セキュリティ**: API キーは直書きせず、**`.env` から読み込む**（`python-dotenv` の `load_dotenv()` と `os.environ.get("GEMINI_API_KEY")`）。

---

## 2. モジュール分割（ファイル構成）

```
atcoder-RAG/
├── make_DB_plan.md          # 既存: 大方針
├── pipeline_design.md       # 本設計書
├── .env                     # GEMINI_API_KEY 等（gitignore 推奨）
├── requirements.txt         # 依存関係
│
├── src/                     # パイプライン本体
│   ├── __init__.py
│   ├── config.py            # 定数・.env 読み込み
│   ├── atcoder_metadata.py  # メタデータ取得（Problems API）
│   ├── scrape.py            # 問題文・解説のスクレイピング
│   ├── llm_extract.py       # Gemini によるキーワード/要約抽出
│   ├── embedding_db.py      # Embedding 関数・ChromaDB 操作
│   └── models.py            # 共通データ型（TypedDict / dataclass）
│
├── data/                    # 中間データ（任意で gitignore）
│   └── raw/                 # 1問1JSON の中間ファイル
│       └── {problem_id}.json
│
├── atcoder_rag_db/          # ChromaDB 永続化先（make_DB_plan 通り）
│
└── run_batch.py             # メインのバッチ処理スクリプト（CLI 入口）
```

| ファイル | 責務 |
|----------|------|
| `config.py` | ベースURL、AtCoder/Problems API のURL、`.env` 読み込み、共通ヘッダー（User-Agent, Accept-Language）の定義。 |
| `models.py` | 中間JSON・Chroma 投入用のデータ構造（問題 id, title, url, difficulty, 問題文, 解説有無, 解説本文, LLM 抽出結果 など）を TypedDict または dataclass で定義。 |
| `atcoder_metadata.py` | AtCoder Problems API から problems.json / problem-models.json を取得し、指定コンテスト・問題インデックス範囲のメタデータ一覧を返す。 |
| `scrape.py` | 問題ページの HTML 取得・問題文抽出（`#task-statement span.lang-ja`）、解説一覧ページの取得・公式HTML解説の特定・解説本文取得。**すべての AtCoder 向け requests の前後に `time.sleep(2)`、ヘッダーに `Accept-Language: ja` を付与。** |
| `llm_extract.py` | **`google-genai`** を使用。問題文＋解説（あれば）を渡し、`response_mime_type="application/json"` で algorithms / keywords / time_complexity / summary を抽出。解説なしでも問題文のみで推論。 |
| `embedding_db.py` | **`google-genai`** の Embedding（`models/embedding-001`, `task_type="RETRIEVAL_DOCUMENT"`）を用いた ChromaDB 用 Embedding 関数。戻り値は **`[e.values for e in response.embeddings]`**。PersistentClient で `./atcoder_rag_db` に upsert。既存 id 一覧取得で差分更新のためのインターフェースを提供。 |
| `run_batch.py` | CLI で「コンテスト ID」「問題インデックス範囲（例: C〜F）」を受け取り、上記モジュールを順に呼び出すオーケストレーション。 |

---

## 3. データ構造（models.py）

以下は `make_DB_plan.md` および experiment のスキーマを踏襲した最小スキーマ。実装時に TypedDict や dataclass で定義する。

### 3.1 メタデータ（API 取得後）

```python
# 例: TypedDict
ProblemMeta = {
    "id": str,           # 例: "abc400_c"
    "contest_id": str,   # 例: "abc400"
    "problem_index": str,# 例: "C"
    "title": str,
    "url": str,          # 例: "https://atcoder.jp/contests/abc400/tasks/abc400_c"
    "difficulty": int | None  # problem-models の difficulty、無ければ None
}
```

### 3.2 中間JSON（1問1ファイル、クロール＋LLM 抽出後）

```python
# ファイル: data/raw/{problem_id}.json
IntermediateProblem = {
    "id": str,
    "title": str,
    "url": str,
    "difficulty": int | None,
    "problem_statement_ja": str,       # #task-statement span.lang-ja のテキスト
    "has_official_editorial": bool,    # 公式HTML解説があったか
    "editorial_text": str | None,      # 公式解説本文（PDF/外部のみの場合は null）
    "gemini_extract": {                # llm_extract の戻り値
        "algorithms": list[str],
        "keywords": list[str],
        "time_complexity": str,        # 例: "O(N log N)"
        "summary": str
    } | None   # LLM 失敗時は None
}
```

### 3.3 ChromaDB 投入用

- **ids**: `list[str]` — 問題 id（例: `"abc400_c"`）
- **documents**: `list[str]` — ベクトル化するテキスト。`title` + `algorithms` + `keywords` + `summary` を結合した1文字列（plan の 3-1 通り）
- **metadatas**: `list[dict]` — 各要素は `{"title": str, "url": str, "difficulty": int | None}`（数値は Chroma 制約に合わせて str 化する場合は設計で明記）

---

## 4. 関数仕様（引数・戻り値）

### 4.1 config.py

| 関数/オブジェクト | 説明 | 引数 | 戻り値 |
|-------------------|------|------|--------|
| `load_config()` | `.env` を読み込み、API キー等を検証。 | なし | なし（失敗時は例外） |
| `get_headers()` | AtCoder 用の共通ヘッダー（User-Agent, **Accept-Language: ja**）を返す。 | なし | `dict[str, str]` |
| `GEMINI_API_KEY` | 環境変数 `GEMINI_API_KEY` を返す（`load_config()` 後に使用）。 | — | `str` |

- API キーが未設定の場合は `ValueError` を発生させ、パイプライン開始前に落とす。

---

### 4.2 atcoder_metadata.py

| 関数 | 説明 | 引数 | 戻り値 |
|------|------|------|--------|
| `fetch_problems_and_models()` | problems.json と problem-models.json を取得。 | なし | `tuple[list, dict]`（problems の list、model の dict） |
| `list_problems_in_range(contest_id, start_index, end_index)` | 指定コンテストの、指定インデックス範囲（例: C〜F）の問題メタデータを列挙。 | `contest_id: str`, `start_index: str`（例: `"C"`）, `end_index: str`（例: `"F"`） | `list[ProblemMeta]` |

- インデックス範囲は `start_index` 以上 `end_index` 以下（A,B,C,...,Z の順）でフィルタする。
- Problems API（kenkoooo.com）は AtCoder 本体ではないため、ここでは **`time.sleep(2)` の義務は不要**（plan は「AtCoder への」アクセス間隔を規定）。必要に応じて短いスリープを入れてもよい。

---

### 4.3 scrape.py

| 関数 | 説明 | 引数 | 戻り値 |
|------|------|------|--------|
| `fetch_problem_statement(url)` | 問題ページを取得し、`#task-statement span.lang-ja` のテキストを抽出。 | `url: str` | `str`（取得失敗・未検出時は空文字） |
| `get_official_editorial_text(contest_id, problem_id)` | 解説一覧ページにアクセスし、「公式」/「Official」の公式HTML解説があれば本文を取得。PDF・外部のみの場合は `None`。 | `contest_id: str`, `problem_id: str`（例: `"abc400_c"`） | `str \| None` |
| `scrape_one_problem(meta: ProblemMeta)` | 1問分のスクレイピングを統合。問題文取得 → **sleep(2)** → 解説取得。 | `meta: ProblemMeta` | `tuple[str, str \| None]`（問題文, 解説本文 or None） |

**厳守事項**

- **すべての** AtCoder 向け `requests.get`（問題ページ・解説一覧・解説本文）の**前**に `time.sleep(2)` を実行する（複数回 get する場合は各回の前に 2 秒）。
- すべての AtCoder 向けリクエストに **`get_headers()` で取得したヘッダー（Accept-Language: ja 含む）** を付与する。
- 解説一覧は `search_editorial.py` と同様、`/editorial/` を含むリンクの親に「公式」または「Official」があるものを採用し、PDF や外部ブログはスキップする。

---

### 4.4 llm_extract.py

| 関数 | 説明 | 引数 | 戻り値 |
|------|------|------|--------|
| `extract_keywords_and_summary(problem_statement_ja: str, editorial_text: str \| None)` | 問題文と解説（あれば）から、RAG 用の構造化データを抽出。 | 問題文（日本語）、解説本文（なしなら `None`） | `dict \| None`（`algorithms`, `keywords`, `time_complexity`, `summary` を持つ辞書。失敗時は `None`） |

**実装上の必須事項**

- **パッケージ**: `google.generativeai` ではなく **`google-genai`**（`from google import genai` 等）を使用する。
- **モデル**: `gemini-2.5-flash` または `gemini-1.5-flash`（plan 2-1 に合わせる）。
- **出力形式**: `response_mime_type="application/json"` で JSON を強制し、パースして返す。
- 解説が空でも、問題文のみで「想定解法・計算量・要約」を推論させる（plan 2-3）。
- API キーは **`config.get_gemini_api_key()` 相当（.env 由来）** から渡す。

---

### 4.5 embedding_db.py

| 関数/クラス | 説明 | 引数 | 戻り値 |
|-------------|------|------|--------|
| `GeminiChromaEmbeddingFunction` | ChromaDB の `EmbeddingFunction` サブクラス。`google-genai` で `models/embedding-001`、`task_type="RETRIEVAL_DOCUMENT"` を指定。 | コンストラクタ: `api_key: str` | — |
| `__call__(self, input: list[str])` | テキストリストを埋め込み。**戻り値は必ず `[e.values for e in response.embeddings]`**。 | `input: list[str]` | `list[list[float]]` |
| `get_chroma_client(path)` | ChromaDB の PersistentClient を返す。 | `path: str`（例: `"./atcoder_rag_db"`） | `chromadb.PersistentClient` |
| `get_existing_ids(collection)` | 既存のドキュメント id 一覧を取得（差分更新用）。 | `collection` | `list[str]` または `set[str]` |
| `upsert_problems(collection, ids, documents, metadatas)` | 指定 id / documents / metadatas で upsert。 | 対応する 3 つの list | なし |

**厳守事項**

- Embedding の戻り値は **必ず `return [e.values for e in response.embeddings]`** とし、単一の `response.embeddings[0].values` のような返し方をしない（ChromaDB の次元エラー回避）。
- メタデータはベクトル化テキストとは分離し、`title`, `url`, `difficulty` を格納（plan 3-3）。

---

### 4.6 中間JSON の読み書き（run_batch または専用ヘルパー）

| 処理 | 説明 |
|------|------|
| 保存 | 1問処理するたびに `data/raw/{problem_id}.json` に `IntermediateProblem` を書き出す（再開・冪等のため）。 |
| 読み込み | 既に `data/raw/{problem_id}.json` が存在し、かつ `gemini_extract` が入っている場合は、再スクレイプ・再LLM をスキップして DB 投入に進めるかどうかをオプションで制御可能にする。 |

---

## 5. メインバッチ処理フロー（run_batch.py）

### 5.1 CLI 引数（例）

- `--contest`: コンテスト ID（例: `abc400`）
- `--start`: 開始問題インデックス（例: `C`）
- `--end`: 終了問題インデックス（例: `F`）
- `--db-path`: ChromaDB の保存先（デフォルト: `./atcoder_rag_db`）
- `--skip-existing`: 既に ChromaDB に id が存在する問題をスキップする（デフォルト: True）
- `--force-re-scrape`: 中間JSON があってもスクレイピングからやり直す（オプション）

### 5.2 処理フロー（擬似コード）

```
1. load_config()  # .env 読み込み・APIキー検証

2. contest_id, start_index, end_index = CLI から取得

3. problems = list_problems_in_range(contest_id, start_index, end_index)
   → 0 件なら「該当問題なし」で終了

4. （オプション）既存ID取得で差分のみに絞る
   chroma_client = get_chroma_client(db_path)
   collection = client.get_or_create_collection("atcoder_problems", embedding_function=...)
   existing_ids = get_existing_ids(collection)
   if --skip-existing:
       problems = [p for p in problems if p["id"] not in existing_ids]

5. クローリング＋中間JSON
   for meta in problems:
       (problem_statement_ja, editorial_text) = scrape_one_problem(meta)
       has_official = editorial_text is not None
       # 中間JSON に problem_statement_ja, editorial_text, has_official を保存
       # 既に中間JSON があり --force-re-scrape でない場合はスキップ可

6. LLM 抽出（未抽出分のみ or 全件）
   for meta in problems:
       intermediate = load_intermediate(meta["id"])  # あれば
       if intermediate and intermediate.get("gemini_extract") and not --force-re-scrape:
           continue
       gemini_extract = extract_keywords_and_summary(
           intermediate["problem_statement_ja"],
           intermediate.get("editorial_text")
       )
       intermediate["gemini_extract"] = gemini_extract
       save_intermediate(meta["id"], intermediate)

7. ベクトル化・DB 投入
   to_upsert = [load_intermediate(p["id"]) for p in problems
                if load_intermediate(p["id"]) and load_intermediate(p["id"]).get("gemini_extract")]
   ids = [x["id"] for x in to_upsert]
   documents = [ build_combined_text(x) for x in to_upsert ]  # title + algorithms + keywords + summary
   metadatas = [ {"title": x["title"], "url": x["url"], "difficulty": x["difficulty"] } for x in to_upsert ]
   upsert_problems(collection, ids, documents, metadatas)

8. 完了メッセージ（処理件数・スキップ数など）
```

### 5.3 フロー図（概要）

```
[CLI] --contest, --start, --end
        ↓
[config] load_config()  (.env)
        ↓
[atcoder_metadata] list_problems_in_range()  → ProblemMeta[]
        ↓
[embedding_db] get_existing_ids()  → 既存 id 集合（--skip-existing 時）
        ↓
[scrape] 各問題: fetch_problem_statement → sleep(2) → get_official_editorial_text
        ↓
[data/raw] 1問1JSON 保存（再開用）
        ↓
[llm_extract] extract_keywords_and_summary()  (google-genai, JSON 出力)
        ↓
[embedding_db] build combined text → GeminiChromaEmbeddingFunction → upsert_problems
        ↓
[完了]
```

---

## 6. 技術制約チェックリスト（実装時確認）

| # | 項目 | 対応 |
|---|------|------|
| 1 | AtCoder への `requests.get` の間に必ず `time.sleep(2)` | `scrape.py` の全 AtCoder リクエストの前に挿入 |
| 2 | リクエストヘッダーに `Accept-Language: ja` を付与 | `config.get_headers()` に含め、`scrape.py` で使用 |
| 3 | Gemini に `google-genai` を使用（旧 `google.generativeai` は使わない） | `llm_extract.py`, `embedding_db.py` で `from google import genai` 等 |
| 4 | ChromaDB Embedding の戻り値を `[e.values for e in response.embeddings]` に | `embedding_db.py` の `__call__` で厳守 |
| 5 | API キーは `.env` から読み込み | `config.load_config()` と `os.environ.get("GEMINI_API_KEY")` |

---

## 7. まとめ

- **モジュール**: `config`, `models`, `atcoder_metadata`, `scrape`, `llm_extract`, `embedding_db` を `src/` に配置し、`run_batch.py` が CLI からコンテスト・問題範囲を指定して一括実行する。
- **データ**: 中間は 1問1JSON（`data/raw/{id}.json`）、ChromaDB は `./atcoder_rag_db`、ベクトル化テキストは title + algorithms + keywords + summary の結合、メタデータは title / url / difficulty を分離。
- **制約**: スクレイピング間隔 2 秒・Accept-Language: ja・google-genai・Chroma のリスト内包戻り値・.env による API キー管理を設計に明示し、実装時に必ず満たす。

以上で、`make_DB_plan.md` を変更せず、実験コードをベースにした一括DB化パイプラインの設計書とする。
