# Railway統一環境デプロイガイド

既存のDiscordボットと同じRailwayプロジェクトでWebアプリを管理する方法

## 方法1: 同じプロジェクトに複数サービス（推奨）

### メリット
- PostgreSQL、Discordボット、Webアプリを1つのプロジェクトで管理
- 環境変数が自動共有（DATABASE_URLなど）
- コスト管理が一元化
- デプロイ状況を一画面で確認可能

---

## ステップ1: GitHubリポジトリの準備

### オプションA: 別リポジトリとして管理（シンプル）

既存のボットとは別リポジトリとして管理します。

```powershell
cd c:\discord-bot-web
git init
git add .
git commit -m "Initial commit: Web viewer"
git remote add origin https://github.com/YOUR_USERNAME/discord-bot-web.git
git push -u origin main
```

### オプションB: モノレポとして統合（上級者向け）

既存のボットリポジトリに統合します。

```powershell
# ボットのリポジトリに移動
cd c:\discord-bot

# Webアプリをサブディレクトリとして追加
# （discord-bot-webの中身をdiscord-bot/web/にコピー）
New-Item -ItemType Directory -Path web -Force
Copy-Item -Path c:\discord-bot-web\* -Destination web\ -Recurse -Force

# コミット
git add web/
git commit -m "Add web viewer to monorepo"
git push origin main
```

**推奨**: オプションA（別リポジトリ）の方がシンプルで管理しやすい

---

## ステップ2: Railway - 既存プロジェクトにWebサービスを追加

### 2-1. 既存のDiscordボットプロジェクトを開く

1. https://railway.app にアクセス
2. 既存のDiscordボットプロジェクトを開く
   - 通常は「PostgreSQL」と「Discord Bot」の2つのサービスがある

### 2-2. 新しいサービスを追加

1. プロジェクト画面で **「+ New」** ボタンをクリック
2. **「GitHub Repo」** を選択
3. 作成した `discord-bot-web` リポジトリを選択
   - モノレポの場合は既存のボットリポジトリを選択
4. **「Add Service」** をクリック

### 2-3. モノレポの場合のみ：ルートパスを設定

モノレポ（オプションB）を選択した場合：

1. 追加したWebサービスをクリック
2. **「Settings」** タブを開く
3. **「Root Directory」** を探す
4. 値を `web` に設定（webディレクトリを指定）
5. 保存

### 2-4. サービス名を変更（オプション）

1. Webサービスをクリック
2. 「Settings」→「Service Name」
3. 名前を `web-viewer` などに変更

---

## ステップ3: 環境変数の設定

### 3-1. プロジェクト共有変数を確認

既存のプロジェクトで共有されている変数：

1. プロジェクトのトップ画面に戻る
2. 「Variables」タブを開く
3. PostgreSQLから以下が自動共有されているはず：
   - `DATABASE_URL`
   - `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD` など

### 3-2. Webサービス固有の変数を追加

1. **Web Viewerサービス** をクリック
2. 「Variables」タブを開く
3. 以下を追加：

| Variable | Value | 説明 |
|----------|-------|------|
| `SECRET_KEY` | ランダム文字列 | Flask用（`python -c "import secrets; print(secrets.token_hex(32))"`） |
| `GUILD_ID` | DiscordギルドID | ボットの環境変数と同じ値 |

**重要**: `DATABASE_URL` は既に共有されているので追加不要！

### 3-3. GUILD_IDを共有変数にする（推奨）

すべてのサービスで使う変数はプロジェクトレベルで設定：

1. プロジェクトのトップ画面で「Variables」タブ
2. 「Shared Variables」セクションで **「New Variable」**
3. `GUILD_ID` を追加（ボットの環境変数からコピー）
4. これで全サービスから参照可能

---

## ステップ4: ドメインの生成

1. **Web Viewerサービス** を開く
2. 「Settings」タブ
3. 「Networking」セクション
4. **「Generate Domain」** をクリック
5. URLが生成される（例: `web-viewer-production.up.railway.app`）

---

## ステップ5: 動作確認

### 5-1. サービス一覧を確認

プロジェクト画面で以下が表示されているはず：

```
📦 Your Discord Bot Project
├── 🗄️ PostgreSQL
├── 🤖 Discord Bot (Running)
└── 🌐 Web Viewer (Running)
```

### 5-2. Webアプリにアクセス

生成されたURLにアクセスして、ボス一覧が表示されることを確認

### 5-3. ログ確認

各サービスの「Logs」タブでエラーがないか確認

---

## ステップ6: 環境変数の統一確認

### 確認項目

