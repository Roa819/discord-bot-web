"""
Discord Bot Web Viewer - 完全読み取り専用
既存のDiscordボットとは完全に独立したWebアプリケーション
"""

import os
import asyncio
import threading
import signal
import atexit
import json
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

# カスタムフィルター: JSON文字列をパース
@app.template_filter('parse_json')
def parse_json(value):
    """JSON文字列をPythonオブジェクトに変換"""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return None
    return value

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
                'last_attack_at': now - timedelta(minutes=5),
                'last_turn_log': {
                    'turns': [
                        {'turn': 1, 'action': '通常攻撃', 'damage': 55, 'boss_hp': 1445},
                        {'turn': 2, 'action': '必殺技', 'damage': 120, 'boss_hp': 1325},
                        {'turn': 3, 'action': '通常攻撃', 'damage': 48, 'boss_hp': 1277},
                        {'turn': 4, 'action': 'スキル発動', 'damage': 85, 'boss_hp': 1192},
                        {'turn': 5, 'action': '通常攻撃', 'damage': 52, 'boss_hp': 1140}
                    ],
                    'total_damage': 550,
                    'final_hp': 950
                }
            },
            {
                'user_id': 234567890123456789,
                'user_name': 'Player2',
                'action_count': 8,
                'total_damage': 480,
                'first_attack_at': now - timedelta(minutes=25),
                'last_attack_at': now - timedelta(minutes=10),
                'last_turn_log': {
                    'turns': [
                        {'turn': 1, 'action': '通常攻撃', 'damage': 60, 'boss_hp': 890},
                        {'turn': 2, 'action': '通常攻撃', 'damage': 58, 'boss_hp': 832},
                        {'turn': 3, 'action': '必殺技', 'damage': 135, 'boss_hp': 697},
                        {'turn': 4, 'action': '通常攻撃', 'damage': 62, 'boss_hp': 635}
                    ],
                    'total_damage': 480,
                    'final_hp': 470
                }
            },
            {
                'user_id': 345678901234567890,
                'user_name': 'Player3',
                'action_count': 12,
                'total_damage': 620,
                'first_attack_at': now - timedelta(minutes=28),
                'last_attack_at': now - timedelta(minutes=3),
                'last_turn_log': {
                    'turns': [
                        {'turn': 1, 'action': '通常攻撃', 'damage': 50, 'boss_hp': 420},
                        {'turn': 2, 'action': 'スキル発動', 'damage': 95, 'boss_hp': 325},
                        {'turn': 3, 'action': '通常攻撃', 'damage': 48, 'boss_hp': 277},
                        {'turn': 4, 'action': '必殺技', 'damage': 150, 'boss_hp': 127},
                        {'turn': 5, 'action': '通常攻撃', 'damage': 45, 'boss_hp': 82},
                        {'turn': 6, 'action': 'トドメの一撃', 'damage': 82, 'boss_hp': 0}
                    ],
                    'total_damage': 620,
                    'final_hp': 0
                }
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
                last_attack_at,
                last_turn_log
            FROM raid_defeat_participants
            WHERE defeat_history_id = $1
            ORDER BY total_damage DESC
        """, defeat_history_id)
        
        result = []
        for p in participants:
            participant_dict = dict(p)
            # last_turn_logを確実にパースする
            log_data = participant_dict.get('last_turn_log')
            if log_data:
                # 文字列の場合はパース
                if isinstance(log_data, str):
                    try:
                        participant_dict['last_turn_log'] = json.loads(log_data)
                    except (json.JSONDecodeError, TypeError):
                        participant_dict['last_turn_log'] = None
                # すでにlistやdictの場合はそのまま使用
                elif not isinstance(log_data, (list, dict)):
                    participant_dict['last_turn_log'] = None
            result.append(participant_dict)
        
        return result


async def get_defeat_attack_history(defeat_history_id: int):
    """討伐履歴の個別攻撃を時系列順に取得 - Updated v2"""
    try:
        if not DATABASE_URL:
            from datetime import datetime, timedelta
            now = datetime.utcnow()
            return [
                {
                    'user_id': 123456789012345678,
                    'user_name': 'Player1',
                    'damage': 84,
                    'is_crit': True,
                    'attacked_at': now - timedelta(minutes=30),
                    'sequence': 1
                },
                {
                    'user_id': 234567890123456789,
                    'user_name': 'Player2',
                    'damage': 56,
                    'is_crit': False,
                    'attacked_at': now - timedelta(minutes=29),
                    'sequence': 2
                },
                {
                    'user_id': 123456789012345678,
                    'user_name': 'Player1',
                    'damage': 56,
                    'is_crit': False,
                    'attacked_at': now - timedelta(minutes=28),
                    'sequence': 3
                }
            ]
        
        pool = await init_db_pool()
        async with pool.acquire() as conn:
            # まず raid_actions テーブルが存在するか確認
            table_exists = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'raid_actions'
                )
            """)
            
            if not table_exists:
                # raid_actions がない場合、participants から last_turn_log を展開
                participants = await conn.fetch("""
                    SELECT 
                        user_id,
                        user_name,
                        last_turn_log,
                        first_attack_at
                    FROM raid_defeat_participants
                    WHERE defeat_history_id = $1
                    ORDER BY first_attack_at
                """, defeat_history_id)
                
                print(f"DEBUG: Found {len(participants)} participants for defeat {defeat_history_id}")
                
                # last_turn_log を展開して履歴を作成
                history = []
                sequence = 1
                for p in participants:
                    log_data = p['last_turn_log']
                    print(f"DEBUG: User {p['user_name']}, log_data type: {type(log_data)}, is string: {isinstance(log_data, str)}")
                    
                    # 文字列の場合はパース
                    if isinstance(log_data, str):
                        try:
                            log_data = json.loads(log_data)
                            print(f"DEBUG: Parsed to type: {type(log_data)}, is list: {isinstance(log_data, list)}, length: {len(log_data) if isinstance(log_data, list) else 'N/A'}")
                            
                            # 二重エンコードされている場合、もう一度パース
                            if isinstance(log_data, str):
                                log_data = json.loads(log_data)
                                print(f"DEBUG: Double-encoded! Parsed again to type: {type(log_data)}, is list: {isinstance(log_data, list)}")
                            
                            if isinstance(log_data, list) and len(log_data) > 0:
                                print(f"DEBUG: First element type: {type(log_data[0])}, is dict: {isinstance(log_data[0], dict)}")
                                if isinstance(log_data[0], dict):
                                    print(f"DEBUG: First element keys: {log_data[0].keys()}, actor value: {log_data[0].get('actor')}, actor type: {type(log_data[0].get('actor'))}")
                        except (json.JSONDecodeError, TypeError) as e:
                            print(f"DEBUG: JSON parse error: {e}")
                            log_data = None
                    # リストまたは辞書の場合はそのまま使用
                    elif not isinstance(log_data, (list, dict)):
                        print(f"DEBUG: Unexpected type, setting to None")
                        log_data = None
                    
                    if log_data and isinstance(log_data, list):
                        print(f"DEBUG: Processing {len(log_data)} actions for {p['user_name']}")
                        # 全てのアクション（プレイヤーとボス）を追加
                        for idx, action in enumerate(log_data):
                            # プレイヤーの攻撃のみを履歴に追加
                            if action.get('actor') == 'player':
                                print(f"DEBUG: Adding player action: damage={action.get('damage')}, crit={action.get('is_crit')}, miss={action.get('is_miss')}")
                                history.append({
                                    'user_id': p['user_id'],
                                    'user_name': p['user_name'],
                                    'damage': action.get('damage', 0),
                                    'is_crit': action.get('is_crit', False),
                                    'is_miss': action.get('is_miss', False),
                                    'attacked_at': p['first_attack_at'],
                                    'sequence': sequence
                                })
                                sequence += 1
                    else:
                        print(f"DEBUG: log_data is not a list or is None for {p['user_name']}")
                
                print(f"DEBUG: Returning {len(history)} attacks")
                return history
            else:
                # raid_actions テーブルから取得
                actions = await conn.fetch("""
                    SELECT 
                        user_id,
                        user_name,
                        damage,
                        is_crit,
                        attacked_at,
                        ROW_NUMBER() OVER (ORDER BY attacked_at) as sequence
                    FROM raid_actions
                    WHERE defeat_history_id = $1
                    ORDER BY attacked_at
                """, defeat_history_id)
                return [dict(a) for a in actions]
    
    except Exception as e:
        print(f"ERROR in get_defeat_attack_history: {e}")
        import traceback
        traceback.print_exc()
        return []


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
            'total_actions': 150,
            'bosses_defeated': [
                {
                    'boss_key': 'Fatal_Lake',
                    'boss_name': 'フェル・レイク',
                    'defeat_count': 8,
                    'total_damage': 4500
                },
                {
                    'boss_key': 'Timed_Dragon',
                    'boss_name': '時間の番竜',
                    'defeat_count': 7,
                    'total_damage': 4000
                }
            ]
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
        
        boss_stats = await conn.fetch("""
            SELECT 
                dh.boss_key,
                dh.boss_name,
                COUNT(*) as defeat_count,
                SUM(dp.total_damage) as total_damage
            FROM raid_defeat_participants dp
            JOIN raid_defeat_history dh ON dp.defeat_history_id = dh.id
            WHERE dh.guild_id = $1 AND dp.user_id = $2
            GROUP BY dh.boss_key, dh.boss_name
            ORDER BY defeat_count DESC
        """, GUILD_ID, user_id)
        
        result = dict(stats) if stats else {}
        result['bosses_defeated'] = [dict(b) for b in boss_stats]
        return result


