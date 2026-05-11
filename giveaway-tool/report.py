"""
Генерирует отчёт для видео — показывает сколько участий было и сколько побед.
"""

import asyncio
import json
from datetime import datetime
from colorama import Fore, Style, init as colorama_init

import database as db

colorama_init(autoreset=True)


async def full_report():
    await db.init_db()
    stats = await db.get_stats()

    print(f"\n{Fore.CYAN}{'='*60}")
    print("  ФИНАЛЬНЫЙ ОТЧЁТ ПО ИССЛЕДОВАНИЮ РОЗЫГРЫШЕЙ В TELEGRAM")
    print(f"  Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    print(f"{'='*60}{Style.RESET_ALL}\n")

    print(f"  Всего розыгрышей найдено:    {stats['total_giveaways_found']}")
    print(f"  Всего участий совершено:      {stats['total_participations']}")
    print(f"  Аккаунтов-расходников:        {stats['accounts_used']}")
    print(f"  Побед зафиксировано:          {Fore.RED}{stats['total_wins']}{Style.RESET_ALL}")
    print(f"  Процент побед:                {Fore.RED}{stats['win_rate']}{Style.RESET_ALL}")

    if stats['total_wins'] == 0 and stats['total_participations'] > 0:
        print(f"\n{Fore.RED}  ВЫВОД: За {stats['total_participations']} участий — НИ ОДНОЙ ПОБЕДЫ.")
        print(f"  Это подтверждает: розыгрыши не дают реальных шансов на выигрыш.{Style.RESET_ALL}")

    print(f"\n{Fore.CYAN}  ДЕТАЛЬНЫЙ ЛОГ УЧАСТИЙ:{Style.RESET_ALL}")
    participations = await db.get_all_participations()
    if not participations:
        print("  (нет данных)")
    else:
        for p in participations[:50]:  # Первые 50
            won_str = f"{Fore.GREEN}ПОБЕДА{Style.RESET_ALL}" if p["won"] else f"{Fore.RED}Не выиграл{Style.RESET_ALL}"
            actions = json.loads(p["actions_taken"]) if p["actions_taken"] else []
            print(
                f"  [{p['participated_at'][:16]}] {p['account']} | "
                f"@{p['channel']} | {won_str} | "
                f"Действий: {len(actions)}"
            )

    print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
    print("  Лог сохранён в research.log | База данных: research.db")
    print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")


if __name__ == "__main__":
    asyncio.run(full_report())
