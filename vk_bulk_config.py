#!/usr/bin/env python3
"""
VK Account Bulk Configurator
────────────────────────────
Файлы на входе:
  accounts.txt   — login:pass, по одному на строку
  proxy.txt      — ip:port:user:pass  (или socks5://ip:port:user:pass)
  names.txt      — "Имя Фамилия", по одному на строку
  usernames.txt  — короткое имя страницы (id-alias), по одному на строку
  avatars/       — изображения (jpg/png), сортировка по имени (1.jpg → акк1)
Вывод: log.txt
"""
import os
import re
import sys
import time
import random
import logging
from datetime import datetime
from pathlib import Path

try:
    import requests
    import vk_api
    from vk_api.exceptions import ApiError, AuthError
except ImportError as exc:
    sys.exit(
        "Установите зависимости:\n"
        "  pip install vk_api requests[socks]\n"
        f"Ошибка: {exc}"
    )


# ─────────────────────────── логирование ────────────────────────────

_logger: logging.Logger = None  # type: ignore


def setup_logger() -> logging.Logger:
    logger = logging.getLogger("vkb")
    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(message)s")

    fh = logging.FileHandler("log.txt", encoding="utf-8")
    fh.setLevel(logging.INFO)
    fh.setFormatter(fmt)

    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(logging.INFO)
    sh.setFormatter(fmt)

    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger


def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log_ok(login: str):
    _logger.info(f"[{_ts()}] {login} — OK")


def log_err(login: str, reason: str):
    _logger.info(f"[{_ts()}] {login} — ОШИБКА: {reason}")


def log_info(msg: str):
    _logger.info(f"[{_ts()}] {msg}")


# ─────────────────────────── чтение файлов ──────────────────────────