async def get_attack_holder(boss_key=None, limit=100):
    """単発最大ダメージランキング（アタックホルダー）"""
    if DATABASE_URL is None:
        return [
            {
                'user_id': 345678901234567890,
                'user_name': 'Player3',
                'max_single_damage': 850,
                'boss_name': 'フェル・レイク',
                'boss_key': 'Fatal_Lake',
                'defeated_at': datetime.utcnow(),
                'defeat_history_id': 3
            },
            {
                'user_id': 123456789012345678,
                'user_name': 'Player1',
                'max_single_damage': 780,
                'boss_name': '時間の番竜',
                'boss_key': 'Timed_Dragon',
                'defeated_at': datetime.utcnow(),
                'defeat_history_id': 5
            }
        ]
    
    pool = await init_db_pool()
    async with pool.acquire() as conn:
        if boss_key:
            rows = await conn.fetch("""
                SELECT 
                    dp.user_id,
                    dp.user_name,
                    MAX(dp.total_damage) as max_single_damage,
                    dh.boss_name,
                    dh.defeated_at,
                    dh.id as defeat_history_id
                FROM raid_defeat_participants dp
                JOIN raid_defeat_history dh ON dp.defeat_history_id = dh.id
                WHERE dh.guild_id=$1 AND dh.boss_key=$2
                GROUP BY dp.user_id, dp.user_name, dh.boss_name, dh.defeated_at, dh.id
                HAVING MAX(dp.total_damage) = (
                    SELECT MAX(dp2.total_damage)
                    FROM raid_defeat_participants dp2
                    JOIN raid_defeat_history dh2 ON dp2.defeat_history_id = dh2.id
                    WHERE dh2.guild_id=$1 AND dh2.boss_key=$2 AND dp2.user_id = dp.user_id
                )
                ORDER BY max_single_damage DESC
                LIMIT $3
            """, GUILD_ID, boss_key, limit)
        else:
            rows = await conn.fetch("""
                SELECT 
                    dp.user_id,
                    dp.user_name,
                    MAX(dp.total_damage) as max_single_damage,
                    dh.boss_name,
                    dh.boss_key,
                    dh.defeated_at,
                    dh.id as defeat_history_id
                FROM raid_defeat_participants dp
                JOIN raid_defeat_history dh ON dp.defeat_history_id = dh.id
                WHERE dh.guild_id=$1
                GROUP BY dp.user_id, dp.user_name, dh.boss_name, dh.boss_key, dh.defeated_at, dh.id
                HAVING MAX(dp.total_damage) = (
                    SELECT MAX(dp2.total_damage)
                    FROM raid_defeat_participants dp2
                    JOIN raid_defeat_history dh2 ON dp2.defeat_history_id = dh2.id
                    WHERE dh2.guild_id=$1 AND dp2.user_id = dp.user_id
                )
                ORDER BY max_single_damage DESC
                LIMIT $2
            """, GUILD_ID, limit)
        return [dict(r) for r in rows]


