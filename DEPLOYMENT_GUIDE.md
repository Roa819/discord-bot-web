# Railway デプロイガイド - 詳細手順

このガイドでは、Discord Bot Web ViewerをRailwayにデプロイする手順を詳しく説明します。

## 📋 前提条件

- Railwayアカウント（無料プランでOK）
- GitHubアカウント
- Discordボットが既にRailway PostgreSQLを使用している

---

## ステップ1: Gitリポジトリの作成

### 1-1. ローカルでGit初期化

PowerShellで以下を実行：

```powershell
# Webアプリのディレクトリに移動
cd c:\discord-bot-web

# Gitリポジトリを初期化
git init

# .envファイルを作成（後で編集）
Copy-Item .env.example .env

# 全ファイルをステージング
git add .

# 初回コミット
git commit -m "Initial commit: Discord bot web viewer"
```

### 1-2. GitHubにリポジトリを作成

1. **GitHubにアクセス**: https://github.com
2. 右上の「+」→「New repository」をクリック
3. リポジトリ設定：
   - **Repository name**: `discord-bot-web` (任意の名前)
   - **Description**: `Discord bot raid history web viewer`
   - **Public or Private**: どちらでもOK（Privateを推奨）
   - **Initialize this repository with**: 何もチェックしない
4. 「Create repository」をクリック

### 1-3. GitHubにプッシュ

GitHubに表示される手順に従って実行：

```powershell
# リモートリポジトリを追加（URLは自分のリポジトリに置き換え）
git remote add origin https://github.com/YOUR_USERNAME/discord-bot-web.git

# メインブランチにリネーム（必要に応じて）
git branch -M main

# GitHubにプッシュ
git push -u origin main
```

**📌 注意**: GitHubへのpush時に認証が必要な場合は、Personal Access Token（PAT）を使用してください。

---

## ステップ2: Railwayでプロジェクト作成

### 2-1. Railwayにログイン

1. **Railwayにアクセス**: https://railway.app
2. 右上の「Login」をクリック
3. GitHubアカウントでログイン

### 2-2. 新規プロジェクトを作成

1. ダッシュボードで「New Project」をクリック
2. 「Deploy from GitHub repo」を選択
3. 「Configure GitHub App」をクリック（初回のみ）
4. GitHubの権限設定画面で：
   - 「Only select repositories」を選択
   - 先ほど作成した `discord-bot-web` リポジトリを選択
   - 「Save」をクリック
5. Railwayに戻り、`discord-bot-web` リポジトリを選択
6. 「Deploy Now」をクリック

### 2-3. デプロイの確認

- デプロイが自動で開始されます
- 「View Logs」でビルド状況を確認できます
- 初回は3-5分程度かかります

---

## ステップ3: 環境変数の設定

### 3-1. DATABASE_URLを取得

**既存のDiscordボットプロジェクトから取得：**

1. Railwayダッシュボードで既存のDiscordボットプロジェクトを開く
2. PostgreSQLサービスをクリック
3. 「Variables」タブを開く
4. `DATABASE_URL` の値をコピー（`postgresql://postgres:...` で始まる長い文字列）

### 3-2. Webアプリに環境変数を設定

1. Railwayで **discord-bot-web** プロジェクトを開く
2. デプロイされたサービスをクリック
3. 「Variables」タブを開く
4. 「New Variable」をクリックして以下を追加：

#### 必須の環境変数

| Variable Name | Value | 説明 |
|--------------|-------|------|
| `DATABASE_URL` | コピーしたPostgreSQL URL | DiscordボットのDBと同じ |
| `SECRET_KEY` | ランダムな文字列 | Flaskセッション用（例: `a8f3j9dk2ls0d9fj3k2l` ） |
| `GUILD_ID` | あなたのDiscordギルドID | 数値のみ（例: `123456789012345678`） |

**SECRET_KEYの生成方法：**

PowerShellで実行：
```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

または任意のランダムな文字列（20文字以上推奨）

#### GUILD_IDの確認方法

1. Discordで開発者モードを有効化：
   - 設定 → 詳細設定 → 開発者モード をON
2. サーバーを右クリック → 「IDをコピー」

### 3-3. 環境変数を保存

- すべて入力したら自動で保存されます
- 保存後、自動的に再デプロイが開始されます

---

## ステップ4: 公開URLの設定

### 4-1. ドメインを有効化

1. discord-bot-webプロジェクトのサービスを開く
2. 「Settings」タブを開く
3. 「Networking」セクションを探す
4. 「Generate Domain」をクリック
5. 自動生成されたURL（例: `discord-bot-web-production-xxxx.up.railway.app`）が表示されます

### 4-2. アクセス確認

1. 生成されたURLをブラウザで開く
2. ボス一覧ページが表示されれば成功！

---

## ステップ5: 動作確認

### 5-1. ページの確認

以下のページがすべて動作することを確認：

- **トップページ**: `https://your-app.up.railway.app/`
  - ボス一覧が表示される
  
