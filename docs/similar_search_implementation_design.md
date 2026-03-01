# 問題番号入力による類題検索 実装設計書

## 1. 参照仕様・目的

- **参照仕様:** `docs/search_design.md`（AtCoder-RAG 類題検索機能 設計仕様書）の方式・UI/UX・バックエンド処理フローを前提とする。
- **目的:** 問題番号（コンテスト種別・番号・大問）を入力し、その問題を基準に ChromaDB のベクトル類似検索で「類題」を取得し、既存のキーワード検索と同一アプリ内で表示する。

既存のキーワード検索（`run_search`）や DB 構築（`embedding_db.py` / `run_batch.py`）との対応の取れた設計とする。

---

## 2. 既存処理との対応関係

| 既存 | 類題検索での扱い |
|------|------------------|
| `app.py` の 1 画面構成 | タブで「キーワードから検索」と「問題番号から類題検索」を分割 |
| `retriever.run_search`（クエリ文字列→拡張→ベクトル化→検索→整形） | 類題は「問題 ID → 既存ベクトル取得 → query」のため別エントリ `search_similar_problems_by_id` を追加 |
| 結果の辞書形式（id, title, url, difficulty, algorithms_keywords, distance） | 同一形式で返却し、表示も既存のカード形式を流用 |
| 難易度フィルタ（サイドバー: number_input、Python 側で min/max 適用） | 類題タブでも同様に「多めに取得 → Python でフィルタ」（Chroma の difficulty は str 保存のため） |
| `data/raw/{problem_id}.json` からアルゴリズム・キーワード取得 | 基準問題・類題とも `_load_raw_json` で取得し、共通タグ比較に利用 |
| `_check_db_available()`（DB 存在・件数） | 共通ヘッダー用に「収録問題数・範囲」を表示する処理を追加 |

---

## 3. 処理フロー概要

1. **ID の正規化・結合**  
   入力（コンテスト種別・番号・大問）から `problem_id`（例: `abc126_c`）を生成する。
2. **存在チェック**  
   その ID が ChromaDB に存在するか確認。存在しなければ警告表示して中断。
3. **基準ベクトルの取得**  
   `collection.get(ids=[problem_id], include=["embeddings"])` でベクトルを取得。
4. **類似ベクトル検索**  
   `collection.query(query_embeddings=[取得ベクトル], n_results=TopK+1, include=[...])` を実行。難易度フィルタは現行の `run_search` と同様、多めに取得して Python 側で min_diff / max_diff を適用する（Chroma の metadatas は difficulty を str で保存しているため、where の数値範囲は使わない）。
5. **自己除外**  
   検索結果の 1 件目（基準問題自身）を除外し、TopK 件とする。
6. **結果の整形・表示**  
   各件について `data/raw/{id}.json` からアルゴリズム・キーワードを補完し、既存と同形式の辞書リストで返す。オプションで共通タグをハイライト表示する。

---

## 4. 改修・追加するファイル一覧

### 4.1 改修するファイル

| ファイル | 改修内容 |
|----------|----------|
| **`app.py`** | 共通ヘッダー（タイトル・DB 収録ステータス）の追加。`st.tabs` で「キーワードから検索」「問題番号から類題検索」の 2 タブに分割。類題タブにコンテスト種別・番号・大問の入力フォーム、難易度・TopK オプション、「この問題の類題を探す」ボタン、結果表示（既存カード形式＋共通タグハイライト用の情報渡し）を実装。 |
| **`src/retriever.py`** | `search_similar_problems_by_id(problem_id, top_k, diff_filter_on, min_diff, max_diff, ...)` を追加。内部で ID 存在確認、`collection.get(ids=[...], include=["embeddings"])`、`collection.query(...)`、自己除外、難易度フィルタ（Python 側）、既存の `_load_raw_json` / `_format_algorithms_keywords` / `_parse_difficulty` を用いた整形。返却形式は `run_search` と同一（id, title, url, difficulty, algorithms_keywords, distance）。共通タグ用に、基準問題の algorithms/keywords を呼び出し元に返すか、各結果に「共通タグ」リストを付与するかを実装で選択可能とする。 |

### 4.2 追加するファイル（必要に応じて）

