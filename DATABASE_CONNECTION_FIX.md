# データベース接続エラー修正

## 問題
アプリケーションで `asyncpg.exceptions.ConnectionDoesNotExistError: connection was closed in the middle of operation` エラーが発生していました。これはデータベース接続が操作中に予期せず閉じられたことを示しています。

## 原因
- データベース接続が長時間アイドル状態になるとタイムアウトする
- 接続プールの設定が不十分
- ネットワークの問題や一時的な接続断
- 再接続ロジックが実装されていない

## 実施した修正

### 1. 接続プールの設定を改善
```python
db_pool = await asyncpg.create_pool(
    DATABASE_URL,
    min_size=1,
    max_size=5,
    command_timeout=30,  # 10秒から30秒に延長
    max_inactive_connection_lifetime=300,  # 5分後に非アクティブな接続をリサイクル
    server_settings={
        'application_name': 'discord_bot_web',
        'tcp_keepalives_idle': '60',
        'tcp_keepalives_interval': '10',
        'tcp_keepalives_count': '5'
    }
)
```

### 2. 自動リトライ機能を追加
新しい `execute_with_retry` 関数を実装:
- 接続エラー時に最大3回まで自動リトライ
- 指数バックオフ戦略（0.5秒、1秒、1.5秒）
- エラー時に接続プールを再初期化

### 3. すべてのデータベースクエリにリトライロジックを適用
以下の関数を更新:
- `get_defeat_history()`
- `get_active_bosses()`
- `get_defeat_history_detail()`
- `get_defeat_participants()`
- `get_attack_history()`
- `get_all_time_rankings()`
- `get_fastest_clears()`
- `get_user_stats()`
- `get_attack_holder()`
- `get_attack_holder_by_boss()`

### 4. エラーハンドリングをルートに追加
すべてのルートに try-catch ブロックを追加し、エラー時にユーザーフレンドリーなメッセージを表示:
- `/` - トップページ
- `/defeat/<int:defeat_id>` - 討伐詳細
- `/rankings` - ランキング
- `/user/<int:user_id>` - ユーザー詳細
- `/attack-holder` - アタックホルダー

## 技術詳細

### 接続プール設定の説明
- **command_timeout**: クエリのタイムアウト時間（30秒）
- **max_inactive_connection_lifetime**: 非アクティブな接続を自動的にクローズする時間（5分）
- **tcp_keepalives_idle**: TCP キープアライブが開始されるまでのアイドル時間（60秒）
- **tcp_keepalives_interval**: TCP キープアライブプローブの間隔（10秒）
- **tcp_keepalives_count**: TCP キープアライブプローブの最大数（5回）

### リトライ戦略
```python
async def execute_with_retry(func, *args, max_retries=3, **kwargs):
    for attempt in range(max_retries):
        try:
            pool = await init_db_pool()
            return await func(pool, *args, **kwargs)
        except (asyncpg.exceptions.ConnectionDoesNotExistError,
                asyncpg.exceptions.ConnectionFailureError,
                asyncpg.exceptions.InterfaceError) as e:
            # 接続プールを再初期化
            # 指数バックオフで待機
            await asyncio.sleep(0.5 * (attempt + 1))
```

## 期待される改善
1. **接続の安定性**: TCP キープアライブと自動リサイクルにより、接続が維持される
2. **一時的な障害への耐性**: 自動リトライにより一時的なネットワーク問題に対応
3. **ユーザーエクスペリエンス**: エラー時に適切なメッセージを表示
4. **ログ**: エラーがログに記録され、トラブルシューティングが容易に

## 監視すべき点
- アプリケーションログで接続エラーの頻度を確認
- データベース接続プールのメトリクス
- リトライが頻繁に発生する場合は、より根本的な問題がある可能性

## 今後の改善案
1. 接続プールのメトリクス収集
2. サーキットブレーカーパターンの実装
3. データベース接続状態のヘルスチェックエンドポイント
4. キャッシュレイヤーの追加（Redis等）
