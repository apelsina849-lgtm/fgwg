import asyncio
import hashlib
import hmac
import html
import json
import os
import random
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

SPIN_REWARDS = [
    {"name":"250K Metro Cash","tier":"COMMON","weight":13,"points":1},
    {"name":"500K Metro Cash","tier":"COMMON","weight":13,"points":1},
    {"name":"Набор патронов","tier":"COMMON","weight":13,"points":1},
    {"name":"Набор аптечек","tier":"COMMON","weight":12,"points":1},
    {"name":"Набор ремонта","tier":"COMMON","weight":12,"points":1},
    {"name":"Ящик базовых ресурсов","tier":"COMMON","weight":12,"points":1},

    {"name":"1M Metro Cash","tier":"RARE","weight":5,"points":2},
    {"name":"Усиленный набор патронов","tier":"RARE","weight":5,"points":2},
    {"name":"Набор брони","tier":"RARE","weight":4,"points":2},
    {"name":"Набор модулей оружия","tier":"RARE","weight":4,"points":2},

    {"name":"3M Metro Cash","tier":"EPIC","weight":2,"points":3},
    {"name":"Metro Starter Kit+","tier":"EPIC","weight":2,"points":3},
    {"name":"Elite Supply Pack","tier":"EPIC","weight":1,"points":3},

    {"name":"Premium Metro Pack","tier":"LEGENDARY","weight":0.75,"points":6},
    {"name":"Буст 3 квестов","tier":"LEGENDARY","weight":0.75,"points":6},

    {"name":"Black Market Pack","tier":"MYTHIC","weight":0.25,"points":10},
    {"name":"Ultimate Metro Bundle","tier":"MYTHIC","weight":0.25,"points":10},
]
UPGRADE_REWARDS = [
    {"points":5,"name":"Набор расходников"},
    {"points":10,"name":"Metro Starter Kit"},
    {"points":18,"name":"Premium Metro Pack"},
    {"points":30,"name":"Ultimate Metro Bundle"},
]


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
      telegram_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT,
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
    CREATE TABLE IF NOT EXISTS promos(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      code TEXT UNIQUE NOT NULL,
      discount_percent INTEGER NOT NULL,
      max_uses INTEGER NOT NULL DEFAULT 0,
      uses INTEGER NOT NULL DEFAULT 0,
      active INTEGER NOT NULL DEFAULT 1,
      expires_at TEXT NOT NULL DEFAULT '',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
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
    order_cols = {r["name"] for r in await (await conn.execute("PRAGMA table_info(orders)")).fetchall()}
    if "promo_code" not in order_cols:
        await conn.execute("ALTER TABLE orders ADD COLUMN promo_code TEXT NOT NULL DEFAULT ''")
    if "discount_percent" not in order_cols:
        await conn.execute("ALTER TABLE orders ADD COLUMN discount_percent INTEGER NOT NULL DEFAULT 0")
    if "telegram_charge_id" not in order_cols:
        await conn.execute("ALTER TABLE orders ADD COLUMN telegram_charge_id TEXT NOT NULL DEFAULT ''")
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
        raise HTTPException(401, "Telegram ID не найден")
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
            await conn.commit()
        finally:
            await conn.close()
    return user


async def tg(method: str, payload: dict | None = None):
    async with httpx.AsyncClient(timeout=35) as client:
        r = await client.post(f"{TG_API}/{method}", json=payload or {})
        data = r.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram {method}: {data}")
        return data.get("result")


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
            await conn.commit()
        finally:
            await conn.close()


async def register_referral(referred_id: int, referrer_id: int):
    if not referred_id or not referrer_id or referred_id == referrer_id:
        return
    async with db_write_lock:
        conn = await db()
        try:
            exists = await (await conn.execute("SELECT 1 FROM users WHERE telegram_id=?", (referrer_id,))).fetchone()
            if exists:
                await conn.execute(
                    "INSERT OR IGNORE INTO referrals(referrer_id,referred_id) VALUES(?,?)",
                    (referrer_id, referred_id)
                )
                await conn.commit()
        finally:
            await conn.close()


async def referral_link(user_id: int):
    global bot_username
    if not bot_username:
        try:
            info = await tg("getMe")
            bot_username = info.get("username", "")
        except Exception:
            bot_username = ""
    return f"https://t.me/{bot_username}?start=ref_{user_id}" if bot_username else BASE_URL


async def send_faq(chat_id: int):
    text = (
        "<b>Частые вопросы</b>\n\n"
        "⭐ <b>Оплата:</b> покупки оплачиваются Telegram Stars прямо внутри Mini App.\n"
        "📦 <b>Заказы:</b> статус смотрите в разделе «Заказы».\n"
        "🎰 <b>SPIN:</b> 1 бесплатное вращение за 24 часа + бонусные билеты от админа и рефералов.\n"
        "🎟 <b>Промокоды:</b> вводятся при оформлении заказа и уменьшают цену в Stars.\n"
        "👥 <b>Рефералы:</b> после первой оплаченной покупки приглашённого вы получаете 1 бонусный SPIN-билет и 3 Upgrade pts.\n"
        "💬 <b>Поддержка:</b> создайте обращение в Mini App или напишите в нашем чате."
    )
    await tg("sendMessage", {"chat_id":chat_id,"parse_mode":"HTML","text":text,"reply_markup":keyboard(chat_id)})


async def send_referral(chat_id: int, user_id: int):
    link = await referral_link(user_id)
    await tg("sendMessage", {
        "chat_id":chat_id,
        "parse_mode":"HTML",
        "text":f"<b>Ваша реферальная ссылка</b>\n\n<code>{html.escape(link)}</code>\n\nЗа первую оплаченную покупку друга: <b>+1 SPIN-билет и +3 Upgrade pts</b>."
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
        answer = f"👥 Ваша ссылка: {link}\nЗа первую оплаченную покупку приглашённого: +1 SPIN-билет и +3 Upgrade pts."
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
                await register_referral(int(user.get("id", 0)), int(parts[1][4:]))
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

    pq = update.get("pre_checkout_query")
    if pq:
        ok = False
        payload = pq.get("invoice_payload", "")
        try:
            _, oid, uid = payload.split(":")
            conn = await db()
            row = await (await conn.execute("SELECT * FROM orders WHERE id=? AND telegram_id=?", (int(oid), int(uid)))).fetchone()
            await conn.close()
            ok = bool(row and row["status"] == "Ожидает оплаты" and pq.get("currency") == "XTR" and int(pq.get("total_amount",0)) == int(row["stars_amount"]))
        except Exception:
            ok = False
        await tg("answerPreCheckoutQuery", {"pre_checkout_query_id":pq["id"],"ok":ok,"error_message":None if ok else "Платёж не соответствует заказу"})
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
                        await conn.execute("UPDATE promos SET uses=uses+1 WHERE code=?", (row["promo_code"],))
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
    telegram_id: int
    tickets: int = Field(default=0, ge=0, le=100)
    upgrade_points: int = Field(default=0, ge=0, le=10000)


class BroadcastIn(BaseModel):
    message: str = Field(min_length=1, max_length=3000)


class PromoCreateIn(BaseModel):
    code: str = Field(min_length=3, max_length=32)
    discount_percent: int = Field(ge=1, le=90)
    max_uses: int = Field(default=0, ge=0, le=100000)
    expires_at: str = Field(default="", max_length=32)


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
    telegram_id: int
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
    return {"id":u["id"],"first_name":u.get("first_name"),"username":u.get("username"),"owner":int(u["id"])==OWNER_ID}


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
                    "SELECT * FROM promos WHERE code=? AND active=1 AND (max_uses=0 OR uses<max_uses) "
                    "AND (expires_at='' OR datetime(expires_at)>datetime('now'))",
                    (promo_code,)
                )).fetchone()
                if not promo:
                    await conn.rollback()
                    raise HTTPException(400,"Промокод недействителен или закончился")
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
    await current_user(x_telegram_init_data)
    code = body.promo_code.strip().upper()
    if not code:
        raise HTTPException(400,"Введите промокод")
    conn = await db()
    try:
        p = await (await conn.execute("SELECT * FROM products WHERE id=? AND active=1",(body.product_id,))).fetchone()
        promo = await (await conn.execute(
            "SELECT * FROM promos WHERE code=? AND active=1 AND (max_uses=0 OR uses<max_uses) "
            "AND (expires_at='' OR datetime(expires_at)>datetime('now'))",
            (code,)
        )).fetchone()
    finally:
        await conn.close()
    if not p:
        raise HTTPException(404,"Товар не найден")
    if not promo:
        raise HTTPException(400,"Промокод недействителен или закончился")
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
                "SELECT reward_name,reward_tier,points,source,created_at FROM spin_history WHERE telegram_id=? ORDER BY id DESC LIMIT 12",
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
      "upgrade_points":int(state["upgrade_points"]),
      "next_reset_seconds":next_reset,
      "history":[dict(x) for x in history],
      "upgrade_rewards":UPGRADE_REWARDS,
      "rewards":[{"name":x["name"],"tier":x["tier"]} for x in SPIN_REWARDS]
    }


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
            await conn.execute("UPDATE spin_state SET upgrade_points=upgrade_points+? WHERE telegram_id=?",(reward["points"],uid))
            await conn.execute(
                "INSERT INTO spin_history(telegram_id,reward_name,reward_tier,points,source) VALUES(?,?,?,?,?)",
                (uid,reward["name"],reward["tier"],reward["points"],source)
            )
            await conn.commit()
            state = await (await conn.execute("SELECT * FROM spin_state WHERE telegram_id=?",(uid,))).fetchone()
        finally:
            await conn.close()

    free_remaining = max(0, MAX_FREE_SPINS_24H - used - (1 if source=="free" else 0))
    return {
      "reward":reward,"source":source,
      "free_remaining":free_remaining,
      "bonus_tickets":int(state["tickets"] or 0),
      "remaining_spins":free_remaining + int(state["tickets"] or 0),
      "upgrade_points":int(state["upgrade_points"])
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
      "reward_text":"+1 бонусный SPIN-билет и +3 Upgrade pts за первую оплаченную покупку друга"
    }


