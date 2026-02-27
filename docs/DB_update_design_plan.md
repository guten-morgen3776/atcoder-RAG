# AtCoder-RAG 自動更新 設計計画書

本ドキュメントは `docs/DB_update.md` の概要設計に基づき、**具体的なファイル・モジュールの新規作成・変更内容**を定義する。既存の `src/` 内モジュールおよび `run_batch.py` の処理と整合性を取った実装方針とする。

---

## 1. 前提・参照

- **上位設計**: `docs/DB_update.md` の「概要」「対象範囲」「ファイル構成と役割」「処理フロー図」は変更しない。
- **既存パイプライン**: `run_batch.py` が行う「スクレイピング → LLM 抽出 → 中間JSON 保存 → ChromaDB upsert」の流れを、自動更新では**中間JSON を保存せずメモリ上で完結**させる形で再利用する。
- **技術制約**: `docs/pipeline_design.md` に記載のとおり（AtCoder へのリクエスト前 `time.sleep(2)`、`Accept-Language: ja`、`google-genai`、ChromaDB の Embedding 仕様、`.env` で API キー管理）を守る。

---

## 2. 対象範囲（フィルタ条件）— 再掲

API から取得した全問題のうち、**すべて**を満たすものだけを更新候補とする。

| 条件 | 内容 |
|------|------|
| コンテスト ID | `abc` で始まること |
| コンテスト番号 | `126` 以上（例: `abc126`, `abc340`） |
| 理由 | ABC125 以前は 4 問体制のため、現行の難易度体系・傾向と異なりノイズとなるため除外する |

---

## 3. 新規作成・変更一覧

| 種別 | パス | 内容 |
|------|------|------|
| **新規** | `src/auto_update.py` | cron から起動するオーケストレーションスクリプト（本節 4 で詳細） |
| **関数追加** | `src/atcoder_metadata.py` | `get_target_abc_problems(min_contest_number=126)` を追加（本節 5 で詳細） |
| **定数追加** | `src/config.py` | `DEFAULT_UPDATE_REPORT_FILENAME = "update_report.jsonl"` を追加 |

上記以外の既存モジュール（`scrape.py`, `llm_extract.py`, `embedding_db.py`, `logging_report.py`, `models.py`）は**変更しない**。既存の関数・定数をそのまま利用する。

---

## 4. 新規: `src/auto_update.py`

### 4.1 役割

- cron から定期実行される**単一の入口**。
- 「ChromaDB 既存 ID 一覧の取得」「ABC126 以降の対象問題一覧の取得」「差分の算出」「差分に対する既存パイプラインのループ実行」「結果の `update_report.jsonl` への追記」を順に実行する。
- **冪等性**: 同じ状態で何度実行しても結果が同じになる（差分がなければ何も書き込まず終了）。

### 4.2 利用する既存モジュール・関数

| モジュール | 利用する関数・定数 |
|------------|--------------------|
| `src.config` | `load_config`, `DEFAULT_DB_PATH`, `DEFAULT_LOG_DIR`, `DEFAULT_UPDATE_REPORT_FILENAME`（本設計で追加） |
| `src.atcoder_metadata` | `get_target_abc_problems`（本設計で追加） |
| `src.embedding_db` | `get_chroma_client`, `get_existing_ids`, `GeminiChromaEmbeddingFunction`, `build_combined_text`, `upsert_problems`, `COLLECTION_NAME` |
| `src.scrape` | `scrape_one_problem` |
| `src.llm_extract` | `extract_keywords_and_summary` |
| `src.logging_report` | `setup_logging`, `get_logger`, `write_report_row`, `console_info`, `console_error` |
| `src.models` | （型として `ProblemMeta` を参照する程度。run_batch と同様に dict のまま扱ってよい） |

### 4.3 処理手順（疑似コード）

