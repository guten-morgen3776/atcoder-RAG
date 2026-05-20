# AtCoder-RAG モバイル公開化 実装計画書

Cloudflare Tunnel + 自宅 Mac + Cloudflare Access により、認証付き HTTPS でどの端末からでもアクセス可能にする計画。

---

## 1. ゴール

- スマホ・タブレット・他PCのブラウザから https URL でアクセスできる
- 自分（`takatoshi.aoki0116@gmail.com`）以外は使えないように認証
- 既存の ChromaDB／中間 JSON／cron 構成はそのまま維持
- 月額コスト 0 円
- ローカル開発体験（`streamlit run app.py`）も壊さない

## 2. 採用アーキテクチャ

```
[ユーザ端末（スマホ等）]
        │ HTTPS
        ▼
[Cloudflare Edge]
   ├─ Access（Google ログイン → email allowlist 認証）
   └─ Tunnel（cloudflared 経由で自宅 Mac に転送）
        │ ローカル接続
        ▼
[自宅 Mac]
   ├─ Streamlit（127.0.0.1:8501 で常駐／launchd 管理）
   ├─ ChromaDB（既存ファイル）
   └─ cron（既存 auto_update、毎週水曜 12:00）
```

ポイント:
- Streamlit は **127.0.0.1 のみで listen**（LAN／外部に直公開しない）
- 外部からのアクセスは **Cloudflare の認証を通過したもののみ** トンネル経由で届く
- ルータのポート開放は **不要**（cloudflared がアウトバウンド接続を確立する）

## 3. 前提条件

| 項目 | 要件 |
|------|------|
| Mac | 24 時間起動／スリープしない設定 |
| Cloudflare | 無料アカウント |
| ドメイン | 任意（無ければ `*.trycloudflare.com` で代用可、ただし固定 URL にしたいなら独自ドメイン推奨） |
| Homebrew | `cloudflared` インストールに使用 |
| Python 環境 | 既存の `/Users/aokitenju/.pyenv/versions/3.13.0` を継続使用 |

## 4. フェーズ別実装手順

### Phase 1: モバイル UI 調整（所要 1〜2 時間）

現状の `app.py` の課題:
- `st.set_page_config(layout="wide")` がスマホで横スクロール発生源
- 検索オプション（AI 拡張・難易度フィルタ・トップK）が **サイドバー** にあり、スマホでは毎回ハンバーガーを開く必要がある UX

