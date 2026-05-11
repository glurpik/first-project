"""
Telegram Giveaway Research Tool
Investigative tool for documenting fake/rigged Telegram giveaways.
Participates with multiple accounts and tracks win statistics.
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime

from colorama import Fore, Style, init as colorama_init
from telethon import TelegramClient, events
from telethon.errors import (
    ChannelPrivateError, FloodWaitError, UserAlreadyParticipantError,
    ChatWriteForbiddenError, SessionPasswordNeededError
)
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest

import database as db
from parser import detect_giveaway

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
        print(f"{Fore.RED}Файл config.json не найден! Скопируй config.json и заполни данные.{Style.RESET_ALL}")
        sys.exit(1)
    with open(CONFIG_FILE, encoding="utf-8") as f:
        cfg = json.load(f)
    if cfg.get("api_id") == 0 or cfg.get("api_hash") == "YOUR_API_HASH_HERE":
        print(f"{Fore.RED}Заполни api_id и api_hash в config.json (получить на my.telegram.org){Style.RESET_ALL}")
        sys.exit(1)
    return cfg


def print_banner():
    print(f"{Fore.CYAN}")
    print("╔══════════════════════════════════════════════╗")
    print("║     Telegram Giveaway Research Tool          ║")
    print("║     Исследование честности розыгрышей        ║")
    print("╚══════════════════════════════════════════════╝")
    print(f"{Style.RESET_ALL}")


async def join_channel(client: TelegramClient, username: str, account_phone: str) -> bool:
    try:
        if username.startswith("joinchat/") or username.startswith("+"):
            invite_hash = username.replace("joinchat/", "").replace("+", "")
            await client(ImportChatInviteRequest(invite_hash))
        else:
            await client(JoinChannelRequest(username))
        log.info(f"{Fore.GREEN}[{account_phone}] Вступил в @{username}{Style.RESET_ALL}")
        await asyncio.sleep(2)  # Небольшая пауза чтобы не триггерить флуд
        return True
    except UserAlreadyParticipantError:
        return True
    except ChannelPrivateError:
        log.warning(f"[{account_phone}] Канал @{username} приватный или недоступен")
        return False
    except FloodWaitError as e:
        log.warning(f"[{account_phone}] FloodWait {e.seconds}s при вступлении в @{username}")
        await asyncio.sleep(e.seconds)
        return False
    except Exception as e:
        log.warning(f"[{account_phone}] Ошибка при вступлении в @{username}: {e}")
        return False


async def participate_in_giveaway(
    client: TelegramClient,
    account_phone: str,
    giveaway_id: int,
    channel: str,
    message_id: int,
    giveaway_info,
):
    actions_taken = []

    # 1. Вступить во все упомянутые каналы
    for ch in giveaway_info.channels_to_join:
        success = await join_channel(client, ch, account_phone)
        if success:
            actions_taken.append(f"joined:{ch}")

    # 2. Основной канал розыгрыша
    await join_channel(client, channel, account_phone)
    actions_taken.append(f"joined_main:{channel}")

    # 3. Оставить комментарий (если требуется)
    if giveaway_info.needs_comment and giveaway_info.comment_text:
        try:
            await client.send_message(
                channel,
                giveaway_info.comment_text,
                comment_to=message_id
            )
            actions_taken.append(f"commented:{giveaway_info.comment_text}")
            log.info(f"{Fore.GREEN}[{account_phone}] Оставил комментарий '{giveaway_info.comment_text}'{Style.RESET_ALL}")
            await asyncio.sleep(3)
        except ChatWriteForbiddenError:
            log.warning(f"[{account_phone}] Нельзя комментировать в {channel}")
        except Exception as e:
            log.warning(f"[{account_phone}] Ошибка комментария: {e}")

    # 4. Сохранить участие в БД
    await db.save_participation(account_phone, giveaway_id, actions_taken)

    print(
        f"{Fore.GREEN}[{account_phone}] Участие зафиксировано | "
        f"Действия: {', '.join(actions_taken) or 'только вступление'}{Style.RESET_ALL}"
    )
    return actions_taken


async def run_account(cfg: dict, account_cfg: dict, all_giveaways: dict):
    """Запускает один аккаунт — подписывается на мониторинг и участвует в розыгрышах."""
    phone = account_cfg["phone"]
    session = account_cfg["session_name"]

    client = TelegramClient(session, cfg["api_id"], cfg["api_hash"])
    await client.start(phone=phone)

    me = await client.get_me()
    print(f"{Fore.CYAN}Аккаунт {phone} ({me.first_name}) подключён{Style.RESET_ALL}")

    # Участвуем в уже найденных розыгрышах
    for key, (gid, channel, message_id, ginfo) in all_giveaways.items():
        await participate_in_giveaway(client, phone, gid, channel, message_id, ginfo)
        await asyncio.sleep(5)

    await client.disconnect()


async def scan_channels(cfg: dict) -> dict:
    """Сканирует каналы одним аккаунтом, возвращает найденные розыгрыши."""
    if not cfg["accounts"]:
        print(f"{Fore.RED}Нет аккаунтов в config.json{Style.RESET_ALL}")
        return {}

    scanner_cfg = cfg["accounts"][0]
    scanner = TelegramClient(
        scanner_cfg["session_name"] + "_scan",
        cfg["api_id"],
        cfg["api_hash"]
    )
    await scanner.start(phone=scanner_cfg["phone"])

    found_giveaways = {}
    keywords = cfg.get("keywords", [])

    for channel_username in cfg.get("channels_to_monitor", []):
        try:
            print(f"Сканирую @{channel_username}...")
            entity = await scanner.get_entity(channel_username)
            messages = await scanner.get_messages(entity, limit=50)

            for msg in messages:
                if not msg.text:
                    continue
                ginfo = detect_giveaway(msg.text, keywords)
                if not ginfo.is_giveaway:
                    continue

                key = f"{channel_username}_{msg.id}"
                if key in found_giveaways:
                    continue

                gid = await db.save_giveaway(
                    channel_username, msg.id, msg.text, ginfo.channels_to_join
                )

                if gid > 0:
                    found_giveaways[key] = (gid, channel_username, msg.id, ginfo)
                    print(
                        f"{Fore.YELLOW}Найден розыгрыш в @{channel_username} "
                        f"(msg #{msg.id}){Style.RESET_ALL}"
                    )
                    if ginfo.end_date_hint:
                        print(f"  Дата окончания: {ginfo.end_date_hint}")
                    print(f"  Каналы для вступления: {ginfo.channels_to_join}")

        except FloodWaitError as e:
            log.warning(f"FloodWait {e.seconds}s при сканировании @{channel_username}")
            await asyncio.sleep(e.seconds)
        except Exception as e:
            log.warning(f"Ошибка при сканировании @{channel_username}: {e}")

    await scanner.disconnect()
    return found_giveaways


async def print_stats():
    stats = await db.get_stats()
    print(f"\n{Fore.CYAN}{'='*50}")
    print("СТАТИСТИКА ИССЛЕДОВАНИЯ")
    print(f"{'='*50}{Style.RESET_ALL}")
    print(f"Розыгрышей найдено:      {stats['total_giveaways_found']}")
    print(f"Участий совершено:        {stats['total_participations']}")
    print(f"Побед:                    {stats['total_wins']}")
    print(f"Аккаунтов задействовано:  {stats['accounts_used']}")
    print(f"Процент побед:            {Fore.RED}{stats['win_rate']}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'='*50}{Style.RESET_ALL}\n")


async def main():
    print_banner()
    cfg = load_config()
    await db.init_db()

    print(f"Аккаунтов: {len(cfg['accounts'])}")
    print(f"Каналов для мониторинга: {len(cfg['channels_to_monitor'])}")
    print(f"Интервал сканирования: {cfg.get('scan_interval_seconds', 60)}s\n")

    iteration = 0
    while True:
        iteration += 1
        print(f"\n{Fore.CYAN}[{datetime.now().strftime('%H:%M:%S')}] Итерация #{iteration}{Style.RESET_ALL}")

        # 1. Сканировать каналы и найти новые розыгрыши
        try:
            giveaways = await scan_channels(cfg)
        except Exception as e:
            log.error(f"Ошибка сканирования: {e}")
            giveaways = {}

        if giveaways:
            print(f"{Fore.YELLOW}Новых розыгрышей: {len(giveaways)}{Style.RESET_ALL}")

            # 2. Каждый расходник участвует во всех найденных розыгрышах
            for account_cfg in cfg["accounts"]:
                try:
                    await run_account(cfg, account_cfg, giveaways)
                    await asyncio.sleep(10)  # Пауза между аккаунтами
                except Exception as e:
                    log.error(f"Ошибка аккаунта {account_cfg['phone']}: {e}")
        else:
            print("Новых розыгрышей не найдено.")

        # 3. Показать текущую статистику
        await print_stats()

        # 4. Ждём до следующего сканирования
        interval = cfg.get("scan_interval_seconds", 60)
        print(f"Следующее сканирование через {interval}s...")
        await asyncio.sleep(interval)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Остановлено. Итоговая статистика:{Style.RESET_ALL}")
        asyncio.run(print_stats())
