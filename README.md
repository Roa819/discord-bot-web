# Discord Bot Web Viewer

Discordボットのレイドボス討伐記録を表示するWebアプリケーション（読み取り専用）

## 特徴

- 🔒 **完全読み取り専用**: データベースへの書き込みは一切行いません
- 🚀 **独立したアプリ**: Discordボットとは完全に分離
- 📊 **リアルタイム表示**: ボットと同じデータベースから最新情報を取得
- 🎨 **レスポンシブUI**: モバイルでも見やすいデザイン

## 表示機能

### 1. ボス一覧ページ (`/`)
- 現在のレイドボス状態（HP、討伐済みフラグ）
- ボス一覧と基本情報

### 2. ボス詳細ページ (`/boss/<boss_key>`)
- 参加者一覧
- ダメージランキング（アタックホルダー）
- 攻撃回数、平均ダメージ
- 初回・最終攻撃時刻

### 3. 全期間ランキング (`/rankings`)
- 累計ダメージランキング TOP 50
- 総攻撃回数、参加ボス数

### 4. API エンドポイント
- `/api/bosses` - ボス一覧（JSON）
- `/api/boss/<boss_key>/participants` - 参加者情報（JSON）
- `/api/rankings` - ランキング情報（JSON）

## セットアップ

### 1. 環境変数の設定

`.env` ファイルを作成：

```bash
DATABASE_URL=postgresql://user:password@host:port/database
SECRET_KEY=your-random-secret-key
GUILD_ID=123456789
```

### 2. ローカル実行

```bash
# 依存パッケージのインストール
pip install -r requirements.txt

# アプリケーション起動
python app.py
```

ブラウザで `http://localhost:5000` にアクセス

## Railwayへのデプロイ

### 手順

1. **新しいプロジェクトを作成**
   - Railway ダッシュボードで「New Project」→「Empty Project」

2. **GitHubリポジトリを接続**
   - このディレクトリを別リポジトリとして管理
   - Railwayに接続

3. **環境変数を設定**
   - `DATABASE_URL`: DiscordボットのRailway PostgreSQL URLと同じものを使用
   - `SECRET_KEY`: ランダムな文字列
   - `GUILD_ID`: DiscordのギルドID

4. **デプロイ**
   - 自動でビルド・デプロイされます
   - Public URLが発行されます

### 注意事項

- DiscordボットのDATABASE_URLと**同じ値**を使用してください
- このWebアプリはデータベースに書き込みを行わないため、ボットの動作に影響しません
- ボット側のデプロイとは**完全に独立**しています

## プロジェクト構造

```
discord-bot-web/
├── app.py              # Flaskアプリケーション
├── requirements.txt    # Python依存パッケージ
├── Procfile           # Railway起動コマンド
├── railway.toml       # Railway設定
├── .env.example       # 環境変数テンプレート
├── templates/         # HTMLテンプレート
│   ├── base.html
│   ├── index.html
│   ├── boss_detail.html
│   ├── rankings.html
│   └── user_detail.html
└── static/
    └── style.css      # カスタムスタイル
```

## 技術スタック

- **Flask 3.0**: Pythonウェブフレームワーク
- **asyncpg**: PostgreSQL非同期ドライバ
- **Bootstrap 5**: レスポンシブUIフレームワーク
- **Gunicorn**: プロダクション用WSGIサーバー

## セキュリティ

- すべてのDB操作は `SELECT` のみ（読み取り専用）
- RailwayのPrivate Networkingを使用可能
- 環境変数で機密情報を管理

## ライセンス

Discordボット本体と同じライセンスを適用
