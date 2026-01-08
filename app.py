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


async def get_defeat_history(guild_id=None, boss_key=None, limit=50):
    """討伐履歴一覧を取得（仕様準拠）"""
    guild = guild_id or GUILD_ID
    limit = max(1, min(int(limit or 50), 500))

    # DBが無い場合のモックデータ
    if not DATABASE_URL:
        from datetime import datetime, timedelta
        now = datetime.utcnow()
        data = [
            {
                'id': 1,
                'guild_id': guild,
                'boss_key': 'Fatal_Lake',
                'boss_name': 'フェル・レイク',
                'boss_max_hp': 1500,
                'defeated_at': now - timedelta(hours=2),
                'total_participants': 3,
                'total_damage': 1650
            },
            {
                'id': 2,
                'guild_id': guild,
                'boss_key': 'Timed_Dragon',
                'boss_name': '時間の番竜',
                'boss_max_hp': 3000,
                'defeated_at': now - timedelta(days=1, hours=5),
                'total_participants': 5,
                'total_damage': 3200
            },
            {
                'id': 3,
                'guild_id': guild,
                'boss_key': 'Fatal_Lake',
                'boss_name': 'フェル・レイク',
                'boss_max_hp': 1500,
                'defeated_at': now - timedelta(days=2, hours=3),
                'total_participants': 4,
                'total_damage': 1550
            }
        ]
        if boss_key:
            data = [d for d in data if d['boss_key'] == boss_key]
        return data[:limit]

    pool = await init_db_pool()
    async with pool.acquire() as conn:
        if boss_key:
            history = await conn.fetch(
                """
                SELECT 
                    id,
                    guild_id,
                    boss_key,
                    boss_name,
                    boss_max_hp,
                    defeated_at,
                    total_participants,
                    total_damage
                FROM raid_defeat_history
                WHERE guild_id = $1 AND boss_key = $2
                ORDER BY defeated_at DESC
                LIMIT $3
                """,
                guild,
                boss_key,
                limit,
            )
        else:
            history = await conn.fetch(
                """
                SELECT 
                    id,
                    guild_id,
                    boss_key,
                    boss_name,
                    boss_max_hp,
                    defeated_at,
                    total_participants,
                    total_damage
                FROM raid_defeat_history
                WHERE guild_id = $1
                ORDER BY defeated_at DESC
                LIMIT $2
                """,
                guild,
                limit,
            )
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


