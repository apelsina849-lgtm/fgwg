import asyncio
import hashlib
import hmac
import html
import json
import os
import random
import secrets
import string
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from urllib.parse import parse_qsl

import aiosqlite
import httpx
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel, Field

BOT_TOKEN = os.environ["BOT_TOKEN"]
OWNER_ID = int(os.getenv("OWNER_TELEGRAM_ID", "8288152903"))
APP_NAME = os.getenv("APP_NAME", "Шрексич")
BASE_URL = os.getenv("WEBAPP_URL", "").rstrip("/")
ADMIN_URL = os.getenv("ADMIN_URL", BASE_URL + "/admin").rstrip("/")
DB_PATH = os.getenv("DB_PATH", "/data/shreksich.db")
MANUAL_PAYMENT = os.getenv("MANUAL_PAYMENT_DETAILS", "Реквизиты пока не настроены. Напишите в поддержку.")
TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
poll_offset = 0
bot_username = ""
db_write_lock = asyncio.Lock()

MAX_FREE_SPINS_24H = 1

SPIN_TIER_CHANCES = {
    "COMMON": 97.5,
    "RARE": 1.8,
    "EPIC": 0.5,
    "LEGENDARY": 0.15,
    "MYTHIC": 0.05,
}

SPIN_REWARDS = [
    # COMMON — total 97.5%
    {"name":"250K Metro Cash","tier":"COMMON","weight":6.9642857143,"points":1,"value_stars":5},
    {"name":"500K Metro Cash","tier":"COMMON","weight":6.9642857143,"points":1,"value_stars":7},
    {"name":"Набор патронов","tier":"COMMON","weight":6.9642857143,"points":1,"value_stars":6},
    {"name":"Набор аптечек","tier":"COMMON","weight":6.9642857143,"points":1,"value_stars":6},
    {"name":"Набор ремонта","tier":"COMMON","weight":6.9642857143,"points":1,"value_stars":7},
    {"name":"Ящик базовых ресурсов","tier":"COMMON","weight":6.9642857143,"points":1,"value_stars":8},
    {"name":"Тактический ремкомплект","tier":"COMMON","weight":6.9642857143,"points":1,"value_stars":9},
    {"name":"Полевой медпак","tier":"COMMON","weight":6.9642857143,"points":1,"value_stars":8},
    {"name":"Комплект дымовых гранат","tier":"COMMON","weight":6.9642857143,"points":1,"value_stars":6},
    {"name":"Комплект осколочных гранат","tier":"COMMON","weight":6.9642857143,"points":1,"value_stars":7},
    {"name":"Набор пластин брони","tier":"COMMON","weight":6.9642857143,"points":1,"value_stars":9},
    {"name":"Ящик стандартных модулей","tier":"COMMON","weight":6.9642857143,"points":1,"value_stars":10},
    {"name":"750K Metro Cash","tier":"COMMON","weight":6.9642857143,"points":1,"value_stars":10},
    {"name":"Набор энергетиков","tier":"COMMON","weight":6.9642857143,"points":1,"value_stars":6},

    # RARE — total 1.8%
    {"name":"1M Metro Cash","tier":"RARE","weight":0.2,"points":2,"value_stars":14},
    {"name":"Усиленный набор патронов","tier":"RARE","weight":0.2,"points":2,"value_stars":15},
    {"name":"Набор брони","tier":"RARE","weight":0.2,"points":2,"value_stars":16},
    {"name":"Набор модулей оружия","tier":"RARE","weight":0.2,"points":2,"value_stars":18},
    {"name":"Тактический Supply Case","tier":"RARE","weight":0.2,"points":2,"value_stars":20},
    {"name":"2M Metro Cash","tier":"RARE","weight":0.2,"points":2,"value_stars":22},
    {"name":"Набор улучшенной брони","tier":"RARE","weight":0.2,"points":2,"value_stars":24},
    {"name":"Rare Weapon Parts Pack","tier":"RARE","weight":0.2,"points":2,"value_stars":25},
    {"name":"Metro Utility Pack","tier":"RARE","weight":0.2,"points":2,"value_stars":26},

    # EPIC — total 0.5%
    {"name":"3M Metro Cash","tier":"EPIC","weight":0.0714285714,"points":3,"value_stars":35},
    {"name":"Metro Starter Kit+","tier":"EPIC","weight":0.0714285714,"points":3,"value_stars":39},
    {"name":"Elite Supply Pack","tier":"EPIC","weight":0.0714285714,"points":3,"value_stars":42},
    {"name":"5M Metro Cash","tier":"EPIC","weight":0.0714285714,"points":3,"value_stars":48},
    {"name":"Elite Armor Pack","tier":"EPIC","weight":0.0714285714,"points":3,"value_stars":50},
    {"name":"Black Zone Supply Case","tier":"EPIC","weight":0.0714285714,"points":3,"value_stars":55},
    {"name":"Advanced Weapon Kit","tier":"EPIC","weight":0.0714285714,"points":3,"value_stars":59},

    # LEGENDARY — total 0.15%
    {"name":"Premium Metro Pack","tier":"LEGENDARY","weight":0.0375,"points":6,"value_stars":79},
    {"name":"Буст 3 квестов","tier":"LEGENDARY","weight":0.0375,"points":6,"value_stars":89},
    {"name":"Legendary Supply Vault","tier":"LEGENDARY","weight":0.0375,"points":6,"value_stars":99},
    {"name":"10M Metro Cash","tier":"LEGENDARY","weight":0.0375,"points":6,"value_stars":109},

    # MYTHIC — total 0.05%
    {"name":"Black Market Pack","tier":"MYTHIC","weight":0.0166666667,"points":10,"value_stars":149},
    {"name":"Ultimate Metro Bundle","tier":"MYTHIC","weight":0.0166666667,"points":10,"value_stars":179},
    {"name":"Mythic Contraband Vault","tier":"MYTHIC","weight":0.0166666666,"points":10,"value_stars":199},
]

SHR_REWARDS = [
    {"points":5,"name":"Набор расходников"},
    {"points":10,"name":"Metro Starter Kit"},
    {"points":18,"name":"Premium Metro Pack"},
    {"points":30,"name":"Ultimate Metro Bundle"},
]


TOP_DROP_CHAT = "@chatshreksi4"
TOP_DROP_MESSAGES = [
    "🏆 КРУПНЫЙ ДРОП! {nick} выбил {item} — {rarity}. Поздравляем! Сегодня удача явно на твоей стороне 🔥",
    "💎 ВОТ ЭТО ЗАНОС! {nick} забирает {item} — {rarity}! Такое выпадает далеко не каждый день. GG! 👑",
    "🚨 ВНИМАНИЕ, ЖИРНЫЙ ДРОП! {nick} выбил {item} ({rarity}). Остальным соболезнуем. Победителю — поздравления 😎",
    "👑 Сегодня главный герой — {nick}! Выпало: {item}. Редкость: {rarity}. Красиво залетел, ещё красивее забрал.",
    "🔥 ШРЕКСИЧ РЕШАЕТ! {nick} ловит {rarity} дроп — {item}! Рандом сегодня сказал: «Этот игрок заслужил» 😏",
    "🤑 Ну всё, можно закрывать рулетку. {nick} уже забрал весь фарт себе: {item} — {rarity}.",
    "😂 АДМИН, ВЫНОСИ ЛУТ! {nick} каким-то образом выбил {item} ({rarity}). Проверяем, не родственник ли он разработчика.",
    "🎰 РУЛЕТКА СОШЛА С УМА! Игроку {nick} выпало {item} — {rarity}. Вот ради таких прокрутов мы здесь и собрались.",
    "💀 Остальные игроки после этого дропа: «А мне когда?» {nick} выбивает {item} — {rarity}! Поздравляем счастливчика 😭🔥",
    "🗿 Спокойно. Просто {nick} решил забрать {item}. Редкость: {rarity}. Ничего необычного. Кроме шанса выпадения.",
    "🚀 ЭТО УЖЕ НЕ ВЕЗЕНИЕ, ЭТО СЦЕНАРИЙ. {nick} получает {item} — {rarity}. Поздравляем с мощнейшим дропом!",
    "⚡ ЛЕГЕНДА РОДИЛАСЬ ПРЯМО СЕЙЧАС. {nick} получает {item} ({rarity}). Этот момент заслуживает место в истории Шрексича.",
    "🤯 КТО ВКЛЮЧИЛ ЕМУ ПОДКРУТКУ?! {nick} выбил {item} — {rarity}. Нет, подкрутки нет. Да, нам тоже больно смотреть на такой фарт.",
    "🥶 ХОЛОДНОКРОВНО ЗАБРАЛ ТОП-ДРОП. {nick} → {item} — {rarity}. Без лишних слов. Просто поздравляем.",
    "🎉 ДЖЕКПОТ МОМЕНТ! Сегодня удача выбрала {nick}. Выпало: {item} — {rarity}. Следующий топ-дроп может быть вашим."
]


TOKEN_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

def make_user_token():
    return "SHX-" + "".join(secrets.choice(TOKEN_ALPHABET) for _ in range(8))


async def ensure_user_token(conn, telegram_id: int):
    row = await (await conn.execute("SELECT token FROM users WHERE telegram_id=?", (telegram_id,))).fetchone()
    if row and row["token"]:
        return row["token"]
    for _ in range(20):
        token = make_user_token()
        exists = await (await conn.execute("SELECT 1 FROM users WHERE token=?", (token,))).fetchone()
        if exists:
            continue
        await conn.execute(
            "UPDATE users SET token=? WHERE telegram_id=? AND (token IS NULL OR token='')",
            (token, telegram_id)
        )
        return token
    raise RuntimeError("Не удалось создать уникальный жетон")


async def telegram_id_by_token(conn, token: str):
    normalized = (token or "").strip().upper()
    if not normalized:
        return None
    row = await (await conn.execute(
        "SELECT telegram_id,token,username,first_name FROM users WHERE upper(token)=?",
        (normalized,)
    )).fetchone()
    return row


async def db():
    conn = await aiosqlite.connect(DB_PATH, timeout=15)
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA busy_timeout=15000")
    await conn.execute("PRAGMA foreign_keys=ON")
    return conn


async def init_db():
    conn = await db()
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute("PRAGMA synchronous=NORMAL")
    await conn.executescript("""
    CREATE TABLE IF NOT EXISTS users(
      telegram_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT, token TEXT,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS products(
      id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT NOT NULL, name TEXT NOT NULL,
      description TEXT NOT NULL DEFAULT '', price INTEGER NOT NULL, stars_price INTEGER NOT NULL DEFAULT 0,
      image TEXT NOT NULL DEFAULT '', active INTEGER NOT NULL DEFAULT 1, sort_order INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS orders(
      id INTEGER PRIMARY KEY AUTOINCREMENT, number INTEGER UNIQUE, telegram_id INTEGER NOT NULL,
      product_id INTEGER NOT NULL, product_name TEXT NOT NULL, amount INTEGER NOT NULL,
      stars_amount INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'Ожидает оплаты',
      uid TEXT NOT NULL DEFAULT '', nickname TEXT NOT NULL DEFAULT '', comment TEXT NOT NULL DEFAULT '',
      payment_method TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS tickets(
      id INTEGER PRIMARY KEY AUTOINCREMENT, telegram_id INTEGER NOT NULL, category TEXT NOT NULL,
      message TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Открыт',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS spin_state(
      telegram_id INTEGER PRIMARY KEY,
      tickets INTEGER NOT NULL DEFAULT 3,
      last_free_spin INTEGER NOT NULL DEFAULT 0,
      upgrade_points INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS spin_history(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      telegram_id INTEGER NOT NULL,
      reward_name TEXT NOT NULL,
      reward_tier TEXT NOT NULL,
      points INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS upgrade_claims(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      telegram_id INTEGER NOT NULL,
      reward_name TEXT NOT NULL,
      points_spent INTEGER NOT NULL,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS inventory_items(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      telegram_id INTEGER NOT NULL,
      reward_name TEXT NOT NULL,
      reward_tier TEXT NOT NULL,
      sell_shr INTEGER NOT NULL DEFAULT 0,
      value_stars INTEGER NOT NULL DEFAULT 0,
      status TEXT NOT NULL DEFAULT 'pending',
      source TEXT NOT NULL DEFAULT 'spin',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      resolved_at TEXT NOT NULL DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS promos(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      code TEXT UNIQUE NOT NULL,
      promo_type TEXT NOT NULL DEFAULT 'discount',
      discount_percent INTEGER NOT NULL DEFAULT 0,
      spin_tickets INTEGER NOT NULL DEFAULT 0,
      max_uses INTEGER NOT NULL DEFAULT 0,
      uses INTEGER NOT NULL DEFAULT 0,
      active INTEGER NOT NULL DEFAULT 1,
      expires_at TEXT NOT NULL DEFAULT '',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS promo_redemptions(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      promo_id INTEGER NOT NULL,
      telegram_id INTEGER NOT NULL,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(promo_id, telegram_id)
    );
    CREATE TABLE IF NOT EXISTS referrals(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      referrer_id INTEGER NOT NULL,
      referred_id INTEGER UNIQUE NOT NULL,
      rewarded INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """)
    # Lightweight SQLite migrations for the persistent Railway volume.
    user_cols = {r["name"] for r in await (await conn.execute("PRAGMA table_info(users)")).fetchall()}
    if "token" not in user_cols:
        await conn.execute("ALTER TABLE users ADD COLUMN token TEXT")
    users_without_token = await (await conn.execute(
        "SELECT telegram_id FROM users WHERE token IS NULL OR token=''"
    )).fetchall()
    for user_row in users_without_token:
        await ensure_user_token(conn, int(user_row["telegram_id"]))
    await conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_token ON users(token)")
    order_cols = {r["name"] for r in await (await conn.execute("PRAGMA table_info(orders)")).fetchall()}
    if "promo_code" not in order_cols:
        await conn.execute("ALTER TABLE orders ADD COLUMN promo_code TEXT NOT NULL DEFAULT ''")
    if "discount_percent" not in order_cols:
        await conn.execute("ALTER TABLE orders ADD COLUMN discount_percent INTEGER NOT NULL DEFAULT 0")
    if "telegram_charge_id" not in order_cols:
        await conn.execute("ALTER TABLE orders ADD COLUMN telegram_charge_id TEXT NOT NULL DEFAULT ''")
    promo_cols = {r["name"] for r in await (await conn.execute("PRAGMA table_info(promos)")).fetchall()}
    if "promo_type" not in promo_cols:
        await conn.execute("ALTER TABLE promos ADD COLUMN promo_type TEXT NOT NULL DEFAULT 'discount'")
    if "spin_tickets" not in promo_cols:
        await conn.execute("ALTER TABLE promos ADD COLUMN spin_tickets INTEGER NOT NULL DEFAULT 0")
    # Rescue legacy SPIN promos created before spin_tickets was stored reliably.
    await conn.execute("UPDATE promos SET spin_tickets=1 WHERE lower(promo_type)='spin' AND COALESCE(spin_tickets,0)<=0")
    await conn.execute(
        "CREATE TABLE IF NOT EXISTS promo_redemptions("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "promo_id INTEGER NOT NULL,"
        "telegram_id INTEGER NOT NULL,"
        "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,"
        "UNIQUE(promo_id, telegram_id))"
    )
    await conn.execute(
        "CREATE TABLE IF NOT EXISTS inventory_items("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "telegram_id INTEGER NOT NULL,"
        "reward_name TEXT NOT NULL,"
        "reward_tier TEXT NOT NULL,"
        "sell_shr INTEGER NOT NULL DEFAULT 0,"
        "value_stars INTEGER NOT NULL DEFAULT 0,"
        "status TEXT NOT NULL DEFAULT 'pending',"
        "source TEXT NOT NULL DEFAULT 'spin',"
        "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,"
        "resolved_at TEXT NOT NULL DEFAULT '')"
    )
    for reward in SPIN_REWARDS:
        await conn.execute(
            "UPDATE inventory_items SET sell_shr=?, value_stars=? "
            "WHERE reward_name=? AND status IN ('pending','saved')",
            (int(reward["value_stars"]), int(reward["value_stars"]), reward["name"])
        )
    spin_cols = {r["name"] for r in await (await conn.execute("PRAGMA table_info(spin_history)")).fetchall()}
    if "source" not in spin_cols:
        await conn.execute("ALTER TABLE spin_history ADD COLUMN source TEXT NOT NULL DEFAULT 'free'")
    reset = await (await conn.execute("SELECT value FROM settings WHERE key='bonus_tickets_v1'")).fetchone()
    if not reset:
        await conn.execute("UPDATE spin_state SET tickets=0")
        await conn.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('bonus_tickets_v1','1')")
    row = await (await conn.execute("SELECT COUNT(*) c FROM products")).fetchone()
    if row["c"] == 0:
        items = [
          ("Metro Royale","Metro Starter Kit","Стартовый набор экипировки для Metro Royale.",490,250,"",1),
          ("Metro Royale","Набор брони","Комплект экипировки. Состав уточняется в заказе.",790,390,"",2),
          ("Буст аккаунта","Буст ранга","Прокачка ранга. Итоговые параметры согласуются после заказа.",1490,700,"",3),
          ("Квесты","Выполнение 5 квестов","Выполнение пяти выбранных заданий.",590,300,"",4),
          ("Фарм","Фарм ресурсов","Фарм ресурсов Metro Royale по согласованному объёму.",990,480,"",5),
        ]
        await conn.executemany("INSERT INTO products(category,name,description,price,stars_price,image,sort_order) VALUES(?,?,?,?,?,?,?)", items)
    await conn.commit()
    await conn.close()


def verify_init_data(init_data: str) -> dict:
    if not init_data:
        raise HTTPException(401, "Откройте приложение через Telegram")
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received = pairs.pop("hash", "")
    if not received:
        raise HTTPException(401, "Некорректная Telegram-авторизация")
    auth_date = int(pairs.get("auth_date", "0") or 0)
    if abs(int(time.time()) - auth_date) > 86400:
        raise HTTPException(401, "Сессия Telegram устарела. Откройте Mini App заново")
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    calculated = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated, received):
        raise HTTPException(401, "Подпись Telegram не прошла проверку")
    try:
        user = json.loads(pairs.get("user", "{}"))
    except json.JSONDecodeError:
        raise HTTPException(401, "Некорректные данные пользователя")
    if not user.get("id"):
        raise HTTPException(401, "Не удалось определить пользователя Telegram")
    return user


async def current_user(init_data: str | None):
    user = verify_init_data(init_data or "")
    async with db_write_lock:
        conn = await db()
        try:
            await conn.execute(
              "INSERT INTO users(telegram_id,username,first_name) VALUES(?,?,?) "
              "ON CONFLICT(telegram_id) DO UPDATE SET username=excluded.username, first_name=excluded.first_name",
              (int(user["id"]), user.get("username"), user.get("first_name"))
            )
            token = await ensure_user_token(conn, int(user["id"]))
            await conn.commit()
        finally:
            await conn.close()
    user["token"] = token
    return user


async def tg(method: str, payload: dict | None = None):
    async with httpx.AsyncClient(timeout=35) as client:
        r = await client.post(f"{TG_API}/{method}", json=payload or {})
        data = r.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram {method}: {data}")
        return data.get("result")


async def announce_top_drop(user_id: int, reward: dict):
    try:
        conn = await db()
        try:
            row = await (await conn.execute(
                "SELECT username,first_name,token FROM users WHERE telegram_id=?",
                (user_id,)
            )).fetchone()
        finally:
            await conn.close()
        if row and row["username"]:
            nick = "@" + row["username"]
        elif row and row["first_name"]:
            nick = row["first_name"]
        else:
            nick = row["token"] if row and row["token"] else "Игрок Шрексича"
        stamp = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")
        base = random.choice(TOP_DROP_MESSAGES).format(
            nick=nick, item=reward["name"], rarity=reward["tier"]
        )
        text = f"{base}\n\n🕒 {stamp}"
        await tg("sendMessage", {"chat_id":TOP_DROP_CHAT,"text":text})
    except Exception as e:
        print("top drop announce error:", repr(e), flush=True)


def keyboard(user_id: int):
    rows = [[{"text":"🛒 Открыть магазин","web_app":{"url":BASE_URL}}]]
    rows.append([{"text":"📦 Мои заказы","web_app":{"url":BASE_URL + "/?tab=orders"}},
                 {"text":"💬 Поддержка","web_app":{"url":BASE_URL + "/?tab=support"}}])
    rows.append([{"text":"📢 Новости","url":"https://t.me/shreksi4PubgNEWS"},
                 {"text":"💬 Наш чат","url":"https://t.me/chatshreksi4"}])
    if user_id == OWNER_ID:
        rows.append([{"text":"⚙️ Админ-панель","web_app":{"url":ADMIN_URL}}])
    return {"inline_keyboard": rows}


