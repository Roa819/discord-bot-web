"""
Discord Bot Web Viewer - 完全読み取り専用
既存のDiscordボットとは完全に独立したWebアプリケーション
"""

import os
import asyncio
import threading
import signal
import atexit
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from flask import Flask, render_template, jsonify
import asyncpg

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key')

DATABASE_URL = os.getenv('DATABASE_URL')
GUILD_ID = int(os.getenv('GUILD_ID', '0'))


# カスタムフィルター: 数値にカンマを追加
@app.template_filter('format_number')
def format_number(value):
    """数値を3桁カンマ区切りでフォーマット"""
    try:
        return "{:,}".format(int(value))
    except (ValueError, TypeError):
        return value

# カスタムフィルター: UTCからJSTに変換
@app.template_filter('to_jst')
def to_jst(value):
    """UTCの日時をJSTに変換してフォーマット"""
    if value is None:
        return 'N/A'
    try:
        # UTCとして扱い、JSTに変換
        if value.tzinfo is None:
            value = value.replace(tzinfo=ZoneInfo('UTC'))
        jst_time = value.astimezone(ZoneInfo('Asia/Tokyo'))
        return jst_time.strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        return str(value)

# カスタムフィルター: 短い日時フォーマット（JST）
@app.template_filter('to_jst_short')
def to_jst_short(value):
    """UTCの日時をJSTに変換して短い形式でフォーマット"""
    if value is None:
        return 'N/A'
    try:
        if value.tzinfo is None:
            value = value.replace(tzinfo=ZoneInfo('UTC'))
        jst_time = value.astimezone(ZoneInfo('Asia/Tokyo'))
        return jst_time.strftime('%m/%d %H:%M')
    except Exception:
        return str(value)

# データベース接続プール (読み取り専用)
db_pool = None
loop = None
loop_thread = None


def get_or_create_eventloop():
    """グローバルなイベントループを取得または作成"""
    global loop, loop_thread
    if loop is None or loop.is_closed():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop


def run_async(coro):
    """非同期関数を同期的に実行"""
    loop = get_or_create_eventloop()
    return loop.run_until_complete(coro)


async def init_db_pool():
    """データベース接続プールを初期化 (読み取り専用)"""
    global db_pool
    if db_pool is None or db_pool._closed:
        db_pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=1,
            max_size=5,
            command_timeout=10
        )
    return db_pool


async def close_db_pool():
    """データベース接続プールをクローズ"""
    global db_pool
    if db_pool is not None and not db_pool._closed:
        await db_pool.close()
        db_pool = None


def cleanup():
    """アプリケーション終了時のクリーンアップ"""
    global loop
    if loop and not loop.is_closed():
        try:
            loop.run_until_complete(close_db_pool())
        except Exception:
            pass


def signal_handler(signum, frame):
    """シグナルハンドラー"""
    cleanup()
    exit(0)


async def get_defeat_history():
    """討伐履歴一覧を取得"""
    # データベース接続がない場合はモックデータを返す
    if not DATABASE_URL:
        from datetime import datetime, timedelta
        now = datetime.utcnow()
        return [
            {
                'id': 1,
                'boss_key': 'Fatal_Lake',
                'boss_name': 'フェル・レイク',
                'boss_max_hp': 1500,
                'defeated_at': now - timedelta(hours=2),
                'total_participants': 3,
                'total_damage': 1650
            },
            {
                'id': 2,
                'boss_key': 'Timed_Dragon',
                'boss_name': '時間の番竜',
                'boss_max_hp': 3000,
                'defeated_at': now - timedelta(days=1, hours=5),
                'total_participants': 5,
                'total_damage': 3200
            },
            {
                'id': 3,
                'boss_key': 'Fatal_Lake',
                'boss_name': 'フェル・レイク',
                'boss_max_hp': 1500,
                'defeated_at': now - timedelta(days=2, hours=3),
                'total_participants': 4,
                'total_damage': 1550
            },
            {
                'id': 4,
                'boss_key': 'Fatal_Lake',
                'boss_name': 'フェル・レイク',
                'boss_max_hp': 1500,
                'defeated_at': now - timedelta(days=3, hours=8),
                'total_participants': 2,
                'total_damage': 1520
            },
            {
                'id': 5,
                'boss_key': 'Timed_Dragon',
                'boss_name': '時間の番竜',
                'boss_max_hp': 3000,
                'defeated_at': now - timedelta(days=4, hours=12),
                'total_participants': 6,
                'total_damage': 3100
            }
        ]
    
    pool = await init_db_pool()
    async with pool.acquire() as conn:
        history = await conn.fetch("""
            SELECT 
                id,
                boss_key,
                boss_name,
                boss_max_hp,
                defeated_at,
                total_participants,
                total_damage
            FROM raid_defeat_history
            WHERE guild_id = $1
            ORDER BY defeated_at DESC
            LIMIT 100
        """, GUILD_ID)
        return [dict(h) for h in history]


