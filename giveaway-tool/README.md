# Telegram Giveaway Research Tool

Инструмент для документирования нечестных розыгрышей в Telegram.

## Установка

```bash
pip install -r requirements.txt
```

## Настройка

1. **Получи API ключи** на [my.telegram.org](https://my.telegram.org):
   - Войди → API development tools → создай приложение
   - Скопируй `App api_id` и `App api_hash`

2. **Заполни config.json**:
```json
{
  "api_id": 12345678,
  "api_hash": "abcdef1234567890abcdef1234567890",
  "channels_to_monitor": ["channel1", "channel2"],
  "accounts": [
    {"phone": "+79991234567", "session_name": "acc1"},
    {"phone": "+79997654321", "session_name": "acc2"}
  ]
}
```

3. Добавь каналы с розыгрышами в `channels_to_monitor`

## Запуск

```bash
# Основной мониторинг
python main.py

# Финальный отчёт для видео
python report.py
```

При первом запуске каждый аккаунт попросит ввести код из SMS.
Сессии сохраняются в файлы `*.session` — повторно вводить не нужно.

## Что собирает инструмент

- Все посты с ключевыми словами розыгрышей
- Каналы, в которые нужно вступить
- Факт участия каждого аккаунта с временной меткой
- Результат: выиграл / не выиграл
- Итоговую статистику и процент побед

## Файлы результатов

- `research.db` — SQLite база со всеми данными
- `research.log` — подробный лог всех действий