```
1. load_config()
2. setup_logging(log_dir)  # DEFAULT_LOG_DIR
3. logger = get_logger("auto_update")
4. report_path = Path(log_dir) / DEFAULT_UPDATE_REPORT_FILENAME  # 例: logs/update_report.jsonl

5. client = get_chroma_client(DEFAULT_DB_PATH)
6. emb_fn = GeminiChromaEmbeddingFunction()
7. collection = client.get_or_create_collection(name=COLLECTION_NAME, embedding_function=emb_fn)
8. existing_ids = get_existing_ids(collection)

9. target_list = get_target_abc_problems(min_contest_number=126)
10. diff_metas = [p for p in target_list if p["id"] not in existing_ids]

11. if not diff_metas:
    - console_info("差分なし。終了します。")
    - （必要なら「実行サマリ」1行を update_report.jsonl に追記: 日時・処理件数 0 など）
    - return

12. console_info(f"差分 {len(diff_metas)} 問を処理します。")

13. report_rows = []   # 1問1行のレポート
    to_upsert = []     # ChromaDB に投入する中間データ（IntermediateProblem 相当の dict のリスト）

14. for meta in diff_metas:
    - row = { "problem_id": meta["id"], "contest_id": meta["contest_id"], "scrape_status": "OK", "llm_status": "OK", "db_upsert_status": "NG", "error_message": "" }
    - try: problem_statement, editorial_text = scrape_one_problem(meta)
      except: row["scrape_status"] = "NG", row["error_message"] += ..., continue または row だけ記録して次へ
    - time.sleep(1)   # run_batch と同様に Gemini API 制限対策
    - try: gemini_extract = extract_keywords_and_summary(problem_statement, editorial_text)
      except: row["llm_status"] = "NG", ...
    - if not gemini_extract: row["llm_status"] = "NG", report_rows.append(row); continue
    - item = { "id": meta["id"], "title": meta["title"], "url": meta["url"], "difficulty": meta["difficulty"], "gemini_extract": gemini_extract }
    - to_upsert.append(item)
    - report_rows.append(row)

15. if to_upsert:
    - ids = [x["id"] for x in to_upsert]
    - documents = [build_combined_text(x) for x in to_upsert]
    - metadatas = [{"title": x["title"], "url": x["url"], "difficulty": x.get("difficulty")} for x in to_upsert]
    - upsert_problems(collection, ids, documents, metadatas)
    - upserted_ids = set(ids)
    - for r in report_rows: r["db_upsert_status"] = "OK" if r["problem_id"] in upserted_ids else "NG"

16. for r in report_rows:
    - write_report_row(r, str(report_path))

17. console_info(f"完了: レポート {report_path}")
```

### 4.4 レポート行の形式

`run_batch.py` の `report.jsonl` と同一形式とする（既存のレポート解析・失敗 ID 抽出と揃えるため）。

| キー | 型 | 説明 |
|------|-----|------|
| `problem_id` | str | 問題 ID（例: `abc400_c`） |
| `contest_id` | str | コンテスト ID（例: `abc400`） |
| `scrape_status` | str | `"OK"` / `"NG"` |
| `llm_status` | str | `"OK"` / `"NG"` |
| `db_upsert_status` | str | `"OK"` / `"NG"` |
| `error_message` | str | エラー時のみ文言を付与 |

### 4.5 CLI（オプション）

- 引数なしで実行し、`DEFAULT_DB_PATH` / `DEFAULT_LOG_DIR` を使用する形でよい。
- 必要になった場合、`run_batch.py` と同様に `--db-path`, `--log-dir` を追加可能とする。

### 4.6 エラー・例外

- スクレイピング・LLM 抽出の失敗時は、当該問題の `row` を `scrape_status` / `llm_status` を `"NG"` にして `report_rows` に追加し、**処理は継続**する（run_batch と同様の Non-blocking 方針）。
- ChromaDB 接続失敗や `get_target_abc_problems` の API 失敗など、全体が止まるような例外は logger で記録し、必要に応じて `console_error` で表示したうえで終了する。

---

## 5. 関数追加: `src/atcoder_metadata.py` — `get_target_abc_problems`

### 5.1 シグネチャ

```python
def get_target_abc_problems(min_contest_number: int = 126) -> list[ProblemMeta]:
```

### 5.2 仕様

- **入力**: `min_contest_number`（デフォルト 126）。コンテスト番号がこの値以上の問題のみ対象とする。
- **処理**:
  1. 既存の `fetch_problems_and_models()` を呼び、`problems_data`（list）と `models_data`（dict）を取得する。
  2. `problems_data` を走査し、`contest_id` が次の条件を**両方**満たすものだけを対象とする。
     - プレフィックスが `abc`（小文字で比較してよい）。
     - コンテスト番号が `min_contest_number` 以上。  
     例: `contest_id == "abc340"` → 番号 340、`min_contest_number=126` なら対象。  
     番号の抽出は正規表現 `re.match(r"^abc(\d+)$", contest_id)` などで行い、`int(m.group(1)) >= min_contest_number` で判定する。
  3. 対象となる各問題について、既存の `list_problems_in_range` と同様に `ProblemMeta` を組み立てる。
     - `problem_id`（API の `id`）、`contest_id`、`problem_index`、`title`、`url`（`https://atcoder.jp/contests/{contest_id}/tasks/{problem_id}`）、`difficulty`（`models_data.get(problem_id, {}).get("difficulty")`）。
  4. 返却リストの順序は、API の並び（コンテスト・問題インデックス順）でよい。特にソート要件は設けない。

