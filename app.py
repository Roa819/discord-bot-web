"""
Discord Bot Web Viewer - 完全読み取り専用
既存のDiscordボットとは完全に独立したWebアプリケーション
"""

import os
import asyncio
from datetime import datetime
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

# データベース接続プール (読み取り専用)
db_pool = None


async def init_db_pool():
    """データベース接続プールを初期化 (読み取り専用)"""
    global db_pool
    if db_pool is None:
        db_pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=1,
            max_size=3,
            command_timeout=10
        )
    return db_pool


async def get_active_bosses():
    """現在アクティブなボス一覧を取得"""
    pool = await init_db_pool()
    async with pool.acquire() as conn:
        bosses = await conn.fetch("""
            SELECT 
                boss_key,
                boss_name,
                current_hp,
                max_hp,
                defeated,
                spawned_at,
                defeated_at
            FROM raid_boss_state
            WHERE guild_id = $1
            ORDER BY spawned_at DESC
        """, GUILD_ID)
        return [dict(b) for b in bosses]


async def get_boss_participants(boss_key: str):
    """特定ボスの参加者とダメージランキングを取得"""
    pool = await init_db_pool()
    async with pool.acquire() as conn:
        participants = await conn.fetch("""
            SELECT 
                user_id,
                action_count,
                total_damage,
                first_attack_at,
                last_attack_at
            FROM raid_participants
            WHERE guild_id = $1 AND boss_key = $2
            ORDER BY total_damage DESC
        """, GUILD_ID, boss_key)
        return [dict(p) for p in participants]


async def get_all_time_rankings():
    """全期間の累計ダメージランキング"""
    pool = await init_db_pool()
    async with pool.acquire() as conn:
        rankings = await conn.fetch("""
            SELECT 
                user_id,
                SUM(total_damage) as total_damage,
                SUM(action_count) as total_actions,
                COUNT(DISTINCT boss_key) as bosses_participated
            FROM raid_participants
            WHERE guild_id = $1
            GROUP BY user_id
            ORDER BY total_damage DESC
            LIMIT 50
        """, GUILD_ID)
        return [dict(r) for r in rankings]


async def get_user_stats(user_id: int):
    """特定ユーザーの統計情報"""
    pool = await init_db_pool()
    async with pool.acquire() as conn:
        stats = await conn.fetchrow("""
            SELECT 
                COUNT(DISTINCT boss_key) as bosses_participated,
                SUM(total_damage) as total_damage,
                SUM(action_count) as total_actions,
                MAX(total_damage) as max_single_boss_damage
            FROM raid_participants
            WHERE guild_id = $1 AND user_id = $2
        """, GUILD_ID, user_id)
        return dict(stats) if stats else None


# ルート定義

@app.route('/')
def index():
    """トップページ：現在のボス状況"""
    bosses = asyncio.run(get_active_bosses())
    return render_template('index.html', bosses=bosses)


@app.route('/boss/<boss_key>')
def boss_detail(boss_key):
    """ボス詳細：参加者とダメージランキング"""
    participants = asyncio.run(get_boss_participants(boss_key))
    bosses = asyncio.run(get_active_bosses())
    
    # 該当ボスの情報を取得
    boss_info = next((b for b in bosses if b['boss_key'] == boss_key), None)
    
    return render_template(
        'boss_detail.html',
        boss=boss_info,
        boss_key=boss_key,
        participants=participants
    )


@app.route('/rankings')
def rankings():
    """全期間ランキング"""
    rankings = asyncio.run(get_all_time_rankings())
    return render_template('rankings.html', rankings=rankings)


@app.route('/user/<int:user_id>')
def user_detail(user_id):
    """ユーザー詳細統計"""
    stats = asyncio.run(get_user_stats(user_id))
    return render_template('user_detail.html', user_id=user_id, stats=stats)


# API エンドポイント (JSON)

@app.route('/api/bosses')
def api_bosses():
    """API: ボス一覧"""
    bosses = asyncio.run(get_active_bosses())
    return jsonify(bosses)


@app.route('/api/boss/<boss_key>/participants')
def api_boss_participants(boss_key):
    """API: ボス参加者"""
    participants = asyncio.run(get_boss_participants(boss_key))
    return jsonify(participants)


@app.route('/api/rankings')
def api_rankings():
    """API: 全期間ランキング"""
    rankings = asyncio.run(get_all_time_rankings())
    return jsonify(rankings)


@app.route('/health')
def health():
    """ヘルスチェック (Railwayモニタリング用)"""
    return jsonify({"status": "ok", "timestamp": datetime.utcnow().isoformat()})


if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