| 変数名 | 設定場所 | 共有状態 |
|--------|---------|---------|
| `DATABASE_URL` | PostgreSQLサービス | ✅ 全サービスで自動共有 |
| `GUILD_ID` | 共有変数 | ✅ 全サービスで利用可能 |
| `BOT_TOKEN` | Discord Botサービス | ⚠️ ボットのみ |
| `SECRET_KEY` | Web Viewerサービス | ⚠️ Webのみ |

---

## プロジェクト構成の比較

### 🟢 統一後（推奨）

```
Railway Project: discord-bot-project
├── PostgreSQL
│   └── DATABASE_URL → 全サービスに自動共有
├── Discord Bot
│   ├── BOT_TOKEN (固有)
│   └── GUILD_ID (共有変数を参照)
└── Web Viewer
    ├── SECRET_KEY (固有)
    └── GUILD_ID (共有変数を参照)
```

**メリット**:
- 一元管理
- 環境変数の重複なし
- コスト可視化が容易
- データベース接続の設定ミスが起きにくい

### 🔴 別プロジェクトの場合（非推奨）

```
Railway Project: discord-bot-project
├── PostgreSQL
└── Discord Bot

Railway Project: web-viewer-project
└── Web Viewer
    └── DATABASE_URL を手動でコピー（管理が煩雑）
```

---

## 更新とメンテナンス

### コードを更新する場合

**別リポジトリ（オプションA）**:
```powershell
# Web側の更新
cd c:\discord-bot-web
git add .
git commit -m "Update web viewer"
git push origin main

# Bot側の更新
cd c:\discord-bot
git add .
git commit -m "Update bot"
git push origin main
```

**モノレポ（オプションB）**:
```powershell
cd c:\discord-bot
# Botまたはwebを更新
git add .
git commit -m "Update bot/web"
git push origin main
```

どちらもGitHub pushで自動デプロイされます。

---

## トラブルシューティング

### ❌ DATABASE_URLが見つからない

**原因**: サービス間で変数が共有されていない

**解決方法**:
1. プロジェクトのトップ画面で「Variables」を確認
2. PostgreSQLサービスの変数が「Shared」になっているか確認
3. 必要に応じて手動で追加

### ❌ 2つのサービスが同時に起動できない

**原因**: Railwayの無料プランの制限

**解決方法**:
- Starter プラン（月$5）にアップグレード
- または、Webアプリのみスリープ設定を有効化

### ❌ モノレポでビルドエラー

**原因**: Root Directoryが正しく設定されていない

**解決方法**:
1. Webサービスの「Settings」
2. 「Root Directory」を `web` に設定
3. 再デプロイ

---

## コスト管理

### 統一プロジェクトのメリット

- すべてのリソース使用量を1画面で確認
- PostgreSQLは1つで済む（追加料金なし）
- 無料枠（月500実行時間）を効率的に配分

### リソース配分の推奨

```
合計 500時間/月（無料プラン）
├── PostgreSQL: 24時間×30日 = 720時間（実際はカウントされない）
├── Discord Bot: 24時間×30日 = 720時間（常時起動推奨）
└── Web Viewer: オンデマンド（アクセス時のみ）
```

**推奨**: ボットは常時起動、Webは必要時のみ起動

---

## セキュリティ

### 統一環境での注意点

1. **環境変数の適切な分離**
   - ボット専用: `BOT_TOKEN`（他のサービスに見せない）
   - Web専用: `SECRET_KEY`
   - 共有: `DATABASE_URL`, `GUILD_ID`

2. **読み取り専用の保証**
   - WebアプリはSELECTクエリのみ
   - INSERTはボットのみ

3. **アクセス制御**
   - 必要に応じてWebアプリに認証を追加
   - RailwayのPrivate Networkingを活用

---

## 完了チェックリスト

- [ ] GitHubリポジトリが準備されている（別リポまたはモノレポ）
- [ ] Railway既存プロジェクトにWebサービスが追加されている
- [ ] PostgreSQLの変数が全サービスで共有されている
- [ ] GUILD_IDが共有変数として設定されている
- [ ] WebサービスにSECRET_KEYが設定されている
- [ ] Webサービスの公開URLが生成されている
- [ ] 3つのサービスすべてが正常に動作している
- [ ] Webアプリでボスデータが表示される

---

## まとめ

### 統一環境のメリット

✅ **管理の簡素化**: 1つのプロジェクトで全体を管理
✅ **環境変数の自動共有**: DATABASE_URLの設定ミス防止
✅ **コスト最適化**: リソース使用量を一元管理
✅ **デプロイの一元化**: すべてのサービスを1画面で監視

### 推奨構成

```
同じRailwayプロジェクト
+ 別々のGitHubリポジトリ（bot用とweb用）
+ 環境変数は共有と固有を使い分け
```

これで、DiscordボットとWebアプリが統一された環境で動作します！

---

**🎉 統一環境の構築完了です！**
