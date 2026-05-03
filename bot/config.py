import os
import time
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
ADMIN_IDS: set[int] = {int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()}

MAX_SLOTS_PER_USER: int = 60
LEADERBOARD_UPDATE_INTERVAL: int = 300  # 5 minutes in seconds

_leaderboard_last_updated: float = time.time()


def leaderboard_last_updated() -> float:
    return _leaderboard_last_updated


def set_leaderboard_updated():
    global _leaderboard_last_updated
    _leaderboard_last_updated = time.time()


def get_seconds_to_update() -> int:
    elapsed = int(time.time() - _leaderboard_last_updated)
    remaining = max(0, LEADERBOARD_UPDATE_INTERVAL - elapsed)
    return remaining