async def get_defeat_history_detail(defeat_history_id: int):
    """討伐履歴1件を取得（参加者以外のメタ情報）"""
    if not DATABASE_URL:
        history = await get_defeat_history(limit=200)
        return next((h for h in history if h.get('id') == defeat_history_id), None)

    pool = await init_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, guild_id, boss_key, boss_name, boss_max_hp,
                   defeated_at, total_participants, total_damage
            FROM raid_defeat_history
            WHERE id = $1
            """,
            defeat_history_id,
        )
        return dict(row) if row else None


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


async def get_attack_history(
    guild_id: int,
    boss_key: str = None,
    boss_level: int = None,
    since: datetime = None,
    limit: int = 50,
    order: str = 'desc',
    defeat_history_id: int = None,
):
    """攻撃履歴取得（進行中/討伐済み両対応）"""
    limit = max(1, min(int(limit or 50), 500))
    order_sql = 'ASC' if str(order).lower() == 'asc' else 'DESC'

    if not DATABASE_URL:
        from datetime import datetime, timedelta
        now = datetime.utcnow()
        mock = [
            {
                'id': 123,
                'guild_id': guild_id,
                'boss_key': boss_key or 'Fatal_Lake',
                'boss_level': boss_level or 3,
                'user_id': 555,
                'user_name': 'Player1',
                'damage': 18750,
                'attacked_at': now - timedelta(minutes=15),
                'defeat_history_id': defeat_history_id,
                'turn_log': [
                    {"actor": "player", "damage": 1250, "is_crit": False, "is_miss": False, "followup": False, "followup_damage": 0},
                    {"actor": "boss", "damage": 800, "is_crit": False, "is_miss": False, "followup": False, "followup_damage": 0},
                    {"actor": "player", "damage": 1875, "is_crit": True, "is_miss": False, "followup": True, "followup_damage": 1312}
                ]
            }
        ]
        return mock[:limit]

    pool = await init_db_pool()
    async with pool.acquire() as conn:
        conditions = ["guild_id = $1"]
        params = [guild_id]
        param_idx = 2

        if boss_key:
            conditions.append(f"boss_key = ${param_idx}")
            params.append(boss_key)
            param_idx += 1
        if boss_level is not None:
            conditions.append(f"boss_level = ${param_idx}")
            params.append(boss_level)
            param_idx += 1
        if since is not None:
            conditions.append(f"attacked_at >= ${param_idx}")
            params.append(since)
            param_idx += 1
        if defeat_history_id is None:
            conditions.append("defeat_history_id IS NULL")
        else:
            conditions.append(f"defeat_history_id = ${param_idx}")
            params.append(defeat_history_id)
            param_idx += 1

        sql = f"""
            SELECT 
                id,
                guild_id,
                boss_key,
                boss_level,
                user_id,
                user_name,
                damage,
                attacked_at,
                defeat_history_id,
                turn_log
            FROM raid_attack_history
            WHERE {' AND '.join(conditions)}
            ORDER BY attacked_at {order_sql}
            LIMIT ${param_idx}
        """
        params.append(limit)

        attacks = await conn.fetch(sql, *params)
        result = []
        for attack in attacks:
            attack_dict = dict(attack)
            turn_log = attack_dict.get('turn_log')
            if isinstance(turn_log, str):
                try:
                    turn_log = json.loads(turn_log)
                    if isinstance(turn_log, str):
                        turn_log = json.loads(turn_log)
                except (json.JSONDecodeError, TypeError):
                    turn_log = None
            attack_dict['turn_log'] = turn_log
            result.append(attack_dict)
        return result


async def get_defeat_attack_history(defeat_history_id: int, limit: int = 500, order: str = 'asc'):
    """討伐済みボスの攻撃履歴を取得（仕様準拠）"""
    return await get_attack_history(
        guild_id=GUILD_ID,
        boss_key=None,
        boss_level=None,
        since=None,
        limit=limit,
        order=order,
        defeat_history_id=defeat_history_id,
    )


async def get_all_time_rankings(guild_id=None, boss_key=None, limit=100):
    """全期間の累計ダメージランキング（仕様準拠）"""
    guild = guild_id or GUILD_ID
    limit = max(1, min(int(limit or 100), 500))

    if not DATABASE_URL:
        mock = [
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
            }
        ]
        return mock[:limit]

    pool = await init_db_pool()
    async with pool.acquire() as conn:
        if boss_key:
            rankings = await conn.fetch(
                """
                SELECT 
                    dp.user_id,
                    dp.user_name,
                    COUNT(*) as defeat_count,
                    SUM(dp.total_damage) as total_damage,
                    SUM(dp.action_count) as total_actions,
                    MAX(dh.defeated_at) as last_defeat_at
                FROM raid_defeat_participants dp
                JOIN raid_defeat_history dh ON dp.defeat_history_id = dh.id
                WHERE dh.guild_id = $1 AND dh.boss_key = $2
                GROUP BY dp.user_id, dp.user_name
                ORDER BY total_damage DESC
                LIMIT $3
                """,
                guild,
                boss_key,
                limit,
            )
        else:
            rankings = await conn.fetch(
                """
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
                LIMIT $2
                """,
                guild,
                limit,
            )
        return [dict(r) for r in rankings]


async def get_fastest_clears(guild_id=None, limit=20):
    """最速討伐記録"""
    guild = guild_id or GUILD_ID
    limit = max(1, min(int(limit or 20), 50))

    if not DATABASE_URL:
        from datetime import datetime, timedelta
        return [
            {
                'id': 5,
                'guild_id': guild,
                'boss_key': 'Fatal_Lake',
                'boss_name': '運命の湖',
                'boss_max_hp': 100000,
                'defeated_at': datetime.utcnow(),
                'total_participants': 5,
                'total_damage': 105000,
                'clear_time': timedelta(minutes=15, seconds=30)
            }
        ]

    pool = await init_db_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
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
            """,
            guild,
            limit,
        )
        return [dict(r) for r in rows]

