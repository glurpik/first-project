"""
Telegram Giveaway Research Tool
Investigative tool for documenting fake/rigged Telegram giveaways.
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timedelta

from colorama import Fore, Style, init as colorama_init
from telethon import TelegramClient
from telethon.errors import (
    ChannelPrivateError, FloodWaitError, UserAlreadyParticipantError,
    ChatWriteForbiddenError
)
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest

import database as db
import anti_ban
from parser import detect_giveaway
from discoverer import (
    run_discovery, get_all_channels, save_channel,
    extract_channels_from_post, init_channels_table
)

colorama_init(autoreset=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("research.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

CONFIG_FILE = "config.json"


def load_config() -> dict:
    if not os.path.exists(CONFIG_FILE):
        print(f"{Fore.RED}Файл config.json не найден!{Style.RESET_ALL}")
        sys.exit(1)
    with open(CONFIG_FILE, encoding="utf-8") as f:
        cfg = json.load(f)
    if cfg.get("api_id") == 0 or cfg.get("api_hash") == "YOUR_API_HASH_HERE":
        print(f"{Fore.RED}Заполни api_id и api_hash в config.json (получить на my.telegram.org){Style.RESET_ALL}")
        sys.exit(1)
    # Обновляем лимиты anti_ban из конфига
    if "limits" in cfg:
        anti_ban.LIMITS.update(cfg["limits"])
    return cfg


def make_client(cfg: dict, account_cfg: dict, suffix: str = "") -> TelegramClient:
    proxy = anti_ban.get_proxy_for_telethon(account_cfg.get("proxy"))
    return TelegramClient(
        account_cfg["session_name"] + suffix,
        cfg["api_id"],
        cfg["api_hash"],
        proxy=proxy
    )


def print_banner():
    print(f"{Fore.CYAN}")
    print("╔══════════════════════════════════════════════╗")
    print("║     Telegram Giveaway Research Tool          ║")
    print("║     Исследование честности розыгрышей        ║")
    print("╚══════════════════════════════════════════════╝")
    print(f"{Style.RESET_ALL}")


async def join_channel_safe(
    client: TelegramClient, username: str, account_phone: str
) -> bool:
    if not anti_ban.can_join(account_phone):
        return False

    await anti_ban.join_delay()
    try:
        if username.startswith("joinchat/") or (len(username) > 5 and username.startswith("+")):
            invite_hash = username.replace("joinchat/", "").lstrip("+")
            await client(ImportChatInviteRequest(invite_hash))
        else:
            await client(JoinChannelRequest(username))

        anti_ban.record_join(account_phone)
        log.info(f"{Fore.GREEN}[{account_phone}] Вступил в @{username}{Style.RESET_ALL}")
        return True

    except UserAlreadyParticipantError:
        return True
    except ChannelPrivateError:
        log.warning(f"[{account_phone}] Канал @{username} приватный")
        return False
    except FloodWaitError as e:
        log.warning(f"[{account_phone}] FloodWait {e.seconds}s — пауза")
        await asyncio.sleep(e.seconds + 5)
        return False
    except Exception as e:
        log.warning(f"[{account_phone}] Ошибка при вступлении в @{username}: {e}")
        return False


async def participate(
    client: TelegramClient,
    account_phone: str,
    giveaway_id: int,
    channel: str,
    message_id: int,
    giveaway_info,
) -> list:
    actions = []

    # 1. Вступить в основной канал
    ok = await join_channel_safe(client, channel, account_phone)
    if ok:
        actions.append(f"joined_main:{channel}")

    # 2. Вступить во все упомянутые каналы
    for ch in giveaway_info.channels_to_join:
        if ch == channel:
            continue
        ok = await join_channel_safe(client, ch, account_phone)
        if ok:
            actions.append(f"joined:{ch}")

    # 3. Оставить комментарий если нужно
    if giveaway_info.needs_comment and giveaway_info.comment_text:
        if anti_ban.can_comment(account_phone):
            await anti_ban.after_comment_delay()
            try:
                await client.send_message(
                    channel,
                    giveaway_info.comment_text,
                    comment_to=message_id
                )
                anti_ban.record_comment(account_phone)
                actions.append(f"commented:{giveaway_info.comment_text}")
                log.info(f"{Fore.GREEN}[{account_phone}] Комментарий '{giveaway_info.comment_text}'{Style.RESET_ALL}")
            except ChatWriteForbiddenError:
                log.warning(f"[{account_phone}] Нельзя комментировать @{channel}")
            except Exception as e:
                log.warning(f"[{account_phone}] Ошибка комментария: {e}")

    await db.save_participation(account_phone, giveaway_id, actions)

    ban_stats = anti_ban.get_stats_for_account(account_phone)
    print(
        f"{Fore.GREEN}[{account_phone}] Участие записано | "
        f"Действий: {len(actions)} | "
        f"Вступлений сегодня: {ban_stats['joins_today']}/{anti_ban.LIMITS['joins_per_day']}"
        f"{Style.RESET_ALL}"
    )
    return actions


async def scan_and_participate(cfg: dict):
    """Один полный цикл: скан → участие всеми аккаунтами."""
    if not cfg["accounts"]:
        return

    # Берём первый аккаунт как сканер
    scanner_cfg = cfg["accounts"][0]
    scanner = make_client(cfg, scanner_cfg, "_scan")
    await scanner.start(phone=scanner_cfg["phone"])

    # Получаем список каналов (из БД + config)
    channels_in_config = cfg.get("channels_to_monitor", [])
    channels_from_db = await get_all_channels()
    all_channels = list(set(channels_in_config + channels_from_db))

    if not all_channels:
        print(f"{Fore.YELLOW}Нет каналов для сканирования. Запусти discovery или добавь в config.json{Style.RESET_ALL}")
        await scanner.disconnect()
        return

    print(f"Сканирую {len(all_channels)} каналов...")
    keywords = cfg.get("keywords", [])
    new_giveaways: dict = {}

    for channel_username in all_channels:
        try:
            entity = await scanner.get_entity(channel_username)
            messages = await scanner.get_messages(entity, limit=30)

            for msg in messages:
                if not msg.text:
                    continue
                ginfo = detect_giveaway(msg.text, keywords)
                if not ginfo.is_giveaway:
                    continue

                key = f"{channel_username}_{msg.id}"
                gid = await db.save_giveaway(
                    channel_username, msg.id, msg.text, ginfo.channels_to_join
                )
                if gid > 0:
                    new_giveaways[key] = (gid, channel_username, msg.id, ginfo)
                    print(f"{Fore.YELLOW}Розыгрыш: @{channel_username} msg#{msg.id}{Style.RESET_ALL}")

                    # Добавляем упомянутые каналы в БД для дальнейшего мониторинга
                    for extra_ch in extract_channels_from_post(msg.text):
                        await save_channel(extra_ch, f"mentioned_in:{channel_username}")

            await asyncio.sleep(1)

        except FloodWaitError as e:
            log.warning(f"FloodWait {e.seconds}s при сканировании @{channel_username}")
            await asyncio.sleep(e.seconds)
        except Exception as e:
            log.debug(f"Пропускаю @{channel_username}: {e}")

    await scanner.disconnect()

    if not new_giveaways:
        print("Новых розыгрышей не найдено.")
        return

    print(f"{Fore.YELLOW}Найдено новых розыгрышей: {len(new_giveaways)}{Style.RESET_ALL}")

    # Каждый расходник участвует
    for account_cfg in cfg["accounts"]:
        phone = account_cfg["phone"]
        client = make_client(cfg, account_cfg)
        try:
            await client.start(phone=phone)
            me = await client.get_me()
            print(f"{Fore.CYAN}Аккаунт {phone} ({me.first_name}){Style.RESET_ALL}")

            for key, (gid, channel, message_id, ginfo) in new_giveaways.items():
                await participate(client, phone, gid, channel, message_id, ginfo)
                await anti_ban.human_delay(3, 8)

        except Exception as e:
            log.error(f"Ошибка аккаунта {phone}: {e}")
        finally:
            await client.disconnect()

        await anti_ban.between_accounts_delay()


async def run_discovery_cycle(cfg: dict, last_discovery: datetime) -> datetime:
    """Запускает discovery если прошло достаточно времени."""
    interval_h = cfg.get("rediscover_interval_hours", 6)
    if datetime.now() - last_discovery < timedelta(hours=interval_h):
        return last_discovery

    if not cfg.get("auto_discover", True):
        return last_discovery

    print(f"{Fore.CYAN}Запускаю автопоиск новых каналов...{Style.RESET_ALL}")
    scanner_cfg = cfg["accounts"][0]
    proxy_cfg = scanner_cfg.get("proxy")

    client = make_client(cfg, scanner_cfg, "_discovery")
    try:
        await client.start(phone=scanner_cfg["phone"])
        total = await run_discovery(client, proxy_cfg)
        print(f"{Fore.CYAN}Каналов в базе: {total}{Style.RESET_ALL}")
    finally:
        await client.disconnect()

    return datetime.now()


async def print_stats():
    stats = await db.get_stats()
    print(f"\n{Fore.CYAN}{'='*50}")
    print("СТАТИСТИКА ИССЛЕДОВАНИЯ")
    print(f"{'='*50}{Style.RESET_ALL}")
    print(f"Розыгрышей найдено:       {stats['total_giveaways_found']}")
    print(f"Участий совершено:         {stats['total_participations']}")
    print(f"Побед:                     {Fore.RED}{stats['total_wins']}{Style.RESET_ALL}")
    print(f"Аккаунтов задействовано:   {stats['accounts_used']}")
    print(f"Процент побед:             {Fore.RED}{stats['win_rate']}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'='*50}{Style.RESET_ALL}\n")


async def main():
    print_banner()
    cfg = load_config()
    await db.init_db()
    await init_channels_table()

    print(f"Аккаунтов: {len(cfg['accounts'])}")
    print(f"Автопоиск каналов: {'ВКЛ' if cfg.get('auto_discover') else 'ВЫКЛ'}")
    print(f"Интервал сканирования: {cfg.get('scan_interval_seconds', 120)}s\n")

    last_discovery = datetime.min
    iteration = 0

    while True:
        iteration += 1
        print(f"\n{Fore.CYAN}[{datetime.now().strftime('%H:%M:%S')}] Итерация #{iteration}{Style.RESET_ALL}")

        # Периодический поиск новых каналов
        try:
            last_discovery = await run_discovery_cycle(cfg, last_discovery)
        except Exception as e:
            log.error(f"Ошибка discovery: {e}")

        # Сканирование и участие
        try:
            await scan_and_participate(cfg)
        except Exception as e:
            log.error(f"Ошибка сканирования: {e}")

        await print_stats()

        interval = cfg.get("scan_interval_seconds", 120)
        print(f"Следующий скан через {interval}s...")
        await asyncio.sleep(interval)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Остановлено. Финальная статистика:{Style.RESET_ALL}")
        asyncio.run(print_stats())