async def get_active_bosses():
    """討伐済みのボス一覧を取得（過去の履歴）"""
    # データベース接続がない場合はモックデータを返す
    if not DATABASE_URL:
        from datetime import datetime, timedelta
        now = datetime.utcnow()
        # 複数の討伐履歴をシミュレート
        return [
            {
                'id': 1,
                'boss_key': 'Fatal_Lake',
                'boss_name': 'フェル・レイク',
                'current_hp': 0,
                'max_hp': 1500,
                'defeated': True,
                'spawned_at': now - timedelta(days=5, hours=3),
                'defeated_at': now - timedelta(days=5, hours=1),
                'participant_count': 3,
                'total_damage': 1500
            },
            {
                'id': 2,
                'boss_key': 'Timed_Dragon',
                'boss_name': '時間の番竜',
                'current_hp': 0,
                'max_hp': 3000,
                'defeated': True,
                'spawned_at': now - timedelta(days=4, hours=8),
                'defeated_at': now - timedelta(days=4, hours=5),
                'participant_count': 5,
                'total_damage': 3200
            },
            {
                'id': 3,
                'boss_key': 'Fatal_Lake',
                'boss_name': 'フェル・レイク',
                'current_hp': 0,
                'max_hp': 1500,
                'defeated': True,
                'spawned_at': now - timedelta(days=3, hours=12),
                'defeated_at': now - timedelta(days=3, hours=9),
                'participant_count': 4,
                'total_damage': 1600
            },
            {
                'id': 4,
                'boss_key': 'Fatal_Lake',
                'boss_name': 'フェル・レイク',
                'current_hp': 0,
                'max_hp': 1500,
                'defeated': True,
                'spawned_at': now - timedelta(days=2, hours=6),
                'defeated_at': now - timedelta(days=2, hours=3),
                'participant_count': 2,
                'total_damage': 1500
            },
            {
                'id': 5,
                'boss_key': 'Timed_Dragon',
                'boss_name': '時間の番竜',
                'current_hp': 0,
                'max_hp': 3000,
                'defeated': True,
                'spawned_at': now - timedelta(days=1, hours=15),
                'defeated_at': now - timedelta(days=1, hours=12),
                'participant_count': 6,
                'total_damage': 3500
            },
            {
                'id': 6,
                'boss_key': 'Fatal_Lake',
                'boss_name': 'フェル・レイク',
                'current_hp': 0,
                'max_hp': 1500,
                'defeated': True,
                'spawned_at': now - timedelta(days=1, hours=2),
                'defeated_at': now - timedelta(hours=23),
                'participant_count': 3,
                'total_damage': 1550
            },
            {
                'id': 7,
                'boss_key': 'Fatal_Lake',
                'boss_name': 'フェル・レイク',
                'current_hp': 0,
                'max_hp': 1500,
                'defeated': True,
                'spawned_at': now - timedelta(hours=20),
                'defeated_at': now - timedelta(hours=18),
                'participant_count': 4,
                'total_damage': 1600
            },
            {
                'id': 8,
                'boss_key': 'Timed_Dragon',
                'boss_name': '時間の番竜',
                'current_hp': 0,
                'max_hp': 3000,
                'defeated': True,
                'spawned_at': now - timedelta(hours=15),
                'defeated_at': now - timedelta(hours=12),
                'participant_count': 5,
                'total_damage': 3100
            },
            {
                'id': 9,
                'boss_key': 'Fatal_Lake',
                'boss_name': 'フェル・レイク',
                'current_hp': 0,
                'max_hp': 1500,
                'defeated': True,
                'spawned_at': now - timedelta(hours=8),
                'defeated_at': now - timedelta(hours=6),
                'participant_count': 3,
                'total_damage': 1520
            },
            {
                'id': 10,
                'boss_key': 'Fatal_Lake',
                'boss_name': 'フェル・レイク',
                'current_hp': 0,
                'max_hp': 1500,
                'defeated': True,
                'spawned_at': now - timedelta(hours=3),
                'defeated_at': now - timedelta(hours=1),
                'participant_count': 2,
                'total_damage': 1500
            }
        ]
    
    pool = await init_db_pool()
    async with pool.acquire() as conn:
        # 履歴テーブルから取得
        bosses = await conn.fetch("""
            SELECT 
                id,
                boss_key,
                boss_name,
                0 as current_hp,
                boss_max_hp as max_hp,
                true as defeated,
                spawned_at,
                defeated_at,
                participant_count,
                total_damage
            FROM raid_boss_history
            WHERE guild_id = $1
            ORDER BY defeated_at DESC
            LIMIT 100
        """, GUILD_ID)
        return [dict(b) for b in bosses]