async def get_user_stats(guild_id, user_id):
    """特定ユーザーの統計（仕様準拠）"""
    guild = guild_id or GUILD_ID

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
        stats = await conn.fetchrow(
            """
            SELECT 
                COUNT(*) as total_defeats,
                SUM(total_damage) as total_damage,
                SUM(action_count) as total_actions
            FROM raid_defeat_participants dp
            JOIN raid_defeat_history dh ON dp.defeat_history_id = dh.id
            WHERE dh.guild_id = $1 AND dp.user_id = $2
            """,
            guild,
            user_id,
        )
        
        boss_stats = await conn.fetch(
            """
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
            """,
            guild,
            user_id,
        )
        
        result = dict(stats) if stats else {}
        result['bosses_defeated'] = [dict(b) for b in boss_stats]
        return result


async def get_attack_holder(guild_id=None, boss_key=None, limit=100):
    """アタックホルダー（1回の戦闘=攻撃記録での最大ダメージ）"""
    guild = guild_id or GUILD_ID
    limit = max(1, min(int(limit or 100), 500))

    if DATABASE_URL is None:
        return [
            {
                'user_id': 345678901234567890,
                'user_name': 'Player3',
                'max_single_damage': 850,
                'boss_name': 'フェル・レイク',
                'boss_key': 'Fatal_Lake',
                'defeated_at': datetime.utcnow(),
                'defeat_history_id': 3,
                'attacked_at': datetime.utcnow(),
            },
            {
                'user_id': 123456789012345678,
                'user_name': 'Player1',
                'max_single_damage': 780,
                'boss_name': '時間の番竜',
                'boss_key': 'Timed_Dragon',
                'defeated_at': datetime.utcnow(),
                'defeat_history_id': 5,
                'attacked_at': datetime.utcnow(),
            }
        ]

    pool = await init_db_pool()
    async with pool.acquire() as conn:
        # raid_attack_history から単一戦闘の最大ダメージを算出
        if boss_key:
            rows = await conn.fetch(
                """
                WITH ranked AS (
                    SELECT 
                        rah.user_id,
                        rah.user_name,
                        rah.damage AS max_single_damage,
                        COALESCE(dh.boss_name, rah.boss_key) AS boss_name,
                        COALESCE(dh.boss_key, rah.boss_key) AS boss_key,
                        dh.defeated_at,
                        rah.attacked_at,
                        rah.defeat_history_id,
                        ROW_NUMBER() OVER (
                            PARTITION BY rah.user_id
                            ORDER BY rah.damage DESC, rah.attacked_at DESC, rah.id DESC
                        ) AS rn
                    FROM raid_attack_history rah
                    LEFT JOIN raid_defeat_history dh ON rah.defeat_history_id = dh.id
                    WHERE rah.guild_id = $1 AND COALESCE(dh.boss_key, rah.boss_key) = $2
                )
                SELECT * FROM ranked WHERE rn = 1
                ORDER BY max_single_damage DESC
                LIMIT $3
                """,
                guild,
                boss_key,
                limit,
            )
        else:
            rows = await conn.fetch(
                """
                WITH ranked AS (
                    SELECT 
                        rah.user_id,
                        rah.user_name,
                        rah.damage AS max_single_damage,
                        COALESCE(dh.boss_name, rah.boss_key) AS boss_name,
                        COALESCE(dh.boss_key, rah.boss_key) AS boss_key,
                        dh.defeated_at,
                        rah.attacked_at,
                        rah.defeat_history_id,
                        ROW_NUMBER() OVER (
                            PARTITION BY rah.user_id
                            ORDER BY rah.damage DESC, rah.attacked_at DESC, rah.id DESC
                        ) AS rn
                    FROM raid_attack_history rah
                    LEFT JOIN raid_defeat_history dh ON rah.defeat_history_id = dh.id
                    WHERE rah.guild_id = $1
                )
                SELECT * FROM ranked WHERE rn = 1
                ORDER BY max_single_damage DESC
                LIMIT $2
                """,
                guild,
                limit,
            )
        return [dict(r) for r in rows]