async def send_start(chat_id: int, user_id: int):
    await tg("sendMessage", {
      "chat_id": chat_id,
      "parse_mode": "HTML",
      "text": f"<b>Добро пожаловать в {html.escape(APP_NAME)}</b>\n\nМагазин товаров и услуг для PUBG Mobile • Metro Royale.\n\nВыберите нужный раздел:",
      "reply_markup": keyboard(user_id)
    })


async def register_bot_user(user: dict):
    if not user.get("id"):
        return
    async with db_write_lock:
        conn = await db()
        try:
            await conn.execute(
                "INSERT INTO users(telegram_id,username,first_name) VALUES(?,?,?) "
                "ON CONFLICT(telegram_id) DO UPDATE SET username=excluded.username, first_name=excluded.first_name",
                (int(user["id"]), user.get("username"), user.get("first_name"))
            )
            await ensure_user_token(conn, int(user["id"]))
            await conn.commit()
        finally:
            await conn.close()


async def register_referral(referred_id: int, referrer_token: str):
    if not referred_id or not referrer_token:
        return
    async with db_write_lock:
        conn = await db()
        try:
            referrer = await telegram_id_by_token(conn, referrer_token)
            if referrer and int(referrer["telegram_id"]) != int(referred_id):
                await conn.execute(
                    "INSERT OR IGNORE INTO referrals(referrer_id,referred_id) VALUES(?,?)",
                    (int(referrer["telegram_id"]), int(referred_id))
                )
                await conn.commit()
        finally:
            await conn.close()


async def referral_link(user_id: int):
    global bot_username
    conn = await db()
    try:
        token = await ensure_user_token(conn, int(user_id))
        await conn.commit()
    finally:
        await conn.close()
    if not bot_username:
        try:
            info = await tg("getMe")
            bot_username = info.get("username", "")
        except Exception:
            bot_username = ""
    return f"https://t.me/{bot_username}?start=ref_{token}" if bot_username else BASE_URL


async def send_token(chat_id: int, user_id: int):
    conn = await db()
    try:
        token = await ensure_user_token(conn, int(user_id))
        await conn.commit()
    finally:
        await conn.close()
    await tg("sendMessage", {
        "chat_id":chat_id,
        "parse_mode":"HTML",
        "text":f"🎫 <b>Ваш жетон Шрексича</b>\n\n<code>{html.escape(token)}</code>\n\nПо этому жетону поддержка может найти ваш аккаунт. Для связи с поддержкой достаточно этого жетона."
    })


async def send_faq(chat_id: int):
    text = (
        "<b>Частые вопросы</b>\n\n"
        "⭐ <b>Оплата:</b> покупки оплачиваются Telegram Stars прямо внутри Mini App.\n"
        "📦 <b>Заказы:</b> статус смотрите в разделе «Заказы».\n"
        "🎰 <b>SPIN:</b> 1 бесплатное вращение за 24 часа + бонусные билеты от админа и рефералов.\n"
        "🎟 <b>Промокоды:</b> вводятся при оформлении заказа и уменьшают цену в Stars.\n"
        "👥 <b>Рефералы:</b> после первой оплаченной покупки приглашённого вы получаете 1 бонусный SPIN-билет и 3 SHR.\n"
        "💬 <b>Поддержка:</b> создайте обращение в Mini App или напишите в нашем чате."
    )
    await tg("sendMessage", {"chat_id":chat_id,"parse_mode":"HTML","text":text,"reply_markup":keyboard(chat_id)})


async def send_referral(chat_id: int, user_id: int):
    link = await referral_link(user_id)
    await tg("sendMessage", {
        "chat_id":chat_id,
        "parse_mode":"HTML",
        "text":f"<b>Ваша реферальная ссылка</b>\n\n<code>{html.escape(link)}</code>\n\nЗа первую оплаченную покупку друга: <b>+1 SPIN-билет и +3 SHR</b>."
    })


async def answer_question(chat_id: int, text: str):
    q = text.lower()
    if any(x in q for x in ("оплат", "stars", "звезд", "звёзд")):
        answer = "⭐ Оплата проходит Telegram Stars внутри Mini App. Откройте товар → создайте заказ → нажмите «Оплатить ⭐»."
    elif any(x in q for x in ("заказ", "статус", "где мой")):
        answer = "📦 Все ваши заказы и их статусы находятся в Mini App → «Заказы»."
    elif any(x in q for x in ("спин", "рулет", "билет")):
        answer = "🎰 Доступно 1 бесплатный SPIN за 24 часа. Дополнительные бонусные билеты можно получить от администратора или за рефералов."
    elif any(x in q for x in ("промо", "скидк", "купон")):
        answer = "🎟 Промокод вводится перед созданием заказа. Если он активен, цена в Stars пересчитается автоматически."
    elif any(x in q for x in ("рефер", "приглас", "друг")):
        link = await referral_link(chat_id)
        answer = f"👥 Ваша ссылка: {link}\nЗа первую оплаченную покупку приглашённого: +1 SPIN-билет и +3 SHR."
    else:
        answer = "Я могу подсказать по оплате, заказам, SPIN, промокодам и реферальной системе. Для полного списка отправьте /faq."
    await tg("sendMessage", {"chat_id":chat_id,"text":answer})


async def process_update(update: dict):
    global poll_offset
    poll_offset = max(poll_offset, int(update.get("update_id", 0)) + 1)
    msg = update.get("message") or {}
    user = msg.get("from") or {}
    text = (msg.get("text") or "").strip()

    if msg:
        await register_bot_user(user)

    if msg and text.startswith("/start"):
        parts = text.split(maxsplit=1)
        if len(parts) > 1 and parts[1].startswith("ref_"):
            try:
                await register_referral(int(user.get("id", 0)), parts[1][4:])
            except Exception:
                pass
        await send_start(int(msg["chat"]["id"]), int(user.get("id", 0)))
        return
    if msg and text.startswith("/shop"):
        await send_start(int(msg["chat"]["id"]), int(user.get("id", 0)))
        return
    if msg and (text.startswith("/faq") or text.startswith("/help")):
        await send_faq(int(msg["chat"]["id"]))
        return
    if msg and text.startswith("/ref"):
        await send_referral(int(msg["chat"]["id"]), int(user.get("id", 0)))
        return
    if msg and text.startswith("/token"):
        await send_token(int(msg["chat"]["id"]), int(user.get("id", 0)))
        return

    pq = update.get("pre_checkout_query")
    if pq:
        ok = False
        error_message = "Платёж не соответствует заказу"
        payload = pq.get("invoice_payload", "")
        try:
            _, oid, uid = payload.split(":")
            conn = await db()
            try:
                row = await (await conn.execute(
                    "SELECT * FROM orders WHERE id=? AND telegram_id=?",
                    (int(oid), int(uid))
                )).fetchone()
                ok = bool(
                    row and row["status"] == "Ожидает оплаты"
                    and pq.get("currency") == "XTR"
                    and int(pq.get("total_amount",0)) == int(row["stars_amount"])
                )
                if ok and row["promo_code"]:
                    promo = await (await conn.execute(
                        "SELECT * FROM promos WHERE code=? AND active=1 AND COALESCE(discount_percent,0)>0 "
                        "AND (max_uses=0 OR uses<max_uses) "
                        "AND (expires_at='' OR datetime(expires_at)>datetime('now'))",
                        (row["promo_code"],)
                    )).fetchone()
                    redeemed = None
                    if promo:
                        redeemed = await (await conn.execute(
                            "SELECT 1 FROM promo_redemptions WHERE promo_id=? AND telegram_id=?",
                            (promo["id"], int(uid))
                        )).fetchone()
                    if not promo or redeemed:
                        ok = False
                        error_message = "Промокод истёк, закончился или уже использован"
            finally:
                await conn.close()
        except Exception:
            ok = False
        await tg("answerPreCheckoutQuery", {
            "pre_checkout_query_id":pq["id"],
            "ok":ok,
            "error_message":None if ok else error_message
        })
        return

    sp = msg.get("successful_payment")
    if sp:
        payload = sp.get("invoice_payload", "")
        try:
            _, oid, uid = payload.split(":")
            charge_id = sp.get("telegram_payment_charge_id", "")
            async with db_write_lock:
                conn = await db()
                try:
                    await conn.execute("BEGIN IMMEDIATE")
                    row = await (await conn.execute("SELECT * FROM orders WHERE id=? AND telegram_id=?", (int(oid), int(uid)))).fetchone()
                    if not row:
                        await conn.rollback()
                        return
                    if row["telegram_charge_id"]:
                        await conn.rollback()
                        return
                    await conn.execute(
                        "UPDATE orders SET status='Оплачен',payment_method='Telegram Stars',telegram_charge_id=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                        (charge_id, int(oid))
                    )
                    if row["promo_code"]:
                        promo = await (await conn.execute(
                            "SELECT id FROM promos WHERE code=? AND COALESCE(discount_percent,0)>0",
                            (row["promo_code"],)
                        )).fetchone()
                        if promo:
                            cur = await conn.execute(
                                "INSERT OR IGNORE INTO promo_redemptions(promo_id,telegram_id) VALUES(?,?)",
                                (promo["id"],int(uid))
                            )
                            if cur.rowcount:
                                await conn.execute("UPDATE promos SET uses=uses+1 WHERE id=?", (promo["id"],))
                    ref = await (await conn.execute(
                        "SELECT * FROM referrals WHERE referred_id=? AND rewarded=0",
                        (int(uid),)
                    )).fetchone()
                    if ref:
                        await conn.execute("UPDATE referrals SET rewarded=1 WHERE id=?", (ref["id"],))
                        await conn.execute(
                            "INSERT OR IGNORE INTO spin_state(telegram_id,tickets,last_free_spin,upgrade_points) VALUES(?,0,0,0)",
                            (ref["referrer_id"],)
                        )
                        await conn.execute(
                            "UPDATE spin_state SET tickets=tickets+1,upgrade_points=upgrade_points+3 WHERE telegram_id=?",
                            (ref["referrer_id"],)
                        )
                    await conn.commit()
                finally:
                    await conn.close()
        except Exception as e:
            print("payment processing error:", repr(e), flush=True)
        return

    if msg and text and not text.startswith("/"):
        await answer_question(int(msg["chat"]["id"]), text)


async def polling():
    global poll_offset, bot_username
    try:
        await tg("deleteWebhook", {"drop_pending_updates":False})
        info = await tg("getMe")
        bot_username = info.get("username", "")
        if BASE_URL:
            await tg("setChatMenuButton", {"menu_button":{"type":"web_app","text":"Открыть магазин","web_app":{"url":BASE_URL}}})
        await tg("setMyCommands", {"commands":[
          {"command":"start","description":"Главное меню"},
          {"command":"shop","description":"Открыть магазин"},
          {"command":"faq","description":"Ответы на вопросы"},
          {"command":"ref","description":"Реферальная ссылка"},
          {"command":"token","description":"Мой жетон"},
          {"command":"help","description":"Помощь"}
        ]})
    except Exception as e:
        print("telegram init:", repr(e), flush=True)
    while True:
        try:
            updates = await tg("getUpdates", {"offset":poll_offset,"timeout":25,"allowed_updates":["message","pre_checkout_query"]})
            for update in updates or []:
                try:
                    await process_update(update)
                except Exception as e:
                    print("update error:", repr(e), flush=True)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print("polling error:", repr(e), flush=True)
            await asyncio.sleep(3)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    task = asyncio.create_task(polling())
    yield
    task.cancel()
    try:
        await task
    except BaseException:
        pass


app = FastAPI(title="Shreksich Shop", lifespan=lifespan)


class OrderIn(BaseModel):
    product_id: int
    uid: str = Field(min_length=3, max_length=64)
    nickname: str = Field(default="", max_length=64)
    comment: str = Field(default="", max_length=1000)
    promo_code: str = Field(default="", max_length=32)


class TicketIn(BaseModel):
    category: str = Field(default="Другое", max_length=80)
    message: str = Field(min_length=3, max_length=2000)


class StatusIn(BaseModel):
    status: str


class AdminGrantIn(BaseModel):
    telegram_id: int
    amount: int = Field(ge=1, le=100)


class AdminRewardIn(BaseModel):
    token: str = Field(min_length=4, max_length=32)
    tickets: int = Field(default=0, ge=0, le=100)
    upgrade_points: int = Field(default=0, ge=0, le=10000)


class BroadcastIn(BaseModel):
    message: str = Field(min_length=1, max_length=3000)


class PromoCreateIn(BaseModel):
    code: str = Field(min_length=3, max_length=32)
    promo_type: str = Field(default="discount", max_length=16)
    discount_percent: int = Field(default=0, ge=0, le=90)
    spin_tickets: int = Field(default=0, ge=0, le=100)
    max_uses: int = Field(default=0, ge=0, le=100000)
    expires_at: str = Field(default="", max_length=32)


class SpinPromoIn(BaseModel):
    code: str = Field(min_length=3, max_length=32)


class InventoryResolveIn(BaseModel):
    action: str = Field(min_length=4, max_length=8)


class PromoToggleIn(BaseModel):
    active: bool


class ProductAdminIn(BaseModel):
    category: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1200)
    stars_price: int = Field(ge=1, le=1000000)
    active: bool = True
    sort_order: int = Field(default=0, ge=0, le=10000)


class AdminReplyIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class AdminMessageIn(BaseModel):
    token: str = Field(min_length=4, max_length=32)
    message: str = Field(min_length=1, max_length=3000)


@app.get("/health")
async def health():
    return {"status":"ok","app":APP_NAME}


@app.get("/api/catalog")
async def catalog():
    conn = await db()
    rows = await (await conn.execute("SELECT * FROM products WHERE active=1 ORDER BY sort_order,id")).fetchall()
    await conn.close()
    return [dict(r) for r in rows]


@app.get("/api/me")
async def me(x_telegram_init_data: str | None = Header(default=None)):
    u = await current_user(x_telegram_init_data)
    return {"token":u["token"],"first_name":u.get("first_name"),"username":u.get("username"),"owner":int(u["id"])==OWNER_ID}


