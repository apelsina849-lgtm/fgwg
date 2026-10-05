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
db_write_lock = asyncio.Lock()

SPIN_REWARDS = [
    {"name":"500K Metro Cash","tier":"COMMON","weight":45,"points":1},
    {"name":"Набор расходников","tier":"RARE","weight":28,"points":2},
    {"name":"Metro Starter Kit","tier":"EPIC","weight":18,"points":3},
    {"name":"Буст 3 квестов","tier":"LEGENDARY","weight":7,"points":5},
    {"name":"Премиум Metro Pack","tier":"MYTHIC","weight":2,"points":8},
]
UPGRADE_REWARDS = [
    {"points":5,"name":"Набор расходников"},
    {"points":10,"name":"Metro Starter Kit"},
    {"points":18,"name":"Премиум Metro Pack"},
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
    """)
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


async def process_update(update: dict):
    global poll_offset
    poll_offset = max(poll_offset, int(update.get("update_id", 0)) + 1)
    msg = update.get("message") or {}
    user = msg.get("from") or {}
    text = msg.get("text") or ""
    if msg and text.startswith("/start"):
        await send_start(int(msg["chat"]["id"]), int(user.get("id", 0)))
        return
    if msg and text.startswith("/shop"):
        await send_start(int(msg["chat"]["id"]), int(user.get("id", 0)))
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
            async with db_write_lock:
                conn = await db()
                try:
                    await conn.execute("UPDATE orders SET status='Оплачен',payment_method='Telegram Stars',updated_at=CURRENT_TIMESTAMP WHERE id=? AND telegram_id=?", (int(oid), int(uid)))
                    row = await (await conn.execute("SELECT number FROM orders WHERE id=?", (int(oid),))).fetchone()
                    await conn.commit()
                finally:
                    await conn.close()
            await tg("sendMessage", {"chat_id":msg["chat"]["id"],"text":f"✅ Оплата получена. Заказ #{row['number']} отмечен как оплаченный."})
        except Exception:
            pass


async def polling():
    global poll_offset
    try:
        await tg("deleteWebhook", {"drop_pending_updates":False})
        if BASE_URL:
            await tg("setChatMenuButton", {"menu_button":{"type":"web_app","text":"Открыть магазин","web_app":{"url":BASE_URL}}})
        await tg("setMyCommands", {"commands":[{"command":"start","description":"Главное меню"},{"command":"shop","description":"Открыть магазин"}]})
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


class TicketIn(BaseModel):
    category: str = Field(default="Другое", max_length=80)
    message: str = Field(min_length=3, max_length=2000)


class StatusIn(BaseModel):
    status: str


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
    try:
        await tg("sendMessage", {"chat_id":OWNER_ID,"text":f"🆕 Новый заказ #{number}\n{p['name']}\nКлиент: {u.get('first_name','')} ({u['id']})\nЦена: {p['stars_price']} ⭐"})
    except Exception:
        pass
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
            history = await (await conn.execute("SELECT reward_name,reward_tier,points,created_at FROM spin_history WHERE telegram_id=? ORDER BY id DESC LIMIT 8",(uid,))).fetchall()
        finally:
            await conn.close()
    now = int(time.time())
    return {
      "tickets":int(state["tickets"]),
      "upgrade_points":int(state["upgrade_points"]),
      "daily_available": now - int(state["last_free_spin"] or 0) >= 86400,
      "history":[dict(x) for x in history],
      "upgrade_rewards":UPGRADE_REWARDS,
      "rewards":[{"name":x["name"],"tier":x["tier"]} for x in SPIN_REWARDS]
    }


@app.post("/api/spin/free")
async def spin_free(x_telegram_init_data: str | None = Header(default=None)):
    u = await current_user(x_telegram_init_data)
    uid = int(u["id"])
    now = int(time.time())
    async with db_write_lock:
        conn = await db()
        try:
            await conn.execute("BEGIN IMMEDIATE")
            await conn.execute("INSERT OR IGNORE INTO spin_state(telegram_id) VALUES(?)",(uid,))
            state = await (await conn.execute("SELECT * FROM spin_state WHERE telegram_id=?",(uid,))).fetchone()
            daily_available = now - int(state["last_free_spin"] or 0) >= 86400
            tickets = int(state["tickets"])
            if not daily_available and tickets <= 0:
                await conn.rollback()
                raise HTTPException(429,"Бесплатные спины закончились. Следующий ежедневный спин будет доступен позже.")
            if daily_available:
                await conn.execute("UPDATE spin_state SET last_free_spin=? WHERE telegram_id=?",(now,uid))
            else:
                await conn.execute("UPDATE spin_state SET tickets=tickets-1 WHERE telegram_id=?",(uid,))
            reward = random.choices(SPIN_REWARDS, weights=[x["weight"] for x in SPIN_REWARDS], k=1)[0]
            await conn.execute("UPDATE spin_state SET upgrade_points=upgrade_points+? WHERE telegram_id=?",(reward["points"],uid))
            await conn.execute("INSERT INTO spin_history(telegram_id,reward_name,reward_tier,points) VALUES(?,?,?,?)",(uid,reward["name"],reward["tier"],reward["points"]))
            await conn.commit()
            state = await (await conn.execute("SELECT * FROM spin_state WHERE telegram_id=?",(uid,))).fetchone()
        finally:
            await conn.close()
    try:
        await tg("sendMessage",{"chat_id":OWNER_ID,"text":f"🎰 HYPE SPIN\nИгрок: {uid}\nВыпало: {reward['name']} ({reward['tier']})\nВыдача производится вручную в игре."})
    except Exception:
        pass
    return {"reward":reward,"tickets":int(state["tickets"]),"upgrade_points":int(state["upgrade_points"])}


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
    try:
        await tg("sendMessage",{"chat_id":OWNER_ID,"text":f"⚡ UPGRADE CLAIM\nИгрок: {uid}\nНаграда: {reward['name']}\nСписано очков: {reward['points']}\nВыдайте награду в игре."})
    except Exception:
        pass
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
    try: await tg("sendMessage",{"chat_id":OWNER_ID,"text":f"💬 Новое обращение #{tid}\n{body.category}\n{body.message}\nTelegram ID: {u['id']}"})
    except Exception: pass
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
    try: await tg("sendMessage",{"chat_id":row["telegram_id"],"text":f"📦 Статус заказа #{row['number']} изменён: {body.status}"})
    except Exception: pass
    return {"ok":True,"status":body.status}


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
.empty{text-align:center;padding:38px 10px;color:#89919a}.hide{display:none!important}.adminline{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.adminline select{width:auto;min-width:150px;margin:8px 0}
@media(max-width:390px){.grid{grid-template-columns:1fr}h1{font-size:25px}}
</style>
</head>
<body>
<div class="wrap">
  <div class="top"><div class="brand">ШРЕКСИЧ <b>SHOP</b></div><div class="pill">PUBG MOBILE</div></div>
  <main id="app"><div class="empty">Загрузка магазина…</div></main>
</div>
<div class="nav" id="nav">
  <button data-tab="home">Главная</button><button data-tab="catalog">Каталог</button><button data-tab="orders">Заказы</button><button data-tab="support">Поддержка</button>
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
let tab = new URLSearchParams(location.search).get('tab') || (ADMIN ? 'admin' : 'home');

function esc(v){
  return String(v == null ? '' : v).replace(/[&<>"']/g,function(m){
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m];
  });
}
function rub(n){ return Number(n).toLocaleString('ru-RU') + ' ₽'; }

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
    return '<div class="card"><div class="cat">'+esc(p.category)+'</div><div class="name">'+esc(p.name)+'</div><div class="desc">'+esc(p.description)+'</div><div class="price">'+rub(p.price)+'</div><button class="buy" data-buy="'+p.id+'">Купить</button></div>';
  }).join('') + '</div>';
}

function home(){
  return '<section class="hero"><div class="cat">PUBG MOBILE</div><h1>METRO <span class="gold">ROYALE</span></h1><div class="muted">Товары • Буст • Квесты • Фарм<br>Быстрое оформление и отслеживание заказа прямо в Telegram.</div></section><h3>Популярное</h3>' + cards(products.slice(0,4));
}

function bindBuyButtons(){
  document.querySelectorAll('[data-buy]').forEach(function(btn){
    btn.addEventListener('click', function(){ orderForm(Number(btn.dataset.buy)); });
  });
}

function orderForm(id){
  const p = products.find(function(x){ return Number(x.id) === Number(id); });
  if(!p) return;
  app.innerHTML = '<div class="hero"><div class="cat">'+esc(p.category)+'</div><h1>'+esc(p.name)+'</h1><div class="muted">'+esc(p.description)+'</div><div class="price">'+rub(p.price)+'</div></div><div class="card"><b>Данные заказа</b><input id="uid" placeholder="UID PUBG Mobile"><input id="nick" placeholder="Игровой ник"><textarea id="comment" placeholder="Комментарий к заказу"></textarea><button class="buy" id="createOrderBtn">Создать заказ</button></div>';
  document.getElementById('createOrderBtn').addEventListener('click', function(){ createOrder(id); });
}

async function createOrder(id){
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
  }catch(e){ alert(e.message); }
}

function showPay(o){
  app.innerHTML = '<div class="hero"><div class="cat">ЗАКАЗ #'+o.number+'</div><h1>Заказ создан</h1><div class="muted">Выберите способ оплаты.</div></div><div class="card"><div class="price">'+rub(o.amount)+'</div><button class="buy" id="starsBtn">Оплатить '+o.stars_amount+' ⭐</button><div style="height:8px"></div><button class="secondary" style="width:100%" id="manualBtn">Ручная оплата</button><p class="muted">'+esc(o.manual_payment)+'</p></div>';
  document.getElementById('starsBtn').addEventListener('click', function(){ payStars(o.id); });
  document.getElementById('manualBtn').addEventListener('click', function(){ manualPay(o.id); });
}

async function payStars(id){
  try{
    const d = await api('/api/orders/'+id+'/stars',{method:'POST'});
    if(tg && tg.openInvoice) tg.openInvoice(d.url,function(){ tab='orders'; render(); });
    else location.href=d.url;
  }catch(e){ alert(e.message); }
}
async function manualPay(id){
  try{
    const d = await api('/api/orders/'+id+'/manual',{method:'POST'});
    alert('Заявка на проверку оплаты отправлена.\\n\\n'+d.details);
    tab='orders'; render();
  }catch(e){ alert(e.message); }
}
async function ordersHtml(){
  const list = await api('/api/orders');
  if(!list.length) return '<div class="empty">У вас пока нет заказов.</div>';
  return list.map(function(o){
    return '<div class="order"><div class="cat">ЗАКАЗ #'+o.number+'</div><div class="name">'+esc(o.product_name)+'</div><div class="row"><div class="price">'+rub(o.amount)+'</div><div style="text-align:right"><span class="status">'+esc(o.status)+'</span></div></div><div class="muted">'+esc(o.created_at)+'</div></div>';
  }).join('');
}
function supportHtml(){
  return '<div class="hero"><div class="cat">ПОДДЕРЖКА</div><h1>Чем помочь?</h1><div class="muted">Создайте обращение — владелец получит уведомление в Telegram.</div></div><div class="card"><select id="tc"><option>Вопрос по заказу</option><option>Оплата</option><option>Техническая проблема</option><option>Другое</option></select><textarea id="tm" placeholder="Опишите вопрос"></textarea><button class="buy" id="ticketBtn">Отправить</button></div>';
}
async function sendTicket(){
  try{
    const d=await api('/api/support',{method:'POST',body:JSON.stringify({category:document.getElementById('tc').value,message:document.getElementById('tm').value})});
    alert('Обращение #'+d.id+' создано');
    document.getElementById('tm').value='';
  }catch(e){ alert(e.message); }
}
async function adminHtml(){
  const results = await Promise.all([api('/api/admin/orders'),api('/api/admin/tickets')]);
  const a=results[0], t=results[1];
  return '<section class="hero"><div class="cat">OWNER PANEL</div><h1>Админ-панель</h1><div class="muted">Заказы: '+a.length+' • Обращения: '+t.length+'</div></section><h3>Заказы</h3>' +
    a.map(function(o){
      const statuses=['Ожидает оплаты','Ожидает проверки оплаты','Оплачен','Принят','В работе','Ожидает клиента','Выполнен','Отменён','Возврат'];
      return '<div class="order"><div class="cat">#'+o.number+' • Telegram '+o.telegram_id+'</div><div class="name">'+esc(o.product_name)+'</div><div>'+rub(o.amount)+' • UID '+esc(o.uid)+'</div><div class="adminline"><select id="s'+o.id+'">'+statuses.map(function(s){return '<option '+(s===o.status?'selected':'')+'>'+s+'</option>';}).join('')+'</select><button class="secondary" data-status="'+o.id+'">Сохранить</button></div></div>';
    }).join('') +
    '<h3>Поддержка</h3>' +
    t.map(function(x){return '<div class="order"><div class="cat">#'+x.id+' • '+esc(x.category)+'</div><div>'+esc(x.message)+'</div><div class="muted">Telegram '+x.telegram_id+'</div></div>';}).join('');
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
    else if(tab==='orders'){ app.innerHTML=await ordersHtml(); }
    else if(tab==='support'){ app.innerHTML=supportHtml(); document.getElementById('ticketBtn').addEventListener('click',sendTicket); }
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
    showFatal(e.message + '<br><br>Откройте приложение кнопкой из Telegram-бота.');
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