async def get_attack_holder_by_boss(guild_id=None, boss_key=None, boss_level=None, per_boss_limit=5):
    """ボス別アタックホルダー（各ボス上位N件、1回の戦闘ダメージ）"""
    guild = guild_id or GUILD_ID
    per_boss_limit = max(1, min(per_boss_limit or 5, 10))

    if DATABASE_URL is None:
        mock = [
            {
                'boss_key': 'Fatal_Lake',
                'boss_name': 'フェル・レイク',
                'boss_level': 3,
                'user_id': 111,
                'user_name': 'Player1',
                'max_single_damage': 920,
                'last_defeated_at': datetime.utcnow(),
                'rn': 1
            },
            {
                'boss_key': 'Timed_Dragon',
                'boss_name': '時間の番竜',
                'boss_level': 2,
                'user_id': 222,
                'user_name': 'Player2',
                'max_single_damage': 805,
                'last_defeated_at': datetime.utcnow(),
                'rn': 1
            }
        ]
        if boss_key:
            return [m for m in mock if m['boss_key'] == boss_key]
        return mock

    pool = await init_db_pool()
    async with pool.acquire() as conn:
        query_with_level = """
            WITH agg AS (
                SELECT 
                    COALESCE(dh.boss_key, rah.boss_key) AS boss_key,
                    COALESCE(dh.boss_name, rah.boss_key) AS boss_name,
                    dh.boss_level,
                    rah.user_id,
                    rah.user_name,
                    MAX(rah.damage) AS max_single_damage,
                    MAX(COALESCE(dh.defeated_at, rah.attacked_at)) AS last_defeated_at
                FROM raid_attack_history rah
                LEFT JOIN raid_defeat_history dh ON rah.defeat_history_id = dh.id
                WHERE rah.guild_id = $1
                  AND ($2::text IS NULL OR COALESCE(dh.boss_key, rah.boss_key) = $2)
                  AND ($3::int IS NULL OR dh.boss_level = $3)
                GROUP BY COALESCE(dh.boss_key, rah.boss_key), COALESCE(dh.boss_name, rah.boss_key), dh.boss_level, rah.user_id, rah.user_name
            ), ranked AS (
                SELECT 
                    agg.*,
                    ROW_NUMBER() OVER (PARTITION BY agg.boss_key, agg.boss_level ORDER BY agg.max_single_damage DESC, agg.user_id) AS rn
                FROM agg
            )
            SELECT *
            FROM ranked
            WHERE rn <= $4
            ORDER BY boss_key, boss_level, rn
        """

        query_without_level = """
            WITH agg AS (
                SELECT 
                    COALESCE(dh.boss_key, rah.boss_key) AS boss_key,
                    COALESCE(dh.boss_name, rah.boss_key) AS boss_name,
                    NULL::int AS boss_level,
                    rah.user_id,
                    rah.user_name,
                    MAX(rah.damage) AS max_single_damage,
                    MAX(COALESCE(dh.defeated_at, rah.attacked_at)) AS last_defeated_at
                FROM raid_attack_history rah
                LEFT JOIN raid_defeat_history dh ON rah.defeat_history_id = dh.id
                WHERE rah.guild_id = $1
                  AND ($2::text IS NULL OR COALESCE(dh.boss_key, rah.boss_key) = $2)
                GROUP BY COALESCE(dh.boss_key, rah.boss_key), COALESCE(dh.boss_name, rah.boss_key), rah.user_id, rah.user_name
            ), ranked AS (
                SELECT 
                    agg.*,
                    ROW_NUMBER() OVER (PARTITION BY agg.boss_key ORDER BY agg.max_single_damage DESC, agg.user_id) AS rn
                FROM agg
            )
            SELECT *
            FROM ranked
            WHERE rn <= $3
            ORDER BY boss_key, rn
        """

        try:
            rows = await conn.fetch(
                query_with_level,
                guild,
                boss_key,
                boss_level,
                per_boss_limit
            )
        except Exception:
            rows = await conn.fetch(
                query_without_level,
                guild,
                boss_key,
                per_boss_limit
            )

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
    defeat_info = run_async(get_defeat_history_detail(defeat_id))
    
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
    rankings = run_async(get_all_time_rankings(guild_id=GUILD_ID, limit=50))
    return render_template('rankings.html', rankings=rankings)