| ファイル | 役割 |
|----------|------|
| **`src/problem_id.py`**（任意） | 入力から `problem_id` を組み立てる関数 `build_problem_id(contest_type: str, contest_number: int, problem_index: str) -> str` を定義。`app.py` と `retriever.py` の両方で使う場合はここに集約するとよい。置かない場合は `app.py` または `retriever.py` 内のヘルパーで実装。 |

### 4.3 改修しないが参照するファイル

| ファイル | 参照内容 |
|----------|----------|
| `src/config.py` | `DEFAULT_DB_PATH`, `DEFAULT_RAW_DATA_DIR` |
| `src/embedding_db.py` | `get_chroma_client`, `COLLECTION_NAME`, `GeminiChromaEmbeddingFunction`（コレクション取得用）。ベクトルは既存ドキュメントのものを取得するだけなので、新規 Embedding API 呼び出しは不要。 |
| `src/models.py` | `IntermediateProblem`（`_load_raw_json` の型・gemini_extract 参照） |

---

## 5. モジュール・関数仕様

### 5.1 `src/retriever.py` に追加する関数

| 関数 | 役割 | 引数 | 戻り値 |
|------|------|------|--------|
| `search_similar_problems_by_id` | 問題 ID を基準に類題を検索する。存在チェック → ベクトル取得 → query → 自己除外 → 難易度フィルタ → 整形。 | `problem_id: str`, `top_k: int`, `diff_filter_on: bool`, `min_diff: int`, `max_diff: int`, `db_path: str = DEFAULT_DB_PATH`, `raw_data_dir: str = DEFAULT_RAW_DATA_DIR` | `list[dict]`。各要素は `run_search` と同形式（id, title, url, difficulty, algorithms_keywords, distance）に加え、共通タグ用に `common_algorithms: list[str]`, `common_keywords: list[str]` を付与する。未収録時は空リスト。 |

**内部手順（案）:**

1. `get_chroma_client(db_path)` → `get_or_create_collection(COLLECTION_NAME, embedding_function=emb_fn)` でコレクション取得。
2. `collection.get(ids=[problem_id], include=[])` で存在チェック（ids が空なら存在しない）。必要なら `include=["metadatas"]` でメタデータのみ取得してもよい。
3. 存在しなければ空リスト（と基準情報なし）を返す。呼び出し側で「未収録」警告を表示。
4. `collection.get(ids=[problem_id], include=["embeddings"])` でベクトル取得。`embeddings` が無い/空の場合はエラー扱いで空を返す。
5. 難易度フィルタ ON のときは `n_results = FETCH_SIZE_WHEN_FILTER`、OFF のときは `n_results = top_k + 1`。`collection.query(query_embeddings=[基準ベクトル], n_results=n_results, include=["metadatas", "distances"])` を実行。
6. 結果の 1 件目が `problem_id` と一致すれば除外。それ以外は順序を維持したまま、難易度フィルタ ON なら `_parse_difficulty` で min_diff〜max_diff に絞り、先頭 `top_k` 件を取る。
7. 各件について `_load_raw_json` → `_format_algorithms_keywords` で整形し、`run_search` と同じキー（id, title, url, difficulty, algorithms_keywords, distance）の dict を組み立てて返す。
8. 共通タグ用に、基準問題の `data/raw/{problem_id}.json` から `gemini_extract.algorithms` / `keywords` を取得し、各結果の raw JSON の algorithms/keywords と比較。共通部分を各結果 dict の `common_algorithms` / `common_keywords` として付与する。

### 5.2 共通タグのハイライト用データ

- 基準問題と各類題のアルゴリズム・キーワードを比較し、共通するタグを「共通タグ」として渡す。
- 返却形式の案:
  - **A:** 各結果 dict に `common_algorithms: list[str]`, `common_keywords: list[str]` を追加する。
  - **B:** 基準問題の `algorithms` / `keywords` を別途返し、UI 側で各結果のアルゴリズム・キーワード文字列と照合してハイライトする。
- 設計書では **A** を推奨（retriever で 1 回だけ比較し、UI は表示のみに専念する）。

### 5.3 problem_id の組み立て

- 形式: `{contest_type_lower}{contest_number}_{problem_index_lower}`（例: ABC, 126, C → `abc126_c`）。
- コンテスト種別は `["ABC", "ARC", "AGC"]` のいずれかを小文字にし、番号はそのまま、大問は 1 文字（A〜G, Ex）を小文字にする。
- 実装場所: `src/problem_id.py` に `build_problem_id(contest_type: str, contest_number: int, problem_index: str) -> str` を用意するか、`app.py` の類題タブ内で `f"{contest_type.lower()}{contest_number}_{problem_index.lower()}"` のように組み立てる。

