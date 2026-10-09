"""SHREKSICH AI: isolated community bot MVP. No access to shop balances."""
import asyncio
import json
import logging
import os
import random
import re
import sqlite3
import time
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path

TOKEN = os.environ["SHREKSICH_AI_BOT_TOKEN"]
ADMIN_IDS = {int(x) for x in os.getenv("SHREKSICH_AI_ADMIN_IDS", "").split(",") if x.strip().isdigit()}
DB_PATH = os.getenv("SHREKSICH_AI_DB", "shreksich_ai.sqlite3")
SHOP_URL = os.getenv("SHREKSICH_SHOP_URL", "https://shreksich-app-y25m-production.up.railway.app/")
AI_URL = os.getenv("SHREKSICH_AI_API_URL", "")
AI_KEY = os.getenv("SHREKSICH_AI_API_KEY", "")
AI_MODEL = os.getenv("SHREKSICH_AI_MODEL", "")
logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger("shreksich-ai")
QUESTIONS = [
    ("Как называется режим PUBG Mobile, посвящённый добыче и эвакуации?", ["Metro Royale", "Arena", "Payload"], 0),
    ("Что важнее при эвакуации с ценным лутом?", ["Игнорировать карту", "Планировать безопасный маршрут", "Выбрасывать всё"], 1),
    ("Что важно проверить перед эвакуацией в Metro Royale?", ["Маршрут до точки выхода", "Цвет интерфейса", "Количество друзей"], 0),
]
SCAM = re.compile(r"(?:telegram\.gift|t\.me/[^\s]+\\?start=|бесплатн.{0,20}(?:uc|зв[её]зд)|пришли.{0,20}(?:пароль|код входа)|переведи.{0,30}(?:на карту|на кошел[её]к))", re.I)
FLOOD = {}
def db():
    c = sqlite3.connect(DB_PATH)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, chat_id INTEGER, user_id INTEGER, kind TEXT, detail TEXT, ts INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS quiz(chat_id INTEGER PRIMARY KEY, question INTEGER, expires INTEGER, winner INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS settings(chat_id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL, enabled INTEGER NOT NULL DEFAULT 1, interval_minutes INTEGER NOT NULL DEFAULT 30, next_quiz INTEGER NOT NULL DEFAULT 0)")
    c.execute("CREATE TABLE IF NOT EXISTS scores(chat_id INTEGER,user_id INTEGER,name TEXT,wins INTEGER DEFAULT 0,PRIMARY KEY(chat_id,user_id))")
    c.commit()
    return c
def api(method, payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request("https://api.telegram.org/bot"+TOKEN+"/"+method, data=data, headers={"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            obj = json.load(response)
    except urllib.error.HTTPError as exc:
        details=exc.read(1000).decode("utf-8","replace")
        raise RuntimeError(f"Telegram {method}: HTTP {exc.code}: {details}") from exc
    if not obj.get("ok"): raise RuntimeError(str(obj))
    return obj["result"]
async def call(method, **kwargs):
    return await asyncio.to_thread(api, method, kwargs)
async def send(chat, text, **kwargs):
    return await call("sendMessage", chat_id=chat, text=text[:4000], **kwargs)
def owner_chat(uid):
    with db() as conn:
        return conn.execute("SELECT chat_id,enabled,interval_minutes,next_quiz FROM settings WHERE owner_id=? ORDER BY chat_id LIMIT 1",(uid,)).fetchone()
def group_owner(cid,uid):
    try:
        member=api("getChatMember",{"chat_id":cid,"user_id":uid})
        return member.get("status")=="creator"
    except Exception:
        LOG.exception("Cannot verify group creator")
        return False
def admin_menu(row):
    cid,enabled,interval,next_quiz=row
    return keyboard([
        [{"text":"🎮 Запустить викторину","callback_data":"admin:quiz"}],
        [{"text":("⏸ Остановить" if enabled else "▶️ Включить")+" автовикторины","callback_data":"admin:toggle"}],
        [{"text":"⏱ 15 мин","callback_data":"admin:interval:15"},{"text":"⏱ 30 мин","callback_data":"admin:interval:30"},{"text":"⏱ 60 мин","callback_data":"admin:interval:60"}],
        [{"text":"🔄 Обновить","callback_data":"admin:refresh"}],
    ])
def admin_text(row):
    cid,enabled,interval,next_quiz=row
    return f"🐸 SHREKSICH AI • УПРАВЛЕНИЕ\\n\\nЧат: {cid}\\nАвтовикторины: {'включены' if enabled else 'выключены'}\\nИнтервал: {interval} мин\\n\\nНастройки доступны только владельцу привязанного чата."
async def periodic_quizzes():
    while True:
        await asyncio.sleep(30)
        now=int(time.time())
        with db() as conn:
            rows=conn.execute("SELECT chat_id,interval_minutes FROM settings WHERE enabled=1 AND next_quiz<=?",(now,)).fetchall()
            for cid,minutes in rows:
                conn.execute("UPDATE settings SET next_quiz=? WHERE chat_id=?",(now+minutes*60,cid))
        for cid,_ in rows:
            try:
                await quiz_start(cid)
            except Exception:
                LOG.exception("Scheduled quiz failed in chat %s",cid)
def leaderboard(cid):
    with db() as conn:
        rows=conn.execute("SELECT name,wins FROM scores WHERE chat_id=? ORDER BY wins DESC LIMIT 10",(cid,)).fetchall()
    return "🏆 РЕЙТИНГ\n\n"+("\n".join(f"{i}. {name} — {wins}" for i,(name,wins) in enumerate(rows,1)) if rows else "Победителей пока нет.")
def keyboard(rows):
    return {"inline_keyboard": rows}
def menu():
    return keyboard([
        [{"text":"🤖 ИИ-помощник","callback_data":"page:ai"}],
        [{"text":"🛒 Магазин","url":SHOP_URL}],
    ])
def back():
    return keyboard([[{"text":"⬅️ Главное меню","callback_data":"page:home"}]])
def home_text():
    return "🐸 ШРЕКСИЧ • ИИ-ПОМОЩНИК\n\n🤖 Задай вопрос командой /ai или упомяни @Shrekchataibot в чате.\n🛒 Официальный магазин — по кнопке ниже."
async def edit(chat, message_id, text, markup=None):
    return await call("editMessageText", chat_id=chat, message_id=message_id, text=text, reply_markup=markup or back())
async def quiz_start(cid, message_id=None):
    now=int(time.time())
    with db() as conn:
        row=conn.execute("SELECT question,expires,winner FROM quiz WHERE chat_id=?",(cid,)).fetchone()
        if row and row[1]>now and row[2] is None:
            index=row[0]
        else:
            index=random.randrange(len(QUESTIONS))
            conn.execute("INSERT OR REPLACE INTO quiz VALUES(?,?,?,NULL)",(cid,index,now+120))
    question,answers,_=QUESTIONS[index]
    text="🎮 ВИКТОРИНА • 2 МИНУТЫ\n\n"+question+"\n\nВыбери правильный ответ:"
    buttons=keyboard([[{"text":f"{i+1}. {answer}","callback_data":f"quiz:answer:{index}:{i}"}] for i,answer in enumerate(answers)]+[[{"text":"⬅️ Главное меню","callback_data":"page:home"}]])
    if message_id:
        await edit(cid,message_id,text,buttons)
    else:
        await send(cid,text,reply_markup=buttons)
async def handle_callback(query):
    qid=query["id"]
    data=query.get("data","")
    msg=query.get("message") or {}
    cid=(msg.get("chat") or {}).get("id")
    mid=msg.get("message_id")
    uid=(query.get("from") or {}).get("id")
    if not cid or not mid or not uid:
        await call("answerCallbackQuery",callback_query_id=qid)
        return
    if data.startswith("admin:") and (msg.get("chat") or {}).get("type")=="private":
        row=owner_chat(uid)
        if not row:
            await call("answerCallbackQuery",callback_query_id=qid,text="Нет доступа к настройкам",show_alert=True)
            return
        if data=="admin:quiz":
            await quiz_start(row[0])
        elif data=="admin:toggle":
            with db() as conn:
                conn.execute("UPDATE settings SET enabled=1-enabled,next_quiz=? WHERE chat_id=?",(int(time.time())+row[2]*60,row[0]))
        elif data.startswith("admin:interval:"):
            minutes=int(data.rsplit(":",1)[1])
            if minutes in (15,30,60):
                with db() as conn:
                    conn.execute("UPDATE settings SET interval_minutes=?,next_quiz=? WHERE chat_id=?",(minutes,int(time.time())+minutes*60,row[0]))
        row=owner_chat(uid)
        try: await edit(cid,mid,admin_text(row),admin_menu(row))
        except Exception: LOG.exception("Admin menu edit failed")
        try: await call("answerCallbackQuery",callback_query_id=qid)
        except Exception: pass
        return
    notice=""
    try:
        await call("answerCallbackQuery",callback_query_id=qid)
    except Exception as exc:
        LOG.warning("Callback acknowledgement failed: %s",exc)
    try:
        if data=="page:home":
            await edit(cid,mid,home_text(),menu())
        elif data=="page:help":
            await edit(cid,mid,"📖 ПОМОЩЬ\n\n🎮 Викторина — отвечай кнопками\n🤖 /ai твой вопрос — спросить ИИ\n🛒 Магазин — перейти к покупкам\n\nВыбери раздел ниже.",keyboard([[{"text":"🎮 Викторина","callback_data":"quiz:new"}],[{"text":"⬅️ Главное меню","callback_data":"page:home"}]]))
        elif data=="page:ai":
            await edit(cid,mid,"🤖 ИИ-ПОМОЩНИК\n\nНапиши в чат команду:\n/ai твой вопрос\n\nСейчас отвечает встроенный помощник без API-ключа.",back())
        elif data=="quiz:new":
            await quiz_start(cid,mid)
        elif data.startswith("quiz:answer:"):
            _,_,question_id,answer_id=data.split(":")
            now=int(time.time())
            with db() as conn:
                row=conn.execute("SELECT question,expires,winner FROM quiz WHERE chat_id=?",(cid,)).fetchone()
                if not row or row[1]<now or row[0]!=int(question_id):
                    notice="⏳ Этот вопрос уже неактуален."
                elif row[2] is not None:
                    notice="🏆 На этот вопрос уже ответили."
                elif int(answer_id)!=QUESTIONS[row[0]][2]:
                    notice="❌ Неверно. Попробуй ещё!"
                else:
                    conn.execute("UPDATE quiz SET winner=? WHERE chat_id=? AND winner IS NULL",(uid,cid))
                    conn.execute("INSERT OR REPLACE INTO scores VALUES(?,?,?,COALESCE((SELECT wins FROM scores WHERE chat_id=? AND user_id=?),0)+1)",(cid,uid,"Игрок",cid,uid))
                    notice="🏆 Верно! Ты победил!"
                    await edit(cid,mid,"🏆 ВИКТОРИНА ЗАВЕРШЕНА\n\nПравильный ответ: "+QUESTIONS[row[0]][1][int(answer_id)]+"\n\n🎉 Победитель определён!",keyboard([[{"text":"🎮 Новая викторина","callback_data":"quiz:new"}],[{"text":"⬅️ Главное меню","callback_data":"page:home"}]]))
        else:
            notice="Неизвестная кнопка."
    except Exception:
        LOG.exception("Callback failed")
        notice="Не удалось обновить сообщение. Попробуй ещё раз."
    finally:
        if notice:
            LOG.info("Callback result: %s",notice)
def log(chat, user, kind, detail):
    with db() as c:
        c.execute("INSERT INTO events(chat_id,user_id,kind,detail,ts) VALUES(?,?,?,?,?)",(chat,user,kind,detail[:500],int(time.time())))
def offline_answer(question):
    q=question.lower().strip()
    if not q:
        return "🐸 Напиши свой вопрос. Например: как открыть магазин или что такое Metro Royale?"
    if any(x in q for x in ("привет", "здравствуй", "хай", "hello")):
        return "🐸 Привет! Я помощник сообщества Шрексич. Могу рассказать о магазине, Metro Royale и правилах безопасности."
    if any(x in q for x in ("магазин", "купить", "каталог", "товар", "продаж")):
        return "🛒 Официальный магазин Шрексич: "+SHOP_URL+"\\nАктуальные товары, наличие и цены смотри в каталоге."
    if any(x in q for x in ("заказ", "достав", "оплат", "покупк")):
        return "📦 Проверь информацию о заказе в официальном магазине. Я не вижу твои покупки и не могу подтвердить оплату или доставку."
    if any(x in q for x in ("metro", "метро", "pubg", "пабг", "эвакуац", "лут")):
        return "🎮 В Metro Royale важно заранее планировать путь к эвакуации, следить за снаряжением и не рисковать ценным лутом без необходимости. Уточни вопрос — например, про выходы или экипировку."
    if any(x in q for x in ("викторин", "игр", "вопрос", "quiz")):
        return "🎮 Нажми «Викторина» в меню или отправь /quiz. Ответы выбираются кнопками, денежные награды не начисляются."
    if any(x in q for x in ("мошен", "обман", "скам", "безопас", "пароль", "код")):
        return "🛡 Не передавай коды входа и пароли, не переходи по сомнительным ссылкам и проверяй покупки только через официальный магазин."
    if any(x in q for x in ("обмен", "трейд", "trade")):
        return "🤝 Трейды пока не поддерживаются ботом Шрексич. Не передавай предметы незнакомцам под обещания обмена."
    return "🐸 Пока я работаю без внешней ИИ-модели и могу помочь с магазином, PUBG Metro Royale, викторинами и безопасностью. Уточни вопрос по одной из этих тем."
async def ask_ai(question):
    question=question.strip()[:900]
    if not question:
        return "Напиши вопрос после /ai."
    def query():
        system=("Ты Шрексич AI, дружелюбный помощник сообщества PUBG Mobile Metro Royale. "
                "Отвечай по-русски, по делу, до 700 символов. "
                "Не придумывай сведения о заказах, балансе, ценах и наличии товаров. "
                "Никогда не проси пароль, код входа или данные карты.")
        if AI_URL and AI_KEY and AI_MODEL:
            body={"model":AI_MODEL,"messages":[{"role":"system","content":system},{"role":"user","content":question}],"max_tokens":300}
            req=urllib.request.Request(AI_URL,data=json.dumps(body).encode(),headers={"Authorization":"Bearer "+AI_KEY,"Content-Type":"application/json"})
            with urllib.request.urlopen(req,timeout=17) as r:
                return json.load(r)["choices"][0]["message"]["content"]
        # Legacy public anonymous endpoint: best-effort, not guaranteed or private.
        prompt=system+"\\nВопрос: "+question+"\\nОтвет:"
        url="https://text.pollinations.ai/"+urllib.parse.quote(prompt,safe="")
        req=urllib.request.Request(url,headers={"User-Agent":"ShreksichCommunityBot/1.0"})
        with urllib.request.urlopen(req,timeout=17) as r:
            result=r.read(5000).decode("utf-8","replace").strip()
            if not result or result.startswith("<") or len(result)>4000:
                raise ValueError("Invalid anonymous AI response")
            return result[:1500]
    try:
        return await asyncio.to_thread(query)
    except Exception:
        LOG.exception("Free AI endpoint unavailable")
        q=question.lower()
        if "магазин" in q or "купить" in q:
            return "🛒 Официальный магазин: "+SHOP_URL
        if "метро" in q or "metro" in q or "pubg" in q:
            return "🎮 В Metro Royale полезно заранее планировать маршрут эвакуации, следить за снаряжением и не рисковать ценным лутом без необходимости."
        return offline_answer(question)
async def handle(msg):
    chat = msg.get("chat",{})
    user = msg.get("from",{})
    cid,uid=chat.get("id"),user.get("id")
    if not cid or not uid or user.get("is_bot"): return
    text=(msg.get("text") or msg.get("caption") or "").strip()
    if not text: return
    now=time.time()
    if chat.get("type") in ("group","supergroup"):
        key=(cid,uid)
        recent=[t for t in FLOOD.get(key,[]) if now-t<8]
        recent.append(now); FLOOD[key]=recent
        if len(recent)>7 and uid not in ADMIN_IDS:
            log(cid,uid,"flood","8 messages / 8 seconds")
            return
        if SCAM.search(text):
            log(cid,uid,"suspected_scam",text)
            await send(cid,"⚠️ Возможная мошенническая схема. Не передавайте пароли и коды. Используйте только официальный магазин.",reply_parameters={"message_id":msg["message_id"],"allow_sending_without_reply":True})
            return
    cmd=text.split()[0].split("@")[0].lower()
    if chat.get("type")=="private":
        row=owner_chat(uid)
        if row:
            await send(cid,admin_text(row),reply_markup=admin_menu(row))
        else:
            await send(cid,"🔒 Настройки доступны только владельцу чата.\\n\\nЧтобы привязать чат, его создатель должен отправить /setup в самом чате.")
        return
    if chat.get("type") not in ("group","supergroup"):
        return
    if cmd=="/setup":
        if not await asyncio.to_thread(group_owner,cid,uid):
            await send(cid,"🔒 Привязать чат может только его создатель.")
            return
        with db() as conn:
            conn.execute("INSERT OR REPLACE INTO settings(chat_id,owner_id,enabled,interval_minutes,next_quiz) VALUES(?,?,1,30,?)",(cid,uid,int(time.time())+1800))
        await send(cid,"✅ SHREKSICH AI подключён к чату. Автовикторины — каждые 30 минут.\\n🔒 Управление доступно создателю чата в личных сообщениях @Shrekchataibot.")
        return
    with db() as conn:
        bound=conn.execute("SELECT 1 FROM settings WHERE chat_id=?",(cid,)).fetchone()
    if not bound:
        return
    if chat.get("type") in ("group","supergroup") and not text.startswith("/"):
        reply=msg.get("reply_to_message") or {}
        botname=(reply.get("from") or {}).get("username","").lower()
        if botname=="shrekchataibot" or "@shrekchataibot" in text.lower():
            question=re.sub(r"@shrekchataibot","",text,flags=re.I).strip()
            await send(cid,await ask_ai(question),reply_parameters={"message_id":msg["message_id"],"allow_sending_without_reply":True})
        return
    if cmd in ("/start","/help","/menu"):
        await send(cid,home_text(),reply_markup=menu())
    elif cmd=="/top": await send(cid,leaderboard(cid))
    elif cmd=="/shop": await send(cid,SHOP_URL)
    elif cmd=="/ping": await send(cid,"✅ Бот на связи. Меню: /start")
    elif cmd=="/ai":
        question=text.partition(" ")[2].strip()
        if not question: await send(cid,"Напиши /ai и свой вопрос.")
        else: await send(cid,await ask_ai(question))
    elif cmd=="/quiz":
        await quiz_start(cid)
    elif cmd=="/answer":
        choice=text.partition(" ")[2].strip()
        with db() as c:
            row=c.execute("SELECT question,expires,winner FROM quiz WHERE chat_id=?",(cid,)).fetchone()
            if not row or row[1]<int(now) or row[2] is not None: reply="Активной викторины нет."
            elif choice not in ("1","2","3"): reply="Ответь /answer 1, 2 или 3."
            elif int(choice)-1==QUESTIONS[row[0]][2]:
                changed=c.execute("UPDATE quiz SET winner=? WHERE chat_id=? AND winner IS NULL",(uid,cid)).rowcount
                reply="🏆 Правильно! Победитель определён." if changed else "Уже есть победитель."
                if changed: log(cid,uid,"quiz_won","no monetary reward")
            else: reply="Неверный ответ."
        await send(cid,reply)
    elif cmd=="/guardstats" and uid in ADMIN_IDS:
        with db() as c: rows=c.execute("SELECT kind,COUNT(*) FROM events WHERE chat_id=? AND ts>? GROUP BY kind",(cid,int(now)-86400)).fetchall()
        await send(cid,"События за 24 часа:\n"+(" | ".join(f"{k}: {n}" for k,n in rows) or "Нет событий"))
async def main():
    db().close()
    me=await call("getMe")
    LOG.info("Started bot @%s",me.get("username"))
    offset=0
    asyncio.create_task(periodic_quizzes())
    while True:
        try:
            updates=await call("getUpdates",offset=offset,timeout=15,allowed_updates=["message","callback_query"])
            for update in updates:
                offset=update["update_id"]+1
                LOG.info("Update received: %s", "callback" if "callback_query" in update else "message")
                try:
                    if "callback_query" in update:
                        await handle_callback(update["callback_query"])
                    else:
                        await handle(update.get("message",{}))
                except Exception: LOG.exception("Update failed")
        except Exception:
            LOG.exception("Polling error")
            await asyncio.sleep(5)
if __name__=="__main__": asyncio.run(main())