@app.route('/user/<int:user_id>')
def user_detail(user_id):
    """ユーザー詳細統計"""
    stats = run_async(get_user_stats(GUILD_ID, user_id))
    return render_template('user_detail.html', stats=stats, user_id=user_id)


@app.route('/attack-holder')
def attack_holder_page():
    """アタックホルダー（1回の戦闘での最大ダメージランキング）"""
    from flask import request

    boss_key = request.args.get('boss_key') or None
    boss_level_raw = request.args.get('boss_level')
    boss_level = int(boss_level_raw) if boss_level_raw else None
    per_boss_limit = int(request.args.get('per_boss_limit', 5) or 5)
    # 全ボス合算（または特定ボス）のランキング
    holders = run_async(get_attack_holder(guild_id=GUILD_ID, boss_key=boss_key, limit=50))
    # ボス別ランキング（各ボス上位N件）
    holders_by_boss = run_async(
        get_attack_holder_by_boss(
            guild_id=GUILD_ID,
            boss_key=boss_key,
            boss_level=boss_level,
            per_boss_limit=per_boss_limit
        )
    )
    # セレクトボックス用のボス一覧（討伐履歴から収集）
    history_list = run_async(get_defeat_history(guild_id=GUILD_ID, limit=200))
    boss_choices = []
    seen_keys = set()
    for h in history_list:
        key = h.get('boss_key')
        name = h.get('boss_name')
        if key and key not in seen_keys:
            boss_choices.append({'boss_key': key, 'boss_name': name})
            seen_keys.add(key)

    return render_template(
        'attack_holder.html',
        holders=holders,
        holders_by_boss=holders_by_boss,
        boss_choices=boss_choices,
        selected_boss_key=boss_key,
        selected_boss_level=boss_level,
        per_boss_limit=per_boss_limit
    )


# ===== API エンドポイント =====

@app.route('/api/defeat-history/<int:guild_id>')
def api_defeat_history(guild_id):
    """API: 討伐履歴一覧（仕様書準拠）"""
    from flask import request
    boss_key = request.args.get('boss_key')
    limit = int(request.args.get('limit', 50))
    history = run_async(get_defeat_history(guild_id=guild_id, boss_key=boss_key, limit=limit))
    return jsonify(history)


@app.route('/api/defeat-history/detail/<int:defeat_history_id>')
def api_defeat_detail(defeat_history_id):
    """API: 討伐履歴詳細（参加者情報含む）"""
    defeat_info = run_async(get_defeat_history_detail(defeat_history_id))
    participants = run_async(get_defeat_participants(defeat_history_id))
    return jsonify({
        'history': defeat_info,
        'participants': participants
    })