class UpgradeClaimIn(BaseModel):
    points: int


@app.post("/api/upgrade/claim")
async def upgrade_claim(body: UpgradeClaimIn, x_telegram_init_data: str | None = Header(default=None)):
    u = await current_user(x_telegram_init_data)
    uid = int(u["id"])
    reward = next((x for x in UPGRADE_REWARDS if int(x["points"]) == int(body.points)), None)
    if not reward:
        raise HTTPException(400,"Некорректный уровень апгрейда")
    async with db_write_lock:
        conn = await db()
        try:
            await conn.execute("BEGIN IMMEDIATE")
            await conn.execute("INSERT OR IGNORE INTO spin_state(telegram_id) VALUES(?)",(uid,))
            state = await (await conn.execute("SELECT * FROM spin_state WHERE telegram_id=?",(uid,))).fetchone()
            if int(state["upgrade_points"]) < int(reward["points"]):
                await conn.rollback()
                raise HTTPException(409,"Недостаточно очков апгрейда")
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
    conn=await db(); rows=await (await conn.execute("SELECT * FROM orders ORDER BY id DESC LIMIT 300")).fetchall(); await conn.close()
    return [dict(r) for r in rows]


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
    rows=await (await conn.execute("SELECT id,telegram_id,reward_name,reward_tier,points,created_at FROM spin_history ORDER BY id DESC LIMIT 200")).fetchall()
    await conn.close()
    return [dict(r) for r in rows]


