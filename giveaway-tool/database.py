import aiosqlite
import json
from datetime import datetime

DB_FILE = "research.db"


async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS giveaways (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel TEXT,
                message_id INTEGER,
                text TEXT,
                detected_at TEXT,
                channels_to_join TEXT,
                UNIQUE(channel, message_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS participations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account TEXT,
                giveaway_id INTEGER,
                participated_at TEXT,
                actions_taken TEXT,
                won INTEGER DEFAULT 0,
                FOREIGN KEY(giveaway_id) REFERENCES giveaways(id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                giveaway_id INTEGER,
                winner_announced TEXT,
                our_account_won INTEGER DEFAULT 0,
                winner_text TEXT,
                checked_at TEXT
            )
        """)
        await db.commit()


async def save_giveaway(channel: str, message_id: int, text: str, channels_to_join: list) -> int:
    async with aiosqlite.connect(DB_FILE) as db:
        try:
            cursor = await db.execute(
                "INSERT INTO giveaways (channel, message_id, text, detected_at, channels_to_join) VALUES (?,?,?,?,?)",
                (channel, message_id, text, datetime.now().isoformat(), json.dumps(channels_to_join, ensure_ascii=False))
            )
            await db.commit()
            return cursor.lastrowid
        except Exception:
            cursor = await db.execute(
                "SELECT id FROM giveaways WHERE channel=? AND message_id=?",
                (channel, message_id)
            )
            row = await cursor.fetchone()
            return row[0] if row else -1


async def save_participation(account: str, giveaway_id: int, actions: list):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "INSERT OR IGNORE INTO participations (account, giveaway_id, participated_at, actions_taken) VALUES (?,?,?,?)",
            (account, giveaway_id, datetime.now().isoformat(), json.dumps(actions, ensure_ascii=False))
        )
        await db.commit()


async def mark_won(account: str, giveaway_id: int):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "UPDATE participations SET won=1 WHERE account=? AND giveaway_id=?",
            (account, giveaway_id)
        )
        await db.commit()


async def save_result(giveaway_id: int, winner_text: str, we_won: bool):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "INSERT INTO results (giveaway_id, winner_announced, our_account_won, winner_text, checked_at) VALUES (?,?,?,?,?)",
            (giveaway_id, datetime.now().isoformat(), int(we_won), winner_text, datetime.now().isoformat())
        )
        await db.commit()


async def get_stats() -> dict:
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM giveaways")
        total_found = (await cursor.fetchone())[0]

        cursor = await db.execute("SELECT COUNT(*) FROM participations")
        total_participations = (await cursor.fetchone())[0]

        cursor = await db.execute("SELECT COUNT(*) FROM participations WHERE won=1")
        total_wins = (await cursor.fetchone())[0]

        cursor = await db.execute("SELECT COUNT(DISTINCT account) FROM participations")
        accounts_used = (await cursor.fetchone())[0]

    return {
        "total_giveaways_found": total_found,
        "total_participations": total_participations,
        "total_wins": total_wins,
        "accounts_used": accounts_used,
        "win_rate": f"{(total_wins / total_participations * 100):.2f}%" if total_participations > 0 else "0%"
    }


async def get_all_participations():
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT p.account, p.participated_at, p.won, p.actions_taken,
                   g.channel, g.text
            FROM participations p
            JOIN giveaways g ON p.giveaway_id = g.id
            ORDER BY p.participated_at DESC
        """)
        return await cursor.fetchall()