@app.route('/api/user-stats/<int:guild_id>/<int:user_id>')
def api_user_stats(guild_id, user_id):
    """API: ユーザー統計（仕様書準拠）"""
    stats = run_async(get_user_stats(guild_id, user_id))
    return jsonify(stats)


@app.route('/api/ranking/<int:guild_id>')
def api_ranking(guild_id):
    """API: ランキング（仕様書準拠）"""
    from flask import request
    boss_key = request.args.get('boss_key')
    limit = int(request.args.get('limit', 100))
    rankings = run_async(get_all_time_rankings(guild_id=guild_id, boss_key=boss_key, limit=limit))
    return jsonify(rankings)


@app.route('/api/attack-holder/<int:guild_id>')
def api_attack_holder(guild_id):
    """API: アタックホルダー（1回の戦闘での最大ダメージランキング）"""
    from flask import request
    boss_key = request.args.get('boss_key')
    limit = int(request.args.get('limit', 100))
    holders = run_async(get_attack_holder(guild_id=guild_id, boss_key=boss_key, limit=limit))
    return jsonify(holders)


@app.route('/api/attack-holder/by-boss/<int:guild_id>')
def api_attack_holder_by_boss(guild_id):
    """API: ボス別アタックホルダー（各ボス上位N件）"""
    from flask import request
    boss_key = request.args.get('boss_key')
    boss_level_raw = request.args.get('boss_level')
    boss_level = int(boss_level_raw) if boss_level_raw else None
    per_boss_limit = int(request.args.get('per_boss_limit', 5) or 5)
    holders = run_async(
        get_attack_holder_by_boss(
            guild_id=guild_id,
            boss_key=boss_key,
            boss_level=boss_level,
            per_boss_limit=per_boss_limit
        )
    )
    return jsonify(holders)


@app.route('/api/attack-history/<int:guild_id>')
def api_attack_history(guild_id):
    """API: 進行中ボスの戦闘ログ取得"""
    from flask import request
    boss_key = request.args.get('boss_key')
    boss_level_raw = request.args.get('boss_level')
    boss_level = int(boss_level_raw) if boss_level_raw else None
    since_raw = request.args.get('since')
    since = None
    if since_raw:
        try:
            since = datetime.fromisoformat(since_raw)
        except Exception:
            since = None
    limit = min(int(request.args.get('limit', 50) or 50), 200)
    order = request.args.get('order', 'desc')

    attacks = run_async(
        get_attack_history(
            guild_id=guild_id,
            boss_key=boss_key,
            boss_level=boss_level,
            since=since,
            limit=limit,
            order=order,
            defeat_history_id=None,
        )
    )
    return jsonify(attacks)


@app.route('/api/attack-history/by-defeat/<int:defeat_history_id>')
def api_attack_history_by_defeat(defeat_history_id):
    """API: 討伐済みボスの戦闘ログ取得"""
    from flask import request
    boss_key = request.args.get('boss_key')
    boss_level_raw = request.args.get('boss_level')
    boss_level = int(boss_level_raw) if boss_level_raw else None
    since_raw = request.args.get('since')
    since = None
    if since_raw:
        try:
            since = datetime.fromisoformat(since_raw)
        except Exception:
            since = None
    limit = min(int(request.args.get('limit', 200) or 200), 500)
    order = request.args.get('order', 'desc')

    attacks = run_async(
        get_attack_history(
            guild_id=GUILD_ID,
            boss_key=boss_key,
            boss_level=boss_level,
            since=since,
            limit=limit,
            order=order,
            defeat_history_id=defeat_history_id,
        )
    )
    return jsonify(attacks)


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


@app.route('/api/fastest-clears/<int:guild_id>')
def api_fastest_clears(guild_id):
    """API: 最速討伐記録"""
    from flask import request
    limit = int(request.args.get('limit', 20) or 20)
    rows = run_async(get_fastest_clears(guild_id=guild_id, limit=limit))
    return jsonify(rows)


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
