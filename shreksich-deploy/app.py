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
from fastapi.responses import HTMLResponse
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
    async with db_write_lock:
        conn = await db()
        try:
            await conn.execute("BEGIN IMMEDIATE")
            p = await (await conn.execute("SELECT * FROM products WHERE id=? AND active=1",(body.product_id,))).fetchone()
            if not p:
                await conn.rollback()
                raise HTTPException(404,"Товар не найден")
            last = await (await conn.execute("SELECT COALESCE(MAX(number),10499) n FROM orders")).fetchone()
            number = int(last["n"]) + 1
            cur = await conn.execute(
              "INSERT INTO orders(number,telegram_id,product_id,product_name,amount,stars_amount,uid,nickname,comment) VALUES(?,?,?,?,?,?,?,?,?)",
              (number,int(u["id"]),p["id"],p["name"],p["price"],p["stars_price"],body.uid,body.nickname,body.comment)
            )
            oid = cur.lastrowid
            await conn.commit()
        finally:
            await conn.close()
    return {"id":oid,"number":number,"status":"Ожидает оплаты","stars_amount":p["stars_price"]}


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
            await conn.execute("INSERT OR IGNORE INTO spin_state(telegram_id) VALUES(?)",(uid,))
            await conn.commit()
            state = await (await conn.execute("SELECT * FROM spin_state WHERE telegram_id=?",(uid,))).fetchone()
            history = await (await conn.execute("SELECT reward_name,reward_tier,points,created_at FROM spin_history WHERE telegram_id=? ORDER BY id DESC LIMIT 12",(uid,))).fetchall()
            used_row = await (await conn.execute(
                "SELECT COUNT(*) c, MIN(strftime('%s', created_at)) first_ts FROM spin_history WHERE telegram_id=? AND created_at >= datetime('now','-24 hours')",
                (uid,)
            )).fetchone()
        finally:
            await conn.close()
    used = int(used_row["c"] or 0)
    remaining = max(0, MAX_FREE_SPINS_24H - used)
    next_reset = 0
    if remaining == 0 and used_row["first_ts"]:
        next_reset = max(0, int(used_row["first_ts"]) + 86400 - int(time.time()))
    return {
      "remaining_spins":remaining,
      "max_spins":MAX_FREE_SPINS_24H,
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
            await conn.execute("INSERT OR IGNORE INTO spin_state(telegram_id) VALUES(?)",(uid,))
            used_row = await (await conn.execute(
                "SELECT COUNT(*) c FROM spin_history WHERE telegram_id=? AND created_at >= datetime('now','-24 hours')",
                (uid,)
            )).fetchone()
            used = int(used_row["c"] or 0)
            if used >= MAX_FREE_SPINS_24H:
                await conn.rollback()
                raise HTTPException(429,"Лимит исчерпан: максимум 1 бесплатный SPIN за 24 часа.")
            reward = random.choices(SPIN_REWARDS, weights=[x["weight"] for x in SPIN_REWARDS], k=1)[0]
            await conn.execute("UPDATE spin_state SET upgrade_points=upgrade_points+? WHERE telegram_id=?",(reward["points"],uid))
            await conn.execute("INSERT INTO spin_history(telegram_id,reward_name,reward_tier,points) VALUES(?,?,?,?)",(uid,reward["name"],reward["tier"],reward["points"]))
            await conn.commit()
            state = await (await conn.execute("SELECT * FROM spin_state WHERE telegram_id=?",(uid,))).fetchone()
        finally:
            await conn.close()
    remaining = max(0, MAX_FREE_SPINS_24H - used - 1)
    return {"reward":reward,"remaining_spins":remaining,"max_spins":MAX_FREE_SPINS_24H,"upgrade_points":int(state["upgrade_points"])}


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


def page(admin=False):
    mode = "true" if admin else "false"
    tpl = """<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,minimum-scale=1,maximum-scale=1,user-scalable=no,viewport-fit=cover">
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<title>__APP_NAME__</title>
<style>
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html,body{margin:0;background:#090b0d;color:#f5f5f5;font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;min-height:100%;touch-action:manipulation;-webkit-text-size-adjust:100%}
body:before{content:"";position:fixed;inset:0;background:radial-gradient(circle at 85% 0,#5a3b001f,transparent 32%),radial-gradient(circle at 10% 30%,#ffb3000c,transparent 25%);pointer-events:none}
.wrap{max-width:720px;margin:auto;padding:18px 16px 110px;position:relative}
.top{display:flex;align-items:center;justify-content:space-between;margin:8px 0 18px}
.brand{font-weight:900;letter-spacing:.7px;font-size:22px}.brand b{color:#ffc21c}
.pill{font-size:12px;color:#ffcf4b;border:1px solid #5f4918;background:#1b160b;padding:7px 10px;border-radius:999px}
.hero{background:linear-gradient(135deg,#1b1e22,#111315 55%,#31250a);border:1px solid #393017;border-radius:24px;padding:24px;box-shadow:0 18px 50px #0008;margin-bottom:20px;overflow:hidden;position:relative}
.hero:after{content:"METRO";position:absolute;right:-10px;bottom:-18px;font-size:62px;font-weight:1000;color:#ffffff08;transform:rotate(-7deg)}
h1{margin:0 0 8px;font-size:29px}.muted{color:#9ea4ab;line-height:1.5}.gold{color:#ffc21c}
button,.btn{border:0;border-radius:14px;padding:12px 15px;font-weight:800;cursor:pointer}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
.card{background:#13161a;border:1px solid #252a30;border-radius:19px;padding:15px;min-width:0}
.cat{font-size:11px;color:#e2ad22;text-transform:uppercase;letter-spacing:.8px}
.name{font-weight:850;font-size:16px;margin:6px 0}.desc{font-size:12px;color:#9299a1;min-height:38px;line-height:1.4}
.price{font-size:20px;font-weight:950;margin:12px 0}.buy{width:100%;background:linear-gradient(135deg,#ffd12d,#f5a900);color:#181000}
.order{background:#13161a;border:1px solid #272c31;border-radius:18px;padding:15px;margin:10px 0}
.status{display:inline-block;padding:5px 8px;border-radius:9px;background:#27200d;color:#ffd158;font-size:12px;font-weight:800}
input,textarea,select{width:100%;background:#0e1013;color:#fff;border:1px solid #30353b;border-radius:13px;padding:13px;margin:6px 0 10px;outline:none}
textarea{min-height:90px;resize:vertical}.row{display:flex;gap:8px}.row>*{flex:1}.secondary{background:#24282d;color:#fff}
.nav{position:fixed;left:50%;transform:translateX(-50%);bottom:10px;width:min(690px,calc(100% - 20px));background:#111418ef;backdrop-filter:blur(18px);border:1px solid #2a2e33;border-radius:20px;padding:8px;display:flex;gap:6px;z-index:10}
.nav button{flex:1;background:transparent;color:#8f969e;font-size:12px;padding:10px 4px}.nav button.active{background:#24200f;color:#ffd24b}
.empty{text-align:center;padding:38px 10px;color:#89919a;white-space:pre-line}.hide{display:none!important}.adminline{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.adminline select{width:auto;min-width:150px;margin:8px 0}
.spin-shell{background:linear-gradient(145deg,#12151a,#090b0d);border:1px solid #3a2c0a;border-radius:22px;padding:16px;margin:14px 0;overflow:hidden}
.reel-window{position:relative;height:118px;border:1px solid #2b3036;background:#0b0d10;border-radius:18px;overflow:hidden;display:flex;align-items:center;justify-content:center}
.reel-window:after{content:"";position:absolute;left:50%;top:0;bottom:0;width:2px;background:#ffc21c;box-shadow:0 0 18px #ffc21c;transform:translateX(-50%)}
.reel-item{font-size:20px;font-weight:950;text-align:center;padding:0 28px;transition:transform .15s,opacity .15s}
.reel-item.spinning{animation:spinPulse .12s linear infinite}
@keyframes spinPulse{0%{transform:translateY(-5px);opacity:.45}50%{transform:translateY(5px);opacity:1}100%{transform:translateY(-5px);opacity:.45}}
.tier{display:inline-block;padding:5px 8px;border-radius:9px;font-size:11px;font-weight:900;letter-spacing:.7px;border:1px solid transparent}
.tier-common{color:#d2d7dd;background:#20242a;border-color:#555d66}
.tier-rare{color:#67b7ff;background:#0b2136;border-color:#1e72b8;box-shadow:0 0 14px #1e72b833}
.tier-epic{color:#c985ff;background:#261034;border-color:#8b3fc7;box-shadow:0 0 16px #8b3fc744}
.tier-legendary{color:#ffbd4a;background:#362109;border-color:#ff9900;box-shadow:0 0 22px #ff990055}
.tier-mythic{color:#ff79df;background:linear-gradient(135deg,#3b0b34,#21113d);border-color:#ff4bd8;box-shadow:0 0 26px #ff4bd866}
.reel-item.tier-common{color:#d1d6dc}
.reel-item.tier-rare{color:#67b7ff;text-shadow:0 0 18px #249cff}
.reel-item.tier-epic{color:#c985ff;text-shadow:0 0 20px #a84cff}
.reel-item.tier-legendary{color:#ffc250;text-shadow:0 0 24px #ff9800}
.reel-item.tier-mythic{color:#ff79df;text-shadow:0 0 26px #ff37d2,0 0 44px #7d45ff}
.spin-stats{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:12px 0}.spin-stat{background:#111418;border:1px solid #24282d;border-radius:15px;padding:12px}
.claim{width:100%;margin-top:8px;background:#20252b;color:#fff}.claim:disabled{opacity:.4}
.socials{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:14px 0}.social-btn{width:100%;background:#171b20;color:#fff;border:1px solid #303640}.social-btn b{color:#ffc21c}
.drop-fx{position:fixed;inset:0;z-index:99;display:flex;align-items:center;justify-content:center;padding:24px;background:#000c;backdrop-filter:blur(7px);animation:fxFade .25s ease-out}
.drop-card{width:min(520px,100%);border-radius:28px;padding:34px 22px;text-align:center;background:#101318;border:1px solid #343941;transform:scale(.72);animation:dropPop .7s cubic-bezier(.2,1.35,.35,1) forwards;position:relative;overflow:hidden}
.drop-card h2{font-size:32px;margin:10px 0}.drop-card .drop-name{font-size:23px;font-weight:950;margin:15px 0}
.drop-fx.legendary .drop-card{border-color:#ff9d00;box-shadow:0 0 60px #ff9d0088,0 0 120px #ff6a0033;animation:dropPop .7s cubic-bezier(.2,1.35,.35,1) forwards,legendaryPulse .85s ease-in-out 2}
.drop-fx.mythic{background:radial-gradient(circle at 50% 40%,#5c175c99,#000e 58%)}
.drop-fx.mythic .drop-card{border-color:#ff4bd8;box-shadow:0 0 80px #ff4bd899,0 0 140px #7547ff66;animation:dropPop .7s cubic-bezier(.2,1.35,.35,1) forwards,mythicPulse .7s ease-in-out 3}
.drop-fx.mythic .drop-card:before{content:"";position:absolute;inset:-70%;background:conic-gradient(from 0deg,transparent,#ff4bd844,transparent,#7d45ff55,transparent);animation:mythicSpin 2s linear infinite}
.drop-content{position:relative;z-index:2}.spark{position:absolute;width:7px;height:7px;border-radius:50%;background:#fff;box-shadow:0 0 14px currentColor;animation:sparkFly 1.2s ease-out forwards}
@keyframes fxFade{from{opacity:0}to{opacity:1}}@keyframes dropPop{to{transform:scale(1)}}
@keyframes legendaryPulse{0%,100%{transform:scale(1)}50%{transform:scale(1.045)}}
@keyframes mythicPulse{0%,100%{filter:brightness(1);transform:scale(1)}50%{filter:brightness(1.55);transform:scale(1.06)}}
@keyframes mythicSpin{to{transform:rotate(360deg)}}@keyframes sparkFly{from{transform:translate(0,0) scale(1);opacity:1}to{transform:translate(var(--x),var(--y)) scale(0);opacity:0}}
@media(max-width:390px){.grid{grid-template-columns:1fr}h1{font-size:25px}}
</style>
</head>
<body>
<div class="wrap">
  <div class="top"><div class="brand">ШРЕКСИЧ <b>SHOP</b></div><div class="pill">PUBG MOBILE</div></div>
  <main id="app"><div class="empty">Загрузка магазина…</div></main>
</div>
<div class="nav" id="nav">
  <button data-tab="home">Главная</button><button data-tab="catalog">Каталог</button><button data-tab="spin">SPIN</button><button data-tab="orders">Заказы</button><button data-tab="support">Поддержка</button>
</div>
<script>
(function(){
'use strict';

const ADMIN = __ADMIN__;
const app = document.getElementById('app');
const navEl = document.getElementById('nav');
const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;

function showFatal(message){
  app.innerHTML = '<div class="empty">' + esc(message) + '</div>';
}
window.addEventListener('error', function(e){ showFatal('Ошибка интерфейса: ' + (e.message || 'неизвестная ошибка')); });
window.addEventListener('unhandledrejection', function(e){ showFatal('Ошибка загрузки: ' + ((e.reason && e.reason.message) || String(e.reason || 'неизвестная ошибка'))); });

document.addEventListener('gesturestart', function(e){ e.preventDefault(); }, {passive:false});
document.addEventListener('gesturechange', function(e){ e.preventDefault(); }, {passive:false});
document.addEventListener('gestureend', function(e){ e.preventDefault(); }, {passive:false});
document.addEventListener('touchmove', function(e){ if(e.touches && e.touches.length > 1) e.preventDefault(); }, {passive:false});
let lastTouchEnd = 0;
document.addEventListener('touchend', function(e){
  const now = Date.now();
  if(now - lastTouchEnd <= 300) e.preventDefault();
  lastTouchEnd = now;
}, {passive:false});

if(tg){
  try{ tg.ready(); tg.expand(); }catch(_){}
  try{ tg.setHeaderColor('#090b0d'); tg.setBackgroundColor('#090b0d'); }catch(_){}
}

const initData = tg ? (tg.initData || '') : '';
const headers = {'Content-Type':'application/json','X-Telegram-Init-Data':initData};
let products = [];
let me = null;
let spinState = null;
let lastSpinReward = null;
let tab = new URLSearchParams(location.search).get('tab') || (ADMIN ? 'admin' : 'home');

function esc(v){
  return String(v == null ? '' : v).replace(/[&<>"']/g,function(m){
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m];
  });
}
function stars(n){ return Number(n).toLocaleString('ru-RU') + ' ⭐'; }
function tierClass(t){ return 'tier-' + String(t||'COMMON').toLowerCase(); }
function formatReset(sec){
  sec=Math.max(0,Number(sec||0));
  if(!sec) return '';
  const h=Math.floor(sec/3600), m=Math.ceil((sec%3600)/60);
  return (h?h+' ч ':'')+m+' мин';
}
function openTelegram(url){
  try{
    if(tg && tg.openTelegramLink) tg.openTelegramLink(url);
    else window.open(url,'_blank');
  }catch(_){ window.open(url,'_blank'); }
}
function bindSocials(){
  document.querySelectorAll('[data-tg]').forEach(function(btn){
    btn.addEventListener('click',function(){openTelegram(btn.dataset.tg);});
  });
}
function showDropFx(reward){
  if(!reward || (reward.tier!=='LEGENDARY' && reward.tier!=='MYTHIC')) return;
  try{
    if(tg && tg.HapticFeedback){
      tg.HapticFeedback.notificationOccurred('success');
      if(reward.tier==='MYTHIC') tg.HapticFeedback.impactOccurred('heavy');
    }
  }catch(_){}
  const fx=document.createElement('div');
  fx.className='drop-fx '+reward.tier.toLowerCase();
  fx.innerHTML='<div class="drop-card"><div class="drop-content"><span class="tier '+tierClass(reward.tier)+'">'+esc(reward.tier)+'</span><h2>'+(reward.tier==='MYTHIC'?'MYTHIC DROP!':'LEGENDARY DROP!')+'</h2><div class="drop-name">'+esc(reward.name)+'</div><div class="muted">+'+reward.points+' upgrade pts</div><button class="buy" id="closeDrop" style="margin-top:18px">ЗАБРАТЬ</button></div></div>';
  document.body.appendChild(fx);
  const card=fx.querySelector('.drop-card');
  const total=reward.tier==='MYTHIC'?30:20;
  for(let i=0;i<total;i++){
    const s=document.createElement('i'); s.className='spark';
    const a=(Math.PI*2*i)/total, d=90+Math.random()*170;
    s.style.left=(45+Math.random()*10)+'%'; s.style.top=(45+Math.random()*10)+'%';
    s.style.setProperty('--x',(Math.cos(a)*d)+'px'); s.style.setProperty('--y',(Math.sin(a)*d)+'px');
    s.style.color=reward.tier==='MYTHIC'?(i%2?'#ff4bd8':'#8b62ff'):'#ffad25';
    card.appendChild(s);
  }
  fx.querySelector('#closeDrop').addEventListener('click',function(){fx.remove();});
}

async function api(path, options){
  options = options || {};
  const controller = new AbortController();
  const timer = setTimeout(function(){ controller.abort(); }, 12000);
  try{
    const response = await fetch(path, Object.assign({}, options, {
      headers:Object.assign({}, headers, options.headers || {}),
      signal:controller.signal
    }));
    let data = {};
    try{ data = await response.json(); }catch(_){}
    if(!response.ok) throw new Error(data.detail || ('HTTP ' + response.status));
    return data;
  }catch(e){
    if(e && e.name === 'AbortError') throw new Error('Сервер не ответил за 12 секунд');
    throw e;
  }finally{
    clearTimeout(timer);
  }
}

function updateNav(){
  document.querySelectorAll('#nav button').forEach(function(b){
    b.classList.toggle('active', b.dataset.tab === tab);
  });
  if(ADMIN) navEl.classList.add('hide');
}

function cards(list){
  return '<div class="grid">' + list.map(function(p){
    return '<div class="card"><div class="cat">'+esc(p.category)+'</div><div class="name">'+esc(p.name)+'</div><div class="desc">'+esc(p.description)+'</div><div class="price">'+stars(p.stars_price)+'</div><button class="buy" data-buy="'+p.id+'">Купить за Stars</button></div>';
  }).join('') + '</div>';
}

function home(){
  return '<section class="hero"><div class="cat">PUBG MOBILE</div><h1>METRO <span class="gold">ROYALE</span></h1><div class="muted">Товары • Буст • Квесты • Фарм<br>Оплата внутри Telegram через ⭐ Stars.</div></section><div class="socials"><button class="social-btn" data-tg="https://t.me/shreksi4PubgNEWS">📢 <b>Новости</b></button><button class="social-btn" data-tg="https://t.me/chatshreksi4">💬 <b>Наш чат</b></button></div><div class="spin-shell"><div class="cat">HYPE MODE</div><h2>HYPE SPIN</h2><div class="muted">1 бесплатный SPIN за 24 часа, Metro-награды и гарантированный Upgrade Lab.</div><button class="buy" id="homeSpinBtn" style="margin-top:12px">Открыть SPIN</button></div><h3>Популярное</h3>' + cards(products.slice(0,4));
}

function bindBuyButtons(){
  document.querySelectorAll('[data-buy]').forEach(function(btn){
    btn.addEventListener('click', function(){ orderForm(Number(btn.dataset.buy)); });
  });
  const hs=document.getElementById('homeSpinBtn');
  if(hs) hs.addEventListener('click',function(){tab='spin';render();});
  bindSocials();
}

function orderForm(id){
  const p = products.find(function(x){ return Number(x.id) === Number(id); });
  if(!p) return;
  app.innerHTML = '<div class="hero"><div class="cat">'+esc(p.category)+'</div><h1>'+esc(p.name)+'</h1><div class="muted">'+esc(p.description)+'</div><div class="price">'+stars(p.stars_price)+'</div></div><div class="card"><b>Данные заказа</b><input id="uid" placeholder="UID PUBG Mobile"><input id="nick" placeholder="Игровой ник"><textarea id="comment" placeholder="Комментарий к заказу"></textarea><button class="buy" id="createOrderBtn">Создать заказ</button></div>';
  document.getElementById('createOrderBtn').addEventListener('click', function(){ createOrder(id); });
}

async function createOrder(id){
  const btn=document.getElementById('createOrderBtn');
  if(btn && btn.disabled) return;
  if(btn){btn.disabled=true;btn.textContent='Создаём заказ…';}
  try{
    const o = await api('/api/orders',{
      method:'POST',
      body:JSON.stringify({
        product_id:id,
        uid:document.getElementById('uid').value,
        nickname:document.getElementById('nick').value,
        comment:document.getElementById('comment').value
      })
    });
    showPay(o);
  }catch(e){
    if(btn){btn.disabled=false;btn.textContent='Создать заказ';}
    alert(e.message);
  }
}

function showPay(o){
  app.innerHTML = '<div class="hero"><div class="cat">ЗАКАЗ #'+o.number+'</div><h1>Заказ создан</h1><div class="muted">Оплатите заказ через Telegram Stars.</div></div><div class="card"><div class="price">'+stars(o.stars_amount)+'</div><button class="buy" id="starsBtn">Оплатить '+o.stars_amount+' ⭐</button><p class="muted">Платёж проходит внутри Telegram.</p></div>';
  document.getElementById('starsBtn').addEventListener('click', function(){ payStars(o.id); });
}

async function payStars(id){
  const btn=document.getElementById('starsBtn');
  if(btn && btn.disabled) return;
  if(btn){btn.disabled=true;btn.textContent='Открываем оплату…';}
  try{
    const d = await api('/api/orders/'+id+'/stars',{method:'POST'});
    if(tg && tg.openInvoice) tg.openInvoice(d.url,function(){ tab='orders'; render(); });
    else location.href=d.url;
  }catch(e){
    if(btn){btn.disabled=false;btn.textContent='Оплатить Stars';}
    alert(e.message);
  }
}
async function ordersHtml(){
  const list = await api('/api/orders');
  if(!list.length) return '<div class="empty">У вас пока нет заказов.</div>';
  return list.map(function(o){
    return '<div class="order"><div class="cat">ЗАКАЗ #'+o.number+'</div><div class="name">'+esc(o.product_name)+'</div><div class="row"><div class="price">'+stars(o.stars_amount)+'</div><div style="text-align:right"><span class="status">'+esc(o.status)+'</span></div></div><div class="muted">'+esc(o.created_at)+'</div></div>';
  }).join('');
}
async function spinHtml(){
  spinState=await api('/api/spin/state');
  const history=(spinState.history||[]).map(function(x){
    return '<div class="order"><span class="tier '+tierClass(x.reward_tier)+'">'+esc(x.reward_tier)+'</span><div class="name">'+esc(x.reward_name)+'</div><div class="muted">+'+x.points+' upgrade pts • '+esc(x.created_at)+'</div></div>';
  }).join('');
  const claims=(spinState.upgrade_rewards||[]).map(function(x){
    const ok=Number(spinState.upgrade_points)>=Number(x.points);
    return '<button class="claim" data-claim="'+x.points+'" '+(ok?'':'disabled')+'>'+esc(x.name)+' • '+x.points+' pts</button>';
  }).join('');
  const last=lastSpinReward?'<div class="order"><div class="cat">ПОСЛЕДНИЙ ДРОП</div><span class="tier '+tierClass(lastSpinReward.tier)+'">'+esc(lastSpinReward.tier)+'</span><div class="name">'+esc(lastSpinReward.name)+'</div><div class="muted">+'+lastSpinReward.points+' upgrade pts</div></div>':'';
  const remaining=Number(spinState.remaining_spins||0);
  const resetText=remaining>0?'Доступно сейчас: '+remaining+' из '+spinState.max_spins:'Лимит исчерпан • следующий SPIN через '+formatReset(spinState.next_reset_seconds);
  return '<section class="hero"><div class="cat">HYPE MODE</div><h1>HYPE <span class="gold">SPIN</span></h1><div class="muted">1 бесплатное вращение за 24 часа. Награды выдаются администратором в игре.</div></section>'+
    '<div class="spin-stats"><div class="spin-stat"><div class="muted">SPIN осталось</div><div class="price" id="ticketsCount">'+remaining+' / '+spinState.max_spins+'</div></div><div class="spin-stat"><div class="muted">Upgrade pts</div><div class="price" id="pointsCount">'+spinState.upgrade_points+'</div></div></div>'+
    '<div class="spin-shell"><div class="reel-window"><div class="reel-item tier-common" id="reelItem">Нажмите SPIN</div></div><button class="buy" id="spinBtn" style="margin-top:12px" '+(remaining<=0?'disabled':'')+'>'+(remaining>0?'КРУТИТЬ SPIN':'ЛИМИТ ИСЧЕРПАН')+'</button><div class="muted" style="margin-top:10px">'+resetText+'</div><div class="muted" style="margin-top:7px">Common 75% • Rare 18% • Epic 5% • Legendary 1.5% • Mythic 0.5%</div></div>'+
    last+'<h3>Upgrade Lab</h3><div class="card"><div class="muted">Очки из бесплатных спинов можно обменять на гарантированную награду.</div>'+claims+'</div>'+
    '<h3>Последние спины</h3>'+(history||'<div class="empty">История пока пустая.</div>');
}
function bindSpin(){
  const b=document.getElementById('spinBtn');
  if(b && !b.disabled) b.addEventListener('click',spinOnce);
  document.querySelectorAll('[data-claim]').forEach(function(btn){
    btn.addEventListener('click',function(){claimUpgrade(Number(btn.dataset.claim));});
  });
}
async function spinOnce(){
  const btn=document.getElementById('spinBtn');
  if(btn && btn.disabled) return;
  if(btn){btn.disabled=true;btn.textContent='КРУТИМ…';}
  const reel=document.getElementById('reelItem');
  const pool=(spinState.rewards||[]);
  let i=0;
  if(reel) reel.classList.add('spinning');
  const timer=setInterval(function(){
    if(reel && pool.length){
      const x=pool[i%pool.length]; i++;
      reel.textContent=x.name;
      reel.className='reel-item spinning '+tierClass(x.tier);
    }
  },80);
  try{
    const d=await api('/api/spin/free',{method:'POST'});
    setTimeout(async function(){
      clearInterval(timer);
      lastSpinReward=d.reward;
      if(reel){
        reel.className='reel-item '+tierClass(d.reward.tier);
        reel.textContent=d.reward.name;
      }
      try{ if(tg && tg.HapticFeedback) tg.HapticFeedback.impactOccurred(d.reward.tier==='MYTHIC'?'heavy':'medium'); }catch(_){}
      await new Promise(function(r){setTimeout(r,650);});
      showDropFx(d.reward);
      app.innerHTML=await spinHtml();
      bindSpin();
    },1800);
  }catch(e){
    clearInterval(timer);
    if(reel) reel.classList.remove('spinning');
    if(btn){btn.disabled=false;btn.textContent='КРУТИТЬ SPIN';}
    alert(e.message);
  }
}
async function claimUpgrade(points){
  try{
    const d=await api('/api/upgrade/claim',{method:'POST',body:JSON.stringify({points:points})});
    alert('Заявка на выдачу создана: '+d.reward.name);
    app.innerHTML=await spinHtml(); bindSpin();
  }catch(e){alert(e.message);}
}

function supportHtml(){
  return '<div class="hero"><div class="cat">ПОДДЕРЖКА</div><h1>Чем помочь?</h1><div class="muted">Создайте обращение — оно появится в админ-панели без лишних сообщений в чате бота.</div></div><div class="socials"><button class="social-btn" data-tg="https://t.me/shreksi4PubgNEWS">📢 <b>Новости</b></button><button class="social-btn" data-tg="https://t.me/chatshreksi4">💬 <b>Наш чат</b></button></div><div class="card"><select id="tc"><option>Вопрос по заказу</option><option>Оплата</option><option>Техническая проблема</option><option>Другое</option></select><textarea id="tm" placeholder="Опишите вопрос"></textarea><button class="buy" id="ticketBtn">Отправить</button></div>';
}
async function sendTicket(){
  try{
    const d=await api('/api/support',{method:'POST',body:JSON.stringify({category:document.getElementById('tc').value,message:document.getElementById('tm').value})});
    alert('Обращение #'+d.id+' создано');
    document.getElementById('tm').value='';
  }catch(e){ alert(e.message); }
}
async function adminHtml(){
  const results = await Promise.all([api('/api/admin/orders'),api('/api/admin/tickets'),api('/api/admin/spins'),api('/api/admin/upgrades')]);
  const a=results[0], t=results[1], spins=results[2], upgrades=results[3];
  return '<section class="hero"><div class="cat">OWNER PANEL</div><h1>Админ-панель</h1><div class="muted">Заказы: '+a.length+' • Обращения: '+t.length+' • SPIN: '+spins.length+' • Upgrade: '+upgrades.length+'</div></section><h3>Заказы</h3>' +
    a.map(function(o){
      const statuses=['Ожидает оплаты','Ожидает проверки оплаты','Оплачен','Принят','В работе','Ожидает клиента','Выполнен','Отменён','Возврат'];
      return '<div class="order"><div class="cat">#'+o.number+' • Telegram '+o.telegram_id+'</div><div class="name">'+esc(o.product_name)+'</div><div>'+stars(o.stars_amount)+' • UID '+esc(o.uid)+'</div><div class="adminline"><select id="s'+o.id+'">'+statuses.map(function(s){return '<option '+(s===o.status?'selected':'')+'>'+s+'</option>';}).join('')+'</select><button class="secondary" data-status="'+o.id+'">Сохранить</button></div></div>';
    }).join('') +
    '<h3>Выигрыши HYPE SPIN</h3>' +
    (spins.map(function(x){return '<div class="order"><span class="tier '+tierClass(x.reward_tier)+'">'+esc(x.reward_tier)+'</span><div class="name">'+esc(x.reward_name)+'</div><div class="muted">Telegram '+x.telegram_id+' • +'+x.points+' pts • '+esc(x.created_at)+'</div></div>';}).join('') || '<div class="empty">Пока нет выигрышей.</div>') +
    '<h3>Заявки Upgrade Lab</h3>' +
    (upgrades.map(function(x){return '<div class="order"><div class="name">'+esc(x.reward_name)+'</div><div class="muted">Telegram '+x.telegram_id+' • списано '+x.points_spent+' pts • '+esc(x.created_at)+'</div></div>';}).join('') || '<div class="empty">Пока нет заявок.</div>') +
    '<h3>Поддержка</h3>' +
    (t.map(function(x){return '<div class="order"><div class="cat">#'+x.id+' • '+esc(x.category)+'</div><div>'+esc(x.message)+'</div><div class="muted">Telegram '+x.telegram_id+'</div></div>';}).join('') || '<div class="empty">Обращений нет.</div>');
}
async function setStatus(id){
  try{
    await api('/api/admin/orders/'+id,{method:'PATCH',body:JSON.stringify({status:document.getElementById('s'+id).value})});
    alert('Статус обновлён');
  }catch(e){ alert(e.message); }
}

async function render(){
  updateNav();
  app.innerHTML='<div class="empty">Загрузка…</div>';
  try{
    if(ADMIN){
      app.innerHTML=await adminHtml();
      document.querySelectorAll('[data-status]').forEach(function(btn){
        btn.addEventListener('click',function(){ setStatus(Number(btn.dataset.status)); });
      });
      return;
    }
    if(tab==='home'){ app.innerHTML=home(); bindBuyButtons(); }
    else if(tab==='catalog'){ app.innerHTML='<h2>Каталог</h2>'+cards(products); bindBuyButtons(); }
    else if(tab==='spin'){ app.innerHTML=await spinHtml(); bindSpin(); }
    else if(tab==='orders'){ app.innerHTML=await ordersHtml(); }
    else if(tab==='support'){ app.innerHTML=supportHtml(); document.getElementById('ticketBtn').addEventListener('click',sendTicket); bindSocials(); }
  }catch(e){ showFatal(e.message); }
}

document.querySelectorAll('#nav button').forEach(function(b){
  b.addEventListener('click',function(){ tab=b.dataset.tab; render(); });
});

async function boot(){
  try{
    app.innerHTML='<div class="empty">Загрузка каталога…</div>';
    products=await api('/api/catalog');
    app.innerHTML='<div class="empty">Проверка Telegram…</div>';
    me=await api('/api/me');
    if(ADMIN && !me.owner) throw new Error('Нет доступа');
    render();
  }catch(e){
    showFatal(e.message + '\\n\\nОткройте приложение кнопкой из Telegram-бота.');
  }
}
boot();
})();
</script>
</body>
</html>"""
    return tpl.replace("__ADMIN__", mode).replace("__APP_NAME__", html.escape(APP_NAME))


@app.get("/", response_class=HTMLResponse)
async def miniapp():
    return page(False)


@app.get("/admin", response_class=HTMLResponse)
async def admin_page():
    return page(True)