async def get_defeat_participants(defeat_history_id: int):
    """討伐履歴の参加者とダメージランキングを取得"""
    # データベース接続がない場合はモックデータを返す
    if not DATABASE_URL:
        from datetime import datetime, timedelta
        now = datetime.utcnow()
        return [
            {
                'user_id': 123456789012345678,
                'user_name': 'Player1',
                'action_count': 10,
                'total_damage': 550,
                'first_attack_at': now - timedelta(minutes=30),
                'last_attack_at': now - timedelta(minutes=5)
            },
            {
                'user_id': 234567890123456789,
                'user_name': 'Player2',
                'action_count': 8,
                'total_damage': 480,
                'first_attack_at': now - timedelta(minutes=25),
                'last_attack_at': now - timedelta(minutes=10)
            },
            {
                'user_id': 345678901234567890,
                'user_name': 'Player3',
                'action_count': 12,
                'total_damage': 620,
                'first_attack_at': now - timedelta(minutes=28),
                'last_attack_at': now - timedelta(minutes=3)
            }
        ]
    
    pool = await init_db_pool()
    async with pool.acquire() as conn:
        participants = await conn.fetch("""
            SELECT 
                user_id,
                user_name,
                action_count,
                total_damage,
                first_attack_at,
                last_attack_at
            FROM raid_defeat_participants
            WHERE defeat_history_id = $1
            ORDER BY total_damage DESC
        """, defeat_history_id)
        return [dict(p) for p in participants]