@app.get("/api/admin/upgrades")
async def admin_upgrades(x_telegram_init_data: str | None = Header(default=None)):
    await owner(x_telegram_init_data)
    conn=await db()
    rows=await (await conn.execute("SELECT id,telegram_id,reward_name,points_spent,created_at FROM upgrade_claims ORDER BY id DESC LIMIT 200")).fetchall()
    await conn.close()
    return [dict(r) for r in rows]


@app.get("/api/admin/tickets")
async def admin_tickets(x_telegram_init_data: str | None = Header(default=None)):
    await owner(x_telegram_init_data)
    conn=await db(); rows=await (await conn.execute("SELECT * FROM tickets ORDER BY id DESC LIMIT 200")).fetchall(); await conn.close()
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
            "SELECT u.telegram_id,u.username,u.first_name,u.created_at,"
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
        raise HTTPException(400,"Укажите билеты или Upgrade pts")
    async with db_write_lock:
        conn = await db()
        try:
            user = await (await conn.execute("SELECT telegram_id FROM users WHERE telegram_id=?",(body.telegram_id,))).fetchone()
            if not user:
                raise HTTPException(404,"Пользователь не найден")
            await conn.execute(
                "INSERT OR IGNORE INTO spin_state(telegram_id,tickets,last_free_spin,upgrade_points) VALUES(?,0,0,0)",
                (body.telegram_id,)
            )
            await conn.execute(
                "UPDATE spin_state SET tickets=tickets+?,upgrade_points=upgrade_points+? WHERE telegram_id=?",
                (body.tickets,body.upgrade_points,body.telegram_id)
            )
            await conn.commit()
        finally:
            await conn.close()
    return {"ok":True,"telegram_id":body.telegram_id,"tickets_added":body.tickets,"upgrade_points_added":body.upgrade_points}


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
    if not code.replace("_","").replace("-","").isalnum():
        raise HTTPException(400,"Код может содержать буквы, цифры, - и _")
    async with db_write_lock:
        conn=await db()
        try:
            try:
                cur=await conn.execute(
                    "INSERT INTO promos(code,discount_percent,max_uses,expires_at) VALUES(?,?,?,?)",
                    (code,body.discount_percent,body.max_uses,body.expires_at.strip())
                )
                await conn.commit()
            except Exception as e:
                if "UNIQUE" in str(e).upper():
                    raise HTTPException(409,"Такой промокод уже существует")
                raise
        finally:
            await conn.close()
    return {"ok":True,"id":cur.lastrowid,"code":code}


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
            "SELECT r.*,u1.username referrer_username,u1.first_name referrer_name,"
            "u2.username referred_username,u2.first_name referred_name "
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
    await tg("sendMessage",{"chat_id":body.telegram_id,"text":body.message})
    return {"ok":True}


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