### 5.3 実装上の注意

- `atcoder_metadata.py` では既に `ProblemMeta` を `src.models` から import しているため、そのまま利用する。
- 全問題を 1 回の `fetch_problems_and_models()` で取得し、メモリ上でフィルタする設計でよい（API は problems.json がまとめて返る前提）。

---

## 6. 定数追加: `src/config.py`

- **追加する定数**: `DEFAULT_UPDATE_REPORT_FILENAME = "update_report.jsonl"`
- **用途**: 自動更新バッチの実行結果を追記するレポートファイル名。パスは `Path(log_dir) / DEFAULT_UPDATE_REPORT_FILENAME`（例: `logs/update_report.jsonl`）とする。

---

## 7. 既存モジュールの利用（変更なし）

| ファイル | 利用箇所・用途 |
|----------|----------------|
| `src/embedding_db.py` | `get_chroma_client`, `get_existing_ids`, `GeminiChromaEmbeddingFunction`, `build_combined_text`, `upsert_problems`, `COLLECTION_NAME`。**変更不要**。 |
| `src/scrape.py` | `scrape_one_problem(meta)`。内部で `time.sleep(2)` 済み。**変更不要**。 |
| `src/llm_extract.py` | `extract_keywords_and_summary(problem_statement_ja, editorial_text)`。**変更不要**。 |
| `src/logging_report.py` | `setup_logging`, `get_logger`, `write_report_row`, `console_info`, `console_error`。**変更不要**。 |
| `src/models.py` | `ProblemMeta` は atcoder_metadata 側で参照。auto_update では dict のまま扱う。**変更不要**。 |

---

## 8. 処理フロー図（DB_update.md 準拠）

```mermaid
graph TD
    A[cronによる定期実行] --> B[auto_update.py 起動]
    B --> C{ChromaDBから<br>既存ID一覧を取得}
    B --> D{AtCoder Problems APIから<br>全問題一覧を取得}
    D --> E[フィルタ: ABC126以降のみ抽出]
    C --> F((引き算<br>差分抽出))
    E --> F
    F --> G{差分(新着問題)は<br>あるか?}
    G -- No --> H[終了・ログ記録]
    G -- Yes --> I[差分に対して1問ずつループ処理]
    
    subgraph 既存パイプラインの再利用
    I --> J[スクレイピング<br>※必ず2秒sleep]
    J --> K[Gemini APIで<br>キーワード抽出]
    K --> L[ChromaDBへ<br>ベクトルUpsert]
    end
    
    L --> M[次の問題へ]
    M -.-> I
    M --> N[全件完了後、終了・ログ記録]
```

---

## 9. 実行方法・運用

- **手動実行**: プロジェクトルートで `python -m src.auto_update` または `python src/auto_update.py` で実行する（エントリポイントは `if __name__ == "__main__"` で `main()` を呼ぶ形とする）。
- **cron**: OS の cron で「毎週コンテスト終了後」など、任意のスケジュールで上記コマンドを実行する。実行のスケジューリングは cron に任せ、Python 側は 1 回の実行で「差分を処理して終了」する冪等な設計のままとする。
- **ログ**: `logs/app.log` に既存と同様に出力する。`logs/update_report.jsonl` に 1 問 1 行の結果を追記する。

---

## 10. 不明点・確認事項（実装前に確認推奨）

以下の点は、現時点の設計で一応の判断をしているが、必要に応じて仕様を調整してください。

1. **実行サマリ行の有無**  
   差分が 0 件のときに `update_report.jsonl` に「実行日時・処理件数 0」のような 1 行を追記するかどうか。追記すると「いつ実行されたか」の履歴になるが、行数が増える。不要であれば「差分なしのときは何も追記しない」でもよい。

2. **auto_update の CLI 引数**  
   最初は引数なし（`DEFAULT_DB_PATH` / `DEFAULT_LOG_DIR` 固定）でよいか、初めから `--db-path` / `--log-dir` を用意するか。

3. **問題の並び順**  
   `get_target_abc_problems` の返却順は「API の並び」でよいか、それとも「コンテスト番号昇順・問題インデックス昇順」などで明示的にソートするか。

上記について希望があれば教えてください。なければ、本設計書の記載どおり（サマリ行は「必要なら追加」、CLI は引数なし、並び順は API のまま）で実装してよい。