def read_lines(path: str) -> list[str]:
    p = Path(path)
    if not p.exists():
        return []
    return [l.strip() for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def get_avatars(folder: str = "avatars") -> list[Path]:
    p = Path(folder)
    if not p.exists():
        return []
    exts = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
    files = [f for f in p.iterdir() if f.suffix.lower() in exts]

    def sort_key(f: Path):
        try:
            return (0, int(f.stem))
        except ValueError:
            return (1, f.stem)

    return sorted(files, key=sort_key)


def parse_proxy(raw: str) -> dict | None:
    """
    Форматы:
      ip:port                      — HTTP без авторизации
      ip:port:user:pass            — HTTP с авторизацией
      socks5://ip:port:user:pass   — SOCKS5 с авторизацией
      http://ip:port:user:pass     — HTTP с авторизацией (явный префикс)
    """
    raw = raw.strip()
    if not raw:
        return None

    scheme = "http"
    for prefix in ("socks5://", "socks4://", "https://", "http://"):
        if raw.lower().startswith(prefix):
            s = prefix.rstrip(":/").lower()
            scheme = "http" if s == "https" else s
            raw = raw[len(prefix):]
            break

    parts = raw.split(":")
    if len(parts) == 4:
        ip, port, user, pw = parts
        url = f"{scheme}://{user}:{pw}@{ip}:{port}"
    elif len(parts) == 2:
        ip, port = parts
        url = f"{scheme}://{ip}:{port}"
    else:
        return None

    return {"http": url, "https": url}


# ─────────────────────────── vk_api-хелперы ─────────────────────────

def _get_http(vk_sess: vk_api.VkApi) -> requests.Session | None:
    """Вернуть внутренний requests.Session из объекта VkApi."""
    for attr in ("http", "_session", "session"):
        obj = getattr(vk_sess, attr, None)
        if isinstance(obj, requests.Session):
            return obj
    return None


def make_vk_session(login: str, password: str, proxy: dict | None) -> vk_api.VkApi:
    safe = re.sub(r"[^\w]", "_", login)
    os.makedirs(".vk_cache", exist_ok=True)

    vk_sess = vk_api.VkApi(
        login=login,
        password=password,
        app_id=2895443,                             # Kate Mobile — стандартный app_id
        scope="offline,photos,account,status",
        api_version="5.131",
        config_filename=f".vk_cache/{safe}.json",
    )

    http = _get_http(vk_sess)
    if http is not None and proxy:
        http.proxies.update(proxy)

    vk_sess.auth()
    return vk_sess


# ─────────────────────────── действия с аккаунтом ───────────────────

def upload_avatar(vk_sess: vk_api.VkApi, path: Path):
    srv = vk_sess.method("photos.getOwnerPhotoUploadServer")
    upload_url = srv["upload_url"]

    http = _get_http(vk_sess) or requests  # type: ignore[assignment]
    with open(path, "rb") as fh:
        resp = http.post(upload_url, files={"photo": fh})
    resp.raise_for_status()

    d = resp.json()
    vk_sess.method("photos.saveOwnerPhoto", {
        "server": d["server"],
        "photo":  d["photo"],
        "hash":   d["hash"],
    })


def set_name(vk_sess: vk_api.VkApi, full_name: str):
    parts = full_name.split(None, 1)
    vk_sess.method("account.saveProfileInfo", {
        "first_name": parts[0],
        "last_name":  parts[1] if len(parts) > 1 else "",
    })


def set_username(vk_sess: vk_api.VkApi, username: str) -> str:
    """Устанавливает юзернейм; если занят — добавляет 4 случайные цифры."""
    candidates = [username] + [
        username + str(random.randint(1000, 9999)) for _ in range(5)
    ]
    for candidate in candidates:
        try:
            r = vk_sess.method("account.saveProfileInfo", {"screen_name": candidate})
            if r.get("changed") == 1:
                return candidate
        except ApiError:
            pass
    raise RuntimeError(f"не удалось задать юзернейм '{username}' (все варианты заняты)")


def set_birth_year(vk_sess: vk_api.VkApi, year: int = 2005):
    info = vk_sess.method("users.get", {"fields": "bdate"})[0]
    raw = info.get("bdate", "")
    parts = raw.split(".") if raw else []
    day   = parts[0] if len(parts) >= 1 else "1"
    month = parts[1] if len(parts) >= 2 else "1"
    vk_sess.method("account.saveProfileInfo", {
        "bdate": f"{day}.{month}.{year}",
    })


def make_profile_closed(vk_sess: vk_api.VkApi):
    """Делает профиль закрытым (виден только друзьям)."""
    # Попытка 1: saveProfileInfo с is_closed (VK API >= 5.116)
    for params in (
        {"is_closed": 1},
    ):
        try:
            vk_sess.method("account.saveProfileInfo", params)
            return
        except ApiError:
            pass

    # Попытка 2: account.setPrivacy
    for val in ("friends", 1):
        try:
            vk_sess.method("account.setPrivacy", {"key": "page", "value": val})
            return
        except ApiError:
            pass


# ─────────────────────────── обработка аккаунта ─────────────────────

def process_account(
    login: str,
    password: str,
    proxy: dict | None,
    avatar: Path | None,
    name: str | None,
    username: str | None,
):
    # ── авторизация ──
    try:
        vk_sess = make_vk_session(login, password, proxy)
    except requests.exceptions.ProxyError as e:
        raise RuntimeError(f"прокси недоступен: {e}") from e
    except requests.exceptions.ConnectionError as e:
        raise RuntimeError(f"ошибка подключения: {e}") from e
    except AuthError as e:
        raise RuntimeError(f"авторизация: {e}") from e
    except ApiError as e:
        if e.code == 14:
            raise RuntimeError("капча") from e
        if e.code == 17:
            raise RuntimeError("требуется подтверждение телефона") from e
        raise RuntimeError(f"API {e.code}: {e}") from e

    # ── шаги конфигурации ──
    errors: list[str] = []

    def step(label: str, fn, *args, **kwargs):
        try:
            fn(*args, **kwargs)
        except Exception as exc:
            errors.append(f"{label}: {exc}")
        time.sleep(random.uniform(1.0, 3.0))

    if avatar:
        step("аватар",          upload_avatar,      vk_sess, avatar)
    if name:
        step("имя/фамилия",     set_name,           vk_sess, name)
    if username:
        step("юзернейм",        set_username,       vk_sess, username)
    step("год рождения",        set_birth_year,     vk_sess)
    step("закрытый профиль",    make_profile_closed, vk_sess)

    if errors:
        raise RuntimeError("; ".join(errors))


# ─────────────────────────── main ───────────────────────────────────

def main():
    global _logger
    _logger = setup_logger()

    accounts  = read_lines("accounts.txt")
    proxies   = read_lines("proxy.txt")
    names     = read_lines("names.txt")
    usernames = read_lines("usernames.txt")
    avatars   = get_avatars("avatars")

    if not accounts:
        log_info("accounts.txt не найден или пуст — выход")
        return

    log_info(
        f"Аккаунтов: {len(accounts)} | "
        f"Прокси: {len(proxies)} | "
        f"Имён: {len(names)} | "
        f"Юзернеймов: {len(usernames)} | "
        f"Аватарок: {len(avatars)}"
    )

    for i, line in enumerate(accounts):
        if ":" not in line:
            log_info(f"Строка {i + 1}: неверный формат — пропуск")
            continue

        login, _, password = line.partition(":")

        proxy    = parse_proxy(proxies[i])   if i < len(proxies)    else None
        avatar   = avatars[i]                if i < len(avatars)    else None
        name     = names[i]                  if i < len(names)      else None
        uname    = usernames[i]              if i < len(usernames)  else None

        log_info(f"[{i + 1}/{len(accounts)}] {login}")

        try:
            process_account(login, password, proxy, avatar, name, uname)
            log_ok(login)
        except RuntimeError as exc:
            log_err(login, str(exc))
        except Exception as exc:
            log_err(login, f"неизвестная ошибка: {exc}")

        if i < len(accounts) - 1:
            pause = random.uniform(3.0, 7.0)
            log_info(f"Пауза {pause:.1f}с")
            time.sleep(pause)

    log_info("Завершено")


if __name__ == "__main__":
    main()