async def get_fastest_clears(limit=20):
    """最速討伐記録"""
    if DATABASE_URL is None:
        from datetime import timedelta
        return [
            {
                'id': 1,
                'boss_name': 'フェル・レイク',
                'defeated_at': datetime.utcnow(),
                'total_participants': 5,
                'clear_time': timedelta(minutes=15, seconds=30)
            },
            {
                'id': 2,
                'boss_name': '時間の番竜',
                'defeated_at': datetime.utcnow(),
                'total_participants': 6,
                'clear_time': timedelta(minutes=28, seconds=45)
            }
        ]
    
    pool = await init_db_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT 
                id,
                guild_id,
                boss_key,
                boss_name,
                boss_max_hp,
                defeated_at,
                total_participants,
                total_damage,
                (
                    SELECT MAX(last_attack_at) - MIN(first_attack_at)
                    FROM raid_defeat_participants
                    WHERE defeat_history_id = raid_defeat_history.id
                ) as clear_time
            FROM raid_defeat_history
            WHERE guild_id=$1
            ORDER BY clear_time ASC
            LIMIT $2
        """, GUILD_ID, limit)
        return [dict(r) for r in rows]


# ===== ルート定義 =====

@app.route('/')
def index():
    """討伐履歴一覧"""
    history = run_async(get_defeat_history())
    return render_template('index.html', history=history)


@app.route('/defeat/<int:defeat_id>')
def defeat_detail(defeat_id):
    """討伐詳細：攻撃履歴"""
    attack_history = run_async(get_defeat_attack_history(defeat_id))
    participants = run_async(get_defeat_participants(defeat_id))
    history_list = run_async(get_defeat_history())
    
    # 該当討伐の情報を取得
    defeat_info = next((h for h in history_list if h['id'] == defeat_id), None)
    
    return render_template(
        'boss_detail.html',
        defeat=defeat_info,
        defeat_id=defeat_id,
        participants=participants,
        attack_history=attack_history
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


@app.route('/attack-holder')
def attack_holder_page():
    """アタックホルダー（単発最大ダメージランキング）"""
    holders = run_async(get_attack_holder(limit=50))
    return render_template('attack_holder.html', holders=holders)


@app.route('/fastest-clears')
def fastest_clears_page():
    """最速討伐記録"""
    clears = run_async(get_fastest_clears(limit=20))
    return render_template('fastest_clears.html', clears=clears)


# ===== API エンドポイント =====

@app.route('/api/defeat-history/<int:guild_id>')
def api_defeat_history(guild_id):
    """API: 討伐履歴一覧（仕様書準拠）"""
    from flask import request
    boss_key = request.args.get('boss_key')
    limit = int(request.args.get('limit', 50))
    # 簡易実装（GUILD_IDを使用）
    history = run_async(get_defeat_history())
    if boss_key:
        history = [h for h in history if h.get('boss_key') == boss_key]
    return jsonify(history[:limit])


@app.route('/api/defeat-history/detail/<int:defeat_history_id>')
def api_defeat_detail(defeat_history_id):
    """API: 討伐履歴詳細（参加者情報含む）"""
    history_list = run_async(get_defeat_history())
    defeat_info = next((h for h in history_list if h['id'] == defeat_history_id), None)
    participants = run_async(get_defeat_participants(defeat_history_id))
    return jsonify({
        'history': defeat_info,
        'participants': participants
    })


@app.route('/api/user-stats/<int:guild_id>/<int:user_id>')
def api_user_stats(guild_id, user_id):
    """API: ユーザー統計（仕様書準拠）"""
    stats = run_async(get_user_stats(user_id))
    return jsonify(stats)


@app.route('/api/ranking/<int:guild_id>')
def api_ranking(guild_id):
    """API: ランキング（仕様書準拠）"""
    from flask import request
    boss_key = request.args.get('boss_key')
    limit = int(request.args.get('limit', 100))
    # 簡易実装（現在の実装を使用）
    rankings = run_async(get_all_time_rankings())
    return jsonify(rankings[:limit])


@app.route('/api/attack-holder/<int:guild_id>')
def api_attack_holder(guild_id):
    """API: アタックホルダー（単発最大ダメージランキング）"""
    from flask import request
    boss_key = request.args.get('boss_key')
    limit = int(request.args.get('limit', 100))
    holders = run_async(get_attack_holder(boss_key=boss_key, limit=limit))
    return jsonify(holders)


@app.route('/api/fastest-clears/<int:guild_id>')
def api_fastest_clears(guild_id):
    """API: 最速討伐記録（仕様書準拠）"""
    clears = run_async(get_fastest_clears(limit=20))
    return jsonify(clears)


@app.route('/api/defeat/<int:defeat_id>/participants')
def api_defeat_participants(defeat_id):
    """API: 討伐参加者（後方互換性のため残す）"""
    participants = run_async(get_defeat_participants(defeat_id))
    return jsonify(participants)


@app.route('/api/rankings')
def api_rankings():
    """API: 全期間ランキング（後方互換性のため残す）"""
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