- **ボス詳細**: `https://your-app.up.railway.app/boss/BOSS_KEY`
  - 参加者とダメージランキングが表示される
  
- **ランキング**: `https://your-app.up.railway.app/rankings`
  - 累計ダメージランキングが表示される

- **ヘルスチェック**: `https://your-app.up.railway.app/health`
  - `{"status":"ok","timestamp":"..."}` が表示される

### 5-2. ログの確認

エラーがある場合：

1. Railwayのプロジェクトを開く
2. 「View Logs」をクリック
3. エラーメッセージを確認

**よくあるエラー：**

- `DATABASE_URL is not set`: 環境変数が設定されていない
- `Connection refused`: DATABASE_URLが間違っている
- `Table does not exist`: ボット側のDBが初期化されていない

---

## ステップ6: 更新とメンテナンス

### 6-1. コードを更新する場合

```powershell
# ローカルでファイルを編集後

cd c:\discord-bot-web

# 変更をコミット
git add .
git commit -m "更新内容の説明"

# GitHubにプッシュ
git push origin main
```

**自動デプロイ**: GitHubにpushすると、Railwayが自動で再デプロイします

### 6-2. 環境変数を変更する場合

1. Railwayのプロジェクトを開く
2. 「Variables」タブで値を変更
3. 自動で再デプロイされます

### 6-3. ログの監視

```
Railway Dashboard → プロジェクト → View Logs
```

リアルタイムでアプリケーションログを確認できます。

---

## トラブルシューティング

### ❌ デプロイが失敗する

**原因**: 依存関係のエラー、構文エラー

**解決方法**:
1. ローカルで動作確認：
   ```powershell
   cd c:\discord-bot-web
   pip install -r requirements.txt
   python app.py
   ```
2. エラーがあれば修正してから再度push

### ❌ ページが表示されない（500エラー）

**原因**: DATABASE_URLが間違っている、DBに接続できない

**解決方法**:
1. Railwayの「Variables」で `DATABASE_URL` を再確認
2. DiscordボットのPostgreSQL URLと一致しているか確認
3. ログを確認：`View Logs`

### ❌ データが表示されない

**原因**: GUILD_IDが間違っている、またはデータがまだない

**解決方法**:
1. `GUILD_ID` が正しいか確認（Discordサーバーのサーバー設定から確認）
2. Discordボットでレイドボスを作成し、データを投入
3. `/api/bosses` にアクセスしてJSONデータを確認

### ❌ "Table does not exist" エラー

**原因**: データベースのテーブルが作成されていない

**解決方法**:
1. Discordボットを一度起動して、テーブルを自動作成させる
2. ボット側の `ensure_db()` が実行されていることを確認

---

## セキュリティ上の注意

### ✅ 推奨事項

1. **環境変数の管理**
   - `.env` ファイルは絶対にGitにコミットしない（`.gitignore` に含まれています）
   - 環境変数はRailwayの管理画面でのみ設定

2. **アクセス制限**
   - 必要に応じて、Railway の Private Networking を利用
   - 特定IPからのみアクセス可能にする（Cloudflare等を利用）

3. **読み取り専用の確保**
   - コード内にINSERT/UPDATE/DELETE文は一切含まれていません
   - 念のため、PostgreSQLで読み取り専用ユーザーを作成することも可能

---

## コスト管理

### Railway 無料プラン

- **実行時間**: 月500時間まで無料
- **データ転送**: 100GB/月まで無料

**推奨設定**:
- アクセスが少ない場合は、スリープ設定を有効化
- 本番環境では有料プランへのアップグレードを検討

### リソース使用量の確認

```
Railway Dashboard → プロジェクト → Metrics
```

CPU、メモリ、ネットワークの使用状況を確認できます。

---

## 完了チェックリスト

デプロイ完了の確認：

- [ ] GitHubリポジトリが作成されている
- [ ] Railwayプロジェクトが作成されている
- [ ] 環境変数 `DATABASE_URL`, `SECRET_KEY`, `GUILD_ID` が設定されている
- [ ] 公開URLが生成されている
- [ ] トップページにアクセスできる
- [ ] ボスデータが表示される（またはデータがない旨のメッセージが表示される）
- [ ] `/health` エンドポイントが `{"status":"ok"}` を返す
- [ ] ログにエラーがない

---

## 次のステップ

✅ デプロイ完了後：

1. Discordボットでレイドボスを作成
2. Webページで討伐履歴を確認
3. 必要に応じてUIをカスタマイズ
4. Discord内でURLを共有

---

## サポート

問題が発生した場合：

1. **Railwayのログ確認**: `View Logs` から詳細を確認
2. **ローカルでテスト**: `python app.py` で動作確認
3. **環境変数の再確認**: DATABASE_URL、GUILD_IDが正しいか確認

---

**🎉 お疲れ様でした！Webアプリケーションのデプロイが完了しました！**
