# AtCoder-RAG 自動更新ワークフロー設計書

## 1. 概要
毎週のコンテスト終了後、最新のAtCoderの問題を自動でChromaDBに取り込むための差分更新バッチ処理。
実行のスケジューリングはOSの `cron` に任せ、Pythonスクリプトは「1回実行されたら差分を埋めて終了する」冪等性（何度実行しても結果が同じになる性質）を持つ設計とする。

## 2. 対象範囲（フィルタ条件）
APIから取得した全問題リストのうち、以下の条件をすべて満たすものだけを更新候補とする。
* コンテストIDが `abc` から始まること。
* コンテスト番号が `126` 以上であること（例: `abc126`, `abc340` など）。
* *理由:* ABC125以前は4問体制であり、現在の難易度体系や問題傾向と異なるためノイズを弾く。

## 3. ファイル構成と役割

### 【新規作成】 `src/auto_update.py`
cronから定期実行されるメインのオーケストレーションスクリプト。
1. `embedding_db.get_existing_ids()` を呼び出し、ChromaDB内の既存ID一覧を取得。
2. `atcoder_metadata.py` の新規関数を呼び出し、ABC126以降の最新問題リストを取得。
3. `最新問題リスト - 既存ID一覧` の集合演算（引き算）を行い、未処理の問題（差分）を特定。
4. 差分が存在する場合のみ、`scrape.py` -> `llm_extract.py` -> `embedding_db.py` の既存パイプラインをループ実行。
5. 処理結果を `logs/update_report.jsonl` に追記。

### 【関数追加】 `src/atcoder_metadata.py`
既存の `fetch_problems_and_models` を活用し、以下の関数を追加する。
* `get_target_abc_problems(min_contest_number: int = 126) -> list[ProblemMeta]`
  * APIから全問題を取得後、正規表現等で `abc` プレフィックスと番号を抽出し、指定番号以上のメタデータのみをリストで返す。

## 4. 処理フロー図 (Mermaid)

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