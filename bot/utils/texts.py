RANK_MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}
RANK_BONUSES = {1: "+10%", 2: "+7%", 3: "+5%"}
RANK_BOXES = ["4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]


def format_leaderboard(entries: list[dict], current_user_id: int, rank: int, user_joins: int, seconds_to_update: int) -> str:
    lines = ["🏆 <b>Таблица лидеров</b> ""\n"]
    for i, entry in enumerate(entries, start=1):
        joins = entry["total_joins"]
        bonus = f" 💰 <b>{RANK_BONUSES[i]}</b>" if i in RANK_BONUSES else ""
        medal = RANK_MEDALS.get(i, RANK_BOXES[i - 4] if i <= 10 else f"{i}.")
        pointer = " ◀ 👈" if entry["user_id"] == current_user_id else ""
        if i <= 3:
            lines.append(f"{medal} ▸ {joins} чел.{bonus}{pointer}")
        else:
            lines.append(f"{medal} ▸ {joins} чел.{pointer}")

    lines.append("")
    lines.append(f"📍 <b>Ты на {rank}-м месте</b> с {user_joins} приглашёнными")
    lines.append("")
    lines.append("🔄 Обновляется раз в 5 мин.")
    mins, secs = divmod(seconds_to_update, 60)
    lines.append(f"⏱ Следующее обновление через {mins} мин. {secs} сек.")
    return "\n".join(lines)


def format_my_links(links: list[dict], page: int, total_pages: int, total_slots: int, max_slots: int) -> str:
    header = (
        f"📋 <b>Мои ссылки</b> ""\n"
        f"Слоты: <b>{total_slots} из {max_slots}</b>\n"
        f"Страница {page} из {total_pages}\n\n"
        f"Нажми на ссылку, чтобы увидеть вступивших:"
    )
    return header


def format_link_button(link: dict) -> str:
    verified = "✅" if link["join_count"] >= 0 else "❌"
    joins = link["join_count"]
    label = link.get("label") or link.get("channel_username") or str(link["channel_id"])
    slot = link["slot_number"]
    return f"#{slot} @{label} · {verified} {joins} вступ."
