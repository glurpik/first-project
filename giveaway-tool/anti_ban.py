"""
Защита от бана: задержки, лимиты, прокси.
"""

import asyncio
import random
import logging
from datetime import datetime, timedelta
from collections import defaultdict

log = logging.getLogger(__name__)

# Лимиты действий на аккаунт
LIMITS = {
    "joins_per_hour": 15,       # Макс вступлений в каналы за час
    "joins_per_day": 50,        # Макс вступлений за день
    "messages_per_hour": 10,    # Макс сообщений/комментариев за час
    "search_per_hour": 5,       # Макс поисков за час
}

# История действий: account -> [(action, timestamp), ...]
_history: dict = defaultdict(list)


def _count_recent(account: str, action: str, window_minutes: int) -> int:
    cutoff = datetime.now() - timedelta(minutes=window_minutes)
    return sum(
        1 for (a, t) in _history[account]
        if a == action and t > cutoff
    )


def _record(account: str, action: str):
    _history[account].append((action, datetime.now()))
    # Чистим старые записи (старше 25 часов)
    cutoff = datetime.now() - timedelta(hours=25)
    _history[account] = [(a, t) for (a, t) in _history[account] if t > cutoff]


def can_join(account: str) -> bool:
    per_hour = _count_recent(account, "join", 60)
    per_day = _count_recent(account, "join", 1440)
    if per_hour >= LIMITS["joins_per_hour"]:
        log.warning(f"[{account}] Лимит вступлений за час ({LIMITS['joins_per_hour']}) исчерпан")
        return False
    if per_day >= LIMITS["joins_per_day"]:
        log.warning(f"[{account}] Лимит вступлений за день ({LIMITS['joins_per_day']}) исчерпан")
        return False
    return True


def can_comment(account: str) -> bool:
    per_hour = _count_recent(account, "comment", 60)
    if per_hour >= LIMITS["messages_per_hour"]:
        log.warning(f"[{account}] Лимит комментариев за час исчерпан")
        return False
    return True


def record_join(account: str):
    _record(account, "join")


def record_comment(account: str):
    _record(account, "comment")


async def human_delay(min_s: float = 2.0, max_s: float = 8.0):
    """Случайная пауза имитирующая живого пользователя."""
    delay = random.uniform(min_s, max_s)
    await asyncio.sleep(delay)


async def join_delay():
    """Пауза перед вступлением в канал."""
    await human_delay(3.0, 12.0)


async def between_accounts_delay():
    """Пауза между действиями разных аккаунтов."""
    await human_delay(8.0, 20.0)


async def after_comment_delay():
    """Пауза после комментария."""
    await human_delay(5.0, 15.0)


def get_proxy_for_telethon(proxy_cfg: dict) -> tuple | None:
    """
    Конвертирует прокси из config.json в формат Telethon.
    config формат:
    {
      "type": "socks5",   // socks4, socks5, http
      "addr": "127.0.0.1",
      "port": 1080,
      "username": "",     // опционально
      "password": ""      // опционально
    }
    """
    if not proxy_cfg:
        return None
    import socks  # PySocks
    proxy_types = {
        "socks4": socks.SOCKS4,
        "socks5": socks.SOCKS5,
        "http": socks.HTTP,
    }
    ptype = proxy_types.get(proxy_cfg.get("type", "socks5").lower())
    if not ptype:
        return None
    return (
        ptype,
        proxy_cfg["addr"],
        proxy_cfg["port"],
        True,  # rdns
        proxy_cfg.get("username") or None,
        proxy_cfg.get("password") or None,
    )


def get_stats_for_account(account: str) -> dict:
    return {
        "joins_last_hour": _count_recent(account, "join", 60),
        "joins_today": _count_recent(account, "join", 1440),
        "comments_last_hour": _count_recent(account, "comment", 60),
    }
