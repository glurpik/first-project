# XMR Miner — Android + Dashboard

CPU майнинг Monero (XMR) на Android через протокол Stratum + веб-панель мониторинга.

## Структура проекта

```
android/          — Android-приложение (Kotlin)
dashboard/        — Веб-дашборд (HTML/CSS/JS)
server/           — Node.js API-сервер для статистики
```

## Android-приложение

### Требования
- Android 7.0+ (API 24)
- Android Studio Hedgehog (2023.1.1) или новее

### Сборка

```bash
cd android
./gradlew assembleDebug
```

APK будет в `android/app/build/outputs/apk/debug/`.

### Настройка
1. Открой приложение
2. Введи адрес XMR-кошелька (95+ символов, формат Monero)
3. Задай имя воркера (например `phone1`)
4. Пул по умолчанию: `pool.supportxmr.com:3333`
5. Нажми **START MINING**

Приложение работает в фоне как Foreground Service с уведомлением.

### Поддерживаемые пулы
- `pool.supportxmr.com:3333`
- `xmrpool.eu:3333`
- `mine.xmrpool.net:3333`
- `pool.minexmr.com:4444`

## Веб-дашборд

### Запуск через сервер (рекомендуется)

```bash
cd server
npm install
npm start
# Открой http://localhost:3000
```

### Запуск напрямую (demo-режим)

Открой `dashboard/index.html` в браузере — работает с демо-данными без сервера.

### Подключение к Android-приложению

В `dashboard/js/dashboard.js` измени строку:
```js
const API_URL = null;
// на:
const API_URL = 'http://<IP-телефона>:3000/api/stats';
```

Для отправки статистики с телефона на сервер, добавь в `StatsManager.kt` HTTP POST к `http://<IP-сервера>:3000/api/stats`.

## Возможности дашборда

- График хешрейта за последний час
- Статистика принятых/отклонённых шар
- График эффективности
- Индикатор онлайн/офлайн воркера
- Авто-обновление каждые 5 секунд
- Адаптивный дизайн (mobile-friendly)

## Примечания

- CPU-майнинг на мобильном телефоне даёт ~100-300 H/s
- Рекомендуется ограничить нагрев (не заряжать во время майнинга)
- Для реального RandomX нужна нативная C++ библиотека (xmrig-android)
