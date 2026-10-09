"""SHREKSICH AI: isolated community bot MVP. No access to shop balances."""
import asyncio
import base64
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
VISION_MODEL = os.getenv("SHREKSICH_VISION_MODEL", "")
TRANSCRIBE_URL = os.getenv("SHREKSICH_TRANSCRIBE_URL", "")
VOICE_MODEL = os.getenv("SHREKSICH_VOICE_MODEL", "")
TTS_URL = os.getenv("SHREKSICH_TTS_URL", "")
TTS_MODEL = os.getenv("SHREKSICH_TTS_MODEL", "")
logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger("shreksich-ai")
QUESTIONS = [
    ("Как называется режим с добычей и эвакуацией?", ["Metro Royale","Arena","Payload"], 0),
    ("Что проверить перед эвакуацией?", ["Безопасный маршрут","Цвет меню","Ник"], 0),
    ("Что помогает услышать врага?", ["Наушники","Скин","Аватар"], 0),
    ("Что брать для лечения?", ["Аптечки","Краску","Лишний прицел"], 0),
    ("Что делать при нехватке патронов?", ["Искать выход","Стрелять в воздух","Бежать в бой"], 0),
    ("Как уменьшить риск потери экипировки?", ["Подбирать снаряжение по риску","Не брать лечение","Игнорировать карту"], 0),
    ("Что помогает команде?", ["Голосовая связь","Случайные маршруты","Молчание"], 0),
    ("Что делать при засаде у выхода?", ["Искать другой путь","Бежать напролом","Выбросить оружие"], 0),
    ("Как проверить подозрительную комнату?", ["Осмотреть углы","Войти спиной","Не смотреть"], 0),
    ("Для чего запас расходников?", ["Для выживания","Для аватара","Для FPS"], 0),
    ("Что важно при выборе оружия?", ["Патроны и дистанция","Цвет","Название"], 0),
    ("Почему опасно стоять на открытом месте?", ["Можно попасть под огонь","Пропадёт ник","Упадёт уровень"], 0),
    ("Что сделать после получения ценного лута?", ["Оценить путь выхода","Искать бой","Выбросить броню"], 0),
    ("Что делать, если напарник ранен?", ["Проверить угрозу","Бежать без прикрытия","Игнорировать врагов"], 0),
    ("Как избежать внезапного боя?", ["Следить за звуками","Играть без звука","Не смотреть"], 0),
    ("Что полезно при небольшом бюджете?", ["Недорогие рейды","Рисковать всем","Не брать патроны"], 0),
    ("Что проверить перед рейдом?", ["Броню, патроны и лечение","Язык телефона","Аватар"], 0),
    ("Что помогает контролировать стрельбу?", ["Контроль отдачи","Случайные прыжки","Выключенный прицел"], 0),
    ("Почему опасен бесплатный лут от незнакомцев?", ["Возможен обман","Всегда безопасно","Это официальный обмен"], 0),
    ("Что важнее при отходе после боя?", ["Укрытия и маршрут","Цвет прицела","Эмоции"], 0),
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
    c.execute("CREATE TABLE IF NOT EXISTS quiz_history(chat_id INTEGER,question INTEGER,played_at INTEGER,PRIMARY KEY(chat_id,question))")
    c.execute("CREATE TABLE IF NOT EXISTS profiles(chat_id INTEGER,user_id INTEGER,name TEXT,xp INTEGER DEFAULT 0,last_xp INTEGER DEFAULT 0,PRIMARY KEY(chat_id,user_id))")
    c.execute("CREATE TABLE IF NOT EXISTS memory(chat_id INTEGER,user_id INTEGER,role TEXT,content TEXT,ts INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS preferences(chat_id INTEGER PRIMARY KEY,persona TEXT DEFAULT 'friendly',ai_enabled INTEGER DEFAULT 1,level_enabled INTEGER DEFAULT 1)")
    c.execute("CREATE TABLE IF NOT EXISTS daily_tasks(chat_id INTEGER,user_id INTEGER,day TEXT,messages INTEGER DEFAULT 0,questions INTEGER DEFAULT 0,claimed INTEGER DEFAULT 0,PRIMARY KEY(chat_id,user_id,day))")
    c.execute("CREATE TABLE IF NOT EXISTS achievements(chat_id INTEGER,user_id INTEGER,code TEXT,awarded_at INTEGER,PRIMARY KEY(chat_id,user_id,code))")
    c.execute("CREATE TABLE IF NOT EXISTS bot_options(chat_id INTEGER PRIMARY KEY,cooldown INTEGER DEFAULT 15,reward INTEGER DEFAULT 25)")
    c.execute("CREATE TABLE IF NOT EXISTS user_preferences(user_id INTEGER PRIMARY KEY,active_chat INTEGER,privacy INTEGER DEFAULT 1,ai_memory INTEGER DEFAULT 1,play_style TEXT DEFAULT '',fav_map TEXT DEFAULT '')")
    c.execute("CREATE TABLE IF NOT EXISTS teammates(chat_id INTEGER,user_id INTEGER PRIMARY KEY,mode TEXT,style TEXT,created_at INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS seasons(chat_id INTEGER PRIMARY KEY,season_start INTEGER NOT NULL)")
    c.execute("CREATE TABLE IF NOT EXISTS seasonal_xp(chat_id INTEGER,user_id INTEGER,season INTEGER,xp INTEGER DEFAULT 0,PRIMARY KEY(chat_id,user_id,season))")
    c.execute("CREATE TABLE IF NOT EXISTS moderation(chat_id INTEGER PRIMARY KEY,anti_scam INTEGER DEFAULT 1,anti_flood INTEGER DEFAULT 1)")
    c.execute("CREATE TABLE IF NOT EXISTS events_schedule(chat_id INTEGER PRIMARY KEY,title TEXT,starts_at INTEGER,created_by INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS event_signups(chat_id INTEGER,user_id INTEGER,PRIMARY KEY(chat_id,user_id))")
    c.execute("CREATE TABLE IF NOT EXISTS battle_rewards(chat_id INTEGER,user_id INTEGER,season INTEGER,level INTEGER,PRIMARY KEY(chat_id,user_id,season,level))")
    c.execute("CREATE TABLE IF NOT EXISTS challenges(chat_id INTEGER,user_id INTEGER,day TEXT,kind TEXT,completed INTEGER DEFAULT 0,PRIMARY KEY(chat_id,user_id,day,kind))")
    c.execute("CREATE TABLE IF NOT EXISTS duels(id INTEGER PRIMARY KEY AUTOINCREMENT,chat_id INTEGER,challenger INTEGER,opponent INTEGER,question INTEGER,answer INTEGER,created_at INTEGER,finished INTEGER DEFAULT 0)")
    c.execute("CREATE TABLE IF NOT EXISTS usage_stats(chat_id INTEGER,user_id INTEGER,kind TEXT,ts INTEGER,success INTEGER DEFAULT 1)")
    c.execute("CREATE TABLE IF NOT EXISTS ai_options(chat_id INTEGER PRIMARY KEY,voice_enabled INTEGER DEFAULT 1,images_enabled INTEGER DEFAULT 1,duels_enabled INTEGER DEFAULT 1)")
    c.execute("CREATE TABLE IF NOT EXISTS raid_history(chat_id INTEGER,user_id INTEGER,ts INTEGER,investment INTEGER,loot INTEGER,escaped INTEGER)")
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
def telegram_file(file_id,limit=8_000_000):
    info=api("getFile",{"file_id":file_id})
    path=info["file_path"]
    if info.get("file_size",0)>limit: raise ValueError("File too large")
    url="https://api.telegram.org/file/bot"+TOKEN+"/"+path
    with urllib.request.urlopen(url,timeout=20) as response:
        data=response.read(limit+1)
    if len(data)>limit: raise ValueError("File too large")
    return data

def local_image_caption(file_id):
    import io
    from PIL import Image
    from transformers import BlipProcessor, BlipForConditionalGeneration
    import torch
    global _BLIP_CACHE
    if "_BLIP_CACHE" not in globals():
        model_name=os.getenv("SHREKSICH_LOCAL_VISION_MODEL","Salesforce/blip-image-captioning-base")
        processor=BlipProcessor.from_pretrained(model_name)
        model=BlipForConditionalGeneration.from_pretrained(model_name).to("cpu").eval()
        _BLIP_CACHE=(processor,model)
    processor,model=_BLIP_CACHE
    photo=Image.open(io.BytesIO(telegram_file(file_id,limit=8_000_000))).convert("RGB")
    photo.thumbnail((768,768))
    inputs=processor(images=photo,return_tensors="pt")
    with torch.inference_mode():
        result=model.generate(**inputs,max_new_tokens=65,num_beams=3)
    return processor.decode(result[0],skip_special_tokens=True).strip()

def vision_query(file_id,caption=""):
    if AI_URL and AI_KEY and VISION_MODEL:
        image=telegram_file(file_id,limit=8_000_000)
        encoded=base64.b64encode(image).decode("ascii")
        question=caption.strip()[:500] or "Что изображено на фото?"
        prompt=("Отвечай по-русски. Анализируй только видимые детали. Если это PUBG Mobile Metro Royale, "
                "опиши снаряжение и риски, но не выдумывай статистику или стоимость предметов. Вопрос: "+question)
        body={"model":VISION_MODEL,"messages":[{"role":"user","content":[
            {"type":"text","text":prompt},
            {"type":"image_url","image_url":{"url":"data:image/jpeg;base64,"+encoded}}
        ]}],"max_tokens":650}
        request=urllib.request.Request(AI_URL,data=json.dumps(body).encode(),headers={"Authorization":"Bearer "+AI_KEY,"Content-Type":"application/json"})
        with urllib.request.urlopen(request,timeout=45) as response:
            result=json.load(response)["choices"][0]["message"]["content"]
        if isinstance(result,list):
            result=" ".join(x.get("text","") for x in result if isinstance(x,dict))
        return str(result).strip()[:3500]
    description=local_image_caption(file_id)
    return ("📸 Локальный анализ фото (базовое распознавание)\\n\\n"
            "Обнаружено: "+description+"\\n\\n"
            "Это предварительное описание изображения, а не точное распознавание игровых предметов. "
            "Для детального разбора PUBG, цен и характеристик нужна полноценная Vision-модель. "
            +("\\nВаш вопрос: "+caption[:300] if caption else ""))

def local_transcribe(file_id):
    import tempfile
    from faster_whisper import WhisperModel
    audio=telegram_file(file_id,limit=12_000_000)
    with tempfile.NamedTemporaryFile(suffix=".ogg") as source:
        source.write(audio)
        source.flush()
        model=WhisperModel("tiny",device="cpu",compute_type="int8",download_root=os.getenv("SHREKSICH_WHISPER_CACHE","/data/whisper_models"))
        segments,_=model.transcribe(source.name,language="ru",beam_size=1,vad_filter=True)
        return " ".join(segment.text.strip() for segment in segments).strip()[:1500]

def transcribe_voice(file_id):
    if not (TRANSCRIBE_URL and AI_KEY):
        return local_transcribe(file_id)
    audio=telegram_file(file_id,limit=12_000_000)
    boundary="----shreksichvoice"
    payload=("--"+boundary+"\r\nContent-Disposition: form-data; name=\"model\"\r\n\r\n"+(VOICE_MODEL or "whisper-1")+"\r\n--"+boundary+"\r\nContent-Disposition: form-data; name=\"file\"; filename=\"voice.ogg\"\r\nContent-Type: audio/ogg\r\n\r\n").encode()+audio+("\r\n--"+boundary+"--\r\n").encode()
    request=urllib.request.Request(TRANSCRIBE_URL,data=payload,headers={"Authorization":"Bearer "+AI_KEY,"Content-Type":"multipart/form-data; boundary="+boundary})
    with urllib.request.urlopen(request,timeout=35) as response:
        result=json.load(response)
    return result.get("text","")[:1500]

def tts_audio(text):
    if not (TTS_URL and AI_KEY and TTS_MODEL): return None
    body={"model":TTS_MODEL,"input":text[:700],"voice":"alloy","response_format":"opus"}
    req=urllib.request.Request(TTS_URL,data=json.dumps(body).encode(),headers={"Authorization":"Bearer "+AI_KEY,"Content-Type":"application/json"})
    with urllib.request.urlopen(req,timeout=35) as response:
        audio=response.read(2_000_000)
    return audio if audio else None

def multipart_voice(chat_id,audio):
    boundary="----shreksichupload"
    fields=("--"+boundary+"\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n"+str(chat_id)+"\r\n--"+boundary+"\r\nContent-Disposition: form-data; name=\"voice\"; filename=\"reply.ogg\"\r\nContent-Type: audio/ogg\r\n\r\n").encode()+audio+("\r\n--"+boundary+"--\r\n").encode()
    req=urllib.request.Request("https://api.telegram.org/bot"+TOKEN+"/sendVoice",data=fields,headers={"Content-Type":"multipart/form-data; boundary="+boundary})
    with urllib.request.urlopen(req,timeout=25) as response:
        return json.load(response)

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
def moderation_pref(cid):
    with db() as conn:
        row=conn.execute("SELECT anti_scam,anti_flood FROM moderation WHERE chat_id=?",(cid,)).fetchone()
    return row or (1,1)

def ai_features(cid):
    with db() as conn:
        row=conn.execute("SELECT voice_enabled,images_enabled,duels_enabled FROM ai_options WHERE chat_id=?",(cid,)).fetchone()
    return row or (1,1,1)

def admin_menu(row):
    cid,enabled,interval,_=row
    persona,ai_on,xp_on=group_pref(cid)
    return keyboard([
        [{"text":"🤖 ИИ "+("✅" if ai_on else "❌"),"callback_data":"admin:ai"},{"text":"⭐ XP "+("✅" if xp_on else "❌"),"callback_data":"admin:xp"}],
        [{"text":"🐸 Характер: "+{"friendly":"Дружелюбный","expert":"Эксперт PUBG","serious":"Серьёзный"}.get(persona,persona),"callback_data":"admin:persona"}],
        [{"text":"🎮 Автовикторины "+("✅" if enabled else "❌"),"callback_data":"admin:toggle"}],
        [{"text":"⏱ 15 мин","callback_data":"admin:interval:15"},{"text":"⏱ 30 мин","callback_data":"admin:interval:30"},{"text":"⏱ 60 мин","callback_data":"admin:interval:60"}],
        [{"text":"🎮 Провести викторину","callback_data":"admin:quiz"},{"text":"🎪 Событие","callback_data":"admin:event"}],
        [{"text":"⏳ Частота ответов","callback_data":"admin:cooldown"},{"text":"🎁 Награда XP","callback_data":"admin:reward"}],
        [{"text":"🛡 Антискам","callback_data":"admin:scam"},{"text":"🚫 Антифлуд","callback_data":"admin:flood"}],
        [{"text":"📸 Фото ИИ","callback_data":"admin:images"},{"text":"🎙 Голос","callback_data":"admin:voice"},{"text":"⚔️ Дуэли","callback_data":"admin:duels"}],
        [{"text":"📊 Статистика","callback_data":"admin:stats"},{"text":"🧠 Очистить память","callback_data":"admin:memory_confirm"}],
        [{"text":"🔄 Обновить","callback_data":"admin:refresh"}],
    ])
def admin_text(row):
    cid,enabled,interval,_=row
    persona,ai_on,xp_on=group_pref(cid)
    cooldown,reward=options(cid)
    anti_scam,anti_flood=moderation_pref(cid)
    voice_on,image_on,duels_on=ai_features(cid)
    return (f"🐸 SHREKSICH AI 2.0 • ПАНЕЛЬ ВЛАДЕЛЬЦА\n\nЧат: {cid}\n"
            f"ИИ: {'включён' if ai_on else 'выключен'}\nХарактер: {persona}\n"
            f"XP: {'включён' if xp_on else 'выключен'}\n"
            f"Автовикторины: {'включены' if enabled else 'выключены'} (каждые {interval} мин)"+chr(10)+f"Ответы ИИ: не чаще раза в {cooldown} сек"+chr(10)+f"Награда за викторину: {reward} XP"+chr(10)+f"Антискам: {bool(anti_scam)} | Антифлуд: {bool(anti_flood)}"+chr(10)+f"Фото: {bool(image_on)} | Голос: {bool(voice_on)} | Дуэли: {bool(duels_on)}")
def admin_stats(cid):
    with db() as conn:
        players=conn.execute("SELECT COUNT(*) FROM profiles WHERE chat_id=?",(cid,)).fetchone()[0]
        xp=conn.execute("SELECT COALESCE(SUM(xp),0) FROM profiles WHERE chat_id=?",(cid,)).fetchone()[0]
        memory=conn.execute("SELECT COUNT(*) FROM memory WHERE chat_id=?",(cid,)).fetchone()[0]
        wins=conn.execute("SELECT COALESCE(SUM(wins),0) FROM scores WHERE chat_id=?",(cid,)).fetchone()[0]
        teams=conn.execute("SELECT COUNT(*) FROM teammates WHERE chat_id=? AND created_at>?",(cid,int(time.time())-7*86400)).fetchone()[0]
        events=conn.execute("SELECT COUNT(*) FROM event_signups WHERE chat_id=?",(cid,)).fetchone()[0]
        alerts=conn.execute("SELECT COUNT(*) FROM events WHERE chat_id=? AND ts>?",(cid,int(time.time())-86400)).fetchone()[0]
    with db() as conn:
        usage=conn.execute("SELECT kind,COUNT(*),SUM(CASE WHEN success=0 THEN 1 ELSE 0 END) FROM usage_stats WHERE chat_id=? AND ts>? GROUP BY kind",(cid,int(time.time())-7*86400)).fetchall()
        active=conn.execute("SELECT COUNT(DISTINCT user_id) FROM usage_stats WHERE chat_id=? AND ts>?",(cid,int(time.time())-7*86400)).fetchone()[0]
        pass_claims=conn.execute("SELECT COUNT(*) FROM battle_rewards WHERE chat_id=?",(cid,)).fetchone()[0]
        duels=conn.execute("SELECT COUNT(*) FROM duels WHERE chat_id=? AND finished=1",(cid,)).fetchone()[0]
    detail="\n".join(f"{kind}: {count} (ошибок: {failed or 0})" for kind,count,failed in usage)
    return f"📊 SHREKSICH AI • АНАЛИТИКА\n\nУчастников: {players}\nАктивных за 7 дней: {active}\nВсего XP: {xp}\nПобед: {wins}\nЗаписей памяти: {memory}\nЗаявок в команду: {teams}\nРегистраций на событие: {events}\nНаград пропуска: {pass_claims}\nЗавершённых дуэлей: {duels}\nСобытий безопасности за сутки: {alerts}\n\nИспользование ИИ за 7 дней:\n"+(detail or "Нет запросов")
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
        with db() as conn:
            events=conn.execute("SELECT chat_id,title FROM events_schedule WHERE starts_at>0 AND starts_at<=?",(now,)).fetchall()
            for cid,title in events:
                conn.execute("UPDATE events_schedule SET starts_at=0 WHERE chat_id=?",(cid,))
        for cid,title in events:
            try:
                with db() as conn:
                    count=conn.execute("SELECT COUNT(*) FROM event_signups WHERE chat_id=?",(cid,)).fetchone()[0]
                await send(cid,f"🎪 {title} начинается! Зарегистрировались: {count}. Удачной игры!")
            except Exception:
                LOG.exception("Event announcement failed")
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
            return
        played={q for (q,) in conn.execute("SELECT question FROM quiz_history WHERE chat_id=?",(cid,)).fetchall() if q<len(QUESTIONS)}
        if len(played)>=len(QUESTIONS):
            conn.execute("DELETE FROM quiz_history WHERE chat_id=?",(cid,))
            played=set()
        choices=[i for i in range(len(QUESTIONS)) if i not in played and (not row or i!=row[0])]
        if not choices: choices=[i for i in range(len(QUESTIONS)) if i not in played]
        index=random.choice(choices)
        conn.execute("INSERT OR REPLACE INTO quiz VALUES(?,?,?,NULL)",(cid,index,now+120))
        conn.execute("INSERT OR REPLACE INTO quiz_history VALUES(?,?,?)",(cid,index,now))
    question,answers,_=QUESTIONS[index]
    text="🎮 ВИКТОРИНА • 2 МИНУТЫ\n\n"+question+"\n\nВыбери правильный ответ:"
    order=list(range(len(answers)))
    random.shuffle(order)
    buttons=keyboard([[{"text":f"{position+1}. {answers[i]}","callback_data":f"quiz:answer:{index}:{i}"}] for position,i in enumerate(order)])
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
    if data.startswith("riddle:") and (msg.get("chat") or {}).get("type")=="private":
        _,group_id,question_id,answer_id=data.split(":")
        group_id=int(group_id)
        expected=(int(time.time())//86400+uid)%len(RIDDLES)
        if int(question_id)!=expected:
            answer="Загадка уже обновилась. Запроси новую."
        elif int(answer_id)==RIDDLES[expected][2]:
            answer="🧩 Правильно! "+("+15 XP" if reward_challenge(group_id,uid,"riddle",15) else "Сегодня награда уже получена.")
        else:
            answer="❌ Неверно, попробуй ещё."
        await call("answerCallbackQuery",callback_query_id=qid,text=answer,show_alert=True)
        return
    if data.startswith("duel:") and (msg.get("chat") or {}).get("type")=="private":
        _,duel_id,answer_id=data.split(":")
        with db() as conn:
            row=conn.execute("SELECT chat_id,challenger,opponent,answer,created_at,finished FROM duels WHERE id=?",(int(duel_id),)).fetchone()
            if not row or uid not in (row[1],row[2]) or row[5] or row[4]<int(time.time())-600:
                answer="Дуэль завершена или недоступна."
            elif int(answer_id)!=row[3]:
                answer="❌ Неверно. Попробуй ещё."
            else:
                result=conn.execute("UPDATE duels SET finished=1 WHERE id=? AND finished=0",(int(duel_id),))
                answer="🏆 Победа в дуэли!" if result.rowcount else "Уже есть победитель."
        if answer=="🏆 Победа в дуэли!":
            answer+=" "+("+20 XP" if reward_challenge(row[0],uid,"duel",20) else "Дневная награда уже получена.")
        await call("answerCallbackQuery",callback_query_id=qid,text=answer,show_alert=True)
        return
    if data.startswith("me:") and (msg.get("chat") or {}).get("type")=="private":
        group=user_group(uid)
        action=data.split(":",1)[1]
        if action=="privacy":
            await call("answerCallbackQuery",callback_query_id=qid)
            await edit(cid,mid,privacy_text(uid),keyboard([[{"text":"🧠 Включить/выключить память","callback_data":"me:memory"},{"text":"🗑 Удалить мою память","callback_data":"me:forget"}],[{"text":"⬅️ Назад","callback_data":"me:home"}]]))
            return
        if action=="memory":
            with db() as conn:
                conn.execute("INSERT OR IGNORE INTO user_preferences(user_id) VALUES(?)",(uid,))
                conn.execute("UPDATE user_preferences SET ai_memory=1-ai_memory WHERE user_id=?",(uid,))
            action="privacy"
        if action=="forget":
            with db() as conn:
                conn.execute("DELETE FROM memory WHERE user_id=?",(uid,))
            action="privacy"
        if group is not None and action in ("riddle","duel"):
            await call("answerCallbackQuery",callback_query_id=qid)
            if action=="riddle": await start_riddle(uid,group)
            else: await start_duel(uid,group)
            return
        if action=="pass" and group is not None:
            answer=battle_pass(group,uid)
        elif action=="pass_claim" and group is not None:
            answer=claim_pass(group,uid)
        elif action=="raids" and group is not None:
            answer=raid_summary(group,uid)
        elif action=="challenges" and group is not None:
            answer=challenge_text(group,uid)
        elif action=="guides":
            answer=pubg_guide("база знаний")
        elif action=="media":
            answer="📸 Пришли скриншот рейда или голосовое сообщение в этот личный чат. Если подключён совместимый ИИ, Шрек сможет обработать его."
        elif action=="home":
            answer="🐸 SHREKSICH AI — твой личный помощник. Задавай вопросы обычным текстом."
        elif group is None:
            answer="Сначала напиши Шреку в группе, чтобы привязать свой профиль."
        elif action=="team":
            answer="🎮 Поиск команды: напиши мне «ищу команду соло», «ищу команду дуо» или «ищу команду сквад»."
        elif action=="privacy":
            answer=privacy_text(uid)
        else:
            answer=await shrek_intent_reply(group,uid,{"profile":"мой профиль","daily":"мои задания","top":"покажи рейтинг","achievements":"мои достижения","claim":"забрать награду"}.get(action,"мой профиль"))
        await call("answerCallbackQuery",callback_query_id=qid)
        await edit(cid,mid,answer or "Не удалось получить данные.",private_menu(uid))
        return
    if data.startswith("admin:") and (msg.get("chat") or {}).get("type")=="private":
        row=owner_chat(uid)
        if not row:
            await call("answerCallbackQuery",callback_query_id=qid,text="Нет доступа к настройкам",show_alert=True)
            return
        if data=="admin:quiz":
            await quiz_start(row[0])
        elif data=="admin:event":
            start=int(time.time())+3600
            with db() as conn:
                conn.execute("INSERT OR REPLACE INTO events_schedule(chat_id,title,starts_at,created_by) VALUES(?,?,?,?)",(row[0],"Вечер Metro Royale",start,uid))
                conn.execute("DELETE FROM event_signups WHERE chat_id=?",(row[0],))
            await send(row[0],"🎪 ВЕЧЕР METRO ROYALE!\nНачало через 1 час.\nНажми кнопку, чтобы записаться.",reply_markup=keyboard([[{"text":"🎮 Участвовать","callback_data":"event:join"}]]))
        elif data=="admin:toggle":
            with db() as conn:
                conn.execute("UPDATE settings SET enabled=1-enabled,next_quiz=? WHERE chat_id=?",(int(time.time())+row[2]*60,row[0]))
        elif data.startswith("admin:interval:"):
            minutes=int(data.rsplit(":",1)[1])
            if minutes in (15,30,60):
                with db() as conn:
                    conn.execute("UPDATE settings SET interval_minutes=?,next_quiz=? WHERE chat_id=?",(minutes,int(time.time())+minutes*60,row[0]))
        elif data in ("admin:ai","admin:xp"):
            column="ai_enabled" if data=="admin:ai" else "level_enabled"
            with db() as conn:
                conn.execute("INSERT OR IGNORE INTO preferences(chat_id) VALUES(?)",(row[0],))
                conn.execute(f"UPDATE preferences SET {column}=1-{column} WHERE chat_id=?",(row[0],))
        elif data=="admin:persona":
            old=group_pref(row[0])[0]
            modes=["friendly","expert","serious"]
            new=modes[(modes.index(old)+1)%len(modes)] if old in modes else "friendly"
            with db() as conn:
                conn.execute("INSERT OR IGNORE INTO preferences(chat_id) VALUES(?)",(row[0],))
                conn.execute("UPDATE preferences SET persona=? WHERE chat_id=?",(new,row[0]))
        elif data in ("admin:images","admin:voice","admin:duels"):
            column={"admin:images":"images_enabled","admin:voice":"voice_enabled","admin:duels":"duels_enabled"}[data]
            with db() as conn:
                conn.execute("INSERT OR IGNORE INTO ai_options(chat_id) VALUES(?)",(row[0],))
                conn.execute(f"UPDATE ai_options SET {column}=1-{column} WHERE chat_id=?",(row[0],))
        elif data in ("admin:scam","admin:flood"):
            column="anti_scam" if data=="admin:scam" else "anti_flood"
            with db() as conn:
                conn.execute("INSERT OR IGNORE INTO moderation(chat_id) VALUES(?)",(row[0],))
                conn.execute(f"UPDATE moderation SET {column}=1-{column} WHERE chat_id=?",(row[0],))
        elif data=="admin:cooldown":
            old=options(row[0])[0]
            choices=[0,10,15,30,60]
            new=choices[(choices.index(old)+1)%len(choices)] if old in choices else 15
            with db() as conn:
                conn.execute("INSERT OR IGNORE INTO bot_options(chat_id) VALUES(?)",(row[0],))
                conn.execute("UPDATE bot_options SET cooldown=? WHERE chat_id=?",(new,row[0]))
        elif data=="admin:reward":
            old=options(row[0])[1]
            choices=[0,10,25,50,100]
            new=choices[(choices.index(old)+1)%len(choices)] if old in choices else 25
            with db() as conn:
                conn.execute("INSERT OR IGNORE INTO bot_options(chat_id) VALUES(?)",(row[0],))
                conn.execute("UPDATE bot_options SET reward=? WHERE chat_id=?",(new,row[0]))
        elif data=="admin:memory_clear":
            with db() as conn:
                conn.execute("DELETE FROM memory WHERE chat_id=?",(row[0],))
        row=owner_chat(uid)
        special=None
        special_buttons=None
        if data=="admin:stats":
            special=admin_stats(row[0])
        elif data=="admin:memory_confirm":
            special="⚠️ Удалить историю диалогов всех участников? Это необратимо."
            special_buttons=keyboard([[{"text":"🗑 Удалить","callback_data":"admin:memory_clear"}],[{"text":"Отмена","callback_data":"admin:refresh"}]])
        if special and not special_buttons:
            special_buttons=keyboard([[{"text":"⬅️ Назад","callback_data":"admin:refresh"}]])
        try: await edit(cid,mid,special or admin_text(row),special_buttons or admin_menu(row))
        except Exception as exc:
            if "message is not modified" not in str(exc): LOG.exception("Admin menu edit failed")
        try: await call("answerCallbackQuery",callback_query_id=qid)
        except Exception: pass
        return
    if data=="event:join":
        with db() as conn:
            event=conn.execute("SELECT title,starts_at FROM events_schedule WHERE chat_id=?",(cid,)).fetchone()
            if event and event[1]>int(time.time()):
                conn.execute("INSERT OR IGNORE INTO event_signups(chat_id,user_id) VALUES(?,?)",(cid,uid))
                response="🎮 Ты записан! Событие начнётся через час после объявления."
            else: response="Регистрация завершена."
        await call("answerCallbackQuery",callback_query_id=qid,text=response,show_alert=True)
        return
    notice=""
    try:
        await call("answerCallbackQuery",callback_query_id=qid)
    except Exception as exc:
        LOG.warning("Callback acknowledgement failed: %s",exc)
    try:
        if data=="page:home":
            await call("editMessageText",chat_id=cid,message_id=mid,text="🐸 SHREKSICH AI работает в чате. Обратись: Шрек, твой вопрос.")
        elif data=="page:help":
            await edit(cid,mid,"📖 ПОМОЩЬ\n\n🎮 Викторина — отвечай кнопками\n🤖 /ai твой вопрос — спросить ИИ\n🛒 Магазин — перейти к покупкам\n\nВыбери раздел ниже.",keyboard([[{"text":"🎮 Викторина","callback_data":"quiz:new"}],[{"text":"⬅️ Главное меню","callback_data":"page:home"}]]))
        elif data=="page:ai":
            await edit(cid,mid,"🤖 ИИ-ПОМОЩНИК\n\nНапиши в чат команду:\n/ai твой вопрос\n\nСейчас отвечает встроенный помощник без API-ключа.",back())
        elif data=="quiz:new":
            await call("editMessageReplyMarkup",chat_id=cid,message_id=mid,reply_markup={"inline_keyboard":[]})
            notice="Новые викторины запускаются только автоматически."
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
                    reward=options(cid)[1]
                    conn.execute("INSERT OR IGNORE INTO profiles(chat_id,user_id,name,xp,last_xp) VALUES(?,?,?,0,0)",(cid,uid,(query.get("from") or {}).get("first_name","Игрок")))
                    conn.execute("UPDATE profiles SET xp=xp+? WHERE chat_id=? AND user_id=?",(reward,cid,uid))
                    season=now//(30*86400)
                    conn.execute("INSERT INTO seasonal_xp(chat_id,user_id,season,xp) VALUES(?,?,?,?) ON CONFLICT(chat_id,user_id,season) DO UPDATE SET xp=xp+excluded.xp",(cid,uid,season,reward))
                    conn.execute("INSERT OR IGNORE INTO achievements(chat_id,user_id,code,awarded_at) VALUES(?,?,?,?)",(cid,uid,"first_win",now))
                    notice=f"🏆 Победа! +{reward} XP"
                    await edit(cid,mid,"🏆 ВИКТОРИНА ЗАВЕРШЕНА\n\nПравильный ответ: "+QUESTIONS[row[0]][1][int(answer_id)]+"\n\n🎉 Победитель определён!",{"inline_keyboard":[]})
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
        return "🛒 Официальный магазин Шрексич: "+SHOP_URL+"\nАктуальные товары, наличие и цены смотри в каталоге."
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
        prompt=system+"\nВопрос: "+question+"\nОтвет:"
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
def rank_name(xp):
    if xp>=2000: return "Легенда Метро"
    if xp>=800: return "Охотник"
    if xp>=250: return "Выживший"
    return "Новичок"

def group_pref(cid):
    with db() as conn:
        row=conn.execute("SELECT persona,ai_enabled,level_enabled FROM preferences WHERE chat_id=?",(cid,)).fetchone()
    return row or ("friendly",1,1)

def add_season_xp(cid,uid,amount):
    season=int(time.time())//(30*86400)
    with db() as conn:
        conn.execute("INSERT INTO seasonal_xp(chat_id,user_id,season,xp) VALUES(?,?,?,?) ON CONFLICT(chat_id,user_id,season) DO UPDATE SET xp=xp+excluded.xp",(cid,uid,season,amount))

def season_top(cid):
    season=int(time.time())//(30*86400)
    with db() as conn:
        rows=conn.execute("SELECT p.name,s.xp FROM seasonal_xp s JOIN profiles p ON p.chat_id=s.chat_id AND p.user_id=s.user_id WHERE s.chat_id=? AND s.season=? ORDER BY s.xp DESC LIMIT 10",(cid,season)).fetchall()
    return "🏆 Рейтинг сезона (30 дней)\n"+("\n".join(f"{i}. {name}: {xp} XP" for i,(name,xp) in enumerate(rows,1)) if rows else "Пока нет участников")

def add_xp(cid,uid,name):
    now=int(time.time())
    with db() as conn:
        conn.execute("INSERT OR IGNORE INTO profiles(chat_id,user_id,name,xp,last_xp) VALUES(?,?,?,0,0)",(cid,uid,name[:80]))
        row=conn.execute("SELECT xp,last_xp FROM profiles WHERE chat_id=? AND user_id=?",(cid,uid)).fetchone()
        if now-row[1]>=60:
            conn.execute("UPDATE profiles SET xp=xp+5,last_xp=?,name=? WHERE chat_id=? AND user_id=?",(now,name[:80],cid,uid))
            season=now//(30*86400)
            conn.execute("INSERT INTO seasonal_xp(chat_id,user_id,season,xp) VALUES(?,?,?,5) ON CONFLICT(chat_id,user_id,season) DO UPDATE SET xp=xp+5",(cid,uid,season))
            return row[0]+5
    return row[0]

def memory_context(cid,uid,question):
    with db() as conn:
        rows=conn.execute("SELECT role,content FROM memory WHERE chat_id=? AND user_id=? ORDER BY ts DESC,rowid DESC LIMIT 8",(cid,uid)).fetchall()
    history="\n".join(role+": "+content for role,content in reversed(rows))
    return (history+"\nПользователь: "+question) if history else question

def remember(cid,uid,question,answer):
    with db() as conn:
        now=int(time.time())
        conn.executemany("INSERT INTO memory(chat_id,user_id,role,content,ts) VALUES(?,?,?,?,?)",[(cid,uid,"Пользователь",question[:600],now),(cid,uid,"Шрек",answer[:900],now)])
        conn.execute("DELETE FROM memory WHERE rowid IN (SELECT rowid FROM memory WHERE chat_id=? AND user_id=? ORDER BY ts DESC,rowid DESC LIMIT -1 OFFSET 20)",(cid,uid))

AI_LAST_ANSWER={}

def options(cid):
    with db() as conn:
        row=conn.execute("SELECT cooldown,reward FROM bot_options WHERE chat_id=?",(cid,)).fetchone()
    return row or (15,25)

PASS_REWARDS={2:"Разведчик",5:"Следопыт",10:"Ветеран",15:"Мастер Метро",20:"Легенда сезона"}

def battle_pass(cid,uid):
    season=int(time.time())//(30*86400)
    with db() as conn:
        row=conn.execute("SELECT xp FROM seasonal_xp WHERE chat_id=? AND user_id=? AND season=?",(cid,uid,season)).fetchone()
        claimed={x[0] for x in conn.execute("SELECT level FROM battle_rewards WHERE chat_id=? AND user_id=? AND season=?",(cid,uid,season))}
    xp=row[0] if row else 0
    level=min(20,xp//100)
    upcoming=[f"Уровень {n}: {name}"+(" ✅" if n in claimed else (" 🎁 доступно" if n<=level else "")) for n,name in PASS_REWARDS.items()]
    return "🎖 БОЕВОЙ ПРОПУСК\nСезон: "+str(season)+"\nXP сезона: "+str(xp)+"\nУровень: "+str(level)+"/20\nСледующий уровень: "+str(max(0,(level+1)*100-xp))+" XP\n\n"+"\n".join(upcoming)+"\n\nНапиши «забрать награды пропуска»."

def claim_pass(cid,uid):
    season=int(time.time())//(30*86400)
    with db() as conn:
        row=conn.execute("SELECT xp FROM seasonal_xp WHERE chat_id=? AND user_id=? AND season=?",(cid,uid,season)).fetchone()
        level=min(20,(row[0] if row else 0)//100)
        claimed=[]
        for n,name in PASS_REWARDS.items():
            if n<=level:
                result=conn.execute("INSERT OR IGNORE INTO battle_rewards(chat_id,user_id,season,level) VALUES(?,?,?,?)",(cid,uid,season,n))
                if result.rowcount: claimed.append(name)
    return "🎁 Получены звания: "+", ".join(claimed) if claimed else "Новых наград пока нет. Зарабатывай XP сезона!"

PUBG_GUIDES={
    "эвакуация":"🧭 Эвакуация: до рейда выбери основной и запасной выход. После ценного лута избегай ненужных перестрелок, проверяй укрытия и слушай шаги.",
    "броня":"🛡 Броня: учитывай прочность, уровень защиты и цену возможной потери. Проверяй состояние шлема и жилета перед рейдом.",
    "оружие":"🔫 Оружие: подбирай под дистанцию и доступные патроны. Важны отдача, стоимость боеприпасов и привычный стиль стрельбы.",
    "соло":"🐺 Соло: избегай открытых маршрутов, заранее продумай отход, не вступай в бой без преимущества и бери запас лечения.",
    "команда":"🤝 Команда: распределяйте роли, называйте позиции противника, не бегите все в одну точку и согласуйте эвакуацию.",
    "экономика":"💰 Экономика: оценивай чистую прибыль как стоимость добычи минус стоимость потерянного снаряжения и расходников.",
}
def pubg_guide(query):
    q=query.lower()
    if any(w in q for w in ("база знаний","все гайды","список гайдов")):
        return "📚 БАЗА ЗНАНИЙ METRO ROYALE\nТемы: "+", ".join(PUBG_GUIDES)+"\nНапиши «гайд броня» или «гайд эвакуация»."
    if any(w in q for w in ("гайд","инструкция","советы по")):
        for key,value in PUBG_GUIDES.items():
            if key in q: return value
        return "📚 Выбери тему: "+", ".join(PUBG_GUIDES)
    return None

def record_usage(cid,uid,kind,success=True):
    with db() as conn:
        conn.execute("INSERT INTO usage_stats(chat_id,user_id,kind,ts,success) VALUES(?,?,?,?,?)",(cid,uid,kind,int(time.time()),int(success)))

RIDDLES=[
    ("Что становится больше, когда из него что-то убирают?",["Яма","Рюкзак","Камень"],0),
    ("Что можно увидеть с закрытыми глазами?",["Сон","Прицел","Карту"],0),
    ("Что принадлежит тебе, но другие используют чаще?",["Имя","Броня","Оружие"],0),
]
def challenge_text(cid,uid):
    day=time.strftime("%Y-%m-%d",time.gmtime())
    with db() as conn:
        rows={k:v for k,v in conn.execute("SELECT kind,completed FROM challenges WHERE chat_id=? AND user_id=? AND day=?",(cid,uid,day))}
    return "🎯 ИСПЫТАНИЯ ДНЯ (UTC)\n🧩 Загадка: "+("готово" if rows.get("riddle") else "доступна")+"\n⚔️ Дуэль знаний: "+("готово" if rows.get("duel") else "доступна")+"\nНапиши «дай загадку» или «вызвать на дуэль»."

def reward_challenge(cid,uid,kind,amount):
    day=time.strftime("%Y-%m-%d",time.gmtime())
    with db() as conn:
        result=conn.execute("INSERT OR IGNORE INTO challenges(chat_id,user_id,day,kind,completed) VALUES(?,?,?,?,1)",(cid,uid,day,kind))
        if not result.rowcount: return False
        conn.execute("INSERT OR IGNORE INTO profiles(chat_id,user_id,name,xp,last_xp) VALUES(?,?,?,0,0)",(cid,uid,"Игрок"))
        conn.execute("UPDATE profiles SET xp=xp+? WHERE chat_id=? AND user_id=?",(amount,cid,uid))
        season=int(time.time())//(30*86400)
        conn.execute("INSERT INTO seasonal_xp(chat_id,user_id,season,xp) VALUES(?,?,?,?) ON CONFLICT(chat_id,user_id,season) DO UPDATE SET xp=xp+excluded.xp",(cid,uid,season,amount))
    return True

def challenge_question(uid):
    index=(int(time.time())//86400+uid)%len(RIDDLES)
    question,answers,_=RIDDLES[index]
    return index,question,answers

async def start_riddle(uid,cid):
    index,question,answers=challenge_question(uid)
    await send(uid,"🧩 ЗАГАДКА ДНЯ\n"+question,reply_markup=keyboard([[{"text":f"{i+1}. {answer}","callback_data":f"riddle:{cid}:{index}:{i}"}] for i,answer in enumerate(answers)]))

async def start_duel(uid,cid):
    if not ai_features(cid)[2]:
        await send(uid,"⚔️ Дуэли отключены администратором.")
        return
    with db() as conn:
        row=conn.execute("SELECT user_id FROM profiles WHERE chat_id=? AND user_id!=? ORDER BY last_xp DESC LIMIT 1",(cid,uid)).fetchone()
    if not row:
        await send(uid,"⚔️ Для дуэли нужен ещё хотя бы один участник сообщества.")
        return
    opponent=row[0]
    question_index=random.randrange(len(QUESTIONS))
    with db() as conn:
        result=conn.execute("INSERT INTO duels(chat_id,challenger,opponent,question,answer,created_at) VALUES(?,?,?,?,?,?)",(cid,uid,opponent,question_index,QUESTIONS[question_index][2],int(time.time())))
        duel_id=result.lastrowid
    question,answers,_=QUESTIONS[question_index]
    markup=keyboard([[{"text":answer,"callback_data":f"duel:{duel_id}:{i}"}] for i,answer in enumerate(answers)])
    await send(uid,"⚔️ ДУЭЛЬ ЗНАНИЙ\n"+question+"\nПервый верный ответ побеждает!",reply_markup=markup)
    try: await send(opponent,"⚔️ Тебя вызвали на дуэль знаний!\n"+question,reply_markup=markup)
    except Exception:
        await send(uid,"Напарник ещё не открыл личный чат с ботом. Приглашение доставлено только тебе.")

def raid_summary(cid,uid):
    with db() as conn:
        row=conn.execute("SELECT COUNT(*),COALESCE(SUM(loot-investment),0),COALESCE(SUM(escaped),0),COALESCE(SUM(investment),0),COALESCE(SUM(loot),0) FROM raid_history WHERE chat_id=? AND user_id=?",(cid,uid)).fetchone()
    n,profit,escapes,cost,loot=row
    return f"📊 ТВОИ РЕЙДЫ\nВсего: {n}\nУспешных эвакуаций: {escapes}\nПроцент эвакуаций: {round(100*escapes/n) if n else 0}%\nВложения: {cost:,}\nДобыча: {loot:,}\nУсловная прибыль: {profit:+,}\n\nЧтобы записать рейд, напиши «рейд 10000 18000 да» (вложения, добыча, эвакуация). Значения вводи в одной игровой валюте."

def save_raid(cid,uid,question):
    parts=question.lower().split()
    if len(parts)!=4 or parts[0]!="рейд": return None
    try:
        cost=int(parts[1]);loot=int(parts[2])
    except ValueError:
        return "Формат: рейд 10000 18000 да"
    if cost<0 or loot<0 or cost>10**12 or loot>10**12: return "Укажи корректные суммы."
    if parts[3] not in ("да","нет"): return "Последнее слово: да или нет (успешная эвакуация)."
    with db() as conn:
        conn.execute("INSERT INTO raid_history(chat_id,user_id,ts,investment,loot,escaped) VALUES(?,?,?,?,?,?)",(cid,uid,int(time.time()),cost,loot,int(parts[3]=="да")))
    return f"📊 Рейд записан. Результат: {loot-cost:+,} игровой валюты. Для статистики напиши «мои рейды»."

def user_group(uid):
    with db() as conn:
        row=conn.execute("SELECT active_chat FROM user_preferences WHERE user_id=?",(uid,)).fetchone()
        if row and row[0]: return row[0]
        row=conn.execute("SELECT chat_id FROM profiles WHERE user_id=? ORDER BY last_xp DESC LIMIT 1",(uid,)).fetchone()
        if not row: return None
        conn.execute("INSERT INTO user_preferences(user_id,active_chat) VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET active_chat=excluded.active_chat",(uid,row[0]))
        return row[0]

def private_menu(uid):
    return keyboard([
        [{"text":"⭐ Мой XP","callback_data":"me:profile"},{"text":"🎯 Задания","callback_data":"me:daily"}],
        [{"text":"🏆 Рейтинг","callback_data":"me:top"},{"text":"🏅 Достижения","callback_data":"me:achievements"}],
        [{"text":"🎁 Забрать XP","callback_data":"me:claim"},{"text":"🎮 Найти команду","callback_data":"me:team"}],
        [{"text":"🎖 Боевой пропуск","callback_data":"me:pass"},{"text":"🎁 Награды сезона","callback_data":"me:pass_claim"}],
        [{"text":"🎯 Испытания","callback_data":"me:challenges"},{"text":"📊 Мои рейды","callback_data":"me:raids"}],
        [{"text":"🧩 Загадка","callback_data":"me:riddle"},{"text":"⚔️ Дуэль","callback_data":"me:duel"}],
        [{"text":"📚 База знаний","callback_data":"me:guides"},{"text":"🎙 Голос и фото","callback_data":"me:media"}],
        [{"text":"🔒 Приватность и память","callback_data":"me:privacy"},{"text":"🛒 Магазин","url":SHOP_URL}],
    ])

def privacy_text(uid):
    with db() as conn:
        row=conn.execute("SELECT ai_memory FROM user_preferences WHERE user_id=?",(uid,)).fetchone()
    return "🔒 Личные настройки\nПамять диалогов: "+("включена" if not row or row[0] else "выключена")+"\nНикому не показываем ваши персональные ответы в группе."

def find_team(cid,uid,question):
    q=question.lower()
    mode="squad" if any(w in q for w in ("сквад","отряд","четвер")) else ("duo" if any(w in q for w in ("дуо","двое","напарник")) else "any")
    if any(w in q for w in ("отмена","удалить заявку","не ищу")):
        with db() as conn: conn.execute("DELETE FROM teammates WHERE user_id=?",(uid,))
        return "🎮 Твоя заявка на поиск команды удалена."
    with db() as conn:
        conn.execute("INSERT OR REPLACE INTO teammates(chat_id,user_id,mode,style,created_at) VALUES(?,?,?,?,?)",(cid,uid,mode,question[:120],int(time.time())))
        rows=conn.execute("SELECT user_id,style FROM teammates WHERE chat_id=? AND user_id!=? AND (mode=? OR mode='any' OR ?='any') AND created_at>? ORDER BY created_at DESC LIMIT 5",(cid,uid,mode,mode,int(time.time())-7*86400)).fetchall()
    if not rows: return "🎮 Заявка сохранена на 7 дней. Пока подходящих игроков нет. Напиши «отмена поиска команды», чтобы удалить её."
    return "🎮 Подходящие игроки (сами разместили заявку):\n"+ "\n".join(f"• Игрок: tg://user?id={other} — {style}" for other,style in rows)+"\nСвяжись с ними самостоятельно. Не передавай пароли и коды."

async def private_answer(uid,question,cid):
    if cid is None:
        await send(uid,"Сначала напиши Шреку в группе сообщества, чтобы привязать свой профиль.")
        return
    q=question.lower()
    raid=save_raid(cid,uid,question)
    if raid is not None:
        await send(uid,raid,reply_markup=private_menu(uid))
        return
    if "мои рейды" in q or "статистика рейдов" in q:
        await send(uid,raid_summary(cid,uid),reply_markup=private_menu(uid))
        return
    if "забрать награды пропуска" in q or "забрать награду пропуска" in q:
        await send(uid,claim_pass(cid,uid),reply_markup=private_menu(uid))
        return
    if "боевой пропуск" in q or "батл пасс" in q or "battle pass" in q:
        await send(uid,battle_pass(cid,uid),reply_markup=private_menu(uid))
        return
    if "испытани" in q:
        await send(uid,challenge_text(cid,uid),reply_markup=private_menu(uid))
        return
    if "загадк" in q:
        await start_riddle(uid,cid)
        return
    if "дуэл" in q:
        await start_duel(uid,cid)
        return
    guide=pubg_guide(question)
    if guide:
        await send(uid,guide,reply_markup=private_menu(uid))
        return
    if ("ищу команд" in question.lower() or "найди команд" in question.lower() or "ищу напарник" in question.lower() or "отмена поиска команд" in question.lower()):
        await send(uid,find_team(cid,uid,question),reply_markup=private_menu(uid))
        return
    direct=await shrek_intent_reply(cid,uid,question)
    if direct is not None:
        await send(uid,direct,reply_markup=private_menu(uid))
        return
    persona,enabled,_=group_pref(cid)
    if not enabled:
        await send(uid,"ИИ временно отключён администратором.")
        return
    style={"friendly":"Ты Шрек, дружелюбный игровой помощник.","expert":"Ты Шрек, эксперт по PUBG Mobile Metro Royale. Не выдумывай цены и патчи.","serious":"Ты Шрек, точный и спокойный помощник."}.get(persona,"Ты Шрек, игровой помощник.")
    with db() as conn:
        pref=conn.execute("SELECT ai_memory FROM user_preferences WHERE user_id=?",(uid,)).fetchone()
    use_memory=not pref or bool(pref[0])
    answer=await ask_ai(style+"\n"+(memory_context(cid,uid,question) if use_memory else question))
    await send(uid,answer,reply_markup=private_menu(uid))
    if use_memory: remember(cid,uid,question,answer)

def shrek_intent(question):
    q=question.lower().strip(" .!?")
    if any(w in q for w in ("забрать награду","получить награду","забрать xp","забрать опыт","получить xp")): return "claim"
    if any(w in q for w in ("ежедневн","задани","квест","как заработать xp","как получить xp","как получать xp","как заработать опыт","как получить опыт")): return "daily"
    if any(w in q for w in ("достижен","награды за достижения")): return "achievements"
    if any(w in q for w in ("сезон","рейтинг месяца")): return "season"
    if any(w in q for w in ("рейтинг","топ игроков","топ участников","лидерборд")): return "top"
    if any(w in q for w in ("мой уровень","мой опыт","сколько у меня xp","сколько у меня опыта","мой профиль","мое звание","моё звание","сколько у меня хп")): return "profile"
    return None

async def shrek_intent_reply(cid,uid,question):
    intent=shrek_intent(question)
    if intent=="daily": return daily_text(cid,uid)
    if intent=="claim": return "🎁 +50 XP! Награда получена." if claim_daily(cid,uid) else "Задание ещё не выполнено или награда уже получена. Спроси: Шрек, мои задания."
    if intent=="season": return season_top(cid)
    if intent=="top": return top_xp(cid)
    if intent=="profile":
        with db() as conn:
            row=conn.execute("SELECT xp FROM profiles WHERE chat_id=? AND user_id=?",(cid,uid)).fetchone()
        xp=row[0] if row else 0
        return f"🐸 У тебя {xp} XP. Звание: {rank_name(xp)}."
    if intent=="achievements":
        with db() as conn:
            row=conn.execute("SELECT COUNT(*) FROM achievements WHERE chat_id=? AND user_id=?",(cid,uid)).fetchone()
        return "🏅 Достижения: "+("🥇 Первая победа в викторине" if row[0] else "пока нет. Победи в викторине!")
    return None

def daily_progress(cid,uid):
    day=time.strftime("%Y-%m-%d",time.gmtime())
    with db() as conn:
        row=conn.execute("SELECT messages,questions,claimed FROM daily_tasks WHERE chat_id=? AND user_id=? AND day=?",(cid,uid,day)).fetchone()
    return row or (0,0,0)

def daily_text(cid,uid):
    messages,questions,claimed=daily_progress(cid,uid)
    status="получена" if claimed else ("команда /claim" if messages>=10 and questions>=3 else "пока недоступна")
    return "📅 ЗАДАНИЯ НА СЕГОДНЯ (UTC)"+chr(10)+chr(10)+f"💬 Сообщения: {min(messages,10)}/10"+chr(10)+f"🐸 Вопросы Шреку: {min(questions,3)}/3"+chr(10)+"🎁 50 XP: "+status

def add_daily(cid,uid,is_question=False):
    day=time.strftime("%Y-%m-%d",time.gmtime())
    with db() as conn:
        conn.execute("INSERT OR IGNORE INTO daily_tasks(chat_id,user_id,day) VALUES(?,?,?)",(cid,uid,day))
        conn.execute("UPDATE daily_tasks SET messages=MIN(messages+1,10),questions=MIN(questions+?,3) WHERE chat_id=? AND user_id=? AND day=?",(int(is_question),cid,uid,day))

def claim_daily(cid,uid):
    day=time.strftime("%Y-%m-%d",time.gmtime())
    with db() as conn:
        result=conn.execute("UPDATE daily_tasks SET claimed=1 WHERE chat_id=? AND user_id=? AND day=? AND messages>=10 AND questions>=3 AND claimed=0",(cid,uid,day))
        if result.rowcount:
            conn.execute("INSERT OR IGNORE INTO profiles(chat_id,user_id,name,xp,last_xp) VALUES(?,?,?,0,0)",(cid,uid,"Игрок"))
            conn.execute("UPDATE profiles SET xp=xp+50 WHERE chat_id=? AND user_id=?",(cid,uid))
            season=int(time.time())//(30*86400)
            conn.execute("INSERT INTO seasonal_xp(chat_id,user_id,season,xp) VALUES(?,?,?,50) ON CONFLICT(chat_id,user_id,season) DO UPDATE SET xp=xp+50",(cid,uid,season))
            return True
    return False

def top_xp(cid):
    with db() as conn:
        rows=conn.execute("SELECT name,xp FROM profiles WHERE chat_id=? ORDER BY xp DESC LIMIT 10",(cid,)).fetchall()
    return "🏆 РЕЙТИНГ АКТИВНОСТИ\n\n"+("\n".join(f"{i}. {name} — {xp} XP ({rank_name(xp)})" for i,(name,xp) in enumerate(rows,1)) if rows else "Пока нет участников.")

async def reply_to_question(chat_id,message_id,question,user_id=0):
    try:
        if not group_pref(chat_id)[1]: return
        try:
            await private_answer(user_id,question,chat_id)
        except Exception as exc:
            LOG.info("User %s has not opened private bot chat: %s",user_id,exc)
    except Exception:
        LOG.exception("Private answer failed")

async def handle(msg):
    chat = msg.get("chat",{})
    user = msg.get("from",{})
    cid,uid=chat.get("id"),user.get("id")
    if not cid or not uid or user.get("is_bot"): return
    text=(msg.get("text") or msg.get("caption") or "").strip()
    if chat.get("type")=="private" and msg.get("photo"):
        group=user_group(uid)
        if not group:
            await send(uid,"Сначала напиши Шреку в группе, чтобы привязать профиль.")
            return
        if not ai_features(group)[1]:
            await send(uid,"📸 Анализ скриншотов отключён администратором.")
            return
        await send(uid,"📸 Анализирую скриншот...")
        try:
            answer=await asyncio.to_thread(vision_query,msg["photo"][-1]["file_id"],text)
            record_usage(group,uid,"vision",bool(VISION_MODEL))
            await send(uid,answer,reply_markup=private_menu(uid))
        except Exception:
            LOG.exception("Vision analysis failed")
            record_usage(group,uid,"vision",False)
            await send(uid,"⚠️ Не удалось обработать изображение. Попробуй позже.")
        return
    if chat.get("type")=="private" and msg.get("voice"):
        group=user_group(uid)
        if not group:
            await send(uid,"Сначала напиши Шреку в группе, чтобы привязать профиль.")
            return
        if not ai_features(group)[0]:
            await send(uid,"🎙 Голосовые функции отключены администратором.")
            return
        if msg["voice"].get("duration",0)>60:
            await send(uid,"🎙 Отправь голосовое сообщение не длиннее 60 секунд.")
            return
        await send(uid,"🎙 Распознаю голосовое сообщение...")
        try:
            transcript=await asyncio.to_thread(transcribe_voice,msg["voice"]["file_id"])
            if not transcript:
                await send(uid,"🎙 Распознавание голоса пока не подключено. Напиши вопрос текстом.")
                return
            record_usage(group,uid,"voice",True)
            await private_answer(uid,transcript,group)
            if TTS_URL and TTS_MODEL:
                answer=await ask_ai(transcript)
                audio=await asyncio.to_thread(tts_audio,answer)
                if audio: await asyncio.to_thread(multipart_voice,uid,audio)
        except Exception:
            LOG.exception("Voice processing failed")
            record_usage(group,uid,"voice",False)
            await send(uid,"⚠️ Не удалось обработать голосовое сообщение.")
        return
    if not text: return
    now=time.time()
    if chat.get("type") in ("group","supergroup"):
        key=(cid,uid)
        recent=[t for t in FLOOD.get(key,[]) if now-t<8]
        recent.append(now); FLOOD[key]=recent
        if len(recent)>7 and uid not in ADMIN_IDS and moderation_pref(cid)[1]:
            log(cid,uid,"flood","8 messages / 8 seconds")
            return
        if moderation_pref(cid)[0] and SCAM.search(text):
            log(cid,uid,"suspected_scam",text)
            await send(cid,"⚠️ Возможная мошенническая схема. Не передавайте пароли и коды. Используйте только официальный магазин.",reply_parameters={"message_id":msg["message_id"],"allow_sending_without_reply":True})
            return
    if chat.get("type") in ("group","supergroup"):
        with db() as conn:
            conn.execute("INSERT OR IGNORE INTO user_preferences(user_id,active_chat) VALUES(?,?)",(uid,cid))
    if chat.get("type") in ("group","supergroup") and len(text)>=3:
        try:
            if group_pref(cid)[2]: add_xp(cid,uid,user.get("first_name") or user.get("username") or "Игрок")
        except Exception: LOG.exception("XP update failed")
    if chat.get("type") in ("group","supergroup") and not text.startswith("/") and len(text)>=3:
        add_daily(cid,uid,bool(re.match(r"^шрек[\\s,:.!?—-]+\\S",text,flags=re.I)))
    cmd=text.split()[0].split("@")[0].lower()
    if chat.get("type")=="private":
        row=owner_chat(uid)
        if text in ("/admin","/settings") and row:
            await send(cid,admin_text(row),reply_markup=admin_menu(row))
        elif text in ("/start","/menu","/help"):
            await send(cid,"🐸 SHREKSICH AI — личный помощник по PUBG Metro Royale. Пиши вопрос прямо здесь. Ответ увидишь только ты.",reply_markup=private_menu(uid))
        else:
            await private_answer(uid,text,user_group(uid))
        return
    if chat.get("type") not in ("group","supergroup"):
        return
    if cmd=="/setup":
        if not await asyncio.to_thread(group_owner,cid,uid):
            await send(cid,"🔒 Привязать чат может только его создатель.")
            return
        with db() as conn:
            conn.execute("INSERT OR REPLACE INTO settings(chat_id,owner_id,enabled,interval_minutes,next_quiz) VALUES(?,?,1,30,?)",(cid,uid,int(time.time())+1800))
        await send(cid,"✅ SHREKSICH AI подключён к чату. Автовикторины — каждые 30 минут.\n🔒 Управление доступно создателю чата в личных сообщениях @Shrekchataibot.")
        return
    with db() as conn:
        bound=conn.execute("SELECT 1 FROM settings WHERE chat_id=?",(cid,)).fetchone()
    if not bound and not re.match(r"^шрек(?:[\s,:.!?—-]+)",text,flags=re.I):
        return
    if chat.get("type") in ("group","supergroup") and not text.startswith("/"):
        match=re.match(r"^шрек(?:[\s,:.!?—-]+)(.+)$",text,flags=re.I|re.S)
        if match:
            question=match.group(1).strip()
            if question:
                asyncio.create_task(reply_to_question(cid,msg["message_id"],question,uid))
        return
    if cmd in ("/start","/help","/menu"):
        return  # No public menus in the group; owner controls are private.
    elif cmd in ("/top","/daily","/claim","/achievements","/profile","/ai"):
        try:
            await private_answer(uid,{"/top":"покажи рейтинг","/daily":"мои задания","/claim":"забрать награду","/achievements":"мои достижения","/profile":"мой профиль","/ai":text.partition(" ")[2].strip() or "помоги с PUBG"}.get(cmd,"мой профиль"),cid)
        except Exception:
            LOG.info("User %s must start private bot first",uid)
        return
    elif cmd=="/top": await send(cid,top_xp(cid))
    elif cmd=="/daily": await send(cid,daily_text(cid,uid))
    elif cmd=="/achievements":
        with db() as conn:
            wins=conn.execute("SELECT COUNT(*) FROM achievements WHERE chat_id=? AND user_id=?",(cid,uid)).fetchone()[0]
        await send(cid,"🏅 ДОСТИЖЕНИЯ"+chr(10)+("🥇 Первая победа в викторине" if wins else "Пока нет достижений. Победи в викторине!"))
    elif cmd=="/claim": await send(cid,"🎁 +50 XP!" if claim_daily(cid,uid) else "Проверь задания: /daily")
    elif cmd=="/profile":
        with db() as conn:
            row=conn.execute("SELECT xp FROM profiles WHERE chat_id=? AND user_id=?",(cid,uid)).fetchone()
        xp=row[0] if row else 0
        await send(cid,f"🐸 Профиль: {user.get('first_name','Игрок')}\n⭐ {xp} XP\n🏅 Звание: {rank_name(xp)}")
    elif cmd=="/aistats" and await asyncio.to_thread(group_owner,cid,uid):
        with db() as conn:
            players=conn.execute("SELECT COUNT(*) FROM profiles WHERE chat_id=?",(cid,)).fetchone()[0]
            memories=conn.execute("SELECT COUNT(*) FROM memory WHERE chat_id=?",(cid,)).fetchone()[0]
        persona,enabled,levels=group_pref(cid)
        await send(cid,f"📊 SHREKSICH AI 2.0\nУчастников: {players}\nЗаписей памяти: {memories}\nИИ: {enabled}\nXP: {levels}\nХарактер: {persona}\nКоманды: /aiconfig friendly|expert|serious, /aitoggle, /xptoggle")
    elif cmd=="/aiconfig" and await asyncio.to_thread(group_owner,cid,uid):
        mode=text.partition(" ")[2].strip().lower()
        if mode not in ("friendly","expert","serious"): await send(cid,"Режимы: /aiconfig friendly, /aiconfig expert, /aiconfig serious")
        else:
            with db() as conn:
                conn.execute("INSERT INTO preferences(chat_id,persona) VALUES(?,?) ON CONFLICT(chat_id) DO UPDATE SET persona=excluded.persona",(cid,mode))
            await send(cid,"✅ Характер Шрека: "+mode)
    elif cmd in ("/aitoggle","/xptoggle") and await asyncio.to_thread(group_owner,cid,uid):
        column="ai_enabled" if cmd=="/aitoggle" else "level_enabled"
        with db() as conn:
            conn.execute("INSERT OR IGNORE INTO preferences(chat_id) VALUES(?)",(cid,))
            conn.execute(f"UPDATE preferences SET {column}=1-{column} WHERE chat_id=?",(cid,))
        await send(cid,"✅ Настройка изменена. /aistats")
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