async def get_all_time_rankings():
    """全期間の累計ダメージランキング"""
    # データベース接続がない場合はモックデータを返す
    if not DATABASE_URL:
        return [
            {
                'user_id': 123456789012345678,
                'user_name': 'Player1',
                'total_defeats': 15,
                'total_damage': 8500,
                'total_actions': 150
            },
            {
                'user_id': 234567890123456789,
                'user_name': 'Player2',
                'total_defeats': 12,
                'total_damage': 7200,
                'total_actions': 120
            },
            {
                'user_id': 345678901234567890,
                'user_name': 'Player3',
                'total_defeats': 18,
                'total_damage': 9100,
                'total_actions': 180
            },
            {
                'user_id': 456789012345678901,
                'user_name': 'Player4',
                'total_defeats': 10,
                'total_damage': 6500,
                'total_actions': 100
            },
            {
                'user_id': 567890123456789012,
                'user_name': 'Player5',
                'total_defeats': 8,
                'total_damage': 5200,
                'total_actions': 80
            }
        ]
    
    pool = await init_db_pool()
    async with pool.acquire() as conn:
        rankings = await conn.fetch("""
            SELECT 
                dp.user_id,
                dp.user_name,
                COUNT(DISTINCT dp.defeat_history_id) as total_defeats,
                SUM(dp.total_damage) as total_damage,
                SUM(dp.action_count) as total_actions
            FROM raid_defeat_participants dp
            JOIN raid_defeat_history dh ON dp.defeat_history_id = dh.id
            WHERE dh.guild_id = $1
            GROUP BY dp.user_id, dp.user_name
            ORDER BY total_damage DESC
            LIMIT 50
        """, GUILD_ID)
        return [dict(r) for r in rankings]

async def get_user_stats(user_id):
    """特定ユーザーの統計を取得"""
    # データベース接続がない場合はモックデータを返す
    if DATABASE_URL is None:
        return {
            'user_id': user_id,
            'total_defeats': 15,
            'total_damage': 8500,
            'total_actions': 150
        }
    
    pool = await init_db_pool()
    async with pool.acquire() as conn:
        stats = await conn.fetchrow("""
            SELECT 
                COUNT(*) as total_defeats,
                SUM(total_damage) as total_damage,
                SUM(action_count) as total_actions
            FROM raid_defeat_participants dp
            JOIN raid_defeat_history dh ON dp.defeat_history_id = dh.id
            WHERE dh.guild_id = $1 AND dp.user_id = $2
        """, GUILD_ID, user_id)
        return dict(stats) if stats else {}


# ===== ルート定義 =====

@app.route('/')
def index():
    """討伐履歴一覧"""
    history = run_async(get_defeat_history())
    return render_template('index.html', history=history)


@app.route('/defeat/<int:defeat_id>')
def defeat_detail(defeat_id):
    """討伐詳細：参加者とダメージランキング"""
    participants = run_async(get_defeat_participants(defeat_id))
    history_list = run_async(get_defeat_history())
    
    # 該当討伐の情報を取得
    defeat_info = next((h for h in history_list if h['id'] == defeat_id), None)
    
    return render_template(
        'boss_detail.html',
        defeat=defeat_info,
        defeat_id=defeat_id,
        participants=participants
    )


@app.route('/rankings')
def rankings():
    """全期間ランキング"""
    rankings = run_async(get_all_time_rankings())
    return render_template('rankings.html', rankings=rankings)


@app.route('/user/<int:user_id>')
def user_detail(user_id):
    """ユーザー詳細統計"""
    stats = run_async(get_user_stats(user_id))
    return render_template('user_detail.html', stats=stats, user_id=user_id)


# ===== API エンドポイント =====

@app.route('/api/defeat-history')
def api_defeat_history():
    """API: 討伐履歴一覧"""
    history = run_async(get_defeat_history())
    return jsonify(history)


@app.route('/api/defeat/<int:defeat_id>/participants')
def api_defeat_participants(defeat_id):
    """API: 討伐参加者"""
    participants = run_async(get_defeat_participants(defeat_id))
    return jsonify(participants)


@app.route('/api/rankings')
def api_rankings():
    """API: 全期間ランキング"""
    rankings = run_async(get_all_time_rankings())
    return jsonify(rankings)


@app.route('/health')
def health():
    """ヘルスチェック (Railwayモニタリング用)"""
    return jsonify({"status": "ok", "timestamp": datetime.utcnow().isoformat()})


# クリーンアップとシグナルハンドラーを登録
atexit.register(cleanup)
signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)


if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