@app.post("/api/orders")
async def create_order(body: OrderIn, x_telegram_init_data: str | None = Header(default=None)):
    u = await current_user(x_telegram_init_data)
    promo_code = body.promo_code.strip().upper()
    async with db_write_lock:
        conn = await db()
        try:
            await conn.execute("BEGIN IMMEDIATE")
            p = await (await conn.execute("SELECT * FROM products WHERE id=? AND active=1",(body.product_id,))).fetchone()
            if not p:
                await conn.rollback()
                raise HTTPException(404,"Товар не найден")

            discount = 0
            if promo_code:
                promo = await (await conn.execute(
                    "SELECT * FROM promos WHERE code=? AND active=1 AND COALESCE(discount_percent,0)>0 "
                    "AND (max_uses=0 OR uses<max_uses) "
                    "AND (expires_at='' OR datetime(expires_at)>datetime('now'))",
                    (promo_code,)
                )).fetchone()
                if not promo:
                    await conn.rollback()
                    raise HTTPException(400,"Промокод на скидку недействителен, закончился или истёк")
                redeemed = await (await conn.execute(
                    "SELECT 1 FROM promo_redemptions WHERE promo_id=? AND telegram_id=?",
                    (promo["id"],int(u["id"]))
                )).fetchone()
                if redeemed:
                    await conn.rollback()
                    raise HTTPException(409,"Вы уже использовали этот промокод")
                discount = int(promo["discount_percent"])

            stars_amount = max(1, (int(p["stars_price"]) * (100 - discount) + 99) // 100)
            last = await (await conn.execute("SELECT COALESCE(MAX(number),10499) n FROM orders")).fetchone()
            number = int(last["n"]) + 1
            cur = await conn.execute(
              "INSERT INTO orders(number,telegram_id,product_id,product_name,amount,stars_amount,uid,nickname,comment,promo_code,discount_percent) "
              "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
              (number,int(u["id"]),p["id"],p["name"],p["price"],stars_amount,body.uid,body.nickname,body.comment,promo_code,discount)
            )
            oid = cur.lastrowid
            await conn.commit()
        finally:
            await conn.close()
    return {
      "id":oid,"number":number,"status":"Ожидает оплаты",
      "stars_amount":stars_amount,"original_stars_amount":int(p["stars_price"]),
      "promo_code":promo_code,"discount_percent":discount
    }


@app.post("/api/promo/check")
async def promo_check(body: OrderIn, x_telegram_init_data: str | None = Header(default=None)):
    u = await current_user(x_telegram_init_data)
    code = body.promo_code.strip().upper()
    if not code:
        raise HTTPException(400,"Введите промокод")
    conn = await db()
    try:
        p = await (await conn.execute("SELECT * FROM products WHERE id=? AND active=1",(body.product_id,))).fetchone()
        promo = await (await conn.execute(
            "SELECT * FROM promos WHERE code=? AND active=1 AND COALESCE(discount_percent,0)>0 "
            "AND (max_uses=0 OR uses<max_uses) "
            "AND (expires_at='' OR datetime(expires_at)>datetime('now'))",
            (code,)
        )).fetchone()
        redeemed = None
        if promo:
            redeemed = await (await conn.execute(
                "SELECT 1 FROM promo_redemptions WHERE promo_id=? AND telegram_id=?",
                (promo["id"],int(u["id"]))
            )).fetchone()
    finally:
        await conn.close()
    if not p:
        raise HTTPException(404,"Товар не найден")
    if not promo:
        raise HTTPException(400,"Промокод на скидку недействителен, закончился или истёк")
    if redeemed:
        raise HTTPException(409,"Вы уже использовали этот промокод")
    discount = int(promo["discount_percent"])
    final_stars = max(1, (int(p["stars_price"]) * (100-discount) + 99)//100)
    return {"code":code,"discount_percent":discount,"original_stars":int(p["stars_price"]),"final_stars":final_stars}


@app.get("/api/orders")
async def orders(x_telegram_init_data: str | None = Header(default=None)):
    u = await current_user(x_telegram_init_data)
    conn = await db()
    rows = await (await conn.execute("SELECT * FROM orders WHERE telegram_id=? ORDER BY id DESC",(int(u["id"]),))).fetchall()
    await conn.close()
    return [dict(r) for r in rows]


@app.post("/api/orders/{order_id}/stars")
async def stars(order_id: int, x_telegram_init_data: str | None = Header(default=None)):
    u = await current_user(x_telegram_init_data)
    conn = await db()
    row = await (await conn.execute("SELECT * FROM orders WHERE id=? AND telegram_id=?",(order_id,int(u["id"])))).fetchone()
    await conn.close()
    if not row: raise HTTPException(404,"Заказ не найден")
    if row["status"] != "Ожидает оплаты": raise HTTPException(409,"Заказ уже обработан")
    if int(row["stars_amount"]) <= 0: raise HTTPException(400,"Оплата Stars для этого товара недоступна")
    if row["promo_code"]:
        conn = await db()
        try:
            promo = await (await conn.execute(
                "SELECT * FROM promos WHERE code=? AND active=1 AND COALESCE(discount_percent,0)>0 "
                "AND (max_uses=0 OR uses<max_uses) "
                "AND (expires_at='' OR datetime(expires_at)>datetime('now'))",
                (row["promo_code"],)
            )).fetchone()
            redeemed = None
            if promo:
                redeemed = await (await conn.execute(
                    "SELECT 1 FROM promo_redemptions WHERE promo_id=? AND telegram_id=?",
                    (promo["id"],int(u["id"]))
                )).fetchone()
        finally:
            await conn.close()
        if not promo:
            raise HTTPException(409,"Промокод истёк или его лимит закончился. Создайте новый заказ.")
        if redeemed:
            raise HTTPException(409,"Этот промокод уже был использован. Создайте новый заказ.")
    link = await tg("createInvoiceLink", {
      "title":f"Заказ #{row['number']}","description":row["product_name"],
      "payload":f"order:{row['id']}:{u['id']}","provider_token":"","currency":"XTR",
      "prices":[{"label":row["product_name"],"amount":int(row["stars_amount"])}]
    })
    return {"url":link}


@app.post("/api/orders/{order_id}/manual")
async def manual(order_id: int, x_telegram_init_data: str | None = Header(default=None)):
    raise HTTPException(410,"Ручная оплата отключена. Используйте Telegram Stars.")


@app.get("/api/spin/state")
async def spin_state(x_telegram_init_data: str | None = Header(default=None)):
    u = await current_user(x_telegram_init_data)
    uid = int(u["id"])
    async with db_write_lock:
        conn = await db()
        try:
            await conn.execute("INSERT OR IGNORE INTO spin_state(telegram_id,tickets,last_free_spin,upgrade_points) VALUES(?,0,0,0)",(uid,))
            await conn.commit()
            state = await (await conn.execute("SELECT * FROM spin_state WHERE telegram_id=?",(uid,))).fetchone()
            history = await (await conn.execute(
                "SELECT reward_name,reward_tier,points,source,created_at FROM spin_history WHERE telegram_id=? ORDER BY id DESC LIMIT 5",
                (uid,)
            )).fetchall()
            used_row = await (await conn.execute(
                "SELECT COUNT(*) c, MIN(strftime('%s', created_at)) first_ts FROM spin_history "
                "WHERE telegram_id=? AND source='free' AND created_at >= datetime('now','-24 hours')",
                (uid,)
            )).fetchone()
        finally:
            await conn.close()
    used = int(used_row["c"] or 0)
    free_remaining = max(0, MAX_FREE_SPINS_24H - used)
    bonus_tickets = max(0, int(state["tickets"] or 0))
    next_reset = 0
    if free_remaining == 0 and used_row["first_ts"]:
        next_reset = max(0, int(used_row["first_ts"]) + 86400 - int(time.time()))
    return {
      "free_remaining":free_remaining,
      "max_free_spins":MAX_FREE_SPINS_24H,
      "bonus_tickets":bonus_tickets,
      "remaining_spins":free_remaining + bonus_tickets,
      "shr":int(state["upgrade_points"]),
      "upgrade_points":int(state["upgrade_points"]),
      "next_reset_seconds":next_reset,
      "history":[dict(x) for x in history],
      "upgrade_rewards":SHR_REWARDS,
      "tier_chances":SPIN_TIER_CHANCES,
      "rewards":[{"name":x["name"],"tier":x["tier"],"value_stars":x["value_stars"]} for x in SPIN_REWARDS]
    }


@app.get("/api/spin/history")
async def spin_history_full(
    period: str = "all",
    tier: str = "ALL",
    from_at: str = "",
    to_at: str = "",
    x_telegram_init_data: str | None = Header(default=None)
):
    u = await current_user(x_telegram_init_data)
    uid = int(u["id"])
    period = (period or "all").strip().lower()
    tier = (tier or "ALL").strip().upper()
    allowed_periods = {"all","24h","7d","30d","90d","custom"}
    allowed_tiers = {"ALL","COMMON","RARE","EPIC","LEGENDARY","MYTHIC"}
    if period not in allowed_periods:
        raise HTTPException(400,"Некорректный период")
    if tier not in allowed_tiers:
        raise HTTPException(400,"Некорректная редкость")

    where = ["telegram_id=?"]
    args = [uid]
    if tier != "ALL":
        where.append("reward_tier=?")
        args.append(tier)

    period_sql = {"24h":"-24 hours","7d":"-7 days","30d":"-30 days","90d":"-90 days"}
    if period in period_sql:
        where.append("created_at >= datetime('now', ?)")
        args.append(period_sql[period])
    elif period == "custom":
        def normalize_dt(value: str) -> str:
            value = (value or "").strip()
            if not value:
                return ""
            value = value.replace("T"," ")
            if len(value) == 16:
                value += ":00"
            try:
                datetime.strptime(value,"%Y-%m-%d %H:%M:%S")
            except ValueError:
                raise HTTPException(400,"Неверный формат даты")
            return value
        start = normalize_dt(from_at)
        end = normalize_dt(to_at)
        if start:
            where.append("created_at >= ?")
            args.append(start)
        if end:
            where.append("created_at <= ?")
            args.append(end)

    conn = await db()
    try:
        rows = await (await conn.execute(
            "SELECT id,reward_name,reward_tier,points,source,created_at FROM spin_history WHERE "
            + " AND ".join(where) + " ORDER BY id DESC LIMIT 500",
            tuple(args)
        )).fetchall()
    finally:
        await conn.close()
    return {"items":[dict(x) for x in rows],"count":len(rows),"period":period,"tier":tier}


@app.post("/api/spin/free")
async def spin_free(x_telegram_init_data: str | None = Header(default=None)):
    u = await current_user(x_telegram_init_data)
    uid = int(u["id"])
    async with db_write_lock:
        conn = await db()
        try:
            await conn.execute("BEGIN IMMEDIATE")
            await conn.execute("INSERT OR IGNORE INTO spin_state(telegram_id,tickets,last_free_spin,upgrade_points) VALUES(?,0,0,0)",(uid,))
            state = await (await conn.execute("SELECT * FROM spin_state WHERE telegram_id=?",(uid,))).fetchone()
            used_row = await (await conn.execute(
                "SELECT COUNT(*) c FROM spin_history WHERE telegram_id=? AND source='free' AND created_at >= datetime('now','-24 hours')",
                (uid,)
            )).fetchone()
            used = int(used_row["c"] or 0)
            source = "free"
            if used >= MAX_FREE_SPINS_24H:
                if int(state["tickets"] or 0) <= 0:
                    await conn.rollback()
                    raise HTTPException(429,"Бесплатный SPIN уже использован. Следующее вращение будет доступно позже.")
                source = "ticket"
                await conn.execute("UPDATE spin_state SET tickets=tickets-1 WHERE telegram_id=?",(uid,))

            reward = random.choices(SPIN_REWARDS, weights=[x["weight"] for x in SPIN_REWARDS], k=1)[0]
            await conn.execute(
                "INSERT INTO spin_history(telegram_id,reward_name,reward_tier,points,source) VALUES(?,?,?,?,?)",
                (uid,reward["name"],reward["tier"],int(reward["value_stars"]),source)
            )
            inv = await conn.execute(
                "INSERT INTO inventory_items(telegram_id,reward_name,reward_tier,sell_shr,value_stars,status,source) "
                "VALUES(?,?,?,?,?,'pending','spin')",
                (uid,reward["name"],reward["tier"],int(reward["value_stars"]),int(reward["value_stars"]))
            )
            inventory_item_id = inv.lastrowid
            await conn.commit()
            state = await (await conn.execute("SELECT * FROM spin_state WHERE telegram_id=?",(uid,))).fetchone()
        finally:
            await conn.close()

    free_remaining = max(0, MAX_FREE_SPINS_24H - used - (1 if source=="free" else 0))
    if reward["tier"] in ("LEGENDARY","MYTHIC"):
        asyncio.create_task(announce_top_drop(uid, reward))
    return {
      "reward":reward,"source":source,
      "inventory_item_id":inventory_item_id,
      "sell_shr":int(reward["value_stars"]),
      "free_remaining":free_remaining,
      "bonus_tickets":int(state["tickets"] or 0),
      "remaining_spins":free_remaining + int(state["tickets"] or 0),
      "shr":int(state["upgrade_points"]),
      "upgrade_points":int(state["upgrade_points"])
    }


@app.post("/api/spin/promo")
async def spin_promo(body: SpinPromoIn, x_telegram_init_data: str | None = Header(default=None)):
    u = await current_user(x_telegram_init_data)
    uid = int(u["id"])
    code = body.code.strip().upper()
    async with db_write_lock:
        conn = await db()
        try:
            await conn.execute("BEGIN IMMEDIATE")
            promo = await (await conn.execute(
                "SELECT * FROM promos WHERE code=? AND active=1 "
                "AND (lower(COALESCE(promo_type,''))='spin' OR COALESCE(spin_tickets,0)>0) "
                "AND (max_uses=0 OR uses<max_uses) "
                "AND (expires_at='' OR datetime(expires_at)>datetime('now'))",
                (code,)
            )).fetchone()
            if not promo:
                await conn.rollback()
                raise HTTPException(400,"SPIN-промокод недействителен, закончился или истёк")
            redeemed = await (await conn.execute(
                "SELECT 1 FROM promo_redemptions WHERE promo_id=? AND telegram_id=?",
                (promo["id"],uid)
            )).fetchone()
            if redeemed:
                await conn.rollback()
                raise HTTPException(409,"Вы уже активировали этот промокод")
            tickets = int(promo["spin_tickets"] or 0)
            if tickets <= 0 and str(promo["promo_type"] or "").lower()=="spin":
                tickets = 1
                await conn.execute("UPDATE promos SET spin_tickets=1 WHERE id=?",(promo["id"],))
            if tickets <= 0:
                await conn.rollback()
                raise HTTPException(400,"Этот промокод не выдаёт SPIN-билеты")
            await conn.execute(
                "INSERT OR IGNORE INTO spin_state(telegram_id,tickets,last_free_spin,upgrade_points) VALUES(?,0,0,0)",
                (uid,)
            )
            await conn.execute(
                "UPDATE spin_state SET tickets=tickets+? WHERE telegram_id=?",
                (tickets,uid)
            )
            await conn.execute(
                "INSERT INTO promo_redemptions(promo_id,telegram_id) VALUES(?,?)",
                (promo["id"],uid)
            )
            await conn.execute("UPDATE promos SET uses=uses+1 WHERE id=?",(promo["id"],))
            await conn.commit()
            state = await (await conn.execute("SELECT tickets FROM spin_state WHERE telegram_id=?",(uid,))).fetchone()
        finally:
            await conn.close()
    return {"ok":True,"code":code,"tickets_added":tickets,"bonus_tickets":int(state["tickets"] or 0)}


@app.get("/api/inventory")
async def inventory(x_telegram_init_data: str | None = Header(default=None)):
    u = await current_user(x_telegram_init_data)
    uid = int(u["id"])
    conn = await db()
    try:
        rows = await (await conn.execute(
            "SELECT id,reward_name,reward_tier,sell_shr,value_stars,status,source,created_at "
            "FROM inventory_items WHERE telegram_id=? AND status IN ('pending','saved') "
            "ORDER BY id DESC",
            (uid,)
        )).fetchall()
        state = await (await conn.execute(
            "SELECT upgrade_points FROM spin_state WHERE telegram_id=?",
            (uid,)
        )).fetchone()
    finally:
        await conn.close()
    return {
        "items":[dict(r) for r in rows],
        "shr":int(state["upgrade_points"] or 0) if state else 0
    }


@app.post("/api/inventory/{item_id}/resolve")
async def inventory_resolve(item_id: int, body: InventoryResolveIn, x_telegram_init_data: str | None = Header(default=None)):
    u = await current_user(x_telegram_init_data)
    uid = int(u["id"])
    action = body.action.strip().lower()
    if action not in ("save","sell"):
        raise HTTPException(400,"Действие: save или sell")
    async with db_write_lock:
        conn = await db()
        try:
            await conn.execute("BEGIN IMMEDIATE")
            item = await (await conn.execute(
                "SELECT * FROM inventory_items WHERE id=? AND telegram_id=?",
                (item_id,uid)
            )).fetchone()
            if not item:
                await conn.rollback()
                raise HTTPException(404,"Предмет не найден")
            if item["status"] == "sold":
                await conn.rollback()
                raise HTTPException(409,"Предмет уже продан")
            if action == "save":
                await conn.execute(
                    "UPDATE inventory_items SET status='saved',resolved_at=CURRENT_TIMESTAMP WHERE id=? AND telegram_id=?",
                    (item_id,uid)
                )
            else:
                await conn.execute("INSERT OR IGNORE INTO spin_state(telegram_id) VALUES(?)",(uid,))
                await conn.execute(
                    "UPDATE spin_state SET upgrade_points=upgrade_points+? WHERE telegram_id=?",
                    (int(item["sell_shr"]),uid)
                )
                await conn.execute(
                    "UPDATE inventory_items SET status='sold',resolved_at=CURRENT_TIMESTAMP WHERE id=? AND telegram_id=?",
                    (item_id,uid)
                )
            await conn.commit()
            state = await (await conn.execute(
                "SELECT upgrade_points FROM spin_state WHERE telegram_id=?",(uid,)
            )).fetchone()
        finally:
            await conn.close()
    return {
        "ok":True,
        "action":action,
        "item_id":item_id,
        "shr":int(state["upgrade_points"] or 0) if state else 0
    }


@app.get("/api/wins-feed")
async def wins_feed():
    conn = await db()
    try:
        rows = await (await conn.execute(
            "SELECT h.id,h.reward_name,h.reward_tier,h.created_at,"
            "CASE WHEN COALESCE(u.username,'')<>'' THEN '@'||u.username "
            "WHEN COALESCE(u.first_name,'')<>'' THEN u.first_name ELSE 'Игрок' END player "
            "FROM spin_history h LEFT JOIN users u ON u.telegram_id=h.telegram_id "
            "WHERE h.reward_tier IN ('LEGENDARY','MYTHIC') ORDER BY h.id DESC LIMIT 30"
        )).fetchall()
    finally:
        await conn.close()
    return [dict(r) for r in rows]


@app.get("/api/referral")
async def referral_info(x_telegram_init_data: str | None = Header(default=None)):
    u = await current_user(x_telegram_init_data)
    uid = int(u["id"])
    link = await referral_link(uid)
    conn = await db()
    try:
        row = await (await conn.execute(
            "SELECT COUNT(*) total,SUM(CASE WHEN rewarded=1 THEN 1 ELSE 0 END) rewarded FROM referrals WHERE referrer_id=?",
            (uid,)
        )).fetchone()
        state = await (await conn.execute("SELECT tickets,upgrade_points FROM spin_state WHERE telegram_id=?",(uid,))).fetchone()
    finally:
        await conn.close()
    return {
      "link":link,
      "invited":int(row["total"] or 0),
      "rewarded":int(row["rewarded"] or 0),
      "bonus_tickets":int(state["tickets"] or 0) if state else 0,
      "upgrade_points":int(state["upgrade_points"] or 0) if state else 0,
      "reward_text":"+1 бонусный SPIN-билет и +3 SHR за первую оплаченную покупку друга"
    }


class UpgradeClaimIn(BaseModel):
    points: int


@app.post("/api/upgrade/claim")
async def upgrade_claim(body: UpgradeClaimIn, x_telegram_init_data: str | None = Header(default=None)):
    u = await current_user(x_telegram_init_data)
    uid = int(u["id"])
    reward = next((x for x in SHR_REWARDS if int(x["points"]) == int(body.points)), None)
    if not reward:
        raise HTTPException(400,"Некорректная награда SHR")
    async with db_write_lock:
        conn = await db()
        try:
            await conn.execute("BEGIN IMMEDIATE")
            await conn.execute("INSERT OR IGNORE INTO spin_state(telegram_id) VALUES(?)",(uid,))
            state = await (await conn.execute("SELECT * FROM spin_state WHERE telegram_id=?",(uid,))).fetchone()
            if int(state["upgrade_points"]) < int(reward["points"]):
                await conn.rollback()
                raise HTTPException(409,"Недостаточно SHR")
            await conn.execute("UPDATE spin_state SET upgrade_points=upgrade_points-? WHERE telegram_id=?",(reward["points"],uid))
            await conn.execute("INSERT INTO upgrade_claims(telegram_id,reward_name,points_spent) VALUES(?,?,?)",(uid,reward["name"],reward["points"]))
            await conn.commit()
        finally:
            await conn.close()
    return {"ok":True,"reward":reward}


@app.post("/api/support")
async def support(body: TicketIn, x_telegram_init_data: str | None = Header(default=None)):
    u = await current_user(x_telegram_init_data)
    async with db_write_lock:
        conn = await db()
        try:
            cur = await conn.execute("INSERT INTO tickets(telegram_id,category,message) VALUES(?,?,?)",(int(u["id"]),body.category,body.message))
            await conn.commit()
            tid = cur.lastrowid
        finally:
            await conn.close()
    return {"id":tid,"status":"Открыт"}


async def run_broadcast(message: str):
    conn = await db()
    try:
        rows = await (await conn.execute("SELECT telegram_id FROM users ORDER BY created_at DESC LIMIT 5000")).fetchall()
    finally:
        await conn.close()
    sent = 0
    failed = 0
    for row in rows:
        try:
            await tg("sendMessage", {"chat_id":int(row["telegram_id"]),"text":message})
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.04)
    print(f"broadcast done sent={sent} failed={failed}", flush=True)


async def owner(init_data: str | None):
    u = await current_user(init_data)
    if int(u["id"]) != OWNER_ID: raise HTTPException(403,"Нет доступа")
    return u


@app.get("/api/admin/orders")
async def admin_orders(x_telegram_init_data: str | None = Header(default=None)):
    await owner(x_telegram_init_data)
    conn=await db()
    try:
        rows=await (await conn.execute(
            "SELECT o.*,u.token user_token FROM orders o "
            "LEFT JOIN users u ON u.telegram_id=o.telegram_id "
            "ORDER BY o.id DESC LIMIT 300"
        )).fetchall()
    finally:
        await conn.close()
    result=[]
    for r in rows:
        d=dict(r); d.pop("telegram_id",None); result.append(d)
    return result


@app.patch("/api/admin/orders/{order_id}")
async def admin_status(order_id:int, body:StatusIn, x_telegram_init_data: str | None = Header(default=None)):
    await owner(x_telegram_init_data)
    allowed={"Ожидает оплаты","Ожидает проверки оплаты","Оплачен","Принят","В работе","Ожидает клиента","Выполнен","Отменён","Возврат"}
    if body.status not in allowed: raise HTTPException(400,"Некорректный статус")
    async with db_write_lock:
        conn=await db()
        try:
            row=await (await conn.execute("SELECT * FROM orders WHERE id=?",(order_id,))).fetchone()
            if not row:
                raise HTTPException(404,"Заказ не найден")
            await conn.execute("UPDATE orders SET status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",(body.status,order_id))
            await conn.commit()
        finally:
            await conn.close()
    return {"ok":True,"status":body.status}


@app.get("/api/admin/spins")
async def admin_spins(x_telegram_init_data: str | None = Header(default=None)):
    await owner(x_telegram_init_data)
    conn=await db()
    try:
        rows=await (await conn.execute(
            "SELECT h.id,u.token user_token,h.reward_name,h.reward_tier,h.points,h.created_at "
            "FROM spin_history h LEFT JOIN users u ON u.telegram_id=h.telegram_id "
            "ORDER BY h.id DESC LIMIT 200"
        )).fetchall()
    finally:
        await conn.close()
    return [dict(r) for r in rows]


@app.get("/api/admin/upgrades")
async def admin_upgrades(x_telegram_init_data: str | None = Header(default=None)):
    await owner(x_telegram_init_data)
    conn=await db()
    try:
        rows=await (await conn.execute(
            "SELECT a.id,u.token user_token,a.reward_name,a.points_spent,a.created_at "
            "FROM upgrade_claims a LEFT JOIN users u ON u.telegram_id=a.telegram_id "
            "ORDER BY a.id DESC LIMIT 200"
        )).fetchall()
    finally:
        await conn.close()
    return [dict(r) for r in rows]


@app.get("/api/admin/tickets")
async def admin_tickets(x_telegram_init_data: str | None = Header(default=None)):
    await owner(x_telegram_init_data)
    conn=await db()
    try:
        rows=await (await conn.execute(
            "SELECT t.id,u.token user_token,t.category,t.message,t.status,t.created_at "
            "FROM tickets t LEFT JOIN users u ON u.telegram_id=t.telegram_id "
            "ORDER BY t.id DESC LIMIT 200"
        )).fetchall()
    finally:
        await conn.close()
    return [dict(r) for r in rows]


@app.get("/api/admin/stats")
async def admin_stats(x_telegram_init_data: str | None = Header(default=None)):
    await owner(x_telegram_init_data)
    conn = await db()
    try:
        users = await (await conn.execute("SELECT COUNT(*) c FROM users")).fetchone()
        orders = await (await conn.execute("SELECT COUNT(*) c FROM orders")).fetchone()
        paid = await (await conn.execute("SELECT COUNT(*) c,COALESCE(SUM(stars_amount),0) stars FROM orders WHERE telegram_charge_id<>''")).fetchone()
        open_tickets = await (await conn.execute("SELECT COUNT(*) c FROM tickets WHERE status NOT IN ('Закрыт','Закрыто')")).fetchone()
        promos = await (await conn.execute("SELECT COUNT(*) c FROM promos WHERE active=1")).fetchone()
        refs = await (await conn.execute("SELECT COUNT(*) c,SUM(CASE WHEN rewarded=1 THEN 1 ELSE 0 END) rewarded FROM referrals")).fetchone()
        today = await (await conn.execute("SELECT COUNT(*) c FROM orders WHERE created_at>=date('now')")).fetchone()
        top = await (await conn.execute(
            "SELECT product_name,COUNT(*) c FROM orders WHERE telegram_charge_id<>'' GROUP BY product_name ORDER BY c DESC LIMIT 1"
        )).fetchone()
    finally:
        await conn.close()
    return {
      "users":int(users["c"] or 0),"orders":int(orders["c"] or 0),
      "paid_orders":int(paid["c"] or 0),"stars_revenue":int(paid["stars"] or 0),
      "open_tickets":int(open_tickets["c"] or 0),"active_promos":int(promos["c"] or 0),
      "referrals":int(refs["c"] or 0),"rewarded_referrals":int(refs["rewarded"] or 0),
      "orders_today":int(today["c"] or 0),
      "top_product":top["product_name"] if top else ""
    }


@app.get("/api/admin/users")
async def admin_users(x_telegram_init_data: str | None = Header(default=None)):
    await owner(x_telegram_init_data)
    conn = await db()
    try:
        rows = await (await conn.execute(
            "SELECT u.token,u.username,u.first_name,u.created_at,"
            "COALESCE(s.tickets,0) tickets,COALESCE(s.upgrade_points,0) upgrade_points,"
            "(SELECT COUNT(*) FROM orders o WHERE o.telegram_id=u.telegram_id) orders_count,"
            "(SELECT COUNT(*) FROM referrals r WHERE r.referrer_id=u.telegram_id) referrals_count "
            "FROM users u LEFT JOIN spin_state s ON s.telegram_id=u.telegram_id "
            "ORDER BY u.created_at DESC LIMIT 1000"
        )).fetchall()
    finally:
        await conn.close()
    return [dict(r) for r in rows]


@app.post("/api/admin/rewards/grant")
async def admin_grant_rewards(body: AdminRewardIn, x_telegram_init_data: str | None = Header(default=None)):
    await owner(x_telegram_init_data)
    if body.tickets <= 0 and body.upgrade_points <= 0:
        raise HTTPException(400,"Укажите билеты или SHR")
    async with db_write_lock:
        conn = await db()
        try:
            user = await telegram_id_by_token(conn, body.token)
            if not user:
                raise HTTPException(404,"Пользователь с таким жетоном не найден")
            uid = int(user["telegram_id"])
            await conn.execute(
                "INSERT OR IGNORE INTO spin_state(telegram_id,tickets,last_free_spin,upgrade_points) VALUES(?,0,0,0)",
                (uid,)
            )
            await conn.execute(
                "UPDATE spin_state SET tickets=tickets+?,upgrade_points=upgrade_points+? WHERE telegram_id=?",
                (body.tickets,body.upgrade_points,uid)
            )
            await conn.commit()
        finally:
            await conn.close()
    return {"ok":True,"token":body.token.strip().upper(),"tickets_added":body.tickets,"upgrade_points_added":body.upgrade_points}


@app.get("/api/admin/promos")
async def admin_promos(x_telegram_init_data: str | None = Header(default=None)):
    await owner(x_telegram_init_data)
    conn=await db()
    try:
        rows=await (await conn.execute("SELECT * FROM promos ORDER BY id DESC LIMIT 500")).fetchall()
    finally:
        await conn.close()
    return [dict(r) for r in rows]


@app.post("/api/admin/promos")
async def admin_create_promo(body: PromoCreateIn, x_telegram_init_data: str | None = Header(default=None)):
    await owner(x_telegram_init_data)
    code=body.code.strip().upper()
    promo_type=body.promo_type.strip().lower()
    if not code.replace("_","").replace("-","").isalnum():
        raise HTTPException(400,"Код может содержать буквы, цифры, - и _")
    if promo_type not in ("discount","spin"):
        raise HTTPException(400,"Тип промокода: discount или spin")
    if promo_type=="discount" and body.discount_percent<=0:
        raise HTTPException(400,"Для скидочного промокода укажите процент скидки")
    if promo_type=="spin" and body.spin_tickets<=0:
        raise HTTPException(400,"Для SPIN-промокода укажите количество билетов")
    async with db_write_lock:
        conn=await db()
        try:
            try:
                cur=await conn.execute(
                    "INSERT INTO promos(code,promo_type,discount_percent,spin_tickets,max_uses,expires_at) VALUES(?,?,?,?,?,?)",
                    (code,promo_type,body.discount_percent if promo_type=="discount" else 0,
                     body.spin_tickets if promo_type=="spin" else 0,
                     body.max_uses,body.expires_at.strip())
                )
                await conn.commit()
            except Exception as e:
                if "UNIQUE" in str(e).upper():
                    raise HTTPException(409,"Такой промокод уже существует")
                raise
        finally:
            await conn.close()
    return {"ok":True,"id":cur.lastrowid,"code":code,"promo_type":promo_type}


@app.patch("/api/admin/promos/{promo_id}")
async def admin_toggle_promo(promo_id:int, body:PromoToggleIn, x_telegram_init_data: str | None = Header(default=None)):
    await owner(x_telegram_init_data)
    async with db_write_lock:
        conn=await db()
        try:
            cur=await conn.execute("UPDATE promos SET active=? WHERE id=?",(1 if body.active else 0,promo_id))
            if cur.rowcount==0:
                raise HTTPException(404,"Промокод не найден")
            await conn.commit()
        finally:
            await conn.close()
    return {"ok":True,"active":body.active}


@app.delete("/api/admin/promos/{promo_id}")
async def admin_delete_promo(promo_id:int, x_telegram_init_data: str | None = Header(default=None)):
    await owner(x_telegram_init_data)
    async with db_write_lock:
        conn=await db()
        try:
            await conn.execute("DELETE FROM promos WHERE id=?",(promo_id,))
            await conn.commit()
        finally:
            await conn.close()
    return {"ok":True}


@app.get("/api/admin/products")
async def admin_products(x_telegram_init_data: str | None = Header(default=None)):
    await owner(x_telegram_init_data)
    conn=await db()
    try:
        rows=await (await conn.execute("SELECT * FROM products ORDER BY sort_order,id")).fetchall()
    finally:
        await conn.close()
    return [dict(r) for r in rows]


@app.post("/api/admin/products")
async def admin_create_product(body:ProductAdminIn, x_telegram_init_data: str | None = Header(default=None)):
    await owner(x_telegram_init_data)
    async with db_write_lock:
        conn=await db()
        try:
            cur=await conn.execute(
                "INSERT INTO products(category,name,description,price,stars_price,active,sort_order) VALUES(?,?,?,?,?,?,?)",
                (body.category.strip(),body.name.strip(),body.description.strip(),body.stars_price,body.stars_price,1 if body.active else 0,body.sort_order)
            )
            await conn.commit()
        finally:
            await conn.close()
    return {"ok":True,"id":cur.lastrowid}


@app.patch("/api/admin/products/{product_id}")
async def admin_update_product(product_id:int, body:ProductAdminIn, x_telegram_init_data: str | None = Header(default=None)):
    await owner(x_telegram_init_data)
    async with db_write_lock:
        conn=await db()
        try:
            cur=await conn.execute(
                "UPDATE products SET category=?,name=?,description=?,price=?,stars_price=?,active=?,sort_order=? WHERE id=?",
                (body.category.strip(),body.name.strip(),body.description.strip(),body.stars_price,body.stars_price,1 if body.active else 0,body.sort_order,product_id)
            )
            if cur.rowcount==0:
                raise HTTPException(404,"Товар не найден")
            await conn.commit()
        finally:
            await conn.close()
    return {"ok":True}


@app.get("/api/admin/referrals")
async def admin_referrals(x_telegram_init_data: str | None = Header(default=None)):
    await owner(x_telegram_init_data)
    conn=await db()
    try:
        rows=await (await conn.execute(
            "SELECT r.id,r.rewarded,r.created_at,"
            "u1.token referrer_token,u1.username referrer_username,u1.first_name referrer_name,"
            "u2.token referred_token,u2.username referred_username,u2.first_name referred_name "
            "FROM referrals r LEFT JOIN users u1 ON u1.telegram_id=r.referrer_id "
            "LEFT JOIN users u2 ON u2.telegram_id=r.referred_id ORDER BY r.id DESC LIMIT 1000"
        )).fetchall()
    finally:
        await conn.close()
    return [dict(r) for r in rows]


@app.post("/api/admin/tickets/{ticket_id}/reply")
async def admin_reply_ticket(ticket_id:int, body:AdminReplyIn, x_telegram_init_data: str | None = Header(default=None)):
    await owner(x_telegram_init_data)
    conn=await db()
    try:
        row=await (await conn.execute("SELECT * FROM tickets WHERE id=?",(ticket_id,))).fetchone()
    finally:
        await conn.close()
    if not row:
        raise HTTPException(404,"Обращение не найдено")
    await tg("sendMessage",{"chat_id":int(row["telegram_id"]),"text":f"💬 Ответ поддержки по обращению #{ticket_id}:\n\n{body.message}"})
    async with db_write_lock:
        conn=await db()
        try:
            await conn.execute("UPDATE tickets SET status='Ответ дан' WHERE id=?",(ticket_id,))
            await conn.commit()
        finally:
            await conn.close()
    return {"ok":True}


@app.post("/api/admin/tickets/{ticket_id}/close")
async def admin_close_ticket(ticket_id:int, x_telegram_init_data: str | None = Header(default=None)):
    await owner(x_telegram_init_data)
    async with db_write_lock:
        conn=await db()
        try:
            await conn.execute("UPDATE tickets SET status='Закрыт' WHERE id=?",(ticket_id,))
            await conn.commit()
        finally:
            await conn.close()
    return {"ok":True}


@app.post("/api/admin/message")
async def admin_message(body:AdminMessageIn, x_telegram_init_data: str | None = Header(default=None)):
    await owner(x_telegram_init_data)
    conn=await db()
    try:
        user=await telegram_id_by_token(conn,body.token)
    finally:
        await conn.close()
    if not user:
        raise HTTPException(404,"Пользователь с таким жетоном не найден")
    await tg("sendMessage",{"chat_id":int(user["telegram_id"]),"text":body.message})
    return {"ok":True,"token":body.token.strip().upper()}


@app.post("/api/admin/broadcast")
async def admin_broadcast(body:BroadcastIn, x_telegram_init_data: str | None = Header(default=None)):
    await owner(x_telegram_init_data)
    asyncio.create_task(run_broadcast(body.message))
    return {"ok":True,"queued":True}


def page(admin=False):
    mode = "true" if admin else "false"
    tpl = r"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,minimum-scale=1,maximum-scale=1,user-scalable=no,viewport-fit=cover">
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<title>__APP_NAME__</title>
<style>
:root{--bg:#090b0d;--card:#13161a;--line:#292e34;--gold:#ffc21c;--muted:#949ba4;--blue:#58aaff;--red:#ff5567}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html,body{margin:0;min-height:100%;background:var(--bg);color:#f5f5f5;font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;touch-action:manipulation;-webkit-text-size-adjust:100%}
body:before{content:"";position:fixed;inset:0;background:radial-gradient(circle at 85% 0,#5a3b001f,transparent 32%),radial-gradient(circle at 10% 30%,#ffb3000c,transparent 25%);pointer-events:none}
.wrap{max-width:760px;margin:auto;padding:18px 16px 118px;position:relative}
.top{display:flex;align-items:center;justify-content:space-between;margin:8px 0 12px}
.brand{font-weight:950;letter-spacing:.8px;font-size:23px}.brand b{color:var(--gold)}
.pill{font-size:12px;color:#ffcf4b;border:1px solid #5f4918;background:#1b160b;padding:7px 10px;border-radius:999px}
.hero{background:linear-gradient(135deg,#1b1e22,#111315 55%,#31250a);border:1px solid #393017;border-radius:24px;padding:24px;box-shadow:0 18px 50px #0008;margin-bottom:18px;overflow:hidden;position:relative}
.hero:after{content:"METRO";position:absolute;right:-10px;bottom:-18px;font-size:62px;font-weight:1000;color:#ffffff08;transform:rotate(-7deg)}
h1{margin:0 0 8px;font-size:29px}h2,h3{margin-top:20px}.muted{color:var(--muted);line-height:1.5}.gold{color:var(--gold)}
button,.btn{border:0;border-radius:14px;padding:12px 15px;font-weight:850;cursor:pointer;font-family:inherit}
button:disabled{opacity:.42;cursor:not-allowed}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:19px;padding:15px;min-width:0}
.cat{font-size:11px;color:#e2ad22;text-transform:uppercase;letter-spacing:.8px}
.name{font-weight:850;font-size:16px;margin:6px 0}.desc{font-size:12px;color:#9299a1;min-height:38px;line-height:1.4}
.price{font-size:20px;font-weight:950;margin:12px 0}.old-price{text-decoration:line-through;color:#777;font-size:14px;margin-left:8px}
.buy{width:100%;background:linear-gradient(135deg,#ffd12d,#f5a900);color:#181000;box-shadow:0 8px 24px #e3a40022}
.secondary{background:#24282d;color:#fff}.danger{background:#40151a;color:#ff9ea8}.blue{background:#102a43;color:#72b9ff}
.order{background:#13161a;border:1px solid #272c31;border-radius:18px;padding:15px;margin:10px 0}
.status{display:inline-block;padding:5px 8px;border-radius:9px;background:#27200d;color:#ffd158;font-size:12px;font-weight:850}
input,textarea,select{width:100%;background:#0e1013;color:#fff;border:1px solid #30353b;border-radius:13px;padding:13px;margin:6px 0 10px;outline:none;font-family:inherit}
input:focus,textarea:focus,select:focus{border-color:#80651d;box-shadow:0 0 0 3px #ffc21c12}
textarea{min-height:90px;resize:vertical}.row{display:flex;gap:8px}.row>*{flex:1}.empty{text-align:center;padding:38px 10px;color:#89919a;white-space:pre-line}.hide{display:none!important}
.nav{position:fixed;left:50%;transform:translateX(-50%);bottom:10px;width:min(710px,calc(100% - 20px));background:#111418ef;backdrop-filter:blur(18px);border:1px solid #2a2e33;border-radius:20px;padding:8px;display:flex;gap:4px;z-index:20}
.nav button{flex:1;background:transparent;color:#8f969e;font-size:12px;padding:10px 3px}.nav button.active{background:#24200f;color:#ffd24b}
.page-home{display:inline-flex;align-items:center;gap:7px;margin:0 0 12px;background:#171b20;color:#dce1e6;border:1px solid #30363d;padding:9px 12px;border-radius:13px;box-shadow:inset 0 1px #ffffff0a}
.settings-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:12px 0}
.setting-card{background:#111418;border:1px solid #2a3036;border-radius:18px;padding:14px}
.setting-card h3{margin:0 0 5px;font-size:15px}.setting-card .muted{font-size:11px}
.switch-row{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-top:12px}
.switch-row input{width:22px;height:22px;accent-color:#ffc21c}
.spin-options-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:12px}
.spin-options-grid .spin-options{margin-top:0;min-height:58px}
@media(max-width:430px){.spin-options-grid{grid-template-columns:1fr}.settings-grid{grid-template-columns:1fr}}
.history-filters{background:#111418;border:1px solid #2a3036;border-radius:18px;padding:12px;margin-bottom:12px}
.history-filter-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}.history-filter-grid>*{min-width:0}
.history-periods{display:flex;gap:6px;overflow-x:auto;padding:8px 0 3px;scrollbar-width:none}.history-periods::-webkit-scrollbar{display:none}
.history-periods button{white-space:nowrap;background:#1c2127;color:#aeb5bd;border:1px solid #30363d;padding:8px 10px}.history-periods button.active{background:#33290c;color:#ffd45b;border-color:#6d5719}
.history-result-head{display:flex;justify-content:space-between;align-items:center;gap:10px;margin:12px 0 8px}
.history-time{font-size:11px;font-weight:850;color:#d0d6dc;margin-top:7px}
@media(max-width:430px){.history-filter-grid{grid-template-columns:1fr}}

/* live big wins */
.wins{height:42px;border:1px solid #2a2f35;background:#0d1013;border-radius:14px;overflow:hidden;margin:0 0 16px;display:flex;align-items:center;position:relative}
.wins:before{content:"LIVE";position:absolute;z-index:3;left:0;top:0;bottom:0;display:flex;align-items:center;padding:0 10px;font-size:10px;font-weight:950;color:#111;background:linear-gradient(135deg,#ffd431,#f4a900);box-shadow:7px 0 18px #000}
.wins-track{display:flex;align-items:center;gap:28px;white-space:nowrap;width:max-content;padding-left:65px;animation:ticker 12s linear infinite}
.win-item{font-size:12px;font-weight:800}.win-item.legendary{color:#ffc15a;text-shadow:0 0 12px #ff970055}.win-item.mythic{color:#ff6262;text-shadow:0 0 14px #ff202088}
@keyframes ticker{from{transform:translateX(0)}to{transform:translateX(-50%)}}

/* Bright vector 3D tiles — no raster images, no gray cards */
.sticker-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin:10px 0 14px}
.sticker{position:relative;min-height:88px;border-radius:18px;overflow:hidden;padding:10px;cursor:pointer;display:flex;align-items:center;gap:8px;text-align:left;border:1px solid currentColor;box-shadow:inset 0 1px #ffffff22,0 10px 24px #0007,0 0 18px color-mix(in srgb,currentColor 12%,transparent);transition:.18s transform,.18s box-shadow}
.sticker:active{transform:scale(.975)}.sticker:before{content:"";position:absolute;inset:0;background:linear-gradient(115deg,#ffffff12 0%,transparent 34%,transparent 68%,#ffffff08 100%);pointer-events:none}
.sticker:after{content:"";position:absolute;right:-24px;bottom:-42px;width:125px;height:125px;border-radius:50%;background:radial-gradient(circle,currentColor 0%,transparent 68%);opacity:.17;filter:blur(2px);pointer-events:none}
.st-gold{--accent:#ffc928;color:var(--accent);background:linear-gradient(145deg,#4a3400 0%,#241700 58%,#0b0905 100%);border-color:#c99a18}
.st-purple{--accent:#d869ff;color:var(--accent);background:linear-gradient(145deg,#421455 0%,#220b2e 58%,#0c0710 100%);border-color:#9a45bd}
.st-blue{--accent:#4fb9ff;color:var(--accent);background:linear-gradient(145deg,#0f3b60 0%,#0a2138 58%,#060b10 100%);border-color:#2d8dcb}
.st-red{--accent:#ff667b;color:var(--accent);background:linear-gradient(145deg,#521521 0%,#2a0b14 58%,#0e0608 100%);border-color:#b43b4f}
.st-cyan{--accent:#49e6dc;color:var(--accent);background:linear-gradient(145deg,#0d4945 0%,#0a2a27 58%,#050d0c 100%);border-color:#2aa69e}
.sticker-icon{width:50px;height:50px;flex:0 0 50px;display:grid;place-items:center;border-radius:15px;position:relative;background:linear-gradient(145deg,color-mix(in srgb,var(--accent) 88%,#fff 12%),color-mix(in srgb,var(--accent) 58%,#090b0d 42%));border:1px solid color-mix(in srgb,var(--accent) 74%,#fff 26%);box-shadow:inset 0 2px 1px #ffffff77,inset 0 -12px 18px #0006,0 11px 18px #0008,0 0 26px color-mix(in srgb,var(--accent) 58%,transparent);transform:perspective(160px) rotateX(7deg) rotateY(-8deg);animation:stickerFloat 3.2s ease-in-out infinite}
.sticker-icon:after{content:"";position:absolute;left:7px;right:7px;top:5px;height:11px;border-radius:50%;background:linear-gradient(180deg,#fff8,transparent);pointer-events:none}
.sticker-icon svg{width:27px;height:27px;stroke:#fff;fill:none;stroke-width:2.35;stroke-linecap:round;stroke-linejoin:round;filter:drop-shadow(0 3px 1px #0008) drop-shadow(0 0 6px color-mix(in srgb,var(--accent) 60%,transparent))}
.sticker-copy{min-width:0;flex:1;position:relative;z-index:2}
.sticker-title{font-size:clamp(11.5px,3.15vw,13.5px);font-weight:950;line-height:1.1;letter-spacing:-.1px;text-transform:uppercase;color:currentColor;text-shadow:0 0 12px color-mix(in srgb,currentColor 40%,transparent),0 2px 6px #000;overflow-wrap:normal;word-break:normal;hyphens:none;white-space:normal}
.sticker-sub{font-size:clamp(8.6px,2.3vw,9.8px);color:#f4f7fb;margin-top:4px;line-height:1.18;letter-spacing:-.1px;opacity:.92;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;word-break:normal;hyphens:none}
@media(max-width:390px){.sticker{min-height:82px;padding:9px;gap:7px}.sticker-icon{width:46px;height:46px;flex-basis:46px;border-radius:14px}.sticker-icon svg{width:25px;height:25px}.sticker-title{font-size:11.5px}.sticker-sub{font-size:8.4px}}
.token-chip{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:11px 13px;border-radius:15px;background:linear-gradient(135deg,#16130a,#0d1013);border:1px solid #5c4817;margin:-6px 0 14px;box-shadow:inset 0 1px #ffffff0a}
.token-code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:14px;font-weight:900;letter-spacing:.8px;color:#ffd155}
.token-copy{background:#28220f;color:#ffd45c;padding:8px 10px;border:1px solid #544515}
@keyframes stickerFloat{0%,100%{transform:perspective(160px) rotateX(7deg) rotateY(-8deg) translateY(0)}50%{transform:perspective(160px) rotateX(5deg) rotateY(-5deg) translateY(-3px)}}
.nav{transition:transform .22s ease,opacity .18s ease}
.nav.keyboard-hidden{transform:translate(-50%,calc(100% + 32px));opacity:0;pointer-events:none}
body.keyboard-open .wrap{padding-bottom:30px}

/* rarity */
.tier{display:inline-block;padding:5px 8px;border-radius:9px;font-size:11px;font-weight:900;letter-spacing:.7px;border:1px solid transparent}
.tier-common{color:#d2d7dd;background:#20242a;border-color:#555d66}
.tier-rare{color:#67b7ff;background:#0b2136;border-color:#1e72b8;box-shadow:0 0 14px #1e72b833}
.tier-epic{color:#c985ff;background:#261034;border-color:#8b3fc7;box-shadow:0 0 16px #8b3fc744}
.tier-legendary{color:#ffbd4a;background:#362109;border-color:#ff9900;box-shadow:0 0 22px #ff990055}
.tier-mythic{color:#ff6262;background:linear-gradient(135deg,#3d0808,#1e0707);border-color:#ff2d2d;box-shadow:0 0 26px #ff2d2d77}
.rarity-row{margin-top:10px}.rarity-label{font-size:10px;font-weight:950;letter-spacing:1px;margin-bottom:5px}
.rarity-bar{height:5px;border-radius:999px;position:relative;overflow:hidden;background:#252a30}
.rarity-bar:after{content:"";position:absolute;inset:0;background:linear-gradient(90deg,transparent,#fff8,transparent);transform:translateX(-120%);animation:raritySweep 2.2s linear infinite}
.rb-common{background:linear-gradient(90deg,#58616a,#aeb6be)}
.rb-rare{background:linear-gradient(90deg,#146bb0,#5fc0ff);box-shadow:0 0 10px #2fa8ff66}
.rb-epic{background:linear-gradient(90deg,#6b28a4,#d071ff);box-shadow:0 0 13px #b349ff77}
.rb-legendary{background:linear-gradient(90deg,#8c5000,#ff9d00,#ffe27a,#ff9d00);background-size:220% 100%;animation:legendaryFlow 1.8s linear infinite;box-shadow:0 0 12px #ff9d00,0 0 25px #ff9d0077}
.rb-mythic{background:linear-gradient(90deg,#5b0505,#ff1f1f,#ff7777,#ff1f1f,#5b0505);background-size:260% 100%;animation:mythicFlow 1.05s linear infinite;box-shadow:0 0 14px #ff2424,0 0 30px #ff0000aa}
@keyframes raritySweep{to{transform:translateX(120%)}}@keyframes legendaryFlow{to{background-position:220% 0}}@keyframes mythicFlow{to{background-position:260% 0}}

/* spin */
.spin-shell{background:linear-gradient(145deg,#12151a,#090b0d);border:1px solid #3a2c0a;border-radius:22px;padding:16px;margin:14px 0;overflow:hidden}
.reel-window{position:relative;height:118px;border:1px solid #2b3036;background:#0b0d10;border-radius:18px;overflow:hidden}
.reel-window:before,.reel-window:after{content:"";position:absolute;top:0;bottom:0;width:46px;z-index:4;pointer-events:none}
.reel-window:before{left:0;background:linear-gradient(90deg,#0b0d10 15%,transparent)}
.reel-window:after{right:0;background:linear-gradient(270deg,#0b0d10 15%,transparent)}
.reel-marker{position:absolute;left:50%;top:0;bottom:0;width:3px;background:#ffc21c;box-shadow:0 0 18px #ffc21c,0 0 34px #ffc21c55;transform:translateX(-50%);z-index:6;pointer-events:none}
.reel-track{position:absolute;left:0;top:50%;display:flex;align-items:center;gap:12px;width:max-content;transform:translate3d(-520px,-50%,0);will-change:transform}
.reel-item{display:grid;place-items:center;width:90px;height:96px;flex:0 0 90px}
.loot-cube{width:78px;height:78px;border-radius:18px;display:grid;place-items:center;font-size:38px;font-weight:1000;color:#fff;position:relative;transform:perspective(180px) rotateX(7deg) rotateY(-8deg);border:2px solid transparent;box-shadow:inset 0 3px 2px #ffffff30,inset 0 -16px 24px #0008,0 16px 22px #0008}
.loot-cube:before{content:"";position:absolute;left:10px;right:10px;top:8px;height:17px;border-radius:50%;background:linear-gradient(180deg,#fff7,transparent);pointer-events:none}
.loot-cube span{position:relative;z-index:2;text-shadow:0 4px 4px #0009}
.cube-common{background:linear-gradient(145deg,#7b8792,#303840);border-color:#aeb7c0;box-shadow:inset 0 3px 2px #ffffff35,inset 0 -16px 24px #0008,0 0 18px #96a1aa55,0 16px 22px #0008}
.cube-rare{background:linear-gradient(145deg,#42adff,#0a4b86);border-color:#6ec1ff;box-shadow:inset 0 3px 2px #ffffff45,inset 0 -16px 24px #001a35aa,0 0 24px #249cff88,0 16px 22px #0008}
.cube-epic{background:linear-gradient(145deg,#c060ff,#5a178a);border-color:#d391ff;box-shadow:inset 0 3px 2px #ffffff45,inset 0 -16px 24px #25003daa,0 0 28px #a84cff99,0 16px 22px #0008}
.cube-legendary{background:linear-gradient(145deg,#ffd35a,#c66a00);border-color:#ffe49a;box-shadow:inset 0 3px 2px #ffffff66,inset 0 -16px 24px #5a2400aa,0 0 32px #ff9d00bb,0 16px 22px #0008;animation:legendaryCube 1.2s ease-in-out infinite}
.cube-mythic{background:linear-gradient(145deg,#ff4a4a,#a60000 55%,#360000);border-color:#ffb0b0;box-shadow:inset 0 3px 2px #ffffff70,inset 0 -16px 24px #4a0000bb,0 0 34px #ff2020dd,0 0 62px #ff000099,0 16px 22px #0008;animation:mythicCube .8s ease-in-out infinite;overflow:visible}
.cube-mythic:after{content:"⚡";position:absolute;z-index:3;left:50%;top:50%;font-size:25px;color:#fff;opacity:0;transform:translate(-50%,-50%) rotate(-18deg) scale(.45);text-shadow:-28px 15px 0 #ff3b3b,28px -15px 0 #fff,18px 25px 0 #ff1d1d;animation:mythicLightning 1.15s steps(1,end) infinite;pointer-events:none}
@keyframes legendaryCube{0%,100%{filter:brightness(1)}50%{filter:brightness(1.25)}}
@keyframes mythicCube{0%,100%{filter:brightness(1)}45%{filter:brightness(1.5)}52%{filter:brightness(2)}58%{filter:brightness(1.2)}}
@keyframes mythicLightning{0%,18%,24%,57%,63%,100%{opacity:0}19%,22%,58%,61%{opacity:1;transform:translate(-50%,-50%) rotate(-18deg) scale(1.08)}20%,60%{opacity:.35;transform:translate(-46%,-54%) rotate(9deg) scale(.82)}}
.reveal-name{font-size:18px;font-weight:950;line-height:1.25;margin-top:10px;animation:revealName .42s cubic-bezier(.2,1.2,.3,1)}
@keyframes revealName{from{opacity:0;transform:translateY(8px) scale(.96)}to{opacity:1;transform:translateY(0) scale(1)}}
.spin-options{display:flex;align-items:center;gap:10px;margin-top:12px;padding:10px 12px;border-radius:14px;background:#111418;border:1px solid #252a30;cursor:pointer;user-select:none}
.spin-options input{width:20px;height:20px;margin:0;accent-color:#ffc21c;flex:0 0 20px}
.spin-options span{font-size:13px;font-weight:800;color:#d7dbe0}
.spin-result{min-height:22px;margin-top:10px;font-size:13px;font-weight:850;text-align:center}
.spin-stats{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:12px 0}.spin-stat{background:#111418;border:1px solid #24282d;border-radius:15px;padding:11px}.spin-stat .price{font-size:17px}
.rarity-catalog{margin:18px 0 8px}
.rarity-catalog-head{display:flex;justify-content:space-between;align-items:end;gap:12px;margin-bottom:10px}
.rarity-catalog-head h3{margin:0}.rarity-catalog-head .mini{text-align:right}
.rarity-scroll{display:flex;gap:10px;overflow-x:auto;padding:2px 2px 10px;scrollbar-width:none;scroll-snap-type:x proximity}
.rarity-scroll::-webkit-scrollbar{display:none}
.rarity-card{flex:0 0 122px;scroll-snap-align:start;border-radius:18px;padding:12px 10px;background:#111418;border:1px solid #2b3036;text-align:center;cursor:pointer;box-shadow:inset 0 1px #ffffff0a;transition:transform .16s ease,border-color .16s ease}
.rarity-card:active{transform:scale(.965)}
.rarity-card .loot-cube{width:58px;height:58px;border-radius:15px;font-size:28px;margin:0 auto 9px;transform:perspective(150px) rotateX(6deg) rotateY(-7deg)}
.rarity-card-title{font-size:12px;font-weight:950;letter-spacing:.6px}
.rarity-card-chance{font-size:18px;font-weight:1000;margin-top:4px}
.rarity-card-count{font-size:10px;color:#9299a1;margin-top:4px}
.rarity-modal{position:fixed;inset:0;z-index:110;background:#000c;backdrop-filter:blur(8px);display:flex;align-items:flex-end;justify-content:center;padding:12px}
.rarity-modal.hide{display:none!important}
.rarity-sheet{width:min(720px,100%);max-height:78%;overflow:auto;background:#111418;border:1px solid #30353b;border-radius:26px 26px 20px 20px;padding:17px;box-shadow:0 -18px 50px #0008}
.rarity-sheet-head{display:flex;align-items:center;gap:12px;margin-bottom:14px;position:sticky;top:-17px;background:#111418;padding:10px 0 12px;z-index:2}
.rarity-sheet-head .loot-cube{width:58px;height:58px;border-radius:15px;font-size:28px;flex:0 0 58px}
.rarity-sheet-title{min-width:0;flex:1}.rarity-sheet-title h3{margin:0 0 4px}.rarity-close{flex:0 0 auto;background:#252a30;color:#fff;padding:10px 12px}
.rarity-item-row{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 2px;border-top:1px solid #252a30}
.rarity-item-name{font-weight:850;min-width:0;line-height:1.3}
.rarity-item-price{flex:0 0 auto;font-size:15px;font-weight:950;color:#ffd35a;white-space:nowrap}
.drop-actions{display:grid;grid-template-columns:1fr 1fr;gap:9px;margin-top:12px}
.drop-actions button{width:100%}.save-drop{background:#17304a;color:#79c7ff}.sell-drop{background:linear-gradient(135deg,#ffd12d,#f5a900);color:#181000}
.inventory-balance{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:15px;border-radius:18px;background:linear-gradient(135deg,#2d2207,#111418);border:1px solid #5c4817;margin-bottom:14px}
.inventory-balance b{font-size:25px;color:#ffd155}
.inventory-card{background:#111419;border:1px solid #292f35;border-radius:20px;padding:15px;margin:10px 0}
.inventory-card-head{display:flex;align-items:center;gap:12px}.inventory-card-head .loot-cube{width:58px;height:58px;border-radius:15px;font-size:28px;flex:0 0 58px}
.inventory-meta{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}.inventory-meta span{font-size:11px;padding:6px 8px;border-radius:9px;background:#1b1f24;color:#c7cdd4}
.inventory-actions{display:flex;gap:8px;margin-top:12px}.inventory-actions button{flex:1}
.claim{width:100%;margin-top:8px;background:#20252b;color:#fff}.claim:disabled{opacity:.4}
.drop-fx{position:fixed;inset:0;z-index:99;display:flex;align-items:center;justify-content:center;padding:24px;background:#000c;backdrop-filter:blur(7px);animation:fxFade .25s ease-out}
.drop-card{width:min(520px,100%);border-radius:28px;padding:34px 22px;text-align:center;background:#101318;border:1px solid #343941;transform:scale(.72);animation:dropPop .7s cubic-bezier(.2,1.35,.35,1) forwards;position:relative;overflow:hidden}
.drop-card h2{font-size:32px;margin:10px 0}.drop-name{font-size:23px;font-weight:950;margin:15px 0}
.drop-fx.legendary .drop-card{border-color:#ff9d00;box-shadow:0 0 60px #ff9d0088,0 0 120px #ff6a0033;animation:dropPop .7s cubic-bezier(.2,1.35,.35,1) forwards,legendaryPulse .85s ease-in-out 2}
.drop-fx.mythic{background:radial-gradient(circle at 50% 40%,#7a090999,#000e 58%)}
.drop-fx.mythic .drop-card{border-color:#ff3131;box-shadow:0 0 80px #ff202099,0 0 140px #a8000066;animation:dropPop .7s cubic-bezier(.2,1.35,.35,1) forwards,mythicPulse .7s ease-in-out 3}
.drop-fx.mythic .drop-card:before{content:"";position:absolute;inset:-70%;background:conic-gradient(from 0deg,transparent,#ff242455,transparent,#ff7a7a44,transparent);animation:mythicSpin 2s linear infinite}.drop-fx.mythic .drop-card:after{content:"⚡";position:absolute;left:12%;top:14%;font-size:64px;color:#fff;z-index:1;text-shadow:210px 35px 0 #ff3434,110px 180px 0 #fff;animation:dropLightning .9s steps(1,end) infinite;opacity:0}@keyframes dropLightning{0%,32%,40%,75%,83%,100%{opacity:0}33%,37%,76%,80%{opacity:1;filter:drop-shadow(0 0 16px #ff2020)}}
.drop-content{position:relative;z-index:2}.spark{position:absolute;width:7px;height:7px;border-radius:50%;background:#fff;box-shadow:0 0 14px currentColor;animation:sparkFly 1.2s ease-out forwards}
@keyframes fxFade{from{opacity:0}to{opacity:1}}@keyframes dropPop{to{transform:scale(1)}}@keyframes legendaryPulse{0%,100%{transform:scale(1)}50%{transform:scale(1.045)}}@keyframes mythicPulse{0%,100%{filter:brightness(1);transform:scale(1)}50%{filter:brightness(1.55);transform:scale(1.06)}}@keyframes mythicSpin{to{transform:rotate(360deg)}}@keyframes sparkFly{from{transform:translate(0,0) scale(1);opacity:1}to{transform:translate(var(--x),var(--y)) scale(0);opacity:0}}

/* admin */
.admin-nav{display:flex;gap:7px;overflow-x:auto;padding:2px 0 10px;margin-bottom:8px;scrollbar-width:none}.admin-nav::-webkit-scrollbar{display:none}
.admin-nav button{white-space:nowrap;background:#181c21;color:#9ea5ad;border:1px solid #292f36;padding:9px 11px}.admin-nav button.active{background:#2b230d;color:#ffd056;border-color:#63501c}
.metrics{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}.metric{padding:14px;border:1px solid #282d33;background:#121519;border-radius:17px}.metric b{display:block;font-size:23px;margin-top:4px}
.adminline{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.adminline>*{flex:1;min-width:120px}.admin-card{background:#111419;border:1px solid #252b31;border-radius:18px;padding:14px;margin:10px 0}
.mini{font-size:11px;color:#8e959d}.ok{color:#68d391}.warn{color:#ffd166}

@media(max-width:390px){.grid,.sticker-grid{grid-template-columns:1fr 1fr}.spin-stats{grid-template-columns:1fr 1fr}.metrics{grid-template-columns:1fr 1fr}h1{font-size:25px}.sticker{min-height:122px;padding:12px}.sticker-icon{font-size:40px}}
</style>
</head>
<body>
<div class="wrap">
  <div class="top"><div class="brand">ШРЕКСИЧ <b>SHOP</b></div><div class="pill">PUBG MOBILE</div></div>
  <div class="wins" id="winsTicker"><div class="wins-track"><span class="muted">Загружаем крупные выигрыши…</span></div></div>
  <main id="app"><div class="empty">Загрузка магазина…</div></main>
</div>
<div class="nav" id="nav">
  <button data-tab="home">Главная</button><button data-tab="catalog">Каталог</button><button data-tab="spin">SPIN</button><button data-tab="orders">Заказы</button><button data-tab="settings">Настройки</button>
</div>
<script>
(function(){
'use strict';
const ADMIN=__ADMIN__;
const app=document.getElementById('app');
const navEl=document.getElementById('nav');
const tg=window.Telegram&&window.Telegram.WebApp?window.Telegram.WebApp:null;
if(tg){try{tg.ready();tg.expand();tg.setHeaderColor('#090b0d');tg.setBackgroundColor('#090b0d')}catch(_){}}
document.addEventListener('gesturestart',e=>e.preventDefault(),{passive:false});
document.addEventListener('gesturechange',e=>e.preventDefault(),{passive:false});
document.addEventListener('gestureend',e=>e.preventDefault(),{passive:false});
document.addEventListener('touchmove',e=>{if(e.touches&&e.touches.length>1)e.preventDefault()},{passive:false});
let lastTouchEnd=0;document.addEventListener('touchend',e=>{const n=Date.now();if(n-lastTouchEnd<=300)e.preventDefault();lastTouchEnd=n},{passive:false});

function typingTarget(el){
 if(!el)return false;
 const tag=String(el.tagName||'').toLowerCase();
 return tag==='input'||tag==='textarea'||tag==='select'||el.isContentEditable
}
function setKeyboardState(open){
 document.body.classList.toggle('keyboard-open',!!open);
 navEl.classList.toggle('keyboard-hidden',!!open)
}
document.addEventListener('focusin',e=>{if(typingTarget(e.target))setKeyboardState(true)});
document.addEventListener('focusout',()=>setTimeout(()=>{if(!typingTarget(document.activeElement))setKeyboardState(false)},120));
if(window.visualViewport){
 let vvBase=window.visualViewport.height;
 window.visualViewport.addEventListener('resize',()=>{
  const h=window.visualViewport.height;
  const keyboard=h<vvBase-110;
  if(h>vvBase)vvBase=h;
  if(keyboard||typingTarget(document.activeElement))setKeyboardState(true);
  else setKeyboardState(false)
 })
}

const initData=tg?(tg.initData||''):'';
const headers={'Content-Type':'application/json','X-Telegram-Init-Data':initData};
let products=[],me=null,spinState=null,lastSpinReward=null,tab=new URLSearchParams(location.search).get('tab')||(ADMIN?'admin':'home');
let adminSection='overview',adminData=null;

let audioCtx=null,spinSoundTimer=null,spinSoundStarted=0,spinSoundStep=0,spinSoundTotalMs=30000,spinSoundActive=false;
function soundsEnabled(){return localStorage.getItem('shx_sound_enabled')!=='0'}
function getAudio(){
 if(!soundsEnabled())return null;
 const AC=window.AudioContext||window.webkitAudioContext;if(!AC)return null;
 if(!audioCtx||audioCtx.state==='closed'){
  try{audioCtx=new AC()}catch(_){audioCtx=null;return null}
 }
 if(audioCtx.state==='suspended')audioCtx.resume().catch(()=>{});
 return audioCtx
}
function unlockAudio(){
 if(!soundsEnabled())return null;
 const ac=getAudio();if(!ac)return null;
 try{
  const o=ac.createOscillator(),g=ac.createGain();
  o.frequency.value=32;g.gain.value=.000001;
  o.connect(g);g.connect(ac.destination);o.start();o.stop(ac.currentTime+.02)
 }catch(_){}
 return ac
}
function tone(freq,dur=.08,vol=.035,type='sine',delay=0){
 const ac=getAudio();if(!ac)return;
 const t=ac.currentTime+delay,o=ac.createOscillator(),g=ac.createGain();
 o.type=type;o.frequency.setValueAtTime(freq,t);
 g.gain.setValueAtTime(.0001,t);g.gain.exponentialRampToValueAtTime(Math.max(.0002,vol),t+.008);g.gain.exponentialRampToValueAtTime(.0001,t+dur);
 o.connect(g);g.connect(ac.destination);o.start(t);o.stop(t+dur+.03)
}
function noiseBurst(dur=.08,vol=.025,delay=0){
 const ac=getAudio();if(!ac)return;
 const len=Math.max(1,Math.floor(ac.sampleRate*dur)),buf=ac.createBuffer(1,len,ac.sampleRate),d=buf.getChannelData(0);
 for(let i=0;i<len;i++)d[i]=(Math.random()*2-1)*(1-i/len);
 const s=ac.createBufferSource(),g=ac.createGain(),f=ac.createBiquadFilter();s.buffer=buf;f.type='highpass';f.frequency.value=900;
 g.gain.value=vol;s.connect(f);f.connect(g);g.connect(ac.destination);s.start(ac.currentTime+delay)
}
function playSpinMelody(progress=0){
 if(!soundsEnabled())return;
 const p=Math.max(0,Math.min(1,progress));
 const melody=[392.00,440.00,523.25,659.25,587.33,523.25,440.00,493.88,587.33,698.46,659.25,523.25];
 const roots=[196.00,220.00,261.63,246.94];
 const note=melody[spinSoundStep%melody.length]*(1-p*.08);
 const root=roots[Math.floor(spinSoundStep/3)%roots.length]*(1-p*.05);
 const dur=.44+p*.34;
 tone(note,dur,.026,'sine');
 tone(note/2,dur+.10,.013,'triangle',.015);
 if(spinSoundStep%3===0)tone(root,dur+.24,.016,'sine',.025);
 if(spinSoundStep%6===4)tone(note*1.25,dur*.8,.010,'sine',.08);
 spinSoundStep++
}
function startSpinSound(totalMs=30000){
 stopSpinSound();if(!soundsEnabled())return;
 unlockAudio();
 spinSoundTotalMs=totalMs;spinSoundStarted=performance.now();spinSoundStep=0;spinSoundActive=true;
 const loop=()=>{
  if(!spinSoundActive||!soundsEnabled())return;
  const p=Math.min(1,(performance.now()-spinSoundStarted)/spinSoundTotalMs);
  playSpinMelody(p);
  if(p<1){
   const gap=Math.round(300 + Math.pow(p,2.1)*650);
   spinSoundTimer=setTimeout(loop,gap)
  }else{spinSoundActive=false;spinSoundTimer=null}
 };
 loop()
}
function stopSpinSound(){
 spinSoundActive=false;
 if(spinSoundTimer){clearTimeout(spinSoundTimer);spinSoundTimer=null}
}
function resumeSpinSoundIfNeeded(){
 if(!soundsEnabled())return;
 unlockAudio();
 if(!spinSoundActive&&spinSoundStarted>0){
  const elapsed=performance.now()-spinSoundStarted;
  if(elapsed>0&&elapsed<spinSoundTotalMs){
   spinSoundActive=true;
   const loop=()=>{
    if(!spinSoundActive||!soundsEnabled())return;
    const p=Math.min(1,(performance.now()-spinSoundStarted)/spinSoundTotalMs);
    playSpinMelody(p);
    if(p<1)spinSoundTimer=setTimeout(loop,Math.round(300+Math.pow(p,2.1)*650));
    else{spinSoundActive=false;spinSoundTimer=null}
   };
   loop()
  }
 }
}
function sfxStop(){if(!soundsEnabled())return;noiseBurst(.09,.035);tone(150,.16,.05,'sine');tone(82,.22,.035,'triangle',.035)}
function sfxDrop(tier){
 if(!soundsEnabled())return;
 const t=String(tier||'COMMON').toUpperCase();
 if(t==='COMMON'){tone(520,.12,.035,'sine');tone(660,.12,.025,'sine',.08)}
 else if(t==='RARE'){tone(520,.13,.035,'triangle');tone(720,.16,.04,'triangle',.08);tone(920,.18,.035,'sine',.16)}
 else if(t==='EPIC'){[440,660,880,1100].forEach((f,i)=>tone(f,.22,.045,'triangle',i*.07))}
 else if(t==='LEGENDARY'){noiseBurst(.18,.035);[392,523,659,784,1047].forEach((f,i)=>tone(f,.32,.055,'sine',i*.085))}
 else {noiseBurst(.28,.055);tone(110,.5,.06,'sawtooth');[440,554,659,880,1108,1320].forEach((f,i)=>tone(f,.28,.055,i%2?'square':'triangle',.08+i*.065))}
}
function sfxSell(){if(!soundsEnabled())return;[660,880,1100,1320].forEach((f,i)=>tone(f,.13,.04,'triangle',i*.055))}
function sfxSave(){if(!soundsEnabled())return;noiseBurst(.08,.018);tone(420,.13,.035,'sine');tone(630,.18,.035,'sine',.08);tone(840,.2,.03,'sine',.14)}
function setSoundEnabled(on){
 localStorage.setItem('shx_sound_enabled',on?'1':'0');
 if(!on){stopSpinSound();return}
 unlockAudio();
 resumeSpinSoundIfNeeded();
 tone(523.25,.10,.018,'sine');tone(659.25,.12,.014,'sine',.07)
}

function esc(v){return String(v==null?'':v).replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]))}
function stars(n){return Number(n||0).toLocaleString('ru-RU')+' ⭐'}
function tierClass(t){return 'tier-'+String(t||'COMMON').toLowerCase()}
function rarityBar(t){const k=String(t||'COMMON').toLowerCase();return '<div class="rarity-row"><div class="rarity-label '+tierClass(t)+'">'+esc(t)+'</div><div class="rarity-bar rb-'+k+'"></div></div>'}
function formatReset(sec){sec=Math.max(0,Number(sec||0));if(!sec)return'';const h=Math.floor(sec/3600),m=Math.ceil((sec%3600)/60);return(h?h+' ч ':'')+m+' мин'}
function showFatal(m){app.innerHTML='<div class="empty">'+esc(m)+'</div>'}
window.addEventListener('error',e=>showFatal('Ошибка интерфейса: '+(e.message||'неизвестная')));
window.addEventListener('unhandledrejection',e=>showFatal('Ошибка загрузки: '+((e.reason&&e.reason.message)||String(e.reason||''))));

async function api(path,options={}){
 const ctl=new AbortController(),timer=setTimeout(()=>ctl.abort(),15000);
 try{
  const r=await fetch(path,Object.assign({},options,{headers:Object.assign({},headers,options.headers||{}),signal:ctl.signal}));
  let d={};try{d=await r.json()}catch(_){}
  if(!r.ok)throw new Error(d.detail||('HTTP '+r.status));
  return d;
 }catch(e){if(e&&e.name==='AbortError')throw new Error('Сервер не ответил за 15 секунд');throw e}
 finally{clearTimeout(timer)}
}
function openTelegram(url){try{if(tg&&tg.openTelegramLink)tg.openTelegramLink(url);else window.open(url,'_blank')}catch(_){window.open(url,'_blank')}}
function bindSocials(){document.querySelectorAll('[data-tg]').forEach(b=>b.addEventListener('click',()=>openTelegram(b.dataset.tg)))}
function updateNav(){document.querySelectorAll('#nav button').forEach(b=>b.classList.toggle('active',b.dataset.tab===tab));if(ADMIN)navEl.classList.add('hide')}
function go(t){tab=t;render()}

async function loadWinsFeed(){
 try{
  const wins=await api('/api/wins-feed');
  const el=document.querySelector('#winsTicker .wins-track');if(!el)return;
  if(!wins.length){el.innerHTML='<span class="muted">Пока ждём первый Legendary / Mythic дроп</span>';return}
  const one=wins.map(x=>'<span class="win-item '+String(x.reward_tier).toLowerCase()+'">'+(x.reward_tier==='MYTHIC'?'◆':'★')+' '+esc(x.player)+' выбил '+esc(x.reward_name)+' <b>'+esc(x.reward_tier)+'</b></span>').join('');
  el.innerHTML=one+one;
 }catch(_){}
}

function cards(list){
 return '<div class="grid">'+list.map(p=>'<div class="card"><div class="cat">'+esc(p.category)+'</div><div class="name">'+esc(p.name)+'</div><div class="desc">'+esc(p.description)+'</div><div class="price">'+stars(p.stars_price)+'</div><button class="buy" data-buy="'+p.id+'">Купить за Stars</button></div>').join('')+'</div>'
}
function bindProductButtons(){document.querySelectorAll('[data-buy]').forEach(b=>b.addEventListener('click',()=>orderForm(Number(b.dataset.buy))))}

function sticker(title,sub,icon,cls,attrs){
 const icons={
  shop:'<svg viewBox="0 0 24 24"><path d="M4 8h16l-1.4 11H5.4L4 8Z"/><path d="M8 8a4 4 0 0 1 8 0"/></svg>',
  spin:'<svg viewBox="0 0 24 24"><path d="M20 7V3l-2 2a8 8 0 1 0 1.5 10"/><path d="M20 3h-4"/><path d="M12 8v4l3 2"/></svg>',
  orders:'<svg viewBox="0 0 24 24"><path d="m4 7 8-4 8 4-8 4-8-4Z"/><path d="M4 7v10l8 4 8-4V7"/><path d="m9 15 2 2 4-4"/></svg>',
  inventory:'<svg viewBox="0 0 24 24"><path d="M4 6h16v14H4V6Z"/><path d="M8 6V3h8v3"/><path d="M8 11h8M8 15h5"/></svg>',
  referral:'<svg viewBox="0 0 24 24"><circle cx="8" cy="8" r="3"/><circle cx="17" cy="9" r="2.5"/><path d="M3 20c.5-4 2.5-6 5-6s4.5 2 5 6"/><path d="M14 15c1-.8 2-1 3-1 2.2 0 3.7 1.5 4 4"/></svg>',
  news:'<svg viewBox="0 0 24 24"><path d="m4 13 12-6v10L4 13Z"/><path d="M16 10c2 0 4-1 4-3v10c0-2-2-3-4-3"/><path d="m6 14 1 5h4l-2-4"/></svg>',
  chat:'<svg viewBox="0 0 24 24"><path d="M4 5h16v11H9l-5 4V5Z"/><path d="M8 10h.01M12 10h.01M16 10h.01"/></svg>',
  promo:'<svg viewBox="0 0 24 24"><circle cx="7" cy="7" r="2.5"/><circle cx="17" cy="17" r="2.5"/><path d="m6 18 12-12"/></svg>',
  support:'<svg viewBox="0 0 24 24"><path d="M4 12a8 8 0 0 1 16 0"/><path d="M4 12v5h4v-6H4M20 12v5h-4v-6h4"/><path d="M16 19c-1 1-2 2-4 2"/></svg>',
  settings:'<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M19 12a7 7 0 0 0-.1-1l2-1.5-2-3.4-2.4 1a8 8 0 0 0-1.7-1L14.5 3h-5l-.4 3.1a8 8 0 0 0-1.7 1L5 6.1 3 9.5 5 11a7 7 0 0 0 0 2l-2 1.5L5 18l2.4-1a8 8 0 0 0 1.7 1l.4 3h5l.4-3a8 8 0 0 0 1.7-1l2.4 1 2-3.5-2-1.5a7 7 0 0 0 .1-1Z"/></svg>',
  history:'<svg viewBox="0 0 24 24"><path d="M4 12a8 8 0 1 0 2.3-5.7L4 8.6"/><path d="M4 4v4.6h4.6"/><path d="M12 7v5l3 2"/></svg>'
 };
 return '<div class="sticker '+cls+'" '+attrs+'><span class="sticker-icon">'+(icons[icon]||icons.shop)+'</span><div class="sticker-copy"><div class="sticker-title">'+title+'</div><div class="sticker-sub">'+sub+'</div></div></div>'
}
function home(){
 return '<section class="hero"><div class="cat">PUBG MOBILE</div><h1>METRO <span class="gold">ROYALE</span></h1><div class="muted">Товары, буст, квесты и Metro-награды. Оплата покупок — через ⭐ Telegram Stars.</div></section>'+
 '<div class="token-chip"><div><div class="mini">ВАШ ЖЕТОН</div><div class="token-code">'+esc(me&&me.token?me.token:'—')+'</div></div><button class="token-copy" id="copyTokenBtn">Копировать</button></div>'+
 '<div class="sticker-grid">'+
 sticker('Каталог','Товары и услуги','shop','st-gold','data-go="catalog"')+
 sticker('HYPE SPIN','1 free / 24h','spin','st-purple','data-go="spin"')+
 sticker('Мои заказы','Статусы покупок','orders','st-blue','data-go="orders"')+
 sticker('Инвентарь','Предметы и SHR','inventory','st-cyan','data-go="inventory"')+
 sticker('Рефералы','Билеты и бонусы','referral','st-red','data-go="referral"')+
 sticker('Новости','@shreksi4PubgNEWS','news','st-gold','data-tg="https://t.me/shreksi4PubgNEWS"')+
 sticker('Наш чат','@chatshreksi4','chat','st-cyan','data-tg="https://t.me/chatshreksi4"')+
 sticker('Настройки','Звук, анимация, помощь','settings','st-blue','data-go="settings"')+
 '</div><h3>Популярное</h3>'+cards(products.slice(0,4))
}
function bindHome(){
 bindProductButtons();
 document.querySelectorAll('[data-go]').forEach(b=>b.addEventListener('click',()=>go(b.dataset.go)));
 bindSocials();
 const t=document.getElementById('copyTokenBtn');if(t)t.addEventListener('click',async()=>{try{await navigator.clipboard.writeText(me.token);alert('Жетон скопирован')}catch(_){alert(me.token)}})
}

function orderForm(id){
 const p=products.find(x=>Number(x.id)===Number(id));if(!p)return;
 app.innerHTML='<div class="hero"><div class="cat">'+esc(p.category)+'</div><h1>'+esc(p.name)+'</h1><div class="muted">'+esc(p.description)+'</div><div class="price" id="orderPrice">'+stars(p.stars_price)+'</div></div>'+
 '<div class="card"><b>Данные заказа</b><input id="uid" placeholder="UID PUBG Mobile"><input id="nick" placeholder="Игровой ник"><textarea id="comment" placeholder="Комментарий к заказу"></textarea>'+
 '<div class="row"><input id="promo" placeholder="Промокод"><button class="secondary" id="promoBtn">Проверить</button></div><div class="mini" id="promoInfo"></div>'+
 '<button class="buy" id="createOrderBtn" style="margin-top:10px">Создать заказ</button></div>';
 document.getElementById('promoBtn').addEventListener('click',()=>checkPromo(id,p.stars_price));
 document.getElementById('createOrderBtn').addEventListener('click',()=>createOrder(id))
}
async function checkPromo(id,base){
 const info=document.getElementById('promoInfo'),code=document.getElementById('promo').value.trim();
 if(!code){info.textContent='Введите промокод';return}
 try{
  const d=await api('/api/promo/check',{method:'POST',body:JSON.stringify({product_id:id,uid:'preview',nickname:'',comment:'',promo_code:code})});
  info.innerHTML='<span class="ok">Промокод '+esc(d.code)+' • скидка '+d.discount_percent+'% • '+stars(d.final_stars)+'</span>';
  document.getElementById('orderPrice').innerHTML=stars(d.final_stars)+' <span class="old-price">'+stars(base)+'</span>'
 }catch(e){info.innerHTML='<span class="warn">'+esc(e.message)+'</span>'}
}
async function createOrder(id){
 const btn=document.getElementById('createOrderBtn');if(btn.disabled)return;btn.disabled=true;btn.textContent='Создаём заказ…';
 try{
  const o=await api('/api/orders',{method:'POST',body:JSON.stringify({product_id:id,uid:document.getElementById('uid').value,nickname:document.getElementById('nick').value,comment:document.getElementById('comment').value,promo_code:document.getElementById('promo').value})});
  showPay(o)
 }catch(e){btn.disabled=false;btn.textContent='Создать заказ';alert(e.message)}
}
function showPay(o){
 const sale=o.discount_percent?'<div class="ok">Промокод '+esc(o.promo_code)+' • -'+o.discount_percent+'%</div>':'';
 app.innerHTML='<div class="hero"><div class="cat">ЗАКАЗ #'+o.number+'</div><h1>Заказ создан</h1><div class="muted">Оплата через Telegram Stars.</div></div><div class="card">'+sale+'<div class="price">'+stars(o.stars_amount)+(o.original_stars_amount>o.stars_amount?' <span class="old-price">'+stars(o.original_stars_amount)+'</span>':'')+'</div><button class="buy" id="starsBtn">Оплатить '+o.stars_amount+' ⭐</button></div>';
 document.getElementById('starsBtn').addEventListener('click',()=>payStars(o.id))
}
async function payStars(id){
 const b=document.getElementById('starsBtn');if(b.disabled)return;b.disabled=true;b.textContent='Открываем оплату…';
 try{
  const d=await api('/api/orders/'+id+'/stars',{method:'POST'});
  if(tg&&tg.openInvoice)tg.openInvoice(d.url,()=>{tab='orders';render()});else location.href=d.url
 }catch(e){b.disabled=false;b.textContent='Оплатить Stars';alert(e.message)}
}
async function ordersHtml(){
 const list=await api('/api/orders');if(!list.length)return'<div class="empty">У вас пока нет заказов.</div>';
 return '<h2>Мои заказы</h2>'+list.map(o=>'<div class="order"><div class="cat">ЗАКАЗ #'+o.number+'</div><div class="name">'+esc(o.product_name)+'</div><div class="row"><div class="price">'+stars(o.stars_amount)+'</div><div style="text-align:right"><span class="status">'+esc(o.status)+'</span></div></div>'+(o.promo_code?'<div class="mini">Промокод: '+esc(o.promo_code)+' (-'+o.discount_percent+'%)</div>':'')+'<div class="muted">'+esc(o.created_at)+'</div></div>').join('')
}

function showDropFx(reward){
 if(!reward||(reward.tier!=='LEGENDARY'&&reward.tier!=='MYTHIC'))return;
 try{if(tg&&tg.HapticFeedback){tg.HapticFeedback.notificationOccurred('success');tg.HapticFeedback.impactOccurred(reward.tier==='MYTHIC'?'heavy':'medium')}}catch(_){}
 const fx=document.createElement('div');fx.className='drop-fx '+reward.tier.toLowerCase();
 fx.innerHTML='<div class="drop-card"><div class="drop-content"><h2>'+(reward.tier==='MYTHIC'?'MYTHIC DROP!':'LEGENDARY DROP!')+'</h2><div class="drop-name">'+esc(reward.name)+'</div>'+rarityBar(reward.tier)+'<div class="muted" style="margin-top:12px">Продажа: '+reward.points+' SHR</div><button class="buy" id="closeDrop" style="margin-top:18px">ЗАБРАТЬ</button></div></div>';
 document.body.appendChild(fx);const card=fx.querySelector('.drop-card'),total=reward.tier==='MYTHIC'?30:20;
 for(let i=0;i<total;i++){const s=document.createElement('i');s.className='spark';const a=Math.PI*2*i/total,d=90+Math.random()*170;s.style.left=(45+Math.random()*10)+'%';s.style.top=(45+Math.random()*10)+'%';s.style.setProperty('--x',(Math.cos(a)*d)+'px');s.style.setProperty('--y',(Math.sin(a)*d)+'px');s.style.color=reward.tier==='MYTHIC'?(i%2?'#ff4bd8':'#8b62ff'):'#ffad25';card.appendChild(s)}
 fx.querySelector('#closeDrop').addEventListener('click',()=>fx.remove())
}
function formatDropDate(value){
 if(!value)return '—';
 let raw=String(value).trim();
 if(!/[zZ]|[+-]\d\d:\d\d$/.test(raw))raw=raw.replace(' ','T')+'Z';
 const d=new Date(raw);
 if(Number.isNaN(d.getTime()))return esc(value);
 return d.toLocaleString('ru-RU',{day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit',second:'2-digit'})
}
function utcFilterValue(value){
 if(!value)return '';
 const d=new Date(value);
 if(Number.isNaN(d.getTime()))return '';
 return d.toISOString().slice(0,19).replace('T',' ')
}
function tierLabel(tier){
 const labels={COMMON:'COMMON',RARE:'RARE',EPIC:'EPIC',LEGENDARY:'LEGENDARY',MYTHIC:'MYTHIC'};
 return labels[String(tier||'').toUpperCase()]||String(tier||'')
}
function tierChance(tier){
 const v=spinState&&spinState.tier_chances?spinState.tier_chances[String(tier||'').toUpperCase()]:0;
 return Number(v||0)
}
function rarityCatalogHtml(){
 const tiers=['COMMON','RARE','EPIC','LEGENDARY','MYTHIC'];
 return '<section class="rarity-catalog"><div class="rarity-catalog-head"><h3>Качество кубиков</h3><div class="mini">Нажмите на кубик<br>чтобы посмотреть содержимое</div></div><div class="rarity-scroll">'+
 tiers.map(t=>{
   const count=(spinState.rewards||[]).filter(x=>x.tier===t).length;
   return '<button type="button" class="rarity-card" data-rarity-open="'+t+'"><div class="loot-cube '+cubeClass(t)+'"><span>?</span></div><div class="rarity-card-title '+tierClass(t)+'">'+tierLabel(t)+'</div><div class="rarity-card-chance">'+tierChance(t)+'%</div><div class="rarity-card-count">'+count+' предметов</div></button>'
 }).join('')+'</div></section><div class="rarity-modal hide" id="rarityModal"><div class="rarity-sheet" id="raritySheet"></div></div>'
}
function openRarityModal(tier){
 const modal=document.getElementById('rarityModal'),sheet=document.getElementById('raritySheet');
 if(!modal||!sheet)return;
 const items=(spinState.rewards||[]).filter(x=>x.tier===tier);
 sheet.innerHTML='<div class="rarity-sheet-head"><div class="loot-cube '+cubeClass(tier)+'"><span>?</span></div><div class="rarity-sheet-title"><h3 class="'+tierClass(tier)+'">'+tierLabel(tier)+'</h3><div class="muted">Шанс качества: '+tierChance(tier)+'% • '+items.length+' предметов</div></div><button type="button" class="rarity-close" id="rarityClose">Закрыть</button></div>'+
 items.map(x=>'<div class="rarity-item-row"><div class="rarity-item-name">'+esc(x.name)+'</div><div class="rarity-item-price">🪙 '+Number(x.value_stars||0).toLocaleString('ru-RU')+'</div></div>').join('');
 modal.classList.remove('hide');
 const close=()=>modal.classList.add('hide');
 document.getElementById('rarityClose').addEventListener('click',close);
 modal.addEventListener('click',e=>{if(e.target===modal)close()},{once:true})
}
function bindRarityCatalog(){
 document.querySelectorAll('[data-rarity-open]').forEach(b=>b.addEventListener('click',()=>openRarityModal(b.dataset.rarityOpen)))
}

async function spinHtml(){
 spinState=await api('/api/spin/state');
 const history=(spinState.history||[]).map(x=>'<div class="order"><div class="name">'+esc(x.reward_name)+'</div>'+rarityBar(x.reward_tier)+'<div class="mini" style="margin-top:9px">'+(x.source==='ticket'?'🎟 Бонусный билет':'🕐 Бесплатный SPIN')+' • продажа '+x.points+' SHR</div><div class="history-time">📅 '+formatDropDate(x.created_at)+'</div></div>').join('');
 const claims=(spinState.upgrade_rewards||[]).map(x=>'<button class="claim" data-claim="'+x.points+'" '+(Number(spinState.shr)>=Number(x.points)?'':'disabled')+'>'+esc(x.name)+' • '+x.points+' SHR</button>').join('');
 const total=Number(spinState.remaining_spins||0);
 const buttonText=spinState.free_remaining>0?'БЕСПЛАТНЫЙ SPIN':spinState.bonus_tickets>0?'SPIN ЗА БОНУСНЫЙ БИЛЕТ':'ЛИМИТ ИСЧЕРПАН';
 const skip=localStorage.getItem('shx_skip_spin_animation')==='1';
 return '<section class="hero"><div class="cat">HYPE MODE</div><h1>HYPE <span class="gold">SPIN</span></h1><div class="muted">1 бесплатное вращение за 24 часа. Дополнительные вращения — бонусными билетами и SPIN-промокодами.</div></section>'+
 '<div class="spin-stats"><div class="spin-stat"><div class="mini">FREE</div><div class="price">'+spinState.free_remaining+' / 1</div></div><div class="spin-stat"><div class="mini">БИЛЕТЫ</div><div class="price">🎟 '+spinState.bonus_tickets+'</div></div><div class="spin-stat"><div class="mini">SHR</div><div class="price">'+spinState.shr+'</div></div></div>'+
 '<div class="spin-shell"><div class="reel-window" id="reelWindow"><div class="reel-track" id="reelTrack">'+idleCubeStrip()+'</div><div class="reel-marker"></div></div><div class="spin-result" id="spinResult"></div><button class="buy" id="spinBtn" style="margin-top:12px" '+(total<=0?'disabled':'')+'>'+buttonText+'</button>'+
 '<div class="spin-options-grid"><label class="spin-options"><input type="checkbox" id="skipSpinAnimation" '+(skip?'checked':'')+'><span>Пропустить анимацию</span></label><label class="spin-options"><input type="checkbox" id="spinSoundToggle" '+(soundsEnabled()?'checked':'')+'><span>Звуки эффектов</span></label></div>'+
 '<div class="muted" style="margin-top:10px">'+(spinState.free_remaining>0?'Бесплатное вращение доступно':spinState.bonus_tickets>0?'Будет использован бонусный билет':'Следующий бесплатный SPIN через '+formatReset(spinState.next_reset_seconds))+'</div></div>'+
 rarityCatalogHtml()+
 '<div class="card"><div class="cat">SPIN-ПРОМОКОД</div><div class="muted">Введите промокод на дополнительные бонусные вращения.</div><div class="row"><input id="spinPromoCode" placeholder="Промокод"><button class="secondary" id="spinPromoBtn">Активировать</button></div><div class="mini" id="spinPromoInfo"></div></div>'+
 '<h3>SHR MARKET</h3><div class="card"><div class="muted">SHR можно получить за продажу выпавших предметов и обменять на гарантированные награды.</div>'+claims+'</div><h3>Последние 5 выпадений</h3>'+(history||'<div class="empty">История пока пустая.</div>')
}
function bindSpin(){
 const b=document.getElementById('spinBtn');if(b&&!b.disabled)b.addEventListener('click',spinOnce);
 const p=document.getElementById('spinPromoBtn');if(p)p.addEventListener('click',applySpinPromo);
 const skip=document.getElementById('skipSpinAnimation');if(skip)skip.addEventListener('change',()=>localStorage.setItem('shx_skip_spin_animation',skip.checked?'1':'0'));
 const snd=document.getElementById('spinSoundToggle');if(snd)snd.addEventListener('change',()=>{
  setSoundEnabled(snd.checked);
  const other=document.getElementById('settingsSound');if(other)other.checked=snd.checked
 });
 bindRarityCatalog();
 document.querySelectorAll('[data-claim]').forEach(b=>b.addEventListener('click',()=>claimUpgrade(Number(b.dataset.claim))))
}
async function applySpinPromo(){
 const code=(document.getElementById('spinPromoCode').value||'').trim(),info=document.getElementById('spinPromoInfo');
 if(!code){info.innerHTML='<span class="warn">Введите промокод</span>';return}
 const b=document.getElementById('spinPromoBtn');b.disabled=true;b.textContent='Проверяем…';
 try{
  const d=await api('/api/spin/promo',{method:'POST',body:JSON.stringify({code})});
  info.innerHTML='<span class="ok">+'+d.tickets_added+' SPIN-билет(а). Теперь у вас 🎟 '+d.bonus_tickets+'</span>';
  setTimeout(async()=>{app.innerHTML=await spinHtml();bindSpin()},650)
 }catch(e){info.innerHTML='<span class="warn">'+esc(e.message)+'</span>';b.disabled=false;b.textContent='Активировать'}
}
function sleep(ms){return new Promise(r=>setTimeout(r,ms))}
function cubeClass(tier){return 'cube-'+String(tier||'COMMON').toLowerCase()}
function cubeHtml(tier,extra=''){
 return '<div class="reel-item '+extra+'"><div class="loot-cube '+cubeClass(tier)+'"><span>?</span></div></div>'
}
function visualTier(){
 const r=Math.random()*100;
 const common=tierChance('COMMON');
 const rare=common+tierChance('RARE');
 const epic=rare+tierChance('EPIC');
 const legendary=epic+tierChance('LEGENDARY');
 if(r<common)return 'COMMON';
 if(r<rare)return 'RARE';
 if(r<epic)return 'EPIC';
 if(r<legendary)return 'LEGENDARY';
 return 'MYTHIC'
}
function idleCubeStrip(){
 const tiers=['COMMON','RARE','COMMON','EPIC','COMMON','RARE','COMMON','LEGENDARY','COMMON'];
 return tiers.map(t=>cubeHtml(t)).join('')
}
function buildSpinStrip(reward){
 const count=125;
 const targetIndex=60;
 const tiers=[];
 for(let i=0;i<count;i++)tiers.push(i===targetIndex?reward.tier:visualTier());
 return {html:tiers.map((t,i)=>cubeHtml(t,i===targetIndex?'target-cube':'')).join(''),targetIndex}
}
function centerTrackOnTarget(track,windowEl,targetIndex,animate){
 const itemWidth=90,gap=12,pitch=itemWidth+gap;
 const targetCenter=targetIndex*pitch+itemWidth/2;
 const finalX=windowEl.clientWidth/2-targetCenter;
 if(!animate){
  track.style.transform='translate3d('+finalX+'px,-50%,0)';
  return Promise.resolve()
 }
 const travel=Math.max(6000,windowEl.clientWidth*15);
 const startX=finalX-travel;
 track.style.transform='translate3d('+startX+'px,-50%,0)';
 void track.offsetWidth;
 if(track.animate){
  const anim=track.animate([
   {transform:'translate3d('+startX+'px,-50%,0)',offset:0},
   {transform:'translate3d('+(finalX-3300)+'px,-50%,0)',offset:.25},
   {transform:'translate3d('+(finalX-1750)+'px,-50%,0)',offset:.50},
   {transform:'translate3d('+(finalX-760)+'px,-50%,0)',offset:.70},
   {transform:'translate3d('+(finalX-300)+'px,-50%,0)',offset:.84},
   {transform:'translate3d('+(finalX-92)+'px,-50%,0)',offset:.95},
   {transform:'translate3d('+finalX+'px,-50%,0)',offset:1}
  ],{
   duration:30000,
   easing:'cubic-bezier(.035,.70,.10,1)',
   fill:'forwards'
  });
  return anim.finished.catch(()=>{}).then(()=>{
   track.style.transform='translate3d('+finalX+'px,-50%,0)';
   anim.cancel()
  })
 }
 track.style.transition='transform 30s cubic-bezier(.035,.70,.10,1)';
 track.style.transform='translate3d('+finalX+'px,-50%,0)';
 return sleep(30050).then(()=>{track.style.transition=''})}
async function animateSpinRight(track,windowEl,reward){
 const strip=buildSpinStrip(reward);
 track.innerHTML=strip.html;
 await centerTrackOnTarget(track,windowEl,strip.targetIndex,true);
 await sleep(650)
}
function showFinalCube(track,windowEl,reward){
 const strip={html:cubeHtml(reward.tier,'target-cube'),targetIndex:0};
 track.innerHTML=strip.html;
 const itemWidth=90;
 const finalX=windowEl.clientWidth/2-itemWidth/2;
 track.style.transform='translate3d('+finalX+'px,-50%,0)'
}
function revealReward(result,data){
 if(!result)return;
 const reward=data.reward;
 result.innerHTML='<div class="reveal-name '+tierClass(reward.tier)+'">'+esc(reward.name)+'</div>'+
 '<div class="mini">Решите, что сделать с предметом</div>'+
 '<div class="drop-actions"><button class="save-drop" id="saveDropBtn">Сохранить</button><button class="sell-drop" id="sellDropBtn">Продать за '+data.sell_shr+' SHR</button></div>';
 const save=document.getElementById('saveDropBtn'),sell=document.getElementById('sellDropBtn');
 if(save)save.addEventListener('click',()=>resolveDrop(data.inventory_item_id,'save',save));
 if(sell)sell.addEventListener('click',()=>resolveDrop(data.inventory_item_id,'sell',sell))
}
async function resolveDrop(itemId,action,btn){
 if(btn)btn.disabled=true;
 try{
  const d=await api('/api/inventory/'+itemId+'/resolve',{method:'POST',body:JSON.stringify({action})});
  if(action==='save'){sfxSave();tab='inventory';await render()}
  else{
   sfxSell();
   alert('Продано. Баланс: '+d.shr+' SHR');
   app.innerHTML=await spinHtml();bindSpin();addHomeExit();loadWinsFeed()
  }
 }catch(e){if(btn)btn.disabled=false;alert(e.message)}
}
async function spinOnce(){
 const b=document.getElementById('spinBtn');if(!b||b.disabled)return;
 const track=document.getElementById('reelTrack'),windowEl=document.getElementById('reelWindow'),result=document.getElementById('spinResult');
 const skip=!!document.getElementById('skipSpinAnimation')?.checked;
 b.disabled=true;b.textContent=skip?'ПОЛУЧАЕМ НАГРАДУ…':'КРУТИМ…';
 if(result)result.textContent='';
 // Unlock Web Audio directly from the user's tap so iOS/Telegram WebView
 // keeps rarity SFX working even when the reel animation is skipped.
 unlockAudio();
 try{
  const d=await api('/api/spin/free',{method:'POST'});
  lastSpinReward=d.reward;
  if(skip){
   showFinalCube(track,windowEl,d.reward);
   sfxDrop(d.reward.tier);
   revealReward(result,d);
   try{if(tg&&tg.HapticFeedback)tg.HapticFeedback.notificationOccurred('success')}catch(_){}
   showDropFx(d.reward)
  }else{
   startSpinSound(30000);
   await animateSpinRight(track,windowEl,d.reward);
   stopSpinSound();sfxStop();
   await sleep(220);
   sfxDrop(d.reward.tier);
   revealReward(result,d);
   try{if(tg&&tg.HapticFeedback)tg.HapticFeedback.notificationOccurred('success')}catch(_){}
   await sleep(500);
   showDropFx(d.reward)
  }
  b.textContent='НАГРАДА ВЫПАЛА';
 }catch(e){
  b.disabled=false;b.textContent='КРУТИТЬ SPIN';
  alert(e.message)
 }
}
async function claimUpgrade(points){try{const d=await api('/api/upgrade/claim',{method:'POST',body:JSON.stringify({points})});alert('Заявка создана: '+d.reward.name);app.innerHTML=await spinHtml();bindSpin()}catch(e){alert(e.message)}}

async function inventoryHtml(){
 const d=await api('/api/inventory');
 const items=d.items||[];
 const list=items.map(x=>{
  const pending=x.status==='pending';
  return '<div class="inventory-card"><div class="inventory-card-head"><div class="loot-cube '+cubeClass(x.reward_tier)+'"><span>?</span></div><div><div class="name">'+esc(x.reward_name)+'</div><div class="'+tierClass(x.reward_tier)+'">'+esc(x.reward_tier)+'</div></div></div>'+
  '<div class="inventory-meta"><span>Продажа: '+x.sell_shr+' SHR</span><span>Оценка: 🪙 '+Number(x.value_stars||0).toLocaleString('ru-RU')+'</span><span>'+(pending?'Новый дроп':'Сохранён')+'</span></div>'+
  '<div class="inventory-actions">'+(pending?'<button class="secondary" data-inv-save="'+x.id+'">Сохранить</button>':'')+'<button class="buy" data-inv-sell="'+x.id+'">Продать за '+x.sell_shr+' SHR</button></div></div>'
 }).join('');
 return '<section class="hero"><div class="cat">ИНВЕНТАРЬ</div><h1>Ваши предметы</h1><div class="muted">Сохраняйте дропы или продавайте их за SHR в любое время.</div></section>'+
 '<div class="inventory-balance"><div><div class="mini">БАЛАНС SHR</div><div class="muted">Внутренняя валюта Шрексича</div></div><b>'+d.shr+' SHR</b></div>'+
 (list||'<div class="empty">Инвентарь пока пуст. Предметы появляются после SPIN.</div>')
}
function bindInventory(){
 document.querySelectorAll('[data-inv-save]').forEach(b=>b.addEventListener('click',()=>resolveInventory(Number(b.dataset.invSave),'save',b)));
 document.querySelectorAll('[data-inv-sell]').forEach(b=>b.addEventListener('click',()=>resolveInventory(Number(b.dataset.invSell),'sell',b)))
}
async function resolveInventory(id,action,btn){
 if(btn)btn.disabled=true;
 try{
  const d=await api('/api/inventory/'+id+'/resolve',{method:'POST',body:JSON.stringify({action})});
  if(action==='sell'){sfxSell();alert('Предмет продан. Баланс: '+d.shr+' SHR')}else{sfxSave()}
  app.innerHTML=await inventoryHtml();bindInventory();addHomeExit()
 }catch(e){if(btn)btn.disabled=false;alert(e.message)}
}

async function referralHtml(){
 const r=await api('/api/referral');
 return '<section class="hero"><div class="cat">REFERRAL</div><h1>Приглашай друзей</h1><div class="muted">'+esc(r.reward_text)+'</div></section>'+
 '<div class="metrics"><div class="metric"><span class="mini">ПРИГЛАШЕНО</span><b>'+r.invited+'</b></div><div class="metric"><span class="mini">НАГРАЖДЕНО</span><b>'+r.rewarded+'</b></div><div class="metric"><span class="mini">БИЛЕТЫ</span><b>🎟 '+r.bonus_tickets+'</b></div><div class="metric"><span class="mini">SHR PTS</span><b>'+r.upgrade_points+'</b></div></div>'+
 '<div class="card" style="margin-top:12px"><div class="mini">ВАША ССЫЛКА</div><input id="refLink" readonly value="'+esc(r.link)+'"><button class="buy" id="copyRef">Скопировать ссылку</button></div>'
}
function bindReferral(){const b=document.getElementById('copyRef');if(b)b.addEventListener('click',async()=>{const v=document.getElementById('refLink').value;try{await navigator.clipboard.writeText(v);alert('Ссылка скопирована')}catch(_){document.getElementById('refLink').select()}})}

function supportHtml(){return '<div class="hero"><div class="cat">ПОДДЕРЖКА</div><h1>Чем помочь?</h1><div class="muted">Обращения попадают в Owner Panel. Бот не спамит автоматическими сообщениями.</div></div><div class="sticker-grid">'+sticker('Новости','@shreksi4PubgNEWS','news','st-gold','data-tg="https://t.me/shreksi4PubgNEWS"')+sticker('Наш чат','@chatshreksi4','chat','st-cyan','data-tg="https://t.me/chatshreksi4"')+'</div><div class="card"><select id="tc"><option>Вопрос по заказу</option><option>Оплата</option><option>Техническая проблема</option><option>Другое</option></select><textarea id="tm" placeholder="Опишите вопрос"></textarea><button class="buy" id="ticketBtn">Отправить</button></div>'}
async function sendTicket(){try{const d=await api('/api/support',{method:'POST',body:JSON.stringify({category:document.getElementById('tc').value,message:document.getElementById('tm').value})});alert('Обращение #'+d.id+' создано');document.getElementById('tm').value=''}catch(e){alert(e.message)}}
function bindSupport(){document.getElementById('ticketBtn').addEventListener('click',sendTicket);bindSocials()}

let dropHistoryPeriod='all';
async function dropHistoryHtml(){
 const period=dropHistoryPeriod||'all';
 const tier=(document.getElementById('historyTier')?.value)||'ALL';
 const from=utcFilterValue(document.getElementById('historyFrom')?.value||'');
 const to=utcFilterValue(document.getElementById('historyTo')?.value||'');
 const q=new URLSearchParams({period,tier});
 if(period==='custom'&&from)q.set('from_at',from);
 if(period==='custom'&&to)q.set('to_at',to);
 const d=await api('/api/spin/history?'+q.toString());
 const items=(d.items||[]).map(x=>'<div class="order"><div class="name">'+esc(x.reward_name)+'</div>'+rarityBar(x.reward_tier)+'<div class="mini" style="margin-top:9px">'+(x.source==='ticket'?'🎟 Бонусный билет':'🕐 Бесплатный SPIN')+' • продажа '+x.points+' SHR</div><div class="history-time">📅 '+formatDropDate(x.created_at)+'</div></div>').join('');
 return '<section class="hero"><div class="cat">ИСТОРИЯ ДРОПОВ</div><h1>Все выпадения</h1><div class="muted">Фильтруйте историю по времени и качеству кубика.</div></section>'+
 '<div class="history-filters"><div class="history-filter-grid"><select id="historyTier"><option value="ALL">Все редкости</option><option value="COMMON">Common</option><option value="RARE">Rare</option><option value="EPIC">Epic</option><option value="LEGENDARY">Legendary</option><option value="MYTHIC">Mythic</option></select><button class="secondary" id="historyApply">Применить фильтр</button><input id="historyFrom" type="datetime-local" aria-label="С даты"><input id="historyTo" type="datetime-local" aria-label="По дату"></div>'+
 '<div class="history-periods"><button data-hperiod="all">Всё время</button><button data-hperiod="24h">24 часа</button><button data-hperiod="7d">7 дней</button><button data-hperiod="30d">30 дней</button><button data-hperiod="90d">90 дней</button><button data-hperiod="custom">Свой период</button></div></div>'+
 '<div class="history-result-head"><h3 style="margin:0">Найдено: '+d.count+'</h3><div class="mini">до 500 записей</div></div>'+
 (items||'<div class="empty">По выбранным фильтрам выпадений нет.</div>')
}
async function refreshDropHistory(){
 const oldTier=document.getElementById('historyTier')?.value||'ALL';
 const oldFrom=document.getElementById('historyFrom')?.value||'';
 const oldTo=document.getElementById('historyTo')?.value||'';
 app.innerHTML=await dropHistoryHtml();addHomeExit();
 const tier=document.getElementById('historyTier'),from=document.getElementById('historyFrom'),to=document.getElementById('historyTo');
 if(tier)tier.value=oldTier;if(from)from.value=oldFrom;if(to)to.value=oldTo;
 bindDropHistory()
}
function bindDropHistory(){
 document.querySelectorAll('[data-hperiod]').forEach(b=>{
  b.classList.toggle('active',b.dataset.hperiod===dropHistoryPeriod);
  b.addEventListener('click',async()=>{dropHistoryPeriod=b.dataset.hperiod;await refreshDropHistory()})
 });
 const apply=document.getElementById('historyApply');if(apply)apply.addEventListener('click',async()=>{
  const hasDates=!!(document.getElementById('historyFrom')?.value||document.getElementById('historyTo')?.value);
  if(hasDates)dropHistoryPeriod='custom';
  await refreshDropHistory()
 })
}

function settingsHtml(){
 const skip=localStorage.getItem('shx_skip_spin_animation')==='1';
 const sound=soundsEnabled();
 return '<section class="hero"><div class="cat">НАСТРОЙКИ</div><h1>Шрексич</h1><div class="muted">Управляйте анимацией, звуками и быстрыми разделами.</div></section>'+
 '<div class="settings-grid"><div class="setting-card"><h3>Анимация SPIN</h3><div class="muted">Обычный прокрут длится 30 секунд: быстрый старт и плавное замедление до полной остановки.</div><label class="switch-row"><span>Пропускать анимацию</span><input type="checkbox" id="settingsSkip" '+(skip?'checked':'')+'></label></div>'+
 '<div class="setting-card"><h3>Звуки эффектов</h3><div class="muted">Прокрут, остановка, выпадение, продажа и сохранение. SFX генерируются внутри приложения.</div><label class="switch-row"><span>Звуки включены</span><input type="checkbox" id="settingsSound" '+(sound?'checked':'')+'></label></div></div>'+
 '<div class="sticker-grid">'+sticker('Инвентарь','Предметы и SHR','inventory','st-cyan','data-go="inventory"')+sticker('История дропов','Фильтр по времени и редкости','history','st-purple','data-go="drop-history"')+sticker('Поддержка','Обращения и помощь','support','st-blue','data-go="support"')+'</div>'
}
function bindSettings(){
 const a=document.getElementById('settingsSkip');if(a)a.addEventListener('change',()=>localStorage.setItem('shx_skip_spin_animation',a.checked?'1':'0'));
 const s=document.getElementById('settingsSound');if(s)s.addEventListener('change',()=>{
  setSoundEnabled(s.checked);
  const other=document.getElementById('spinSoundToggle');if(other)other.checked=s.checked
 });
 document.querySelectorAll('[data-go]').forEach(b=>b.addEventListener('click',()=>go(b.dataset.go)))
}
function addHomeExit(){
 if(ADMIN||tab==='home'||document.getElementById('pageHomeBtn'))return;
 app.insertAdjacentHTML('afterbegin','<button id="pageHomeBtn" class="page-home">← На главную</button>');
 document.getElementById('pageHomeBtn').addEventListener('click',()=>go('home'))
}

/* OWNER PANEL */
async function loadAdminData(){
 const r=await Promise.all([
  api('/api/admin/stats'),api('/api/admin/orders'),api('/api/admin/users'),api('/api/admin/products'),
  api('/api/admin/promos'),api('/api/admin/tickets'),api('/api/admin/spins'),api('/api/admin/upgrades'),api('/api/admin/referrals')
 ]);
 adminData={stats:r[0],orders:r[1],users:r[2],products:r[3],promos:r[4],tickets:r[5],spins:r[6],upgrades:r[7],referrals:r[8]}
}
function adminNav(){
 const items=[['overview','Обзор'],['orders','Заказы'],['users','Игроки'],['products','Товары'],['promos','Промо'],['rewards','Награды'],['support','Поддержка'],['bot','Бот']];
 return '<div class="admin-nav">'+items.map(x=>'<button data-admin="'+x[0]+'" class="'+(adminSection===x[0]?'active':'')+'">'+x[1]+'</button>').join('')+'</div>'
}
function metric(label,val){return '<div class="metric"><span class="mini">'+label+'</span><b>'+val+'</b></div>'}
function adminOverview(){
 const s=adminData.stats;
 return '<section class="hero"><div class="cat">OWNER PANEL</div><h1>Управление проектом</h1><div class="muted">Все основные функции бота и Mini App из одной панели.</div></section><div class="metrics">'+
 metric('ПОЛЬЗОВАТЕЛИ',s.users)+metric('ЗАКАЗЫ',s.orders)+metric('ОПЛАЧЕНО',s.paid_orders)+metric('ВЫРУЧКА',stars(s.stars_revenue))+metric('СЕГОДНЯ',s.orders_today)+metric('ТИКЕТЫ',s.open_tickets)+metric('ПРОМО',s.active_promos)+metric('РЕФЕРАЛЫ',s.rewarded_referrals+'/'+s.referrals)+'</div>'+
 (s.top_product?'<div class="card" style="margin-top:12px"><div class="mini">ТОП ТОВАР</div><div class="name">'+esc(s.top_product)+'</div></div>':'')
}
function adminOrders(){
 return '<h2>Заказы</h2>'+adminData.orders.map(o=>{const st=['Ожидает оплаты','Оплачен','Принят','В работе','Ожидает клиента','Выполнен','Отменён','Возврат'];return '<div class="admin-card"><div class="cat">#'+o.number+' • '+esc(o.user_token||'Без жетона')+'</div><div class="name">'+esc(o.product_name)+'</div><div>'+stars(o.stars_amount)+' • PUBG UID '+esc(o.uid)+(o.promo_code?' • '+esc(o.promo_code):'')+'</div><div class="adminline"><select id="os'+o.id+'">'+st.map(s=>'<option '+(s===o.status?'selected':'')+'>'+s+'</option>').join('')+'</select><button class="secondary" data-order-save="'+o.id+'">Сохранить</button></div></div>'}).join('')
}
function adminUsers(){
 return '<h2>Игроки и бонусы</h2><div class="card"><input id="userSearch" placeholder="Поиск по жетону, нику или имени"><div class="adminline"><input id="grantToken" placeholder="Жетон SHX-..."><input id="grantTickets" type="number" min="0" value="1" placeholder="Билеты"><input id="grantPts" type="number" min="0" value="0" placeholder="SHR"><button class="buy" id="grantBtn">Выдать</button></div></div>'+
 adminData.users.map(u=>'<div class="admin-card user-row" data-search="'+esc(((u.token||'')+' '+(u.username||'')+' '+(u.first_name||'')).toLowerCase())+'"><div class="name">'+esc(u.first_name||u.username||'Игрок')+' '+(u.username?'@'+esc(u.username):'')+'</div><div class="token-code">'+esc(u.token||'Без жетона')+'</div><div class="mini">заказов '+u.orders_count+' • рефералов '+u.referrals_count+' • 🎟 '+u.tickets+' • pts '+u.upgrade_points+'</div><button class="secondary" data-message-user="'+esc(u.token||'')+'" style="margin-top:8px">Написать по жетону</button></div>').join('')
}
function adminProducts(){
 return '<h2>Товары</h2><div class="card"><input id="newPName" placeholder="Название"><input id="newPCat" placeholder="Категория"><textarea id="newPDesc" placeholder="Описание"></textarea><div class="row"><input id="newPStars" type="number" placeholder="Цена ⭐"><input id="newPSort" type="number" value="0" placeholder="Сортировка"></div><button class="buy" id="newPBtn">Добавить товар</button></div>'+
 adminData.products.map(p=>'<div class="admin-card" data-product-card="'+p.id+'"><input data-p="name" value="'+esc(p.name)+'"><input data-p="category" value="'+esc(p.category)+'"><textarea data-p="description">'+esc(p.description)+'</textarea><div class="row"><input data-p="stars_price" type="number" value="'+p.stars_price+'"><input data-p="sort_order" type="number" value="'+p.sort_order+'"></div><label class="mini"><input data-p="active" type="checkbox" '+(p.active?'checked':'')+' style="width:auto"> Активен</label><button class="secondary" data-product-save="'+p.id+'" style="width:100%;margin-top:8px">Сохранить</button></div>').join('')
}
function adminPromos(){
 return '<h2>Промокоды</h2><div class="card"><select id="promoTypeNew"><option value="discount">Скидка на покупку</option><option value="spin">SPIN-билеты</option></select><input id="promoCodeNew" placeholder="Код"><div class="row"><input id="promoDiscountNew" type="number" min="0" max="90" placeholder="Скидка %"><input id="promoSpinNew" type="number" min="0" max="100" placeholder="SPIN-билетов"></div><div class="row"><input id="promoUsesNew" type="number" value="0" placeholder="Участников (0=∞)"><input id="promoExpiryNew" placeholder="Срок: 2026-12-31 23:59:59"></div><div class="mini">Можно оставить только срок, только лимит участников или задать оба ограничения сразу.</div><button class="buy" id="promoCreateBtn" style="margin-top:10px">Создать промокод</button></div>'+
 adminData.promos.map(p=>{const isSpin=Number(p.spin_tickets||0)>0||String(p.promo_type||'').toLowerCase()==='spin';const reward=isSpin?('🎟 +'+Math.max(1,Number(p.spin_tickets||0))+' SPIN'):('-'+p.discount_percent+'% ⭐');return '<div class="admin-card"><div class="name">'+esc(p.code)+' • '+reward+'</div><div class="mini">'+(isSpin?'SPIN-промокод':'Скидочный промокод')+' • участников '+p.uses+(p.max_uses?' / '+p.max_uses:' / ∞')+(p.expires_at?' • до '+esc(p.expires_at):' • без срока')+'</div><div class="row" style="margin-top:8px"><button class="secondary" data-promo-toggle="'+p.id+'" data-active="'+p.active+'">'+(p.active?'Отключить':'Включить')+'</button><button class="danger" data-promo-del="'+p.id+'">Удалить</button></div></div>'}).join('')
}
function adminRewards(){
 const spin=adminData.spins.slice(0,80).map(x=>'<div class="order"><span class="tier '+tierClass(x.reward_tier)+'">'+x.reward_tier+'</span><div class="name">'+esc(x.reward_name)+'</div><div class="mini">'+esc(x.user_token||'Без жетона')+' • '+esc(x.created_at)+'</div></div>').join('');
 const ups=adminData.upgrades.slice(0,80).map(x=>'<div class="order"><div class="name">'+esc(x.reward_name)+'</div><div class="mini">'+esc(x.user_token||'Без жетона')+' • '+x.points_spent+' pts • '+esc(x.created_at)+'</div></div>').join('');
 const refs=adminData.referrals.slice(0,80).map(x=>'<div class="order"><div class="name">'+esc(x.referrer_name||x.referrer_username||x.referrer_token||'Игрок')+' → '+esc(x.referred_name||x.referred_username||x.referred_token||'Игрок')+'</div><div class="mini">'+esc(x.referrer_token||'—')+' → '+esc(x.referred_token||'—')+' • '+(x.rewarded?'✅ Награда выдана':'⏳ Ждём первую оплату')+' • '+esc(x.created_at)+'</div></div>').join('');
 return '<h2>Выигрыши</h2>'+(spin||'<div class="empty">Нет</div>')+'<h2>Upgrade Lab</h2>'+(ups||'<div class="empty">Нет</div>')+'<h2>Рефералы</h2>'+(refs||'<div class="empty">Нет</div>')
}
function adminSupport(){
 return '<h2>Обращения</h2>'+adminData.tickets.map(t=>'<div class="admin-card"><div class="cat">#'+t.id+' • '+esc(t.category)+' • '+esc(t.status)+'</div><div style="margin:8px 0">'+esc(t.message)+'</div><div class="token-code">'+esc(t.user_token||'Без жетона')+'</div><textarea id="tr'+t.id+'" placeholder="Ответ пользователю"></textarea><div class="row"><button class="blue" data-ticket-reply="'+t.id+'">Ответить</button><button class="secondary" data-ticket-close="'+t.id+'">Закрыть</button></div></div>').join('')
}
function adminBot(){
 return '<h2>Управление ботом</h2><div class="card"><h3>Сообщение пользователю</h3><input id="botUserToken" placeholder="Жетон SHX-..."><textarea id="botUserMsg" placeholder="Сообщение"></textarea><button class="buy" id="botSendBtn">Отправить</button></div><div class="card" style="margin-top:12px"><h3>Рассылка</h3><textarea id="broadcastMsg" placeholder="Сообщение всем зарегистрированным пользователям"></textarea><button class="danger" id="broadcastBtn">Запустить рассылку</button></div><div class="card" style="margin-top:12px"><div class="name">Команды бота</div><div class="muted">/start • /shop • /faq • /ref • /token • /help<br>Каждый пользователь имеет постоянный жетон SHX-.... Вся работа с пользователями идёт по жетонам.</div></div>'
}
function adminSectionHtml(){if(adminSection==='orders')return adminOrders();if(adminSection==='users')return adminUsers();if(adminSection==='products')return adminProducts();if(adminSection==='promos')return adminPromos();if(adminSection==='rewards')return adminRewards();if(adminSection==='support')return adminSupport();if(adminSection==='bot')return adminBot();return adminOverview()}
async function adminHtml(){if(!adminData)await loadAdminData();return adminNav()+adminSectionHtml()}
async function refreshAdmin(){adminData=null;app.innerHTML='<div class="empty">Обновляем…</div>';app.innerHTML=await adminHtml();bindAdmin()}
function bindAdmin(){
 document.querySelectorAll('[data-admin]').forEach(b=>b.addEventListener('click',()=>{adminSection=b.dataset.admin;app.innerHTML=adminNav()+adminSectionHtml();bindAdmin()}));
 document.querySelectorAll('[data-order-save]').forEach(b=>b.addEventListener('click',async()=>{const id=b.dataset.orderSave;try{await api('/api/admin/orders/'+id,{method:'PATCH',body:JSON.stringify({status:document.getElementById('os'+id).value})});alert('Статус сохранён')}catch(e){alert(e.message)}}));
 const gb=document.getElementById('grantBtn');if(gb)gb.addEventListener('click',async()=>{try{await api('/api/admin/rewards/grant',{method:'POST',body:JSON.stringify({token:document.getElementById('grantToken').value,tickets:Number(document.getElementById('grantTickets').value||0),upgrade_points:Number(document.getElementById('grantPts').value||0)})});alert('Награда выдана');refreshAdmin()}catch(e){alert(e.message)}});
 document.querySelectorAll('[data-message-user]').forEach(b=>b.addEventListener('click',()=>{adminSection='bot';app.innerHTML=adminNav()+adminBot();document.getElementById('botUserToken').value=b.dataset.messageUser;bindAdmin()}));
 const np=document.getElementById('newPBtn');if(np)np.addEventListener('click',async()=>{try{await api('/api/admin/products',{method:'POST',body:JSON.stringify({name:document.getElementById('newPName').value,category:document.getElementById('newPCat').value,description:document.getElementById('newPDesc').value,stars_price:Number(document.getElementById('newPStars').value),sort_order:Number(document.getElementById('newPSort').value||0),active:true})});alert('Товар добавлен');refreshAdmin()}catch(e){alert(e.message)}});
 document.querySelectorAll('[data-product-save]').forEach(b=>b.addEventListener('click',async()=>{const id=b.dataset.productSave,card=document.querySelector('[data-product-card="'+id+'"]'),v=n=>card.querySelector('[data-p="'+n+'"]');try{await api('/api/admin/products/'+id,{method:'PATCH',body:JSON.stringify({name:v('name').value,category:v('category').value,description:v('description').value,stars_price:Number(v('stars_price').value),sort_order:Number(v('sort_order').value||0),active:v('active').checked})});alert('Товар сохранён')}catch(e){alert(e.message)}}));
 const pc=document.getElementById('promoCreateBtn');if(pc)pc.addEventListener('click',async()=>{try{await api('/api/admin/promos',{method:'POST',body:JSON.stringify({code:document.getElementById('promoCodeNew').value,promo_type:document.getElementById('promoTypeNew').value,discount_percent:Number(document.getElementById('promoDiscountNew').value||0),spin_tickets:Number(document.getElementById('promoSpinNew').value||0),max_uses:Number(document.getElementById('promoUsesNew').value||0),expires_at:document.getElementById('promoExpiryNew').value})});alert('Промокод создан');refreshAdmin()}catch(e){alert(e.message)}});
 document.querySelectorAll('[data-promo-toggle]').forEach(b=>b.addEventListener('click',async()=>{try{await api('/api/admin/promos/'+b.dataset.promoToggle,{method:'PATCH',body:JSON.stringify({active:!(Number(b.dataset.active)===1)})});refreshAdmin()}catch(e){alert(e.message)}}));
 document.querySelectorAll('[data-promo-del]').forEach(b=>b.addEventListener('click',async()=>{if(!confirm('Удалить промокод?'))return;try{await api('/api/admin/promos/'+b.dataset.promoDel,{method:'DELETE'});refreshAdmin()}catch(e){alert(e.message)}}));
 document.querySelectorAll('[data-ticket-reply]').forEach(b=>b.addEventListener('click',async()=>{const id=b.dataset.ticketReply;try{await api('/api/admin/tickets/'+id+'/reply',{method:'POST',body:JSON.stringify({message:document.getElementById('tr'+id).value})});alert('Ответ отправлен');refreshAdmin()}catch(e){alert(e.message)}}));
 document.querySelectorAll('[data-ticket-close]').forEach(b=>b.addEventListener('click',async()=>{try{await api('/api/admin/tickets/'+b.dataset.ticketClose+'/close',{method:'POST'});refreshAdmin()}catch(e){alert(e.message)}}));
 const bs=document.getElementById('botSendBtn');if(bs)bs.addEventListener('click',async()=>{try{await api('/api/admin/message',{method:'POST',body:JSON.stringify({token:document.getElementById('botUserToken').value,message:document.getElementById('botUserMsg').value})});alert('Сообщение отправлено')}catch(e){alert(e.message)}});
 const us=document.getElementById('userSearch');if(us)us.addEventListener('input',()=>{const q=us.value.trim().toLowerCase();document.querySelectorAll('.user-row').forEach(r=>r.style.display=!q||String(r.dataset.search||'').includes(q)?'':'none')});
 const br=document.getElementById('broadcastBtn');if(br)br.addEventListener('click',async()=>{if(!confirm('Отправить всем пользователям?'))return;try{await api('/api/admin/broadcast',{method:'POST',body:JSON.stringify({message:document.getElementById('broadcastMsg').value})});alert('Рассылка запущена')}catch(e){alert(e.message)}})
}

async function render(){
 updateNav();app.innerHTML='<div class="empty">Загрузка…</div>';
 try{
  if(ADMIN){app.innerHTML=await adminHtml();bindAdmin();return}
  if(tab==='home'){app.innerHTML=home();bindHome()}
  else if(tab==='catalog'){app.innerHTML='<h2>Каталог</h2>'+cards(products);bindProductButtons()}
  else if(tab==='spin'){app.innerHTML=await spinHtml();bindSpin()}
  else if(tab==='orders'){app.innerHTML=await ordersHtml()}
  else if(tab==='inventory'){app.innerHTML=await inventoryHtml();bindInventory()}
  else if(tab==='referral'){app.innerHTML=await referralHtml();bindReferral()}
  else if(tab==='support'){app.innerHTML=supportHtml();bindSupport()}
  else if(tab==='settings'){app.innerHTML=settingsHtml();bindSettings()}
  else if(tab==='drop-history'){app.innerHTML=await dropHistoryHtml();bindDropHistory()}
  addHomeExit()
 }catch(e){showFatal(e.message)}
}
document.querySelectorAll('#nav button').forEach(b=>b.addEventListener('click',()=>{tab=b.dataset.tab;render()}));

async function boot(){
 try{
  products=await api('/api/catalog');
  me=await api('/api/me');
  if(ADMIN&&!me.owner)throw new Error('Нет доступа');
  await loadWinsFeed();setInterval(loadWinsFeed,20000);render()
 }catch(e){showFatal(e.message+'\n\nОткройте приложение кнопкой из Telegram-бота.')}
}
boot();
})();
</script>
</body>
</html>"""
    return tpl.replace("__ADMIN__", mode).replace("__APP_NAME__", html.escape(APP_NAME))


@app.get("/assets/stickers.webp")
async def sticker_asset():
    return FileResponse("stickers.webp", media_type="image/webp", headers={"Cache-Control":"public, max-age=86400"})


@app.get("/", response_class=HTMLResponse)
async def miniapp():
    return page(False)


@app.get("/admin", response_class=HTMLResponse)
async def admin_page():
    return page(True)
