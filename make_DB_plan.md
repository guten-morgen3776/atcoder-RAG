AtCoder RAG ベクトルデータベース構築計画書
本計画は、過去のAtCoderの問題を「曖昧な記憶」や「自然言語のキーワード」から検索可能にするためのローカルRAGシステムにおける、データ収集からデータベース構築までのパイプライン仕様である。

1. クローリングフェーズ (データ収集)

AtCoderの問題文と解説文を取得し、LLMが処理しやすい生データ（JSON）を作成する。サーバーへの負荷を最小限に抑える同期的な処理（Pythonの requests + BeautifulSoup4）を採用する。

1-1. メタデータ取得

非公式API（AtCoder Problems API）の problems.json と problem-models.json を叩く。

問題の id、title、url、および内部レート値からの difficulty を取得する。

1-2. 問題文スクレイピング

問題ページのHTMLを取得し、#task-statement span.lang-ja を指定して日本語の問題文のみを抽出する。

数式（N≤10 
5
  など）はLaTeX形式のままテキストとして保持する。

1-3. 解説リンクの特定と取得

各問題の解説一覧ページ (/editorial) にアクセスする。

【重要】 英語ページへのリダイレクトを防ぐため、リクエストヘッダーに Accept-Language: ja を必ず付与する。

<span class="label"> の親要素に「公式」または「Official」が含まれるリンクのみを探す。

PDFや外部ブログ（公式HTMLが存在しない古い問題など）はノイズとなるためスキップし、フラグ has_official_editorial = False を立てる。

1-4. 中間JSONの生成

取得したデータを1問につき1つのJSONオブジェクトとして保存する（途中で処理が落ちても再開できるようにするため）。

2. LLM抽出フェーズ (データ構造化)

生のHTMLテキストから、検索システム（ベクトル化）に最適なキーワードや要約を抽出する。

2-1. モデルとプロンプト設計

モデル: gemini-2.5-flash （または 1.5-flash）を使用。

API設定: response_mime_type="application/json" を指定し、出力を純粋なJSONに強制してパースエラーを防ぐ。

2-2. 抽出項目

algorithms: 解法に必要なアルゴリズム（表記揺れを防ぐようプロンプトで指示）。

keywords: 問題のシチュエーションや制約（例: "スライム", "木構造"）。

time_complexity: 想定計算量（例: O(NlogN)）。

summary: 自然言語検索に引っかかりやすい、解法と状況の200文字程度の要約。

2-3. 解説なし問題への対応

解説テキストが空の場合でも、LLMの推論能力を活用し、問題文の制約や条件から想定される解法と計算量を推論させる。

3. ベクトル化・DB構築フェーズ (検索エンジンの作成)

抽出されたデータをベクトルに変換し、ローカルのChromaDBに格納する。

3-1. テキストの結合（Concatenation）

抽出した title, algorithms, keywords, summary を1つの文字列に結合する。

これにより「要素が混ざった曖昧な自然言語クエリ」に対するセマンティック検索のヒット率を最大化する。

3-2. ベクトル化 (Embedding)

SDK: 最新の google-genai パッケージを使用。

モデル: 安定版である models/embedding-001 を採用。

設定: 検索されるドキュメント側であるため task_type="RETRIEVAL_DOCUMENT" を指定する。

3-3. ChromaDBへの格納 (Upsert)

保存先: ローカルディレクトリ ./atcoder_rag_db。

【重要】 ChromaDBの仕様に合わせ、Embedding関数の戻り値は必ずリスト内包表記 [e.values for e in response.embeddings] で返す。

メタデータの分離: ベクトル化するテキストとは別に、UI表示や将来の厳密な絞り込み用として title, url, difficulty を metadatas 辞書に格納する。

4. 運用ルールの定義 (バッチ処理)

アクセス間隔: AtCoderへのスクレイピング処理のループ内には、必ず time.sleep(2) を挿入し、サーバーに負荷をかけない。

差分更新: 実行時にChromaDB内の既存 id リストを取得し、未取得の問題のみを処理対象とする（冪等性の担保）。