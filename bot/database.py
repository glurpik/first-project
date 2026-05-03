import aiosqlite
import asyncio
from datetime import datetime

DB_PATH = "traffic_bot.db"


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                has_access INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS channels (
                channel_id INTEGER PRIMARY KEY,
                title TEXT,
                username TEXT,
                added_by INTEGER,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS invite_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                invite_link TEXT UNIQUE NOT NULL,
                slot_number INTEGER,
                label TEXT,
                join_count INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (channel_id) REFERENCES channels(channel_id)
            );

            CREATE TABLE IF NOT EXISTS joins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invite_link_id INTEGER NOT NULL,
                joined_user_id INTEGER NOT NULL,
                joined_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (invite_link_id) REFERENCES invite_links(id)
            );

            CREATE TABLE IF NOT EXISTS leaderboard_cache (
                user_id INTEGER PRIMARY KEY,
                total_joins INTEGER DEFAULT 0,
                updated_at TEXT DEFAULT (datetime('now'))
            );
        """)
        await db.commit()


# --- Users ---

async def get_user(user_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def upsert_user(user_id: int, username: str, full_name: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO users (user_id, username, full_name)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET username=excluded.username, full_name=excluded.full_name
        """, (user_id, username, full_name))
        await db.commit()


async def grant_access(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET has_access = 1 WHERE user_id = ?", (user_id,))
        await db.commit()


async def revoke_access(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET has_access = 0 WHERE user_id = ?", (user_id,))
        await db.commit()


async def get_all_users_with_access() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE has_access = 1") as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


# --- Channels ---

async def add_channel(channel_id: int, title: str, username: str, added_by: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT OR REPLACE INTO channels (channel_id, title, username, added_by)
            VALUES (?, ?, ?, ?)
        """, (channel_id, title, username, added_by))
        await db.commit()


async def remove_channel(channel_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM channels WHERE channel_id = ?", (channel_id,))
        await db.commit()


async def get_channels() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM channels") as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def get_channel(channel_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM channels WHERE channel_id = ?", (channel_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


# --- Invite Links ---

async def save_invite_link(user_id: int, channel_id: int, invite_link: str, slot_number: int, label: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT OR IGNORE INTO invite_links (user_id, channel_id, invite_link, slot_number, label)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, channel_id, invite_link, slot_number, label))
        await db.commit()


async def get_user_links(user_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT il.*, c.title as channel_title, c.username as channel_username
            FROM invite_links il
            JOIN channels c ON il.channel_id = c.channel_id
            WHERE il.user_id = ?
            ORDER BY il.slot_number ASC
        """, (user_id,)) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def get_link_by_url(invite_link: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM invite_links WHERE invite_link = ?", (invite_link,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def record_join(invite_link_id: int, joined_user_id: int) -> bool:
    """Returns True if this is a new join (not duplicate)."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM joins WHERE invite_link_id = ? AND joined_user_id = ?",
            (invite_link_id, joined_user_id)
        ) as cur:
            if await cur.fetchone():
                return False
        await db.execute(
            "INSERT INTO joins (invite_link_id, joined_user_id) VALUES (?, ?)",
            (invite_link_id, joined_user_id)
        )
        await db.execute(
            "UPDATE invite_links SET join_count = join_count + 1 WHERE id = ?",
            (invite_link_id,)
        )
        await db.commit()
        return True


async def get_total_joins_for_user(user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COALESCE(SUM(join_count), 0) FROM invite_links WHERE user_id = ?",
            (user_id,)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0


async def count_user_slots(user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM invite_links WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0


# --- Leaderboard ---

async def refresh_leaderboard():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM leaderboard_cache")
        await db.execute("""
            INSERT INTO leaderboard_cache (user_id, total_joins, updated_at)
            SELECT user_id, COALESCE(SUM(join_count), 0), datetime('now')
            FROM invite_links
            GROUP BY user_id
        """)
        await db.commit()


async def get_leaderboard() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT lc.user_id, lc.total_joins, u.username, u.full_name
            FROM leaderboard_cache lc
            JOIN users u ON lc.user_id = u.user_id
            ORDER BY lc.total_joins DESC
            LIMIT 10
        """) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def get_user_rank(user_id: int) -> tuple[int, int]:
    """Returns (rank, total_joins). Rank is 0 if not in leaderboard."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT COUNT(*) + 1 as rank
            FROM leaderboard_cache
            WHERE total_joins > (
                SELECT COALESCE(total_joins, 0) FROM leaderboard_cache WHERE user_id = ?
            )
        """, (user_id,)) as cur:
            rank_row = await cur.fetchone()
        async with db.execute(
            "SELECT COALESCE(total_joins, 0) FROM leaderboard_cache WHERE user_id = ?", (user_id,)
        ) as cur:
            joins_row = await cur.fetchone()
        rank = rank_row[0] if rank_row else 1
        joins = joins_row[0] if joins_row else 0
        return rank, joins


async def get_next_slot_number() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COALESCE(MAX(slot_number), 0) + 1 FROM invite_links") as cur:
            row = await cur.fetchone()
            return row[0] if row else 1