/* live big wins */
.wins{height:42px;border:1px solid #2a2f35;background:#0d1013;border-radius:14px;overflow:hidden;margin:0 0 16px;display:flex;align-items:center;position:relative}
.wins:before{content:"LIVE";position:absolute;z-index:3;left:0;top:0;bottom:0;display:flex;align-items:center;padding:0 10px;font-size:10px;font-weight:950;color:#111;background:linear-gradient(135deg,#ffd431,#f4a900);box-shadow:7px 0 18px #000}
.wins-track{display:flex;align-items:center;gap:28px;white-space:nowrap;width:max-content;padding-left:65px;animation:ticker 28s linear infinite}
.win-item{font-size:12px;font-weight:800}.win-item.legendary{color:#ffc15a;text-shadow:0 0 12px #ff970055}.win-item.mythic{color:#ff7ee5;text-shadow:0 0 14px #ff40da77}
@keyframes ticker{from{transform:translateX(0)}to{transform:translateX(-50%)}}

/* 3D-style sticker tiles inspired by approved sticker set */
.sticker-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin:14px 0 18px}
.sticker{position:relative;min-height:132px;border-radius:22px;overflow:hidden;border:1px solid #30363d;background:linear-gradient(145deg,#171b20,#0d0f12);padding:14px;cursor:pointer;box-shadow:inset 0 1px #ffffff0a,0 14px 28px #0005;transition:.18s transform}
.sticker:active{transform:scale(.975)}.sticker:after{content:"";position:absolute;inset:auto -30px -45px auto;width:120px;height:120px;border-radius:50%;background:radial-gradient(circle,currentColor,transparent 67%);opacity:.11}
.sticker-icon{width:88px;height:104px;display:block;margin:-6px auto 4px;background-image:url('/assets/stickers.webp');background-size:352px 208px;background-repeat:no-repeat;filter:drop-shadow(0 10px 12px #0008);border-radius:14px}
.ico-shop{background-position:0 0}.ico-spin{background-position:-88px 0}.ico-orders{background-position:-176px 0}.ico-referral{background-position:-264px 0}.ico-promo{background-position:0 -104px}.ico-news{background-position:-88px -104px}.ico-chat{background-position:-176px -104px}.ico-support{background-position:-264px -104px}
.sticker-title{font-size:15px;font-weight:950;line-height:1.05;text-transform:uppercase;text-shadow:0 2px 6px #000}
.sticker-sub{font-size:10px;color:#b4bac1;margin-top:5px}.st-gold{color:#ffc229;border-color:#5a4516}.st-purple{color:#d766ff;border-color:#5a276a}.st-blue{color:#55b9ff;border-color:#1d5276}.st-red{color:#ff6674;border-color:#6a2731}.st-cyan{color:#4cebe0;border-color:#1d605c}

/* rarity */
.tier{display:inline-block;padding:5px 8px;border-radius:9px;font-size:11px;font-weight:900;letter-spacing:.7px;border:1px solid transparent}
.tier-common{color:#d2d7dd;background:#20242a;border-color:#555d66}
.tier-rare{color:#67b7ff;background:#0b2136;border-color:#1e72b8;box-shadow:0 0 14px #1e72b833}
.tier-epic{color:#c985ff;background:#261034;border-color:#8b3fc7;box-shadow:0 0 16px #8b3fc744}
.tier-legendary{color:#ffbd4a;background:#362109;border-color:#ff9900;box-shadow:0 0 22px #ff990055}
.tier-mythic{color:#ff79df;background:linear-gradient(135deg,#3b0b34,#21113d);border-color:#ff4bd8;box-shadow:0 0 26px #ff4bd866}

/* spin */
.spin-shell{background:linear-gradient(145deg,#12151a,#090b0d);border:1px solid #3a2c0a;border-radius:22px;padding:16px;margin:14px 0;overflow:hidden}
.reel-window{position:relative;height:118px;border:1px solid #2b3036;background:#0b0d10;border-radius:18px;overflow:hidden;display:flex;align-items:center;justify-content:center}
.reel-window:after{content:"";position:absolute;left:50%;top:0;bottom:0;width:2px;background:#ffc21c;box-shadow:0 0 18px #ffc21c;transform:translateX(-50%)}
.reel-item{font-size:20px;font-weight:950;text-align:center;padding:0 28px;transition:transform .15s,opacity .15s}
.reel-item.spinning{animation:spinPulse .11s linear infinite}
.reel-item.tier-common{color:#d1d6dc}.reel-item.tier-rare{color:#67b7ff;text-shadow:0 0 18px #249cff}.reel-item.tier-epic{color:#c985ff;text-shadow:0 0 20px #a84cff}.reel-item.tier-legendary{color:#ffc250;text-shadow:0 0 24px #ff9800}.reel-item.tier-mythic{color:#ff79df;text-shadow:0 0 26px #ff37d2,0 0 44px #7d45ff}
@keyframes spinPulse{0%{transform:translateY(-5px);opacity:.45}50%{transform:translateY(5px);opacity:1}100%{transform:translateY(-5px);opacity:.45}}
.spin-stats{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:12px 0}.spin-stat{background:#111418;border:1px solid #24282d;border-radius:15px;padding:11px}.spin-stat .price{font-size:17px}
.claim{width:100%;margin-top:8px;background:#20252b;color:#fff}.claim:disabled{opacity:.4}
.drop-fx{position:fixed;inset:0;z-index:99;display:flex;align-items:center;justify-content:center;padding:24px;background:#000c;backdrop-filter:blur(7px);animation:fxFade .25s ease-out}
.drop-card{width:min(520px,100%);border-radius:28px;padding:34px 22px;text-align:center;background:#101318;border:1px solid #343941;transform:scale(.72);animation:dropPop .7s cubic-bezier(.2,1.35,.35,1) forwards;position:relative;overflow:hidden}
.drop-card h2{font-size:32px;margin:10px 0}.drop-name{font-size:23px;font-weight:950;margin:15px 0}
.drop-fx.legendary .drop-card{border-color:#ff9d00;box-shadow:0 0 60px #ff9d0088,0 0 120px #ff6a0033;animation:dropPop .7s cubic-bezier(.2,1.35,.35,1) forwards,legendaryPulse .85s ease-in-out 2}
.drop-fx.mythic{background:radial-gradient(circle at 50% 40%,#5c175c99,#000e 58%)}
.drop-fx.mythic .drop-card{border-color:#ff4bd8;box-shadow:0 0 80px #ff4bd899,0 0 140px #7547ff66;animation:dropPop .7s cubic-bezier(.2,1.35,.35,1) forwards,mythicPulse .7s ease-in-out 3}
.drop-fx.mythic .drop-card:before{content:"";position:absolute;inset:-70%;background:conic-gradient(from 0deg,transparent,#ff4bd844,transparent,#7d45ff55,transparent);animation:mythicSpin 2s linear infinite}
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
  <button data-tab="home">Главная</button><button data-tab="catalog">Каталог</button><button data-tab="spin">SPIN</button><button data-tab="orders">Заказы</button><button data-tab="support">Поддержка</button>
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

const initData=tg?(tg.initData||''):'';
const headers={'Content-Type':'application/json','X-Telegram-Init-Data':initData};
let products=[],me=null,spinState=null,lastSpinReward=null,tab=new URLSearchParams(location.search).get('tab')||(ADMIN?'admin':'home');
let adminSection='overview',adminData=null;

function esc(v){return String(v==null?'':v).replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]))}
function stars(n){return Number(n||0).toLocaleString('ru-RU')+' ⭐'}
function tierClass(t){return 'tier-'+String(t||'COMMON').toLowerCase()}
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

function sticker(title,sub,icon,cls,attrs){return '<div class="sticker '+cls+'" '+attrs+'><span class="sticker-icon ico-'+icon+'"></span><div class="sticker-title">'+title+'</div><div class="sticker-sub">'+sub+'</div></div>'}
function home(){
 return '<section class="hero"><div class="cat">PUBG MOBILE</div><h1>METRO <span class="gold">ROYALE</span></h1><div class="muted">Товары, буст, квесты и Metro-награды. Оплата покупок — через ⭐ Telegram Stars.</div></section>'+
 '<div class="sticker-grid">'+
 sticker('Каталог','Товары и услуги','shop','st-gold','data-go="catalog"')+
 sticker('HYPE SPIN','1 free / 24h','spin','st-purple','data-go="spin"')+
 sticker('Мои заказы','Статусы покупок','orders','st-blue','data-go="orders"')+
 sticker('Рефералы','Билеты и бонусы','referral','st-red','data-go="referral"')+
 sticker('Новости','@shreksi4PubgNEWS','news','st-gold','data-tg="https://t.me/shreksi4PubgNEWS"')+
 sticker('Наш чат','@chatshreksi4','chat','st-cyan','data-tg="https://t.me/chatshreksi4"')+
 '</div><h3>Популярное</h3>'+cards(products.slice(0,4))
}
function bindHome(){bindProductButtons();document.querySelectorAll('[data-go]').forEach(b=>b.addEventListener('click',()=>go(b.dataset.go)));bindSocials()}

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
 fx.innerHTML='<div class="drop-card"><div class="drop-content"><span class="tier '+tierClass(reward.tier)+'">'+esc(reward.tier)+'</span><h2>'+(reward.tier==='MYTHIC'?'MYTHIC DROP!':'LEGENDARY DROP!')+'</h2><div class="drop-name">'+esc(reward.name)+'</div><div class="muted">+'+reward.points+' Upgrade pts</div><button class="buy" id="closeDrop" style="margin-top:18px">ЗАБРАТЬ</button></div></div>';
 document.body.appendChild(fx);const card=fx.querySelector('.drop-card'),total=reward.tier==='MYTHIC'?30:20;
 for(let i=0;i<total;i++){const s=document.createElement('i');s.className='spark';const a=Math.PI*2*i/total,d=90+Math.random()*170;s.style.left=(45+Math.random()*10)+'%';s.style.top=(45+Math.random()*10)+'%';s.style.setProperty('--x',(Math.cos(a)*d)+'px');s.style.setProperty('--y',(Math.sin(a)*d)+'px');s.style.color=reward.tier==='MYTHIC'?(i%2?'#ff4bd8':'#8b62ff'):'#ffad25';card.appendChild(s)}
 fx.querySelector('#closeDrop').addEventListener('click',()=>fx.remove())
}
async function spinHtml(){
 spinState=await api('/api/spin/state');
 const history=(spinState.history||[]).map(x=>'<div class="order"><span class="tier '+tierClass(x.reward_tier)+'">'+esc(x.reward_tier)+'</span><div class="name">'+esc(x.reward_name)+'</div><div class="mini">'+(x.source==='ticket'?'🎟 Бонусный билет':'🕐 Бесплатный SPIN')+' • +'+x.points+' pts • '+esc(x.created_at)+'</div></div>').join('');
 const claims=(spinState.upgrade_rewards||[]).map(x=>'<button class="claim" data-claim="'+x.points+'" '+(Number(spinState.upgrade_points)>=Number(x.points)?'':'disabled')+'>'+esc(x.name)+' • '+x.points+' pts</button>').join('');
 const total=Number(spinState.remaining_spins||0);
 const buttonText=spinState.free_remaining>0?'БЕСПЛАТНЫЙ SPIN':spinState.bonus_tickets>0?'SPIN ЗА БОНУСНЫЙ БИЛЕТ':'ЛИМИТ ИСЧЕРПАН';
 return '<section class="hero"><div class="cat">HYPE MODE</div><h1>HYPE <span class="gold">SPIN</span></h1><div class="muted">1 бесплатное вращение за 24 часа. Дополнительные вращения — только бонусными билетами.</div></section>'+
 '<div class="spin-stats"><div class="spin-stat"><div class="mini">FREE</div><div class="price">'+spinState.free_remaining+' / 1</div></div><div class="spin-stat"><div class="mini">БИЛЕТЫ</div><div class="price">🎟 '+spinState.bonus_tickets+'</div></div><div class="spin-stat"><div class="mini">UPGRADE</div><div class="price">'+spinState.upgrade_points+'</div></div></div>'+
 '<div class="spin-shell"><div class="reel-window"><div class="reel-item tier-common" id="reelItem">Нажмите SPIN</div></div><button class="buy" id="spinBtn" style="margin-top:12px" '+(total<=0?'disabled':'')+'>'+buttonText+'</button><div class="muted" style="margin-top:10px">'+(spinState.free_remaining>0?'Бесплатное вращение доступно':spinState.bonus_tickets>0?'Будет использован бонусный билет':'Следующий бесплатный SPIN через '+formatReset(spinState.next_reset_seconds))+'</div><div class="mini" style="margin-top:8px">Common 75% • Rare 18% • Epic 5% • Legendary 1.5% • Mythic 0.5%</div></div>'+
 '<h3>Upgrade Lab</h3><div class="card"><div class="muted">Upgrade pts обмениваются на гарантированную награду — без случайной ставки.</div>'+claims+'</div><h3>История</h3>'+(history||'<div class="empty">История пока пустая.</div>')
}
function bindSpin(){
 const b=document.getElementById('spinBtn');if(b&&!b.disabled)b.addEventListener('click',spinOnce);
 document.querySelectorAll('[data-claim]').forEach(b=>b.addEventListener('click',()=>claimUpgrade(Number(b.dataset.claim))))
}
async function spinOnce(){
 const b=document.getElementById('spinBtn');if(!b||b.disabled)return;b.disabled=true;b.textContent='КРУТИМ…';
 const reel=document.getElementById('reelItem'),pool=spinState.rewards||[];let i=0;if(reel)reel.classList.add('spinning');
 const timer=setInterval(()=>{if(reel&&pool.length){const x=pool[i%pool.length];i++;reel.textContent=x.name;reel.className='reel-item spinning '+tierClass(x.tier)}},80);
 try{
  const d=await api('/api/spin/free',{method:'POST'});
  setTimeout(async()=>{clearInterval(timer);lastSpinReward=d.reward;if(reel){reel.className='reel-item '+tierClass(d.reward.tier);reel.textContent=d.reward.name}await new Promise(r=>setTimeout(r,650));showDropFx(d.reward);app.innerHTML=await spinHtml();bindSpin();loadWinsFeed()},1800)
 }catch(e){clearInterval(timer);if(reel)reel.classList.remove('spinning');b.disabled=false;b.textContent='КРУТИТЬ SPIN';alert(e.message)}
}
async function claimUpgrade(points){try{const d=await api('/api/upgrade/claim',{method:'POST',body:JSON.stringify({points})});alert('Заявка создана: '+d.reward.name);app.innerHTML=await spinHtml();bindSpin()}catch(e){alert(e.message)}}

async function referralHtml(){
 const r=await api('/api/referral');
 return '<section class="hero"><div class="cat">REFERRAL</div><h1>Приглашай друзей</h1><div class="muted">'+esc(r.reward_text)+'</div></section>'+
 '<div class="metrics"><div class="metric"><span class="mini">ПРИГЛАШЕНО</span><b>'+r.invited+'</b></div><div class="metric"><span class="mini">НАГРАЖДЕНО</span><b>'+r.rewarded+'</b></div><div class="metric"><span class="mini">БИЛЕТЫ</span><b>🎟 '+r.bonus_tickets+'</b></div><div class="metric"><span class="mini">UPGRADE PTS</span><b>'+r.upgrade_points+'</b></div></div>'+
 '<div class="card" style="margin-top:12px"><div class="mini">ВАША ССЫЛКА</div><input id="refLink" readonly value="'+esc(r.link)+'"><button class="buy" id="copyRef">Скопировать ссылку</button></div>'
}
function bindReferral(){const b=document.getElementById('copyRef');if(b)b.addEventListener('click',async()=>{const v=document.getElementById('refLink').value;try{await navigator.clipboard.writeText(v);alert('Ссылка скопирована')}catch(_){document.getElementById('refLink').select()}})}

function supportHtml(){return '<div class="hero"><div class="cat">ПОДДЕРЖКА</div><h1>Чем помочь?</h1><div class="muted">Обращения попадают в Owner Panel. Бот не спамит автоматическими сообщениями.</div></div><div class="sticker-grid">'+sticker('Новости','@shreksi4PubgNEWS','news','st-gold','data-tg="https://t.me/shreksi4PubgNEWS"')+sticker('Наш чат','@chatshreksi4','chat','st-cyan','data-tg="https://t.me/chatshreksi4"')+'</div><div class="card"><select id="tc"><option>Вопрос по заказу</option><option>Оплата</option><option>Техническая проблема</option><option>Другое</option></select><textarea id="tm" placeholder="Опишите вопрос"></textarea><button class="buy" id="ticketBtn">Отправить</button></div>'}
async function sendTicket(){try{const d=await api('/api/support',{method:'POST',body:JSON.stringify({category:document.getElementById('tc').value,message:document.getElementById('tm').value})});alert('Обращение #'+d.id+' создано');document.getElementById('tm').value=''}catch(e){alert(e.message)}}
function bindSupport(){document.getElementById('ticketBtn').addEventListener('click',sendTicket);bindSocials()}

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
 return '<h2>Заказы</h2>'+adminData.orders.map(o=>{const st=['Ожидает оплаты','Оплачен','Принят','В работе','Ожидает клиента','Выполнен','Отменён','Возврат'];return '<div class="admin-card"><div class="cat">#'+o.number+' • TG '+o.telegram_id+'</div><div class="name">'+esc(o.product_name)+'</div><div>'+stars(o.stars_amount)+' • UID '+esc(o.uid)+(o.promo_code?' • '+esc(o.promo_code):'')+'</div><div class="adminline"><select id="os'+o.id+'">'+st.map(s=>'<option '+(s===o.status?'selected':'')+'>'+s+'</option>').join('')+'</select><button class="secondary" data-order-save="'+o.id+'">Сохранить</button></div></div>'}).join('')
}
function adminUsers(){
 return '<h2>Игроки и бонусы</h2><div class="card"><div class="adminline"><input id="grantUid" type="number" placeholder="Telegram ID"><input id="grantTickets" type="number" min="0" value="1" placeholder="Билеты"><input id="grantPts" type="number" min="0" value="0" placeholder="Upgrade pts"><button class="buy" id="grantBtn">Выдать</button></div></div>'+
 adminData.users.map(u=>'<div class="admin-card"><div class="name">'+esc(u.first_name||u.username||'Игрок')+' '+(u.username?'@'+esc(u.username):'')+'</div><div class="mini">TG '+u.telegram_id+' • заказов '+u.orders_count+' • рефералов '+u.referrals_count+' • 🎟 '+u.tickets+' • pts '+u.upgrade_points+'</div><button class="secondary" data-message-user="'+u.telegram_id+'" style="margin-top:8px">Написать</button></div>').join('')
}
function adminProducts(){
 return '<h2>Товары</h2><div class="card"><input id="newPName" placeholder="Название"><input id="newPCat" placeholder="Категория"><textarea id="newPDesc" placeholder="Описание"></textarea><div class="row"><input id="newPStars" type="number" placeholder="Цена ⭐"><input id="newPSort" type="number" value="0" placeholder="Сортировка"></div><button class="buy" id="newPBtn">Добавить товар</button></div>'+
 adminData.products.map(p=>'<div class="admin-card" data-product-card="'+p.id+'"><input data-p="name" value="'+esc(p.name)+'"><input data-p="category" value="'+esc(p.category)+'"><textarea data-p="description">'+esc(p.description)+'</textarea><div class="row"><input data-p="stars_price" type="number" value="'+p.stars_price+'"><input data-p="sort_order" type="number" value="'+p.sort_order+'"></div><label class="mini"><input data-p="active" type="checkbox" '+(p.active?'checked':'')+' style="width:auto"> Активен</label><button class="secondary" data-product-save="'+p.id+'" style="width:100%;margin-top:8px">Сохранить</button></div>').join('')
}
function adminPromos(){
 return '<h2>Промокоды</h2><div class="card"><div class="row"><input id="promoCodeNew" placeholder="Код"><input id="promoDiscountNew" type="number" placeholder="Скидка %"></div><div class="row"><input id="promoUsesNew" type="number" value="0" placeholder="Лимит (0=∞)"><input id="promoExpiryNew" placeholder="2026-12-31 23:59:59"></div><button class="buy" id="promoCreateBtn">Создать промокод</button></div>'+
 adminData.promos.map(p=>'<div class="admin-card"><div class="name">'+esc(p.code)+' • -'+p.discount_percent+'%</div><div class="mini">Использовано '+p.uses+(p.max_uses?' / '+p.max_uses:' / ∞')+(p.expires_at?' • до '+esc(p.expires_at):'')+'</div><div class="row" style="margin-top:8px"><button class="secondary" data-promo-toggle="'+p.id+'" data-active="'+p.active+'">'+(p.active?'Отключить':'Включить')+'</button><button class="danger" data-promo-del="'+p.id+'">Удалить</button></div></div>').join('')
}
function adminRewards(){
 const spin=adminData.spins.slice(0,80).map(x=>'<div class="order"><span class="tier '+tierClass(x.reward_tier)+'">'+x.reward_tier+'</span><div class="name">'+esc(x.reward_name)+'</div><div class="mini">TG '+x.telegram_id+' • '+esc(x.created_at)+'</div></div>').join('');
 const ups=adminData.upgrades.slice(0,80).map(x=>'<div class="order"><div class="name">'+esc(x.reward_name)+'</div><div class="mini">TG '+x.telegram_id+' • '+x.points_spent+' pts • '+esc(x.created_at)+'</div></div>').join('');
 const refs=adminData.referrals.slice(0,80).map(x=>'<div class="order"><div class="name">'+esc(x.referrer_name||x.referrer_username||x.referrer_id)+' → '+esc(x.referred_name||x.referred_username||x.referred_id)+'</div><div class="mini">'+(x.rewarded?'✅ Награда выдана':'⏳ Ждём первую оплату')+' • '+esc(x.created_at)+'</div></div>').join('');
 return '<h2>Выигрыши</h2>'+(spin||'<div class="empty">Нет</div>')+'<h2>Upgrade Lab</h2>'+(ups||'<div class="empty">Нет</div>')+'<h2>Рефералы</h2>'+(refs||'<div class="empty">Нет</div>')
}
function adminSupport(){
 return '<h2>Обращения</h2>'+adminData.tickets.map(t=>'<div class="admin-card"><div class="cat">#'+t.id+' • '+esc(t.category)+' • '+esc(t.status)+'</div><div style="margin:8px 0">'+esc(t.message)+'</div><div class="mini">TG '+t.telegram_id+'</div><textarea id="tr'+t.id+'" placeholder="Ответ пользователю"></textarea><div class="row"><button class="blue" data-ticket-reply="'+t.id+'">Ответить</button><button class="secondary" data-ticket-close="'+t.id+'">Закрыть</button></div></div>').join('')
}
function adminBot(){
 return '<h2>Управление ботом</h2><div class="card"><h3>Сообщение пользователю</h3><input id="botUserId" type="number" placeholder="Telegram ID"><textarea id="botUserMsg" placeholder="Сообщение"></textarea><button class="buy" id="botSendBtn">Отправить</button></div><div class="card" style="margin-top:12px"><h3>Рассылка</h3><textarea id="broadcastMsg" placeholder="Сообщение всем зарегистрированным пользователям"></textarea><button class="danger" id="broadcastBtn">Запустить рассылку</button></div><div class="card" style="margin-top:12px"><div class="name">Команды бота</div><div class="muted">/start • /shop • /faq • /ref • /help<br>Обычные вопросы по оплате, заказам, SPIN, промокодам и рефералам бот распознаёт автоматически.</div></div>'
}
function adminSectionHtml(){if(adminSection==='orders')return adminOrders();if(adminSection==='users')return adminUsers();if(adminSection==='products')return adminProducts();if(adminSection==='promos')return adminPromos();if(adminSection==='rewards')return adminRewards();if(adminSection==='support')return adminSupport();if(adminSection==='bot')return adminBot();return adminOverview()}
async function adminHtml(){if(!adminData)await loadAdminData();return adminNav()+adminSectionHtml()}
async function refreshAdmin(){adminData=null;app.innerHTML='<div class="empty">Обновляем…</div>';app.innerHTML=await adminHtml();bindAdmin()}
function bindAdmin(){
 document.querySelectorAll('[data-admin]').forEach(b=>b.addEventListener('click',()=>{adminSection=b.dataset.admin;app.innerHTML=adminNav()+adminSectionHtml();bindAdmin()}));
 document.querySelectorAll('[data-order-save]').forEach(b=>b.addEventListener('click',async()=>{const id=b.dataset.orderSave;try{await api('/api/admin/orders/'+id,{method:'PATCH',body:JSON.stringify({status:document.getElementById('os'+id).value})});alert('Статус сохранён')}catch(e){alert(e.message)}}));
 const gb=document.getElementById('grantBtn');if(gb)gb.addEventListener('click',async()=>{try{await api('/api/admin/rewards/grant',{method:'POST',body:JSON.stringify({telegram_id:Number(document.getElementById('grantUid').value),tickets:Number(document.getElementById('grantTickets').value||0),upgrade_points:Number(document.getElementById('grantPts').value||0)})});alert('Награда выдана');refreshAdmin()}catch(e){alert(e.message)}});
 document.querySelectorAll('[data-message-user]').forEach(b=>b.addEventListener('click',()=>{adminSection='bot';app.innerHTML=adminNav()+adminBot();document.getElementById('botUserId').value=b.dataset.messageUser;bindAdmin()}));
 const np=document.getElementById('newPBtn');if(np)np.addEventListener('click',async()=>{try{await api('/api/admin/products',{method:'POST',body:JSON.stringify({name:document.getElementById('newPName').value,category:document.getElementById('newPCat').value,description:document.getElementById('newPDesc').value,stars_price:Number(document.getElementById('newPStars').value),sort_order:Number(document.getElementById('newPSort').value||0),active:true})});alert('Товар добавлен');refreshAdmin()}catch(e){alert(e.message)}});
 document.querySelectorAll('[data-product-save]').forEach(b=>b.addEventListener('click',async()=>{const id=b.dataset.productSave,card=document.querySelector('[data-product-card="'+id+'"]'),v=n=>card.querySelector('[data-p="'+n+'"]');try{await api('/api/admin/products/'+id,{method:'PATCH',body:JSON.stringify({name:v('name').value,category:v('category').value,description:v('description').value,stars_price:Number(v('stars_price').value),sort_order:Number(v('sort_order').value||0),active:v('active').checked})});alert('Товар сохранён')}catch(e){alert(e.message)}}));
 const pc=document.getElementById('promoCreateBtn');if(pc)pc.addEventListener('click',async()=>{try{await api('/api/admin/promos',{method:'POST',body:JSON.stringify({code:document.getElementById('promoCodeNew').value,discount_percent:Number(document.getElementById('promoDiscountNew').value),max_uses:Number(document.getElementById('promoUsesNew').value||0),expires_at:document.getElementById('promoExpiryNew').value})});alert('Промокод создан');refreshAdmin()}catch(e){alert(e.message)}});
 document.querySelectorAll('[data-promo-toggle]').forEach(b=>b.addEventListener('click',async()=>{try{await api('/api/admin/promos/'+b.dataset.promoToggle,{method:'PATCH',body:JSON.stringify({active:!(Number(b.dataset.active)===1)})});refreshAdmin()}catch(e){alert(e.message)}}));
 document.querySelectorAll('[data-promo-del]').forEach(b=>b.addEventListener('click',async()=>{if(!confirm('Удалить промокод?'))return;try{await api('/api/admin/promos/'+b.dataset.promoDel,{method:'DELETE'});refreshAdmin()}catch(e){alert(e.message)}}));
 document.querySelectorAll('[data-ticket-reply]').forEach(b=>b.addEventListener('click',async()=>{const id=b.dataset.ticketReply;try{await api('/api/admin/tickets/'+id+'/reply',{method:'POST',body:JSON.stringify({message:document.getElementById('tr'+id).value})});alert('Ответ отправлен');refreshAdmin()}catch(e){alert(e.message)}}));
 document.querySelectorAll('[data-ticket-close]').forEach(b=>b.addEventListener('click',async()=>{try{await api('/api/admin/tickets/'+b.dataset.ticketClose+'/close',{method:'POST'});refreshAdmin()}catch(e){alert(e.message)}}));
 const bs=document.getElementById('botSendBtn');if(bs)bs.addEventListener('click',async()=>{try{await api('/api/admin/message',{method:'POST',body:JSON.stringify({telegram_id:Number(document.getElementById('botUserId').value),message:document.getElementById('botUserMsg').value})});alert('Сообщение отправлено')}catch(e){alert(e.message)}});
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
  else if(tab==='referral'){app.innerHTML=await referralHtml();bindReferral()}
  else if(tab==='support'){app.innerHTML=supportHtml();bindSupport()}
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