対応:
1. [app.py:39](../app.py#L39) の `layout="wide"` を `layout="centered"` に変更
2. キーワード検索タブのサイドバー（`with st.sidebar:` ブロック）を、検索ボックス上部の `with st.expander("検索設定", expanded=False):` に置き換え
   - 類題検索タブと UI を揃える
3. `st.columns(2)` で「最小／最大 Difficulty」を横並びにし、縦スペースを節約
4. 実機テスト
   - iPhone Safari、Android Chrome 最低各1
   - キーワード入力 → 検索 → 結果カードまでスクロールできるか確認

完了条件: `streamlit run app.py` をローカル起動し、Chrome DevTools のモバイルエミュレータ（iPhone 14, Pixel 7）で操作できることを目視確認。

### Phase 2: Cloudflare 環境準備（所要 30 分）

1. **Cloudflare アカウント作成**（既存ならスキップ）
   - https://dash.cloudflare.com/sign-up
2. **ドメイン準備**（どちらか選択）
   - **A. 独自ドメイン**: お名前.com／Cloudflare Registrar 等で取得 → Cloudflare の DNS にネームサーバ移管
   - **B. お試し**: ドメイン不要、`*.trycloudflare.com` の自動発行 URL を使用（URL が毎回変わる点に注意）
3. **`cloudflared` インストール**
   ```
   brew install cloudflared
   cloudflared --version
   ```
4. **Cloudflare ログイン**
   ```
   cloudflared tunnel login
   ```
   ブラウザが開いて Cloudflare アカウント連携、対象ドメイン（または「全アカウント」）を許可する。

完了条件: `cloudflared tunnel list` がエラーなく実行できる。

### Phase 3: トンネル作成（所要 30 分）

1. **トンネル作成**
   ```
   cloudflared tunnel create atcoder-rag
   ```
   → `~/.cloudflared/<UUID>.json` に認証情報が生成される。UUID をメモ。
2. **DNS ルート設定**
   ```
   cloudflared tunnel route dns atcoder-rag atcoder-rag.<your-domain>
   ```
   （`trycloudflare.com` 利用時はこの手順不要）
3. **設定ファイル作成** `~/.cloudflared/config.yml`
   ```yaml
   tunnel: <UUID>
   credentials-file: /Users/aokitenju/.cloudflared/<UUID>.json
   ingress:
     - hostname: atcoder-rag.<your-domain>
       service: http://127.0.0.1:8501
     - service: http_status:404
   ```
4. **疎通確認**
   - 別ターミナルで `streamlit run app.py --server.address 127.0.0.1 --server.port 8501` を起動
   - `cloudflared tunnel run atcoder-rag` を実行
   - ブラウザで `https://atcoder-rag.<your-domain>` にアクセス → Streamlit が表示されることを確認

完了条件: PC ブラウザで HTTPS URL から Streamlit にアクセスでき、検索が動作する。**この時点ではまだ無認証なので外部公開しない**。

### Phase 4: Cloudflare Access で認証（所要 15 分）

> 重要: Phase 3 終了時点では URL を知っていれば誰でもアクセスでき、API キーが消費されてしまう。必ず Phase 4 まで通してから外部に URL を出すこと。

1. Cloudflare ダッシュボード → **Zero Trust** → **Access** → **Applications** → **Add an application**
2. タイプ: **Self-hosted**
3. 設定:
   - Application name: `atcoder-rag`
   - Session duration: `1 month`（任意）
   - Application domain: `atcoder-rag.<your-domain>`
4. **Identity providers**: Google を追加（One-time PIN でも可）
5. **Policy 作成**
   - Name: `owner-only`
   - Action: `Allow`
   - Rule: `Include` → `Emails` → `takatoshi.aoki0116@gmail.com`
6. 動作確認
   - シークレットウィンドウで URL にアクセス → Cloudflare のログイン画面 → Google 認証後に Streamlit にリダイレクトされることを確認
   - 別 Google アカウントでアクセス → ブロックされることを確認

完了条件: 自分のアカウントのみ通過、他はブロックされる。

### Phase 5: 常駐化（launchd）（所要 30 分）

Streamlit と cloudflared を Mac 起動時に自動立ち上げ・落ちたら再起動する。

1. **Streamlit 用 plist** `~/Library/LaunchAgents/com.atcoder-rag.streamlit.plist`
   ```xml
   <?xml version="1.0" encoding="UTF-8"?>
   <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
     "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
   <plist version="1.0">
   <dict>
     <key>Label</key><string>com.atcoder-rag.streamlit</string>
     <key>WorkingDirectory</key><string>/Users/aokitenju/atcoder-RAG</string>
     <key>ProgramArguments</key>
     <array>
       <string>/Users/aokitenju/.pyenv/versions/3.13.0/bin/streamlit</string>
       <string>run</string>
       <string>app.py</string>
       <string>--server.address</string><string>127.0.0.1</string>
       <string>--server.port</string><string>8501</string>
       <string>--server.headless</string><string>true</string>
       <string>--browser.gatherUsageStats</string><string>false</string>
     </array>
     <key>RunAtLoad</key><true/>
     <key>KeepAlive</key><true/>
     <key>StandardOutPath</key><string>/Users/aokitenju/atcoder-RAG/logs/streamlit.log</string>
     <key>StandardErrorPath</key><string>/Users/aokitenju/atcoder-RAG/logs/streamlit.err.log</string>
   </dict>
   </plist>
   ```
2. **cloudflared 用 plist** `~/Library/LaunchAgents/com.atcoder-rag.cloudflared.plist`
   ```xml
   <?xml version="1.0" encoding="UTF-8"?>
   <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
     "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
   <plist version="1.0">
   <dict>
     <key>Label</key><string>com.atcoder-rag.cloudflared</string>
     <key>ProgramArguments</key>
     <array>
       <string>/opt/homebrew/bin/cloudflared</string>
       <string>tunnel</string>
       <string>run</string>
       <string>atcoder-rag</string>
     </array>
     <key>RunAtLoad</key><true/>
     <key>KeepAlive</key><true/>
     <key>StandardOutPath</key><string>/Users/aokitenju/atcoder-RAG/logs/cloudflared.log</string>
     <key>StandardErrorPath</key><string>/Users/aokitenju/atcoder-RAG/logs/cloudflared.err.log</string>
   </dict>
   </plist>
   ```
3. **ロード**
   ```
   launchctl load ~/Library/LaunchAgents/com.atcoder-rag.streamlit.plist
   launchctl load ~/Library/LaunchAgents/com.atcoder-rag.cloudflared.plist
   ```
4. **スリープ抑制**
   - システム設定 → ディスプレイ → 詳細 → 「ディスプレイがオフのときコンピュータを自動でスリープさせない」を ON
   - 必要なら `caffeinate -i` を別の launchd で常駐
5. **再起動テスト**: Mac を再起動し、URL に再アクセスして自動復帰を確認。

完了条件: Mac 再起動後、人手介入なしで URL からアクセスできる。

### Phase 6: 運用・モニタリング（継続）

- **ログローテーション**: `logs/streamlit.log` / `logs/cloudflared.log` が肥大化するので、月1で truncate するか `newsyslog` 設定
- **Cloudflare Access ログ**: Zero Trust ダッシュボード → Logs → Access でアクセス履歴を月次確認
- **既存 cron**: 変更不要。`auto_update.py` は引き続き毎週水曜 12:00 に走る
- **モデル更新時の動作確認**: Gemini モデル切替時は `streamlit.log` の Embedding／LLM エラーをチェック

## 5. リスクと対応

| リスク | 影響 | 対応 |
|--------|------|------|
| Mac がスリープ／落ちる | アクセス不可 | スリープ抑制設定＋ launchd `KeepAlive` |
| 自宅停電・回線断 | アクセス不可（数時間〜半日） | 許容。重要度高なら UPS／別案 C（VPS）に移行 |
| Cloudflare Access の設定漏れ | 無認証で公開、API キー枯渇 | Phase 3 完了後 **必ず Phase 4 完了まで URL を秘匿**。Phase 4 完了前にシークレットウィンドウで未認証アクセスがブロックされることを確認 |
| `.env` の漏洩 | API キー悪用 | 既に `.gitignore` 済み。Git 履歴に過去コミットされていないか `git log -p .env` で確認 |
| Gemini モデル過負荷（503） | 検索失敗（Embedding 側） | 検索側のリトライは未実装。Phase 1 のついでに `src/embedding_db.py` も同様のリトライを入れるか検討 |
| ChromaDB の破損 | DB 復旧必要 | 月次で `tar -czf atcoder_rag_db_backup_$(date +%Y%m).tar.gz atcoder_rag_db/` を別ディスクへ |

## 6. ロールバック手順

何か問題が起きた場合の戻し方:

1. **トンネルだけ停止**: `launchctl unload ~/Library/LaunchAgents/com.atcoder-rag.cloudflared.plist` → 外部から到達不可、ローカル `streamlit run` は影響なし
2. **完全ロールバック**: 上記 2 つの plist を `unload` & ファイル削除 → 元の「ローカル `streamlit run` のみ」状態に戻る
3. **UI 改修だけ戻したい**: `git checkout app.py`
4. **Cloudflare 側の取り消し**: ダッシュボードで Application と Tunnel を削除

cron／DB／中間 JSON には一切手を入れないため、ロールバックで失うものは無い。

## 7. 完了基準（受け入れテスト）

- [ ] iPhone Safari から URL アクセス → Google 認証 → 検索実行 → 結果表示
- [ ] Android Chrome から同上
- [ ] 別 Google アカウントで URL アクセス → ブロック画面
- [ ] Mac 再起動後、人手介入なしで再アクセス可能
- [ ] `streamlit.log` / `cloudflared.log` が `logs/` に出力されている
- [ ] cron (`auto_update`) が翌週水曜に成功している（`logs/cron.log` 確認）

## 8. 将来の拡張余地

- **B 案で運用 → 不満点が出たら C 案（VPS）へ移行**: 移行は ChromaDB／中間 JSON／コードを `rsync` でコピーし、cron と launchd を systemd に書き直すだけ。アプリ本体は無改修。
- **PWA 化**: `manifest.json` 追加でホーム画面に「アプリ風」配置可能
- **複数ユーザ運用**: Cloudflare Access の Policy を email 単位で増やすだけ

---

## 推定総工数

| Phase | 所要 |
|-------|------|
| 1. UI 改修 | 1〜2h |
| 2. Cloudflare 準備 | 0.5h |
| 3. トンネル作成 | 0.5h |
| 4. Access 認証 | 0.25h |
| 5. 常駐化 | 0.5h |
| 6. 運用整備 | 随時 |
| **合計** | **約半日（3〜4h）** |