---

## 6. UI 仕様（`app.py`）

### 6.1 共通ヘッダー（全タブ共通）

- **タイトル:** 「AtCoder-RAG」または既存の「AtCoder 過去問 類似検索」を維持するかは任意。
- **DB 収録ステータス:** 「現在の収録データ: ABC126 〜 最新 (計 N 問)」のような文言。  
  - 取得方法: 既存の `_check_db_available()` と同様に `get_chroma_client` → `get_collection` で `collection.count()` と `collection.get(include=[])` から `ids` を取得し、`ids` からコンテスト範囲（例: 先頭・末尾の contest 部分をパース）と件数を算出する。  
  - ヘルパーは `app.py` 内の関数でも、`embedding_db.py` に `get_db_status(collection) -> dict` を追加してもよい。

### 6.2 タブ構成

- **タブ 1:** 「キーワードから検索」— 既存のサイドバー（AI 拡張・難易度・TopK）＋メイン（キーワード入力・検索・結果）をそのまま配置。
- **タブ 2:** 「問題番号から類題検索」— 以下を配置。

### 6.3 類題タブの入力フォーム

- **コンテスト種別:** `st.selectbox`、選択肢 `["ABC", "ARC", "AGC"]`、デフォルト `"ABC"`。
- **コンテスト番号:** `st.number_input`、整数のみ（例: 126）。
- **問題/大問:** `st.radio`、水平配置、選択肢 `["A", "B", "C", "D", "E", "F", "G", "Ex"]`。
- **難易度フィルタ:** 既存と揃える場合は `st.checkbox("Difficulty で絞り込む")` ＋ `st.number_input`（最小・最大）。`docs/search_design.md` の「難易度（Difficulty）フィルタ (st.slider)」に合わせる場合は `st.slider` にしてもよい（**確認事項** に記載）。
- **取得件数 Top K:** `st.number_input`（最小 1、最大 20 など、既存と同様）。
- **実行ボタン:** `st.button("この問題の類題を探す")`。

### 6.4 類題タブの結果表示

- 既存のキーワード検索と同様のカード形式（タイトル、URL、Difficulty、アルゴリズム・キーワード、類似度（距離））。
- 共通タグがある場合、そのタグを太字やバッジでハイライトする（**確認事項** に記載）。

---

## 7. 確認事項・不明点（仕様が詰めきれない点）

実装前に以下を決めたいです。

1. **DB 収録ステータスの「最新」の定義**  
   - 「最新」を、収録されているコンテスト ID のうち最大のコンテスト番号（例: abc350）として「ABC126 〜 ABC350 (計 N 問)」のように出すか、文言だけ「〜 最新」のままにするか。

2. **難易度フィルタの UI**  
   - 類題タブでは `docs/search_design.md` で「難易度（Difficulty）フィルタ (st.slider)` とあるが、既存キーワード検索は `st.number_input`（最小・最大）。類題タブも `number_input` で統一するか、`st.slider`（最小・最大の 2 本）にするか。

3. **共通タグのハイライト表示形式**  
   - 「共通タグをハイライト表示」を、太字・バッジ・色のどれで行うか（例: `**タグ**`、`st.badge`、色付き span など）。デザイン指定がなければ「太字」で進めてよいか。

4. **問題番号ユーティリティの配置**  
   - `build_problem_id` を `src/problem_id.py` として新規ファイルに出すか、`app.py` または `retriever.py` の先頭のヘルパーでよいか。

以上を決めたうえで、本設計書に反映し実装に進む想定です。

## 不明点に対する回答（実装前に必ずこれを参照し、設計に反映させてください）
1. 最新がどこまで反映されているのかは重要なのでABC126~ABC...と言った感じで具体的な数字を出してください　あとC,D,E,Fしか入ってないこともUIに明示すると良いです
2. 既存のUIと一貫性を持たせてください　difficultyの絞り込み機能は既存と同様にON,OFF機能もつけてくださいね
3. 強調は太字でお願いします
4. src/problem_id.pyを作成してそこにbuild_problem_idをおいてください