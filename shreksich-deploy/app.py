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

MAX_FREE_SPINS_24H = 3

SPIN_TIER_CHANCES = {
    "GRAY": 60.0,
    "CYAN": 30.0,
    "BLUE": 10.0,
    "PURPLE": 0.0,
    "PINK": 0.0,
    "RED": 0.0,
    "GOLD": 0.0,
}

SPIN_REWARDS = [
    # GRAY — 30 items
    {"name":"250K Metro Cash","tier":"GRAY","weight":1.0,"points":4,"value_stars":4},
    {"name":"350K Metro Cash","tier":"GRAY","weight":1.0,"points":5,"value_stars":5},
    {"name":"500K Metro Cash","tier":"GRAY","weight":1.0,"points":6,"value_stars":6},
    {"name":"600K Metro Cash","tier":"GRAY","weight":1.0,"points":7,"value_stars":7},
    {"name":"750K Metro Cash","tier":"GRAY","weight":1.0,"points":8,"value_stars":8},
    {"name":"Базовый набор патронов","tier":"GRAY","weight":1.0,"points":5,"value_stars":5},
    {"name":"Набор аптечек","tier":"GRAY","weight":1.0,"points":5,"value_stars":5},
    {"name":"Набор ремонта","tier":"GRAY","weight":1.0,"points":6,"value_stars":6},
    {"name":"Комплект дымовых гранат","tier":"GRAY","weight":1.0,"points":5,"value_stars":5},
    {"name":"Комплект осколочных гранат","tier":"GRAY","weight":1.0,"points":6,"value_stars":6},
    {"name":"Набор энергетиков","tier":"GRAY","weight":1.0,"points":5,"value_stars":5},
    {"name":"Базовые пластины брони","tier":"GRAY","weight":1.0,"points":7,"value_stars":7},
    {"name":"Ящик стандартных модулей","tier":"GRAY","weight":1.0,"points":8,"value_stars":8},
    {"name":"Тактическая сумка","tier":"GRAY","weight":1.0,"points":8,"value_stars":8},
    {"name":"Полевой медпак","tier":"GRAY","weight":1.0,"points":7,"value_stars":7},
    {"name":"Лёгкий рюкзак","tier":"GRAY","weight":1.0,"points":7,"value_stars":7},
    {"name":"Ремкомплект шлема","tier":"GRAY","weight":1.0,"points":8,"value_stars":8},
    {"name":"Ремкомплект жилета","tier":"GRAY","weight":1.0,"points":8,"value_stars":8},
    {"name":"Тактические бинты","tier":"GRAY","weight":1.0,"points":5,"value_stars":5},
    {"name":"Набор обезболивающих","tier":"GRAY","weight":1.0,"points":6,"value_stars":6},
    {"name":"Мини-набор адреналина","tier":"GRAY","weight":1.0,"points":7,"value_stars":7},
    {"name":"Базовые детали оружия","tier":"GRAY","weight":1.0,"points":9,"value_stars":9},
    {"name":"Базовый Supply Case","tier":"GRAY","weight":1.0,"points":9,"value_stars":9},
    {"name":"Metro Ration Pack","tier":"GRAY","weight":1.0,"points":6,"value_stars":6},
    {"name":"Набор метательного снаряжения","tier":"GRAY","weight":1.0,"points":7,"value_stars":7},
    {"name":"Базовый набор ключевых деталей","tier":"GRAY","weight":1.0,"points":10,"value_stars":10},
    {"name":"Набор радиодеталей","tier":"GRAY","weight":1.0,"points":8,"value_stars":8},
    {"name":"Набор металлолома","tier":"GRAY","weight":1.0,"points":6,"value_stars":6},
    {"name":"Набор полимеров","tier":"GRAY","weight":1.0,"points":7,"value_stars":7},
    {"name":"Стандартный набор инструментов","tier":"GRAY","weight":1.0,"points":9,"value_stars":9},

    # CYAN — 22 items
    {"name":"1M Metro Cash","tier":"CYAN","weight":1.0,"points":14,"value_stars":14},
    {"name":"1.25M Metro Cash","tier":"CYAN","weight":1.0,"points":16,"value_stars":16},
    {"name":"1.5M Metro Cash","tier":"CYAN","weight":1.0,"points":18,"value_stars":18},
    {"name":"Усиленный набор патронов","tier":"CYAN","weight":1.0,"points":17,"value_stars":17},
    {"name":"Набор брони II","tier":"CYAN","weight":1.0,"points":18,"value_stars":18},
    {"name":"Набор модулей оружия","tier":"CYAN","weight":1.0,"points":20,"value_stars":20},
    {"name":"Тактический Supply Case","tier":"CYAN","weight":1.0,"points":21,"value_stars":21},
    {"name":"Metro Utility Pack","tier":"CYAN","weight":1.0,"points":22,"value_stars":22},
    {"name":"Улучшенные детали оружия","tier":"CYAN","weight":1.0,"points":23,"value_stars":23},
    {"name":"Усиленные пластины брони","tier":"CYAN","weight":1.0,"points":21,"value_stars":21},
    {"name":"Расширенный медицинский набор","tier":"CYAN","weight":1.0,"points":19,"value_stars":19},
    {"name":"Улучшенный ремкомплект","tier":"CYAN","weight":1.0,"points":20,"value_stars":20},
    {"name":"Combat Stim Pack","tier":"CYAN","weight":1.0,"points":22,"value_stars":22},
    {"name":"Рюкзак III уровня","tier":"CYAN","weight":1.0,"points":24,"value_stars":24},
    {"name":"Детали шлема III уровня","tier":"CYAN","weight":1.0,"points":24,"value_stars":24},
    {"name":"Детали жилета III уровня","tier":"CYAN","weight":1.0,"points":25,"value_stars":25},
    {"name":"Набор модулей прицела","tier":"CYAN","weight":1.0,"points":22,"value_stars":22},
    {"name":"Набор дульных модулей","tier":"CYAN","weight":1.0,"points":23,"value_stars":23},
    {"name":"Набор рукоятей","tier":"CYAN","weight":1.0,"points":22,"value_stars":22},
    {"name":"Набор магазинов","tier":"CYAN","weight":1.0,"points":23,"value_stars":23},
    {"name":"Тактический набор ключей","tier":"CYAN","weight":1.0,"points":27,"value_stars":27},
    {"name":"Secure Supply Box","tier":"CYAN","weight":1.0,"points":30,"value_stars":30},

    # BLUE — 18 items
    {"name":"2M Metro Cash","tier":"BLUE","weight":1.0,"points":32,"value_stars":32},
    {"name":"2.5M Metro Cash","tier":"BLUE","weight":1.0,"points":36,"value_stars":36},
    {"name":"3M Metro Cash","tier":"BLUE","weight":1.0,"points":40,"value_stars":40},
    {"name":"Elite Ammo Crate","tier":"BLUE","weight":1.0,"points":38,"value_stars":38},
    {"name":"Advanced Armor Pack","tier":"BLUE","weight":1.0,"points":42,"value_stars":42},
    {"name":"Advanced Weapon Kit","tier":"BLUE","weight":1.0,"points":45,"value_stars":45},
    {"name":"Elite Supply Pack","tier":"BLUE","weight":1.0,"points":46,"value_stars":46},
    {"name":"Metro Starter Kit+","tier":"BLUE","weight":1.0,"points":44,"value_stars":44},
    {"name":"Black Zone Supply Case","tier":"BLUE","weight":1.0,"points":48,"value_stars":48},
    {"name":"High Grade Weapon Parts","tier":"BLUE","weight":1.0,"points":49,"value_stars":49},
    {"name":"High Grade Armor Plates","tier":"BLUE","weight":1.0,"points":47,"value_stars":47},
    {"name":"Advanced Module Case","tier":"BLUE","weight":1.0,"points":50,"value_stars":50},
    {"name":"Tactical Operator Pack","tier":"BLUE","weight":1.0,"points":52,"value_stars":52},
    {"name":"Premium Repair Cache","tier":"BLUE","weight":1.0,"points":45,"value_stars":45},
    {"name":"Medical Reserve Case","tier":"BLUE","weight":1.0,"points":43,"value_stars":43},
    {"name":"Secure Contraband Box","tier":"BLUE","weight":1.0,"points":53,"value_stars":53},
    {"name":"Metro Vault Key Set","tier":"BLUE","weight":1.0,"points":54,"value_stars":54},
    {"name":"Classified Supply Crate","tier":"BLUE","weight":1.0,"points":55,"value_stars":55},

    # PURPLE — 12 items
    {"name":"4M Metro Cash","tier":"PURPLE","weight":1.0,"points":60,"value_stars":60},
    {"name":"5M Metro Cash","tier":"PURPLE","weight":1.0,"points":65,"value_stars":65},
    {"name":"6M Metro Cash","tier":"PURPLE","weight":1.0,"points":70,"value_stars":70},
    {"name":"Elite Armor Pack","tier":"PURPLE","weight":1.0,"points":72,"value_stars":72},
    {"name":"Elite Weapon Pack","tier":"PURPLE","weight":1.0,"points":75,"value_stars":75},
    {"name":"Black Market Supply Case","tier":"PURPLE","weight":1.0,"points":78,"value_stars":78},
    {"name":"Advanced Operator Bundle","tier":"PURPLE","weight":1.0,"points":80,"value_stars":80},
    {"name":"Classified Weapon Case","tier":"PURPLE","weight":1.0,"points":82,"value_stars":82},
    {"name":"Classified Armor Case","tier":"PURPLE","weight":1.0,"points":84,"value_stars":84},
    {"name":"Metro Elite Bundle","tier":"PURPLE","weight":1.0,"points":86,"value_stars":86},
    {"name":"High Value Contraband Pack","tier":"PURPLE","weight":1.0,"points":88,"value_stars":88},
    {"name":"Tactical Master Kit","tier":"PURPLE","weight":1.0,"points":90,"value_stars":90},

    # PINK — 8 items
    {"name":"7M Metro Cash","tier":"PINK","weight":1.0,"points":100,"value_stars":100},
    {"name":"8M Metro Cash","tier":"PINK","weight":1.0,"points":110,"value_stars":110},
    {"name":"9M Metro Cash","tier":"PINK","weight":1.0,"points":120,"value_stars":120},
    {"name":"Premium Metro Pack","tier":"PINK","weight":1.0,"points":125,"value_stars":125},
    {"name":"Premium Contraband Cache","tier":"PINK","weight":1.0,"points":130,"value_stars":130},
    {"name":"Elite Quest Booster","tier":"PINK","weight":1.0,"points":135,"value_stars":135},
    {"name":"Black Market Pack","tier":"PINK","weight":1.0,"points":145,"value_stars":145},
    {"name":"Special Ops Bundle","tier":"PINK","weight":1.0,"points":150,"value_stars":150},

    # RED — 6 items
    {"name":"10M Metro Cash","tier":"RED","weight":1.0,"points":170,"value_stars":170},
    {"name":"12M Metro Cash","tier":"RED","weight":1.0,"points":190,"value_stars":190},
    {"name":"15M Metro Cash","tier":"RED","weight":1.0,"points":220,"value_stars":220},
    {"name":"Legendary Supply Vault","tier":"RED","weight":1.0,"points":230,"value_stars":230},
    {"name":"Ultimate Metro Bundle","tier":"RED","weight":1.0,"points":245,"value_stars":245},
    {"name":"Mythic Contraband Vault","tier":"RED","weight":1.0,"points":260,"value_stars":260},

    # GOLD — 4 items
    {"name":"20M Metro Cash","tier":"GOLD","weight":1.0,"points":320,"value_stars":320},
    {"name":"Golden Contraband Vault","tier":"GOLD","weight":1.0,"points":380,"value_stars":380},
    {"name":"Apex Metro Bundle","tier":"GOLD","weight":1.0,"points":440,"value_stars":440},
    {"name":"Ultimate Golden Supply","tier":"GOLD","weight":1.0,"points":500,"value_stars":500},
]

FREE_SPIN_TIERS = ("GRAY","CYAN","BLUE")

def pick_free_spin_reward():
    tier = random.choices(
        ["GRAY","CYAN","BLUE"],
        weights=[SPIN_TIER_CHANCES["GRAY"],SPIN_TIER_CHANCES["CYAN"],SPIN_TIER_CHANCES["BLUE"]],
        k=1
    )[0]
    pool = [x for x in SPIN_REWARDS if x["tier"] == tier]
    return random.choice(pool)

DEFAULT_CASE_CATALOG = [
    {
        "id":"FREE","name":"Бесплатная рулетка","description":"Бесплатное колесо фортуны с Metro-наградами.",
        "icon":"crate","stars_price":0,"is_free":True,"active":True,"sort_order":0,
        "tiers":[
            {"tier":"GRAY","chance":60.0},
            {"tier":"CYAN","chance":30.0},
            {"tier":"BLUE","chance":10.0},
        ],
    },
    {
        "id":"CASE29","name":"Кейс 29","description":"Стартовый донат-кейс с улучшенным Metro-лутом.",
        "icon":"helmet","stars_price":29,"is_free":False,"active":True,"sort_order":10,
        "tiers":[
            {"tier":"BLUE","chance":65.0},
            {"tier":"PURPLE","chance":25.0},
            {"tier":"PINK","chance":10.0},
        ],
    },
    {
        "id":"CASE79","name":"Кейс 79","description":"Продвинутый кейс с высоким шансом редкого лута.",
        "icon":"airdrop","stars_price":79,"is_free":False,"active":True,"sort_order":20,
        "tiers":[
            {"tier":"PURPLE","chance":55.0},
            {"tier":"PINK","chance":30.0},
            {"tier":"RED","chance":15.0},
        ],
    },
    {
        "id":"CASE199","name":"Кейс 199","description":"Премиальный Metro-кейс с красными и золотыми наградами.",
        "icon":"vault","stars_price":199,"is_free":False,"active":True,"sort_order":30,
        "tiers":[
            {"tier":"PURPLE","chance":40.0},
            {"tier":"PINK","chance":30.0},
            {"tier":"RED","chance":25.0},
            {"tier":"GOLD","chance":5.0},
        ],
    },
    {
        "id":"CASE499","name":"Mythic Case","description":"Топовый кейс: только мифические и легендарные награды.",
        "icon":"crown","stars_price":499,"is_free":False,"active":True,"sort_order":40,
        "tiers":[
            {"tier":"RED","chance":70.0},
            {"tier":"GOLD","chance":30.0},
        ],
    },
]

TIER_ORDER = ("GRAY","CYAN","BLUE","PURPLE","PINK","RED","GOLD")

def case_default_contents(case_cfg: dict) -> list[str]:
    allowed = {str(x.get("tier","")).upper() for x in case_cfg.get("tiers", []) if float(x.get("chance",0) or 0) > 0}
    return [x["name"] for x in SPIN_REWARDS if x["tier"] in allowed]

def parse_case_row(row) -> dict:
    tiers = json.loads(row["tiers_json"] or "[]")
    contents = json.loads(row["contents_json"] or "[]")
    return {
        "id":row["id"],"name":("Бесплатная рулетка" if row["id"]=="FREE" and row["name"]=="Бесплатный кейс" else row["name"]),"description":row["description"],"icon":row["icon"],
        "stars_price":int(row["stars_price"] or 0),"is_free":bool(row["is_free"]),
        "active":bool(row["active"]),"sort_order":int(row["sort_order"] or 0),
        "price_label":"БЕСПЛАТНО" if bool(row["is_free"]) else f"{int(row['stars_price'] or 0)} ⭐",
        "tiers":tiers,"contents":contents
    }

async def load_case_catalog(conn, telegram_id: int | None = None, include_inactive: bool = False) -> list[dict]:
    where = "" if include_inactive else "WHERE active=1"
    rows = await (await conn.execute(
        f"SELECT * FROM case_configs {where} ORDER BY sort_order,id"
    )).fetchall()
    wallet = {}
    if telegram_id is not None:
        wrows = await (await conn.execute(
            "SELECT case_id,tickets FROM donation_ticket_balances WHERE telegram_id=?",
            (telegram_id,)
        )).fetchall()
        wallet = {str(x["case_id"]):int(x["tickets"] or 0) for x in wrows}
    generic = int(wallet.get("*",0))
    result = []
    reward_by_name = {x["name"]:x for x in SPIN_REWARDS}
    for row in rows:
        cfg = parse_case_row(row)
        valid_contents = [n for n in cfg["contents"] if n in reward_by_name]
        cfg["contents"] = valid_contents
        cfg["donation_tickets"] = generic + int(wallet.get(cfg["id"],0))
        cfg["available_tiers"] = [
            t for t in cfg["tiers"]
            if float(t.get("chance",0) or 0) > 0
            and any(reward_by_name[n]["tier"] == str(t.get("tier","")).upper() for n in valid_contents)
        ]
        cfg["tiers"] = cfg["available_tiers"]
        result.append(cfg)
    return result

def pick_case_reward(case_cfg: dict) -> dict:
    contents = set(case_cfg.get("contents") or [])
    by_tier = {}
    for reward in SPIN_REWARDS:
        if reward["name"] in contents:
            by_tier.setdefault(reward["tier"], []).append(reward)
    tiers, weights = [], []
    for t in case_cfg.get("tiers") or []:
        tier = str(t.get("tier","")).upper()
        chance = float(t.get("chance",0) or 0)
        if chance > 0 and by_tier.get(tier):
            tiers.append(tier); weights.append(chance)
    if not tiers or sum(weights) <= 0:
        raise HTTPException(409,"В кейсе нет доступных наград. Проверьте его настройки.")
    tier = random.choices(tiers, weights=weights, k=1)[0]
    return random.choice(by_tier[tier])


async def complete_case_opening(conn, opening) -> dict:
    if opening["status"] == "opened":
        if not opening["reward_name"] or int(opening["inventory_item_id"] or 0) <= 0:
            raise HTTPException(409,"Открытие уже завершено некорректно. Обратитесь в поддержку.")
        return {
            "opening_id":int(opening["id"]),
            "inventory_item_id":int(opening["inventory_item_id"]),
            "sell_shr":int(opening["reward_value"] or 0),
            "source":opening["payment_method"],
            "reward":{
                "name":opening["reward_name"],
                "tier":opening["reward_tier"],
                "points":int(opening["reward_value"] or 0),
                "value_stars":int(opening["reward_value"] or 0),
            }
        }
    if opening["status"] != "paid":
        raise HTTPException(409,"Оплата кейса ещё не подтверждена")
    try:
        snapshot = json.loads(opening["snapshot_json"] or "{}")
    except json.JSONDecodeError:
        raise HTTPException(409,"Не удалось прочитать конфигурацию оплаченного кейса")
    reward = pick_case_reward(snapshot)
    value = int(reward["value_stars"])
    source = "case_stars"
    if opening["payment_method"] == "Donation Ticket":
        source = "donation_ticket"
    elif opening["payment_method"] == "Бесплатно":
        source = "case_free"
    await conn.execute(
        "INSERT INTO spin_history(telegram_id,reward_name,reward_tier,points,source) VALUES(?,?,?,?,?)",
        (int(opening["telegram_id"]),reward["name"],reward["tier"],value,source)
    )
    inv = await conn.execute(
        "INSERT INTO inventory_items(telegram_id,reward_name,reward_tier,sell_shr,value_stars,status,source) "
        "VALUES(?,?,?,?,?,'pending',?)",
        (int(opening["telegram_id"]),reward["name"],reward["tier"],value,value,f"case:{opening['case_id']}:{source}")
    )
    inventory_item_id = int(inv.lastrowid)
    cur = await conn.execute(
        "UPDATE case_openings SET status='opened',reward_name=?,reward_tier=?,reward_value=?,inventory_item_id=?,opened_at=CURRENT_TIMESTAMP "
        "WHERE id=? AND status='paid'",
        (reward["name"],reward["tier"],value,inventory_item_id,int(opening["id"]))
    )
    if cur.rowcount != 1:
        raise HTTPException(409,"Открытие уже было обработано")
    return {
        "opening_id":int(opening["id"]),
        "inventory_item_id":inventory_item_id,
        "sell_shr":value,
        "source":source,
        "reward":reward
    }

FARM_MAX_LEVEL = 50
FARM_WITHDRAW_MIN_UC = 120
FARM_DAILY_UC_CREDITS = 2

# UC Credits can be redeemed for actual UC: every new farm award must be
# backed by a pre-funded, owner-approved pool from verified NET Stars profit.
UC_MINE_SECONDS_PER_CREDIT = 172800
def uc_mine_daily_rate(level: int) -> int:
    return max(1,min(5,1+max(1,min(FARM_MAX_LEVEL,int(level)))//5))

def farm_uc_progress(state, now: int):
    rate = min(5, uc_mine_daily_rate(int(state["level"] or 1)) + int(state["uc_generator_level"] or 0)//10)
    last = int(state["uc_mine_last_at"] or now)
    elapsed = min(86400,max(0,now-last))
    progress = min(UC_MINE_SECONDS_PER_CREDIT*rate,max(0,int(state["uc_mine_progress"] or 0))+elapsed*rate)
    ready = int(progress//UC_MINE_SECONDS_PER_CREDIT)
    next_seconds = max(0,(UC_MINE_SECONDS_PER_CREDIT-progress%UC_MINE_SECONDS_PER_CREDIT+rate-1)//rate) if ready<rate else 0
    return int(progress),ready,rate,int(next_seconds)

async def uc_fund(conn):
    return await (await conn.execute(
        "SELECT available_credits,funded_credits,issued_credits FROM uc_mining_fund WHERE id=1"
    )).fetchone()

FARM_TIER_ORDER = ("GRAY","CYAN","BLUE","PURPLE","PINK","RED","GOLD","RAINBOW")

FARM_RESOURCES = [
    {"id":"postcard","name":"Открытка","tier":"GRAY","icon":"📮","coins":1},
    {"id":"travel_guide","name":"Путеводитель","tier":"GRAY","icon":"🗺️","coins":1},
    {"id":"magazine","name":"Журнал","tier":"GRAY","icon":"📖","coins":1},
    {"id":"playing_cards","name":"Игральные карты","tier":"GRAY","icon":"🃏","coins":1},
    {"id":"letter","name":"Письмо","tier":"GRAY","icon":"✉️","coins":1},
    {"id":"can","name":"Банка","tier":"GRAY","icon":"🥫","coins":1},
    {"id":"canteen","name":"Армейский чайник","tier":"GRAY","icon":"🫖","coins":2},
    {"id":"video_tape","name":"Старая видеокассета","tier":"GRAY","icon":"📼","coins":2},
    {"id":"compass","name":"Компас","tier":"GRAY","icon":"🧭","coins":2},

    {"id":"pocket_watch","name":"Карманные часы","tier":"CYAN","icon":"⌚","coins":4},
    {"id":"motor_oil","name":"Моторное масло","tier":"CYAN","icon":"🛢️","coins":4},
    {"id":"heart_necklace","name":"Ожерелье-сердце","tier":"CYAN","icon":"📿","coins":5},
    {"id":"purse","name":"Кошелёк","tier":"CYAN","icon":"👝","coins":5},
    {"id":"gas_bottle","name":"Бутылка с горючим","tier":"CYAN","icon":"🧯","coins":6},
    {"id":"diesel","name":"Дизель","tier":"CYAN","icon":"⛽","coins":6},
    {"id":"lubricating_oil","name":"Смазка","tier":"CYAN","icon":"🧴","coins":7},
    {"id":"car_key","name":"Ключ от машины","tier":"CYAN","icon":"🔑","coins":8},
    {"id":"military_watch","name":"Армейские часы","tier":"CYAN","icon":"⏱️","coins":8},
    {"id":"metro_2036","name":"Metro 2036","tier":"CYAN","icon":"📕","coins":8},

    {"id":"dog_tag","name":"Армейский жетон","tier":"BLUE","icon":"🏷️","coins":14},
    {"id":"water_purifier","name":"Опреснитель воды","tier":"BLUE","icon":"💧","coins":16},
    {"id":"cpu","name":"Процессор","tier":"BLUE","icon":"🧠","coins":18},
    {"id":"signal_generator","name":"Генератор сигнала","tier":"BLUE","icon":"📡","coins":21},
    {"id":"tech_part","name":"Технический компонент","tier":"BLUE","icon":"⚙️","coins":24},

    {"id":"password_white","name":"Письмо с паролем — белое","tier":"PURPLE","icon":"🤍","coins":34},
    {"id":"password_red","name":"Письмо с паролем — красное","tier":"PURPLE","icon":"❤️","coins":35},
    {"id":"password_yellow","name":"Письмо с паролем — жёлтое","tier":"PURPLE","icon":"💛","coins":36},
    {"id":"password_green","name":"Письмо с паролем — зелёное","tier":"PURPLE","icon":"💚","coins":37},
    {"id":"tablet","name":"Планшет","tier":"PURPLE","icon":"📱","coins":45},
    {"id":"detector","name":"Детектор","tier":"PURPLE","icon":"📟","coins":52},

    {"id":"precision_blueprint","name":"Чертёж высокоточного прибора","tier":"PINK","icon":"📐","coins":85},
    {"id":"password_black","name":"Письмо с паролем — чёрное","tier":"PINK","icon":"🖤","coins":95},

    {"id":"gold_watch","name":"Золотые механические часы","tier":"RED","icon":"🕰️","coins":145},
    {"id":"gold_kettle","name":"Золотой армейский чайник","tier":"RED","icon":"🏺","coins":160},
    {"id":"heart_of_gold","name":"Золотое ожерелье-сердце","tier":"RED","icon":"💛","coins":175},

    {"id":"gold_bar","name":"Золотой слиток","tier":"GOLD","icon":"🪙","coins":260},
    # Новая премиальная коллекция: базовая стоимость сопоставимых предметов ×10.
    {"id":"metro_quantum_watch","name":"Квантовые часы Метро","tier":"PINK","icon":"⌚","coins":1450},
    {"id":"metro_encrypted_tablet","name":"Зашифрованный планшет","tier":"PINK","icon":"📱","coins":950},
    {"id":"metro_royal_kettle","name":"Королевский армейский чайник","tier":"RED","icon":"🫖","coins":1600},
    {"id":"metro_ancient_medallion","name":"Древний золотой медальон","tier":"RED","icon":"🏅","coins":1750},
    {"id":"metro_legendary_compass","name":"Компас командира Метро","tier":"GOLD","icon":"🧭","coins":2600},
    {"id":"metro_golden_core","name":"Золотое ядро реактора","tier":"GOLD","icon":"⚙️","coins":2600},
    # Радужное качество: стоимость сопоставимого золотого предмета ×20.
    {"id":"rainbow_prism","name":"Призматический артефакт","tier":"RAINBOW","icon":"💎","coins":5200},
    {"id":"rainbow_relic","name":"Реликвия семи спектров","tier":"RAINBOW","icon":"🏆","coins":5200},
    {"id":"rainbow_reactor","name":"Радужное ядро реактора","tier":"RAINBOW","icon":"⚡","coins":5200},
    {"id":"rainbow_crown","name":"Корона подземного короля","tier":"RAINBOW","icon":"👑","coins":5200},

]
FARM_RESOURCE_BY_ID = {x["id"]:x for x in FARM_RESOURCES}

# Улучшения фермы за ShrekCOINS. Эти монеты нельзя обменять на Stars/UC.
FARM_COIN_MAX_LEVEL = 60
FARM_MODULE_LIMITS = {'drill':50,'warehouse':60,'trader':50,'quality':40,'automation':35,'uc_generator':40,'research':30}
FARM_COIN_MODULES = {
    "drill": {"column":"drill_level", "name":"Фермерские инструменты", "icon":"🪓", "base":55,
              "description":"Качественные инструменты ускоряют сбор ресурсов на 9% за уровень."},
    "warehouse": {"column":"warehouse_level", "name":"Вместительный амбар", "icon":"🧺", "base":85,
                  "description":"Каждый уровень добавляет 24 места для добычи."},
    "trader": {"column":"trader_level", "name":"Торговая лавка", "icon":"⚖️", "base":120,
               "description":"Цена продажи добычи повышается на 15% за уровень."},
}

FARM_COIN_MODULES.update({
    "quality":{"column":"quality_level","name":"Качество добычи","icon":"💎","base":175,"description":"Повышает шанс редких ресурсов."},
    "automation":{"column":"automation_level","name":"Автоматизация","icon":"🤖","base":230,"description":"Увеличивает вместимость склада."},
    "uc_generator":{"column":"uc_generator_level","name":"UC-генератор","icon":"⚡","base":290,"description":"Развитие UC-майнинга в пределах фонда."},
    "research":{"column":"research_level","name":"Исследовательский центр","icon":"🔬","base":360,"description":"Увеличивает вместимость и открывает новые технологии."}
})

def farm_coin_upgrade_cost(module: str, level: int) -> int:
    spec = FARM_COIN_MODULES[module]
    return int(round(spec["base"] * (1.34 ** min(level,40) * 1.20 ** max(0,level-40) * (1+level/18))))

def farm_mining_interval(level: int, drill_level: int = 0) -> int:
    # Economy v3: slower resource production, including fully upgraded farms.
    # The base mining interval is tripled; bonuses remain capped.
    old_interval = max(90, farm_interval_seconds(level) * (max(35,100 - 9*min(5,int(drill_level)) - int(1.5*max(0,int(drill_level)-5)**0.8))) // 100)
    return old_interval * 3

def farm_total_capacity(level: int, warehouse_level: int = 0) -> int:
    return farm_capacity(level) + 24*min(5,max(0,int(warehouse_level))) + int(8*max(0,int(warehouse_level)-5)**1.3)

def farm_sale_price(item: dict, trader_level: int = 0) -> int:
    # Every farm resource is worth exactly twice its previous ShrekCOIN value.
    # Preserve the existing +15% per trader level and its rounding behavior.
    old_price = max(1, int(round(int(item["coins"]) * (100 + 15*min(5,max(0,int(trader_level))) + int(1.5*max(0,int(trader_level)-5)**1.2)) / 100)))
    return old_price * 2

def farm_coin_modules(state) -> list[dict]:
    results = []
    for key, spec in FARM_COIN_MODULES.items():
        level = max(0, min(FARM_MODULE_LIMITS[key], int(state[spec["column"]] or 0)))
        results.append({
            "id":key, "name":spec["name"], "icon":spec["icon"],
            "description":spec["description"], "level":level,
            "max_level":FARM_MODULE_LIMITS[key],
            "cost":farm_coin_upgrade_cost(key,level) if level<FARM_MODULE_LIMITS[key] else 0
        })
    return results

def farm_upgrade_cost(level: int) -> int:
    level = max(1,min(FARM_MAX_LEVEL,int(level)))
    if level >= FARM_MAX_LEVEL:
        return 0
    return int(round(25 * (1.48 ** min(level-1,19)) * (1.18 ** max(0,level-20))))

def farm_interval_seconds(level: int) -> int:
    level = max(1,min(FARM_MAX_LEVEL,int(level)))
    return max(180, 600 - (min(level,20) - 1) * 22 - max(0,level-20)*3)

def farm_capacity(level: int) -> int:
    level = max(1,min(FARM_MAX_LEVEL,int(level)))
    return 36 + level * 12

def farm_stage(level: int) -> int:
    return min(10, 1 + (max(1,min(FARM_MAX_LEVEL,int(level))) - 1)//5)

def farm_tier_weights(level: int) -> dict[str,float]:
    p = (max(1,min(FARM_MAX_LEVEL,int(level))) - 1) / max(1,FARM_MAX_LEVEL - 1)
    # Повышенные шансы редкой добычи; доли нормализуются до 100%.
    # Начальная ферма: 72 / 18 / 7 / 2.5 / 0.45 / 0.045 / 0.0045 / 0.0005
    # Максимальная ферма: 55 / 22 / 12 / 7 / 2.8 / 0.9 / 0.28 / 0.02
    starting = {"GRAY":72, "CYAN":18, "BLUE":7, "PURPLE":2.5, "PINK":0.45, "RED":0.045, "GOLD":0.0045, "RAINBOW":0.0005}
    ending = {"GRAY":55, "CYAN":22, "BLUE":12, "PURPLE":7, "PINK":2.8, "RED":0.9, "GOLD":0.28, "RAINBOW":0.02}
    weights = {tier:starting[tier] + (ending[tier] - starting[tier])*p for tier in FARM_TIER_ORDER}
    total = sum(weights.values()) or 1
    return {k:round(v*100/total,3) for k,v in weights.items()}

def farm_item_weights(pool: list[dict]) -> list[float]:
    # Используем базовую цену, не изменяемую бонусом торговой лавки.
    # Степень 0.7 даёт заметную разницу без обнуления дорогого лута.
    return [1.0 / (max(1, int(item["coins"])) ** 0.7) for item in pool]

def farm_item_chances(level: int) -> dict[str,float]:
    tier_chances = farm_tier_weights(level)
    result = {}
    for tier in FARM_TIER_ORDER:
        pool = [item for item in FARM_RESOURCES if item["tier"] == tier]
        if not pool:
            continue
        weights = farm_item_weights(pool)
        total = sum(weights)
        for item, weight in zip(pool, weights):
            result[item["id"]] = tier_chances[tier] * weight / total
    return result

def pick_farm_resource(level: int) -> dict:
    weights = farm_tier_weights(level)
    tiers = list(FARM_TIER_ORDER)
    tier = random.choices(tiers,weights=[weights[t] for t in tiers],k=1)[0]
    pool = [x for x in FARM_RESOURCES if x["tier"] == tier]
    return random.choices(pool, weights=farm_item_weights(pool), k=1)[0]

async def ensure_farm_state(conn, uid: int):
    row = await (await conn.execute("SELECT * FROM farm_state WHERE telegram_id=?",(uid,))).fetchone()
    if row:
        return row
    now = int(time.time())
    await conn.execute(
        "INSERT INTO farm_state(telegram_id,level,shrek_coins,uc_credits,uc_reserved,last_mine_at,last_collect_at,last_activity_at,activity_streak,activity_total,uc_mine_last_at,uc_mine_progress) "
        "VALUES(?,1,0,0,0,?,?,0,0,0,?,0)",
        (uid,now-farm_mining_interval(1),0,now)
    )
    return await (await conn.execute("SELECT * FROM farm_state WHERE telegram_id=?",(uid,))).fetchone()

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
    CREATE TABLE IF NOT EXISTS uc_support_chats(id INTEGER PRIMARY KEY AUTOINCREMENT,withdrawal_id INTEGER NOT NULL UNIQUE,telegram_id INTEGER NOT NULL,status TEXT NOT NULL DEFAULT 'Открыт',created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS uc_support_messages(id INTEGER PRIMARY KEY AUTOINCREMENT,chat_id INTEGER NOT NULL,sender TEXT NOT NULL,message TEXT NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS uc_chat_reads(chat_id INTEGER NOT NULL,reader TEXT NOT NULL,last_read_id INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(chat_id,reader));
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
    CREATE TABLE IF NOT EXISTS case_configs(
      id TEXT PRIMARY KEY,
      name TEXT NOT NULL,
      description TEXT NOT NULL DEFAULT '',
      icon TEXT NOT NULL DEFAULT 'crate',
      stars_price INTEGER NOT NULL DEFAULT 0,
      is_free INTEGER NOT NULL DEFAULT 0,
      active INTEGER NOT NULL DEFAULT 1,
      sort_order INTEGER NOT NULL DEFAULT 0,
      tiers_json TEXT NOT NULL DEFAULT '[]',
      contents_json TEXT NOT NULL DEFAULT '[]',
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS case_openings(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      telegram_id INTEGER NOT NULL,
      case_id TEXT NOT NULL,
      case_name TEXT NOT NULL,
      stars_amount INTEGER NOT NULL DEFAULT 0,
      payment_method TEXT NOT NULL DEFAULT '',
      status TEXT NOT NULL DEFAULT 'awaiting_payment',
      snapshot_json TEXT NOT NULL DEFAULT '{}',
      reward_name TEXT NOT NULL DEFAULT '',
      reward_tier TEXT NOT NULL DEFAULT '',
      reward_value INTEGER NOT NULL DEFAULT 0,
      inventory_item_id INTEGER NOT NULL DEFAULT 0,
      telegram_charge_id TEXT NOT NULL DEFAULT '',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      paid_at TEXT NOT NULL DEFAULT '',
      opened_at TEXT NOT NULL DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS donation_ticket_balances(
      telegram_id INTEGER NOT NULL,
      case_id TEXT NOT NULL DEFAULT '*',
      tickets INTEGER NOT NULL DEFAULT 0,
      PRIMARY KEY(telegram_id,case_id)
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

    # Supplier marketplace, fully isolated from original first-party products.
    # Stars split is an accounting estimate, never an automatic Stars transfer.
    await conn.executescript("""
    CREATE TABLE IF NOT EXISTS shop_sellers(
      telegram_id INTEGER PRIMARY KEY,
      display_name TEXT NOT NULL,
      contact TEXT NOT NULL,
      experience TEXT NOT NULL DEFAULT '',
      status TEXT NOT NULL DEFAULT 'pending',
      commission_pct INTEGER NOT NULL DEFAULT 30,
      rules_confirmed INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS seller_payout_requests(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      seller_id INTEGER NOT NULL,
      amount INTEGER NOT NULL CHECK(amount>0),
      proof TEXT NOT NULL,
      payment_details TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'pending',
      created_at INTEGER NOT NULL,
      approved_at INTEGER NOT NULL DEFAULT 0,
      available_at INTEGER NOT NULL DEFAULT 0,
      reviewed_by INTEGER NOT NULL DEFAULT 0,
      reason TEXT NOT NULL DEFAULT '',
      paid_note TEXT NOT NULL DEFAULT ''
    );
    CREATE INDEX IF NOT EXISTS idx_seller_payout_requests_seller ON seller_payout_requests(seller_id,status);
    CREATE TABLE IF NOT EXISTS seller_settlement_log(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      order_id INTEGER NOT NULL UNIQUE,
      seller_id INTEGER NOT NULL,
      seller_stars INTEGER NOT NULL,
      note TEXT NOT NULL,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_shop_sellers_status ON shop_sellers(status);
    CREATE TABLE IF NOT EXISTS seller_warnings(id INTEGER PRIMARY KEY AUTOINCREMENT,seller_id INTEGER NOT NULL,reason TEXT NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS seller_removals(id INTEGER PRIMARY KEY AUTOINCREMENT,seller_id INTEGER NOT NULL,display_name TEXT NOT NULL,reason TEXT NOT NULL,removed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS seller_reviews(id INTEGER PRIMARY KEY AUTOINCREMENT,seller_id INTEGER NOT NULL,buyer_id INTEGER NOT NULL,rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),comment TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,UNIQUE(seller_id,buyer_id));
    """)
    product_cols = {r["name"] for r in await (await conn.execute("PRAGMA table_info(products)")).fetchall()}
    for col,ddl in {
        "seller_id":"INTEGER NOT NULL DEFAULT 0",
        "seller_stock":"INTEGER NOT NULL DEFAULT 0",
        "seller_status":"TEXT NOT NULL DEFAULT 'active'",
    }.items():
        if col not in product_cols:
            await conn.execute(f"ALTER TABLE products ADD COLUMN {col} {ddl}")
    seller_order_cols = {r["name"] for r in await (await conn.execute("PRAGMA table_info(orders)")).fetchall()}
    for col,ddl in {
        "seller_id":"INTEGER NOT NULL DEFAULT 0",
        "seller_commission_pct":"INTEGER NOT NULL DEFAULT 0",
        "seller_share_stars":"INTEGER NOT NULL DEFAULT 0",
        "platform_share_stars":"INTEGER NOT NULL DEFAULT 0",
        "reserve_share_stars":"INTEGER NOT NULL DEFAULT 0",
        "seller_reserved_until":"INTEGER NOT NULL DEFAULT 0",
        "seller_delivery_note":"TEXT NOT NULL DEFAULT ''",
        "seller_submitted_at":"TEXT NOT NULL DEFAULT ''",
    }.items():
        if col not in seller_order_cols:
            await conn.execute(f"ALTER TABLE orders ADD COLUMN {col} {ddl}")
    # One-time new terms migration: future orders use 30% combined commission.
    # Older order snapshots are deliberately untouched, even if already paid.
    terms_change = await (await conn.execute(
        "SELECT value FROM settings WHERE key='seller_commission_20_10_v2'"
    )).fetchone()
    if not terms_change:
        await conn.execute(
            "UPDATE shop_sellers SET commission_pct=30,updated_at=CURRENT_TIMESTAMP"
        )
        await conn.execute(
            "INSERT INTO settings(key,value) VALUES('seller_commission_20_10_v2','1')"
        )
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_seller_products ON products(seller_id,seller_status,active)")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_seller_orders ON orders(seller_id,status)")
    promo_cols = {r["name"] for r in await (await conn.execute("PRAGMA table_info(promos)")).fetchall()}
    if "promo_type" not in promo_cols:
        await conn.execute("ALTER TABLE promos ADD COLUMN promo_type TEXT NOT NULL DEFAULT 'discount'")
    if "spin_tickets" not in promo_cols:
        await conn.execute("ALTER TABLE promos ADD COLUMN spin_tickets INTEGER NOT NULL DEFAULT 0")
    if "donation_tickets" not in promo_cols:
        await conn.execute("ALTER TABLE promos ADD COLUMN donation_tickets INTEGER NOT NULL DEFAULT 0")
    if "case_id" not in promo_cols:
        await conn.execute("ALTER TABLE promos ADD COLUMN case_id TEXT NOT NULL DEFAULT ''")
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

    # Seed editable case configuration once. Existing admin changes are never overwritten.
    for case_cfg in DEFAULT_CASE_CATALOG:
        await conn.execute(
            "INSERT OR IGNORE INTO case_configs(id,name,description,icon,stars_price,is_free,active,sort_order,tiers_json,contents_json) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                case_cfg["id"],case_cfg["name"],case_cfg.get("description",""),case_cfg.get("icon","crate"),
                int(case_cfg.get("stars_price",0)),1 if case_cfg.get("is_free") else 0,
                1 if case_cfg.get("active",True) else 0,int(case_cfg.get("sort_order",0)),
                json.dumps(case_cfg.get("tiers",[]),ensure_ascii=False),
                json.dumps(case_default_contents(case_cfg),ensure_ascii=False)
            )
        )
    opening_cols = {r["name"] for r in await (await conn.execute("PRAGMA table_info(case_openings)")).fetchall()}
    if "inventory_item_id" not in opening_cols:
        await conn.execute("ALTER TABLE case_openings ADD COLUMN inventory_item_id INTEGER NOT NULL DEFAULT 0")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_case_openings_user_status ON case_openings(telegram_id,status)")
    await conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_case_openings_charge ON case_openings(telegram_charge_id) WHERE telegram_charge_id<>''")

    await conn.executescript("""
    CREATE TABLE IF NOT EXISTS farm_state(
      telegram_id INTEGER PRIMARY KEY,
      level INTEGER NOT NULL DEFAULT 1,
      shrek_coins INTEGER NOT NULL DEFAULT 0,
      uc_credits INTEGER NOT NULL DEFAULT 0,
      uc_reserved INTEGER NOT NULL DEFAULT 0,
      last_mine_at INTEGER NOT NULL DEFAULT 0,
      last_collect_at INTEGER NOT NULL DEFAULT 0,
      last_activity_at INTEGER NOT NULL DEFAULT 0,
      activity_streak INTEGER NOT NULL DEFAULT 0,
      activity_total INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS farm_item_locks(
      telegram_id INTEGER NOT NULL,
      resource_id TEXT NOT NULL,
      PRIMARY KEY(telegram_id,resource_id)
    );
    CREATE TABLE IF NOT EXISTS farm_inventory(
      telegram_id INTEGER NOT NULL,
      resource_id TEXT NOT NULL,
      qty INTEGER NOT NULL DEFAULT 0,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY(telegram_id,resource_id)
    );
    CREATE TABLE IF NOT EXISTS farm_log(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      telegram_id INTEGER NOT NULL,
      action TEXT NOT NULL,
      details TEXT NOT NULL DEFAULT '',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS uc_withdrawals(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      telegram_id INTEGER NOT NULL,
      pubg_uid TEXT NOT NULL,
      uc_amount INTEGER NOT NULL,
      status TEXT NOT NULL DEFAULT 'Ожидает',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      processed_at TEXT NOT NULL DEFAULT ''
    );
    CREATE INDEX IF NOT EXISTS idx_uc_withdrawals_status ON uc_withdrawals(status,id);
    """)
    farm_cols = {r["name"] for r in await (await conn.execute("PRAGMA table_info(farm_state)")).fetchall()}
    for col,ddl in {
        "uc_reserved":"INTEGER NOT NULL DEFAULT 0",
        "last_collect_at":"INTEGER NOT NULL DEFAULT 0",
        "last_activity_at":"INTEGER NOT NULL DEFAULT 0",
        "activity_streak":"INTEGER NOT NULL DEFAULT 0",
        "activity_total":"INTEGER NOT NULL DEFAULT 0",
        "uc_mine_last_at":"INTEGER NOT NULL DEFAULT 0",
        "uc_mine_progress":"INTEGER NOT NULL DEFAULT 0",
        "drill_level":"INTEGER NOT NULL DEFAULT 0",
        "warehouse_level":"INTEGER NOT NULL DEFAULT 0",
        "trader_level":"INTEGER NOT NULL DEFAULT 0",
        "quality_level":"INTEGER NOT NULL DEFAULT 0",
        "automation_level":"INTEGER NOT NULL DEFAULT 0",
        "uc_generator_level":"INTEGER NOT NULL DEFAULT 0",
        "research_level":"INTEGER NOT NULL DEFAULT 0",
    }.items():
        if col not in farm_cols:
            await conn.execute(f"ALTER TABLE farm_state ADD COLUMN {col} {ddl}")

    await conn.executescript("""
    CREATE TABLE IF NOT EXISTS uc_mining_fund(
        id INTEGER PRIMARY KEY CHECK(id=1),
        available_credits INTEGER NOT NULL DEFAULT 0 CHECK(available_credits>=0),
        funded_credits INTEGER NOT NULL DEFAULT 0 CHECK(funded_credits>=0),
        issued_credits INTEGER NOT NULL DEFAULT 0 CHECK(issued_credits>=0),
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS uc_mining_fund_log(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        operator_id INTEGER NOT NULL,
        credited_amount INTEGER NOT NULL,
        note TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """)
    await conn.execute("INSERT OR IGNORE INTO uc_mining_fund(id) VALUES(1)")
    await conn.execute("UPDATE farm_state SET uc_mine_last_at=? WHERE uc_mine_last_at=0",(int(time.time()),))

    # Economy v2 one-time migration: keep already-earned item cycles and
    # partial progress when doubling every interval. Do not change existing
    # stored items, balances, UC counters, or inventory rows.
    farm_economy_v2 = await (await conn.execute(
        "SELECT value FROM settings WHERE key='farm_items_slower_x2_prices_x2_v2'"
    )).fetchone()
    if not farm_economy_v2:
        rollout_now = int(time.time())
        farm_rows = await (await conn.execute(
            "SELECT telegram_id,last_mine_at FROM farm_state"
        )).fetchall()
        migrated = []
        for farm_row in farm_rows:
            mined_at = int(farm_row["last_mine_at"] or 0)
            if mined_at <= 0:
                continue
            old_elapsed = min(30*86400,max(0,rollout_now-mined_at))
            migrated.append((rollout_now-2*old_elapsed,int(farm_row["telegram_id"])))
        if migrated:
            await conn.executemany(
                "UPDATE farm_state SET last_mine_at=? WHERE telegram_id=?",
                migrated
            )
        await conn.execute(
            "INSERT INTO settings(key,value) VALUES('farm_items_slower_x2_prices_x2_v2','1')"
        )

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
    rows.append([{"text":"🌾 Ферма","web_app":{"url":BASE_URL + "/?tab=farm"}},
                 {"text":"🎡 Рулетка","web_app":{"url":BASE_URL + "/?tab=roulette"}}])
    rows.append([{"text":"📦 Мои заказы","web_app":{"url":BASE_URL + "/?tab=orders"}},
                 {"text":"💬 Поддержка","web_app":{"url":BASE_URL + "/?tab=support"}}])
    rows.append([{"text":"🤝 Стать продавцом","web_app":{"url":BASE_URL + "/?tab=seller"}}])
    rows.append([{"text":"📢 Новости","url":"https://t.me/shreksi4PubgNEWS"},
                 {"text":"💬 Наш чат","url":"https://t.me/chatshreksi4"}])
    if user_id == OWNER_ID:
        rows.append([{"text":"⚙️ Админ-панель","web_app":{"url":ADMIN_URL}}])
    return {"inline_keyboard": rows}


async def send_start(chat_id: int, user_id: int):
    kb = keyboard(user_id)
    if user_id != OWNER_ID and await is_shop_admin(user_id):
        kb["inline_keyboard"].append([{"text":"⚙️ Админ-панель","web_app":{"url":ADMIN_URL}}])
    await tg("sendMessage", {
      "chat_id": chat_id,
      "parse_mode": "HTML",
      "text": f"<b>Добро пожаловать в {html.escape(APP_NAME)}</b>\n\nМагазин товаров и услуг для PUBG Mobile • Metro Royale.\n\nВыберите нужный раздел:",
      "reply_markup": kb
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


async def send_roulette(chat_id: int):
    await tg("sendMessage", {
        "chat_id":chat_id,
        "parse_mode":"HTML",
        "text":("🎡 <b>Бесплатная рулетка Шрексича</b>\n\n"
                "Круглое колесо фортуны с Metro-наградами. "
                "До 3 бесплатных прокруток за 24 часа, дополнительные вращения — за бонусные билеты.\n\n"
                "Откройте колесо кнопкой ниже."),
        "reply_markup":{"inline_keyboard":[
            [{"text":"🎡 Крутить рулетку","web_app":{"url":BASE_URL + "/?tab=roulette"}}],
            [{"text":"📦 Платные кейсы","web_app":{"url":BASE_URL + "/?tab=spin"}}]
        ]}
    })


async def send_farm(chat_id: int):
    await tg("sendMessage", {
        "chat_id":chat_id,
        "parse_mode":"HTML",
        "text":("🌾 <b>Metro Farm — твоя ферма</b>\n\n"
                "Собирай ресурсы, продавай их за ShrekCOINS и улучшай буровую станцию, склад и торговый терминал.\n"
                "Забирай ежедневные награды за активность — внутри фермы.\n\n"
                "Нажми кнопку ниже, чтобы перейти прямо к добыче."),
        "reply_markup":{"inline_keyboard":[
            [{"text":"🌾 Открыть ферму","web_app":{"url":BASE_URL + "/?tab=farm"}}],
            [{"text":"🏠 Вернуться в магазин","web_app":{"url":BASE_URL}}]
        ]}
    })



async def send_seller(chat_id: int):
    await tg("sendMessage", {
        "chat_id":chat_id,
        "parse_mode":"HTML",
        "text":("🤝 <b>Партнёрская программа Шрексич SHOP</b>\n\n"
                "Добавляйте товары Metro Royale на витрину после одобрения администрации.\n"
                "Доли по новым заказам: продавцу 70%, магазину 20%, резерву 10% от оплаченных Stars.\n"
                "Расчёты с продавцами ведутся отдельно от Stars-платежей покупателей."),
        "reply_markup":{"inline_keyboard":[
            [{"text":"🤝 Открыть кабинет продавца","web_app":{"url":BASE_URL + "/?tab=seller"}}],
            [{"text":"🛒 Каталог товаров","web_app":{"url":BASE_URL + "/?tab=catalog"}}]
        ]}
    })


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
        "🎡 <b>Рулетка:</b> /roulette — до 3 бесплатных прокруток за 24 часа и дополнительные билеты.\n"
        "🎟 <b>Промокоды:</b> вводятся при оформлении заказа и уменьшают цену в Stars.\n"
        "👥 <b>Рефералы:</b> после первой оплаченной покупки приглашённого вы получаете 1 бонусный SPIN-билет и 3 SHR.\n"
        "🌾 <b>Ферма:</b> команда /farm откроет добычу ресурсов, склад и улучшения за ShrekCOINS.\n"
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
        answer = "🎰 Доступно до 3 бесплатных SPIN за 24 часа. Дополнительные бонусные билеты можно получить от администратора или за рефералов."
    elif any(x in q for x in ("ферм", "добыч", "shrekcoins", "шреккоин")):
        await send_farm(chat_id)
        return
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
    if msg and text.split("@")[0].split(" ")[0] == "/roulette":
        await send_roulette(int(msg["chat"]["id"]))
        return
    if msg and text.split("@")[0].split(" ")[0] == "/farm":
        await send_farm(int(msg["chat"]["id"]))
        return
    if msg and text.split("@")[0].split(" ")[0] == "/seller":
        await send_seller(int(msg["chat"]["id"]))
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
        error_message = "Платёж не соответствует операции"
        payload = pq.get("invoice_payload", "")
        try:
            parts = payload.split(":")
            conn = await db()
            try:
                if len(parts) == 3 and parts[0] == "case":
                    opening_id, uid = int(parts[1]), int(parts[2])
                    row = await (await conn.execute(
                        "SELECT * FROM case_openings WHERE id=? AND telegram_id=?",
                        (opening_id,uid)
                    )).fetchone()
                    ok = bool(
                        row and row["status"] == "awaiting_payment"
                        and pq.get("currency") == "XTR"
                        and int(pq.get("total_amount",0)) == int(row["stars_amount"])
                    )
                    if not ok:
                        error_message = "Счёт кейса устарел, уже оплачен или его цена изменилась"
                elif len(parts) == 3 and parts[0] == "order":
                    oid, uid = int(parts[1]), int(parts[2])
                    row = await (await conn.execute(
                        "SELECT * FROM orders WHERE id=? AND telegram_id=?",
                        (oid,uid)
                    )).fetchone()
                    ok = bool(
                        row and row["status"] == "Ожидает оплаты"
                        and pq.get("currency") == "XTR"
                        and int(pq.get("total_amount",0)) == int(row["stars_amount"])
                    )
                    if ok and int(row["seller_id"] or 0):
                        current_seller = await (await conn.execute(
                            "SELECT status FROM shop_sellers WHERE telegram_id=?",
                            (int(row["seller_id"]),)
                        )).fetchone()
                        ok = bool(
                            current_seller and current_seller["status"]=="approved"
                            and int(row["seller_reserved_until"] or 0)>int(time.time())
                        )
                        if not ok:
                            error_message = "Бронь товара продавца истекла или магазин недоступен. Создайте новый заказ."
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
                                (promo["id"],uid)
                            )).fetchone()
                        if not promo or redeemed:
                            ok = False
                            error_message = "Промокод истёк, закончился или уже использован"
                else:
                    error_message = "Неизвестный тип платежа"
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
        charge_id = sp.get("telegram_payment_charge_id", "")
        try:
            parts = payload.split(":")
            if len(parts) == 3 and parts[0] == "case":
                opening_id, uid = int(parts[1]), int(parts[2])
                async with db_write_lock:
                    conn = await db()
                    try:
                        await conn.execute("BEGIN IMMEDIATE")
                        row = await (await conn.execute(
                            "SELECT * FROM case_openings WHERE id=? AND telegram_id=?",
                            (opening_id,uid)
                        )).fetchone()
                        if not row:
                            await conn.rollback()
                            return
                        if row["telegram_charge_id"] or row["status"] in ("paid","opened"):
                            await conn.rollback()
                            return
                        if row["status"] != "awaiting_payment":
                            await conn.rollback()
                            return
                        await conn.execute(
                            "UPDATE case_openings SET status='paid',payment_method='Telegram Stars',"
                            "telegram_charge_id=?,paid_at=CURRENT_TIMESTAMP WHERE id=?",
                            (charge_id,opening_id)
                        )
                        await conn.commit()
                    finally:
                        await conn.close()
                return

            if len(parts) != 3 or parts[0] != "order":
                return
            oid, uid = int(parts[1]), int(parts[2])
            async with db_write_lock:
                conn = await db()
                try:
                    await conn.execute("BEGIN IMMEDIATE")
                    row = await (await conn.execute(
                        "SELECT * FROM orders WHERE id=? AND telegram_id=?",
                        (oid,uid)
                    )).fetchone()
                    if not row:
                        await conn.rollback()
                        return
                    if row["telegram_charge_id"]:
                        await conn.rollback()
                        return
                    seller_order = int(row["seller_id"] or 0)>0
                    reserved_payment = row["status"]=="Ожидает оплаты" and (
                        not seller_order or int(row["seller_reserved_until"] or 0)>int(time.time())
                    )
                    # A delayed Telegram charge must never silently allocate sold-out stock.
                    payment_status = "Оплачен" if reserved_payment else "Проверка оплаты"
                    await conn.execute(
                        "UPDATE orders SET status=?,payment_method='Telegram Stars',"
                        "telegram_charge_id=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                        (payment_status,charge_id,oid)
                    )
                    if row["promo_code"]:
                        promo = await (await conn.execute(
                            "SELECT id FROM promos WHERE code=? AND COALESCE(discount_percent,0)>0",
                            (row["promo_code"],)
                        )).fetchone()
                        if promo:
                            cur = await conn.execute(
                                "INSERT OR IGNORE INTO promo_redemptions(promo_id,telegram_id) VALUES(?,?)",
                                (promo["id"],uid)
                            )
                            if cur.rowcount:
                                await conn.execute("UPDATE promos SET uses=uses+1 WHERE id=?", (promo["id"],))
                    ref = await (await conn.execute(
                        "SELECT * FROM referrals WHERE referred_id=? AND rewarded=0",
                        (uid,)
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
            if seller_order:
                try:
                    await tg("sendMessage",{"chat_id":OWNER_ID,
                        "text":f"🛒 Оплата заказа #{oid}: {payment_status}. Продавец: {row['seller_id']}. Проверьте Owner Panel."})
                    if reserved_payment:
                        await tg("sendMessage",{"chat_id":int(row["seller_id"]),
                            "text":f"📦 Новый оплаченный заказ #{oid}: {row['product_name']}. Откройте раздел продавца в магазине."})
                except Exception:
                    pass
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
          {"command":"farm","description":"🌾 Открыть ферму"},
          {"command":"seller","description":"🤝 Стать продавцом"},
          {"command":"roulette","description":"🎡 Бесплатная рулетка"},
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



class SellerApplicationIn(BaseModel):
    display_name: str = Field(min_length=3,max_length=72)
    contact: str = Field(min_length=3,max_length=120)
    experience: str = Field(default="",max_length=700)
    rules_confirmed: bool = False

class SellerListingIn(BaseModel):
    category: str = Field(min_length=2,max_length=80)
    name: str = Field(min_length=3,max_length=120)
    description: str = Field(default="",max_length=1200)
    stars_price: int = Field(ge=1,le=100000)
    stock: int = Field(ge=1,le=1000)

class SellerRestockIn(BaseModel):
    stock_to_add: int = Field(ge=1,le=1000)

class SellerDeliveryIn(BaseModel):
    note: str = Field(min_length=5,max_length=700)

class AdminSellerDecisionIn(BaseModel):
    status: str
    commission_pct: int = Field(default=30,ge=30,le=30)

class AdminSellerListingDecisionIn(BaseModel):
    status: str

class AdminSellerSettlementIn(BaseModel):
    note: str = Field(min_length=5,max_length=400)

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
    tickets: int = Field(default=0, ge=0, le=1000000000)
    donation_tickets: int = Field(default=0, ge=0, le=1000000000)
    donation_case_id: str = Field(default="*", max_length=32)
    upgrade_points: int = Field(default=0, ge=0, le=1000000000)
    shrek_coins: int = Field(default=0, ge=0, le=1000000000000)


class AdminSetBalanceIn(BaseModel):
    token: str = Field(min_length=4,max_length=32)
    asset: str
    amount: int = Field(ge=0,le=1000000000000000)
    resource_id: str = ""
    case_id: str = "*"


class BroadcastIn(BaseModel):
    message: str = Field(min_length=1, max_length=3000)


class PromoCreateIn(BaseModel):
    code: str = Field(min_length=3, max_length=32)
    promo_type: str = Field(default="discount", max_length=24)
    discount_percent: int = Field(default=0, ge=0, le=90)
    spin_tickets: int = Field(default=0, ge=0, le=100)
    donation_tickets: int = Field(default=0, ge=0, le=100)
    case_id: str = Field(default="", max_length=32)
    max_uses: int = Field(default=0, ge=0, le=100000)
    expires_at: str = Field(default="", max_length=32)


class SpinPromoIn(BaseModel):
    code: str = Field(min_length=3, max_length=32)


class CaseStartIn(BaseModel):
    case_id: str = Field(min_length=2, max_length=32)


class CaseAdminIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    icon: str = Field(default="crate", max_length=32)
    stars_price: int = Field(default=0, ge=0, le=1000000)
    is_free: bool = False
    active: bool = True
    sort_order: int = Field(default=0, ge=0, le=10000)
    tiers: dict[str, float]
    contents: list[str]


class InventoryResolveIn(BaseModel):
    action: str = Field(min_length=4, max_length=8)


class FarmSellIn(BaseModel):
    resource_id: str = Field(min_length=1, max_length=64)
    qty: int = Field(default=1, ge=1, le=100000)


class FarmCoinUpgradeIn(BaseModel):
    module: str = Field(min_length=3, max_length=20)
    levels: int = Field(default=1, ge=1, le=100)
    max_upgrade: bool = False


class FarmWithdrawIn(BaseModel):
    pubg_uid: str = Field(min_length=5, max_length=64)
    uc_amount: int = Field(ge=120, le=100000)


class AdminFarmWithdrawalIn(BaseModel):
    status: str = Field(min_length=4, max_length=20)


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



SELLER_ORDER_HOLD_SECONDS = 30 * 60

async def expire_seller_reservations(conn):
    """Run under db_write_lock and BEGIN IMMEDIATE. Restore stock exactly once."""
    now = int(time.time())
    pending = await (await conn.execute(
        "SELECT id,product_id FROM orders WHERE seller_id>0 AND status='Ожидает оплаты' "
        "AND seller_reserved_until>0 AND seller_reserved_until<=?",
        (now,)
    )).fetchall()
    for o in pending:
        await conn.execute(
            "UPDATE orders SET status='Истёк',updated_at=CURRENT_TIMESTAMP WHERE id=? "
            "AND status='Ожидает оплаты'",
            (o["id"],)
        )
        await conn.execute(
            "UPDATE products SET seller_stock=seller_stock+1 WHERE id=? AND seller_id>0",
            (o["product_id"],)
        )

def shop_order_shares(stars_amount: int, commission_pct: int = 30):
    # 70% seller / 20% store / 10% reserve. Stars are indivisible.
    # Round the total 30% deduction up, then allocate approximately 20/10
    # inside it; ensure seller + store + reserve equals the paid amount.
    total=max(0,int(stars_amount))
    if int(commission_pct)!=30:
        raise ValueError("Комиссия новых заказов должна составлять 30%")
    platform=(total*30+99)//100
    store=min(platform,(total*20+99)//100)
    reserve=platform-store
    return (total-platform,store,reserve)


@app.get("/api/seller")
async def seller_dashboard(x_telegram_init_data: str | None = Header(default=None)):
    u = await current_user(x_telegram_init_data)
    uid=int(u["id"])
    async with db_write_lock:
        sweep_conn=await db()
        try:
            await sweep_conn.execute("BEGIN IMMEDIATE")
            await expire_seller_reservations(sweep_conn)
            await sweep_conn.commit()
        finally:
            await sweep_conn.close()
    conn=await db()
    try:
        profile=await (await conn.execute(
            "SELECT * FROM shop_sellers WHERE telegram_id=?",(uid,)
        )).fetchone()
        listings=await (await conn.execute(
            "SELECT id,name,category,description,stars_price,seller_stock,seller_status,active "
            "FROM products WHERE seller_id=? ORDER BY id DESC",(uid,)
        )).fetchall()
        # No buyer data is shared before a payment is confirmed.
        jobs=await (await conn.execute(
            "SELECT id,number,product_name,stars_amount,seller_share_stars,platform_share_stars,"
            "reserve_share_stars,status,uid,nickname,comment,seller_delivery_note,updated_at "
            "FROM orders WHERE seller_id=? AND telegram_charge_id<>'' ORDER BY id DESC LIMIT 100",
            (uid,)
        )).fetchall()
        payouts=await (await conn.execute("SELECT id,amount,status,created_at,available_at,reason FROM seller_payout_requests WHERE seller_id=? ORDER BY id DESC LIMIT 50",(uid,))).fetchall()
        settlements=await (await conn.execute(
            "SELECT order_id,seller_stars,note FROM seller_settlement_log WHERE seller_id=? "
            "ORDER BY id DESC LIMIT 100",(uid,)
        )).fetchall()
    finally:
        await conn.close()
    paid_ids={int(x["order_id"]) for x in settlements}
    return {"profile":dict(profile) if profile else None,
            "listings":[dict(x) for x in listings],
            "orders":[{**dict(x),"settled":int(x["id"]) in paid_ids} for x in jobs],
            "settlements":[dict(x) for x in settlements],"payouts":[dict(x) for x in payouts]}

@app.post("/api/seller/apply")
async def seller_apply(body: SellerApplicationIn, x_telegram_init_data: str | None = Header(default=None)):
    u=await current_user(x_telegram_init_data)
    if not body.rules_confirmed:
        raise HTTPException(400,"Подтвердите ответственность за законность товара и наличие остатков")
    uid=int(u["id"])
    async with db_write_lock:
        conn=await db()
        try:
            await conn.execute("BEGIN IMMEDIATE")
            old=await (await conn.execute(
                "SELECT status FROM shop_sellers WHERE telegram_id=?",(uid,)
            )).fetchone()
            if old and old["status"]=="removed":
                old=None
            if old and old["status"]=="blocked":
                await conn.rollback()
                raise HTTPException(403,"Заявка заблокирована администрацией")
            if old and old["status"]=="pending":
                await conn.rollback()
                raise HTTPException(409,"Ваша заявка уже на рассмотрении")
            if old and old["status"]=="approved":
                await conn.rollback()
                raise HTTPException(409,"Вы уже продавец")
            await conn.execute(
                "INSERT INTO shop_sellers(telegram_id,display_name,contact,experience,rules_confirmed,status) "
                "VALUES(?,?,?,?,1,'pending') "
                "ON CONFLICT(telegram_id) DO UPDATE SET display_name=excluded.display_name,"
                "contact=excluded.contact,experience=excluded.experience,rules_confirmed=1,"
                "status='pending',updated_at=CURRENT_TIMESTAMP",
                (uid,body.display_name.strip(),body.contact.strip(),body.experience.strip())
            )
            await conn.commit()
        finally:
            await conn.close()
    try:
        await tg("sendMessage",{"chat_id":OWNER_ID,"text":"🧾 Новая заявка продавца: "+body.display_name[:72]+
                  "\nПроверьте раздел «Продавцы» в админ-панели."})
    except Exception:
        pass
    return {"ok":True,"status":"pending"}

@app.post("/api/seller/listings")
async def seller_create_listing(body: SellerListingIn, x_telegram_init_data: str | None = Header(default=None)):
    u=await current_user(x_telegram_init_data)
    uid=int(u["id"])
    async with db_write_lock:
        conn=await db()
        try:
            await conn.execute("BEGIN IMMEDIATE")
            profile=await (await conn.execute(
                "SELECT status FROM shop_sellers WHERE telegram_id=?",(uid,)
            )).fetchone()
            if not profile or profile["status"]!="approved":
                await conn.rollback()
                raise HTTPException(403,"Только подтверждённый продавец может добавлять товары")
            count=await (await conn.execute(
                "SELECT COUNT(*) c FROM products WHERE seller_id=?",(uid,)
            )).fetchone()
            if int(count["c"] or 0)>=100:
                await conn.rollback()
                raise HTTPException(409,"Максимум 100 товаров на одного продавца")
            cursor=await conn.execute(
                "INSERT INTO products(category,name,description,price,stars_price,active,sort_order,"
                "seller_id,seller_stock,seller_status) VALUES(?,?,?,?,?,0,100,?,?,'pending')",
                (body.category.strip(),body.name.strip(),body.description.strip() or "Товар продавца. Условия выдачи уточняйте перед покупкой.",body.stars_price,
                 body.stars_price,uid,body.stock)
            )
            await conn.commit()
            lid=cursor.lastrowid
        finally:
            await conn.close()
    try:
        await tg("sendMessage",{"chat_id":OWNER_ID,"text":"📦 Новый товар на модерации в Шрексиче!\\nПродавец ID: "+str(uid)+"\\nТовар #"+str(lid)+": "+body.name.strip()[:100]+"\\nЦена: "+str(body.stars_price)+" ⭐ · Остаток: "+str(body.stock)+"\\nОткройте админ-панель → Продавцы → Модерация товаров."})
    except Exception:
        pass
    return {"ok":True,"id":lid,"status":"pending"}

@app.post("/api/seller/listings/{listing_id}/restock")
async def seller_restock(listing_id:int, body:SellerRestockIn,
                         x_telegram_init_data: str | None = Header(default=None)):
    u=await current_user(x_telegram_init_data)
    uid=int(u["id"])
    async with db_write_lock:
        conn=await db()
        try:
            await conn.execute("BEGIN IMMEDIATE")
            profile=await (await conn.execute(
                "SELECT status FROM shop_sellers WHERE telegram_id=?",(uid,)
            )).fetchone()
            if not profile or profile["status"]!="approved":
                await conn.rollback()
                raise HTTPException(403,"Нет доступа")
            cur=await conn.execute(
                "UPDATE products SET seller_stock=seller_stock+? WHERE id=? AND seller_id=? "
                "AND seller_stock+?<=100000",
                (body.stock_to_add,listing_id,uid,body.stock_to_add)
            )
            if cur.rowcount!=1:
                await conn.rollback()
                raise HTTPException(404,"Товар не найден или превышен лимит остатков")
            await conn.commit()
        finally:
            await conn.close()
    return {"ok":True}


@app.post("/api/seller/listings/{listing_id}/pause")
async def seller_pause_listing(listing_id: int, x_telegram_init_data: str | None = Header(default=None)):
    """Seller can stop NEW purchases without affecting paid/reserved orders."""
    u = await current_user(x_telegram_init_data)
    uid = int(u["id"])
    async with db_write_lock:
        conn = await db()
        try:
            await conn.execute("BEGIN IMMEDIATE")
            seller = await (await conn.execute(
                "SELECT status FROM shop_sellers WHERE telegram_id=?",(uid,)
            )).fetchone()
            if not seller or seller["status"]!="approved":
                await conn.rollback()
                raise HTTPException(403,"Нет доступа")
            cur = await conn.execute(
                "UPDATE products SET seller_status='paused',active=0 "
                "WHERE id=? AND seller_id=? AND seller_status='active'",
                (listing_id,uid)
            )
            if cur.rowcount!=1:
                await conn.rollback()
                raise HTTPException(409,"Остановить можно только активный товар")
            await conn.commit()
        finally:
            await conn.close()
    return {"ok":True,"status":"paused"}

@app.post("/api/seller/listings/{listing_id}/review")
async def seller_request_listing_review(listing_id: int, x_telegram_init_data: str | None = Header(default=None)):
    """Reactivation always requires owner review."""
    u = await current_user(x_telegram_init_data)
    uid = int(u["id"])
    async with db_write_lock:
        conn = await db()
        try:
            await conn.execute("BEGIN IMMEDIATE")
            seller = await (await conn.execute(
                "SELECT status FROM shop_sellers WHERE telegram_id=?",(uid,)
            )).fetchone()
            if not seller or seller["status"]!="approved":
                await conn.rollback()
                raise HTTPException(403,"Нет доступа")
            cur = await conn.execute(
                "UPDATE products SET seller_status='pending',active=0 "
                "WHERE id=? AND seller_id=? AND seller_status='paused' AND seller_stock>0",
                (listing_id,uid)
            )
            if cur.rowcount!=1:
                await conn.rollback()
                raise HTTPException(409,"Отправить на проверку можно только приостановленный товар с остатком")
            await conn.commit()
        finally:
            await conn.close()
    return {"ok":True,"status":"pending"}


@app.post("/api/seller/orders/{order_id}/delivered")
async def seller_mark_delivered(order_id:int,body:SellerDeliveryIn,
                                x_telegram_init_data: str | None = Header(default=None)):
    u=await current_user(x_telegram_init_data)
    uid=int(u["id"])
    async with db_write_lock:
        conn=await db()
        try:
            await conn.execute("BEGIN IMMEDIATE")
            seller=await (await conn.execute(
                "SELECT status FROM shop_sellers WHERE telegram_id=?",(uid,)
            )).fetchone()
            order=await (await conn.execute(
                "SELECT id,status,telegram_charge_id FROM orders WHERE id=? AND seller_id=?",
                (order_id,uid)
            )).fetchone()
            if not seller or seller["status"]!="approved" or not order or not order["telegram_charge_id"]\
               or order["status"] not in ("Оплачен","Принят","В работе"):
                await conn.rollback()
                raise HTTPException(409,"Заказ недоступен для подтверждения")
            await conn.execute(
                "UPDATE orders SET status='Проверка выдачи',seller_delivery_note=?,"
                "seller_submitted_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (body.note.strip(),order_id)
            )
            await conn.commit()
        finally:
            await conn.close()
    try:
        await tg("sendMessage",{"chat_id":OWNER_ID,
            "text":f"✅ Продавец отметил заказ #{order_id} выданным. Проверьте заказ в Owner Panel."})
    except Exception:
        pass
    return {"ok":True,"status":"Проверка выдачи"}


class SellerPayoutIn(BaseModel):
    amount: int = Field(ge=1,le=10000000)
    proof: str = Field(min_length=15,max_length=1500)
    payment_details: str = Field(min_length=5,max_length=500)

class SellerPayoutDecisionIn(BaseModel):
    action: str
    reason: str = Field(default="",max_length=1000)
    payment_reference: str = Field(default="",max_length=500)

@app.post("/api/seller/payouts")
async def seller_request_payout(body:SellerPayoutIn,x_telegram_init_data:str|None=Header(default=None)):
    uid=int((await current_user(x_telegram_init_data))["id"])
    async with db_write_lock:
        conn=await db()
        try:
            await conn.execute("BEGIN IMMEDIATE")
            seller=await (await conn.execute("SELECT status FROM shop_sellers WHERE telegram_id=?",(uid,))).fetchone()
            if not seller or seller["status"]!="approved":
                raise HTTPException(403,"Продавец не одобрен")
            eligible=await (await conn.execute("""
                SELECT COALESCE(SUM(o.seller_share_stars),0) n FROM orders o
                LEFT JOIN seller_settlement_log l ON l.order_id=o.id
                WHERE o.seller_id=? AND o.status='Выполнен' AND o.telegram_charge_id<>'' AND l.id IS NULL
            """,(uid,))).fetchone()
            reserved=await (await conn.execute("SELECT COALESCE(SUM(amount),0) n FROM seller_payout_requests WHERE seller_id=? AND status IN ('pending','approved','ready','frozen')",(uid,))).fetchone()
            available=max(0,int(eligible["n"])-int(reserved["n"]))
            if body.amount>available:
                raise HTTPException(409,"Недостаточно доступных средств")
            await conn.execute("INSERT INTO seller_payout_requests(seller_id,amount,proof,payment_details,created_at) VALUES(?,?,?,?,?)",(uid,body.amount,body.proof.strip(),body.payment_details.strip(),int(time.time())))
            await conn.commit()
        except:
            await conn.rollback()
            raise
        finally:
            await conn.close()
    try:
        await tg("sendMessage",{"chat_id":OWNER_ID,"text":f"💸 Новая заявка на выплату от продавца {uid}: {body.amount} ⭐. Проверьте доказательства в админке."})
    except Exception:
        pass
    return {"ok":True}

@app.post("/api/admin/seller-payouts/{payout_id}")
async def admin_seller_payout_decision(payout_id:int,body:SellerPayoutDecisionIn,x_telegram_init_data:str|None=Header(default=None)):
    admin=await owner(x_telegram_init_data)
    action=body.action
    if action not in ("approve","freeze","reject","unfreeze","paid"):
        raise HTTPException(400,"Недопустимое действие")
    async with db_write_lock:
        conn=await db()
        try:
            await conn.execute("BEGIN IMMEDIATE")
            p=await (await conn.execute("SELECT * FROM seller_payout_requests WHERE id=?",(payout_id,))).fetchone()
            if not p:
                raise HTTPException(404,"Заявка не найдена")
            status=p["status"]
            now=int(time.time())
            if action=="approve" and status=="pending":
                await conn.execute("UPDATE seller_payout_requests SET status='approved',approved_at=?,available_at=?,reviewed_by=? WHERE id=?",(now,now+24*86400,OWNER_ID,payout_id))
            elif action=="freeze" and status in ("pending","approved","ready"):
                if len(body.reason.strip())<5: raise HTTPException(400,"Укажите причину блокировки")
                await conn.execute("UPDATE seller_payout_requests SET status='frozen',reason=? WHERE id=?",(body.reason.strip(),payout_id))
            elif action=="reject" and status in ("pending","approved","ready","frozen"):
                if len(body.reason.strip())<5: raise HTTPException(400,"Укажите причину отказа")
                await conn.execute("UPDATE seller_payout_requests SET status='rejected',reason=? WHERE id=?",(body.reason.strip(),payout_id))
            elif action=="unfreeze" and status=="frozen" and int(p["approved_at"])>0:
                await conn.execute("UPDATE seller_payout_requests SET status='approved',reason='' WHERE id=?",(payout_id,))
            elif action=="paid" and status in ("approved","ready") and now>=int(p["available_at"])>0:
                if len(body.payment_reference.strip())<6: raise HTTPException(400,"Укажите подтверждение реального перевода")
                seller=await (await conn.execute("SELECT status FROM shop_sellers WHERE telegram_id=?",(p["seller_id"],))).fetchone()
                if not seller or seller["status"]!="approved": raise HTTPException(409,"Продавец заблокирован")
                rows=await (await conn.execute("""
                    SELECT o.id,o.seller_share_stars FROM orders o LEFT JOIN seller_settlement_log l ON l.order_id=o.id
                    WHERE o.seller_id=? AND o.status='Выполнен' AND o.telegram_charge_id<>'' AND l.id IS NULL ORDER BY o.id
                """,(p["seller_id"],))).fetchall()
                remaining=int(p["amount"])
                for o in rows:
                    if remaining<=0: break
                    # A partial order payout is deliberately forbidden to preserve one-order-one-settlement accounting.
                    if int(o["seller_share_stars"])>remaining: continue
                    await conn.execute("INSERT INTO seller_settlement_log(order_id,seller_id,seller_stars,note) VALUES(?,?,?,?)",(o["id"],p["seller_id"],o["seller_share_stars"],"Заявка #"+str(payout_id)+" · "+body.payment_reference.strip()))
                    remaining-=int(o["seller_share_stars"])
                if remaining: raise HTTPException(409,"Сумма не соответствует целым неоплаченным заказам; выплата не зафиксирована")
                await conn.execute("UPDATE seller_payout_requests SET status='paid',paid_note=? WHERE id=?",(body.payment_reference.strip(),payout_id))
            else:
                raise HTTPException(409,"Недопустимый переход статуса или срок ожидания ещё не истёк")
            await conn.commit()
        except:
            await conn.rollback()
            raise
        finally:
            await conn.close()
    return {"ok":True}

@app.get("/api/admin/sellers")
async def admin_sellers(x_telegram_init_data: str | None = Header(default=None)):
    await owner(x_telegram_init_data)
    conn=await db()
    try:
        sellers=await (await conn.execute(
            "SELECT s.*,u.token,u.username,(SELECT COUNT(*) FROM seller_warnings w WHERE w.seller_id=s.telegram_id) warning_count,(SELECT ROUND(AVG(r.rating),2) FROM seller_reviews r WHERE r.seller_id=s.telegram_id) avg_rating,(SELECT COUNT(*) FROM seller_reviews r WHERE r.seller_id=s.telegram_id) review_count FROM shop_sellers s LEFT JOIN users u "
            "ON u.telegram_id=s.telegram_id ORDER BY s.created_at DESC"
        )).fetchall()
        listings=await (await conn.execute(
            "SELECT p.*,s.display_name seller_name FROM products p "
            "LEFT JOIN shop_sellers s ON s.telegram_id=p.seller_id "
            "WHERE p.seller_id>0 ORDER BY p.id DESC LIMIT 500"
        )).fetchall()
        payouts=await (await conn.execute("SELECT p.*,s.display_name FROM seller_payout_requests p LEFT JOIN shop_sellers s ON s.telegram_id=p.seller_id ORDER BY p.id DESC LIMIT 200")).fetchall()
        removals=await (await conn.execute("SELECT seller_id,display_name,reason,removed_at FROM seller_removals ORDER BY id DESC LIMIT 200")).fetchall()
        jobs=await (await conn.execute(
            "SELECT o.id,o.number,o.product_name,o.status,o.stars_amount,o.seller_share_stars,"
            "o.platform_share_stars,o.reserve_share_stars,o.seller_delivery_note,o.telegram_charge_id,o.seller_id,"
            "s.display_name seller_name,COALESCE(x.id,0) settled_id "
            "FROM orders o JOIN shop_sellers s ON s.telegram_id=o.seller_id "
            "LEFT JOIN seller_settlement_log x ON x.order_id=o.id "
            "WHERE o.seller_id>0 AND o.telegram_charge_id<>'' ORDER BY o.id DESC LIMIT 250"
        )).fetchall()
    finally:
        await conn.close()
    return {"sellers":[dict(x) for x in sellers],"listings":[dict(x) for x in listings],
            "orders":[dict(x) for x in jobs],"removals":[dict(x) for x in removals],"payouts":[dict(x) for x in payouts]}



class SellerRemovalIn(BaseModel):
    reason: str = Field(min_length=5,max_length=600)

class SellerContactIn(BaseModel):
    message: str = Field(min_length=1,max_length=1500)

@app.post("/api/admin/sellers/{seller_id}/contact")
async def admin_contact_seller(seller_id:int,body:SellerContactIn,x_telegram_init_data:str|None=Header(default=None)):
    await owner(x_telegram_init_data)
    conn=await db()
    try:
        seller=await (await conn.execute("SELECT telegram_id FROM shop_sellers WHERE telegram_id=?",(seller_id,))).fetchone()
        if not seller: raise HTTPException(404,"Продавец не найден")
    finally:
        await conn.close()
    try:
        await tg("sendMessage",{"chat_id":seller_id,"text":"💬 Сообщение от администрации Шрексича:\\n"+body.message.strip()+"\\n\\nДля ответа напишите администрации через поддержку бота."})
    except Exception:
        raise HTTPException(502,"Telegram не доставил сообщение. Продавец должен сначала запустить бота.")
    return {"ok":True}

@app.post("/api/admin/sellers/{seller_id}/remove")
async def admin_remove_seller(seller_id:int,body:SellerRemovalIn,x_telegram_init_data:str|None=Header(default=None)):
    await owner(x_telegram_init_data)
    async with db_write_lock:
        conn=await db()
        try:
            await conn.execute("BEGIN IMMEDIATE")
            seller=await (await conn.execute("SELECT display_name,status FROM shop_sellers WHERE telegram_id=?",(seller_id,))).fetchone()
            if not seller or seller["status"]=="removed":
                await conn.rollback()
                raise HTTPException(409,"Продавец уже удалён или не найден")
            await conn.execute("INSERT INTO seller_removals(seller_id,display_name,reason) VALUES(?,?,?)",(seller_id,seller["display_name"],body.reason.strip()))
            await conn.execute("UPDATE shop_sellers SET status='removed',updated_at=CURRENT_TIMESTAMP WHERE telegram_id=?",(seller_id,))
            await conn.execute("UPDATE products SET active=0,seller_status='paused' WHERE seller_id=?",(seller_id,))
            await conn.commit()
        finally:
            await conn.close()
    try:
        await tg("sendMessage",{"chat_id":seller_id,"text":"⛔ Ваш статус продавца удалён. Причина: "+body.reason.strip()+"\\nДля возвращения подайте новую заявку в разделе «Продавцам»."})
    except Exception: pass
    return {"ok":True}

class SellerWarningIn(BaseModel):
    reason: str = Field(min_length=5,max_length=600)

@app.post("/api/admin/sellers/{seller_id}/warnings")
async def admin_issue_seller_warning(seller_id:int,body:SellerWarningIn,x_telegram_init_data:str|None=Header(default=None)):
    await owner(x_telegram_init_data)
    async with db_write_lock:
        conn=await db()
        try:
            seller=await (await conn.execute("SELECT status FROM shop_sellers WHERE telegram_id=?",(seller_id,))).fetchone()
            if not seller or seller["status"]!="approved":
                raise HTTPException(409,"Выговор доступен только действующему продавцу")
            await conn.execute("INSERT INTO seller_warnings(seller_id,reason) VALUES(?,?)",(seller_id,body.reason.strip()))
            await conn.commit()
        finally:
            await conn.close()
    try:
        await tg("sendMessage",{"chat_id":seller_id,"text":"⚠️ Вам выдан выговор в Шрексиче. Причина: "+body.reason.strip()})
    except Exception:
        pass
    return {"ok":True}

@app.get("/api/admin/sellers/{seller_id}/history")
async def admin_seller_history(seller_id:int,x_telegram_init_data:str|None=Header(default=None)):
    await owner(x_telegram_init_data)
    conn=await db()
    try:
        warnings=await (await conn.execute("SELECT id,reason,created_at FROM seller_warnings WHERE seller_id=? ORDER BY id DESC",(seller_id,))).fetchall()
        reviews=await (await conn.execute("SELECT rating,comment,created_at FROM seller_reviews WHERE seller_id=? ORDER BY id DESC LIMIT 100",(seller_id,))).fetchall()
        return {"warnings":[dict(x) for x in warnings],"reviews":[dict(x) for x in reviews]}
    finally:
        await conn.close()

@app.patch("/api/admin/sellers/{seller_id}")
async def admin_seller_decision(seller_id:int,body:AdminSellerDecisionIn,
                                x_telegram_init_data: str | None = Header(default=None)):
    await owner(x_telegram_init_data)
    if body.status not in ("approved","blocked"):
        raise HTTPException(400,"Некорректный статус")
    if body.status=="approved":
        conn=await db()
        try:
            existing=await (await conn.execute("SELECT status FROM shop_sellers WHERE telegram_id=?",(seller_id,))).fetchone()
            if not existing or existing["status"]!="pending":
                raise HTTPException(409,"Одобрить можно только новую заявку")
        finally:
            await conn.close()
    async with db_write_lock:
        conn=await db()
        try:
            cur=await conn.execute(
                "UPDATE shop_sellers SET status=?,commission_pct=30,updated_at=CURRENT_TIMESTAMP "
                "WHERE telegram_id=?",(body.status,seller_id)
            )
            if cur.rowcount!=1:
                raise HTTPException(404,"Продавец не найден")
            await conn.commit()
        finally:
            await conn.close()
    try:
        if body.status=="approved":
            await tg("sendMessage",{"chat_id":seller_id,"text":"✅ Ваша заявка продавца в Шрексиче одобрена! Откройте Mini App → Продавцам, чтобы увидеть кабинет и добавить товары."})
        elif body.status=="blocked":
            await tg("sendMessage",{"chat_id":seller_id,"text":"⛔ Ваш доступ продавца в Шрексиче заблокирован. Обратитесь к администрации."})
    except Exception:
        pass
    return {"ok":True}

@app.patch("/api/admin/seller-listings/{listing_id}")
async def admin_seller_listing(listing_id:int,body:AdminSellerListingDecisionIn,
                               x_telegram_init_data: str | None = Header(default=None)):
    await owner(x_telegram_init_data)
    if body.status not in ("active","rejected","paused"):
        raise HTTPException(400,"Некорректный статус товара")
    async with db_write_lock:
        conn=await db()
        try:
            cur=await conn.execute(
                "UPDATE products SET seller_status=?,active=? WHERE id=? AND seller_id>0",
                (body.status,1 if body.status=="active" else 0,listing_id)
            )
            if cur.rowcount!=1:
                raise HTTPException(404,"Товар продавца не найден")
            await conn.commit()
        finally:
            await conn.close()
    try:
        conn=await db()
        try:
            product=await (await conn.execute("SELECT seller_id,name FROM products WHERE id=?",(listing_id,))).fetchone()
        finally:
            await conn.close()
        if product:
            message=("✅ Товар опубликован в каталоге" if body.status=="active" else "❌ Товар отклонён" if body.status=="rejected" else "⏸ Товар скрыт из каталога")
            await tg("sendMessage",{"chat_id":int(product["seller_id"]),"text":message+": "+str(product["name"])[:120]})
    except Exception:
        pass
    return {"ok":True}

@app.post("/api/admin/seller-orders/{order_id}/settle")
async def admin_settle_seller_order(order_id:int,body:AdminSellerSettlementIn,
                                   x_telegram_init_data: str | None = Header(default=None)):
    await owner(x_telegram_init_data)
    raise HTTPException(409,"Прямые расчёты отключены: используйте защищённые заявки продавцов")
    async with db_write_lock:
        conn=await db()
        try:
            await conn.execute("BEGIN IMMEDIATE")
            order=await (await conn.execute(
                "SELECT seller_id,seller_share_stars,status,telegram_charge_id "
                "FROM orders WHERE id=?",(order_id,)
            )).fetchone()
            if not order or not int(order["seller_id"] or 0) or order["status"]!="Выполнен"\
               or not order["telegram_charge_id"]:
                await conn.rollback()
                raise HTTPException(409,"Расчёт допускается только после подтверждения выдачи товара")
            old=await (await conn.execute(
                "SELECT id FROM seller_settlement_log WHERE order_id=?",(order_id,)
            )).fetchone()
            if old:
                await conn.rollback()
                raise HTTPException(409,"Этот заказ уже отмечен оплаченным продавцу")
            await conn.execute(
                "INSERT INTO seller_settlement_log(order_id,seller_id,seller_stars,note) "
                "VALUES(?,?,?,?)",
                (order_id,int(order["seller_id"]),int(order["seller_share_stars"]),body.note.strip())
            )
            await conn.commit()
        finally:
            await conn.close()
    return {"ok":True,"settlement_recorded":True}


@app.get("/api/catalog")
async def catalog():
    async with db_write_lock:
        conn = await db()
        try:
            await conn.execute("BEGIN IMMEDIATE")
            await expire_seller_reservations(conn)
            rows = await (await conn.execute(
                "SELECT p.*,s.display_name seller_name,COALESCE((SELECT ROUND(AVG(r.rating),2) FROM seller_reviews r WHERE r.seller_id=p.seller_id),0) seller_rating,COALESCE((SELECT COUNT(*) FROM seller_reviews r WHERE r.seller_id=p.seller_id),0) seller_review_count FROM products p "
                "LEFT JOIN shop_sellers s ON s.telegram_id=p.seller_id "
                "WHERE p.active=1 AND (p.seller_id=0 OR "
                "(p.seller_status='active' AND p.seller_stock>0 AND s.status='approved')) "
                "ORDER BY p.sort_order,p.id"
            )).fetchall()
            await conn.commit()
        finally:
            await conn.close()
    return [dict(r) for r in rows]


@app.get("/api/me")
async def me(x_telegram_init_data: str | None = Header(default=None)):
    u = await current_user(x_telegram_init_data)
    return {"token":u["token"],"first_name":u.get("first_name"),"username":u.get("username"),"owner":await is_shop_admin(int(u["id"])), "super_owner":int(u["id"])==OWNER_ID}


@app.post("/api/orders")
async def create_order(body: OrderIn, x_telegram_init_data: str | None = Header(default=None)):
    u = await current_user(x_telegram_init_data)
    promo_code = body.promo_code.strip().upper()
    async with db_write_lock:
        conn = await db()
        try:
            await conn.execute("BEGIN IMMEDIATE")
            await expire_seller_reservations(conn)
            p = await (await conn.execute("SELECT * FROM products WHERE id=? AND active=1",(body.product_id,))).fetchone()
            if not p:
                await conn.rollback()
                raise HTTPException(404,"Товар не найден")
            seller_id = int(p["seller_id"] or 0)
            seller = None
            if seller_id:
                seller = await (await conn.execute(
                    "SELECT status,commission_pct FROM shop_sellers WHERE telegram_id=?",(seller_id,)
                )).fetchone()
                if not seller or seller["status"]!="approved" or p["seller_status"]!="active" or int(p["seller_stock"] or 0)<1:
                    await conn.rollback()
                    raise HTTPException(409,"Предмет у этого продавца закончился")
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
            pct = 30 if seller else 0
            seller_share,store_share,reserve_share = shop_order_shares(stars_amount,pct) if seller else (0,0,0)
            platform_share = store_share+reserve_share
            if seller_id:
                reserved = await conn.execute(
                    "UPDATE products SET seller_stock=seller_stock-1 WHERE id=? AND seller_id=? "
                    "AND seller_stock>0 AND seller_status='active' AND active=1",
                    (p["id"],seller_id)
                )
                if reserved.rowcount!=1:
                    await conn.rollback()
                    raise HTTPException(409,"Товар закончился, попробуйте другой")
            cur = await conn.execute(
              "INSERT INTO orders(number,telegram_id,product_id,product_name,amount,stars_amount,"
              "uid,nickname,comment,promo_code,discount_percent,seller_id,seller_commission_pct,"
              "seller_share_stars,platform_share_stars,reserve_share_stars,seller_reserved_until) "
              "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
              (number,int(u["id"]),p["id"],p["name"],p["price"],stars_amount,body.uid,body.nickname,
               body.comment,promo_code,discount,seller_id,pct,seller_share,platform_share,reserve_share,
               int(time.time())+SELLER_ORDER_HOLD_SECONDS if seller_id else 0)
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



@app.post("/api/orders/{order_id}/cancel")
async def cancel_unpaid_order(order_id: int, x_telegram_init_data: str | None = Header(default=None)):
    """Buyer may release a seller's reserved item before payment, exactly once."""
    u = await current_user(x_telegram_init_data)
    uid = int(u["id"])
    async with db_write_lock:
        conn = await db()
        try:
            await conn.execute("BEGIN IMMEDIATE")
            await expire_seller_reservations(conn)
            row = await (await conn.execute(
                "SELECT product_id,seller_id,status,telegram_charge_id FROM orders "
                "WHERE id=? AND telegram_id=?",(order_id,uid)
            )).fetchone()
            if not row:
                await conn.rollback()
                raise HTTPException(404,"Заказ не найден")
            if row["status"]!="Ожидает оплаты" or row["telegram_charge_id"]:
                await conn.rollback()
                raise HTTPException(409,"Отменить можно только неоплаченный заказ")
            await conn.execute(
                "UPDATE orders SET status='Отменён',updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (order_id,)
            )
            if int(row["seller_id"] or 0)>0:
                await conn.execute(
                    "UPDATE products SET seller_stock=seller_stock+1 WHERE id=? AND seller_id=?",
                    (int(row["product_id"]),int(row["seller_id"]))
                )
            await conn.commit()
        finally:
            await conn.close()
    return {"ok":True,"status":"Отменён"}


@app.post("/api/orders/{order_id}/stars")
async def stars(order_id: int, x_telegram_init_data: str | None = Header(default=None)):
    u = await current_user(x_telegram_init_data)
    conn = await db()
    row = await (await conn.execute("SELECT * FROM orders WHERE id=? AND telegram_id=?",(order_id,int(u["id"])))).fetchone()
    await conn.close()
    if not row: raise HTTPException(404,"Заказ не найден")
    if row["status"] != "Ожидает оплаты": raise HTTPException(409,"Заказ уже обработан")
    if int(row["seller_id"] or 0)>0 and int(row["seller_reserved_until"] or 0)<=int(time.time()):
        raise HTTPException(409,"Бронь товара продавца истекла. Оформите заказ заново.")
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
            pending = await (await conn.execute(
                "SELECT id,reward_name,reward_tier,sell_shr,value_stars,source,created_at "
                "FROM inventory_items WHERE telegram_id=? AND status='pending' "
                "ORDER BY id DESC LIMIT 1",
                (uid,)
            )).fetchone()
            paid_case = await (await conn.execute(
                "SELECT id,case_id,case_name,stars_amount,payment_method,created_at,paid_at "
                "FROM case_openings WHERE telegram_id=? AND status='paid' ORDER BY id ASC LIMIT 1",
                (uid,)
            )).fetchone()
            all_cases = await load_case_catalog(conn,uid,True)
            roulette_cfg = next((x for x in all_cases if x["id"] == "FREE"), None)
            case_catalog = [x for x in all_cases if x.get("active") and x["id"] != "FREE"]
            if paid_case and not any(x["id"] == paid_case["case_id"] for x in case_catalog):
                paid_cfg = next((x for x in all_cases if x["id"] == paid_case["case_id"]), None)
                if paid_cfg:
                    case_catalog.append(paid_cfg)
            donation_rows = await (await conn.execute(
                "SELECT case_id,tickets FROM donation_ticket_balances WHERE telegram_id=? AND tickets>0",
                (uid,)
            )).fetchall()
        finally:
            await conn.close()
    used = int(used_row["c"] or 0)
    free_remaining = max(0, MAX_FREE_SPINS_24H - used)
    bonus_tickets = max(0, int(state["tickets"] or 0))
    next_reset = 0
    if free_remaining == 0 and used_row["first_ts"]:
        next_reset = max(0, int(used_row["first_ts"]) + 86400 - int(time.time()))
    donation_wallet = {str(x["case_id"]):int(x["tickets"] or 0) for x in donation_rows}
    return {
      "free_remaining":free_remaining,
      "max_free_spins":MAX_FREE_SPINS_24H,
      "bonus_tickets":bonus_tickets,
      "remaining_spins":free_remaining + bonus_tickets,
      "donation_tickets_total":sum(donation_wallet.values()),
      "donation_ticket_wallet":donation_wallet,
      "shr":int(state["upgrade_points"]),
      "upgrade_points":int(state["upgrade_points"]),
      "next_reset_seconds":next_reset,
      "history":[dict(x) for x in history],
      "upgrade_rewards":SHR_REWARDS,
      "tier_chances":SPIN_TIER_CHANCES,
      "rewards":[{"name":x["name"],"tier":x["tier"],"value_stars":x["value_stars"]} for x in SPIN_REWARDS],
      "case_catalog":case_catalog,
      "roulette":roulette_cfg,
      "paid_case_opening":dict(paid_case) if paid_case else None,
      "pending_drop":(
        {
          "inventory_item_id":int(pending["id"]),
          "sell_shr":int(pending["sell_shr"]),
          "source":pending["source"],
          "created_at":pending["created_at"],
          "reward":{
            "name":pending["reward_name"],
            "tier":pending["reward_tier"],
            "points":int(pending["sell_shr"]),
            "value_stars":int(pending["value_stars"])
          }
        } if pending else None
      )
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
    allowed_tiers = {"ALL","GRAY","CYAN","BLUE","PURPLE","PINK","RED","GOLD","RAINBOW","COMMON","RARE","EPIC","LEGENDARY","MYTHIC"}
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
            pending = await (await conn.execute(
                "SELECT id FROM inventory_items WHERE telegram_id=? AND status='pending' ORDER BY id DESC LIMIT 1",
                (uid,)
            )).fetchone()
            if pending:
                await conn.rollback()
                raise HTTPException(409,"Сначала сохраните или продайте предыдущий выпавший предмет")
            paid_case = await (await conn.execute(
                "SELECT id,case_name FROM case_openings WHERE telegram_id=? AND status='paid' ORDER BY id ASC LIMIT 1",
                (uid,)
            )).fetchone()
            if paid_case:
                await conn.rollback()
                raise HTTPException(409,f"Сначала откройте уже оплаченный кейс «{paid_case['case_name']}»")
            case_row = await (await conn.execute(
                "SELECT * FROM case_configs WHERE id='FREE' AND active=1"
            )).fetchone()
            if not case_row:
                await conn.rollback()
                raise HTTPException(409,"Бесплатная рулетка сейчас отключена")
            free_cfg = parse_case_row(case_row)
            used_row = await (await conn.execute(
                "SELECT COUNT(*) c FROM spin_history WHERE telegram_id=? AND source='free' AND created_at >= datetime('now','-24 hours')",
                (uid,)
            )).fetchone()
            used = int(used_row["c"] or 0)
            source = "free"
            if used >= MAX_FREE_SPINS_24H:
                if int(state["tickets"] or 0) <= 0:
                    await conn.rollback()
                    raise HTTPException(429,"Лимит бесплатных SPIN исчерпан. Следующее вращение будет доступно позже.")
                source = "ticket"
                await conn.execute("UPDATE spin_state SET tickets=tickets-1 WHERE telegram_id=?",(uid,))

            reward = pick_case_reward(free_cfg)
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
    if reward["tier"] in ("RED","GOLD","LEGENDARY","MYTHIC"):
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


@app.post("/api/spin/case/open")
async def spin_case_open(body: CaseStartIn, x_telegram_init_data: str | None = Header(default=None)):
    u = await current_user(x_telegram_init_data)
    uid = int(u["id"])
    case_id = body.case_id.strip().upper()
    if case_id == "FREE":
        raise HTTPException(400,"Бесплатная рулетка открывается только через /api/spin/free")
    async with db_write_lock:
        conn = await db()
        try:
            await conn.execute("BEGIN IMMEDIATE")
            pending = await (await conn.execute(
                "SELECT id FROM inventory_items WHERE telegram_id=? AND status='pending' ORDER BY id DESC LIMIT 1",
                (uid,)
            )).fetchone()
            if pending:
                await conn.rollback()
                raise HTTPException(409,"Сначала сохраните или продайте предыдущий выпавший предмет")
            existing_paid = await (await conn.execute(
                "SELECT * FROM case_openings WHERE telegram_id=? AND status='paid' ORDER BY id ASC LIMIT 1",
                (uid,)
            )).fetchone()
            if existing_paid:
                result = await complete_case_opening(conn,existing_paid)
                await conn.commit()
                return {"mode":"ready",**result}
            cases = await load_case_catalog(conn,uid,include_inactive=True)
            cfg = next((x for x in cases if x["id"] == case_id),None)
            if not cfg or not cfg["active"]:
                await conn.rollback()
                raise HTTPException(404,"Кейс недоступен")
            snapshot = {
                "id":cfg["id"],"name":cfg["name"],"description":cfg["description"],"icon":cfg["icon"],
                "stars_price":int(cfg["stars_price"]),"tiers":cfg["tiers"],"contents":cfg["contents"]
            }
            snapshot_json = json.dumps(snapshot,ensure_ascii=False,separators=(",",":"))

            payment_method = ""
            stars_amount = int(cfg["stars_price"] or 0)
            is_free = bool(cfg["is_free"]) or stars_amount <= 0
            if is_free:
                payment_method = "Бесплатно"
                stars_amount = 0
            else:
                exact = await (await conn.execute(
                    "SELECT tickets FROM donation_ticket_balances WHERE telegram_id=? AND case_id=?",
                    (uid,case_id)
                )).fetchone()
                generic = await (await conn.execute(
                    "SELECT tickets FROM donation_ticket_balances WHERE telegram_id=? AND case_id='*'",
                    (uid,)
                )).fetchone()
                if exact and int(exact["tickets"] or 0) > 0:
                    await conn.execute(
                        "UPDATE donation_ticket_balances SET tickets=tickets-1 WHERE telegram_id=? AND case_id=?",
                        (uid,case_id)
                    )
                    payment_method = "Donation Ticket"
                    stars_amount = 0
                elif generic and int(generic["tickets"] or 0) > 0:
                    await conn.execute(
                        "UPDATE donation_ticket_balances SET tickets=tickets-1 WHERE telegram_id=? AND case_id='*'",
                        (uid,)
                    )
                    payment_method = "Donation Ticket"
                    stars_amount = 0

            if payment_method:
                cur = await conn.execute(
                    "INSERT INTO case_openings(telegram_id,case_id,case_name,stars_amount,payment_method,status,snapshot_json,paid_at) "
                    "VALUES(?,?,?,?,?,'paid',?,CURRENT_TIMESTAMP)",
                    (uid,case_id,cfg["name"],stars_amount,payment_method,snapshot_json)
                )
                opening = await (await conn.execute(
                    "SELECT * FROM case_openings WHERE id=?",(int(cur.lastrowid),)
                )).fetchone()
                result = await complete_case_opening(conn,opening)
                await conn.commit()
                announce_reward = result["reward"]
                mode = "ticket" if payment_method == "Donation Ticket" else "free"
            else:
                await conn.execute(
                    "UPDATE case_openings SET status='cancelled' "
                    "WHERE telegram_id=? AND status='awaiting_payment' AND telegram_charge_id=''",
                    (uid,)
                )
                cur = await conn.execute(
                    "INSERT INTO case_openings(telegram_id,case_id,case_name,stars_amount,payment_method,status,snapshot_json) "
                    "VALUES(?,?,?,?,?,'awaiting_payment',?)",
                    (uid,case_id,cfg["name"],stars_amount,"Telegram Stars",snapshot_json)
                )
                opening_id = int(cur.lastrowid)
                await conn.commit()
                announce_reward = None
                mode = "invoice"
        finally:
            await conn.close()

    if mode in ("free","ticket"):
        if announce_reward["tier"] in ("RED","GOLD","LEGENDARY","MYTHIC"):
            asyncio.create_task(announce_top_drop(uid,announce_reward))
        return {"mode":mode,**result}

    link = await tg("createInvoiceLink", {
        "title":cfg["name"],
        "description":f"Открытие кейса {cfg['name']}",
        "payload":f"case:{opening_id}:{uid}",
        "provider_token":"",
        "currency":"XTR",
        "prices":[{"label":cfg["name"],"amount":stars_amount}]
    })
    return {"mode":"invoice","opening_id":opening_id,"url":link,"stars_amount":stars_amount}


@app.post("/api/spin/case/{opening_id}/claim")
async def spin_case_claim(opening_id: int, x_telegram_init_data: str | None = Header(default=None)):
    u = await current_user(x_telegram_init_data)
    uid = int(u["id"])
    async with db_write_lock:
        conn = await db()
        try:
            await conn.execute("BEGIN IMMEDIATE")
            opening = await (await conn.execute(
                "SELECT * FROM case_openings WHERE id=? AND telegram_id=?",
                (opening_id,uid)
            )).fetchone()
            if not opening:
                await conn.rollback()
                raise HTTPException(404,"Открытие кейса не найдено")
            result = await complete_case_opening(conn,opening)
            await conn.commit()
        finally:
            await conn.close()
    if result["reward"]["tier"] in ("RED","GOLD","LEGENDARY","MYTHIC"):
        asyncio.create_task(announce_top_drop(uid,result["reward"]))
    return {"mode":"ready",**result}


@app.post("/api/spin/case/start")
async def spin_case_start(body: CaseStartIn, x_telegram_init_data: str | None = Header(default=None)):
    result = await spin_case_open(body,x_telegram_init_data)
    if result.get("mode") == "invoice":
        return {
            "mode":"stars",
            "opening_id":int(result["opening_id"]),
            "url":result["url"],
            "stars_price":int(result["stars_amount"])
        }
    return result


@app.get("/api/spin/case/opening/{opening_id}")
async def spin_case_opening_status(opening_id: int, x_telegram_init_data: str | None = Header(default=None)):
    u = await current_user(x_telegram_init_data)
    uid = int(u["id"])
    conn = await db()
    try:
        row = await (await conn.execute(
            "SELECT id,case_id,case_name,stars_amount,payment_method,status,created_at,paid_at,opened_at "
            "FROM case_openings WHERE id=? AND telegram_id=?",
            (opening_id,uid)
        )).fetchone()
    finally:
        await conn.close()
    if not row:
        raise HTTPException(404,"Открытие кейса не найдено")
    return dict(row)


@app.post("/api/spin/case/opening/{opening_id}/resolve")
async def spin_case_opening_resolve(opening_id: int, x_telegram_init_data: str | None = Header(default=None)):
    return await spin_case_claim(opening_id,x_telegram_init_data)


@app.post("/api/spin/case/opening/{opening_id}/cancel")
async def spin_case_opening_cancel(opening_id: int, x_telegram_init_data: str | None = Header(default=None)):
    u = await current_user(x_telegram_init_data)
    uid = int(u["id"])
    async with db_write_lock:
        conn = await db()
        try:
            cur = await conn.execute(
                "UPDATE case_openings SET status='cancelled' "
                "WHERE id=? AND telegram_id=? AND status='awaiting_payment' AND telegram_charge_id=''",
                (opening_id,uid)
            )
            await conn.commit()
        finally:
            await conn.close()
    return {"ok":True,"cancelled":bool(cur.rowcount)}


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
                "AND (lower(COALESCE(promo_type,'')) IN ('spin','donation') OR COALESCE(spin_tickets,0)>0 OR COALESCE(donation_tickets,0)>0) "
                "AND (max_uses=0 OR uses<max_uses) "
                "AND (expires_at='' OR datetime(expires_at)>datetime('now'))",
                (code,)
            )).fetchone()
            if not promo:
                await conn.rollback()
                raise HTTPException(400,"Промокод недействителен, закончился или истёк")
            redeemed = await (await conn.execute(
                "SELECT 1 FROM promo_redemptions WHERE promo_id=? AND telegram_id=?",
                (promo["id"],uid)
            )).fetchone()
            if redeemed:
                await conn.rollback()
                raise HTTPException(409,"Вы уже активировали этот промокод")

            ptype = str(promo["promo_type"] or "").lower()
            if ptype == "donation_spin":
                ptype = "donation"
            spin_added = int(promo["spin_tickets"] or 0)
            donation_added = int(promo["donation_tickets"] or 0)
            target_case = str(promo["case_id"] or "").strip().upper() or "*"
            if ptype == "spin" and spin_added <= 0:
                spin_added = 1
            if ptype == "donation" and donation_added <= 0:
                donation_added = 1

            if ptype == "donation":
                if target_case != "*":
                    case_row = await (await conn.execute(
                        "SELECT id FROM case_configs WHERE id=? AND active=1",(target_case,)
                    )).fetchone()
                    if not case_row:
                        await conn.rollback()
                        raise HTTPException(400,"Кейс для Donation Ticket больше недоступен")
                await conn.execute(
                    "INSERT INTO donation_ticket_balances(telegram_id,case_id,tickets) VALUES(?,?,?) "
                    "ON CONFLICT(telegram_id,case_id) DO UPDATE SET tickets=tickets+excluded.tickets",
                    (uid,target_case,donation_added)
                )
            elif ptype == "spin":
                await conn.execute(
                    "INSERT OR IGNORE INTO spin_state(telegram_id,tickets,last_free_spin,upgrade_points) VALUES(?,0,0,0)",
                    (uid,)
                )
                await conn.execute(
                    "UPDATE spin_state SET tickets=tickets+? WHERE telegram_id=?",
                    (spin_added,uid)
                )
            else:
                await conn.rollback()
                raise HTTPException(400,"Этот промокод предназначен для покупки товара")

            await conn.execute(
                "INSERT INTO promo_redemptions(promo_id,telegram_id) VALUES(?,?)",
                (promo["id"],uid)
            )
            await conn.execute("UPDATE promos SET uses=uses+1 WHERE id=?",(promo["id"],))
            await conn.commit()
            state = await (await conn.execute(
                "SELECT tickets FROM spin_state WHERE telegram_id=?",(uid,)
            )).fetchone()
            donation_total = await (await conn.execute(
                "SELECT COALESCE(SUM(tickets),0) total FROM donation_ticket_balances WHERE telegram_id=?",(uid,)
            )).fetchone()
        finally:
            await conn.close()

    return {
        "ok":True,"code":code,"promo_type":ptype,
        "tickets_added":spin_added if ptype=="spin" else 0,
        "bonus_tickets":int(state["tickets"] or 0) if state else 0,
        "donation_tickets_added":donation_added if ptype=="donation" else 0,
        "donation_case_id":target_case,
        "donation_tickets_total":int(donation_total["total"] or 0)
    }


@app.get("/api/farm")
async def farm_state_api(x_telegram_init_data: str | None = Header(default=None)):
    u = await current_user(x_telegram_init_data)
    uid = int(u["id"])
    conn = await db()
    try:
        state = await ensure_farm_state(conn,uid)
        await conn.commit()
        inv_rows = await (await conn.execute(
            "SELECT i.resource_id,i.qty,CASE WHEN l.resource_id IS NULL THEN 0 ELSE 1 END AS locked FROM farm_inventory i LEFT JOIN farm_item_locks l ON l.telegram_id=i.telegram_id AND l.resource_id=i.resource_id WHERE i.telegram_id=? AND i.qty>0 ORDER BY i.updated_at DESC",
            (uid,)
        )).fetchall()
        spin = await (await conn.execute("SELECT upgrade_points FROM spin_state WHERE telegram_id=?",(uid,))).fetchone()
        fund = await uc_fund(conn)
        withdrawals = await (await conn.execute(
            "SELECT id,pubg_uid,uc_amount,status,created_at,processed_at FROM uc_withdrawals WHERE telegram_id=? ORDER BY id DESC LIMIT 10",
            (uid,)
        )).fetchall()
    finally:
        await conn.close()

    level = int(state["level"] or 1)
    now = int(time.time())
    drill_level = int(state["drill_level"] or 0)
    warehouse_level = int(state["warehouse_level"] or 0)
    trader_level = int(state["trader_level"] or 0)
    interval = farm_mining_interval(level,drill_level)
    stored = sum(int(x["qty"] or 0) for x in inv_rows)
    cap = farm_total_capacity(level,warehouse_level) + int(state["automation_level"] or 0)*4 + int(state["research_level"] or 0)*3
    available_cycles = max(0,min(cap-stored,(now-int(state["last_mine_at"] or now))//interval))
    inventory = []
    for r in inv_rows:
        item = FARM_RESOURCE_BY_ID.get(r["resource_id"])
        if item:
            inventory.append({**item,"coins":farm_sale_price(item,trader_level),"qty":int(r["qty"] or 0),"total_coins":int(r["qty"] or 0)*farm_sale_price(item,trader_level),"locked":bool(r["locked"])})
    # UI must not show a claimable daily reward if the funded pool cannot pay it.
    activity_ready = bool(
        int(state["last_collect_at"] or 0) > int(state["last_activity_at"] or 0)
        and now-int(state["last_activity_at"] or 0)>=20*3600
        and int(fund["available_credits"] or 0)>=FARM_DAILY_UC_CREDITS
    )
    mine_progress,mine_ready,mine_rate,mine_next = farm_uc_progress(state,now)
    fund_available = int(fund["available_credits"] or 0) if fund else 0
    return {
        "level":level,"max_level":FARM_MAX_LEVEL,"stage":farm_stage(level),
        "shr":int(spin["upgrade_points"] or 0) if spin else 0,
        "shrek_coins":int(state["shrek_coins"] or 0),
        "uc_credits":int(state["uc_credits"] or 0),
        "uc_reserved":int(state["uc_reserved"] or 0),
        "uc_available":max(0,int(state["uc_credits"] or 0)-int(state["uc_reserved"] or 0)),
        "withdraw_min_uc":FARM_WITHDRAW_MIN_UC,
        "daily_uc_credits":FARM_DAILY_UC_CREDITS,
        "uc_mining":{"daily_rate":mine_rate,"period_seconds":UC_MINE_SECONDS_PER_CREDIT,"ready":mine_ready,
            "next_seconds":mine_next,"capacity":mine_rate,
            "reserve_available":fund_available,"claimable":min(mine_ready,fund_available)},
        "interval_seconds":interval,"capacity":cap,"stored":stored,
        "available_cycles":int(available_cycles),
        "next_cycle_seconds":(0 if available_cycles>0 else max(0,interval-max(0,now-int(state["last_mine_at"] or now))%interval)) if stored<cap else 0,
        "upgrade_cost":farm_upgrade_cost(level),
        "coin_upgrades":farm_coin_modules(state),
        "tier_weights":farm_tier_weights(level),
        "item_chances":farm_item_chances(level),
        "inventory":inventory,
        "resources":[{**item,"coins":farm_sale_price(item,trader_level)} for item in FARM_RESOURCES],
        "uc_targets":[
            {"uc":amount,
             "required_credits":amount,
             "need_more":max(0,amount-max(0,int(state["uc_credits"] or 0)-int(state["uc_reserved"] or 0))),
             "days_at_daily_rate":(max(0,amount-max(0,int(state["uc_credits"] or 0)-int(state["uc_reserved"] or 0)))+FARM_DAILY_UC_CREDITS-1)//FARM_DAILY_UC_CREDITS}
            for amount in (120,325,660,1800)
        ],
        "activity_streak":int(state["activity_streak"] or 0),
        "activity_total":int(state["activity_total"] or 0),
        "activity_ready":activity_ready,
        "withdrawals":[dict(x) for x in withdrawals]
    }



@app.post("/api/farm/uc/claim")
async def claim_mined_uc(x_telegram_init_data: str | None = Header(default=None)):
    u = await current_user(x_telegram_init_data)
    uid = int(u["id"])
    now = int(time.time())
    async with db_write_lock:
        conn = await db()
        try:
            await conn.execute("BEGIN IMMEDIATE")
            state = await ensure_farm_state(conn,uid)
            progress,ready,rate,_ = farm_uc_progress(state,now)
            if ready <= 0:
                await conn.rollback()
                raise HTTPException(409,"Добыча UC ещё не готова")
            reserve = await uc_fund(conn)
            available = int(reserve["available_credits"] or 0) if reserve else 0
            if available <= 0:
                await conn.rollback()
                raise HTTPException(409,"Фонд UC Credits временно исчерпан")
            award = min(ready,rate,available)
            await conn.execute(
                "UPDATE farm_state SET uc_credits=uc_credits+?,uc_mine_last_at=?,"
                "uc_mine_progress=?,updated_at=CURRENT_TIMESTAMP WHERE telegram_id=?",
                (award,now,progress-award*UC_MINE_SECONDS_PER_CREDIT,uid)
            )
            await conn.execute(
                "UPDATE uc_mining_fund SET available_credits=available_credits-?,"
                "issued_credits=issued_credits+?,updated_at=CURRENT_TIMESTAMP WHERE id=1",
                (award,award)
            )
            await conn.execute(
                "INSERT INTO farm_log(telegram_id,action,details) VALUES(?,?,?)",
                (uid,"uc_mined",json.dumps({"credits":award,"level":int(state["level"] or 1)}))
            )
            await conn.commit()
            after = await (await conn.execute(
                "SELECT uc_credits,uc_reserved FROM farm_state WHERE telegram_id=?",(uid,)
            )).fetchone()
        finally:
            await conn.close()
    return {"ok":True,"uc_credits_added":award,
            "uc_available":max(0,int(after["uc_credits"])-int(after["uc_reserved"]))}


@app.post("/api/farm/collect")
async def farm_collect(x_telegram_init_data: str | None = Header(default=None)):
    u = await current_user(x_telegram_init_data)
    uid = int(u["id"])
    async with db_write_lock:
        conn = await db()
        try:
            await conn.execute("BEGIN IMMEDIATE")
            state = await ensure_farm_state(conn,uid)
            level = int(state["level"] or 1)
            now = int(time.time())
            interval = farm_mining_interval(level,int(state["drill_level"] or 0))
            stored_row = await (await conn.execute(
                "SELECT COALESCE(SUM(qty),0) q FROM farm_inventory WHERE telegram_id=?",(uid,)
            )).fetchone()
            stored = int(stored_row["q"] or 0)
            capacity = farm_total_capacity(level,int(state["warehouse_level"] or 0)) + int(state["automation_level"] or 0)*4 + int(state["research_level"] or 0)*3
            room = max(0,capacity-stored)
            if room <= 0:
                await conn.execute("UPDATE farm_state SET last_mine_at=?,updated_at=CURRENT_TIMESTAMP WHERE telegram_id=?",(now,uid))
                await conn.commit()
                return {"ok":True,"mined":[],"count":0,"full":True}
            elapsed = max(0,now-int(state["last_mine_at"] or now))
            cycles = min(room,elapsed//interval,250)
            if cycles <= 0:
                await conn.rollback()
                raise HTTPException(409,"Добыча ещё не готова")
            mined = {}
            for _ in range(int(cycles)):
                item = pick_farm_resource(min(FARM_MAX_LEVEL,level+int(state["quality_level"] or 0)//4))
                mined[item["id"]] = mined.get(item["id"],0)+1
            for resource_id,qty in mined.items():
                await conn.execute(
                    "INSERT INTO farm_inventory(telegram_id,resource_id,qty) VALUES(?,?,?) "
                    "ON CONFLICT(telegram_id,resource_id) DO UPDATE SET qty=qty+excluded.qty,updated_at=CURRENT_TIMESTAMP",
                    (uid,resource_id,qty)
                )
            new_last = int(state["last_mine_at"] or now) + int(cycles)*interval
            if int(cycles) >= room:
                new_last = now
            await conn.execute(
                "UPDATE farm_state SET last_mine_at=?,last_collect_at=?,updated_at=CURRENT_TIMESTAMP WHERE telegram_id=?",
                (new_last,now,uid)
            )
            await conn.execute(
                "INSERT INTO farm_log(telegram_id,action,details) VALUES(?,?,?)",
                (uid,"collect",json.dumps(mined,ensure_ascii=False))
            )
            await conn.commit()
        finally:
            await conn.close()
    return {
        "ok":True,"count":int(cycles),"full":False,
        "mined":[{**FARM_RESOURCE_BY_ID[k],"qty":v} for k,v in mined.items() if k in FARM_RESOURCE_BY_ID]
    }


class FarmLockIn(BaseModel):
    resource_id: str = Field(min_length=1,max_length=64)
    locked: bool

@app.post("/api/farm/lock")
async def farm_lock_resource(body:FarmLockIn,x_telegram_init_data:str|None=Header(default=None)):
    u=await current_user(x_telegram_init_data)
    uid=int(u["id"])
    if body.resource_id not in FARM_RESOURCE_BY_ID:
        raise HTTPException(404,"Ресурс не найден")
    async with db_write_lock:
        conn=await db()
        try:
            if body.locked:
                row=await (await conn.execute("SELECT qty FROM farm_inventory WHERE telegram_id=? AND resource_id=?",(uid,body.resource_id))).fetchone()
                if not row or int(row["qty"] or 0)<=0:
                    raise HTTPException(409,"Предмет отсутствует на складе")
                await conn.execute("INSERT OR IGNORE INTO farm_item_locks(telegram_id,resource_id) VALUES(?,?)",(uid,body.resource_id))
            else:
                await conn.execute("DELETE FROM farm_item_locks WHERE telegram_id=? AND resource_id=?",(uid,body.resource_id))
            await conn.commit()
        finally:
            await conn.close()
    return {"ok":True,"resource_id":body.resource_id,"locked":body.locked}

@app.post("/api/farm/sell")
async def farm_sell(body: FarmSellIn, x_telegram_init_data: str | None = Header(default=None)):
    u = await current_user(x_telegram_init_data)
    uid = int(u["id"])
    resource_id = body.resource_id.strip()
    item = FARM_RESOURCE_BY_ID.get(resource_id)
    if not item:
        raise HTTPException(404,"Ресурс не найден")
    async with db_write_lock:
        conn = await db()
        try:
            await conn.execute("BEGIN IMMEDIATE")
            state = await ensure_farm_state(conn,uid)
            row = await (await conn.execute(
                "SELECT qty FROM farm_inventory WHERE telegram_id=? AND resource_id=?",(uid,resource_id)
            )).fetchone()
            have = int(row["qty"] or 0) if row else 0
            locked=await (await conn.execute("SELECT 1 FROM farm_item_locks WHERE telegram_id=? AND resource_id=?",(uid,resource_id))).fetchone()
            if locked:
                await conn.rollback()
                raise HTTPException(409,"Предмет заблокирован. Сначала разблокируйте его.")
            qty = min(have,int(body.qty))
            if qty <= 0:
                await conn.rollback()
                raise HTTPException(409,"Этого ресурса нет на складе")
            value = qty * farm_sale_price(item,int(state["trader_level"] or 0))
            await conn.execute(
                "UPDATE farm_inventory SET qty=qty-?,updated_at=CURRENT_TIMESTAMP WHERE telegram_id=? AND resource_id=?",
                (qty,uid,resource_id)
            )
            await conn.execute(
                "UPDATE farm_state SET shrek_coins=shrek_coins+?,updated_at=CURRENT_TIMESTAMP WHERE telegram_id=?",
                (value,uid)
            )
            await conn.execute(
                "INSERT INTO farm_log(telegram_id,action,details) VALUES(?,?,?)",
                (uid,"sell",json.dumps({"resource_id":resource_id,"qty":qty,"coins":value},ensure_ascii=False))
            )
            await conn.commit()
            state = await (await conn.execute("SELECT shrek_coins FROM farm_state WHERE telegram_id=?",(uid,))).fetchone()
        finally:
            await conn.close()
    return {"ok":True,"sold_qty":qty,"coins_added":value,"shrek_coins":int(state["shrek_coins"] or 0)}


@app.post("/api/farm/sell-all")
async def farm_sell_all(x_telegram_init_data: str | None = Header(default=None)):
    u = await current_user(x_telegram_init_data)
    uid = int(u["id"])
    async with db_write_lock:
        conn = await db()
        try:
            await conn.execute("BEGIN IMMEDIATE")
            state = await ensure_farm_state(conn,uid)
            rows = await (await conn.execute(
                "SELECT i.resource_id,i.qty FROM farm_inventory i LEFT JOIN farm_item_locks l ON l.telegram_id=i.telegram_id AND l.resource_id=i.resource_id WHERE i.telegram_id=? AND i.qty>0 AND l.resource_id IS NULL",(uid,)
            )).fetchall()
            total = 0
            sold = 0
            for r in rows:
                item = FARM_RESOURCE_BY_ID.get(r["resource_id"])
                if not item: continue
                qty = int(r["qty"] or 0)
                total += qty * farm_sale_price(item,int(state["trader_level"] or 0)); sold += qty
            if sold <= 0:
                await conn.rollback()
                raise HTTPException(409,"Нет незаблокированных предметов для продажи")
            await conn.execute("UPDATE farm_inventory SET qty=0,updated_at=CURRENT_TIMESTAMP WHERE telegram_id=? AND resource_id NOT IN (SELECT resource_id FROM farm_item_locks WHERE telegram_id=?)",(uid,uid))
            await conn.execute("UPDATE farm_state SET shrek_coins=shrek_coins+?,updated_at=CURRENT_TIMESTAMP WHERE telegram_id=?",(total,uid))
            await conn.execute("INSERT INTO farm_log(telegram_id,action,details) VALUES(?,?,?)",(uid,"sell_all",json.dumps({"qty":sold,"coins":total})))
            await conn.commit()
        finally:
            await conn.close()
    return {"ok":True,"sold_qty":sold,"coins_added":total}


@app.post("/api/farm/upgrade")
async def farm_upgrade(x_telegram_init_data: str | None = Header(default=None)):
    u = await current_user(x_telegram_init_data)
    uid = int(u["id"])
    async with db_write_lock:
        conn = await db()
        try:
            await conn.execute("BEGIN IMMEDIATE")
            state = await ensure_farm_state(conn,uid)
            level = int(state["level"] or 1)
            if level >= FARM_MAX_LEVEL:
                await conn.rollback()
                raise HTTPException(409,"Ферма уже максимального уровня")
            cost = farm_upgrade_cost(level)
            await conn.execute("INSERT OR IGNORE INTO spin_state(telegram_id,tickets,last_free_spin,upgrade_points) VALUES(?,0,0,0)",(uid,))
            spin = await (await conn.execute("SELECT upgrade_points FROM spin_state WHERE telegram_id=?",(uid,))).fetchone()
            if int(spin["upgrade_points"] or 0) < cost:
                await conn.rollback()
                raise HTTPException(409,f"Нужно {cost} SHR")
            # Snapshot the old-level UC accrual before enabling the higher rate.
            # Otherwise an upgrade would retroactively award elapsed hours at the
            # new, faster level; that could consume more UC than budgeted.
            uc_now = int(time.time())
            prior_progress,_,_,_ = farm_uc_progress(state,uc_now)
            await conn.execute("UPDATE spin_state SET upgrade_points=upgrade_points-? WHERE telegram_id=?",(cost,uid))
            await conn.execute(
                "UPDATE farm_state SET level=level+1,uc_mine_progress=?,"
                "uc_mine_last_at=?,updated_at=CURRENT_TIMESTAMP WHERE telegram_id=?",
                (prior_progress,uc_now,uid)
            )
            await conn.execute("INSERT INTO farm_log(telegram_id,action,details) VALUES(?,?,?)",(uid,"upgrade",json.dumps({"from":level,"to":level+1,"shr":cost})))
            await conn.commit()
        finally:
            await conn.close()
    return {"ok":True,"level":level+1,"cost":cost}


@app.get("/api/farm/coin-upgrade/quote")
async def farm_coin_upgrade_quote(module:str,levels:int=1,max_upgrade:bool=False,x_telegram_init_data:str|None=Header(default=None)):
    u=await current_user(x_telegram_init_data)
    spec=FARM_COIN_MODULES.get(module)
    if not spec: raise HTTPException(400,"Неизвестный модуль фермы")
    if levels<1 or levels>100: raise HTTPException(422,"Укажите от 1 до 100 уровней")
    conn=await db()
    try:
        state=await ensure_farm_state(conn,int(u["id"]))
        current=int(state[spec["column"]] or 0)
        balance=int(state["shrek_coins"] or 0)
        requested=(FARM_MODULE_LIMITS[module]-current) if max_upgrade else min(levels,FARM_MODULE_LIMITS[module]-current)
        total=0;affordable=0;spend=0
        for i in range(requested):
            price=farm_coin_upgrade_cost(module,current+i)
            total+=price
            if affordable==i and spend+price<=balance:
                spend+=price;affordable+=1
        return {"requested":requested,"total_cost":total,"affordable_levels":affordable,"actual_cost":spend,"balance":balance,"balance_after":balance-spend}
    finally:
        await conn.close()


@app.post("/api/farm/coin-upgrade")
async def farm_coin_upgrade(body: FarmCoinUpgradeIn, x_telegram_init_data: str | None = Header(default=None)):
    u = await current_user(x_telegram_init_data)
    uid = int(u["id"])
    module = body.module.strip()
    spec = FARM_COIN_MODULES.get(module)
    if not spec:
        raise HTTPException(400,"Неизвестный модуль фермы")
    async with db_write_lock:
        conn = await db()
        try:
            await conn.execute("BEGIN IMMEDIATE")
            state = await ensure_farm_state(conn,uid)
            old_level = int(state[spec["column"]] or 0)
            if old_level >= FARM_MODULE_LIMITS[module]:
                await conn.rollback()
                raise HTTPException(409,"Модуль уже максимально улучшен")
            available = int(state["shrek_coins"] or 0)
            remaining = FARM_MODULE_LIMITS[module] - old_level
            requested = remaining if body.max_upgrade else min(body.levels, remaining)
            count = 0
            cost = 0
            for offset in range(requested):
                next_cost = farm_coin_upgrade_cost(module,old_level+offset)
                if cost + next_cost > available:
                    break
                cost += next_cost
                count += 1
            if count == 0:
                await conn.rollback()
                raise HTTPException(409,f"Нужно {cost} ShrekCOINS")
            if module == "drill":
                now = int(time.time())
                base_level = int(state["level"] or 1)
                previous_interval = farm_mining_interval(base_level,old_level)
                improved_interval = farm_mining_interval(base_level,old_level+count)
                elapsed = max(0,now-int(state["last_mine_at"] or now))
                complete_cycles, part_seconds = divmod(elapsed,previous_interval)
                adjusted_elapsed = complete_cycles*improved_interval + part_seconds*improved_interval//previous_interval
                await conn.execute("UPDATE farm_state SET last_mine_at=? WHERE telegram_id=?",(now-adjusted_elapsed,uid))
            column = spec["column"]  # Только фиксированные серверные имена, не данные запроса.
            await conn.execute(
                f"UPDATE farm_state SET shrek_coins=shrek_coins-?,{column}={column}+?,updated_at=CURRENT_TIMESTAMP WHERE telegram_id=?",
                (cost,count,uid)
            )
            await conn.execute("INSERT INTO farm_log(telegram_id,action,details) VALUES(?,?,?)",
                               (uid,"coin_upgrade",json.dumps({"module":module,"from":old_level,"to":old_level+count,"coins":cost})))
            await conn.commit()
        finally:
            await conn.close()
    return {"ok":True,"module":module,"level":old_level+count,"levels_added":count,"spent":cost}


@app.post("/api/farm/activity")
async def farm_activity_reward(x_telegram_init_data: str | None = Header(default=None)):
    u = await current_user(x_telegram_init_data)
    uid = int(u["id"])
    now = int(time.time())
    async with db_write_lock:
        conn = await db()
        try:
            await conn.execute("BEGIN IMMEDIATE")
            state = await ensure_farm_state(conn,uid)
            last_activity = int(state["last_activity_at"] or 0)
            last_collect = int(state["last_collect_at"] or 0)
            if last_collect <= last_activity:
                await conn.rollback()
                raise HTTPException(409,"Сначала соберите добычу на ферме")
            if last_activity and now-last_activity < 20*3600:
                await conn.rollback()
                raise HTTPException(429,"Награда за активность уже получена")
            reserve = await uc_fund(conn)
            if not reserve or int(reserve["available_credits"] or 0) < FARM_DAILY_UC_CREDITS:
                await conn.rollback()
                raise HTTPException(409,"Фонд UC Credits временно исчерпан")
            streak = int(state["activity_streak"] or 0)
            if last_activity and now-last_activity <= 48*3600:
                streak += 1
            else:
                streak = 1
            total = int(state["activity_total"] or 0)+1
            case_ticket = ""
            if streak % 30 == 0:
                case_ticket = "CASE79"
            elif streak % 7 == 0:
                case_ticket = "CASE29"
            if case_ticket:
                await conn.execute(
                    "INSERT INTO donation_ticket_balances(telegram_id,case_id,tickets) VALUES(?,?,1) "
                    "ON CONFLICT(telegram_id,case_id) DO UPDATE SET tickets=tickets+1",
                    (uid,case_ticket)
                )
            await conn.execute(
                "UPDATE uc_mining_fund SET available_credits=available_credits-?,"
                "issued_credits=issued_credits+?,updated_at=CURRENT_TIMESTAMP WHERE id=1",
                (FARM_DAILY_UC_CREDITS,FARM_DAILY_UC_CREDITS)
            )
            await conn.execute(
                "UPDATE farm_state SET uc_credits=uc_credits+?,last_activity_at=?,activity_streak=?,activity_total=?,updated_at=CURRENT_TIMESTAMP WHERE telegram_id=?",
                (FARM_DAILY_UC_CREDITS,now,streak,total,uid)
            )
            await conn.execute(
                "INSERT INTO farm_log(telegram_id,action,details) VALUES(?,?,?)",
                (uid,"activity",json.dumps({"uc_credits":FARM_DAILY_UC_CREDITS,"streak":streak,"case_ticket":case_ticket}))
            )
            await conn.commit()
        finally:
            await conn.close()
    return {"ok":True,"uc_credits_added":FARM_DAILY_UC_CREDITS,"streak":streak,"case_ticket":case_ticket}


@app.post("/api/farm/withdraw")
async def farm_withdraw(body: FarmWithdrawIn, x_telegram_init_data: str | None = Header(default=None)):
    u = await current_user(x_telegram_init_data)
    uid = int(u["id"])
    if body.uc_amount < FARM_WITHDRAW_MIN_UC:
        raise HTTPException(400,f"Минимальный вывод — {FARM_WITHDRAW_MIN_UC} UC")
    async with db_write_lock:
        conn = await db()
        try:
            await conn.execute("BEGIN IMMEDIATE")
            state = await ensure_farm_state(conn,uid)
            available = int(state["uc_credits"] or 0)-int(state["uc_reserved"] or 0)
            if available < body.uc_amount:
                await conn.rollback()
                raise HTTPException(409,"Недостаточно UC Credits")
            cur = await conn.execute(
                "INSERT INTO uc_withdrawals(telegram_id,pubg_uid,uc_amount,status) VALUES(?,?,?,'Ожидает')",
                (uid,body.pubg_uid.strip(),int(body.uc_amount))
            )
            wid = int(cur.lastrowid)
            await conn.execute("UPDATE farm_state SET uc_reserved=uc_reserved+?,updated_at=CURRENT_TIMESTAMP WHERE telegram_id=?",(int(body.uc_amount),uid))
            await conn.commit()
        finally:
            await conn.close()
    try:
        await tg("sendMessage",{"chat_id":OWNER_ID,"text":f"🪙 Новый запрос UC #{wid}\nЖетон: {u.get('token','—')}\nPUBG UID: {body.pubg_uid}\nСумма: {body.uc_amount} UC\nОткройте Owner Panel → UC выводы."})
    except Exception:
        pass
    return {"ok":True,"id":wid,"status":"Ожидает","uc_amount":int(body.uc_amount)}


@app.get("/api/admin/farm-withdrawals")
async def admin_farm_withdrawals(x_telegram_init_data: str | None = Header(default=None)):
    await owner(x_telegram_init_data)
    conn = await db()
    try:
        rows = await (await conn.execute(
            "SELECT w.id,w.telegram_id,u.token,u.username,u.first_name,w.pubg_uid,w.uc_amount,w.status,w.created_at,w.processed_at "
            "FROM uc_withdrawals w LEFT JOIN users u ON u.telegram_id=w.telegram_id ORDER BY CASE WHEN w.status='Ожидает' THEN 0 ELSE 1 END,w.id DESC LIMIT 300"
        )).fetchall()
    finally:
        await conn.close()
    return [dict(x) for x in rows]


@app.patch("/api/admin/farm-withdrawals/{withdrawal_id}")
async def admin_farm_withdrawal_update(withdrawal_id: int, body: AdminFarmWithdrawalIn, x_telegram_init_data: str | None = Header(default=None)):
    await owner(x_telegram_init_data)
    status = body.status.strip()
    if status not in ("Выполнен","Отклонён"):
        raise HTTPException(400,"Статус: Выполнен или Отклонён")
    async with db_write_lock:
        conn = await db()
        try:
            await conn.execute("BEGIN IMMEDIATE")
            row = await (await conn.execute("SELECT * FROM uc_withdrawals WHERE id=?",(withdrawal_id,))).fetchone()
            if not row:
                await conn.rollback()
                raise HTTPException(404,"Заявка не найдена")
            if row["status"] != "Ожидает":
                await conn.rollback()
                raise HTTPException(409,"Заявка уже обработана")
            uid = int(row["telegram_id"]); amount = int(row["uc_amount"])
            state = await ensure_farm_state(conn,uid)
            if int(state["uc_reserved"] or 0) < amount:
                await conn.rollback()
                raise HTTPException(409,"Резерв UC повреждён")
            if status == "Выполнен":
                if int(state["uc_credits"] or 0) < amount:
                    await conn.rollback()
                    raise HTTPException(409,"Недостаточно UC Credits")
                await conn.execute("UPDATE farm_state SET uc_credits=uc_credits-?,uc_reserved=uc_reserved-?,updated_at=CURRENT_TIMESTAMP WHERE telegram_id=?",(amount,amount,uid))
            else:
                await conn.execute("UPDATE farm_state SET uc_reserved=uc_reserved-?,updated_at=CURRENT_TIMESTAMP WHERE telegram_id=?",(amount,uid))
            await conn.execute("UPDATE uc_withdrawals SET status=?,processed_at=CURRENT_TIMESTAMP WHERE id=?",(status,withdrawal_id))
            await conn.commit()
        finally:
            await conn.close()
    try:
        await tg("sendMessage",{"chat_id":uid,"text":f"🎮 Запрос UC #{withdrawal_id}: {status}. Сумма: {amount} UC."})
    except Exception:
        pass
    return {"ok":True,"status":status}


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
    # Один общий поток для всех игроков. Включает ценные ресурсы фермы и редкие
    # выигрыши из кейсов/рулеток. Публикуем лишь открытые ники, не Telegram ID.
    conn = await db()
    try:
        rows = await (await conn.execute(
            "SELECT h.id,h.reward_name,h.reward_tier,h.created_at,"
            "CASE WHEN COALESCE(u.username,'')<>'' THEN '@'||u.username "
            "WHEN COALESCE(u.first_name,'')<>'' THEN u.first_name ELSE 'Игрок' END player "
            "FROM spin_history h LEFT JOIN users u ON u.telegram_id=h.telegram_id "
            "WHERE h.reward_tier IN ('PURPLE','PINK','RED','GOLD','LEGENDARY','MYTHIC') ORDER BY h.id DESC LIMIT 45"
        )).fetchall()
        farm_rows = await (await conn.execute(
            "SELECT f.id,f.details,f.created_at,"
            "CASE WHEN COALESCE(u.username,'')<>'' THEN '@'||u.username "
            "WHEN COALESCE(u.first_name,'')<>'' THEN u.first_name ELSE 'Игрок' END player "
            "FROM farm_log f LEFT JOIN users u ON u.telegram_id=f.telegram_id "
            "WHERE f.action='collect' ORDER BY f.id DESC LIMIT 180"
        )).fetchall()
    finally:
        await conn.close()
    combined = [
        {"id":f"spin-{row['id']}","origin":"spin","reward_name":row["reward_name"],
         "reward_tier":row["reward_tier"],"created_at":row["created_at"],"player":row["player"]}
        for row in rows
    ]
    for row in farm_rows:
        try:
            mined = json.loads(row["details"] or "{}")
        except (json.JSONDecodeError,TypeError):
            continue
        if not isinstance(mined,dict):
            continue
        for resource_id, quantity in mined.items():
            item = FARM_RESOURCE_BY_ID.get(resource_id)
            if not item or item["tier"] not in ("PURPLE","PINK","RED","GOLD","RAINBOW"):
                continue
            try:
                count = max(0,int(quantity))
            except (ValueError,TypeError):
                continue
            if count < 1:
                continue
            combined.append({
                "id":f"farm-{row['id']}-{resource_id}",
                "origin":"farm","reward_name":item["name"] + (f" ×{count}" if count>1 else ""),
                "reward_tier":item["tier"],"created_at":row["created_at"],
                "player":row["player"]
            })
    combined.sort(key=lambda x:(str(x["created_at"] or ""),str(x["id"])),reverse=True)
    return combined[:35]


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


async def is_shop_admin(uid: int) -> bool:
    if uid == OWNER_ID:
        return True
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("CREATE TABLE IF NOT EXISTS shop_admins (telegram_id INTEGER PRIMARY KEY, role TEXT NOT NULL DEFAULT 'admin', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
        row = await (await conn.execute("SELECT telegram_id FROM shop_admins WHERE telegram_id=?", (uid,))).fetchone()
        return row is not None

SHOP_ROLE_LEVELS = {"moderator":1,"admin":2,"head_admin":3,"deputy_owner":4,"co_owner":5}
SHOP_ROLE_NAMES = {"moderator":"Модератор","admin":"Администратор","head_admin":"Старший администратор","deputy_owner":"Заместитель владельца","co_owner":"Совладелец"}

async def shop_actor_level(uid: int) -> int:
    if uid == OWNER_ID:
        return 6
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("CREATE TABLE IF NOT EXISTS shop_admins (telegram_id INTEGER PRIMARY KEY, role TEXT NOT NULL DEFAULT 'admin', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
        row = await (await conn.execute("SELECT role FROM shop_admins WHERE telegram_id=?", (uid,))).fetchone()
    return SHOP_ROLE_LEVELS.get(row[0],0) if row else 0

async def shop_require_staff_power(actor_id: int, target_id: int, new_role: str | None = None):
    actor_level = await shop_actor_level(actor_id)
    if actor_level < 3:
        raise HTTPException(403,"Управление администраторами доступно старшему составу")
    if target_id == OWNER_ID:
        raise HTTPException(403,"Владельца нельзя изменить или удалить")
    target_level = await shop_actor_level(target_id)
    if target_level >= actor_level:
        raise HTTPException(403,"Нельзя управлять равным или старшим званием")
    if new_role is not None and SHOP_ROLE_LEVELS.get(new_role,0) >= actor_level:
        raise HTTPException(403,"Нельзя назначить равное или более высокое звание")

async def owner(init_data: str | None):
    u = await current_user(init_data)
    if not await is_shop_admin(int(u["id"])):
        raise HTTPException(403,"Нет доступа")
    return u

async def ensure_shop_staff_schema(conn):
    await conn.execute("CREATE TABLE IF NOT EXISTS shop_admins (telegram_id INTEGER PRIMARY KEY, role TEXT NOT NULL DEFAULT 'admin', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
    await conn.execute("""CREATE TABLE IF NOT EXISTS shop_admin_warnings (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      telegram_id INTEGER NOT NULL,
      issued_by INTEGER NOT NULL,
      reason TEXT NOT NULL,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")

class ShopWarningIn(BaseModel):
    reason: str = Field(min_length=5, max_length=500)

class ShopAdminIn(BaseModel):
    telegram_id: int = Field(gt=0)
    role: str = "admin"

@app.get("/api/admin/staff")
async def shop_staff_list(x_telegram_init_data: str | None = Header(default=None)):
    await owner(x_telegram_init_data)
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        await ensure_shop_staff_schema(conn)
        rows = await (await conn.execute("""
          SELECT a.telegram_id,a.role,a.created_at,u.first_name,u.username,
          (SELECT COUNT(*) FROM shop_admin_warnings w WHERE w.telegram_id=a.telegram_id) AS warnings
          FROM shop_admins a LEFT JOIN users u ON u.telegram_id=a.telegram_id
          ORDER BY a.created_at DESC""")).fetchall()
        own = await (await conn.execute("SELECT first_name,username FROM users WHERE telegram_id=?", (OWNER_ID,))).fetchone()
    result = [{"telegram_id":OWNER_ID,"role":"owner","first_name":own["first_name"] if own else None,"username":own["username"] if own else None,"created_at":None,"warnings":0}]
    result.extend(dict(r) for r in rows)
    return result

@app.get("/api/admin/staff/{staff_id}/warnings")
async def shop_staff_warnings(staff_id: int, x_telegram_init_data: str | None = Header(default=None)):
    await owner(x_telegram_init_data)
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        await ensure_shop_staff_schema(conn)
        rows = await (await conn.execute("SELECT id,reason,issued_by,created_at FROM shop_admin_warnings WHERE telegram_id=? ORDER BY id DESC", (staff_id,))).fetchall()
    return [dict(r) for r in rows]

@app.post("/api/admin/staff/{staff_id}/warnings")
async def shop_staff_warn(staff_id: int, body: ShopWarningIn, x_telegram_init_data: str | None = Header(default=None)):
    actor = await owner(x_telegram_init_data)
    await shop_require_staff_power(int(actor["id"]), staff_id)
    if staff_id == OWNER_ID:
        raise HTTPException(400,"Владельцу нельзя выдать выговор")
    async with aiosqlite.connect(DB_PATH) as conn:
        await ensure_shop_staff_schema(conn)
        exists = await (await conn.execute("SELECT 1 FROM shop_admins WHERE telegram_id=?", (staff_id,))).fetchone()
        if not exists:
            raise HTTPException(404,"Администратор не найден")
        await conn.execute("INSERT INTO shop_admin_warnings(telegram_id,issued_by,reason) VALUES(?,?,?)", (staff_id,int(actor["id"]),body.reason.strip()))
        await conn.commit()
    return {"ok":True}

@app.delete("/api/admin/staff/{staff_id}/warnings/{warning_id}")
async def shop_staff_unwarn(staff_id: int, warning_id: int, x_telegram_init_data: str | None = Header(default=None)):
    actor = await owner(x_telegram_init_data)
    await shop_require_staff_power(int(actor["id"]), staff_id)
    async with aiosqlite.connect(DB_PATH) as conn:
        await ensure_shop_staff_schema(conn)
        await conn.execute("DELETE FROM shop_admin_warnings WHERE id=? AND telegram_id=?", (warning_id,staff_id))
        await conn.commit()
    return {"ok":True}

@app.post("/api/admin/staff")
async def shop_staff_add(body: ShopAdminIn, x_telegram_init_data: str | None = Header(default=None)):
    actor = await owner(x_telegram_init_data)
    await shop_require_staff_power(int(actor["id"]), body.telegram_id, body.role)
    if body.role not in SHOP_ROLE_LEVELS:
        raise HTTPException(400,"Недопустимая роль")
    if body.telegram_id == OWNER_ID:
        raise HTTPException(400,"Владелец уже имеет доступ")
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("CREATE TABLE IF NOT EXISTS shop_admins (telegram_id INTEGER PRIMARY KEY, role TEXT NOT NULL DEFAULT 'admin', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
        await conn.execute("INSERT INTO shop_admins(telegram_id,role) VALUES(?,?) ON CONFLICT(telegram_id) DO UPDATE SET role=excluded.role", (body.telegram_id,body.role))
        await conn.commit()
    return {"ok":True}

@app.delete("/api/admin/staff/{staff_id}")
async def shop_staff_remove(staff_id: int, x_telegram_init_data: str | None = Header(default=None)):
    actor = await owner(x_telegram_init_data)
    await shop_require_staff_power(int(actor["id"]), staff_id)
    if staff_id == OWNER_ID:
        raise HTTPException(400,"Владельца нельзя удалить")
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("DELETE FROM shop_admin_warnings WHERE telegram_id=?", (staff_id,))
        await conn.execute("DELETE FROM shop_admins WHERE telegram_id=?", (staff_id,))
        await conn.commit()
    return {"ok":True}


@app.get("/api/admin/orders")
async def admin_orders(x_telegram_init_data: str | None = Header(default=None)):
    await owner(x_telegram_init_data)
    conn=await db()
    try:
        rows=await (await conn.execute(
            "SELECT o.*,u.token user_token,u.username buyer_username,u.first_name buyer_name, "
            "su.token seller_token,su.username seller_username,ss.display_name seller_name "
            "FROM orders o LEFT JOIN users u ON u.telegram_id=o.telegram_id "
            "LEFT JOIN users su ON su.telegram_id=o.seller_id "
            "LEFT JOIN shop_sellers ss ON ss.telegram_id=o.seller_id "
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
    allowed={"Ожидает оплаты","Ожидает проверки оплаты","Проверка оплаты","Оплачен","Принят","В работе","Ожидает клиента","Проверка выдачи","Выполнен","Отменён","Возврат"}
    if body.status not in allowed: raise HTTPException(400,"Некорректный статус")
    async with db_write_lock:
        conn=await db()
        try:
            await conn.execute("BEGIN IMMEDIATE")
            row=await (await conn.execute("SELECT * FROM orders WHERE id=?",(order_id,))).fetchone()
            if not row:
                await conn.rollback()
                raise HTTPException(404,"Заказ не найден")
            if int(row["seller_id"] or 0)>0:
                charged = bool(row["telegram_charge_id"])
                original_status = str(row["status"])
                if charged and body.status in ("Ожидает оплаты","Ожидает проверки оплаты","Истёк"):
                    await conn.rollback()
                    raise HTTPException(409,"Нельзя возвращать оплаченный заказ в неоплаченное состояние")
                if not charged and body.status not in ("Ожидает оплаты","Отменён"):
                    await conn.rollback()
                    raise HTTPException(409,"Статус оплаченного заказа доступен только после подтверждения Stars")
                if original_status in ("Отменён","Истёк") and body.status!="Отменён":
                    await conn.rollback()
                    raise HTTPException(409,"Закрытый заказ нельзя возобновить: оформите новый заказ")
                if charged and original_status=="Проверка оплаты" and body.status not in ("Проверка оплаты","Возврат"):
                    await conn.rollback()
                    raise HTTPException(409,"Платёж по истёкшей брони требует проверки и возврата Stars")
                if body.status=="Проверка выдачи" and original_status!="Проверка выдачи":
                    await conn.rollback()
                    raise HTTPException(409,"Проверку выдачи может инициировать только продавец")
                if body.status=="Выполнен" and (
                    not row["telegram_charge_id"] or row["status"]!="Проверка выдачи"
                    or not row["seller_delivery_note"]
                ):
                    await conn.rollback()
                    raise HTTPException(409,"Для завершения сначала требуется подтверждение выдачи продавцом")
                settled=await (await conn.execute(
                    "SELECT id FROM seller_settlement_log WHERE order_id=?",(order_id,)
                )).fetchone()
                if settled and body.status!="Выполнен":
                    await conn.rollback()
                    raise HTTPException(409,"По заказу уже зарегистрирован расчёт с продавцом")
                if row["status"]=="Ожидает оплаты" and body.status in ("Отменён","Возврат"):
                    await conn.execute("UPDATE products SET seller_stock=seller_stock+1 WHERE id=? AND seller_id>0",
                                       (int(row["product_id"]),))
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
            "SELECT t.id,u.token user_token,u.first_name,u.username,t.category,t.message,t.status,t.created_at "
            "FROM tickets t LEFT JOIN users u ON u.telegram_id=t.telegram_id "
            "ORDER BY t.id DESC LIMIT 200"
        )).fetchall()
    finally:
        await conn.close()
    return [dict(r) for r in rows]



class UCProfitFundIn(BaseModel):
    credits: int = Field(ge=1,le=100000)
    note: str = Field(min_length=4,max_length=220)
    profit_verified: bool = False

class AdminUCGrantIn(BaseModel):
    token: str = Field(min_length=5,max_length=40)
    credits: int = Field(ge=1,le=100000)
    reason: str = Field(min_length=5,max_length=250)

@app.post("/api/admin/uc-grant")
async def admin_uc_grant(body: AdminUCGrantIn, x_telegram_init_data: str | None = Header(default=None)):
    actor=await owner(x_telegram_init_data)
    if int(actor["id"]) != OWNER_ID:
        raise HTTPException(403,"Выдавать UC может только владелец")
    async with db_write_lock:
        conn=await db()
        try:
            await conn.execute("BEGIN IMMEDIATE")
            user=await telegram_id_by_token(conn,body.token)
            if not user: raise HTTPException(404,"Игрок с таким жетоном не найден")
            uid=int(user["telegram_id"])
            await ensure_farm_state(conn,uid)
            pool=await uc_fund(conn)
            if int(pool["available_credits"] or 0)<body.credits:
                raise HTTPException(409,"Недостаточно UC в подтверждённом фонде")
            await conn.execute("UPDATE uc_mining_fund SET available_credits=available_credits-?,issued_credits=issued_credits+?,updated_at=CURRENT_TIMESTAMP WHERE id=1",(body.credits,body.credits))
            await conn.execute("UPDATE farm_state SET uc_credits=uc_credits+?,updated_at=CURRENT_TIMESTAMP WHERE telegram_id=?",(body.credits,uid))
            await conn.execute("INSERT INTO farm_log(telegram_id,action,details) VALUES(?,?,?)",(uid,"admin_uc_grant",json.dumps({"credits":body.credits,"reason":body.reason.strip(),"operator_id":int(actor["id"])},ensure_ascii=False)))
            await conn.commit()
            return {"ok":True,"token":body.token.strip().upper(),"credits":body.credits}
        except Exception:
            await conn.rollback()
            raise
        finally:
            await conn.close()

@app.get("/api/admin/uc-fund")
async def admin_uc_fund(x_telegram_init_data: str | None = Header(default=None)):
    await owner(x_telegram_init_data)
    conn = await db()
    try:
        pool = await uc_fund(conn)
        orders = await (await conn.execute(
            "SELECT COALESCE(SUM(stars_amount),0) total FROM orders WHERE telegram_charge_id<>''"
        )).fetchone()
        cases = await (await conn.execute(
            "SELECT COALESCE(SUM(stars_amount),0) total FROM case_openings WHERE telegram_charge_id<>''"
        )).fetchone()
        logs = await (await conn.execute(
            "SELECT id,credited_amount,note,created_at FROM uc_mining_fund_log ORDER BY id DESC LIMIT 15"
        )).fetchall()
        uc_liability = await (await conn.execute(
            "SELECT COALESCE(SUM(uc_credits),0) outstanding,"
            "COALESCE(SUM(uc_reserved),0) reserved FROM farm_state"
        )).fetchone()
    finally:
        await conn.close()
    return {"available":int(pool["available_credits"] or 0),
            "funded":int(pool["funded_credits"] or 0),
            "issued":int(pool["issued_credits"] or 0),
            "gross_stars":int(orders["total"] or 0)+int(cases["total"] or 0),
            "existing_liability":int(uc_liability["outstanding"] or 0),
            "reserved_liability":int(uc_liability["reserved"] or 0),
            "history":[dict(r) for r in logs]}

@app.post("/api/admin/uc-fund")
async def fund_uc_from_profit(body: UCProfitFundIn, x_telegram_init_data: str | None = Header(default=None)):
    admin = await owner(x_telegram_init_data)
    if not body.profit_verified:
        raise HTTPException(400,"Подтвердите резерв из чистой прибыли после себестоимости призов и комиссий")
    async with db_write_lock:
        conn = await db()
        try:
            await conn.execute("BEGIN IMMEDIATE")
            await conn.execute(
                "UPDATE uc_mining_fund SET available_credits=available_credits+?,"
                "funded_credits=funded_credits+?,updated_at=CURRENT_TIMESTAMP WHERE id=1",
                (body.credits,body.credits)
            )
            await conn.execute(
                "INSERT INTO uc_mining_fund_log(operator_id,credited_amount,note) VALUES(?,?,?)",
                (int(admin["id"]),body.credits,body.note.strip())
            )
            await conn.commit()
            pool = await uc_fund(conn)
        finally:
            await conn.close()
    return {"ok":True,"added":body.credits,"available":int(pool["available_credits"])}


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
            "COALESCE((SELECT SUM(d.tickets) FROM donation_ticket_balances d WHERE d.telegram_id=u.telegram_id),0) donation_tickets,"
            "(SELECT COUNT(*) FROM orders o WHERE o.telegram_id=u.telegram_id) orders_count,"
            "(SELECT COUNT(*) FROM referrals r WHERE r.referrer_id=u.telegram_id) referrals_count "
            "FROM users u LEFT JOIN spin_state s ON s.telegram_id=u.telegram_id "
            "ORDER BY u.created_at DESC LIMIT 1000"
        )).fetchall()
    finally:
        await conn.close()
    return [dict(r) for r in rows]


@app.get("/api/admin/players/{token}/details")
async def admin_player_details(token:str,x_telegram_init_data:str|None=Header(default=None)):
    await owner(x_telegram_init_data)
    conn=await db()
    try:
        user=await (await conn.execute("SELECT telegram_id,token,username,first_name,created_at FROM users WHERE UPPER(token)=?",(token.strip().upper(),))).fetchone()
        if not user: raise HTTPException(404,"Игрок не найден")
        uid=int(user["telegram_id"])
        farm=await (await conn.execute("SELECT * FROM farm_state WHERE telegram_id=?",(uid,))).fetchone()
        spin=await (await conn.execute("SELECT tickets,upgrade_points FROM spin_state WHERE telegram_id=?",(uid,))).fetchone()
        inventory=await (await conn.execute("SELECT COALESCE(SUM(qty),0) total,COUNT(*) types FROM farm_inventory WHERE telegram_id=? AND qty>0",(uid,))).fetchone()
        cases=await (await conn.execute("SELECT COUNT(*) total,COALESCE(SUM(CASE WHEN telegram_charge_id<>'' THEN stars_amount ELSE 0 END),0) stars FROM case_openings WHERE telegram_id=? AND (opened_at<>'' OR status IN ('opened','completed','done'))",(uid,))).fetchone()
        orders=await (await conn.execute("SELECT COUNT(*) total,COALESCE(SUM(CASE WHEN telegram_charge_id<>'' THEN stars_amount ELSE 0 END),0) stars FROM orders WHERE telegram_id=?",(uid,))).fetchone()
        spins=await (await conn.execute("SELECT COUNT(*) total FROM spin_history WHERE telegram_id=?",(uid,))).fetchone()
        donate=await (await conn.execute("SELECT COALESCE(SUM(tickets),0) total FROM donation_ticket_balances WHERE telegram_id=?",(uid,))).fetchone()
        return {"user":dict(user),"farm":dict(farm) if farm else {},"spin":dict(spin) if spin else {},"inventory":dict(inventory),"cases":dict(cases),"orders":dict(orders),"spins":dict(spins),"donation_tickets":donate["total"],"stars_spent":int(cases["stars"] or 0)+int(orders["stars"] or 0)}
    finally:
        await conn.close()


@app.post("/api/admin/balances/set")
async def admin_set_balance(body: AdminSetBalanceIn,x_telegram_init_data:str|None=Header(default=None)):
    await owner(x_telegram_init_data)
    limits={"tickets":1000000000,"donation_tickets":1000000000,"shr":1000000000,"shrek_coins":1000000000000000,"farm_item":1000000000}
    if body.asset not in limits or body.amount>limits.get(body.asset,0): raise HTTPException(400,"Недопустимая валюта или количество")
    async with db_write_lock:
        conn=await db()
        try:
            user=await telegram_id_by_token(conn,body.token)
            if not user: raise HTTPException(404,"Игрок не найден")
            uid=int(user["telegram_id"])
            if body.asset in ("tickets","shr"):
                await conn.execute("INSERT OR IGNORE INTO spin_state(telegram_id,tickets,last_free_spin,upgrade_points) VALUES(?,0,0,0)",(uid,))
                col="tickets" if body.asset=="tickets" else "upgrade_points"
                await conn.execute(f"UPDATE spin_state SET {col}=? WHERE telegram_id=?",(body.amount,uid))
            elif body.asset=="donation_tickets":
                case=(body.case_id or "*").strip().upper()
                if case!="*" and not await (await conn.execute("SELECT 1 FROM case_configs WHERE id=?",(case,))).fetchone(): raise HTTPException(404,"Кейс не найден")
                await conn.execute("INSERT INTO donation_ticket_balances(telegram_id,case_id,tickets) VALUES(?,?,?) ON CONFLICT(telegram_id,case_id) DO UPDATE SET tickets=excluded.tickets",(uid,case,body.amount))
            elif body.asset=="shrek_coins":
                await ensure_farm_state(conn,uid)
                await conn.execute("UPDATE farm_state SET shrek_coins=?,updated_at=CURRENT_TIMESTAMP WHERE telegram_id=?",(body.amount,uid))
            else:
                rid=body.resource_id.strip()
                if not rid: raise HTTPException(400,"Укажите ID предмета")
                cur=await conn.execute("UPDATE farm_inventory SET qty=?,updated_at=CURRENT_TIMESTAMP WHERE telegram_id=? AND resource_id=?",(body.amount,uid,rid))
                if cur.rowcount==0: raise HTTPException(404,"Предмет не найден на складе")
            await conn.execute("INSERT INTO farm_log(telegram_id,action,details) VALUES(?,?,?)",(uid,"admin_set_balance",json.dumps({"asset":body.asset,"amount":body.amount,"resource_id":body.resource_id,"case_id":body.case_id},ensure_ascii=False)))
            await conn.commit()
            return {"ok":True}
        finally:
            await conn.close()


@app.post("/api/admin/rewards/grant")
async def admin_grant_rewards(body: AdminRewardIn, x_telegram_init_data: str | None = Header(default=None)):
    await owner(x_telegram_init_data)
    if body.tickets <= 0 and body.donation_tickets <= 0 and body.upgrade_points <= 0 and body.shrek_coins <= 0:
        raise HTTPException(400,"Укажите обычные билеты, Donation Tickets или SHR")
    target_case = (body.donation_case_id or "*").strip().upper() or "*"
    async with db_write_lock:
        conn = await db()
        try:
            user = await telegram_id_by_token(conn, body.token)
            if not user:
                raise HTTPException(404,"Пользователь с таким жетоном не найден")
            uid = int(user["telegram_id"])
            if body.donation_tickets > 0 and target_case != "*":
                case_row = await (await conn.execute("SELECT id FROM case_configs WHERE id=?",(target_case,))).fetchone()
                if not case_row:
                    raise HTTPException(404,"Кейс для Donation Ticket не найден")
            await conn.execute(
                "INSERT OR IGNORE INTO spin_state(telegram_id,tickets,last_free_spin,upgrade_points) VALUES(?,0,0,0)",
                (uid,)
            )
            await conn.execute(
                "UPDATE spin_state SET tickets=tickets+?,upgrade_points=upgrade_points+? WHERE telegram_id=?",
                (body.tickets,body.upgrade_points,uid)
            )
            if body.shrek_coins > 0:
                farm = await ensure_farm_state(conn,uid)
                if int(farm["shrek_coins"] or 0) + body.shrek_coins > 1000000000000000:
                    raise HTTPException(409,"Баланс ShrekCOINS превысит безопасный лимит 1 квадриллион")
                await conn.execute("UPDATE farm_state SET shrek_coins=shrek_coins+?,updated_at=CURRENT_TIMESTAMP WHERE telegram_id=?",(body.shrek_coins,uid))
            if body.donation_tickets > 0:
                await conn.execute(
                    "INSERT INTO donation_ticket_balances(telegram_id,case_id,tickets) VALUES(?,?,?) "
                    "ON CONFLICT(telegram_id,case_id) DO UPDATE SET tickets=tickets+excluded.tickets",
                    (uid,target_case,body.donation_tickets)
                )
            await conn.commit()
        finally:
            await conn.close()
    return {
        "ok":True,"token":body.token.strip().upper(),
        "tickets_added":body.tickets,"donation_tickets_added":body.donation_tickets,
        "donation_case_id":target_case,"upgrade_points_added":body.upgrade_points,"shrek_coins_added":body.shrek_coins
    }


@app.get("/api/admin/cases")
async def admin_cases(x_telegram_init_data: str | None = Header(default=None)):
    await owner(x_telegram_init_data)
    conn = await db()
    try:
        cases = await load_case_catalog(conn,None,include_inactive=True)
    finally:
        await conn.close()
    rewards = [
        {"name":x["name"],"tier":x["tier"],"value_stars":int(x["value_stars"])}
        for x in sorted(SPIN_REWARDS,key=lambda r:(TIER_ORDER.index(r["tier"]),int(r["value_stars"]),r["name"]))
    ]
    return {"cases":cases,"rewards":rewards,"tiers":list(TIER_ORDER)}


@app.patch("/api/admin/cases/{case_id}")
async def admin_update_case(case_id: str, body: CaseAdminIn, x_telegram_init_data: str | None = Header(default=None)):
    await owner(x_telegram_init_data)
    case_id = (case_id or "").strip().upper()
    clean_tiers = {}
    for tier,chance in body.tiers.items():
        t = str(tier).strip().upper()
        if t not in TIER_ORDER:
            raise HTTPException(400,f"Неизвестная редкость: {t}")
        value = float(chance or 0)
        if value > 0:
            clean_tiers[t] = value
    if not clean_tiers:
        raise HTTPException(400,"Включите хотя бы одно качество")
    if abs(sum(clean_tiers.values()) - 100.0) > 0.05:
        raise HTTPException(400,"Сумма процентов должна быть ровно 100%")

    reward_by_name = {x["name"]:x for x in SPIN_REWARDS}
    contents = []
    for name in body.contents:
        if name in reward_by_name and name not in contents:
            contents.append(name)
    if not contents:
        raise HTTPException(400,"Добавьте хотя бы один предмет")
    enabled_tiers = set(clean_tiers)
    invalid = [n for n in contents if reward_by_name[n]["tier"] not in enabled_tiers]
    if invalid:
        raise HTTPException(400,"В содержимом есть предметы из выключенной редкости")
    for tier in enabled_tiers:
        if not any(reward_by_name[n]["tier"] == tier for n in contents):
            raise HTTPException(400,f"Для {tier} нет ни одного предмета")

    is_free = bool(body.is_free)
    stars_price = int(body.stars_price or 0)
    if case_id == "FREE":
        is_free = True
        stars_price = 0
    elif not is_free and stars_price <= 0:
        raise HTTPException(400,"Для платного кейса укажите цену в Stars")

    async with db_write_lock:
        conn = await db()
        try:
            cur = await conn.execute(
                "UPDATE case_configs SET name=?,description=?,icon=?,stars_price=?,is_free=?,active=?,sort_order=?,"
                "tiers_json=?,contents_json=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (
                    body.name.strip(),body.description.strip(),body.icon.strip() or "crate",stars_price,
                    1 if is_free else 0,1 if body.active else 0,int(body.sort_order),
                    json.dumps([{"tier":t,"chance":clean_tiers[t]} for t in TIER_ORDER if t in clean_tiers],ensure_ascii=False),
                    json.dumps(contents,ensure_ascii=False),case_id
                )
            )
            if cur.rowcount == 0:
                raise HTTPException(404,"Кейс не найден")
            await conn.commit()
            row = await (await conn.execute("SELECT * FROM case_configs WHERE id=?",(case_id,))).fetchone()
        finally:
            await conn.close()
    return {"ok":True,"case":parse_case_row(row)}


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
    if promo_type == "donation_spin":
        promo_type = "donation"
    if promo_type not in ("discount","spin","donation"):
        raise HTTPException(400,"Тип промокода: discount, spin или donation")
    if promo_type=="discount" and body.discount_percent<=0:
        raise HTTPException(400,"Для скидочного промокода укажите процент скидки")
    if promo_type=="spin" and body.spin_tickets<=0:
        raise HTTPException(400,"Для SPIN-промокода укажите количество билетов")
    if promo_type=="donation" and body.donation_tickets<=0:
        raise HTTPException(400,"Для Donation Ticket промокода укажите количество синих тикетов")
    target_case=(body.case_id or "").strip().upper() or "*"
    async with db_write_lock:
        conn=await db()
        try:
            if promo_type=="donation" and target_case!="*":
                exists=await (await conn.execute("SELECT id FROM case_configs WHERE id=?",(target_case,))).fetchone()
                if not exists:
                    raise HTTPException(404,"Кейс для промокода не найден")
            try:
                cur=await conn.execute(
                    "INSERT INTO promos(code,promo_type,discount_percent,spin_tickets,donation_tickets,case_id,max_uses,expires_at) "
                    "VALUES(?,?,?,?,?,?,?,?)",
                    (
                        code,promo_type,
                        body.discount_percent if promo_type=="discount" else 0,
                        body.spin_tickets if promo_type=="spin" else 0,
                        body.donation_tickets if promo_type=="donation" else 0,
                        target_case if promo_type=="donation" else "",
                        body.max_uses,body.expires_at.strip()
                    )
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


@app.delete("/api/admin/products/{product_id}")
async def admin_delete_product(product_id:int,x_telegram_init_data:str|None=Header(default=None)):
    await owner(x_telegram_init_data)
    async with db_write_lock:
        conn=await db()
        try:
            await conn.execute("BEGIN IMMEDIATE")
            row=await (await conn.execute("SELECT id,name FROM products WHERE id=?",(product_id,))).fetchone()
            if not row:
                raise HTTPException(404,"Товар уже удалён или не найден")
            # Orders retain historical product names and amounts for audit and disputes.
            await conn.execute("DELETE FROM products WHERE id=?",(product_id,))
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise
        finally:
            await conn.close()
    return {"ok":True,"deleted_id":product_id,"deleted_name":row["name"]}


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


class UCChatMessageIn(BaseModel):
    message: str = Field(min_length=1,max_length=2000)

class UCChatStatusIn(BaseModel):
    status: str

@app.get("/api/uc-chats")
async def user_uc_chats(x_telegram_init_data: str | None = Header(default=None)):
    u=await current_user(x_telegram_init_data)
    conn=await db()
    try:
        rows=await (await conn.execute("SELECT c.id,c.withdrawal_id,c.status,c.created_at,w.uc_amount,(SELECT COUNT(*) FROM uc_support_messages m WHERE m.chat_id=c.id AND m.sender='admin' AND m.id>COALESCE((SELECT last_read_id FROM uc_chat_reads WHERE chat_id=c.id AND reader='user'),0)) unread FROM uc_support_chats c LEFT JOIN uc_withdrawals w ON w.id=c.withdrawal_id WHERE c.telegram_id=? ORDER BY c.id DESC",(int(u["id"]),))).fetchall()
        result=[]
        for r in rows:
            messages=await (await conn.execute("SELECT sender,message,created_at FROM uc_support_messages WHERE chat_id=? ORDER BY id ASC LIMIT 300",(r["id"],))).fetchall()
            result.append({**dict(r),"messages":[dict(m) for m in messages]})
        return result
    finally:await conn.close()

@app.post("/api/uc-chats/{chat_id}/messages")
async def user_uc_chat_reply(chat_id:int,body:UCChatMessageIn,x_telegram_init_data:str|None=Header(default=None)):
    u=await current_user(x_telegram_init_data)
    async with db_write_lock:
        conn=await db()
        try:
            row=await (await conn.execute("SELECT telegram_id,status,withdrawal_id FROM uc_support_chats WHERE id=?",(chat_id,))).fetchone()
            if not row or int(row["telegram_id"])!=int(u["id"]):raise HTTPException(404,"Чат не найден")
            if row["status"]!='Открыт':raise HTTPException(409,"Чат закрыт администратором")
            await conn.execute("INSERT INTO uc_support_messages(chat_id,sender,message) VALUES(?,'user',?)",(chat_id,body.message.strip()))
            await conn.commit()
            withdrawal_id=int(row["withdrawal_id"])
            admins=await (await conn.execute("SELECT telegram_id FROM shop_admins")).fetchall()
            recipients={OWNER_ID,*[int(a["telegram_id"]) for a in admins]}
        finally:await conn.close()
    notice=f"💬 Новый ответ игрока по UC #{withdrawal_id}\n\n{body.message.strip()}\n\nОткройте Админ-панель → Статистика UC → Заявка #{withdrawal_id} → История чата."
    for admin_id in recipients:
        try:
            await tg("sendMessage",{"chat_id":admin_id,"text":notice})
        except Exception:
            print(f"UC chat notification delivery failed for admin {admin_id}")
    return {"ok":True}

@app.get("/api/admin/uc-chats/{withdrawal_id}")
async def admin_uc_chat_read(withdrawal_id:int,x_telegram_init_data:str|None=Header(default=None)):
    await owner(x_telegram_init_data)
    conn=await db()
    try:
        chat=await (await conn.execute("SELECT * FROM uc_support_chats WHERE withdrawal_id=?",(withdrawal_id,))).fetchone()
        if not chat:return {"chat":None,"messages":[]}
        messages=await (await conn.execute("SELECT sender,message,created_at FROM uc_support_messages WHERE chat_id=? ORDER BY id ASC LIMIT 300",(chat["id"],))).fetchall()
        return {"chat":dict(chat),"messages":[dict(m) for m in messages]}
    finally:await conn.close()

@app.post("/api/admin/uc-chats/{withdrawal_id}/messages")
async def admin_uc_chat_send(withdrawal_id:int,body:UCChatMessageIn,x_telegram_init_data:str|None=Header(default=None)):
    await owner(x_telegram_init_data)
    async with db_write_lock:
        conn=await db()
        try:
            w=await (await conn.execute("SELECT id,telegram_id FROM uc_withdrawals WHERE id=?",(withdrawal_id,))).fetchone()
            if not w:raise HTTPException(404,"Заявка не найдена")
            await conn.execute("INSERT OR IGNORE INTO uc_support_chats(withdrawal_id,telegram_id) VALUES(?,?)",(withdrawal_id,int(w["telegram_id"])))
            chat=await (await conn.execute("SELECT id,status FROM uc_support_chats WHERE withdrawal_id=?",(withdrawal_id,))).fetchone()
            if chat["status"]!='Открыт':raise HTTPException(409,"Сначала откройте чат")
            await conn.execute("INSERT INTO uc_support_messages(chat_id,sender,message) VALUES(?,'admin',?)",(chat["id"],body.message.strip()))
            await conn.commit()
            uid=int(w["telegram_id"])
        finally:await conn.close()
    try:await tg("sendMessage",{"chat_id":uid,"text":f"💬 Сообщение по выдаче UC #{withdrawal_id}:\n\n{body.message.strip()}\n\nОтветить можно в разделе «Поддержка» мини-приложения."})
    except Exception:pass
    return {"ok":True}

@app.patch("/api/admin/uc-chats/{withdrawal_id}")
async def admin_uc_chat_status(withdrawal_id:int,body:UCChatStatusIn,x_telegram_init_data:str|None=Header(default=None)):
    await owner(x_telegram_init_data)
    if body.status not in ("Открыт","Закрыт"):raise HTTPException(400,"Недопустимый статус")
    async with db_write_lock:
        conn=await db()
        try:
            w=await (await conn.execute("SELECT telegram_id FROM uc_withdrawals WHERE id=?",(withdrawal_id,))).fetchone()
            if not w:raise HTTPException(404,"Заявка не найдена")
            await conn.execute("INSERT OR IGNORE INTO uc_support_chats(withdrawal_id,telegram_id) VALUES(?,?)",(withdrawal_id,int(w["telegram_id"])))
            await conn.execute("UPDATE uc_support_chats SET status=? WHERE withdrawal_id=?",(body.status,withdrawal_id))
            await conn.commit()
        finally:await conn.close()
    return {"ok":True,"status":body.status}


async def uc_chat_mark(conn,chat_id,reader):
    await conn.execute("INSERT INTO uc_chat_reads(chat_id,reader,last_read_id) VALUES(?,?,COALESCE((SELECT MAX(id) FROM uc_support_messages WHERE chat_id=?),0)) ON CONFLICT(chat_id,reader) DO UPDATE SET last_read_id=excluded.last_read_id",(chat_id,reader,chat_id))

@app.get("/api/uc-chats/unread")
async def user_uc_unread(x_telegram_init_data:str|None=Header(default=None)):
    u=await current_user(x_telegram_init_data)
    conn=await db()
    try:
        row=await (await conn.execute("SELECT COUNT(*) n FROM uc_support_messages m JOIN uc_support_chats c ON c.id=m.chat_id WHERE c.telegram_id=? AND m.sender='admin' AND m.id>COALESCE((SELECT last_read_id FROM uc_chat_reads WHERE chat_id=c.id AND reader='user'),0)",(int(u["id"]),))).fetchone()
        return {"unread":int(row["n"])}
    finally:await conn.close()

@app.post("/api/uc-chats/read-all")
async def user_uc_read_all(x_telegram_init_data:str|None=Header(default=None)):
    u=await current_user(x_telegram_init_data)
    async with db_write_lock:
        conn=await db()
        try:
            rows=await (await conn.execute("SELECT id FROM uc_support_chats WHERE telegram_id=?",(int(u["id"]),))).fetchall()
            for row in rows:await uc_chat_mark(conn,int(row["id"]),"user")
            await conn.commit()
        finally:await conn.close()
    return {"ok":True}

@app.post("/api/uc-chats/{chat_id}/read")
async def user_uc_read(chat_id:int,x_telegram_init_data:str|None=Header(default=None)):
    u=await current_user(x_telegram_init_data)
    async with db_write_lock:
        conn=await db()
        try:
            row=await (await conn.execute("SELECT id FROM uc_support_chats WHERE id=? AND telegram_id=?",(chat_id,int(u["id"])))).fetchone()
            if not row:raise HTTPException(404,"Чат не найден")
            await uc_chat_mark(conn,chat_id,"user")
            await conn.commit()
        finally:await conn.close()
    return {"ok":True}

@app.get("/api/admin/uc-chats/unread")
async def admin_uc_unread(x_telegram_init_data:str|None=Header(default=None)):
    await owner(x_telegram_init_data)
    conn=await db()
    try:
        rows=await (await conn.execute("SELECT c.withdrawal_id,COUNT(m.id) unread FROM uc_support_chats c JOIN uc_support_messages m ON m.chat_id=c.id AND m.sender='user' AND m.id>COALESCE((SELECT last_read_id FROM uc_chat_reads WHERE chat_id=c.id AND reader='admin'),0) GROUP BY c.id")).fetchall()
        return {"unread":sum(int(r["unread"]) for r in rows),"chats":[dict(r) for r in rows]}
    finally:await conn.close()

@app.post("/api/admin/uc-chats/{withdrawal_id}/read")
async def admin_uc_read(withdrawal_id:int,x_telegram_init_data:str|None=Header(default=None)):
    await owner(x_telegram_init_data)
    async with db_write_lock:
        conn=await db()
        try:
            row=await (await conn.execute("SELECT id FROM uc_support_chats WHERE withdrawal_id=?",(withdrawal_id,))).fetchone()
            if not row:raise HTTPException(404,"Чат не найден")
            await uc_chat_mark(conn,int(row["id"]),"admin")
            await conn.commit()
        finally:await conn.close()
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
.nav.spin-locked{opacity:.48;filter:saturate(.55);pointer-events:none}.nav.spin-locked:after{content:"SPIN";position:absolute;right:10px;top:-8px;font-size:9px;font-weight:1000;letter-spacing:.7px;color:#171000;background:#ffd044;border-radius:8px;padding:3px 6px;box-shadow:0 0 14px #ffc21c55}
.spin-lock-note{display:none;margin-top:9px;font-size:11px;font-weight:850;color:#ffd45a;text-align:center}.spin-lock-note.show{display:block}
.spin-case-picker{margin:12px 0 14px}.spin-case-picker h3{margin:0 0 9px}.spin-case-scroll{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;padding:2px 0 8px}
.spin-case-card{min-width:0;min-height:202px;background:#111418;border:1px solid #2b3036;border-radius:19px;padding:12px 11px;color:#fff;text-align:left;position:relative;overflow:hidden;transition:.16s transform,.16s border-color,.16s box-shadow;display:flex;flex-direction:column}.spin-case-card:active{transform:scale(.98)}.spin-case-card.active{border-color:#ffd044;box-shadow:0 0 22px #ffc21c44,inset 0 0 24px #ffc21c12}
.spin-case-card:disabled{opacity:.55}.spin-case-top{display:grid;grid-template-columns:56px minmax(0,1fr);align-items:center;gap:9px;min-height:60px}.spin-case-title{font-size:13px;font-weight:950;line-height:1.15}.spin-case-price{font-size:12px;font-weight:950;color:#ffd45a;margin-top:4px}.spin-case-desc{font-size:10.5px;color:#a8b0b8;line-height:1.35;min-height:44px;margin:9px 0 7px}.spin-case-odds{display:flex;flex-wrap:wrap;align-content:flex-start;gap:4px;margin-top:auto;min-height:48px}.spin-case-odds span{font-size:8.7px;font-weight:900;padding:4px 6px;border-radius:8px;background:#1c2127;border:1px solid #2c3238}.spin-case-ticket{margin-top:8px;font-size:9.5px;font-weight:950;color:#75c6ff}
.spin-case-note{font-size:10px;color:#939aa2;margin-top:7px;line-height:1.35}.case-icon{width:54px;height:54px;border-radius:16px;display:grid;place-items:center;border:1px solid #3b4857;background:linear-gradient(145deg,#202a35,#0b1015);box-shadow:inset 0 1px #ffffff22,0 10px 18px #0007;position:relative;color:#8bc8ff}.case-icon svg{width:31px;height:31px;stroke:currentColor;fill:none;stroke-width:2.1;stroke-linecap:round;stroke-linejoin:round;filter:drop-shadow(0 0 7px currentColor)}.case-icon-crate{color:#67b8ff}.case-icon-helmet{color:#a881ff}.case-icon-airdrop{color:#6be7d8}.case-icon-vault{color:#ff79ca}.case-icon-crown{color:#ffd45a;border-color:#82671e;background:linear-gradient(145deg,#3d2d08,#0d0a04)}
.blue-ticket{color:#75c6ff!important;text-shadow:0 0 10px #319fff66}.donation-stat{border-color:#245f98!important;background:linear-gradient(145deg,#10283f,#0b141e)!important}
@media(max-width:360px){.spin-case-scroll{grid-template-columns:1fr}.spin-case-card{min-height:182px}}
.page-home{display:inline-flex;align-items:center;gap:7px;margin:0 0 12px;background:#171b20;color:#dce1e6;border:1px solid #30363d;padding:9px 12px;border-radius:13px;box-shadow:inset 0 1px #ffffff0a}
.settings-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:12px 0}
.setting-card{background:#111418;border:1px solid #2a3036;border-radius:18px;padding:14px}
.setting-card h3{margin:0 0 5px;font-size:15px}.setting-card .muted{font-size:11px}
.switch-row{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-top:12px}
.switch-row input{width:22px;height:22px;accent-color:#ffc21c}
.spin-options-grid{display:grid;grid-template-columns:1fr;gap:8px;margin-top:12px}
.spin-options-grid .spin-options{margin-top:0;min-height:58px}
@media(max-width:430px){.spin-options-grid{grid-template-columns:1fr}.settings-grid{grid-template-columns:1fr}}
.history-filters{background:#111418;border:1px solid #2a3036;border-radius:18px;padding:12px;margin-bottom:12px}
.history-filter-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}.history-filter-grid>*{min-width:0}
.history-periods{display:flex;gap:6px;overflow-x:auto;padding:8px 0 3px;scrollbar-width:none}.history-periods::-webkit-scrollbar{display:none}
.history-periods button{white-space:nowrap;background:#1c2127;color:#aeb5bd;border:1px solid #30363d;padding:8px 10px}.history-periods button.active{background:#33290c;color:#ffd45b;border-color:#6d5719}
.history-result-head{display:flex;justify-content:space-between;align-items:center;gap:10px;margin:12px 0 8px}
.history-time{font-size:11px;font-weight:850;color:#d0d6dc;margin-top:7px}
.case-guide{display:grid;gap:12px}.case-guide-card{background:#111418;border:1px solid #2a3036;border-radius:20px;padding:14px;overflow:hidden;min-height:250px;display:flex;flex-direction:column}
.case-guide-head{display:grid;grid-template-columns:62px minmax(0,1fr) auto;align-items:center;gap:10px;margin-bottom:8px;min-height:64px}.case-guide-head .case-icon{width:58px;height:58px}.case-guide-name{font-size:17px;font-weight:950}.case-guide-price{font-size:15px;font-weight:1000;color:#ffd45a;white-space:nowrap}.case-guide-desc{min-height:42px;font-size:11px;color:#a1a8b0;line-height:1.35;margin-bottom:10px}
.case-tier-row{display:flex;gap:9px;overflow-x:auto;padding:3px 0 5px;scrollbar-width:none;margin-top:auto}.case-tier-row::-webkit-scrollbar{display:none}.case-tier-btn{flex:0 0 134px;min-height:132px;background:#171b20;border:1px solid #2c3238;border-radius:17px;padding:12px 10px;text-align:center;color:#fff}.case-tier-btn .loot-cube{width:60px;height:60px;border-radius:15px;font-size:28px;margin:0 auto 8px}.case-tier-btn .rarity-card-title{font-size:10.5px}.case-tier-btn .rarity-card-chance{font-size:17px}.case-guide-note{font-size:10px;color:#858d96;margin-top:10px;line-height:1.35}
.case-admin-card{border-color:#304154}.case-admin-top{display:grid;grid-template-columns:1fr 1fr;gap:8px}.case-admin-tier-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin:8px 0}.case-admin-tier{display:grid;grid-template-columns:auto 1fr 78px;gap:7px;align-items:center;background:#151a20;border:1px solid #2c333b;border-radius:13px;padding:8px}.case-admin-tier input[type=checkbox]{width:20px;height:20px;margin:0}.case-admin-tier input[type=number]{margin:0;padding:9px}.case-admin-items details{background:#11161b;border:1px solid #29323b;border-radius:13px;padding:8px 10px;margin:7px 0}.case-admin-items summary{cursor:pointer;font-weight:900}.case-item-list{display:grid;gap:6px;margin-top:8px;max-height:230px;overflow:auto}.case-item-list label{display:flex;align-items:center;gap:8px;font-size:11px;background:#171d23;border-radius:9px;padding:7px}.case-item-list input{width:17px;height:17px;margin:0}.case-item-list b{margin-left:auto;color:#ffd45a}.donation-ticket-chip{display:inline-flex;align-items:center;gap:5px;padding:4px 7px;border-radius:9px;background:#0c2d4d;border:1px solid #2678bd;color:#78c9ff;font-size:10px;font-weight:950}
@media(max-width:430px){.case-guide-head{grid-template-columns:58px minmax(0,1fr)}.case-guide-price{grid-column:2}.case-admin-top,.case-admin-tier-grid{grid-template-columns:1fr}}
@media(max-width:430px){.history-filter-grid{grid-template-columns:1fr}}

/* live big wins */
.wins{height:42px;border:1px solid #2a2f35;background:#0d1013;border-radius:14px;overflow:hidden;margin:0 0 16px;display:flex;align-items:center;position:relative}
.wins:before{content:"LIVE";position:absolute;z-index:3;left:0;top:0;bottom:0;display:flex;align-items:center;padding:0 10px;font-size:10px;font-weight:950;color:#111;background:linear-gradient(135deg,#ffd431,#f4a900);box-shadow:7px 0 18px #000}
.wins-track{display:flex;align-items:center;gap:28px;white-space:nowrap;width:max-content;padding-left:65px;animation:ticker 48s linear infinite;will-change:transform}
.win-item{font-size:12px;font-weight:800}.win-item.legendary,.win-item.gold{color:#ffd85c;text-shadow:0 0 14px #ffc40088}.win-item.mythic,.win-item.red{color:#ff6262;text-shadow:0 0 14px #ff202088}
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




.shx-player-detail-btn{width:100%;text-align:left;cursor:pointer;color:#eaf4ff;background:transparent;border:0}.shx-player-name{min-width:0}.shx-player-name b,.shx-player-name small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.shx-player-name small{color:#91add0}.shx-player-detail-result{background:#061c35;border:1px solid #24629b;border-radius:12px;padding:12px;margin:6px 0 12px}.shx-player-detail-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}.shx-player-detail-grid>div{background:#0b2948;border:1px solid #204e7c;border-radius:9px;padding:9px;min-width:0}.shx-player-detail-grid small{display:block;color:#9bbbd6;font-size:10px}.shx-player-detail-grid b{display:block;font-size:17px;margin-top:5px}.shx-order-detail{border-top:1px solid #21486d;padding:10px 2px}.shx-order-detail summary{display:flex;align-items:center;justify-content:space-between;gap:7px;cursor:pointer;font-size:12px}.shx-order-detail summary span{flex:1}.shx-order-detail summary em{color:#5ce2b3;font-size:10px}.shx-order-fields{display:grid;gap:7px;padding:12px 6px;font-size:12px;color:#bcd7ed}.shx-order-links{display:flex;flex-wrap:wrap;gap:10px}.shx-order-links a{color:#69c2ff;text-decoration:underline}@media(max-width:760px){.shx-player-detail-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.shx-player-detail-btn{grid-template-columns:12px 25px minmax(0,1fr) 55px}.shx-player-detail-btn>span:last-child{display:none}}
.shx-product-actions{display:flex;gap:10px;margin-top:12px}.shx-product-actions .secondary{flex:1}.shx-product-delete{background:#571a2b!important;border:1px solid #df5c78!important;color:#ffdce5!important;border-radius:12px!important;padding:10px 13px!important;font-weight:800;min-height:43px}.shx-product-delete:disabled{opacity:.55}@media(max-width:420px){.shx-product-actions{flex-wrap:wrap}.shx-product-actions button{flex:1 1 100%}}
.farm-overview .farm-wallet-value,.shx-wallet-count{min-width:0;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-variant-numeric:tabular-nums}.farm-overview .farm-wallet-value{font-size:clamp(15px,3.5vw,28px)!important;gap:3px}.farm-overview .farm-wallet-value svg{flex-shrink:0;max-width:28px}.farm-upgrade-explainer{font-size:12px;line-height:1.5;color:#a9c7df;padding:9px 12px;margin:5px 0 13px;background:#091e34;border:1px solid #235276;border-radius:10px}.farm-upgrade-explainer b{color:#f8cf76}@media(max-width:420px){.farm-overview .farm-wallet-value{font-size:16px!important}.farm-overview .farm-wallet-value svg{max-width:23px}}
.farm-bulk-selector{margin:8px 0}.farm-bulk-selector select{width:100%;min-height:40px;border:1px solid #477caa;border-radius:10px;background:#0c2741;color:#eaf5ff;padding:6px;font-weight:800}.farm-module .farm-bulk-selector+button{width:100%}
.farm-bulk-quote{margin:7px 0 10px;padding:10px;border:1px solid #37658a;border-radius:10px;background:#0b263c;color:#b9d9ef;font-size:12px;line-height:1.6}.farm-bulk-quote b{color:#f9d48b}
.farm-collectible[data-tier="RAINBOW"]:before{background:conic-gradient(from 30deg,#fa6589,#ffcf68,#72e7a5,#65c9ff,#ae7dff,#fa6589);border:2px solid #d8b6ff;box-shadow:0 0 18px #a76fff77}.farm-rarity-label.RAINBOW{color:#f8e5ff;border-color:#b78cff;background:linear-gradient(110deg,#713a82,#245c83,#6a3979);text-shadow:0 1px 3px #000}.shx-farm-catalog .farm-catalog-card[data-tier="RAINBOW"]{border:2px solid #b08aff;background:linear-gradient(145deg,#14243c,#292047 50%,#0e2b3b);box-shadow:0 0 18px #a76fff22}
.farm-module{display:flex;flex-direction:column;min-width:0;overflow:hidden;box-sizing:border-box}.farm-module .farm-bulk-selector,.farm-module .farm-bulk-quote,.farm-module .farm-upgrade-btn{width:100%;min-width:0;box-sizing:border-box}.farm-bulk-quote{overflow-wrap:anywhere;line-height:1.45;font-size:12px}.farm-bulk-selector select{max-width:100%}.farm-max-label{padding:12px 8px;margin:10px 0;border:1px solid #35685a;border-radius:10px;background:#12332c;color:#9de6c0;text-align:center;font-weight:800;font-size:12px}.farm-module .farm-upgrade-btn{margin-top:8px;min-height:44px;white-space:normal;overflow-wrap:anywhere}@media(max-width:700px){.farm-modules{grid-template-columns:minmax(0,1fr)!important}.farm-module{padding:14px}.farm-module-header{font-size:15px}.farm-module-desc{font-size:12px}}
/* Exact reference layout structure: PUBG owner console */
.shx-reference{grid-template-columns:220px minmax(0,1fr);background:#020b1b;border-color:#143a70;border-radius:15px}.shx-reference .shx-v4-sidebar{background:linear-gradient(180deg,#071d3b,#031027);padding:14px 12px}.shx-reference .shx-v4-brand{display:flex;align-items:center;gap:8px;padding:3px 4px 16px}.shx-reference .shx-v4-brand b{font-size:15px;white-space:nowrap}.shx-reference .shx-v4-brand small{margin:4px 0 0;font-size:10px}.shx-crown{font-size:29px}.shx-reference .shx-v4-sidebar nav button{display:flex;align-items:center;gap:12px;padding:10px 11px;font-size:13px}.shx-menu-icon{font-size:19px;width:22px;text-align:center;color:#a7d3ff}.shx-reference .shx-v4-main{background:radial-gradient(ellipse at 65% -15%,#1e375e,#06162d 40%,#020b1b 100%);padding:15px 12px 24px}.shx-reference .shx-v4-header{min-height:60px;padding:2px 8px 17px}.shx-reference .shx-v4-header h1{font-size:24px;font-weight:900}.shx-header-pills{display:flex;gap:9px}.shx-header-pills b{border:1px solid #224c7d;background:#061b35;border-radius:12px;padding:11px 13px;font-size:11px;white-space:nowrap}.shx-reference .shx-v4-metrics{grid-template-columns:repeat(6,minmax(0,1fr));gap:9px}.shx-reference .shx-v4-metric{min-height:66px;padding:10px 8px}.shx-reference .shx-v4-metric>div{display:flex;align-items:center;gap:6px}.shx-reference .shx-v4-metric small{font-size:9px}.shx-reference .shx-v4-metric strong{font-size:19px;margin:8px 0}.shx-metric-icon{font-size:23px}.shx-ref-topgrid{display:grid;grid-template-columns:minmax(0,1.7fr) minmax(0,1fr);gap:10px}.shx-reference .shx-v4-panel{padding:12px;margin-bottom:10px}.shx-reference .shx-v4-panel h2{font-size:15px!important}.shx-reference .shx-v4-actions{grid-template-columns:repeat(5,minmax(0,1fr));gap:7px}.shx-reference .shx-v4-actions button{font-size:11px;min-height:91px}.shx-ref-user{display:grid;grid-template-columns:14px 29px minmax(0,1fr) 72px 67px;align-items:center;gap:8px;border-top:1px solid #173b64;padding:6px 4px;font-size:11px}.shx-ref-user>div{min-width:0}.shx-ref-user b,.shx-ref-user small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.shx-ref-user small{color:#91add0;margin-top:3px}.shx-ref-user button{border:1px solid #197dd1;border-radius:7px;background:#0a4c93;color:#e9f5ff;padding:7px 3px;font-size:11px}.shx-ref-avatar{font-size:22px}.shx-ref-bal{font-size:10px;color:#ffd274}.shx-ref-art{height:106px;border:1px solid #1d4c80;border-radius:12px;background:linear-gradient(110deg,#06142a 5%,#122d53 60%,#533e31);display:flex;align-items:center;justify-content:space-around;overflow:hidden;color:#bcd7f5;font-weight:900;letter-spacing:2px}.shx-ref-art span:last-child{font-size:70px}.shx-ref-bottom{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}.shx-ref-bottom .shx-v4-panel{min-height:135px}.shx-ref-bottom .buy{width:100%}
@media(max-width:1100px){.shx-reference .shx-v4-metrics{grid-template-columns:repeat(3,minmax(0,1fr))}.shx-ref-topgrid{grid-template-columns:1fr}.shx-ref-bottom{grid-template-columns:1fr 1fr}.shx-header-pills{display:none}}
@media(max-width:760px){.shx-reference{display:block}.shx-reference .shx-v4-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.shx-reference .shx-v4-metric strong{font-size:22px}.shx-ref-bottom{grid-template-columns:1fr}.shx-ref-user{grid-template-columns:12px 25px minmax(0,1fr) 55px}.shx-ref-user button{display:none}.shx-ref-bal{font-size:9px}.shx-reference .shx-v4-actions{grid-template-columns:repeat(3,minmax(0,1fr))}}

/* SHREKSICH premium console inspired by approved reference */
.shx-v4{display:grid;grid-template-columns:210px minmax(0,1fr);background:#041023;border:1px solid #174c79;border-radius:18px;overflow:hidden;color:#eaf4ff;min-height:650px;margin:6px 0 24px}.shx-v4-sidebar{background:linear-gradient(180deg,#08264c,#04172d);border-right:1px solid #1b4a77;padding:16px 10px;display:flex;flex-direction:column;gap:16px}.shx-v4-brand{font-size:13px;padding:7px 6px 18px;border-bottom:1px solid #23527a}.shx-v4-brand small{display:block;color:#8bb4dd;font-size:10px;letter-spacing:1.5px;margin:5px 0 0 26px}.shx-v4-sidebar nav{display:flex;flex-direction:column;gap:5px}.shx-v4-sidebar nav button{border:1px solid transparent;background:transparent;text-align:left;padding:11px 9px;border-radius:9px;color:#c6dafa;font-size:13px;font-weight:750}.shx-v4-sidebar nav button.active{background:linear-gradient(110deg,#087bdf,#0a397a);border-color:#208bf1;color:white}.shx-v4-online{margin-top:auto;background:#092d43;color:#38e7b0;padding:12px;border-radius:12px;font-size:12px}.shx-v4-main{min-width:0;padding:15px 17px 28px;background:radial-gradient(ellipse at 45% 0,#102d50,transparent 40%),#041124}.shx-v4-header{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:8px 4px 20px}.shx-v4-header small{color:#f6bf59;font-size:10px;letter-spacing:1.5px;font-weight:900}.shx-v4-header h1{font-size:27px;margin:5px 0}.shx-v4-header span{font-size:12px;color:#a1c5e8}.shx-v4-header>b{background:#082c3b;border:1px solid #176a62;padding:10px;border-radius:10px;color:#67eebc;font-size:12px}.shx-v4-mobile{display:none}.shx-v4-mobile label{font-size:11px;color:#a9c8e7;font-weight:900;letter-spacing:1px}.shx-v4-mobile select{width:100%;margin:7px 0 10px;background:#0a2b50;border:1px solid #3777b0;border-radius:13px;color:#fff;font-weight:800;font-size:15px;padding:14px}.shx-admin-quick{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px}.shx-admin-quick button{min-width:0;background:#0a3159;color:#cbe5ff;border:1px solid #285783;border-radius:10px;padding:10px 4px;font-size:12px}.shx-v4-metrics{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin-bottom:13px}.shx-v4-metric{position:relative;overflow:hidden;border:1px solid #225c9c;border-radius:13px;padding:13px;background:linear-gradient(145deg,#0d3155,#06172d);min-width:0}.shx-v4-metric small{font-size:10px;color:#c5d8ed}.shx-v4-metric strong{display:block;font-size:25px;margin:12px 0}.shx-v4-metric i{position:absolute;right:8px;bottom:5px;color:#18c5ff;opacity:.6}.shx-v4-metric.tone1{border-color:#7e365b}.shx-v4-metric.tone2{border-color:#967b39}.shx-v4-metric.tone4{border-color:#13745e}.shx-v4-metric.tone5{border-color:#714b9c}.shx-v4-panel{border:1px solid #1b568c;background:linear-gradient(145deg,#0a2a4a,#061a30);padding:15px;border-radius:14px;margin-bottom:12px;min-width:0}.shx-v4-panel h2{font-size:16px!important;margin:0 0 14px!important;display:flex;justify-content:space-between;gap:6px}.shx-v4-panel h2 button{background:none;border:0;color:#69baff;font-size:12px}.shx-v4-panel p{color:#a5c5df;font-size:13px;line-height:1.5}.shx-v4-actions{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:9px}.shx-v4-actions button{min-height:93px;border:1px solid #2583d8;border-radius:12px;background:linear-gradient(135deg,#155bb1,#0c306e);color:white;font-size:11px;font-weight:800;display:flex;flex-direction:column;justify-content:center;align-items:center;gap:10px}.shx-v4-actions span{font-size:27px}.shx-v4-actions .tone0{background:linear-gradient(130deg,#08997c,#086050);border-color:#14c79f}.shx-v4-actions .tone2{background:linear-gradient(130deg,#753ec1,#3b1874);border-color:#a567ee}.shx-v4-actions .tone3{background:linear-gradient(130deg,#9b631e,#633c13);border-color:#e4a54d}.shx-v4-actions .tone4{background:linear-gradient(130deg,#a82f56,#611832);border-color:#f06486}.shx-v4-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.shx-v4-item{display:flex;align-items:center;gap:8px;border-top:1px solid #204566;padding:10px 0;font-size:12px}.shx-v4-item>div{flex:1;min-width:0}.shx-v4-item b,.shx-v4-item small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.shx-v4-item small{color:#91b4d2;margin-top:4px}.shx-v4-item em{font-size:10px;color:#56deb1}.shx-v4-item button{background:#0a599c;border:1px solid #2581c8;border-radius:8px;padding:6px;color:white}.shx-v4 .shx-owner-content .card,.shx-v4 .shx-owner-content .admin-card{background:linear-gradient(145deg,#0a2948,#07192e)!important;border:1px solid #255a87!important}.shx-v4 .shx-owner-content input:not([type=checkbox]),.shx-v4 .shx-owner-content textarea,.shx-v4 .shx-owner-content select{background:#071b31!important;border-color:#305f87!important}
@media(min-width:1120px){.shx-v4-metrics{grid-template-columns:repeat(6,minmax(0,1fr))}.shx-v4-metric{padding:10px}.shx-v4-metric strong{font-size:20px}}
@media(max-width:760px){.shx-v4{display:block;margin:3px -2px 20px}.shx-v4-sidebar{display:none}.shx-v4-main{padding:11px 12px 20px}.shx-v4-header h1{font-size:23px}.shx-v4-mobile{display:block;padding-bottom:14px;white-space:normal}.shx-v4-mobile button{flex:0 0 auto;border:1px solid #285783;background:#09284b;color:#bad8f3;border-radius:10px;padding:10px 12px;font-size:12px;font-weight:800}.shx-v4-mobile button.active{background:#1166bb;border-color:#3699f4;color:white}.shx-v4-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.shx-v4-grid{grid-template-columns:1fr}.shx-v4-actions{grid-template-columns:repeat(3,minmax(0,1fr))}.shx-v4-actions button{min-height:83px}.shx-v4-metric strong{font-size:23px}}

/* Owner dashboard v3 — consistent mobile-first design across all sections */
.shx-owner-header{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:18px 17px;margin:12px 0 14px;border-radius:22px;border:1px solid #376284;background:linear-gradient(115deg,#17354e,#091827 78%);box-shadow:0 10px 34px #0004}
.shx-owner-header>div{display:flex;flex-direction:column;gap:5px;min-width:0}.shx-owner-eyebrow{font-size:10px;font-weight:900;letter-spacing:2px;color:#f2c469}.shx-owner-header strong{font-size:22px;line-height:1.2;color:#f2f8ff}.shx-owner-header small{color:#9fbad0;font-size:12px}
.shx-owner-home{width:48px;height:48px;border-radius:14px;background:#17334b;border:1px solid #426c89;color:#f4ca74;font-size:28px;flex-shrink:0}
.shx-owner-nav{display:flex!important;gap:8px!important;overflow-x:auto!important;overflow-y:hidden;white-space:nowrap;scroll-snap-type:x proximity;scrollbar-width:none;padding:5px 0 15px!important;margin:0 0 12px!important;-webkit-overflow-scrolling:touch}
.shx-owner-nav::-webkit-scrollbar{display:none}.shx-owner-nav button{display:inline-flex!important;align-items:center;justify-content:center;gap:8px;flex:0 0 auto!important;min-height:42px;padding:9px 15px!important;border:1px solid #344e65!important;border-radius:13px!important;background:#101f30!important;color:#a9bfd0!important;font-size:13px!important;font-weight:750!important}
.shx-owner-nav button.active{background:linear-gradient(120deg,#45351a,#302818)!important;color:#ffd470!important;border-color:#a37b29!important;box-shadow:0 0 0 1px #d6a83e25}.shx-nav-dot{width:6px;height:6px;border-radius:50%;background:#5d7890}.shx-owner-nav button.active .shx-nav-dot{background:#ffd470}
.shx-owner-content h2{font-size:23px;line-height:1.25;margin:14px 0 16px;color:#edf6ff}.shx-owner-content .card,.shx-owner-content .admin-card{background:linear-gradient(140deg,#14263a,#101b2a)!important;border:1px solid #304c65!important;border-radius:19px!important;padding:16px!important;margin-bottom:13px!important;box-shadow:0 8px 22px #0002}
.shx-owner-content .admin-card .name{font-size:16px;font-weight:850}.shx-owner-content .cat{color:#f2c369;font-size:12px;letter-spacing:.6px}
.shx-owner-content input:not([type=checkbox]),.shx-owner-content textarea,.shx-owner-content select{max-width:100%;min-width:0;box-sizing:border-box;border-radius:12px!important;background:#0b1a2b!important;border:1px solid #3b5871!important;color:#eaf5ff!important;padding:12px!important;font-size:15px!important}
.shx-owner-content input:focus,.shx-owner-content textarea:focus,.shx-owner-content select:focus{outline:2px solid #b58c36!important;outline-offset:0}.shx-owner-content button{touch-action:manipulation}.shx-owner-content .buy{border-radius:13px!important;min-height:46px!important;font-weight:850!important}.shx-owner-content .secondary{border-radius:12px!important;min-height:42px!important}
.shx-owner-content .adminline,.shx-owner-content .row{flex-wrap:wrap;gap:9px}.shx-owner-content .adminline>*{flex:1 1 145px;min-width:0}
.shx-owner-content .metrics{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:11px}.shx-owner-content .metric{min-width:0;border-radius:17px!important;border:1px solid #36516b!important;background:linear-gradient(135deg,#142a40,#101924)!important;padding:17px 13px!important}.shx-owner-content .metric b{font-size:25px;word-break:break-word}
.shx-owner-content .shx-admin-grant{background:linear-gradient(150deg,#132c45,#0c192b 75%)!important;border-color:#365f7b!important}
@media(max-width:420px){.shx-owner-header strong{font-size:19px}.shx-owner-content .metrics{gap:8px}.shx-owner-content .metric{padding:13px 11px!important}.shx-owner-content .metric b{font-size:23px}.shx-owner-content .adminline>*{flex-basis:100%}}

/* Mobile-first owner rewards redesign */
.shx-admin-grant{background:linear-gradient(150deg,#132c45,#0c192b 75%);border:1px solid #365f7b;border-radius:24px;padding:20px 16px;margin:12px 0 22px;box-shadow:0 16px 40px #0003}
.shx-admin-kicker{color:#f4c76c;font-size:11px;letter-spacing:2px;font-weight:900}
.shx-admin-grant h2{font-size:25px;margin:9px 0}.shx-admin-grant p{color:#adc2d3;line-height:1.5;margin:0 0 20px;font-size:14px}
.shx-grant-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.shx-grant-field{display:flex;flex-direction:column;gap:7px;margin:0 0 14px;min-width:0;font-weight:750;color:#e6f4ff;font-size:13px}
.shx-grant-field small{font-size:11px;font-weight:400;color:#8eaac2;min-height:26px}.shx-grant-field input,.shx-grant-field select{box-sizing:border-box;width:100%;min-width:0;margin:0;padding:14px 12px;background:#071827;color:#f5faff;border:1px solid #3b607d;border-radius:13px;font-size:15px;outline:none}
.shx-grant-field input:focus,.shx-grant-field select:focus{border-color:#f1bd55;box-shadow:0 0 0 2px #f1bd5530}.shx-grant-note{font-size:12px;line-height:1.5;color:#99bcd3;background:#0b2538;border-radius:12px;padding:12px;margin:4px 0 16px}.shx-grant-submit{width:100%;min-height:52px;font-size:16px;font-weight:900}.shx-admin-players-head{display:flex;align-items:center;justify-content:space-between;gap:8px;margin:20px 0 10px}.shx-admin-players-head h3{margin:0}.shx-admin-players-head span{color:#95b4c9;font-size:12px}.shx-admin-player{border-radius:17px!important}.shx-player-token{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0}.shx-player-token .token-code{flex:1;min-width:135px;text-align:left;background:#102c42;color:#ffd477;border:1px solid #3c6580;border-radius:10px;padding:11px;cursor:pointer}.shx-player-token .secondary{flex:1;min-width:135px;margin:0}
@media(max-width:380px){.shx-grant-grid{grid-template-columns:1fr}.shx-admin-grant{padding:16px 12px}}

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
.tier-gray{color:#d0d5da;background:#20242a;border-color:#606870}
.tier-cyan{color:#70efff;background:#082a30;border-color:#22bccc;box-shadow:0 0 14px #27d9e744}
.tier-blue{color:#65a9ff;background:#0a1d3b;border-color:#2a6fd0;box-shadow:0 0 16px #2a7dff55}
.tier-purple{color:#c982ff;background:#29103a;border-color:#9142d0;box-shadow:0 0 18px #a64cff66}
.tier-pink{color:#ff82d6;background:#3b0b2c;border-color:#db399d;box-shadow:0 0 20px #ff4fba77}
.tier-red{color:#ff6767;background:#3a0808;border-color:#e72c2c;box-shadow:0 0 26px #ff242488}
.tier-gold{color:#ffe06a;background:#3a2a05;border-color:#ffb400;box-shadow:0 0 30px #ffc40099}
.rarity-row{margin-top:10px}.rarity-label{font-size:10px;font-weight:950;letter-spacing:1px;margin-bottom:5px}
.rarity-bar{height:5px;border-radius:999px;position:relative;overflow:hidden;background:#252a30}
.rarity-bar:after{content:"";position:absolute;inset:0;background:linear-gradient(90deg,transparent,#fff8,transparent);transform:translateX(-120%);animation:raritySweep 2.2s linear infinite}
.rb-common{background:linear-gradient(90deg,#58616a,#aeb6be)}
.rb-rare{background:linear-gradient(90deg,#146bb0,#5fc0ff);box-shadow:0 0 10px #2fa8ff66}
.rb-epic{background:linear-gradient(90deg,#6b28a4,#d071ff);box-shadow:0 0 13px #b349ff77}
.rb-legendary{background:linear-gradient(90deg,#8c5000,#ff9d00,#ffe27a,#ff9d00);background-size:220% 100%;animation:legendaryFlow 1.8s linear infinite;box-shadow:0 0 12px #ff9d00,0 0 25px #ff9d0077}
.rb-mythic{background:linear-gradient(90deg,#5b0505,#ff1f1f,#ff7777,#ff1f1f,#5b0505);background-size:260% 100%;animation:mythicFlow 1.05s linear infinite;box-shadow:0 0 14px #ff2424,0 0 30px #ff0000aa}
.rb-gray{background:linear-gradient(90deg,#58616a,#b3bbc3)}
.rb-cyan{background:linear-gradient(90deg,#087b88,#65f1ff);box-shadow:0 0 10px #43e6f777}
.rb-blue{background:linear-gradient(90deg,#123d91,#63aaff);box-shadow:0 0 12px #3d86ff77}
.rb-purple{background:linear-gradient(90deg,#6620a0,#cc78ff);box-shadow:0 0 14px #b54cff88}
.rb-pink{background:linear-gradient(90deg,#8f155f,#ff78cf,#ffb2e3);background-size:200% 100%;animation:legendaryFlow 2s linear infinite;box-shadow:0 0 18px #ff4fbc88}
.rb-red{background:linear-gradient(90deg,#5b0505,#ff2323,#ff7777,#ff2323);background-size:240% 100%;animation:mythicFlow 1.25s linear infinite;box-shadow:0 0 20px #ff2525aa}
.rb-gold{background:linear-gradient(90deg,#8d5700,#ffbe00,#fff0a0,#ffbe00,#8d5700);background-size:260% 100%;animation:legendaryFlow .95s linear infinite;box-shadow:0 0 22px #ffc400,0 0 38px #ff9d0088}
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
.cube-gray{background:linear-gradient(145deg,#7b8792,#303840);border-color:#aeb7c0;box-shadow:inset 0 3px 2px #ffffff35,inset 0 -16px 24px #0008,0 0 18px #96a1aa55,0 16px 22px #0008}
.cube-cyan{background:linear-gradient(145deg,#5eefff,#087580);border-color:#9af8ff;box-shadow:inset 0 3px 2px #ffffff55,inset 0 -16px 24px #003b42aa,0 0 24px #48eaff99,0 16px 22px #0008}
.cube-blue{background:linear-gradient(145deg,#559cff,#123b86);border-color:#8cbdff;box-shadow:inset 0 3px 2px #ffffff50,inset 0 -16px 24px #001a4aaa,0 0 27px #3985ff99,0 16px 22px #0008}
.cube-purple{background:linear-gradient(145deg,#c060ff,#5a178a);border-color:#d391ff;box-shadow:inset 0 3px 2px #ffffff45,inset 0 -16px 24px #25003daa,0 0 30px #a84cffaa,0 16px 22px #0008}
.cube-pink{background:linear-gradient(145deg,#ff77d2,#9d176d);border-color:#ffb5e8;box-shadow:inset 0 3px 2px #ffffff55,inset 0 -16px 24px #47002faa,0 0 34px #ff4fbcaa,0 16px 22px #0008;animation:pinkCube 1.35s ease-in-out infinite}
.cube-red{background:linear-gradient(145deg,#ff4a4a,#a60000 55%,#360000);border-color:#ffb0b0;box-shadow:inset 0 3px 2px #ffffff70,inset 0 -16px 24px #4a0000bb,0 0 38px #ff2020dd,0 0 62px #ff000099,0 16px 22px #0008;animation:redCube .8s ease-in-out infinite;overflow:visible}
.cube-red:after{content:"⚡";position:absolute;z-index:3;left:50%;top:50%;font-size:25px;color:#fff;opacity:0;transform:translate(-50%,-50%) rotate(-18deg) scale(.45);text-shadow:-28px 15px 0 #ff3b3b,28px -15px 0 #fff,18px 25px 0 #ff1d1d;animation:redLightning 1.15s steps(1,end) infinite;pointer-events:none}
.cube-gold{background:linear-gradient(145deg,#fff29a,#ffbf00 45%,#9a5600);border-color:#fff4bd;box-shadow:inset 0 3px 2px #ffffffaa,inset 0 -16px 24px #7d3e00aa,0 0 42px #ffc400ee,0 0 78px #ff9d0099,0 16px 22px #0008;animation:goldCube .7s ease-in-out infinite;overflow:visible}
.cube-gold:after{content:"✦";position:absolute;z-index:3;left:50%;top:50%;font-size:24px;color:#fff9c9;text-shadow:-34px -18px 0 #fff,34px 18px 0 #ffd54a,28px -28px 0 #fff7b0,-25px 30px 0 #ffbf00;animation:goldSpark .95s ease-in-out infinite;pointer-events:none}
@keyframes pinkCube{0%,100%{filter:brightness(1)}50%{filter:brightness(1.28)}}
@keyframes redCube{0%,100%{filter:brightness(1)}45%{filter:brightness(1.5)}52%{filter:brightness(2)}58%{filter:brightness(1.2)}}
@keyframes redLightning{0%,18%,24%,57%,63%,100%{opacity:0}19%,22%,58%,61%{opacity:1;transform:translate(-50%,-50%) rotate(-18deg) scale(1.08)}20%,60%{opacity:.35;transform:translate(-46%,-54%) rotate(9deg) scale(.82)}}
@keyframes goldCube{0%,100%{filter:brightness(1);transform:perspective(180px) rotateX(7deg) rotateY(-8deg) scale(1)}50%{filter:brightness(1.35);transform:perspective(180px) rotateX(4deg) rotateY(-5deg) scale(1.045)}}
@keyframes goldSpark{0%,100%{opacity:.35;transform:translate(-50%,-50%) rotate(0deg) scale(.75)}50%{opacity:1;transform:translate(-50%,-50%) rotate(20deg) scale(1.2)}}
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
.spin-stats{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:12px 0}.spin-stat{background:#111418;border:1px solid #24282d;border-radius:15px;padding:11px}.spin-stat .price{font-size:17px}@media(max-width:430px){.spin-stats{grid-template-columns:repeat(2,1fr)}}
.farm-scene{position:relative;height:220px;border-radius:24px;overflow:hidden;margin:12px 0;background:linear-gradient(180deg,#091827 0%,#102431 58%,#0a0d0f 58%,#111 100%);border:1px solid #26333d;box-shadow:inset 0 1px #ffffff12,0 18px 42px #0008}
.farm-sky{position:absolute;inset:0 0 42% 0;background:radial-gradient(circle at 72% 22%,#63d9ff22 0 16%,transparent 36%),linear-gradient(180deg,#07121f,#132c38)}
.farm-ground{position:absolute;left:0;right:0;bottom:0;height:42%;background:linear-gradient(180deg,#262a2b,#111415)}
.farm-core{position:absolute;left:50%;bottom:38px;width:112px;height:82px;transform:translateX(-50%);border-radius:18px 18px 8px 8px;background:linear-gradient(145deg,#313940,#151a1f);border:2px solid #4e5b65;box-shadow:0 0 24px #5fd9ff22}
.farm-core:before{content:"";position:absolute;left:18px;right:18px;top:18px;height:20px;border-radius:7px;background:#173544;border:1px solid #4edfff;box-shadow:0 0 18px #43d9ff55}
.farm-conveyor{position:absolute;left:5%;right:5%;bottom:24px;height:18px;border-radius:8px;background:repeating-linear-gradient(90deg,#30373c 0 20px,#171b1e 20px 38px);border:1px solid #4a5258;animation:farmMove 1.4s linear infinite}
.farm-tower{position:absolute;bottom:45px;width:38px;height:92px;background:linear-gradient(90deg,#1b2024,#3b454c,#171b1f);border:1px solid #56616a;border-radius:8px 8px 3px 3px}
.farm-tower.left{left:12%}.farm-tower.right{right:12%}.farm-tower:before{content:"";position:absolute;left:8px;right:8px;top:10px;height:28px;border-radius:5px;background:#133d46;box-shadow:0 0 15px #42e5ff66}
.farm-drone{position:absolute;top:42px;left:14%;font-size:28px;animation:farmDrone 4.2s ease-in-out infinite}.farm-crate{position:absolute;right:17%;bottom:44px;font-size:34px;filter:drop-shadow(0 8px 8px #000)}
.farm-scene.stage-1 .farm-tower,.farm-scene.stage-1 .farm-drone{display:none}.farm-scene.stage-2 .farm-tower.right,.farm-scene.stage-2 .farm-drone{display:none}.farm-scene.stage-3 .farm-drone{display:none}
.farm-scene.stage-4 .farm-core,.farm-scene.stage-5 .farm-core{box-shadow:0 0 38px #6de9ff66}.farm-scene.stage-5{background:linear-gradient(180deg,#06131e,#143b42 58%,#0a0d0f 58%,#111)}
@keyframes farmMove{to{background-position:38px 0}}@keyframes farmDrone{0%,100%{transform:translate(0,0)}50%{transform:translate(150px,18px)}}
.farm-level-badge{position:absolute;left:12px;top:12px;z-index:4;background:#0a0d0fcc;border:1px solid #4edfff55;border-radius:14px;padding:8px 10px;font-size:12px;font-weight:950;color:#7feaff}
.farm-metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}.farm-metric{background:#111418;border:1px solid #272d33;border-radius:16px;padding:11px}.farm-metric b{display:block;font-size:17px;margin-top:3px}
.farm-actions{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:10px 0}.farm-actions button{width:100%}
.farm-inventory{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}.farm-item{background:#111418;border:1px solid #272d33;border-radius:18px;padding:11px;min-width:0}.farm-item-head{display:flex;gap:9px;align-items:center}.farm-item-icon{width:45px;height:45px;flex:0 0 45px;display:grid;place-items:center;font-size:25px;border-radius:13px;background:#20262b;border:1px solid #343d44}.farm-item-name{font-size:12px;font-weight:900;line-height:1.15}.farm-item-meta{font-size:10px;color:#9ca4ac;margin-top:5px}.farm-item button{width:100%;margin-top:8px;padding:8px;font-size:11px}
.farm-tier-chances{display:flex;gap:6px;overflow-x:auto;margin:10px 0 14px}.farm-chance{flex:0 0 auto;border-radius:12px;padding:7px 9px;background:#12161a;border:1px solid #2a3036;font-size:10px}
.farm-activity{background:linear-gradient(135deg,#10191c,#132c25);border:1px solid #245c45;border-radius:18px;padding:13px;margin:12px 0}.farm-activity b{color:#6df5b0}
.farm-withdraw{background:#111418;border:1px solid #2b3036;border-radius:18px;padding:13px;margin-top:12px}
.farm-modules{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin:10px 0 17px}
.farm-module{border:1px solid #34414a;border-radius:17px;padding:11px;background:linear-gradient(145deg,#172027,#0e1217)}
.farm-module-header{display:flex;gap:7px;align-items:center;font-size:13px;font-weight:900}
.farm-module-icon{font-size:23px}
.farm-module-desc{font-size:11px;color:#a8b3ba;line-height:1.4;min-height:46px;margin:9px 0}
.farm-module-progress{height:5px;border-radius:9px;background:#29333a;overflow:hidden;margin:10px 0}
.farm-module-progress span{display:block;height:100%;background:linear-gradient(90deg,#16abac,#c4f9ff)}
.farm-module button{width:100%;font-size:11px;padding:9px 4px}
@media(max-width:520px){.farm-modules{grid-template-columns:1fr}.farm-module-desc{min-height:0}}
@media(max-width:390px){.farm-metrics{grid-template-columns:1fr 1fr}.farm-inventory{grid-template-columns:1fr}.farm-actions{grid-template-columns:1fr}}
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
.drop-fx.red{background:radial-gradient(circle at 50% 40%,#7a090999,#000e 58%)}.drop-fx.red .drop-card{border-color:#ff3131;box-shadow:0 0 90px #ff2020aa,0 0 150px #a8000077;animation:dropPop .7s cubic-bezier(.2,1.35,.35,1) forwards,mythicPulse .65s ease-in-out 4}.drop-fx.red .drop-card:after{content:"⚡";position:absolute;left:12%;top:14%;font-size:64px;color:#fff;z-index:1;text-shadow:210px 35px 0 #ff3434,110px 180px 0 #fff;animation:dropLightning .8s steps(1,end) infinite;opacity:0}
.drop-fx.gold{background:radial-gradient(circle at 50% 40%,#8a650099,#000e 60%)}.drop-fx.gold .drop-card{border-color:#ffd43b;box-shadow:0 0 100px #ffc400cc,0 0 180px #ff8c0077;animation:dropPop .65s cubic-bezier(.2,1.45,.3,1) forwards,goldDropPulse .55s ease-in-out 5}.drop-fx.gold .drop-card:before{content:"";position:absolute;inset:-70%;background:conic-gradient(from 0deg,transparent,#fff29a77,transparent,#ffbe0088,transparent);animation:mythicSpin 1.25s linear infinite}.drop-fx.gold .drop-card:after{content:"✦";position:absolute;left:8%;top:8%;font-size:72px;color:#fff7bd;z-index:1;text-shadow:230px 30px 0 #ffd84a,105px 190px 0 #fff,210px 175px 0 #ffbf00;animation:goldDropStars .75s ease-in-out infinite}
@keyframes goldDropPulse{0%,100%{filter:brightness(1);transform:scale(1)}50%{filter:brightness(1.5);transform:scale(1.065)}}@keyframes goldDropStars{0%,100%{opacity:.35;transform:rotate(0deg) scale(.8)}50%{opacity:1;transform:rotate(20deg) scale(1.15)}}
.drop-content{position:relative;z-index:2}.spark{position:absolute;width:7px;height:7px;border-radius:50%;background:#fff;box-shadow:0 0 14px currentColor;animation:sparkFly 1.2s ease-out forwards}
@keyframes fxFade{from{opacity:0}to{opacity:1}}@keyframes dropPop{to{transform:scale(1)}}@keyframes legendaryPulse{0%,100%{transform:scale(1)}50%{transform:scale(1.045)}}@keyframes mythicPulse{0%,100%{filter:brightness(1);transform:scale(1)}50%{filter:brightness(1.55);transform:scale(1.06)}}@keyframes mythicSpin{to{transform:rotate(360deg)}}@keyframes sparkFly{from{transform:translate(0,0) scale(1);opacity:1}to{transform:translate(var(--x),var(--y)) scale(0);opacity:0}}

/* admin */
.admin-nav{display:flex;gap:7px;overflow-x:auto;padding:2px 0 10px;margin-bottom:8px;scrollbar-width:none}.admin-nav::-webkit-scrollbar{display:none}
.admin-nav button{white-space:nowrap;background:#181c21;color:#9ea5ad;border:1px solid #292f36;padding:9px 11px}.admin-nav button.active{background:#2b230d;color:#ffd056;border-color:#63501c}
.metrics{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}.metric{padding:14px;border:1px solid #282d33;background:#121519;border-radius:17px}.metric b{display:block;font-size:23px;margin-top:4px}
.adminline{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.adminline>*{flex:1;min-width:120px}.admin-card{background:#111419;border:1px solid #252b31;border-radius:18px;padding:14px;margin:10px 0}
.mini{font-size:11px;color:#8e959d}.ok{color:#68d391}.warn{color:#ffd166}

@media(max-width:390px){.grid,.sticker-grid{grid-template-columns:1fr 1fr}.spin-stats{grid-template-columns:1fr 1fr}.metrics{grid-template-columns:1fr 1fr}h1{font-size:25px}.sticker{min-height:122px;padding:12px}.sticker-icon{font-size:40px}}

/* Rustic Metro Farm 2.0 — wood, countryside, warm brass rather than futuristic factory */
.farm-ui{--farm-gold:#f2bf50;--farm-sage:#86c697;--farm-edge:#4a3a28;color:#f7f4ec}
.farm-ui .farm-lead{display:flex;align-items:center;justify-content:space-between;gap:14px;margin:12px 2px 14px}
.farm-ui .farm-lead h1{font-size:27px;line-height:1.05;margin:3px 0 5px}
.farm-ui .farm-lead .muted{font-size:12px;line-height:1.5}
.farm-ui .farm-eyebrow{color:#edc779;font-size:11px;font-weight:900;letter-spacing:1.7px}
.farm-ui .farm-lead-level{flex:0 0 auto;background:#2b241a;border:1px solid #80663d;color:#f5d899;border-radius:13px;padding:9px 11px;font-weight:950;text-align:center;font-size:13px}
.farm-landscape{position:relative;isolation:isolate;border:1px solid #6c5731;border-radius:24px;overflow:hidden;background:#403322;box-shadow:0 20px 55px #0007,0 0 0 2px #d7a34a12;min-height:212px}
.farm-landscape svg{width:100%;height:auto;min-height:214px;display:block;aspect-ratio:790/344;object-fit:cover}
.farm-landscape:after{content:"";pointer-events:none;position:absolute;inset:0;box-shadow:inset 0 -48px 45px #150f0b8a}
.farm-landscape .farm-landscape-title{position:absolute;bottom:11px;left:14px;right:14px;display:flex;align-items:center;justify-content:space-between;gap:12px;z-index:2;color:#fff2d5;text-shadow:0 2px 9px #000;font-weight:900;font-size:12px}
.farm-landscape .farm-stage-pill{border:1px solid #f0c8797d;background:#20170bc4;border-radius:20px;padding:7px 10px}
.farm-overview{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin:12px 0}
.farm-wallet{background:linear-gradient(160deg,#252016,#131614);border:1px solid #4d4534;border-radius:16px;padding:10px 9px;min-width:0;box-shadow:inset 0 1px #f0ce7620}
.farm-wallet .farm-wallet-label{font-size:9px;letter-spacing:.5px;font-weight:900;color:#aaa99e;white-space:nowrap}
.farm-wallet .farm-wallet-value{display:flex;align-items:center;gap:5px;margin-top:7px;min-width:0;font-size:20px;font-weight:1000;white-space:nowrap}
.farm-wallet .farm-wallet-value svg{flex:0 0 31px;width:31px;height:31px;filter:drop-shadow(0 3px 3px #0009)}
.farm-wallet .farm-wallet-value span{min-width:0;overflow:hidden;text-overflow:ellipsis}
.farm-wallet.shr{background:linear-gradient(160deg,#24312a,#121815);border-color:#385543}
.farm-wallet.uc{background:linear-gradient(160deg,#20303c,#11171e);border-color:#365466}
.farm-status{background:#171a14;border:1px solid #425039;border-radius:15px;padding:12px;margin:10px 0;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
.farm-status span{color:#a9aca0;font-size:11px}.farm-status b{display:block;color:#f3ecdb;margin-top:4px;font-size:14px}
.farm-status-bar{grid-column:1 / -1;height:7px;border-radius:20px;background:#33362d;overflow:hidden}
.farm-status-bar span{display:block;height:100%;background:linear-gradient(90deg,#75c07e,#f9c75b);border-radius:20px}
.farm-primary-actions{display:grid;grid-template-columns:1.2fr 1fr;gap:9px;margin:12px 0}
.farm-primary-actions button{font-size:12px;padding:12px 8px;line-height:1.3;min-width:0}
.farm-primary-actions .farm-primary{border:1px solid #ffe1a0;background:linear-gradient(160deg,#ffe493,#f3b929 55%,#d68d1c);color:#34210a;font-weight:1000;box-shadow:0 5px 16px #e39f3033}
.farm-section{background:#171b17;border:1px solid #3c473a;border-radius:20px;padding:13px;margin:13px 0}
.farm-section.wood{background:linear-gradient(150deg,#2c251c,#191914 70%);border-color:#5b4832}
.farm-section-head{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:9px}
.farm-section h3{margin:0;font-size:16px}
.farm-aux{font-size:11px;color:#aaa99f;line-height:1.55}
.farm-mini-stats{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0}
.farm-mini-stats span{border:1px solid #5d5542;border-radius:10px;background:#141713;padding:6px 8px;font-size:10px;color:#d0c9b8}
.farm-ui .farm-modules{grid-template-columns:repeat(3,minmax(0,1fr));margin:13px 0 0}
.farm-ui .farm-module{background:linear-gradient(145deg,#31271b,#181a16);border:1px solid #675235;border-radius:15px;padding:11px;min-width:0}
.farm-ui .farm-module-desc{min-height:63px}
.farm-ui .farm-module button{font-size:10px;line-height:1.3;white-space:normal}
.farm-ui .farm-module-progress span{background:linear-gradient(90deg,#6bba75,#eec365)}
.farm-currency-inline{display:inline-flex;align-items:center;gap:4px;font-weight:900;color:#f6d77e;white-space:nowrap}
.farm-currency-inline svg{height:21px;width:21px;display:inline-block;vertical-align:middle;flex:0 0 21px}
.farm-uc-targets{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin:12px 0}
.farm-uc-target{border:1px solid #3a4f56;background:#142025;border-radius:13px;padding:10px}
.farm-uc-target b{color:#c4eaff;font-size:14px;display:block}
.farm-uc-target span{font-size:10px;line-height:1.4;display:block;margin-top:4px;color:#a7bec5}
.farm-uc-target.farm-uc-complete{border-color:#678851;background:#1d2a1e}
.farm-uc-target.farm-uc-complete b{color:#9be1a4}
.farm-ui .farm-withdraw{background:linear-gradient(135deg,#1b2526,#12191a);border-color:#466266}
.farm-ui .farm-withdraw .farm-section-head h3{display:flex;gap:9px;align-items:center}.farm-ui .farm-withdraw .farm-section-head h3 svg{height:32px;width:32px;flex:0 0 32px}
.farm-ui .farm-withdraw .row{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.farm-ui .farm-withdraw .row>*{min-width:0}
.farm-ui .farm-activity{background:linear-gradient(135deg,#243221,#151c16);border-color:#4c6b41}
.farm-ui .farm-inventory{grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}
.farm-ui .farm-item{background:linear-gradient(145deg,#222821,#141816);border-color:#4b5145;border-radius:15px;padding:10px}
.farm-ui .farm-item .farm-item-head{align-items:flex-start;gap:7px}
.farm-ui .farm-item .farm-item-name{font-size:12px;line-height:1.3}
.farm-ui .farm-item .farm-item-meta{line-height:1.5}
.farm-ui .farm-item .farm-item-icon{border:0;background:transparent;width:80px;flex:0 0 80px;height:76px;padding:0}
.farm-ui .farm-item button{margin-top:8px}
.farm-collectible{width:86px;height:84px;position:relative;display:grid;place-items:center;isolation:isolate;perspective:300px}
.farm-collectible:before{content:"";position:absolute;left:10px;right:10px;top:10px;bottom:12px;border-radius:16px;background:linear-gradient(135deg,#516047,#29362e 48%,#111816);border:1px solid #87958258;box-shadow:inset 2px 2px 8px #fff2,5px 11px 7px #0009;transform:rotateX(13deg) rotateY(-14deg) rotateZ(-6deg)}
.farm-collectible:after{content:"";position:absolute;z-index:-1;bottom:4px;left:23px;width:49px;height:12px;border-radius:50%;background:#0009;filter:blur(5px)}
.farm-collectible-icon{z-index:1;position:relative;line-height:1;font-size:38px;transform:rotate(-8deg) translateY(-3px);filter:drop-shadow(3px 7px 1px #0009) drop-shadow(-2px -2px 1px #fff5)}
.farm-collectible-shine{position:absolute;z-index:2;top:16px;left:19px;width:45px;height:5px;border-radius:50%;transform:rotate(-25deg);background:#ffffff40;filter:blur(2px)}
.farm-collectible[data-tier="CYAN"]:before{background:linear-gradient(135deg,#31777f,#122e32,#10151b);border-color:#47dae6}
.farm-collectible[data-tier="BLUE"]:before{background:linear-gradient(135deg,#2b5794,#142241,#0c1321);border-color:#4a9fff}
.farm-collectible[data-tier="PURPLE"]:before{background:linear-gradient(135deg,#70418b,#2c1b45,#151222);border-color:#c177ff}
.farm-collectible[data-tier="PINK"]:before{background:linear-gradient(135deg,#b34582,#452039,#1f111d);border-color:#fc77c5}
.farm-collectible[data-tier="RED"]:before{background:linear-gradient(135deg,#c15e3e,#47221a,#20130c);border-color:#ff7d5f}
.farm-collectible[data-tier="GOLD"]:before{background:linear-gradient(135deg,#ffdf6b,#946018,#36230e);border-color:#ffe68a}
.farm-catalog-btn{border:1px solid #816535;background:linear-gradient(135deg,#312718,#1a1b15);color:#ffe29f;font-size:12px;font-weight:900;padding:9px 12px;border-radius:11px}
.farm-filterbar{display:flex;gap:7px;overflow-x:auto;margin:10px 0;padding-bottom:5px;scrollbar-width:none}
.farm-filterbar button{flex:0 0 auto;background:#181c18;border:1px solid #465143;color:#c6c7bb;border-radius:20px;padding:8px 10px;font-size:11px}
.farm-filterbar button.active{background:#a77c2a;color:#fff5cf;border-color:#ffd876}
.farm-catalog-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}
.farm-catalog-card{min-width:0;display:flex;flex-direction:column;align-items:center;text-align:center;background:#141a18;border:1px solid #394639;border-radius:16px;padding:9px 7px}
.farm-catalog-card .farm-collectible{width:94px;height:92px;transform:scale(1.02);margin:0 auto 3px}
.farm-catalog-card h4{font-size:11px;min-height:28px;margin:5px 0 2px;line-height:1.3}
.farm-catalog-card p{margin:0;font-size:10px;color:#b8b8ab}
.farm-catalog-card .farm-currency-inline{font-size:13px;margin:6px 0 4px}
.farm-catalog-card .farm-chance-text{font-size:10px;color:#abb7a9}
.farm-rarity-label{display:inline-block;font-size:9px;font-weight:900;padding:4px 7px;border-radius:10px;border:1px solid #646e5a;color:#c8d2be;background:#1c281b}
.farm-rarity-label.CYAN{color:#66dfed;border-color:#298594;background:#0f3236}
.farm-rarity-label.BLUE{color:#7bb8ff;border-color:#345c9c;background:#152742}
.farm-rarity-label.PURPLE{color:#c38eff;border-color:#72518f;background:#2c2040}
.farm-rarity-label.PINK{color:#ff9ad4;border-color:#a54886;background:#45243a}
.farm-rarity-label.RED{color:#ff8d75;border-color:#a54637;background:#451f1e}
.farm-rarity-label.GOLD{color:#ffe17b;border-color:#a97c2d;background:#40300f}
.farm-ui .farm-tier-chances{flex-wrap:wrap;overflow:visible;margin:10px 0}
.farm-ui .farm-chance{border-color:#675536;background:#222118;color:#e8dab7}
@media(min-width:620px){.farm-ui .farm-catalog-grid{grid-template-columns:repeat(4,minmax(0,1fr))}}
@media(max-width:520px){.farm-ui .farm-modules{grid-template-columns:1fr}.farm-ui .farm-module-desc{min-height:0}.farm-ui .farm-overview{grid-template-columns:repeat(3,minmax(0,1fr))}.farm-ui .farm-wallet{padding:9px 6px}.farm-ui .farm-wallet-value{font-size:17px;gap:3px}.farm-ui .farm-wallet .farm-wallet-label{font-size:9px}.farm-ui .farm-wallet-value svg{height:26px;width:26px;flex-basis:26px}}
@media(max-width:370px){.farm-ui .farm-item .farm-item-icon{width:60px;flex-basis:60px}.farm-ui .farm-item .farm-collectible{transform:scale(.78);transform-origin:top left}.farm-ui .farm-wallet-value{font-size:15px}.farm-ui .farm-uc-targets{grid-template-columns:1fr}}


.farm-collectible-icon{display:grid;place-items:center;width:86px;height:80px}
.farm-collectible .farm-object-svg{width:83px;height:83px;display:block;filter:drop-shadow(2px 5px 2px #0007) drop-shadow(-1px -1px 1px #ffffff55)}


/* SHREKSICH PREMIUM NAVY — responsive redesign based on approved layout */
:root{--bg:#050d19;--card:#0e1a2b;--line:#24374d;--gold:#ffc947;--muted:#91a7be;--blue:#62b9ff}
html,body{background:#050d19;color:#ecf5ff}
body:before{background:radial-gradient(ellipse at 10% 3%,#15406b69,transparent 46%),radial-gradient(ellipse at 85% 34%,#1b28495d,transparent 46%);z-index:0}
.wrap{max-width:800px;padding:12px 12px calc(115px + env(safe-area-inset-bottom));}
.top{margin:5px 2px 15px;padding:9px 2px}
.brand{font-size:20px;letter-spacing:.3px;text-shadow:0 2px 12px #0009}.brand b{color:#ffd26b}
.pill{background:#0b2036;border-color:#274765;color:#8bcfff}
.hero{background:linear-gradient(125deg,#112238,#101823 62%,#382b14);border-color:#405577}
.card,.order{background:linear-gradient(145deg,#122238,#0c1624);border-color:#28415c;box-shadow:0 9px 27px #0005}
.secondary{background:#17263a;border:1px solid #30455c;color:#e4f2ff}
.buy{background:linear-gradient(140deg,#ffe39a,#f5bd35 58%,#d99918);color:#221600}
input,textarea,select{background:#0a1625;border-color:#2c455e}
.nav{bottom:max(8px,env(safe-area-inset-bottom));max-width:760px;width:calc(100% - 16px);border-radius:19px;background:#081523f5;border:1px solid #2a455c;box-shadow:0 -8px 36px #020a17df,0 0 18px #286ab222;padding:6px 4px;gap:0}
.nav button{display:flex;flex:1;flex-direction:column;align-items:center;justify-content:center;min-width:0;gap:4px;border-radius:13px;color:#8498ac;font-size:10px;padding:8px 0 6px;white-space:nowrap}
.nav button.active{background:linear-gradient(180deg,#332912a8,#1d2541);color:#ffda71}
.nav-ico{font-size:22px;line-height:1;display:block;font-weight:900;color:#97b8d3}
.nav button.active .nav-ico{color:#ffca4d;text-shadow:0 0 16px #ffc94d9e}
.wins{background:#071727;border-color:#2e4a68;border-radius:13px;box-shadow:inset 0 1px #ffffff12;margin:0 0 16px}
.wins:before{background:linear-gradient(135deg,#1cbd8d,#079477);color:#fff;padding:0 9px}
.shx-home{display:block}
.shx-profile{position:relative;overflow:hidden;border:1px solid #3c6281;border-radius:23px;padding:16px 16px 12px;background:radial-gradient(ellipse at 90% 0,#173657,#091625 67%);box-shadow:inset 0 1px #bce8ff22,0 14px 45px #0008}
.shx-profile:before{content:"";pointer-events:none;position:absolute;inset:0;background:linear-gradient(130deg,#b5e7ff09,transparent 44%,#ffc84c05)}
.shx-profile-top{display:flex;align-items:center;gap:11px;position:relative}
.shx-avatar{border:2px solid #c2a159;flex:0 0 59px;width:59px;height:59px;border-radius:50%;display:grid;place-items:center;background:radial-gradient(circle at 38% 20%,#3e6176,#1a263a 60%,#080d16);box-shadow:0 0 0 3px #071629,0 6px 15px #0007;color:#ffe19c;font-size:28px;font-weight:950}
.shx-username{font-size:17px;font-weight:950;color:#f2f7ff;overflow-wrap:anywhere}
.shx-user-sub{font-size:10px;color:#8da6bc;margin-top:6px}
.shx-profile-quick{margin-left:auto;width:37px;height:37px;flex:0 0 37px;border-radius:12px;border:1px solid #365779;background:#0e2238;color:#e7f6ff;padding:7px;font-size:20px}
.shx-wallets{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:0;align-items:stretch;margin-top:15px;padding-top:13px;border-top:1px solid #2b4861;position:relative}
.shx-wallet{min-width:0;display:flex;align-items:center;gap:7px;padding:2px 6px}
.shx-wallet:not(:last-child){border-right:1px solid #244663}
.shx-wallet svg{height:34px;width:34px;flex:0 0 34px;filter:drop-shadow(0 3px 5px #000b)}
.shx-wallet-count{min-width:0;font-size:16px;font-weight:950;line-height:1.1;color:#fff;overflow:hidden;text-overflow:ellipsis}
.shx-wallet-name{font-size:9px;line-height:1.1;margin-top:5px;color:#88a5bd}
.shx-star{font-size:27px;color:#ffb833;line-height:1;filter:drop-shadow(0 3px 5px #000a);flex:0 0 27px}
.shx-caption{color:#a0b5cd;font-size:11px;margin:13px 3px 9px}
.shx-tiles{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin:14px 0}
.shx-tile{position:relative;text-align:left;padding:14px 13px;min-height:125px;display:flex;align-items:flex-end;overflow:hidden;border-radius:20px;border:1px solid #314b6b;color:#e8f2ff;box-shadow:inset 0 1px #ffffff22,0 12px 20px #0007;transition:transform .15s}
.shx-tile:active{transform:scale(.97)}
.shx-tile:before{content:"";position:absolute;width:120px;height:120px;right:-28px;top:-40px;border-radius:50%;background:radial-gradient(circle,#91beff55,transparent 69%)}
.shx-tile .tile-visual{position:absolute;right:11px;top:6px;width:79px;height:79px;display:grid;place-items:center;transform:rotate(-8deg);filter:drop-shadow(4px 10px 6px #0009)}
.shx-tile .tile-visual svg{height:74px;width:74px;stroke-width:1.7;stroke-linejoin:round}
.shx-tile .tile-copy{position:relative;z-index:2;display:flex;flex-direction:column;gap:5px;max-width:90%}
.shx-tile .tile-copy b{font-size:16px;letter-spacing:.1px;line-height:1.1;text-shadow:0 2px 8px #000}
.shx-tile .tile-copy small{font-size:10px;color:#ccdae9;line-height:1.3}
.shx-tile .tile-tag{position:absolute;right:7px;top:8px;border-radius:7px;padding:4px 5px;background:#bb282c;color:white;font-size:8px;font-weight:900;z-index:3}
.shx-tile.t-catalog{background:linear-gradient(145deg,#152e49,#0a1629 63%,#634322);border-color:#54739a}
.shx-tile.t-cases{background:linear-gradient(145deg,#121d40,#0b1331 62%,#3e1d66);border-color:#58469a}
.shx-tile.t-spin{background:linear-gradient(145deg,#182a42,#0b152b 67%,#223d71);border-color:#416da8}
.shx-tile.t-farm{background:linear-gradient(145deg,#1e382f,#091d22 60%,#77521d);border-color:#87703d}
.shx-tile.t-tasks,.shx-tile.t-promo{background:linear-gradient(145deg,#112f3e,#0a192d);min-height:98px}
.shx-tile.t-uc,.shx-tile.t-help{background:linear-gradient(145deg,#10263e,#071424);min-height:98px}
.shx-tile.t-tasks .tile-visual,.shx-tile.t-promo .tile-visual,.shx-tile.t-uc .tile-visual,.shx-tile.t-help .tile-visual{width:58px;height:58px}
.shx-tile.t-tasks .tile-visual svg,.shx-tile.t-promo .tile-visual svg,.shx-tile.t-uc .tile-visual svg,.shx-tile.t-help .tile-visual svg{width:51px;height:51px}
.shx-live{padding:14px;background:#091826;border:1px solid #2c455e;border-radius:19px;margin:14px 0 18px}
.shx-live-head{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:11px;font-size:14px;font-weight:950}
.shx-live-head small{font-size:10px;color:#9cafc4;font-weight:500}
.shx-online{display:inline-block;width:8px;height:8px;border-radius:50%;background:#16d585;box-shadow:0 0 12px #16d585;margin-right:6px}
.shx-live-row{display:flex;gap:9px;overflow-x:auto;scrollbar-width:none;padding-bottom:3px}
.shx-live-card{min-width:155px;max-width:170px;flex:0 0 155px;border:1px solid #325273;background:linear-gradient(135deg,#0f233b,#101723);border-radius:14px;padding:10px}
.shx-live-card[data-tier="GOLD"]{border-color:#ab873c;background:linear-gradient(135deg,#392a16,#161b2c)}
.shx-live-card[data-tier="RED"],.shx-live-card[data-tier="MYTHIC"]{border-color:#ac495c;background:linear-gradient(135deg,#331728,#171529)}
.shx-live-card[data-tier="PURPLE"],.shx-live-card[data-tier="PINK"]{border-color:#7950ad}
.shx-live-title{font-size:10px;color:#adbed2;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.shx-live-name{font-weight:900;font-size:11px;margin:7px 0;line-height:1.35;min-height:30px}
.shx-live-rarity{font-size:10px;color:#ebc16c}
.shx-page-title{padding:9px 2px 12px;display:flex;align-items:center;gap:12px}
.shx-page-title h1{font-size:22px;margin:0}
.shx-back{background:#0d2036;border:1px solid #31577a;color:#dcecff;font-size:12px}
.shx-panel{background:linear-gradient(135deg,#122338,#0a1626);border:1px solid #304c69;border-radius:18px;padding:14px;margin:12px 0}
.shx-panel h3{margin:0 0 10px}
.shx-profile-actions{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
.shx-profile-actions button{padding:14px;background:linear-gradient(145deg,#162e49,#101a2a);border:1px solid #33516d;color:#d9edff;min-height:72px;text-align:left}
.shx-farm-catalog .farm-catalog-grid{grid-template-columns:repeat(2,minmax(0,1fr))}
.shx-farm-catalog .farm-catalog-card{background:linear-gradient(145deg,#101f33,#0a1629);border:1px solid #345478;box-shadow:0 6px 22px #0007}
.shx-farm-catalog .farm-catalog-card[data-tier="CYAN"]{border-color:#2484a8}
.shx-farm-catalog .farm-catalog-card[data-tier="BLUE"]{border-color:#317dcc}
.shx-farm-catalog .farm-catalog-card[data-tier="PURPLE"]{border-color:#8b48c7}
.shx-farm-catalog .farm-catalog-card[data-tier="PINK"]{border-color:#bd548c}
.shx-farm-catalog .farm-catalog-card[data-tier="RED"]{border-color:#ab4941}
.shx-farm-catalog .farm-catalog-card[data-tier="GOLD"]{border-color:#caa046}
.shx-farm-catalog .farm-filterbar{gap:7px;scrollbar-width:none}
.shx-farm-catalog .farm-filterbar button{background:#0b1b2e;border-color:#304c6d;color:#b1c5d9}
.shx-farm-catalog .farm-filterbar button.active{background:linear-gradient(145deg,#eec45a,#b78426);border-color:#ffe79f;color:#1a190d}
.farm-ui .farm-lead-level{border-color:#8c7137;background:#1b2531}
.farm-ui .farm-lead h1{color:#fff5db}
.farm-ui .farm-overview{gap:7px}
.farm-ui .farm-wallet{background:linear-gradient(140deg,#172b3e,#0f1a28);border-color:#345574}
.farm-ui .farm-wallet.uc{background:linear-gradient(145deg,#132f3b,#101c2a)}
.farm-ui .farm-status{background:linear-gradient(150deg,#12263b,#0d1827);border-color:#416080}
.farm-ui .farm-section{background:linear-gradient(135deg,#121f2d,#0b1825);border-color:#38536c}
.farm-ui .farm-section.wood{background:linear-gradient(140deg,#1d2a2d,#0e1b23 62%,#3d301e);border-color:#62523a}
.farm-ui .farm-module{background:linear-gradient(140deg,#1a3044,#14202a);border-color:#52607a}
.farm-ui .farm-activity{background:linear-gradient(135deg,#17382f,#0c1d22);border-color:#3a826a}
.farm-ui .farm-withdraw{background:linear-gradient(135deg,#172d3d,#0c1b29);border-color:#406c86}
.farm-ui .farm-collectible{filter:drop-shadow(0 3px 7px #000b)}
.farm-ui .farm-catalog-card{border-color:#426480;background:#0b1c2e}
.farm-ui .farm-modules{grid-template-columns:repeat(3,minmax(0,1fr))}
.farm-ui .farm-module-header{font-size:11px;display:block;text-align:center}
.farm-ui .farm-module-icon{display:block;font-size:25px;margin-bottom:6px}
.farm-ui .farm-module-desc{font-size:10px;min-height:62px;text-align:center}
.farm-ui .farm-module button{font-size:9px;padding:9px 3px}
@media(min-width:620px){.shx-farm-catalog .farm-catalog-grid{grid-template-columns:repeat(4,minmax(0,1fr))}}
@media(max-width:365px){.shx-wallet svg{width:28px;height:28px;flex-basis:28px}.shx-wallet-count{font-size:14px}.shx-wallet-name{font-size:8px}.shx-tile{min-height:115px}.shx-tile .tile-copy b{font-size:14px}.farm-ui .farm-module{padding:7px}.farm-ui .farm-module-desc{font-size:9px}}


/* Standalone circular free roulette */
.roul-page{max-width:590px;margin:0 auto}.roul-hero{text-align:center;background:linear-gradient(145deg,#112b4b,#0c162b 65%,#322210);border-color:#53708e;padding:19px 16px}
.roul-hero h1{font-size:28px}.roul-box{border-radius:25px;padding:18px 13px;background:radial-gradient(circle at 50% 32%,#1c3656,#0b172b 70%);border:1px solid #3d6081;box-shadow:inset 0 1px #ffffff22,0 16px 35px #000a}
.roul-stage{position:relative;aspect-ratio:1;width:min(100%,340px);margin:4px auto 16px;display:grid;place-items:center;isolation:isolate}
.roul-stage:before{content:"";position:absolute;inset:-2%;border-radius:50%;background:repeating-conic-gradient(#f9d987 0 10deg,#85541e 10deg 19deg);box-shadow:0 0 0 4px #4b331e,0 16px 30px #0009,0 0 28px #e6a93b77}
.roul-wheel{position:absolute;inset:4%;border-radius:50%;border:4px solid #fbdc8d;overflow:hidden;box-shadow:inset 0 0 12px #0009;will-change:transform}
.roul-wheel:after{content:"";position:absolute;inset:0;border-radius:50%;pointer-events:none;background:radial-gradient(circle at 27% 17%,#ffffff55,transparent 36%),radial-gradient(circle,#0000 38%,#0009 100%)}
.roul-label{position:absolute;font-size:clamp(9px,2.7vw,12px);font-weight:1000;color:white;text-shadow:0 2px 6px #000,0 0 4px #000;z-index:2;line-height:1.2;text-align:center;white-space:nowrap;transform:translate(-50%,-50%)}
.roul-label small{display:block;font-size:9px;color:#fff5c7}
.roul-hub{position:absolute;inset:35%;z-index:5;border-radius:50%;background:radial-gradient(circle at 36% 26%,#fff4c6,#e8b54f 48%,#9d5b19);border:5px solid #ffecb2;box-shadow:0 3px 15px #000a;display:flex;flex-direction:column;align-items:center;justify-content:center;color:#51330c;font-size:clamp(11px,3.8vw,15px);font-weight:1000}
.roul-hub small{font-size:8px;letter-spacing:.5px}
.roul-pointer{position:absolute;z-index:9;top:-2%;left:50%;transform:translateX(-50%);width:43px;height:55px;background:linear-gradient(110deg,#ffecb1,#eeb135 65%,#a65a19);clip-path:polygon(50% 100%,3% 10%,27% 2%,73% 2%,97% 10%);filter:drop-shadow(0 5px 5px #000)}
.roul-legend{display:flex;gap:6px;flex-wrap:wrap;justify-content:center;margin:5px 0 12px}
.roul-legend span{font-size:10px;font-weight:900;padding:6px 8px;background:#132940;border:1px solid #375577;border-radius:20px}
.roul-legend i{display:inline-block;height:9px;width:9px;vertical-align:middle;border-radius:50%;margin-right:5px}
.roul-stats{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px;margin:12px 0}
.roul-stat{background:#0b2035;border:1px solid #385675;border-radius:13px;padding:9px 5px;text-align:center}.roul-stat small{display:block;color:#a4b8cd;font-size:9px}.roul-stat b{display:block;font-size:20px;color:#ffe29d;margin-top:4px}
.roul-go{width:100%;padding:16px 8px;font-size:15px;background:linear-gradient(130deg,#ffe4a3,#f6b931 60%,#c88b22);box-shadow:0 0 21px #ffb83345;color:#231b0a}
.roul-hint{font-size:11px;color:#abc4dc;text-align:center;line-height:1.5;margin:12px 0 3px}
.roul-result{text-align:center;margin:12px 0 0}
.roul-result:not(:empty){background:#0d2035;border:1px solid #376088;border-radius:15px;padding:15px}
.roul-route{width:100%;margin:10px 0;color:#c4e4ff;background:#102840;border:1px solid #34577b}


/* Roulette v2: smooth inertia, progress, a real skip button and music settings */
.roul-stage.roul-turning:before{box-shadow:0 0 0 4px #76511d,0 16px 35px #000c,0 0 38px #ffd15c8b}
.roul-stage.roul-turning .roul-pointer{animation:roul-needle .18s ease-in-out infinite alternate}
@keyframes roul-needle{from{transform:translateX(-50%) rotate(-4deg)}to{transform:translateX(-50%) rotate(4deg)}}
.roul-options{display:grid;grid-template-columns:1fr 1fr;gap:9px;margin-top:12px}
.roul-option{min-width:0;display:flex;gap:9px;align-items:center;justify-content:flex-start;text-align:left;background:#10243a;border:1px solid #385779;border-radius:13px;padding:10px;font-weight:750;color:#d5eaff;font-size:11px;line-height:1.3;cursor:pointer}
.roul-option input{flex:0 0 auto;width:18px;height:18px;accent-color:#f5c656;margin:0}
.roul-skip-now{width:100%;display:block;margin-top:12px;min-height:46px;background:linear-gradient(140deg,#27476b,#172b45);border:1px solid #6d99bf;color:#d7efff;font-size:13px;box-shadow:0 8px 19px #0005}
.roul-skip-now:disabled{opacity:.6}
.roul-progress{height:7px;background:#172e49;border-radius:12px;border:1px solid #2d4c71;overflow:hidden;margin:12px 0 7px}
.roul-progress i{display:block;width:0;height:100%;background:linear-gradient(90deg,#d99b32,#ffe9a5);border-radius:12px;transition:width .10s linear}
.roul-spin-status{font-size:11px;color:#d8b66c;font-weight:850;min-height:18px;margin-top:8px;text-align:center}
@media(max-width:350px){.roul-options{grid-template-columns:1fr}}
@media(prefers-reduced-motion:reduce){.roul-stage.roul-turning .roul-pointer{animation:none}}


/* The gold center of the wheel is the accessible spin button */
.roul-hub.roul-hub-action{inset:33%;border:5px solid #ffe5a0;padding:6px 3px;color:#51330c;cursor:pointer;touch-action:manipulation;-webkit-appearance:none;appearance:none;transition:transform .16s,box-shadow .16s,filter .16s;box-shadow:0 3px 15px #000a,0 0 0 2px #f5ce6599,0 0 22px #ffd25a7a}
.roul-hub-action:not(:disabled){animation:roul-hub-pulse 2.3s ease-in-out infinite}
.roul-hub-action:not(:disabled):active{transform:scale(.91);animation:none}
.roul-hub-action:focus-visible{outline:3px solid #80caff;outline-offset:4px}
.roul-hub-action:disabled{opacity:1;cursor:default;animation:none;filter:saturate(.74)}
.roul-hub-action.roul-hub-working{box-shadow:0 3px 15px #000b,0 0 0 3px #ffc854,0 0 22px #ffd25a98;filter:none}
.roul-hub-action .roul-hub-title{display:block;font-size:clamp(9px,2.6vw,11px);line-height:1.1;font-weight:1000;letter-spacing:.2px}
.roul-hub-action .roul-hub-main{font-size:clamp(12px,3.8vw,16px);font-weight:1000;line-height:1.15;letter-spacing:-.4px;margin:4px 0 2px}
.roul-hub-action .roul-hub-sub{font-size:clamp(7px,2vw,9px);font-weight:950;letter-spacing:.4px;line-height:1.1}
@keyframes roul-hub-pulse{0%,100%{box-shadow:0 3px 15px #000a,0 0 0 2px #f5ce6599,0 0 17px #ffd25a65}50%{box-shadow:0 4px 17px #000a,0 0 0 4px #ffe191a6,0 0 28px #ffd25ab5}}
@media(prefers-reduced-motion:reduce){.roul-hub-action:not(:disabled){animation:none}}


/* Rarity colors: match the item tier, overriding the old brown/gold farm pills */
.farm-ui .farm-chance{--rr:#a6b6c6;--rb:#2c3b4a;--rd:#102030;display:inline-flex;align-items:center;gap:5px;background:var(--rd)!important;color:var(--rr)!important;border:1px solid var(--rb)!important;box-shadow:0 0 11px color-mix(in srgb,var(--rr) 13%,transparent);font-weight:850;border-radius:22px;padding:9px 12px}
.farm-ui .farm-chance.tier-gray{--rr:#c3ccd6;--rb:#687989;--rd:#202c39}
.farm-ui .farm-chance.tier-cyan{--rr:#76e9f5;--rb:#1985ad;--rd:#102b3c}
.farm-ui .farm-chance.tier-blue{--rr:#82b9ff;--rb:#2767b3;--rd:#102343}
.farm-ui .farm-chance.tier-purple{--rr:#ce9bff;--rb:#7a46aa;--rd:#2b1c43}
.farm-ui .farm-chance.tier-pink{--rr:#ffa1d3;--rb:#ad458c;--rd:#3b1d37}
.farm-ui .farm-chance.tier-red{--rr:#ff9a92;--rb:#aa394b;--rd:#3d1727}
.farm-ui .farm-chance.tier-gold{--rr:#ffe081;--rb:#bd872c;--rd:#382b16}
.shx-farm-catalog .farm-filterbar button.active{background:#243248;color:#e8f4ff;border-color:#79a3c3}
.shx-farm-catalog .farm-filterbar button[data-farm-filter="GRAY"].active,.farm-filterbar button[data-farm-filter="GRAY"].active{background:#273340;color:#d8e0eb;border-color:#7e91a2}
.shx-farm-catalog .farm-filterbar button[data-farm-filter="CYAN"].active,.farm-filterbar button[data-farm-filter="CYAN"].active{background:#10374a;color:#7deaf9;border-color:#2dacc8}
.shx-farm-catalog .farm-filterbar button[data-farm-filter="BLUE"].active,.farm-filterbar button[data-farm-filter="BLUE"].active{background:#122b57;color:#8abaff;border-color:#488bea}
.shx-farm-catalog .farm-filterbar button[data-farm-filter="PURPLE"].active,.farm-filterbar button[data-farm-filter="PURPLE"].active{background:#35204f;color:#d2a7ff;border-color:#9360d8}
.shx-farm-catalog .farm-filterbar button[data-farm-filter="PINK"].active,.farm-filterbar button[data-farm-filter="PINK"].active{background:#48203e;color:#ffa8d6;border-color:#d66aac}
.shx-farm-catalog .farm-filterbar button[data-farm-filter="RED"].active,.farm-filterbar button[data-farm-filter="RED"].active{background:#471d26;color:#ffa29b;border-color:#df6572}
.shx-farm-catalog .farm-filterbar button[data-farm-filter="GOLD"].active,.farm-filterbar button[data-farm-filter="GOLD"].active{background:#47340f;color:#ffe08d;border-color:#daa94c}
/* Case contents: individual 3D vector stickers, framed by rarity */
.case-loot-sticker{--loot:#bfcbd7;--loot-dark:#233043;--loot-glow:#bfcbd733;position:relative;display:grid;place-items:center;width:82px;height:87px;margin:0 auto;isolation:isolate;flex:0 0 auto}
.case-loot-sticker[data-tier="GRAY"]{--loot:#bfcbd7;--loot-dark:#253240;--loot-glow:#bfcbd733}
.case-loot-sticker[data-tier="CYAN"]{--loot:#6ae4f1;--loot-dark:#0b3950;--loot-glow:#4ddff244}
.case-loot-sticker[data-tier="BLUE"]{--loot:#83b7ff;--loot-dark:#112e64;--loot-glow:#438dff55}
.case-loot-sticker[data-tier="PURPLE"]{--loot:#cf91ff;--loot-dark:#3b1d60;--loot-glow:#aa67ff66}
.case-loot-sticker[data-tier="PINK"]{--loot:#ff9bdb;--loot-dark:#571e4a;--loot-glow:#ff69c866}
.case-loot-sticker[data-tier="RED"]{--loot:#ff858b;--loot-dark:#641b2b;--loot-glow:#ff465c66}
.case-loot-sticker[data-tier="GOLD"]{--loot:#ffe18a;--loot-dark:#644010;--loot-glow:#ffbf4077}
.case-loot-sticker:before{content:"";position:absolute;inset:7px 4px 5px 4px;border-radius:18px;background:linear-gradient(135deg,var(--loot-dark),#0b1422 68%);border:2px solid var(--loot);box-shadow:inset 0 1px 7px #ffffff36,0 0 16px var(--loot-glow),0 10px 16px #0007;transform:perspective(140px) rotateX(4deg) rotateY(-8deg)}
.case-loot-sticker:after{content:"";position:absolute;inset:13px 12px auto 13px;height:19px;border-radius:14px;background:linear-gradient(#ffffff55,transparent);filter:blur(5px);pointer-events:none}
.case-loot-sticker svg{position:relative;z-index:2;width:75px;height:75px;filter:drop-shadow(2px 6px 3px #0009)}
.case-loot-sticker.compact{width:48px;height:52px}.case-loot-sticker.compact:before{inset:5px 1px}.case-loot-sticker.compact svg{width:47px;height:47px}
.case-loot-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px;margin:11px 0}
.case-loot-card{display:flex;gap:7px;align-items:center;min-width:0;border:1px solid var(--loot,#52667e);background:linear-gradient(125deg,#11243a,#0a1727);border-radius:15px;padding:7px 6px;color:#ebf3ff;box-shadow:inset 0 1px #ffffff15;--loot:#566f8a}
.case-loot-card[data-tier="GRAY"]{--loot:#8797a8}.case-loot-card[data-tier="CYAN"]{--loot:#269fb5}.case-loot-card[data-tier="BLUE"]{--loot:#377be0}.case-loot-card[data-tier="PURPLE"]{--loot:#8c4ed0}.case-loot-card[data-tier="PINK"]{--loot:#d0529f}.case-loot-card[data-tier="RED"]{--loot:#c94b5d}.case-loot-card[data-tier="GOLD"]{--loot:#dcac4b}
.case-loot-card-name{font-size:10px;font-weight:900;line-height:1.28;overflow-wrap:anywhere}
.case-loot-card-meta{font-size:10px;margin-top:4px;color:#bfcfe0}
.case-loot-card .case-loot-sticker{width:55px;height:57px}.case-loot-card .case-loot-sticker svg{width:50px;height:50px}
.case-loot-card .case-loot-sticker:before{inset:4px 0}
.case-loot-details{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;max-height:47vh;overflow-y:auto;margin-top:10px;padding:3px}
.case-loot-details .case-loot-card{min-height:79px}
.case-guide-card .case-loot-preview{margin-top:14px;border-top:1px solid #2c4560;padding-top:9px}
.case-guide-card .case-loot-preview-title{font-size:12px;color:#a8c9e5;font-weight:900}
.case-tier-btn .case-loot-sticker{width:62px;height:62px}.case-tier-btn .case-loot-sticker svg{width:60px;height:60px}.case-tier-btn .case-loot-sticker:before{inset:3px}
.spin-result .case-loot-sticker,.roul-result .case-loot-sticker{width:106px;height:112px;margin:7px auto}
.spin-result .case-loot-sticker svg,.roul-result .case-loot-sticker svg{width:95px;height:95px}
.case-farm-feature{position:relative;overflow:hidden;border-radius:23px;margin:21px 0;border:1px solid #667b4a;background:linear-gradient(145deg,#19332f,#0e1b28 68%,#43321a);box-shadow:0 12px 30px #0008}
.case-farm-feature:before{content:"";position:absolute;inset:-30%;background:radial-gradient(circle at 70% 20%,#e8c46f2a,transparent 36%),radial-gradient(circle at 8% 85%,#76d49e18,transparent 35%);pointer-events:none}
.case-farm-scene{position:relative;height:167px;overflow:hidden}
.case-farm-scene .farm-landscape{border:0;border-radius:0;box-shadow:none;min-height:0;height:100%}
.case-farm-scene .farm-landscape svg{min-height:0;height:100%;width:100%;aspect-ratio:auto}
.case-farm-scene .farm-landscape-title{font-size:11px}
.case-farm-sky{position:absolute;left:68%;top:21px;z-index:2;font-size:23px;animation:caseFarmBob 3.4s ease-in-out infinite;filter:drop-shadow(0 4px 3px #0009)}
.case-farm-feature-content{position:relative;padding:14px}
.case-farm-feature-title{font-size:19px;font-weight:1000;color:#f0f8e8}
.case-farm-feature-desc{font-size:11px;line-height:1.5;color:#b4ccba;margin:8px 0 11px}
.case-farm-icons{display:flex;gap:7px;align-items:center;justify-content:space-between;margin-bottom:11px}
.case-farm-icons .farm-collectible{width:66px;height:63px;transform:scale(.8);transform-origin:center}
.case-farm-feature-stats{display:flex;gap:7px;flex-wrap:wrap;margin-bottom:12px}
.case-farm-feature-stats span{font-size:10px;border-radius:10px;background:#0f2630;border:1px solid #4b7667;padding:7px;color:#def5e5}
.case-farm-enter{width:100%;font-size:14px;color:#163017;background:linear-gradient(135deg,#d9f6a3,#a2d673 70%,#6dba5e);box-shadow:0 5px 19px #69be6359}
@keyframes caseFarmBob{0%,100%{transform:translateY(0) rotate(-4deg)}50%{transform:translateY(-10px) rotate(6deg)}}
@media(max-width:390px){.case-loot-grid{grid-template-columns:1fr 1fr;gap:5px}.case-loot-card-name{font-size:9px}}
@media(prefers-reduced-motion:reduce){.case-farm-sky{animation:none}}
.farm-uc-need{margin:12px 0;padding:12px;border:1px solid #326b83;border-radius:13px;background:linear-gradient(125deg,#123045,#102231);color:#c8f4ff;font-size:12px;line-height:1.5}
.farm-uc-need strong{color:#f0faff}


/* Post-release mobile polish: keep farm improvements readable on small phones */
.case-view-all{width:100%;margin-top:7px;background:linear-gradient(130deg,#162b46,#102237);border:1px solid #507bad;color:#cce8ff;font-size:12px;min-height:44px}
.case-all-items{margin-top:13px;padding-top:11px;border-top:1px solid #2e4b68}
.case-all-items h4{font-size:14px;color:#e1edff;margin:2px 0 9px}
.case-odds-list{display:flex;flex-wrap:wrap;gap:6px}
.case-odds-chip{font-size:10px;border-radius:12px;padding:7px 9px;font-weight:900;background:#14263b;border:1px solid #526b81;color:#d0dfef}
.case-odds-chip[data-tier="GRAY"]{color:#c9d2dd;background:#202d39;border-color:#75869a}
.case-odds-chip[data-tier="CYAN"]{color:#7ceefc;background:#102c38;border-color:#2791b5}
.case-odds-chip[data-tier="BLUE"]{color:#91c0ff;background:#142a50;border-color:#397be3}
.case-odds-chip[data-tier="PURPLE"]{color:#d5a8ff;background:#2d2146;border-color:#814bcc}
.case-odds-chip[data-tier="PINK"]{color:#ff9fd8;background:#411f39;border-color:#bd509a}
.case-odds-chip[data-tier="RED"]{color:#ffa0a6;background:#421c28;border-color:#c75262}
.case-odds-chip[data-tier="GOLD"]{color:#ffe596;background:#443312;border-color:#c3963d}
@media(max-width:580px){
 .farm-ui .farm-modules{display:grid;grid-template-columns:minmax(0,1fr)!important;gap:10px}
 .farm-ui .farm-module{display:grid;grid-template-columns:minmax(0,1fr) minmax(112px,35%);column-gap:10px;row-gap:5px;align-items:center;padding:11px;border:1px solid #426480;background:linear-gradient(120deg,#173349,#112435 70%,#262b28);border-radius:15px}
 .farm-ui .farm-module-header{grid-column:1;grid-row:1;display:flex;align-items:center;gap:8px;text-align:left;font-size:13px;line-height:1.2;overflow-wrap:anywhere}
 .farm-ui .farm-module-icon{display:inline-flex;align-items:center;justify-content:center;font-size:28px;margin:0;flex:0 0 29px}
 .farm-ui .farm-module-desc{grid-column:1;grid-row:2;min-height:0;font-size:10px;text-align:left;line-height:1.35;color:#afc3d5;margin:2px 0;overflow-wrap:anywhere}
 .farm-ui .farm-module .mini{grid-column:2;grid-row:1;font-size:10px;text-align:center;color:#c5d4e6;margin:0}
 .farm-ui .farm-module-progress{grid-column:1;grid-row:3;margin:5px 0 0}
 .farm-ui .farm-module button{grid-column:2;grid-row:2/span 2;width:100%;min-height:48px;font-size:10px;padding:8px 4px;line-height:1.3;white-space:normal;overflow-wrap:anywhere}
}


/* Case reel items: coloured rarity aureoles around actual item stickers */
.reel-item-prize{--reel-rarity:#9eadbc;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:0;position:relative}
.reel-item-prize[data-tier="GRAY"]{--reel-rarity:#b4becb}
.reel-item-prize[data-tier="CYAN"]{--reel-rarity:#79e8f6}
.reel-item-prize[data-tier="BLUE"]{--reel-rarity:#79b9ff}
.reel-item-prize[data-tier="PURPLE"]{--reel-rarity:#d09bff}
.reel-item-prize[data-tier="PINK"]{--reel-rarity:#ff8fcd}
.reel-item-prize[data-tier="RED"]{--reel-rarity:#ff868e}
.reel-item-prize[data-tier="GOLD"]{--reel-rarity:#ffe188}
.reel-item-prize .case-loot-sticker.compact{width:78px;height:75px;margin:0 auto;flex:0 0 75px}
.reel-item-prize .case-loot-sticker.compact svg{width:73px;height:73px;filter:drop-shadow(1px 5px 3px #000b)}
.reel-item-prize .case-loot-sticker:before{inset:5px 7px 4px 7px;border-radius:50%;background:radial-gradient(ellipse at 38% 25%,#ffffff1e 0%,#102036 58%,#060e1c 100%);border:1.5px solid var(--reel-rarity);box-shadow:inset 0 1px 5px #ffffff18,0 0 15px color-mix(in srgb,var(--reel-rarity) 40%,transparent),0 3px 8px #0009;transform:none}
.reel-item-prize .case-loot-sticker:after{inset:5px 14px auto 14px;opacity:.55}
.reel-prize-name{width:88px;max-width:88px;height:17px;display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;text-align:center;font-size:8px;line-height:17px;font-weight:850;color:var(--reel-rarity);text-shadow:0 1px 5px #000b;letter-spacing:-.2px}
.reel-item-prize.target-cube .case-loot-sticker:before{border-width:2px;box-shadow:0 0 18px color-mix(in srgb,var(--reel-rarity) 65%,transparent),0 2px 9px #000b}
.reel-item-empty{font-size:10px;color:#aac0d8;text-align:center;line-height:1.4;white-space:normal}
.farm-upgrade-btn{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:5px;white-space:normal!important;padding:8px 5px!important;min-height:52px;line-height:1.3}
.farm-upgrade-cost{font-size:10px;line-height:1.2;color:#f2d99e;white-space:normal;overflow-wrap:anywhere;font-weight:900}
.farm-upgrade-btn:disabled .farm-upgrade-cost{color:#9fa9b4}
@media(max-width:580px){.farm-ui .farm-module .farm-upgrade-btn{font-size:10px;min-height:58px}}


/* Clean mode: all tutorial hints removed from player mini app.
   Keep controls, win status, rarity odds, prices and withdrawal requirements. */
#app .spin-case-note,#app .case-guide-note,#app .roul-hint,#app .spin-lock-note,
#app .case-farm-feature-desc,#app .farm-aux,#app .case-prizes-panel>.muted,
#app .settings-grid .setting-card>.muted,#app .roul-hero>.muted,
#app .spin-shell>.muted,#app .spin-case-note,#app .rarity-catalog-head>.mini,
#app .shx-farm-catalog .shx-panel>.muted,
#app .case-guide+.muted,#app .farm-lead>.muted,
#app .spin-shell~.card>.muted,#app .case-farm-feature-content>.muted
{display:none!important}
#app .farm-uc-need,#app .farm-uc-target,#app .case-odds-chip,#app .farm-upgrade-cost{display:revert}


/* Level-scaled, profit-backed UC mining */
.farm-uc-miner{margin:13px 0 17px;padding:16px;border-radius:21px;position:relative;overflow:hidden;
background:radial-gradient(ellipse at 75% 0,#32a8d22d,transparent 58%),linear-gradient(140deg,#102a39,#0a1a2c 68%,#163244);
border:1px solid #458caa;box-shadow:inset 0 1px #a3eaff2a,0 11px 31px #0007}
.farm-uc-miner:before{content:"";position:absolute;right:-30px;top:-49px;width:170px;height:170px;border-radius:50%;
background:radial-gradient(circle,#71e0ff1f,transparent 70%);pointer-events:none;animation:shxUcHalo 3.4s ease-in-out infinite alternate}
@keyframes shxUcHalo{from{opacity:.55;transform:scale(.85)}to{opacity:1;transform:scale(1.08)}}
.farm-uc-miner-head{position:relative;display:flex;align-items:center;justify-content:space-between;gap:10px}
.farm-uc-miner-label{font-size:16px;font-weight:1000;color:#e2f7ff;line-height:1.25}
.farm-uc-miner-head svg{width:44px;height:44px;flex:0 0 44px;filter:drop-shadow(0 0 8px #65d5f55e)}
.farm-uc-miner-stats{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin:13px 0}
.farm-uc-miner-stat{background:#092033c9;border:1px solid #315976;border-radius:12px;padding:9px 7px;min-width:0}
.farm-uc-miner-stat small{display:block;color:#a0bfcc;font-size:9px;line-height:1.35;margin-bottom:5px}
.farm-uc-miner-stat strong{font-size:13px;color:#e3f6fe;font-weight:1000;overflow-wrap:anywhere}
.farm-uc-miner-track{height:9px;border-radius:20px;background:#092031;border:1px solid #37647b;overflow:hidden}
.farm-uc-miner-track>span{height:100%;display:block;border-radius:20px;background:linear-gradient(90deg,#2f9ec7,#6de2f4,#c6f7ff);box-shadow:0 0 15px #7eeafcad;transition:width .2s linear}
.farm-uc-miner-foot{display:flex;align-items:center;justify-content:space-between;gap:10px;color:#8db9d3;font-size:10px;margin:8px 0 13px}
.farm-uc-miner-claim{width:100%;min-height:49px;font-size:13px;background:linear-gradient(120deg,#90f4ed,#36bdd1 60%,#2287b5);color:#09222b;border:1px solid #b3f5ef;box-shadow:0 7px 18px #189cbd49}
.farm-uc-miner-claim:disabled{background:#163048;border-color:#37516a;color:#849db4;box-shadow:none}
.farm-uc-miner .farm-uc-paused{font-size:11px;color:#f7c787;margin-top:9px;text-align:center}
@media(max-width:360px){.farm-uc-miner-stats{gap:5px}.farm-uc-miner-stat{padding:8px 5px}.farm-uc-miner-stat strong{font-size:11px}}
@media(prefers-reduced-motion:reduce){.farm-uc-miner:before{animation:none}}


/* SHOP marketplace: vendor-facing controls isolated from the existing store */
.seller-hero{padding:20px 17px;border-radius:22px;border:1px solid #497f97;background:radial-gradient(circle at 80% 0%,#77c9eb25,transparent 48%),linear-gradient(137deg,#102e48,#091b2c 80%);box-shadow:0 12px 30px #0005;margin-bottom:15px}
.seller-hero h1{margin:8px 0 3px;font-size:25px;font-weight:1000}
.seller-hero .seller-headline{color:#9de3f7;font-size:11px;font-weight:900;letter-spacing:.15em}
.seller-feature-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px;margin-top:13px}
.seller-feature-grid>div{min-width:0;padding:10px 7px;border:1px solid #35546f;border-radius:12px;background:#0b2034}
.seller-feature-grid strong{display:block;color:#e9fbff;font-size:16px;font-weight:950}
.seller-feature-grid small{font-size:9px;color:#9ebac7;line-height:1.4}
.seller-status-pill{display:inline-flex;border-radius:9px;padding:5px 8px;font-weight:900;font-size:10px;background:#193953;border:1px solid #548bac;color:#b4e9ff}
.seller-status-pill.approved,.seller-status-pill.active{background:#183b32;border-color:#459c7e;color:#a1f1bf}
.seller-status-pill.blocked,.seller-status-pill.rejected{background:#431e2c;border-color:#be5975;color:#ffc1c4}
.seller-stock-tag{color:#8ceec5;font-weight:900;font-size:11px}
.seller-market-card{padding:12px;border:1px solid #365974;background:linear-gradient(140deg,#122840,#0b182a);border-radius:16px;margin:9px 0;overflow-wrap:anywhere}
.seller-market-card h3{margin:4px 0 7px;font-size:15px;color:#f3faff}
.seller-market-card .mini{font-size:11px}
.seller-market-actions{display:flex;flex-wrap:wrap;gap:7px;margin-top:10px}
.seller-market-actions button{flex:1 1 110px;font-size:11px}
.seller-inputs{display:grid;gap:9px}
.seller-inputs input,.seller-inputs textarea,.seller-inputs select{width:100%;max-width:100%;box-sizing:border-box}
.seller-income-row{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}
.seller-income-row>div{background:#132c44;border:1px solid #42657e;padding:12px;border-radius:12px}
.seller-income-row span{display:block;font-size:10px;color:#a0bcce}
.seller-income-row b{display:block;margin-top:4px;font-size:19px;color:#ddf6ff}
.seller-help{font-size:11px;color:#aac3d2;line-height:1.5;margin-top:10px}
.seller-accept{display:flex;gap:9px;align-items:start;font-size:12px}
.seller-accept input{width:auto;flex:0 0 auto}
.seller-badge{color:#9bd9ff;font-size:10px;font-weight:900}
.seller-chip{display:inline-flex;font-size:10px;font-weight:850;border:1px solid #467189;border-radius:8px;padding:4px 8px;background:#10283b}
.seller-admin-list{max-height:600px;overflow-y:auto}
.seller-admin-box{margin:10px 0;padding:12px;border:1px solid #45637d;border-radius:15px;background:#11253b}
.seller-admin-box .seller-market-actions{margin-top:12px}
@media(max-width:390px){.seller-feature-grid{grid-template-columns:repeat(3,minmax(0,1fr))}.seller-hero h1{font-size:22px}}


/* Seller marketplace storefront */
.seller-catalog-head{padding:19px 16px 13px;border-radius:19px;border:1px solid #385c79;
background:radial-gradient(ellipse at 91% 0,#367f9a38,transparent 52%),linear-gradient(135deg,#10263d,#09192c);
box-shadow:0 13px 30px #0008;margin-bottom:18px}
.seller-catalog-head h1{font-size:25px;line-height:1.2;margin:5px 0 14px;color:#eaf7ff}
.seller-market-switch{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:5px}
.seller-market-switch button{font-size:10px;font-weight:850;padding:10px 3px;line-height:1.2;min-height:43px;color:#a9bed7;border:1px solid #34516a;background:#0e2138;border-radius:11px}
.seller-market-switch button.active{border-color:#7bd7fa;color:#e8f8ff;background:linear-gradient(135deg,#214f70,#153855);box-shadow:0 0 12px #6ccafc27}
.shop-list-section{margin:15px 0 23px}
.shop-list-heading{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:10px}
.shop-list-heading h3{font-size:16px;color:#e1f4ff;margin:0;line-height:1.25}
.seller-availability{font-size:11px;color:#b4d9ec;margin-top:9px;padding:8px 10px;background:#102b40;border:1px solid #365e7b;border-radius:8px}
.shop-list-section .grid{margin-top:0}
@media(max-width:345px){.seller-market-switch button{font-size:9px}.shop-list-heading h3{font-size:14px}}

.shx-uc-uid-label{margin:14px 0 7px;color:#94bfe8;font-size:11px;font-weight:900;letter-spacing:1.1px}.shx-uc-uid-copy{width:100%;min-height:82px;padding:13px 12px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px;border:2px solid #38a7ff;border-radius:14px;background:#0a2849;color:#fff;cursor:pointer;touch-action:manipulation}.shx-uc-uid-value{font-size:clamp(25px,7vw,38px);font-weight:950;letter-spacing:1.5px;font-variant-numeric:tabular-nums;overflow-wrap:anywhere;text-align:center;line-height:1.2}.shx-uc-copy-action{font-size:13px;font-weight:800;color:#8cddff}
.shx-uc-contact{margin:12px 0;padding:12px;border:1px solid #2c6a9c;border-radius:12px;background:#09223c}.shx-uc-contact summary{cursor:pointer;font-weight:850;color:#b5e6ff;padding:5px}.shx-uc-contact textarea{width:100%;margin:12px 0 8px;min-height:95px}.shx-uc-contact button{width:100%;min-height:46px}.shx-uc-contact a{display:block;margin-top:12px;color:#8bd6ff;text-align:center;font-weight:750}
.shx-chat-tabs{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px;margin:15px 0}.shx-chat-tabs button{font-size:12px;padding:10px 4px;min-width:0}.shx-chat-filter-active{border-color:#48baff!important;color:#fff!important;background:#145180!important}.shx-user-chat summary{display:flex;justify-content:space-between;align-items:center;gap:8px;list-style:none}.shx-user-chat summary::-webkit-details-marker{display:none}.shx-chat-status{font-size:12px;border-radius:20px;padding:5px 9px;white-space:nowrap}.shx-chat-status.is-open{background:#164f42;color:#91f5ca}.shx-chat-status.is-closed{background:#47343e;color:#ffc0ce}.shx-chat-msg{padding:10px;margin:9px 0;border:1px solid #25476a;border-radius:9px;overflow-wrap:anywhere}.shx-chat-msg p{white-space:pre-wrap;margin:6px 0 0}
.shx-unread-badge:empty{display:none!important}.shx-unread-badge{display:inline-flex;align-items:center;justify-content:center;min-width:20px;height:20px;padding:2px 6px;border-radius:20px;background:#f34e65;color:#fff;font-weight:900;font-size:12px;margin-left:7px;vertical-align:middle}
.shx-player-detail-grid{min-width:0}.shx-player-detail-grid>div{min-width:0;overflow:hidden}.shx-player-detail-grid b{display:block;max-width:100%;overflow-wrap:anywhere;word-break:break-word;font-variant-numeric:tabular-nums}
.shx-admin-unread-notice{margin:12px 18px 0;padding:12px 16px;border:1px solid #f15a6a;border-radius:12px;background:#3b1927;color:#ffdce3;font-weight:800}.shx-admin-unread-notice[hidden]{display:none!important}
</style>
</head>
<body>
<div class="wrap">
  <div class="top"><div class="brand">ШРЕКСИЧ <b>SHOP</b></div><div class="pill">PUBG MOBILE</div></div>
  <div class="wins" id="winsTicker" title="Крупные выигрыши всех игроков Шрексича"><div class="wins-track"><span class="muted">Загружаем крупные выигрыши…</span></div></div>
  <main id="app"><div class="empty">Загрузка магазина…</div></main>
</div>
<div class="nav" id="nav">
  <button data-tab="home"><span class="nav-ico">⌂</span><span>Главная</span></button><button data-tab="catalog"><span class="nav-ico">▦</span><span>Каталог</span></button><button data-tab="spin"><span class="nav-ico">▣</span><span>Кейсы</span></button><button data-tab="farm"><span class="nav-ico">⌂</span><span>Ферма</span></button><button data-tab="profile"><span class="nav-ico">♙</span><span>Профиль</span></button>
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
let spinNavigationLocked=false;
let selectedCaseId=localStorage.getItem('shx_selected_case')||'CASE29';

let audioCtx=null,spinSoundTimer=null,spinSoundStarted=0,spinSoundStep=0,spinSoundTotalMs=30000,spinSoundActive=false,spinAudioHold=null;
function soundsEnabled(){
 const saved=localStorage.getItem('shx_sound_enabled');
 const prefV2=localStorage.getItem('shx_sound_pref_v2');
 if(saved==='0'&&prefV2!=='1'){
  localStorage.setItem('shx_sound_enabled','1');
  return true
 }
 return saved!=='0'
}
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
  if(ac.state==='suspended')ac.resume().catch(()=>{});
  const o=ac.createOscillator(),g=ac.createGain();
  o.frequency.value=32;g.gain.value=.000001;
  o.connect(g);g.connect(ac.destination);o.start();o.stop(ac.currentTime+.025)
 }catch(_){}
 return ac
}
async function ensureAudioReady(){
 if(!soundsEnabled())return null;
 const ac=unlockAudio();if(!ac)return null;
 try{if(ac.state!=='running')await ac.resume()}catch(_){}
 return ac
}
document.addEventListener('pointerdown',()=>{if(soundsEnabled())unlockAudio()},{passive:true});
document.addEventListener('touchstart',()=>{if(soundsEnabled())unlockAudio()},{passive:true});
document.addEventListener('visibilitychange',()=>{if(!document.hidden&&soundsEnabled())unlockAudio()});
function beginAudioHold(){
 const ac=unlockAudio();if(!ac||spinAudioHold)return;
 try{
  const o=ac.createOscillator(),g=ac.createGain();
  o.frequency.value=55;g.gain.value=.000001;o.connect(g);g.connect(ac.destination);o.start();
  spinAudioHold={o,g}
 }catch(_){}
}
function endAudioHold(){
 if(!spinAudioHold)return;
 try{spinAudioHold.o.stop()}catch(_){}
 try{spinAudioHold.o.disconnect();spinAudioHold.g.disconnect()}catch(_){}
 spinAudioHold=null
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
 tone(note,dur,.042,'sine');
 tone(note/2,dur+.10,.021,'triangle',.015);
 if(spinSoundStep%3===0)tone(root,dur+.24,.024,'sine',.025);
 if(spinSoundStep%6===4)tone(note*1.25,dur*.8,.017,'sine',.08);
 spinSoundStep++
}
function startSpinSound(totalMs=30000){
 if(spinSoundTimer){clearTimeout(spinSoundTimer);spinSoundTimer=null}
 if(!soundsEnabled()){endAudioHold();return}
 unlockAudio();
 spinSoundTotalMs=totalMs;spinSoundStarted=performance.now();spinSoundStep=0;spinSoundActive=true;
 const loop=()=>{
  if(!spinSoundActive||!soundsEnabled())return;
  const p=Math.min(1,(performance.now()-spinSoundStarted)/spinSoundTotalMs);
  playSpinMelody(p);
  if(p<1){
   const gap=Math.round(300 + Math.pow(p,2.1)*650);
   spinSoundTimer=setTimeout(loop,gap)
  }else{spinSoundActive=false;spinSoundTimer=null;endAudioHold()}
 };
 loop()
}
function stopSpinSound(){
 spinSoundActive=false;
 if(spinSoundTimer){clearTimeout(spinSoundTimer);spinSoundTimer=null}
 endAudioHold()
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
 const t=String(tier||'GRAY').toUpperCase();
 if(t==='GRAY'||t==='COMMON'){tone(520,.12,.03,'sine');tone(660,.12,.022,'sine',.08)}
 else if(t==='CYAN'||t==='RARE'){tone(520,.13,.032,'triangle');tone(720,.16,.036,'triangle',.08);tone(920,.18,.03,'sine',.16)}
 else if(t==='BLUE'){[440,587,784].forEach((f,i)=>tone(f,.18,.038,'triangle',i*.07))}
 else if(t==='PURPLE'||t==='EPIC'){[440,660,880,1100].forEach((f,i)=>tone(f,.22,.045,'triangle',i*.07))}
 else if(t==='PINK'){[523,659,784,1047,1318].forEach((f,i)=>tone(f,.25,.048,'sine',i*.065))}
 else if(t==='RED'||t==='MYTHIC'){noiseBurst(.22,.045);tone(110,.45,.05,'sawtooth');[440,554,659,880,1108].forEach((f,i)=>tone(f,.3,.052,i%2?'square':'triangle',.07+i*.07))}
 else {noiseBurst(.3,.055);[392,523,659,784,1047,1318,1568].forEach((f,i)=>tone(f,.38,.06,'sine',i*.07))}
}
function sfxSell(){if(!soundsEnabled())return;[660,880,1100,1320].forEach((f,i)=>tone(f,.13,.04,'triangle',i*.055))}
function sfxSave(){if(!soundsEnabled())return;noiseBurst(.08,.018);tone(420,.13,.035,'sine');tone(630,.18,.035,'sine',.08);tone(840,.2,.03,'sine',.14)}
async function setSoundEnabled(on){
 localStorage.setItem('shx_sound_pref_v2','1');
 localStorage.setItem('shx_sound_enabled',on?'1':'0');
 if(!on){stopSpinSound();return}
 await ensureAudioReady();
 resumeSpinSoundIfNeeded();
 tone(523.25,.12,.030,'sine');tone(659.25,.15,.026,'sine',.07)
}

function esc(v){return String(v==null?'':v).replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]))}
function stars(n){return Number(n||0).toLocaleString('ru-RU')+' ⭐'}
function compactCurrency(n){const v=Number(n||0);if(!Number.isFinite(v))return '0';const a=Math.abs(v);if(a<10000)return v.toLocaleString('ru-RU');const units=[[1e15,'квадрлн'],[1e12,'трлн'],[1e9,'млрд'],[1e6,'млн'],[1e3,'тыс.']];const unit=units.find(x=>a>=x[0]);if(!unit)return v.toLocaleString('ru-RU');const scaled=v/unit[0];return scaled.toLocaleString('ru-RU',{maximumFractionDigits:scaled>=100?0:scaled>=10?1:2})+' '+unit[1]}
function shrAmount(n){return compactCurrency(n)}

function tierClass(t){return 'tier-'+String(t||'COMMON').toLowerCase()}
function rarityBar(t){const k=String(t||'COMMON').toLowerCase();return '<div class="rarity-row"><div class="rarity-label '+tierClass(t)+'">'+esc(t)+'</div><div class="rarity-bar rb-'+k+'"></div></div>'}
function formatReset(sec){sec=Math.max(0,Number(sec||0));if(!sec)return'';const h=Math.floor(sec/3600),m=Math.ceil((sec%3600)/60);return(h?h+' ч ':'')+m+' мин'}
function showFatal(m){app.innerHTML='<div class="empty">'+esc(m)+'</div>'}
window.addEventListener('error',e=>showFatal('Ошибка интерфейса: '+(e.message||'неизвестная')));
window.addEventListener('unhandledrejection',e=>showFatal('Ошибка загрузки: '+((e.reason&&e.reason.message)||String(e.reason||''))));

async function api(path,options={}){
 const ctl=new AbortController(),timer=setTimeout(()=>ctl.abort(),30000);
 try{
  const r=await fetch(path,Object.assign({},options,{headers:Object.assign({},headers,options.headers||{}),signal:ctl.signal}));
  let d={};try{d=await r.json()}catch(_){}
  if(!r.ok){const detail=Array.isArray(d.detail)?d.detail.map(x=>{const field=(x.loc||[]).filter(v=>v!=='body').join('.');return (field?field+': ':'')+(x.msg||'Неверное значение')}).join('; '):typeof d.detail==='string'?d.detail:('HTTP '+r.status);throw new Error(detail)}
  return d;
 }catch(e){if(e&&e.name==='AbortError')throw new Error('Сервер не ответил за 30 секунд');throw e}
 finally{clearTimeout(timer)}
}
function openTelegram(url){try{if(tg&&tg.openTelegramLink)tg.openTelegramLink(url);else window.open(url,'_blank')}catch(_){window.open(url,'_blank')}}
function bindSocials(){document.querySelectorAll('[data-tg]').forEach(b=>b.addEventListener('click',()=>openTelegram(b.dataset.tg)))}
function updateNav(){document.querySelectorAll('#nav button').forEach(b=>b.classList.toggle('active',b.dataset.tab===tab));if(ADMIN)navEl.classList.add('hide')}
function setSpinNavigationLocked(on){
 spinNavigationLocked=!!on;
 if(navEl)navEl.classList.toggle('spin-locked',spinNavigationLocked);
 document.querySelectorAll('#nav button').forEach(b=>b.disabled=spinNavigationLocked);
 const home=document.getElementById('pageHomeBtn');if(home)home.disabled=spinNavigationLocked;
 const note=document.getElementById('spinLockNote');if(note)note.classList.toggle('show',spinNavigationLocked)
}
let ucUnreadCount=0;async function refreshUCUnread(){if(ADMIN)return;try{const d=await api('/api/uc-chats/unread');ucUnreadCount=Number(d.unread||0);document.querySelectorAll('[data-tab="support"],.shx-profile-support').forEach(b=>{let badge=b.querySelector('.shx-unread-badge');if(ucUnreadCount){if(!badge){badge=document.createElement('span');badge.className='shx-unread-badge';b.appendChild(badge)}badge.textContent=String(ucUnreadCount)}else badge?.remove()});const h=document.getElementById('ucSupportUnread');if(h)h.textContent=ucUnreadCount?String(ucUnreadCount):''}catch(_){}}
function go(t){
 if(spinNavigationLocked){
  try{if(tg&&tg.HapticFeedback)tg.HapticFeedback.impactOccurred('light')}catch(_){}
  return
 }
 tab=t;render()
}

let lastWinsFingerprint='';
async function loadWinsFeed(){
 try{
  // Глобальная история редких выигрышей. У всех пользователей отображается один поток.
  const wins=await api('/api/wins-feed');
  const el=document.querySelector('#winsTicker .wins-track');if(!el)return;
  const fingerprint=JSON.stringify(wins.map(x=>[x.id,x.player,x.reward_name,x.reward_tier]));
  lastWinsData=wins;
  const liveCards=document.getElementById('homeLiveCards');if(liveCards)liveCards.innerHTML=homeWinsHtml();
  if(fingerprint===lastWinsFingerprint)return; // Не перезапускаем CSS-анимацию каждые 20 секунд.
  lastWinsFingerprint=fingerprint;
  if(!wins.length){el.innerHTML='<span class="muted">Пока нет крупных выигрышей игроков</span>';el.style.animation='none';return}
  el.style.animation='';
  const one=wins.map(x=>'<span class="win-item '+String(x.reward_tier).toLowerCase()+'">'+(x.reward_tier==='RED'||x.reward_tier==='MYTHIC'?'◆':'★')+' '+esc(x.player)+' выбил '+esc(x.reward_name)+' <b>'+esc(x.reward_tier)+'</b></span>').join('');
  el.innerHTML=one+one;
 }catch(_){}
}

function cards(list){
 return '<div class="grid">'+list.map(p=>'<div class="card"><div class="cat">'+esc(p.category)+'</div>'+
 '<div class="name">'+esc(p.name)+'</div><div class="desc">'+esc(p.description)+'</div>'+
 (Number(p.seller_id||0)>0?'<div class="seller-badge">✓ ПРОДАВЕЦ: '+esc(p.seller_name||'Проверенный продавец')+'</div>'+
 '<div class="seller-stock-tag">● В наличии: '+Number(p.seller_stock||0)+' шт.</div>':'')+
 '<div class="price">'+stars(p.stars_price)+'</div><button class="buy" data-buy="'+p.id+'">Купить за Stars</button></div>').join('')+'</div>'
}

function marketplaceCatalogHtml(){
 const cats=[...new Set(products.map(p=>String(p.category||'Другое')))].sort((a,b)=>a.localeCompare(b,'ru'));
 return '<section class="seller-catalog-head"><div class="seller-headline">SHREKSICH SHOP · METRO ROYALE</div><h1>🛒 Каталог товаров</h1><div class="mini">Товары Шрексича и проверенных продавцов · '+products.length+' предложений</div></section>'+
 '<div class="shx-panel seller-inputs" style="margin:10px 0"><h3>🔎 Поиск и фильтры</h3><input id="shopSearch" placeholder="Название, описание или продавец" autocomplete="off">'+
 '<div class="seller-income-row"><label class="mini">Категория<select id="shopCategory"><option value="">Все категории</option>'+cats.map(c=>'<option value="'+esc(c)+'">'+esc(c)+'</option>').join('')+'</select></label><label class="mini">Продавец<select id="shopSource"><option value="all">Все товары</option><option value="partners">Партнёры</option><option value="official">Шрексич</option></select></label></div>'+
 '<div class="seller-income-row"><label class="mini">Цена от ⭐<input id="shopMin" type="number" min="0" inputmode="numeric" placeholder="От"></label><label class="mini">Цена до ⭐<input id="shopMax" type="number" min="0" inputmode="numeric" placeholder="До"></label></div>'+
 '<div class="seller-income-row"><label class="mini">Рейтинг продавца<select id="shopRating"><option value="0">Любой рейтинг</option><option value="4.5">От 4,5 ⭐</option><option value="4">От 4 ⭐</option><option value="3">От 3 ⭐</option></select></label><label class="mini">Сортировка<select id="shopSort"><option value="default">По умолчанию</option><option value="cheap">Сначала дешёвые</option><option value="expensive">Сначала дорогие</option><option value="rating">По рейтингу</option><option value="new">Сначала новые</option><option value="stock">По наличию</option></select></label></div>'+
 '<label class="seller-accept"><input type="checkbox" id="shopStock" checked> Только в наличии</label><button class="secondary" type="button" id="shopReset">Сбросить фильтры</button></div>'+
 '<div class="mini" id="shopCount" aria-live="polite"></div><div id="shopResults"></div>';
}
function bindMarketplaceCatalog(){
 const ids=['shopSearch','shopCategory','shopSource','shopMin','shopMax','shopRating','shopSort','shopStock'];
 const render=()=>{
  const val=id=>document.getElementById(id)?.value||'';
  const query=val('shopSearch').trim().toLocaleLowerCase('ru'),cat=val('shopCategory'),source=val('shopSource'),min=val('shopMin')===''?0:Number(val('shopMin')),max=val('shopMax')===''?Infinity:Number(val('shopMax')),rating=Number(val('shopRating'));
  const stockOnly=document.getElementById('shopStock').checked;
  let found=products.filter(p=>{
   const partner=Number(p.seller_id||0)>0,price=Number(p.stars_price||0),r=Number(p.seller_rating||0);
   return (!query||[p.name,p.description,p.seller_name,p.category].some(x=>String(x||'').toLocaleLowerCase('ru').includes(query)))&&(!cat||p.category===cat)&&(source==='all'||(source==='partners'&&partner)||(source==='official'&&!partner))&&price>=min&&price<=max&&(!rating||(partner&&r>=rating))&&(!stockOnly||!partner||Number(p.seller_stock||0)>0);
  });
  const sort=val('shopSort');if(sort==='cheap')found.sort((a,b)=>Number(a.stars_price)-Number(b.stars_price));else if(sort==='expensive')found.sort((a,b)=>Number(b.stars_price)-Number(a.stars_price));else if(sort==='rating')found.sort((a,b)=>Number(b.seller_rating||0)-Number(a.seller_rating||0));else if(sort==='new')found.sort((a,b)=>Number(b.id)-Number(a.id));else if(sort==='stock')found.sort((a,b)=>Number(b.seller_stock||0)-Number(a.seller_stock||0));
  document.getElementById('shopCount').textContent='Найдено: '+found.length+' из '+products.length;
  const partners=found.filter(p=>Number(p.seller_id||0)>0),official=found.filter(p=>Number(p.seller_id||0)===0);
  document.getElementById('shopResults').innerHTML=(partners.length?'<section class="shop-list-section"><div class="shop-list-heading"><h3>🤝 Продавцы · '+partners.length+'</h3></div>'+partners.map(p=>'<div class="mini" style="margin:7px 0 2px">🏪 '+esc(p.seller_name||'Продавец')+' · '+(Number(p.seller_review_count||0)>0?'⭐ '+Number(p.seller_rating).toFixed(1)+' ('+Number(p.seller_review_count)+' оценок)':'Пока без оценок')+'</div>'+cards([p])).join('')+'</section>':'')+(official.length?'<section class="shop-list-section"><div class="shop-list-heading"><h3>📦 Шрексич · '+official.length+'</h3></div>'+cards(official)+'</section>':'')+(!found.length?'<div class="empty">По этим фильтрам товаров нет. Попробуйте сбросить фильтры.</div>':'');
  bindProductButtons();
 };
 ids.forEach(id=>document.getElementById(id)?.addEventListener(id==='shopStock'?'change':'input',render));
 document.getElementById('shopReset')?.addEventListener('click',()=>{ids.forEach(id=>{const e=document.getElementById(id);if(!e)return;if(id==='shopStock')e.checked=true;else if(e.tagName==='SELECT')e.selectedIndex=0;else e.value=''});render()});
 render();
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
  history:'<svg viewBox="0 0 24 24"><path d="M4 12a8 8 0 1 0 2.3-5.7L4 8.6"/><path d="M4 4v4.6h4.6"/><path d="M12 7v5l3 2"/></svg>',
  cases:'<svg viewBox="0 0 24 24"><path d="m4 7 8-4 8 4-8 4-8-4Z"/><path d="M4 7v10l8 4 8-4V7"/><path d="M8 13h8M12 11v8"/></svg>',
  farm:'<svg viewBox="0 0 24 24"><path d="M4 20V9l8-5 8 5v11H4Z"/><path d="M8 20v-6h8v6M7 10h2m6 0h2"/><path d="M2 20h20"/></svg>'
 };
 return '<div class="sticker '+cls+'" '+attrs+'><span class="sticker-icon">'+(icons[icon]||icons.shop)+'</span><div class="sticker-copy"><div class="sticker-title">'+title+'</div><div class="sticker-sub">'+sub+'</div></div></div>'
}

function homeTileArt(kind){
 const paths={
  catalog:'<path d="M12 24L39 12 64 25 38 39Z" fill="#d6a55d" stroke="#ffe1a5"/><path d="M12 24V49L38 64V39Z" fill="#644021" stroke="#c99e62"/><path d="M64 25V50L38 64V39Z" fill="#a17138" stroke="#ecc88a"/><path d="M24 17L49 31 49 57" stroke="#f7dfad" stroke-width="3" fill="none"/>',
  cases:'<path d="M10 26L34 12 64 26 38 42Z" fill="#bd5bfd" stroke="#f5bdff"/><path d="M10 26V53L38 70V42Z" fill="#452a80" stroke="#a77bff"/><path d="M64 26V53L38 70V42Z" fill="#783bc3" stroke="#d7a8ff"/><path d="M35 16L47 27 34 41 22 28Z" fill="#f7b3ff"/><path d="M38 43V65" stroke="#fff4b9" stroke-width="4"/>',
  spin:'<circle cx="37" cy="39" r="30" fill="#242752" stroke="#a48bff" stroke-width="5"/><circle cx="37" cy="39" r="23" fill="#33265e" stroke="#7edaff"/><path d="M37 16V62M14 39H60M21 22L54 55M54 22L21 55" stroke="#b2a2fd" stroke-width="4"/><circle cx="37" cy="39" r="6" fill="#ffe28f"/><path d="M32 5L37 14 42 5" fill="#ffcc50" stroke="#fbe39b"/>',
  farm:'<path d="M9 36L36 15 66 36V65H9Z" fill="#79502f" stroke="#e2b57c" stroke-width="3"/><path d="M4 36L36 9 72 36 63 39 36 20 12 40Z" fill="#a15f3f" stroke="#edbf77" stroke-width="3"/><path d="M28 65V39H48V65" fill="#251c18" stroke="#d2a16b" stroke-width="3"/><path d="M28 39L48 65M48 39L28 65" stroke="#b88451" stroke-width="3"/><path d="M6 65H70" stroke="#7ac070" stroke-width="5"/>',
  tasks:'<path d="M27 12L39 24 27 36 15 24Z" fill="#c79553" stroke="#ffe0a1" stroke-width="3"/><path d="M46 12L58 24 46 36 34 24Z" fill="#6d90ae" stroke="#d2eafb" stroke-width="3"/><path d="M20 43L32 55 44 43" fill="none" stroke="#f9d57a" stroke-width="5"/><circle cx="52" cy="53" r="8" fill="#f2c155"/>',
  promo:'<path d="M8 25L51 11 65 28 24 62 8 48Z" fill="#41678b" stroke="#b4ddff" stroke-width="3"/><circle cx="20" cy="33" r="5" fill="#edc46c"/><path d="M39 25L31 49M31 29H31M45 45H45" stroke="#fff0b2" stroke-width="5" stroke-linecap="round"/>',
  uc:'<path d="M15 11H56L66 23V53L56 65H15L7 53V23Z" fill="#13638d" stroke="#a8f0ff" stroke-width="4"/><path d="M19 18H52L58 26V51L52 58H19L15 51V26Z" fill="#0b3654" stroke="#65c9f7"/><text x="36" y="46" text-anchor="middle" fill="#dbfcff" font-size="20" font-weight="900">UC</text>',
  help:'<path d="M11 15Q39 0 65 18V51Q39 67 11 51Z" fill="#155681" stroke="#9de4ff" stroke-width="3"/><path d="M24 27Q30 15 43 22Q57 29 39 40L37 45" stroke="#ebfaff" stroke-width="5" fill="none"/><circle cx="37" cy="52" r="3" fill="#e3faff"/>'
 };
 return '<svg viewBox="0 0 76 76" aria-hidden="true" xmlns="http://www.w3.org/2000/svg">'+(paths[kind]||paths.catalog)+'</svg>';
}
function homeTile(title,sub,type,dest,section,tag){
 return '<button class="shx-tile t-'+type+'" data-go="'+dest+'"'+(section?' data-go-section="'+section+'"':'')+'><span class="tile-visual">'+homeTileArt(type)+'</span><span class="tile-copy"><b>'+title+'</b><small>'+sub+'</small></span>'+(tag?'<span class="tile-tag">'+tag+'</span>':'')+'</button>';
}
let homeFarmData=null, farmJumpTarget='', lastWinsData=[];
function homeWinsHtml(){
 if(!lastWinsData.length)return '<div class="muted" style="font-size:12px">Пока нет редких выигрышей. Первые находки появятся здесь у всех игроков.</div>';
 return '<div class="shx-live-row">'+lastWinsData.slice(0,10).map(x=>'<div class="shx-live-card" data-tier="'+esc(x.reward_tier)+'"><div class="shx-live-title">'+esc(x.player)+'</div><div class="shx-live-name">'+esc(x.reward_name)+'</div><div class="shx-live-rarity">'+(x.origin==='farm'?'🌾 Ферма':'✦ Кейс / SPIN')+' • '+tierLabel(x.reward_tier)+'</div></div>').join('')+'</div>';
}
function home(){
 const u=me||{},f=homeFarmData||farmCachedData||{},display=String(u.username?'@'+u.username:u.first_name||'Игрок');
 return '<div class="shx-home">'+
 '<section class="shx-profile"><div class="shx-profile-top"><div class="shx-avatar">'+esc(display.replace(/^@/,'').charAt(0).toUpperCase()||'S')+'</div><div><div class="shx-username">'+esc(display)+'</div><button type="button" class="shx-user-sub" data-copy-token="'+esc(u.token||'')+'" style="background:none;border:0;padding:4px 0;color:#91c9e8;cursor:pointer;text-align:left">Жетон '+esc(u.token||'—')+' 📋</button></div><button class="shx-profile-quick" data-go="profile" aria-label="Профиль">⚙</button></div>'+
 '<div class="shx-wallets"><div class="shx-wallet">'+farmCoinIcon()+'<div><div class="shx-wallet-count">'+compactCurrency(f.shrek_coins||0)+'</div><div class="shx-wallet-name">ShrekCOIN</div></div></div>'+
 '<div class="shx-wallet">'+farmUcIcon()+'<div><div class="shx-wallet-count">'+compactCurrency(f.uc_available||0)+'</div><div class="shx-wallet-name">UC Credits</div></div></div>'+
 '<div class="shx-wallet"><div class="shx-star">✦</div><div><div class="shx-wallet-count">'+compactCurrency(f.shr||0)+'</div><div class="shx-wallet-name">SHR</div></div></div></div></section>'+
 '<div class="shx-caption">PUBG MOBILE · METRO ROYALE · ШРЕКСИЧ SHOP</div>'+
 '<div class="shx-tiles">'+
 homeTile('Каталог','Товары и услуги','catalog','catalog')+
 homeTile('Кейсы','Открывай за Stars','cases','spin')+
 homeTile('Рулетки','Крути колесо','spin','roulette')+
 homeTile('Ферма','Добывай ресурсы','farm','farm','','НОВИНКА')+
 homeTile('Награды','Активность и UC','tasks','farm','activity')+
 homeTile('Промокоды','Бонусные билеты','promo','spin')+
 homeTile('Вывод UC','Обмен UC Credits','uc','farm','uc')+
 homeTile('Продавцам','Стань поставщиком','catalog','seller')+
 
 '</div>'+
 '<section class="shx-live"><div class="shx-live-head"><span>LIVE ДРОПЫ</span><small><span class="shx-online"></span>Реальные находки игроков</small></div><div id="homeLiveCards">'+homeWinsHtml()+'</div></section>'+
 '<div class="shx-panel"><h3>Другие разделы</h3><div class="shx-profile-actions"><button data-go="inventory">🎒 Инвентарь</button><button data-go="orders">📦 Мои заказы</button><button data-go="referral">👥 Пригласить друзей</button><button data-go="settings">⚙ Настройки</button></div></div>'+
 '</div>';
}
function bindHome(){
 document.querySelectorAll('[data-go]').forEach(b=>b.addEventListener('click',()=>{farmJumpTarget=b.dataset.goSection||'';go(b.dataset.go)}));
 bindUserTokenCopy();
}

/* SUPPLIER MARKETPLACE — seller is bound to Telegram auth, not a nickname. */
async function sellerHtml(){
 const d=await api('/api/seller'),profile=d.profile;
 const top='<div class="seller-hero"><div class="seller-headline">SHREKSICH · PARTNERS</div><h1>🤝 Кабинет продавца</h1>'+
 '<div class="mini" style="color:#b9ddeb">Товары, заказы и комиссии под контролем магазина</div>'+
 '<div class="seller-feature-grid"><div><strong>70%</strong><small>Продавцу</small></div>'+
 '<div><strong>20%</strong><small>Магазину</small></div>'+
 '<div><strong>10%</strong><small>В резерв</small></div></div></div>';
 const calculator='<div class="shx-panel"><h3>⭐ Калькулятор комиссии</h3><div class="mini">Рассчитайте распределение Stars до публикации товара. Расчёт соответствует правилам реальных заказов.</div><div class="seller-inputs"><label>Цена товара в Stars<input id="sellerCalcPrice" type="number" min="1" max="1000000" value="100" inputmode="numeric"></label><label>Количество<input id="sellerCalcQty" type="number" min="1" max="1000" value="1" inputmode="numeric"></label></div><div id="sellerCalcResult" class="seller-income-row" aria-live="polite"></div><div class="mini">Предварительный расчёт, не выплата Stars.</div></div>';
 const sellerRulesHtml='<details class="shx-panel" style="margin-top:12px"><summary style="cursor:pointer;font-weight:800">📜 Правила продавцов · прочитать перед заявкой</summary><div class="mini" style="line-height:1.7;margin-top:12px"><b>1. Честные объявления.</b> Продавайте только товары и услуги, которые действительно можете предоставить. Указывайте точное описание, цену в Stars, количество и сроки передачи.<br><b>2. Законность и правила игры.</b> Запрещены мошенничество, краденые предметы и аккаунты, взлом, читы, передача чужих персональных данных и товары, нарушающие правила PUBG Mobile или Telegram.<br><b>3. Выполнение заказов.</b> После подтверждённой оплаты своевременно связывайтесь с покупателем, передавайте товар согласованным способом и сохраняйте доказательства выдачи. Не отмечайте заказ выполненным до фактической передачи.<br><b>4. Остатки и доступность.</b> Следите за количеством товаров. Если выдача временно невозможна — приостановите объявление и сообщите администрации об оплаченных заказах.<br><b>5. Общение и безопасность.</b> Общайтесь уважительно. Не запрашивайте пароли, коды Telegram, данные банковских карт и другие секреты. Не уводите оплаченные заказы за пределы площадки.<br><b>6. Споры и возвраты.</b> При проблеме с заказом незамедлительно уведомите администрацию, предоставьте подтверждения и содействуйте разрешению спора. Решения о возврате и компенсации принимаются после проверки.<br><b>7. Комиссия.</b> Для новых заказов действует распределение: 70% продавцу, 20% магазину, 10% в резерв, с округлением целых Stars. Начисление в кабинете — учёт обязательства, а не автоматическая выплата. Способ и сроки расчётов согласовываются с администрацией.<br><b>8. Модерация.</b> Администрация вправе отклонить заявку, снять объявление или ограничить продажи при нарушениях. Уже оплаченные обязательства при этом сохраняются.<br><b>9. Ответственность.</b> Продавец отвечает за достоверность информации, наличие товара и надлежащее исполнение заказа. Площадка может запрашивать доказательства выдачи.<br><b>10. Серьёзные нарушения и чёрный список.</b> За мошенничество, подделку доказательств выдачи, присвоение оплаченного товара, повторные обманы покупателей или другие серьёзные нарушения администрация вправе немедленно удалить продавца из маркетплейса, заблокировать его кабинет и внести в чёрный список без повторного допуска. Начисленные, но ещё не выплаченные Stars по спорным заказам могут быть заморожены на время проверки; их возврат или удержание определяется результатами разбирательства, правилами Telegram и применимым законодательством. Уже подтверждённые законные обязательства перед продавцом не аннулируются автоматически.<br><b>11. Доступ к игровым аккаунтам.</b> Покупатель самостоятельно решает, предоставлять ли продавцу доступ к своему игровому аккаунту, и принимает на себя риски добровольной передачи доступа третьему лицу: блокировка аккаунта, утрата предметов и прогресса, изменение настроек или потеря доступа. Шрексич выступает площадкой размещения предложений независимых продавцов и не получает пароли, коды подтверждения и резервные ключи. Никогда не передавайте пароль Telegram, одноразовые коды, банковские данные или доступ к почте. При подозрении на мошенничество немедленно сообщите администрации. Продавец отвечает за собственные действия и причинённый по его вине ущерб; площадка рассматривает обращения и принимает меры в пределах своих полномочий. Условия не ограничивают обязательные права покупателей и ответственность площадки, которую нельзя исключить по закону.</div></details>';
 const calculatorTop=top+calculator+sellerRulesHtml;
 if(!profile||profile.status==='removed')return calculatorTop+'<div class="shx-panel"><h3>🛍 Стать продавцом Шрексича</h3><p class="mini">Подайте заявку, дождитесь одобрения администратора и размещайте товары за Telegram Stars.</p><div class="seller-feature-grid"><div><strong>1</strong><small>Заявка</small></div><div><strong>2</strong><small>Одобрение</small></div><div><strong>3</strong><small>Продажи</small></div></div>'+ 
 '<div class="seller-inputs"><input id="sellerName" maxlength="72" placeholder="Имя магазина / продавца">'+
 '<input id="sellerContact" maxlength="120" placeholder="Контакт для связи (например, @username)">'+
 '<textarea id="sellerExperience" maxlength="700" placeholder="Какие товары поставляете, наличие и сроки выдачи"></textarea>'+
 '<label class="seller-accept"><input id="sellerRules" type="checkbox" aria-required="true"><span>Я прочитал(а) правила продавцов выше и принимаю их. Подтверждаю наличие товаров и ответственность за выполнение оплаченных заказов</span></label>'+
 '<button class="buy" id="sellerApply" disabled>🛍 СТАТЬ ПРОДАВЦОМ · ПОДАТЬ ЗАЯВКУ</button></div></div>';
 const status=profile.status==='approved'?'Одобрен':profile.status==='blocked'?'Заблокирован':'На рассмотрении';
 let html=calculatorTop+'<div class="shx-panel"><div class="row" style="align-items:center;justify-content:space-between"><h3>Ваш статус</h3><span class="seller-status-pill '+esc(profile.status)+'">'+status+'</span></div>'+
 '<div class="name">'+esc(profile.display_name)+'</div><div class="mini">Новые заказы: продавцу 70% · магазину 20% · резерву 10% от оплаченных Stars. По старым заказам действуют сохранённые доли.</div></div>';
 if(profile.status!=='approved')return html;
 html+='<div class="seller-help">✅ Вы зарегистрированы как продавец. Повторная заявка не требуется — добавляйте товары ниже.</div>';
 const orders=d.orders||[],settled=orders.filter(x=>x.settled),completed=orders.filter(x=>x.status==='Выполнен'&&!x.settled);
 const paidSum=settled.reduce((a,x)=>a+Number(x.seller_share_stars||0),0);
 const toSettle=completed.reduce((a,x)=>a+Number(x.seller_share_stars||0),0); const reserved=(d.payouts||[]).filter(x=>['pending','approved','ready','frozen'].includes(x.status)).reduce((a,x)=>a+Number(x.amount||0),0);
 html+='<div class="seller-income-row"><div><span>К РАСЧЁТУ · УЧЁТ ⭐</span><b>'+toSettle+' ⭐</b></div><div><span>ОТМЕЧЕНО РАСЧЁТОВ · ⭐</span><b>'+paidSum+' ⭐</b></div></div>'+
 '<div class="seller-help">Доли рассчитываются от оплаты за товар после скидок. Это учёт обязательств в эквиваленте Stars, а не автоматический перевод Stars. Расчёты проводит администрация отдельно.</div>'+
 '<div class="shx-panel"><h3>💸 Вывод средств</h3><div class="mini">Доступно к заявке: '+Math.max(0,toSettle-reserved)+' ⭐. После одобрения администратора действует ожидание 24 суток. Выплата только вручную после проверки.</div><div class="seller-inputs"><input id="sellerPayoutAmount" type="number" min="1" max="'+Math.max(0,toSettle-reserved)+'" placeholder="Сумма ⭐"><textarea id="sellerPayoutProof" maxlength="1500" placeholder="Обязательные доказательства передачи: ссылки на скриншоты/видео, номера заказов и описание"></textarea><textarea id="sellerPayoutDetails" maxlength="500" placeholder="Способ выплаты и реквизиты (не указывайте пароли или коды)"></textarea><button class="buy" id="sellerRequestPayout">💸 ЗАПРОСИТЬ ВЫВОД</button></div><h3>История заявок</h3>'+((d.payouts||[]).map(x=>'<div class="seller-market-card">#'+x.id+' · '+x.amount+' ⭐ · '+esc(x.status)+(x.available_at?'<div class="mini">Не ранее: '+new Date(x.available_at*1000).toLocaleString('ru-RU')+'</div>':'')+(x.reason?'<div class="mini">'+esc(x.reason)+'</div>':'')+'</div>').join('')||'<div class="mini">Заявок пока нет</div>')+'</div>'+
 '<div class="shx-panel"><h3>➕ Добавить товар</h3><div class="seller-inputs">'+
 '<input id="sellerListingName" maxlength="120" placeholder="Название товара">'+
 '<select id="sellerListingCategory"><option value="Metro Royale">🎒 Metro Royale · предметы</option><option value="Ресурсы">💎 Ресурсы</option><option value="Буст">🚀 Буст и помощь</option><option value="Квесты">🎯 Квесты</option><option value="Другое">📦 Другое</option></select>'+
 '<textarea id="sellerListingDesc" maxlength="1200" placeholder="Что получает покупатель? (необязательно)"></textarea>'+
 '<input id="sellerListingStars" type="number" min="1" max="100000" placeholder="Цена за 1 шт. в Stars">'+
 '<input id="sellerListingStock" type="number" min="1" max="1000" value="1" placeholder="Количество в наличии">'+
 '<button class="buy" id="sellerAddListing">📨 ОТПРАВИТЬ НА МОДЕРАЦИЮ</button></div></div>'+
 '<div class="mini">Товар появится в каталоге после одобрения администратором. О решении сообщит бот.</div><h3 style="margin:16px 0 7px">Ваши товары</h3>'+
 ((d.listings||[]).map(x=>'<div class="seller-market-card"><span class="seller-status-pill '+esc(x.seller_status)+'">'+esc(x.seller_status)+'</span>'+
 '<h3>'+esc(x.name)+'</h3><div class="mini">'+esc(x.category)+' · '+Number(x.stars_price)+' ⭐</div>'+
 '<div class="seller-stock-tag">Доступно: '+Number(x.seller_stock)+' шт.</div>'+
 '<div class="seller-market-actions"><input type="number" id="sellerRestock'+x.id+'" min="1" max="1000" placeholder="+ остаток" style="width:110px">'+
 '<button class="secondary" data-seller-restock="'+x.id+'">Пополнить</button>'+
 (x.seller_status==='active'?'<button class="secondary" data-seller-pause="'+x.id+'">⏸ Скрыть</button>':x.seller_status==='paused'?'<button class="secondary" data-seller-review="'+x.id+'">На повторную проверку</button>':'')+
 '</div></div>').join('')||'<div class="empty">Товаров пока нет</div>')+
 '<h3 style="margin:16px 0 7px">Оплаченные заказы</h3>'+
 (orders.map(x=>'<div class="seller-market-card"><div class="mini">#'+x.number+' · '+esc(x.status)+'</div>'+
 '<h3>'+esc(x.product_name)+'</h3><div class="mini">UID: '+esc(x.uid)+' · Ник: '+esc(x.nickname||'—')+'</div>'+
 (x.comment?'<div class="mini">Комментарий: '+esc(x.comment)+'</div>':'')+
 '<div class="seller-market-actions"><span class="seller-chip">Цена '+Number(x.stars_amount)+' ⭐</span>'+
 '<span class="seller-chip">Продавцу '+Number(x.seller_share_stars)+' ⭐</span>'+
 '<span class="seller-chip">Магазину '+(Number(x.platform_share_stars||0)-Number(x.reserve_share_stars||0))+' ⭐</span>'+
 '<span class="seller-chip">Резерв '+Number(x.reserve_share_stars||0)+' ⭐</span>'+
 (x.settled?'<span class="seller-status-pill approved">Расчёт отмечен</span>':'')+'</div>'+
 (['Оплачен','Принят','В работе'].includes(x.status)?'<div class="seller-inputs" style="margin-top:10px">'+
 '<textarea id="sellerProof'+x.id+'" maxlength="700" placeholder="Подтверждение выдачи: что и как передали покупателю"></textarea>'+
 '<button class="buy" data-seller-deliver="'+x.id+'">ПЕРЕДАНО ПОКУПАТЕЛЮ</button></div>':'')+
 (x.seller_delivery_note?'<div class="mini">Подтверждение: '+esc(x.seller_delivery_note)+'</div>':'')+'</div>').join('')||'<div class="empty">Новых оплаченных заказов нет</div>');
 return html;
}
function bindSeller(){
 const updateCalc=()=>{const p=Number(document.getElementById('sellerCalcPrice')?.value),q=Number(document.getElementById('sellerCalcQty')?.value),out=document.getElementById('sellerCalcResult');if(!out)return;if(!Number.isSafeInteger(p)||p<1||p>1000000||!Number.isSafeInteger(q)||q<1||q>1000){out.textContent='Укажите корректную цену и количество';return}const gross=p*q,fee=Math.ceil(gross*30/100),store=Math.min(fee,Math.ceil(gross*20/100)),reserve=fee-store,seller=gross-fee;out.innerHTML='<div><span>ВСЕГО</span><b>'+gross.toLocaleString('ru-RU')+' ⭐</b></div><div><span>ПРОДАВЦУ</span><b>'+seller.toLocaleString('ru-RU')+' ⭐</b></div><div><span>МАГАЗИНУ</span><b>'+store.toLocaleString('ru-RU')+' ⭐</b></div><div><span>РЕЗЕРВ</span><b>'+reserve.toLocaleString('ru-RU')+' ⭐</b></div>'};
 ['sellerCalcPrice','sellerCalcQty'].forEach(id=>document.getElementById(id)?.addEventListener('input',updateCalc));updateCalc();
 const refresh=async()=>{app.innerHTML=await sellerHtml();bindSeller();addHomeExit()};
 const consent=document.getElementById('sellerRules');
 if(consent){const submit=document.getElementById('sellerApply');const sync=()=>{if(submit)submit.disabled=!consent.checked};consent.addEventListener('change',sync);sync()}
 const apply=document.getElementById('sellerApply');
 if(apply)apply.addEventListener('click',async()=>{
  apply.disabled=true;
  try{await api('/api/seller/apply',{method:'POST',body:JSON.stringify({
   display_name:document.getElementById('sellerName').value,contact:document.getElementById('sellerContact').value,
   experience:document.getElementById('sellerExperience').value,rules_confirmed:document.getElementById('sellerRules').checked
  })});await refresh()}catch(e){alert(e.message);apply.disabled=false}
 });
 const payout=document.getElementById('sellerRequestPayout');if(payout)payout.addEventListener('click',async()=>{payout.disabled=true;try{await api('/api/seller/payouts',{method:'POST',body:JSON.stringify({amount:Number(document.getElementById('sellerPayoutAmount').value),proof:document.getElementById('sellerPayoutProof').value,payment_details:document.getElementById('sellerPayoutDetails').value})});await refresh()}catch(e){alert(e.message);payout.disabled=false}});
 const add=document.getElementById('sellerAddListing');
 if(add)add.addEventListener('click',async()=>{
  const name=document.getElementById('sellerListingName').value.trim(),price=Number(document.getElementById('sellerListingStars').value),stock=Number(document.getElementById('sellerListingStock').value);
  if(name.length<3){alert('Введите название товара — минимум 3 символа');return}
  if(!Number.isInteger(price)||price<1||price>100000){alert('Цена должна быть от 1 до 100 000 Stars');return}
  if(!Number.isInteger(stock)||stock<1||stock>1000){alert('Количество должно быть от 1 до 1000');return}
  add.disabled=true;try{await api('/api/seller/listings',{method:'POST',body:JSON.stringify({
   name:document.getElementById('sellerListingName').value,category:document.getElementById('sellerListingCategory').value,
   description:document.getElementById('sellerListingDesc').value,
   stars_price:Number(document.getElementById('sellerListingStars').value),
   stock:Number(document.getElementById('sellerListingStock').value)
  })});await refresh()}catch(e){alert(e.message);add.disabled=false}
 });
 document.querySelectorAll('[data-seller-pause]').forEach(btn=>btn.addEventListener('click',async()=>{
  if(!confirm('Скрыть товар от новых покупателей?'))return;
  btn.disabled=true;
  try{await api('/api/seller/listings/'+btn.dataset.sellerPause+'/pause',{method:'POST'});await refresh()}catch(e){alert(e.message);btn.disabled=false}
 }));
 document.querySelectorAll('[data-seller-review]').forEach(btn=>btn.addEventListener('click',async()=>{
  btn.disabled=true;
  try{await api('/api/seller/listings/'+btn.dataset.sellerReview+'/review',{method:'POST'});await refresh()}catch(e){alert(e.message);btn.disabled=false}
 }));
 document.querySelectorAll('[data-seller-restock]').forEach(btn=>btn.addEventListener('click',async()=>{
  const id=Number(btn.dataset.sellerRestock);
  btn.disabled=true;try{await api('/api/seller/listings/'+id+'/restock',{method:'POST',body:JSON.stringify({
   stock_to_add:Number(document.getElementById('sellerRestock'+id).value)
  })});await refresh()}catch(e){alert(e.message);btn.disabled=false}
 }));
 document.querySelectorAll('[data-seller-deliver]').forEach(btn=>btn.addEventListener('click',async()=>{
  const id=Number(btn.dataset.sellerDeliver);
  if(!confirm('Заказ действительно выдан покупателю?'))return;
  btn.disabled=true;try{await api('/api/seller/orders/'+id+'/delivered',{method:'POST',body:JSON.stringify({
   note:document.getElementById('sellerProof'+id).value
  })});await refresh()}catch(e){alert(e.message);btn.disabled=false}
 }));
}

function profileHtml(){
 const u=me||{},f=homeFarmData||farmCachedData||{},display=String(u.username?'@'+u.username:u.first_name||'Игрок');
 return '<div class="shx-page-title"><button class="shx-back" data-go="home">← Главная</button><h1>Профиль</h1></div>'+
 '<section class="shx-profile"><div class="shx-profile-top"><div class="shx-avatar">'+esc(display.replace(/^@/,'').charAt(0).toUpperCase()||'S')+'</div><div><div class="shx-username">'+esc(display)+'</div><button type="button" class="shx-user-sub" data-copy-token="'+esc(u.token||'')+'" style="background:none;border:0;padding:4px 0;color:#91c9e8;cursor:pointer;text-align:left">Жетон: '+esc(u.token||'—')+' 📋 Копировать</button></div></div>'+
 '<div class="shx-wallets"><div class="shx-wallet">'+farmCoinIcon()+'<div><div class="shx-wallet-count">'+compactCurrency(f.shrek_coins||0)+'</div><div class="shx-wallet-name">ShrekCOIN</div></div></div><div class="shx-wallet">'+farmUcIcon()+'<div><div class="shx-wallet-count">'+Number(f.uc_available||0)+'</div><div class="shx-wallet-name">UC Credits</div></div></div><div class="shx-wallet"><div class="shx-star">✦</div><div><div class="shx-wallet-count">'+Number(f.shr||0)+'</div><div class="shx-wallet-name">SHR</div></div></div></div></section>'+
 '<section class="shx-panel"><h3>Управление аккаунтом</h3><div class="shx-profile-actions"><button data-go="seller">🤝 Продавцам</button><button data-go="orders">📦 Мои заказы</button><button data-go="inventory">🎒 Инвентарь</button><button data-go="farm">🌾 Моя ферма</button><button data-go="referral">👥 Рефералы</button><button data-go="settings">⚙ Настройки</button><button data-go="support" class="shx-profile-support">💬 Поддержка'+(ucUnreadCount?'<span class="shx-unread-badge">'+ucUnreadCount+'</span>':'')+'</button></div></section>';
}
async function copyUserToken(value,button){
 if(!value)return;
 try{
  if(navigator.clipboard&&window.isSecureContext)await navigator.clipboard.writeText(value);
  else{const t=document.createElement('textarea');t.value=value;t.style.position='fixed';t.style.opacity='0';document.body.appendChild(t);t.select();const ok=document.execCommand('copy');t.remove();if(!ok)throw Error('copy')}
  const previous=button.textContent;button.textContent='✓ Жетон скопирован';setTimeout(()=>{if(button.isConnected)button.textContent=previous},1700);
 }catch(e){prompt('Скопируйте жетон:',value)}
}
function bindUserTokenCopy(){document.querySelectorAll('[data-copy-token]').forEach(b=>{if(b.dataset.copyBound)return;b.dataset.copyBound='1';b.addEventListener('click',()=>copyUserToken(b.dataset.copyToken,b))})}
function bindProfile(){document.querySelectorAll('[data-go]').forEach(b=>b.addEventListener('click',()=>go(b.dataset.go)));bindUserTokenCopy();}

function orderForm(id){
 const p=products.find(x=>Number(x.id)===Number(id));if(!p)return;
 app.innerHTML='<div class="hero"><div class="cat">'+esc(p.category)+'</div><h1>'+esc(p.name)+'</h1><div class="muted">'+esc(p.description)+'</div><div class="price" id="orderPrice">'+stars(p.stars_price)+'</div></div>'+
 '<div class="card"><b>Данные заказа</b>'+(Number(p.seller_id||0)>0?'<div class="seller-help"><b>⚠️ Безопасность аккаунта</b><div class="mini">Партнёр — независимый продавец. Передача ему доступа к игровому аккаунту добровольна и может привести к потере аккаунта, блокировке или утрате игровых предметов. Не передавайте пароли Telegram, коды входа, доступ к почте или банковские данные. Продавец отвечает за свои действия; обязательные права покупателя сохраняются.</div><label class="seller-accept"><input id="buyerPartnerConsent" type="checkbox"> Я ознакомился с рисками передачи доступа третьему лицу и понимаю, что Шрексич не запрашивает пароли и коды</label></div>':'')+'<input id="uid" placeholder="UID PUBG Mobile"><input id="nick" placeholder="Игровой ник"><textarea id="comment" placeholder="Комментарий к заказу"></textarea>'+
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
 const consent=document.getElementById('buyerPartnerConsent');
 if(consent&&!consent.checked){alert('Перед оформлением заказа ознакомьтесь с рисками и подтвердите согласие');return}
 const btn=document.getElementById('createOrderBtn');if(btn.disabled)return;btn.disabled=true;btn.textContent='Создаём заказ…';
 try{
  const o=await api('/api/orders',{method:'POST',body:JSON.stringify({product_id:id,uid:document.getElementById('uid').value,nickname:document.getElementById('nick').value,comment:document.getElementById('comment').value,promo_code:document.getElementById('promo').value})});
  showPay(o)
 }catch(e){btn.disabled=false;btn.textContent='Создать заказ';if(String(e.message).includes('не ответил')){alert('Соединение с сервером прервалось. Проверьте «Мои заказы» перед повторной попыткой — заказ мог сохраниться.');go('orders')}else alert(e.message)}
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
 const list=await api('/api/orders');
 if(!list.length)return '<div class="empty">У вас пока нет заказов.</div>';
 return '<h2>Мои заказы</h2>'+list.map(o=>{
  const unpaid=o.status==='Ожидает оплаты'&&!o.telegram_charge_id;
  const hold=Number(o.seller_reserved_until||0)-Math.floor(Date.now()/1000);
  const cancel=unpaid?'<button class="secondary" data-order-cancel="'+o.id+'" style="margin-top:9px;min-height:38px;width:100%">Отменить неоплаченный заказ</button>':'';
  const reserved=unpaid&&Number(o.seller_id||0)>0?
   '<div class="seller-availability">'+(hold>0?'Резерв товара: '+Math.ceil(hold/60)+' мин':'Время бронирования истекло')+'</div>':'';
  return '<div class="order"><div class="cat">ЗАКАЗ #'+o.number+
   (Number(o.seller_id||0)>0?' · ПАРТНЁР':'')+'</div><div class="name">'+esc(o.product_name)+
   '</div><div class="row"><div class="price">'+stars(o.stars_amount)+'</div>'+
   '<div style="text-align:right"><span class="status">'+esc(o.status)+'</span></div></div>'+
   (o.promo_code?'<div class="mini">Промокод: '+esc(o.promo_code)+' (-'+o.discount_percent+'%)</div>':'')+
   reserved+cancel+'</div>'
 }).join('')
}
function bindOrders(){
 document.querySelectorAll('[data-order-cancel]').forEach(btn=>btn.addEventListener('click',async()=>{
  if(!confirm('Отменить неоплаченный заказ и вернуть товар в наличие?'))return;
  btn.disabled=true;
  try{
   await api('/api/orders/'+btn.dataset.orderCancel+'/cancel',{method:'POST'});
   app.innerHTML=await ordersHtml();bindOrders();addHomeExit()
  }catch(e){alert(e.message);btn.disabled=false}
 }))
}

function showDropFx(reward){
 if(!reward||!['RED','GOLD','LEGENDARY','MYTHIC'].includes(reward.tier))return;
 const top=reward.tier==='GOLD'||reward.tier==='LEGENDARY';
 try{if(tg&&tg.HapticFeedback){tg.HapticFeedback.notificationOccurred('success');tg.HapticFeedback.impactOccurred('heavy')}}catch(_){}
 const fx=document.createElement('div');fx.className='drop-fx '+reward.tier.toLowerCase();
 fx.innerHTML='<div class="drop-card"><div class="drop-content"><h2>'+(top?'GOLD DROP!':'RED DROP!')+'</h2><div class="drop-name">'+esc(reward.name)+'</div>'+rarityBar(reward.tier)+'<div class="muted" style="margin-top:12px">Продажа: '+shrAmount(reward.points)+' SHR</div><button class="buy" id="closeDrop" style="margin-top:18px">ЗАБРАТЬ</button></div></div>';
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
 const labels={GRAY:'ОБЫЧНЫЙ',CYAN:'УЛУЧШЕННЫЙ',BLUE:'РЕДКИЙ',PURPLE:'ЭПИЧЕСКИЙ',PINK:'ЛЕГЕНДАРНЫЙ',RED:'МИФИЧЕСКИЙ',GOLD:'РЕЛИКТОВЫЙ',RAINBOW:'УНИКАЛЬНЫЙ',COMMON:'ОБЫЧНЫЙ',RARE:'РЕДКИЙ',EPIC:'ЭПИЧЕСКИЙ',LEGENDARY:'ЛЕГЕНДАРНЫЙ',MYTHIC:'МИФИЧЕСКИЙ'};
 return labels[String(tier||'').toUpperCase()]||String(tier||'')
}
function caseTierLabel(caseId,tier){
 const id=String(caseId||'').toUpperCase(),t=String(tier||'').toUpperCase();
 if(id==='CASE499'){
  if(t==='RED')return 'МИФИЧЕСКИЙ';
  if(t==='GOLD')return 'ЛЕГЕНДАРНЫЙ'
 }
 return tierLabel(t)
}
function caseIcon(kind){
 const k=String(kind||'crate').toLowerCase();
 const icons={
  crate:'<svg viewBox="0 0 32 32"><path d="M5 8h22v18H5z"/><path d="M5 13h22M10 8v18M22 8v18"/><path d="M10 13l12 13M22 13L10 26"/></svg>',
  helmet:'<svg viewBox="0 0 32 32"><path d="M6 17c0-7 4-12 10-12s10 5 10 12v6H15l-4-4H6z"/><path d="M15 23v4h8l3-4"/><path d="M10 10h12"/></svg>',
  airdrop:'<svg viewBox="0 0 32 32"><path d="M7 20h18v8H7z"/><path d="M10 20v8M22 20v8"/><path d="M16 4v16"/><path d="M6 10c2.2-4 5.6-6 10-6s7.8 2 10 6"/><path d="M6 10l10 4 10-4"/></svg>',
  vault:'<svg viewBox="0 0 32 32"><rect x="5" y="5" width="22" height="22" rx="3"/><circle cx="16" cy="16" r="6"/><path d="M16 10v4M16 18v4M10 16h4M18 16h4"/><path d="M8 9h3M21 9h3M8 23h3M21 23h3"/></svg>',
  crown:'<svg viewBox="0 0 32 32"><path d="M5 11l6 5 5-9 5 9 6-5-3 14H8z"/><path d="M8 25h16"/></svg>'
 };
 return '<div class="case-icon case-icon-'+esc(k)+'">'+(icons[k]||icons.crate)+'</div>'
}
function historySourceLabel(src){
 const s=String(src||'');
 if(s==='ticket')return '🎟 Билет рулетки';
 if(s==='free')return '🎡 Бесплатная рулетка';
 if(s==='donation_ticket')return '🎟️ Donation Ticket';
 if(s==='case_stars')return '⭐ Telegram Stars';
 if(s==='case_free')return '🎁 Бесплатный кейс';
 return '🎰 Кейс'
}
function tierChance(tier){
 const v=spinState&&spinState.tier_chances?spinState.tier_chances[String(tier||'').toUpperCase()]:0;
 return Number(v||0)
}
function rarityCatalogHtml(){
 const tiers=['GRAY','CYAN','BLUE','PURPLE','PINK','RED','GOLD'];
 return '<section class="rarity-catalog"><div class="rarity-catalog-head"><h3>Качество кубиков</h3><div class="mini"></div></div><div class="rarity-scroll">'+
 tiers.map(t=>{
   const count=(spinState.rewards||[]).filter(x=>x.tier===t).length;
   return '<button type="button" class="rarity-card" data-rarity-open="'+t+'"><div class="loot-cube '+cubeClass(t)+'"><span>?</span></div><div class="rarity-card-title '+tierClass(t)+'">'+tierLabel(t)+'</div><div class="rarity-card-chance">'+tierChance(t)+'%</div><div class="rarity-card-count">'+count+' предметов</div></button>'
 }).join('')+'</div></section><div class="rarity-modal hide" id="rarityModal"><div class="rarity-sheet" id="raritySheet"></div></div>'
}
function openRarityModal(tier){
 const modal=document.getElementById('rarityModal'),sheet=document.getElementById('raritySheet');
 if(!modal||!sheet)return;
 const items=(spinState.rewards||[]).filter(x=>x.tier===tier).slice().sort((a,b)=>Number(a.value_stars||0)-Number(b.value_stars||0));
 sheet.innerHTML='<div class="rarity-sheet-head">'+caseLootSticker(items[0]||{name:'Metro',tier},true)+'<div class="rarity-sheet-title"><h3 class="'+tierClass(tier)+'">'+tierLabel(tier)+'</h3><div class="muted">Шанс качества: '+tierChance(tier)+'% • '+items.length+' предметов</div></div><button type="button" class="rarity-close" id="rarityClose">Закрыть</button></div>'+
 '<div class="case-loot-details">'+items.map(caseLootCard).join('')+'</div>';
  modal.classList.remove('hide');
 const close=()=>modal.classList.add('hide');
 document.getElementById('rarityClose').addEventListener('click',close);
 modal.addEventListener('click',e=>{if(e.target===modal)close()},{once:true})
}
function bindRarityCatalog(){
 document.querySelectorAll('[data-rarity-open]').forEach(b=>b.addEventListener('click',()=>openRarityModal(b.dataset.rarityOpen)))
}

function caseIconMarkup(icon){
 const k=String(icon||'crate').toLowerCase();
 const paths={
  crate:'<path d="M5 10h22v16H5z"/><path d="M8 10l3-5h10l3 5M5 15h22M11 15v11M21 15v11"/><path d="M14 19h4"/>',
  helmet:'<path d="M6 18c0-7 4.7-12 11-12s11 5 11 12v3H16l-4 5H8v-5H6z"/><path d="M16 21v-5h12M11 10h12"/>',
  airdrop:'<path d="M6 11c3-7 19-7 22 0M8 11l7 8M26 11l-7 8"/><rect x="11" y="19" width="12" height="9" rx="2"/><path d="M11 23h12M17 19v9"/>',
  vault:'<rect x="5" y="5" width="24" height="24" rx="4"/><circle cx="17" cy="17" r="6"/><path d="M17 11v3M17 20v3M11 17h3M20 17h3M14 14l2 2M20 20l-2-2"/>',
  crown:'<path d="M6 24l2-14 7 7 5-10 5 10 7-7 2 14z"/><path d="M8 24h24v5H8z"/><circle cx="8" cy="10" r="1.4"/><circle cx="20" cy="7" r="1.4"/><circle cx="32" cy="10" r="1.4"/>'
 };
 return '<div class="case-icon case-icon-'+esc(k)+'"><svg viewBox="0 0 40 34" aria-hidden="true">'+(paths[k]||paths.crate)+'</svg></div>'
}

function caseItemArchetype(name){
 const n=String(name||'').toLowerCase();
 if(/metro cash|метро кэш|налич/.test(n))return 'cash';
 if(/ammo|патрон/.test(n))return 'ammo';
 if(/grenade|гранат|метательн/.test(n))return 'grenade';
 if(/med|аптеч|бинт|обезбол|adren|адреналин|stim|лечени/.test(n))return 'medical';
 if(/helmet|шлем/.test(n))return 'helmet';
 if(/armor|брон|жилет|plates/.test(n))return 'armor';
 if(/key|ключ/.test(n))return 'key';
 if(/weapon|оруж|прицел|дульн|рукоят|магазин/.test(n))return 'weapon';
 if(/repair|ремонт|детал|module|модул|полимер|металлолом|радиодетал|инструмент/.test(n))return 'tools';
 if(/energy|ration|энергет/.test(n))return 'ration';
 if(/pack|kit|bundle|рюкзак|сумка|снаряжен|booster/.test(n))return 'pack';
 if(/vault|case|crate|cache|box|supply|contraband|ящик/.test(n))return 'crate';
 return 'artifact';
}
function caseLootSticker(item,compact=false){
 const name=String(item?.name||'Metro Item'),tier=String(item?.tier||'GRAY').toUpperCase();
 let hash=2166136261;for(let i=0;i<name.length;i++)hash=Math.imul(hash^name.charCodeAt(i),16777619)>>>0;
 const gold=tier==='GOLD'||tier==='RED';
 const hue={GRAY:'#a8b9c7',CYAN:'#7cecf2',BLUE:'#81b7ff',PURPLE:'#d6a0ff',PINK:'#ff9fce',RED:'#ff8d97',GOLD:'#ffe18a'}[tier]||'#dbe6ef';
 const dark={GRAY:'#415769',CYAN:'#12687b',BLUE:'#255a9b',PURPLE:'#7043a4',PINK:'#ac477d',RED:'#aa3946',GOLD:'#a47727'}[tier]||'#364e61';
 const tag=String(name.match(/\b\d+(?:\.\d+)?[MK]\b/i)?.[0]||name.split(/\s+/).filter(Boolean).map(w=>w[0]).join('').slice(0,4)||'MR').slice(0,6).toUpperCase();
 const serial=String(hash%997).padStart(3,'0');
 const archetype=caseItemArchetype(name);
 let form='';
 if(archetype==='cash'){
  form='<path d="M15 47L58 29 89 44 46 64Z" fill="#192f2b" stroke="'+hue+'" stroke-width="2"/>'+
   '<path d="M14 31L57 13 89 30 46 49Z" fill="#2d7354" stroke="#afe9b4" stroke-width="3"/>'+
   '<path d="M14 38L57 20 89 37 46 56Z" fill="#39785b" stroke="#c7f4c0" stroke-width="2"/>'+
   '<path d="M17 42L60 24 87 38 44 58Z" fill="#438d65" stroke="#d2f8c8"/>'+
   '<path d="M45 28L60 24 72 31 57 38Z" fill="#b6dfb0"/><circle cx="53" cy="39" r="7" fill="none" stroke="#d1f0ba" stroke-width="2"/>'+
   '<path d="M42 26L53 32 53 59 44 63 44 38Z" fill="#d8b36b" stroke="#ffe5a6" stroke-width="2"/>';
 }else if(archetype==='medical'){
  form='<path d="M22 30L50 16 79 28 51 44Z" fill="'+hue+'" stroke="#f8fdff" stroke-width="2"/>'+
   '<path d="M22 30V68L51 82V44Z" fill="'+dark+'" stroke="'+hue+'" stroke-width="3"/>'+
   '<path d="M79 28V67L51 82V44Z" fill="#203a4a" stroke="'+hue+'" stroke-width="3"/>'+
   '<path d="M33 48H41V40L47 43V51H55V59H47V67L41 64V56H33Z" fill="#f6f7f4"/>'+
   '<path d="M43 18V13Q51 7 59 13V22" fill="none" stroke="#d9f7ff" stroke-width="4"/>';
 }else if(archetype==='armor'){
  form='<path d="M23 22L40 15 51 26 64 15 81 22 73 48 70 77 31 77 29 46Z" fill="'+dark+'" stroke="'+hue+'" stroke-width="4"/>'+
   '<path d="M40 19L51 30 64 19 68 37 58 44 58 72 42 72 42 44 34 36Z" fill="'+hue+'" opacity=".75"/>'+
   '<path d="M40 46H62V67H40Z" fill="#17253a" stroke="#f7ecda" stroke-width="2"/>'+
   '<path d="M41 51H61M41 57H61M41 63H61" stroke="'+hue+'" stroke-width="2"/>';
 }else if(archetype==='helmet'){
  form='<path d="M16 53Q13 23 50 17Q86 20 85 53L75 61H61L51 72 41 61H26Z" fill="'+dark+'" stroke="'+hue+'" stroke-width="4"/>'+
   '<path d="M24 48Q28 26 50 27Q72 26 77 48Z" fill="#314c68" stroke="#c8deef" stroke-width="2"/>'+
   '<path d="M26 52H76L65 62H46L38 69H26Z" fill="#071923" stroke="'+hue+'" stroke-width="2"/>'+
   '<path d="M32 31L41 27M59 27L69 31" stroke="#fff9d1" stroke-width="3" opacity=".7"/>';
 }else if(archetype==='weapon'){
  form='<g transform="rotate(-17 50 50)"><path d="M13 35H69V44H81V51H67V56H48L39 73H28L36 55H20Z" fill="'+dark+'" stroke="'+hue+'" stroke-width="3"/>'+
   '<path d="M22 30H65V35H22Z" fill="#d5e4f0" stroke="'+hue+'" stroke-width="2"/><path d="M67 35H94V41H67Z" fill="#c5d6e1"/>'+
   '<path d="M39 56L51 58 47 78H35Z" fill="#31465e" stroke="'+hue+'" stroke-width="2"/>'+
   '<path d="M30 28L35 19H58L64 28" fill="none" stroke="#c8e4f3" stroke-width="3"/></g>';
 }else if(archetype==='ammo'){
  form='<path d="M24 73V34L35 22 44 33V73Z" fill="#ba8b40" stroke="#ffe5a5" stroke-width="3"/>'+
   '<path d="M44 77V26L55 12 66 26V77Z" fill="'+dark+'" stroke="'+hue+'" stroke-width="3"/>'+
   '<path d="M64 72V39L75 25 85 39V72Z" fill="#b7813f" stroke="#ffe5b0" stroke-width="3"/>'+
   '<path d="M24 55H44M44 51H66M64 56H85" stroke="#ffe4a0" stroke-width="4"/>';
 }else if(archetype==='grenade'){
  form='<path d="M38 18H63V29H38Z" fill="#859cac" stroke="#eafaff" stroke-width="2"/>'+
   '<path d="M50 13V7H68L73 17" fill="none" stroke="#b9dbeb" stroke-width="4"/>'+
   '<rect x="25" y="27" width="50" height="52" rx="18" fill="'+dark+'" stroke="'+hue+'" stroke-width="4"/>'+
   '<path d="M26 45H74M26 59H74M44 28V79M58 28V79" stroke="'+hue+'" stroke-width="3"/>';
 }else if(archetype==='key'){
  form='<g transform="rotate(-28 50 50)"><circle cx="37" cy="26" r="16" fill="none" stroke="'+hue+'" stroke-width="8"/>'+
   '<circle cx="37" cy="26" r="7" fill="#132a3f"/><path d="M37 43V87H48V76H56V67H48V56H42" fill="'+dark+'" stroke="'+hue+'" stroke-width="4"/></g>';
 }else if(archetype==='tools'){
  form='<circle cx="50" cy="45" r="26" fill="'+dark+'" stroke="'+hue+'" stroke-width="6" stroke-dasharray="9 5"/>'+
   '<circle cx="50" cy="45" r="15" fill="#1e3548" stroke="#e1eaf1" stroke-width="3"/>'+
   '<circle cx="50" cy="45" r="6" fill="'+hue+'"/>'+
   '<path d="M18 78L76 20" stroke="#d4a571" stroke-width="8" stroke-linecap="round"/>'+
   '<path d="M69 12L87 29L79 40L61 22Z" fill="#bfd0df" stroke="#f6f9ff" stroke-width="2"/>';
 }else if(archetype==='ration'){
  form='<path d="M24 25L72 25 79 73 20 73Z" fill="'+dark+'" stroke="'+hue+'" stroke-width="4"/>'+
   '<path d="M23 27Q50 13 76 27" fill="none" stroke="#fff5df" stroke-width="4"/>'+
   '<circle cx="50" cy="52" r="14" fill="#61965b" stroke="#e4f3ac" stroke-width="3"/>'+
   '<path d="M44 53Q49 38 56 50M39 60L59 43" stroke="#e6f7bf" stroke-width="3" fill="none"/>';
 }else if(archetype==='pack'){
  form='<rect x="24" y="21" width="53" height="61" rx="10" fill="'+dark+'" stroke="'+hue+'" stroke-width="4"/>'+
   '<path d="M36 21V15Q51 5 65 16V21" fill="none" stroke="#ecdbb4" stroke-width="4"/>'+
   '<rect x="31" y="44" width="39" height="31" rx="6" fill="#234052" stroke="'+hue+'" stroke-width="3"/>'+
   '<path d="M38 44V33M64 44V33M32 58H70" stroke="#dfe6e8" stroke-width="3"/>'+
   '<circle cx="50" cy="58" r="5" fill="'+hue+'"/>';
 }else if(archetype==='crate'){
  form='<path d="M14 33L48 17 85 36 51 53Z" fill="'+hue+'" stroke="#fff3cd" stroke-width="2.8"/>'+
   '<path d="M14 33V71L51 89V53Z" fill="'+dark+'" stroke="'+hue+'" stroke-width="3"/>'+
   '<path d="M85 36V72L51 89V53Z" fill="#1f354a" stroke="'+hue+'" stroke-width="3"/>'+
   '<path d="M26 27L63 45V82M36 23L73 41M25 39V76M73 44V77" fill="none" stroke="#d7bc8a" stroke-width="4"/>'+
   '<path d="M30 58L41 64M60 66L75 58" stroke="'+hue+'" stroke-width="4"/>';
 }else{
  form='<path d="M50 9L75 29 84 57 62 83 36 83 16 57 25 29Z" fill="'+dark+'" stroke="'+hue+'" stroke-width="5"/>'+
   '<path d="M50 9L50 67L16 57M50 67L84 57M25 29L75 29" fill="none" stroke="'+hue+'" stroke-width="3"/>'+
   '<circle cx="50" cy="46" r="11" fill="#8acaca" stroke="#e1ffff" stroke-width="3"/>';
 }
 const rays=hash%3===0?'<path d="M13 16L22 20M78 12L84 21M11 74L20 70" stroke="'+hue+'" stroke-width="3" stroke-linecap="round"/>':hash%3===1?'<circle cx="18" cy="20" r="3" fill="'+hue+'"/><circle cx="79" cy="17" r="4" fill="'+hue+'"/>':'<path d="M15 16L20 24L25 16M75 15L80 23L85 15" stroke="'+hue+'" stroke-width="3" fill="none"/>';
 const svg='<svg viewBox="0 0 100 100" role="img" aria-label="'+esc(name)+'">'+
 '<ellipse cx="50" cy="89" rx="35" ry="5" fill="#000" opacity=".4"/>'+rays+form+
 '<rect x="12" y="82" width="76" height="14" rx="5" fill="#102132" stroke="'+hue+'" stroke-width="1.8"/>'+
 '<text x="43" y="92" font-size="10" font-family="Arial,sans-serif" font-weight="900" text-anchor="middle" fill="'+hue+'">'+esc(tag)+'</text>'+
 '<text x="81" y="92" font-size="7" font-family="Arial,sans-serif" font-weight="800" text-anchor="end" fill="#c8d4de">'+serial+'</text>'+
 (gold?'<path d="M80 9L83 20L94 23L83 26L80 38L77 26L67 23L77 20Z" fill="#fff2b3" opacity=".9"/>':'')+
 '</svg>';
 return '<div class="case-loot-sticker'+(compact?' compact':'')+'" data-tier="'+esc(tier)+'" title="'+esc(name)+'">'+svg+'</div>';
}
function caseLootCard(item){
 return '<div class="case-loot-card" data-tier="'+esc(item.tier)+'">'+caseLootSticker(item,true)+
 '<div style="min-width:0"><div class="case-loot-card-name">'+esc(item.name)+'</div><div class="case-loot-card-meta">'+tierLabel(item.tier)+' • '+Number(item.value_stars||0).toLocaleString('ru-RU')+' SHR</div></div></div>';
}
function caseItemsOf(cfg){
 const allowed=new Set(cfg?.contents||[]);
 return (spinState?.rewards||[]).filter(x=>allowed.has(x.name)).slice().sort((a,b)=>Number(a.value_stars)-Number(b.value_stars)||a.name.localeCompare(b.name,'ru'));
}
function caseItemCountText(n){
 const count=Number(n)||0,part=count%100,tail=count%10;
 return count+' '+(part>=11&&part<=14?'предметов':tail===1?'предмет':tail>=2&&tail<=4?'предмета':'предметов');
}
function caseSelectedPreview(cfg){
 if(!cfg)return '';
 const all=caseItemsOf(cfg);
 if(!all.length)return '';
 // Distinct tier sampler, followed by a few inexpensive rewards. Display in ascending price order.
 const tierSamples=[],seen=new Set();
 for(const r of all){if(!seen.has(r.tier)){seen.add(r.tier);tierSamples.push(r)}}
 for(const r of all){if(tierSamples.length>=6)break;if(!tierSamples.includes(r))tierSamples.push(r)}
 tierSamples.sort((a,b)=>a.value_stars-b.value_stars);
 return '<div class="shx-panel case-prizes-panel" style="margin-top:13px"><h3 style="margin:0 0 5px">🎁 Предметы кейса «'+esc(cfg.name)+'»</h3>'+
 '<div class="muted" style="font-size:11px"></div>'+
 '<div class="case-loot-grid">'+tierSamples.map(caseLootCard).join('')+'</div>'+
 '<button type="button" class="secondary case-view-all" aria-expanded="false" aria-controls="spinAllItemsContent" id="spinAllItems">Показать все '+caseItemCountText(all.length)+' и шансы ↓</button>'+
 '<div class="case-all-items hide" id="spinAllItemsContent"></div></div>';
}

function spinSourceLabel(source){
 const s=String(source||'');
 if(s==='ticket')return '🎟 Билет рулетки';
 if(s==='free')return '🎡 Бесплатная рулетка';
 if(s==='donation_ticket'||s.startsWith('donation_ticket:'))return '<span class="blue-ticket">🎫 Donation Ticket</span>';
 if(s==='case_stars'||s.startsWith('case_stars:'))return '⭐ Stars-кейс';
 if(s==='case_free'||s.startsWith('case_free:'))return '🎁 Бесплатный кейс';
 return '🎰 Кейс'
}

function selectedCase(){
 const cases=(spinState&&spinState.case_catalog)||[];
 let cfg=cases.find(x=>x.id===selectedCaseId);
 if(!cfg){cfg=cases[0]||null;selectedCaseId=cfg?cfg.id:''}
 return cfg
}
function caseVisualTier(cfg){
 if(!cfg||!cfg.tiers||!cfg.tiers.length)return 'GRAY';
 const order=['GRAY','CYAN','BLUE','PURPLE','PINK','RED','GOLD'];
 return cfg.tiers.map(x=>x.tier).sort((a,b)=>order.indexOf(b)-order.indexOf(a))[0]||'GRAY'
}
function spinCasePickerHtml(){
 const cases=(spinState&&spinState.case_catalog)||[];
 if(!cases.length)return '';
 return '<section class="spin-case-picker"><h3>Выберите кейс</h3><div class="spin-case-scroll">'+cases.map(c=>{
  const active=c.id===selectedCaseId;
  const odds=(c.tiers||[]).map(t=>'<span class="'+tierClass(t.tier)+'">'+caseTierLabel(c.id,t.tier)+' '+Number(t.chance||0)+'%</span>').join('');
  const ticket=Number(c.donation_tickets||0);
  return '<button type="button" class="spin-case-card '+(active?'active':'')+'" data-spin-case="'+esc(c.id)+'" '+(spinState.pending_drop?'disabled':'')+'>'+
   '<div class="spin-case-top">'+caseIconMarkup(c.icon)+'<div class="spin-case-copy"><div class="spin-case-title">'+esc(c.name)+'</div><div class="spin-case-price">'+esc(c.price_label)+'</div></div></div>'+
   '<div class="spin-case-desc">'+esc(c.description||'Metro Royale кейс')+'</div><div class="spin-case-odds">'+odds+'</div>'+
   (ticket>0&&c.id!=='FREE'?'<div class="spin-case-ticket">🎫 '+ticket+' Donation Ticket</div>':'')+'</button>'
 }).join('')+'</div><div class="spin-case-note"></div></section>'
}
function bindSpinCasePicker(){
 document.querySelectorAll('[data-spin-case]').forEach(b=>b.addEventListener('click',async()=>{
  if(spinNavigationLocked||spinState?.pending_drop)return;
  selectedCaseId=b.dataset.spinCase||'CASE29';
  localStorage.setItem('shx_selected_case',selectedCaseId);
  app.innerHTML=await spinHtml();bindSpin();addHomeExit()
 }))
}

function reelVisualPool(cfg){
 const items=caseItemsOf(cfg);
 const tierPools=(cfg?.tiers||[]).map(t=>({tier:t.tier,chance:Number(t.chance||0),items:items.filter(i=>i.tier===t.tier)}))
  .filter(x=>x.chance>0&&x.items.length>0);
 return {items,tierPools,total:tierPools.reduce((sum,x)=>sum+x.chance,0)};
}
function randomReelPrize(pool){
 if(!pool?.items?.length)return null;
 if(!pool.tierPools.length||pool.total<=0)return pool.items[Math.floor(Math.random()*pool.items.length)];
 let r=Math.random()*pool.total;
 let selected=pool.tierPools[pool.tierPools.length-1];
 for(const tier of pool.tierPools){r-=tier.chance;if(r<=0){selected=tier;break}}
 return selected.items[Math.floor(Math.random()*selected.items.length)]||pool.items[0];
}
function reelItemHtml(item,extra=''){
 if(!item)return '<div class="reel-item reel-item-empty">НЕТ ПРЕДМЕТОВ</div>';
 return '<div class="reel-item reel-item-prize '+extra+'" data-tier="'+esc(item.tier)+'">'+
  caseLootSticker(item,true)+'<span class="reel-prize-name" title="'+esc(item.name)+'">'+esc(item.name)+'</span></div>';
}
function selectedCaseIdleStrip(){
 const pool=reelVisualPool(selectedCase());
 return Array.from({length:10},()=>reelItemHtml(randomReelPrize(pool))).join('');
}


const ROULETTE_COLORS={GRAY:'#778695',CYAN:'#22a6c8',BLUE:'#3c76d9',PURPLE:'#865bc7',PINK:'#d562ae',RED:'#db5760',GOLD:'#e5b843'};
const ROULETTE_LABELS={GRAY:'СЕРЫЙ',CYAN:'ГОЛУБОЙ',BLUE:'СИНИЙ',PURPLE:'ФИОЛЕТ',PINK:'РОЗОВЫЙ',RED:'КРАСНЫЙ',GOLD:'ЗОЛОТО'};
let rouletteLastAngle=0,rouletteSlices=[];
function makeRouletteWheel(cfg){
 const ts=(cfg?.tiers||[]).filter(t=>ROULETTE_COLORS[t.tier]&&Number(t.chance)>0);
 const total=ts.reduce((a,t)=>a+Number(t.chance),0);
 if(!total)return {slices:[],bg:'conic-gradient(#243b5a 0 360deg)',labels:'',legend:''};
 let pos=0;const slices=[],stops=[],labels=[],legend=[];
 for(const t of ts){
  const span=360*Number(t.chance)/total,from=pos,parts=Math.max(1,Math.round(span/26));
  for(let i=0;i<parts;i++){
   const end=i===parts-1?from+span:pos+span/parts;
   const shade=(i%2)?{'GRAY':'#929caa','CYAN':'#42bddb','BLUE':'#6595e9','PURPLE':'#a177de','PINK':'#ed7bc5','RED':'#ec7680','GOLD':'#ffe286'}[t.tier]:ROULETTE_COLORS[t.tier];
   const edge=Math.min(.9,(end-pos)/12);
   stops.push(shade+' '+pos.toFixed(4)+'deg '+(end-edge).toFixed(4)+'deg','#14263e '+(end-edge).toFixed(4)+'deg '+end.toFixed(4)+'deg');
   slices.push({tier:t.tier,start:pos,end});pos=end;
  }
  if(span>16){
   const mid=(from+span/2)*Math.PI/180;
   const x=(50+32*Math.sin(mid)).toFixed(2),y=(50-32*Math.cos(mid)).toFixed(2);
   labels.push('<span class="roul-label" style="left:'+x+'%;top:'+y+'%">'+ROULETTE_LABELS[t.tier]+'<small>'+Number(t.chance)+'%</small></span>');
  }
  legend.push('<span><i style="background:'+ROULETTE_COLORS[t.tier]+'"></i>'+tierLabel(t.tier)+' '+Number(t.chance)+'%</span>');
 }
 return {slices,bg:'conic-gradient(from 0deg,'+stops.join(',')+')',labels:labels.join(''),legend:legend.join('')};
}

/* Roulette spin uses server-side results. Rotation, melody, skipping are only presentation. */
const ROULETTE_STANDARD_MS=11500;
let rouletteSpinBusy=false,rouletteSkipRequested=false,rouletteMusicTimer=null;
function rouletteEase(progress){
 const p=Math.min(1,Math.max(0,progress)),acc=.12,cruise=.46,brake=1-cruise;
 const total=acc/2+(cruise-acc)+brake/3;
 if(p<=acc)return (p*p/(2*acc))/total;
 if(p<=cruise)return (acc/2+(p-acc))/total;
 const u=(p-cruise)/brake;
 return (acc/2+cruise-acc+brake*(u-u*u+u*u*u/3))/total;
}
function rouletteMusicStop(){
 if(rouletteMusicTimer!==null){clearTimeout(rouletteMusicTimer);rouletteMusicTimer=null}
}
function rouletteMusicStart(totalMs){
 rouletteMusicStop();
 if(!soundsEnabled())return;
 const melody=[392,493.88,587.33,659.25,587.33,493.88,440,523.25,659.25,783.99,698.46,523.25,440,392,493.88,587.33];
 const bass=[196,174.61,220,164.81];
 const started=performance.now();
 let noteIndex=0;
 function melodyLoop(){
  if(!rouletteSpinBusy||rouletteSkipRequested||!soundsEnabled()){rouletteMusicTimer=null;return}
  const progress=Math.min(1,(performance.now()-started)/totalMs);
  const freq=melody[noteIndex%melody.length];
  const vol=progress>.72?Math.max(.009,.029*(1-progress)):.029;
  tone(freq,.16+progress*.16,vol,'triangle');
  if(noteIndex%2===0)tone(freq/2,.24,.016,'sine',.024);
  if(noteIndex%4===0)tone(bass[Math.floor(noteIndex/4)%bass.length],.35,.018,'sine',.02);
  if(noteIndex%8===7)tone(freq*1.5,.12,.011,'sine',.07);
  noteIndex++;
  if(progress<.99)rouletteMusicTimer=setTimeout(melodyLoop,Math.round(215+progress*235));
  else rouletteMusicTimer=null;
 }
 melodyLoop();
}
function rouletteSectorTick(){
 if(!soundsEnabled())return;
 tone(930,.025,.014,'triangle');
 tone(510,.036,.008,'sine',.012);
}
function animateRouletteWheel(wheel,start,end,duration,progressBar,statusText){
 return new Promise(resolve=>{
  const startAt=performance.now();
  let lastSector=-1,lastTick=0;
  function frame(now){
   if(rouletteSkipRequested){
    wheel.style.transform='rotate('+end+'deg)';
    if(progressBar)progressBar.style.width='100%';
    resolve('skipped');return;
   }
   const p=Math.max(0,Math.min(1,(now-startAt)/duration));
   const angle=start+(end-start)*rouletteEase(p);
   wheel.style.transform='rotate('+angle+'deg)';
   if(progressBar)progressBar.style.width=Math.round(p*100)+'%';
   if(statusText)statusText.textContent=p<.12?'⚡ Разгон колеса…':p<.55?'🎵 Колесо вращается…':p<.9?'✨ Плавно замедляется…':'🎯 Почти остановилось…';
   const atPointer=(360-((angle%360)+360)%360)%360;
   const index=rouletteSlices.findIndex(x=>atPointer>=x.start && atPointer<x.end);
   if(index!==lastSector){
    if(lastSector>=0&&now-lastTick>78){rouletteSectorTick();lastTick=now}
    lastSector=index;
   }
   if(p>=1){resolve('complete');return}
   requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
 });
}

async function rouletteHtml(){
 spinState=await api('/api/spin/state');
 const cfg=spinState.roulette,enabled=!!(cfg&&cfg.active),pending=spinState.pending_drop,paid=spinState.paid_case_opening;
 const wheel=makeRouletteWheel(cfg);rouletteSlices=wheel.slices;
 const free=Number(spinState.free_remaining||0),ticket=Number(spinState.bonus_tickets||0);
 const ready=enabled&&!pending&&!paid&&(free+ticket)>0;
 const hubMain=pending?'ПРИЗ':paid?'КЕЙС':!enabled?'ЗАКРЫТО':ready?'КРУТИТЬ':'ОЖИДАНИЕ';
 const hubSub=pending?'ЗАБЕРИ':paid?'ЗАБЕРИ':!enabled?'НЕДОСТУПНО':free>0?'БЕСПЛАТНО':ticket>0?'ЗА БИЛЕТ':'НЕТ СПИНОВ';
 const note=pending?'Приз уже выпал: сначала сохраните или продайте его.':paid?'Сначала заберите оплаченный кейс во вкладке «Кейсы».':!enabled?'Рулетка отключена администратором.':free>0?'Вращение бесплатное. Результат выбирает сервер.':ticket>0?'Будет использован один бонусный билет.':'Следующая бесплатная прокрутка через '+formatReset(spinState.next_reset_seconds);
 const history=(spinState.history||[]).filter(x=>x.source==='free'||x.source==='ticket').slice(0,5).map(x=>'<div class="order"><div class="name">'+esc(x.reward_name)+'</div><div class="mini">'+tierLabel(x.reward_tier)+'</div></div>').join('');
 const rouletteSkipDefault=localStorage.getItem('shx_roulette_skip_v1')==='1';
 const rouletteSoundEnabled=soundsEnabled();
 return '<div class="roul-page"><section class="hero roul-hero"><div class="cat">МЕТРО · КОЛЕСО ФОРТУНЫ</div><h1>Бесплатная <span class="gold">рулетка</span></h1><div class="muted"></div></section>'+
 '<section class="roul-box"><div class="roul-stage"><div class="roul-wheel" id="roulWheel" style="background:'+wheel.bg+';transform:rotate('+(rouletteLastAngle%360)+'deg)">'+wheel.labels+'</div><button type="button" class="roul-hub roul-hub-action" id="roulSpin" aria-label="Крутить колесо фортуны" '+(ready?'':'disabled')+'><span class="roul-hub-title">ШРЕКСИЧ</span><strong class="roul-hub-main" id="roulHubMain">'+hubMain+'</strong><small class="roul-hub-sub" id="roulHubSub">'+hubSub+'</small></button><div class="roul-pointer"></div></div>'+
 '<div class="roul-legend">'+wheel.legend+'</div>'+
 '<div class="roul-stats"><div class="roul-stat"><small>БЕСПЛАТНО</small><b>'+free+' / '+Number(spinState.max_free_spins||0)+'</b></div><div class="roul-stat"><small>БИЛЕТЫ</small><b>🎟 '+ticket+'</b></div><div class="roul-stat"><small>SHR</small><b>'+shrAmount(spinState.shr||0)+'</b></div></div>'+

 '<div class="roul-options"><label class="roul-option"><input type="checkbox" id="roulSkipPref" '+(rouletteSkipDefault?'checked':'')+'><span>⏩ Пропускать анимацию</span></label><label class="roul-option"><input type="checkbox" id="roulMusicPref" '+(rouletteSoundEnabled?'checked':'')+'><span>🔊 Мелодия и щелчки</span></label></div>'+ 
 '<button type="button" class="roul-skip-now hide" id="roulSkipNow">⏭ Пропустить прокрутку</button><div class="roul-progress hide" id="roulProgress"><i id="roulProgressBar"></i></div><div class="roul-spin-status" id="roulStatus" role="status" aria-live="polite"></div>'+
 '<div class="spin-lock-note" id="spinLockNote"></div><div class="roul-hint"><div style="margin-top:4px">'+note+'</div></div><div class="roul-result" id="roulResult"></div></section>'+
 '<button id="roulCases" class="roul-route">📦 Перейти к платным кейсам</button>'+
 '<div class="shx-panel"><h3>🎟 Промокод на прокрутки</h3><div class="row"><input id="spinPromoCode" placeholder="Промокод"><button class="secondary" id="spinPromoBtn">Активировать</button></div><div class="mini" id="spinPromoInfo"></div></div>'+
 '<div class="shx-panel"><h3>Последние выигрыши рулетки</h3>'+(history||'<div class="empty">Здесь появятся ваши награды.</div>')+'</div></div>';
}
function rouletteAngleFor(tier){
 const matches=rouletteSlices.filter(x=>x.tier===tier);
 if(!matches.length)return rouletteLastAngle%360;
 const pick=matches[Math.floor(Math.random()*matches.length)];
 return ((360-(pick.start+pick.end)/2)%360+360)%360;
}
function setRouletteHubLabel(main,sub){
 const title=document.getElementById('roulHubMain'),subtitle=document.getElementById('roulHubSub');
 if(title)title.textContent=main;
 if(subtitle)subtitle.textContent=sub;
}
function bindRoulette(){
 const play=document.getElementById('roulSpin');if(play&&!play.disabled)play.addEventListener('click',rollRoulette);
 const cases=document.getElementById('roulCases');if(cases)cases.addEventListener('click',()=>go('spin'));
 const promo=document.getElementById('spinPromoBtn');if(promo)promo.addEventListener('click',applySpinPromo);
 const skipPref=document.getElementById('roulSkipPref');if(skipPref)skipPref.addEventListener('change',()=>localStorage.setItem('shx_roulette_skip_v1',skipPref.checked?'1':'0'));
 const musicPref=document.getElementById('roulMusicPref');if(musicPref)musicPref.addEventListener('change',()=>setSoundEnabled(musicPref.checked));
 const skipNow=document.getElementById('roulSkipNow');if(skipNow)skipNow.addEventListener('click',()=>{if(!rouletteSpinBusy||rouletteSkipRequested)return;rouletteSkipRequested=true;skipNow.disabled=true;skipNow.textContent='Завершаем прокрутку…';rouletteMusicStop()});
 const p=spinState?.pending_drop;
 if(p?.reward&&String(p.source||'').startsWith('case:')){
  const result=document.getElementById('roulResult');
  if(result)result.innerHTML='<div class="muted">У вас остался незабранный предмет из кейса. Вернитесь в «Кейсы», чтобы сохранить или продать его.</div>';
 }else if(p?.reward){
  const wheel=document.getElementById('roulWheel'),result=document.getElementById('roulResult');
  rouletteLastAngle=rouletteAngleFor(p.reward.tier);
  if(wheel)wheel.style.transform='rotate('+rouletteLastAngle+'deg)';
  if(result)revealReward(result,p);
 }
}
async function rollRoulette(){
 const btn=document.getElementById('roulSpin'),wheel=document.getElementById('roulWheel'),result=document.getElementById('roulResult');
 if(!btn||btn.disabled||!wheel||!result||spinNavigationLocked||rouletteSpinBusy)return;
 const stage=document.querySelector('.roul-stage'),status=document.getElementById('roulStatus');
 const skipNow=document.getElementById('roulSkipNow'),progress=document.getElementById('roulProgress'),bar=document.getElementById('roulProgressBar');
 const skipPref=document.getElementById('roulSkipPref'),musicPref=document.getElementById('roulMusicPref');
 const promo=document.getElementById('spinPromoBtn'),paidCases=document.getElementById('roulCases');
 // Unlock audio on the actual button click: Telegram iOS restricts audio started after async requests.
 if(soundsEnabled()){unlockAudio();beginAudioHold()}
 const skipByDefault=!!skipPref?.checked;
 rouletteSpinBusy=true;rouletteSkipRequested=false;
 btn.disabled=true;btn.classList.add('roul-hub-working');setRouletteHubLabel('ЖДЁМ…','ПРИЗ');
 if(skipPref)skipPref.disabled=true;
 if(musicPref)musicPref.disabled=true;
 if(promo)promo.disabled=true;
 if(paidCases)paidCases.disabled=true;
 setSpinNavigationLocked(true);
 if(status)status.textContent='🎲 Определяем приз на сервере…';
 try{
  // The reward is committed by the server before any animation; skipping does not reroll it.
  const d=await api('/api/spin/free',{method:'POST'});
  if(!d?.reward?.tier)throw Error('Сервер не вернул приз');
  lastSpinReward=d.reward;
  const start=((rouletteLastAngle%360)+360)%360,angle=rouletteAngleFor(d.reward.tier);
  const correction=((angle-start)%360+360)%360,end=start+360*9+correction;
  if(!skipByDefault){
   if(skipNow)skipNow.classList.remove('hide');
   if(progress)progress.classList.remove('hide');
   if(stage)stage.classList.add('roul-turning');
   setRouletteHubLabel('КРУТИМ…','УДАЧИ!');
   rouletteMusicStart(ROULETTE_STANDARD_MS);
   await animateRouletteWheel(wheel,start,end,ROULETTE_STANDARD_MS,bar,status);
   rouletteMusicStop();
   if(!rouletteSkipRequested)sfxStop();
  }else{
   wheel.style.transform='rotate('+angle+'deg)';
   if(status)status.textContent='⏩ Анимация пропущена';
  }
  wheel.style.transform='rotate('+angle+'deg)';
  rouletteLastAngle=angle;
  if(stage)stage.classList.remove('roul-turning');
  if(skipNow)skipNow.classList.add('hide');
  if(progress)progress.classList.add('hide');
  if(status)status.textContent='🎁 Награда получена!';
  sfxDrop(d.reward.tier);
  revealReward(result,d);
  setRouletteHubLabel('ПРИЗ!','ЗАБЕРИ');
  loadWinsFeed();
  if(['RED','GOLD','LEGENDARY','MYTHIC'].includes(d.reward.tier))showDropFx(d.reward);
 }catch(e){
  if(!e.silent)alert(e.message);
  // If the API succeeded but the animation failed, the server-side pending reward
  // is recovered by rouletteHtml() rather than rolling a second prize.
  try{app.innerHTML=await rouletteHtml();bindRoulette();addHomeExit()}catch(_){}
 }finally{
  rouletteMusicStop();
  endAudioHold();
  rouletteSpinBusy=false;
  rouletteSkipRequested=false;
  if(stage)stage.classList.remove('roul-turning');
  if(btn)btn.classList.remove('roul-hub-working');
  if(skipNow){skipNow.classList.add('hide');skipNow.disabled=false;skipNow.textContent='⏭ Пропустить прокрутку'}
  if(skipPref)skipPref.disabled=false;
  if(musicPref)musicPref.disabled=false;
  if(promo)promo.disabled=false;
  if(paidCases)paidCases.disabled=false;
  setSpinNavigationLocked(false);
 }
}


function caseFarmFeature(d){
 const stage=Math.max(1,Math.min(5,Number(d?.stage||1)));
 const resources=Array.isArray(d?.resources)?d.resources:[];
 const showcase=['gold_bar','gold_watch','pocket_watch'].map(id=>resources.find(r=>r.id===id)).filter(Boolean);
 for(const r of resources){if(showcase.length>=3)break;if(!showcase.some(x=>x.id===r.id))showcase.push(r)}
 return '<section class="case-farm-feature"><div class="case-farm-scene">'+farmScene({stage})+'<div class="case-farm-sky" aria-hidden="true">🌾</div></div>'+
 '<div class="case-farm-feature-content"><div class="farm-eyebrow">METRO FARM · ТВОЯ ФЕРМА</div>'+
 '<div class="case-farm-feature-title">🌿 Ферма ресурсов</div>'+
 '<div class="case-farm-feature-desc"></div>'+
 '<div class="case-farm-icons">'+showcase.map(farmItemSticker).join('')+'</div>'+
 '<div class="case-farm-feature-stats"><span>🌾 Уровень '+Number(d?.level||1)+'</span>'+
 '<span>🪙 '+Number(d?.shrek_coins||0).toLocaleString('ru-RU')+' ShrekCOIN</span>'+
 '<span>🎟 '+Number(d?.uc_available||0)+' UC Credits</span></div>'+
 '<button type="button" id="spinFarmBtn" class="case-farm-enter">🌾 Открыть ферму →</button></div></section>';
}

async function spinHtml(){
 spinState=await api('/api/spin/state');
 let caseFarmData=farmCachedData;
 try{caseFarmData=await api('/api/farm');farmCachedData=caseFarmData}catch(_){}
 const paidReady=spinState.paid_case_opening||null;
 if(paidReady){selectedCaseId=paidReady.case_id;localStorage.setItem('shx_selected_case',selectedCaseId)}
 const history=(spinState.history||[]).map(x=>'<div class="order"><div class="name">'+esc(x.reward_name)+'</div>'+rarityBar(x.reward_tier)+'<div class="mini" style="margin-top:9px">'+spinSourceLabel(x.source)+' • продажа '+shrAmount(x.points)+' SHR</div></div>').join('');
 const total=Number(spinState.remaining_spins||0),pending=spinState.pending_drop||null,cfg=selectedCase();
 const adminFree=!!(cfg&&cfg.is_free),donation=Number(cfg&&cfg.donation_tickets||0);
 const paidForSelected=!!(paidReady&&cfg&&paidReady.case_id===cfg.id);
 let buttonText='КРУТИТЬ',canOpen=!pending&&!!cfg;
 if(pending){buttonText='СНАЧАЛА РАЗБЕРИТЕ ДРОП';canOpen=false}
 else if(paidForSelected){buttonText='ОТКРЫТЬ ОПЛАЧЕННЫЙ КЕЙС'}
 else if(!cfg){buttonText='КЕЙСЫ ВРЕМЕННО НЕДОСТУПНЫ';canOpen=false}
 else if(adminFree){buttonText='ОТКРЫТЬ БЕСПЛАТНО'}
 else if(donation>0){buttonText='ОТКРЫТЬ ЗА DONATION TICKET'}
 else if(Number(cfg.stars_price||0)>0){buttonText='ОТКРЫТЬ ЗА '+Number(cfg.stars_price)+' ⭐'}
 else{buttonText='КЕЙС НЕДОСТУПЕН';canOpen=false}
 const skip=localStorage.getItem('shx_skip_spin_animation')==='1';
 let modeNote='';
 if(paidForSelected)modeNote='Оплата уже подтверждена. Нажмите кнопку, чтобы прокрутить кейс.';
 else if(adminFree)modeNote='Этот кейс отмечен бесплатным в админ-панели.';
 else if(donation>0)modeNote='Будет использован синий Donation Ticket. Stars не спишутся.';
 else modeNote='Стоимость открытия: '+Number(cfg&&cfg.stars_price||0)+' Telegram Stars.';
 return '<section class="hero"><div class="cat">МЕТРО-КЕЙСЫ</div><h1>Платные <span class="gold">кейсы</span></h1><div class="muted"></div></section>'+
 spinCasePickerHtml()+caseSelectedPreview(cfg)+
 '<div class="spin-stats"><div class="spin-stat donation-stat"><div class="mini blue-ticket">DONATION TICKETS</div><div class="price blue-ticket">🎫 '+Number(spinState.donation_tickets_total||0)+'</div></div><div class="spin-stat"><div class="mini">SHR</div><div class="price">'+shrAmount(spinState.shr)+'</div></div></div>'+
 '<div class="spin-shell"><div class="reel-window" id="reelWindow"><div class="reel-track" id="reelTrack">'+selectedCaseIdleStrip()+'</div><div class="reel-marker"></div></div><div class="spin-result" id="spinResult"></div><button class="buy" id="spinBtn" style="margin-top:12px" '+(canOpen?'':'disabled')+'>'+buttonText+'</button><div class="spin-lock-note" id="spinLockNote"></div>'+
 '<div class="spin-options-grid"><label class="spin-options"><input type="checkbox" id="skipSpinAnimation" '+(skip?'checked':'')+'><span>Пропустить анимацию</span></label></div>'+
 '<div class="muted" style="margin-top:10px">'+modeNote+'</div></div>'+
 '<div class="card"><div class="cat">ПРОМОКОД НА ПРОКРУТКИ</div><div class="muted"></div><div class="row"><input id="spinPromoCode" placeholder="Промокод"><button class="secondary" id="spinPromoBtn">Активировать</button></div><div class="mini" id="spinPromoInfo"></div></div>'+
 caseFarmFeature(caseFarmData)+'<h3>Последние 5 выпадений</h3>'+(history||'<div class="empty">История пока пустая.</div>')
}
function bindSpin(){
 bindSpinCasePicker();
 const allItems=document.getElementById('spinAllItems');
 if(allItems)allItems.addEventListener('click',()=>{
  if(spinNavigationLocked)return;
  const panel=document.getElementById('spinAllItemsContent'),cfg=selectedCase();if(!panel||!cfg)return;
  const willOpen=panel.classList.contains('hide');
  if(willOpen&&!panel.dataset.loaded){
   const rewards=caseItemsOf(cfg);
   const tiers=(cfg.tiers||[]).filter(t=>Number(t.chance)>0).map(t=>
    '<span class="case-odds-chip" data-tier="'+esc(t.tier)+'">'+caseTierLabel(cfg.id,t.tier)+' · '+Number(t.chance)+'%</span>').join('');
   panel.innerHTML='<h4>Шансы и содержимое «'+esc(cfg.name)+'»</h4><div class="case-odds-list">'+tiers+'</div>'+
    '<div class="muted" style="font-size:11px;margin:12px 0 5px">Все '+rewards.length+' предметов по возрастанию стоимости. Награда определяется случайно на сервере.</div>'+
    '<div class="case-loot-grid case-all-grid">'+rewards.map(caseLootCard).join('')+'</div>';
   panel.dataset.loaded='1';
  }
  panel.classList.toggle('hide',!willOpen);
  allItems.setAttribute('aria-expanded',willOpen?'true':'false');
  allItems.textContent=willOpen?'Скрыть все предметы ↑':'Показать все '+caseItemCountText(caseItemsOf(cfg).length)+' и шансы ↓';
 });
 const farmBtn=document.getElementById('spinFarmBtn');if(farmBtn)farmBtn.addEventListener('click',()=>go('farm'));
 const b=document.getElementById('spinBtn');if(b&&!b.disabled)b.addEventListener('click',spinOnce);
 const p=document.getElementById('spinPromoBtn');if(p)p.addEventListener('click',applySpinPromo);
 const skip=document.getElementById('skipSpinAnimation');if(skip)skip.addEventListener('change',()=>localStorage.setItem('shx_skip_spin_animation',skip.checked?'1':'0'));
 if(spinState&&spinState.pending_drop)restorePendingDrop(spinState.pending_drop);
 // SHR Market section removed; backend admin settings remain intact.
}
function restorePendingDrop(data){
 const track=document.getElementById('reelTrack'),windowEl=document.getElementById('reelWindow'),result=document.getElementById('spinResult'),b=document.getElementById('spinBtn');
 if(!track||!windowEl||!result||!data||!data.reward)return;
 lastSpinReward=data.reward;
 showFinalCube(track,windowEl,data.reward);
 revealReward(result,data);
 if(b){b.disabled=true;b.textContent='СНАЧАЛА РАЗБЕРИТЕ ДРОП'}
}
async function applySpinPromo(){
 const code=(document.getElementById('spinPromoCode').value||'').trim(),info=document.getElementById('spinPromoInfo');
 if(!code){info.innerHTML='<span class="warn">Введите промокод</span>';return}
 const b=document.getElementById('spinPromoBtn');b.disabled=true;b.textContent='Проверяем…';
 try{
  const d=await api('/api/spin/promo',{method:'POST',body:JSON.stringify({code})});
  if(d.promo_type==='donation'||Number(d.donation_tickets_added||0)>0){
   const target=d.donation_case_id==='*'?'все донат-кейсы':d.donation_case_id;
   info.innerHTML='<span class="blue-ticket">🎫 +'+d.donation_tickets_added+' Donation Ticket • '+esc(target)+' • всего '+d.donation_tickets_total+'</span>'
  }else{
   info.innerHTML='<span class="ok">+'+d.tickets_added+' SPIN-билет(а). Теперь у вас 🎟 '+d.bonus_tickets+'</span>'
  }
  setTimeout(async()=>{if(tab==='roulette'){app.innerHTML=await rouletteHtml();bindRoulette()}else{app.innerHTML=await spinHtml();bindSpin()}addHomeExit()},650)
 }catch(e){info.innerHTML='<span class="warn">'+esc(e.message)+'</span>';b.disabled=false;b.textContent='Активировать'}
}
function sleep(ms){return new Promise(r=>setTimeout(r,ms))}
function cubeClass(tier){return 'cube-'+String(tier||'COMMON').toLowerCase()}
function cubeHtml(tier,extra=''){
 return '<div class="reel-item '+extra+'"><div class="loot-cube '+cubeClass(tier)+'"><span>?</span></div></div>'
}
function visualTier(){
 const cfg=selectedCase(),tiers=(cfg&&cfg.tiers)||[];
 const valid=tiers.filter(t=>Number(t.chance||0)>0),total=valid.reduce((s,t)=>s+Number(t.chance||0),0);
 if(valid.length&&total>0){
  let r=Math.random()*total;
  for(const t of valid){r-=Number(t.chance||0);if(r<=0)return t.tier}
  return valid[valid.length-1].tier
 }
 const r=Math.random()*100,gray=tierChance('GRAY'),cyan=gray+tierChance('CYAN');
 if(r<gray)return 'GRAY';if(r<cyan)return 'CYAN';return 'BLUE'
}
function idleCubeStrip(){
 const tiers=['GRAY','CYAN','GRAY','BLUE','GRAY','CYAN','GRAY','BLUE','GRAY'];
 return tiers.map(t=>cubeHtml(t)).join('')
}
function buildSpinStrip(reward){
 const count=125,targetIndex=60,pool=reelVisualPool(selectedCase());
 const bits=[];
 for(let i=0;i<count;i++){
  const prize=i===targetIndex?reward:randomReelPrize(pool);
  bits.push(reelItemHtml(prize,i===targetIndex?'target-cube':''));
 }
 return {html:bits.join(''),targetIndex}
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
 track.innerHTML=reelItemHtml(reward,'target-cube');
 const itemWidth=90;
 const finalX=windowEl.clientWidth/2-itemWidth/2;
 track.style.transform='translate3d('+finalX+'px,-50%,0)'
}
function revealReward(result,data){
 if(!result)return;
 const reward=data.reward;
 result.innerHTML='<div class="reveal-name '+tierClass(reward.tier)+'">'+esc(reward.name)+'</div>'+
 caseLootSticker(reward)+'<div class="mini">Решите, что сделать с предметом</div>'+
 '<div class="drop-actions"><button class="save-drop" id="saveDropBtn">Сохранить</button><button class="sell-drop" id="sellDropBtn">Продать за '+shrAmount(data.sell_shr)+' SHR</button></div>';
 const save=document.getElementById('saveDropBtn'),sell=document.getElementById('sellDropBtn');
 if(save)save.addEventListener('click',()=>resolveDrop(data.inventory_item_id,'save',save));
 if(sell)sell.addEventListener('click',()=>resolveDrop(data.inventory_item_id,'sell',sell))
}
async function resolveDrop(itemId,action,btn){
 if(btn)btn.disabled=true;
 setSpinNavigationLocked(false);
 try{
  const d=await api('/api/inventory/'+itemId+'/resolve',{method:'POST',body:JSON.stringify({action})});
  if(action==='save'){sfxSave();tab='inventory';await render()}
  else{
   sfxSell();
   alert('Продано. Баланс: '+shrAmount(d.shr)+' SHR');
   if(tab==='roulette'){app.innerHTML=await rouletteHtml();bindRoulette();addHomeExit()}
   else{app.innerHTML=await spinHtml();bindSpin();addHomeExit()}
   loadWinsFeed()
  }
 }catch(e){if(btn)btn.disabled=false;alert(e.message)}
}
async function claimPaidCase(openingId){
 let lastErr=null;
 for(let i=0;i<30;i++){
  try{return await api('/api/spin/case/'+openingId+'/claim',{method:'POST'})}
  catch(e){lastErr=e;await sleep(500)}
 }
 throw lastErr||new Error('Платёж принят, но выдача ещё не завершена')
}
async function requestSpinResult(){
 const cfg=selectedCase();
 if(!cfg||cfg.id==='FREE')throw new Error('Для бесплатной прокрутки откройте раздел «Рулетки»');
 const d=await api('/api/spin/case/open',{method:'POST',body:JSON.stringify({case_id:cfg.id})});
 if(d.mode!=='invoice')return d;
 if(!(tg&&tg.openInvoice)){
  location.href=d.url;
  throw Object.assign(new Error('Счёт открыт во внешнем окне. После оплаты вернитесь в рулетку.'),{silent:true})
 }
 const status=await new Promise(resolve=>tg.openInvoice(d.url,s=>resolve(String(s||'cancelled'))));
 if(status!=='paid'){
  try{await api('/api/spin/case/opening/'+d.opening_id+'/cancel',{method:'POST'})}catch(_){}
  throw Object.assign(new Error(status==='cancelled'?'Оплата отменена':'Оплата не завершена'),{silent:true})
 }
 return await claimPaidCase(d.opening_id)
}
async function animateObtainedDrop(d,b,track,windowEl,result,skip,audioReady){
 await audioReady;
 lastSpinReward=d.reward;
 if(!skip)beginAudioHold();else tone(523.25,.09,.024,'sine');
 if(skip){
  showFinalCube(track,windowEl,d.reward);sfxDrop(d.reward.tier);revealReward(result,d);
  try{if(tg&&tg.HapticFeedback)tg.HapticFeedback.notificationOccurred('success')}catch(_){}
  showDropFx(d.reward);setSpinNavigationLocked(false)
 }else{
  startSpinSound(30000);await animateSpinRight(track,windowEl,d.reward);stopSpinSound();sfxStop();await sleep(220);
  sfxDrop(d.reward.tier);revealReward(result,d);
  try{if(tg&&tg.HapticFeedback)tg.HapticFeedback.notificationOccurred('success')}catch(_){}
  await sleep(500);showDropFx(d.reward);setSpinNavigationLocked(false)
 }
 b.textContent='НАГРАДА ВЫПАЛА'
}
async function spinOnce(){
 const b=document.getElementById('spinBtn');if(!b||b.disabled)return;
 const cfg=selectedCase();if(!cfg)return;
 const track=document.getElementById('reelTrack'),windowEl=document.getElementById('reelWindow'),result=document.getElementById('spinResult');
 const skip=!!document.getElementById('skipSpinAnimation')?.checked;
 const audioReady=ensureAudioReady();
 b.disabled=true;b.textContent='ПОДГОТАВЛИВАЕМ…';if(result)result.textContent='';
 setSpinNavigationLocked(true);
 try{
  const d=await requestSpinResult();
  await animateObtainedDrop(d,b,track,windowEl,result,skip,audioReady)
 }catch(e){
  stopSpinSound();setSpinNavigationLocked(false);
  if(!e.silent)alert(e.message);
  app.innerHTML=await spinHtml();bindSpin();addHomeExit()
 }
}
async function claimUpgrade(points){try{const d=await api('/api/upgrade/claim',{method:'POST',body:JSON.stringify({points})});alert('Заявка создана: '+d.reward.name);app.innerHTML=await spinHtml();bindSpin()}catch(e){alert(e.message)}}

async function inventoryHtml(){
 const d=await api('/api/inventory');
 const items=d.items||[];
 const list=items.map(x=>{
  const pending=x.status==='pending';
  return '<div class="inventory-card"><div class="inventory-card-head">'+caseLootSticker({name:x.reward_name,tier:x.reward_tier},true)+'<div><div class="name">'+esc(x.reward_name)+'</div><div class="'+tierClass(x.reward_tier)+'">'+esc(x.reward_tier)+'</div></div></div>'+
  '<div class="inventory-meta"><span>Продажа: '+shrAmount(x.sell_shr)+' SHR</span><span>Оценка: 🪙 '+Number(x.value_stars||0).toLocaleString('ru-RU')+'</span><span>'+(pending?'Новый дроп':'Сохранён')+'</span></div>'+
  '<div class="inventory-actions">'+(pending?'<button class="secondary" data-inv-save="'+x.id+'">Сохранить</button>':'')+'<button class="buy" data-inv-sell="'+x.id+'">Продать за '+shrAmount(x.sell_shr)+' SHR</button></div></div>'
 }).join('');
 return '<section class="hero"><div class="cat">ИНВЕНТАРЬ</div><h1>Ваши предметы</h1><div class="muted">Сохраняйте дропы или продавайте их за SHR в любое время.</div></section>'+
 '<div class="inventory-balance"><div><div class="mini">БАЛАНС SHR</div><div class="muted">Внутренняя валюта Шрексича</div></div><b>'+shrAmount(d.shr)+' SHR</b></div>'+
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
  if(action==='sell'){sfxSell();alert('Предмет продан. Баланс: '+shrAmount(d.shr)+' SHR')}else{sfxSave()}
  app.innerHTML=await inventoryHtml();bindInventory();addHomeExit()
 }catch(e){if(btn)btn.disabled=false;alert(e.message)}
}


let farmCatalogExpanded=false;
let farmDevelopmentExpanded=false;
let farmInventoryFilter='ALL';
let farmCatalogFilter='ALL';
let farmCachedData=null;
let farmUcMineTicker=null;
let farmCoinSerial=0;
function farmCoinIcon(){
 const id='shxcoin'+(++farmCoinSerial);
 return '<svg viewBox="0 0 100 100" aria-label="ShrekCOIN" role="img"><defs>'+
 '<linearGradient id="'+id+'" x1="0" x2="1" y1="0" y2="1"><stop stop-color="#fff5b9"/><stop offset=".27" stop-color="#f5cc52"/><stop offset=".58" stop-color="#c68118"/><stop offset=".8" stop-color="#ffe07d"/><stop offset="1" stop-color="#905411"/></linearGradient></defs>'+
 '<ellipse cx="50" cy="55" rx="43" ry="42" fill="#714314"/><circle cx="50" cy="47" r="42" fill="url(#'+id+')" stroke="#ffdf81" stroke-width="2.5"/>'+
 '<circle cx="50" cy="47" r="32" fill="none" stroke="#9d651d" stroke-width="3"/><circle cx="50" cy="47" r="35" fill="none" stroke="#ffeb9d" stroke-width="1"/>'+
 '<path d="M24 30Q50 7 78 30" fill="none" stroke="#ffedac" stroke-width="2" opacity=".65"/>'+
 '<text x="50" y="45" font-family="Arial,sans-serif" font-size="17" font-weight="1000" letter-spacing="-.8" text-anchor="middle" fill="#69380b">Shrek</text>'+
 '<text x="50" y="61" font-family="Arial,sans-serif" font-size="14" font-weight="1000" text-anchor="middle" fill="#69380b">COIN</text></svg>';
}
function farmUcIcon(){
 return '<svg viewBox="0 0 100 100" aria-label="UC Credits" role="img"><defs><linearGradient id="shxucgloss" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#c8f1ff"/><stop offset=".42" stop-color="#397caa"/><stop offset="1" stop-color="#0c2e4c"/></linearGradient></defs>'+
 '<path d="M19 8L80 8 92 24 92 74 80 90 19 90 8 74 8 24Z" fill="#12283a" stroke="#79b8d2" stroke-width="3"/>'+
 '<path d="M23 14L77 14 85 26 85 72 77 83 23 83 15 72 15 26Z" fill="url(#shxucgloss)" stroke="#d0f4ff" stroke-width="1.5"/>'+
 '<path d="M18 21L82 21" stroke="#edfaff" stroke-width="2" opacity=".5"/>'+
 '<text x="50" y="60" fill="#f4fdff" font-family="Arial,sans-serif" font-size="32" font-weight="1000" text-anchor="middle" stroke="#15324d" stroke-width="1" paint-order="stroke">UC</text>'+
 '<text x="50" y="73" fill="#e8faff" font-family="Arial,sans-serif" font-size="9" font-weight="900" letter-spacing=".5" text-anchor="middle">CREDITS</text></svg>';
}
function farmPrice(value){return '<span class="farm-currency-inline">'+farmCoinIcon()+' '+Number(value).toLocaleString('ru-RU')+'</span>'}
function farmVectorAsset(item){
 // Все ресурсы имеют собственные изометрические объёмные SVG-стикеры, без emoji-картинок.
 const id=item.id||'';
 const c={GRAY:'#baa981',CYAN:'#78cad1',BLUE:'#79a5e9',PURPLE:'#c88af4',PINK:'#e78cbf',RED:'#f28764',GOLD:'#f8cf5d',RAINBOW:'#a884ff'}[item.tier]||'#b7c6bb';
 const metallic=item.tier==='GOLD'||id.startsWith('gold_')||id==='heart_of_gold';
 const edge=metallic?'#9b6115':'#3c3b36';
 const light=metallic?'#ffe49a':'#edeee5';
 const base=metallic?'#da9c27':c;
 const label=(id.includes('password')?'PASS':id.includes('metro')?'2036':id.includes('gold')?'GOLD':id==='cpu'?'CPU':id==='diesel'?'DIESEL':id==='signal_generator'?'RF':id==='tech_part'?'GEAR':id==='playing_cards'?'ACE':'MR');
 let shape='';
 if(['postcard','playing_cards','letter','password_white','password_red','password_yellow','password_green','password_black'].includes(id)){
  shape='<path d="M18 16L65 13 75 62 28 67Z" fill="'+edge+'" opacity=".85"/>'+
  '<path d="M13 11L61 8 71 57 23 62Z" fill="'+light+'" stroke="'+base+'" stroke-width="3"/>'+
  '<path d="M21 21L59 17 61 25 24 29Z" fill="'+c+'" opacity=".65"/>'+
  '<path d="M25 45L60 41M27 51L54 47" stroke="#755d4c" stroke-width="2" opacity=".6"/>'+
  '<path d="M41 32L53 29 57 38 45 41Z" fill="'+base+'" stroke="'+edge+'" stroke-width="1"/>';
  if(id==='playing_cards')shape+='<text x="39" y="44" font-size="21" fill="#bd2020">♠</text>';
  else if(id.includes('password'))shape+='<text x="32" y="40" font-size="8" font-weight="900" fill="#5b3429">PASS</text>';
 }else if(['travel_guide','magazine','metro_2036'].includes(id)){
  shape='<path d="M21 11L66 6 73 65 27 72 20 63Z" fill="#ded3ab" stroke="#604833" stroke-width="3"/>'+
  '<path d="M16 8L60 3 69 59 24 65Z" fill="'+base+'" stroke="'+edge+'" stroke-width="3"/>'+
  '<path d="M19 13L25 64M35 28L59 26M37 35L60 33" stroke="'+light+'" stroke-width="2" opacity=".65"/>'+
  '<text x="35" y="51" font-size="9" font-weight="900" fill="#352d21">'+label+'</text>';
 }else if(['can','motor_oil','gas_bottle','diesel','lubricating_oil','water_purifier'].includes(id)){
  shape='<path d="M28 19Q44 11 62 19V67Q44 79 28 67Z" fill="'+edge+'" stroke="#20292c" stroke-width="2"/>'+
  '<path d="M24 17Q44 7 66 17V61Q45 75 24 61Z" fill="'+base+'" stroke="'+edge+'" stroke-width="3"/>'+
  '<ellipse cx="45" cy="17" rx="21" ry="8" fill="'+light+'" stroke="'+edge+'" stroke-width="3"/>'+
  '<path d="M31 23V57" stroke="'+light+'" stroke-width="6" opacity=".46"/>'+
  '<rect x="32" y="34" width="26" height="17" rx="3" fill="#183447" opacity=".86"/>'+
  '<text x="45" y="45" text-anchor="middle" font-size="8" font-weight="900" fill="#e8f8ff">'+(id==='diesel'?'D':id==='water_purifier'?'H2O':'OIL')+'</text>';
 }else if(['compass','pocket_watch','military_watch','gold_watch'].includes(id)){
  shape='<path d="M43 8V19" stroke="'+base+'" stroke-width="8" stroke-linecap="round"/>'+
  '<circle cx="45" cy="47" r="29" fill="'+edge+'" stroke="#433022" stroke-width="3"/>'+
  '<circle cx="43" cy="43" r="27" fill="'+base+'" stroke="'+light+'" stroke-width="4"/>'+
  '<circle cx="43" cy="43" r="20" fill="#fff6da" stroke="'+edge+'" stroke-width="2"/>'+
  '<path d="M43 24V29M61 43H56M43 61V56M26 43H31M43 43L34 31M43 43L57 39" stroke="#76582d" stroke-width="3" stroke-linecap="round"/>'+
  '<circle cx="43" cy="43" r="4" fill="#4f3021"/>';
 }else if(['canteen','gold_kettle'].includes(id)){
  shape='<path d="M31 13Q45 3 57 13L62 25V65Q45 75 23 65L29 25Z" fill="'+base+'" stroke="'+edge+'" stroke-width="4"/>'+
  '<ellipse cx="44" cy="16" rx="15" ry="5" fill="'+light+'" stroke="'+edge+'" stroke-width="2"/>'+
  '<path d="M60 31Q82 22 78 43Q76 53 62 53" fill="none" stroke="'+edge+'" stroke-width="7"/>'+
  '<path d="M27 35L12 31 24 44" fill="'+base+'" stroke="'+edge+'" stroke-width="3"/>'+
  '<path d="M35 26V61" stroke="'+light+'" stroke-width="6" opacity=".45"/>';
 }else if(['heart_necklace','heart_of_gold'].includes(id)){
  shape='<path d="M20 18Q44 70 70 18" fill="none" stroke="'+base+'" stroke-width="7" stroke-linecap="round"/>'+
  '<path d="M20 18Q44 70 70 18" fill="none" stroke="'+light+'" stroke-width="2" stroke-dasharray="3 5"/>'+
  '<path d="M45 48Q16 27 24 61L45 77 66 61Q74 27 45 48Z" fill="'+base+'" stroke="'+edge+'" stroke-width="4"/>'+
  '<path d="M32 53L44 67" stroke="'+light+'" stroke-width="5" opacity=".52"/>';
 }else if(['purse','car_key','dog_tag'].includes(id)){
  shape='<path d="M19 26L58 19 72 61 31 72Z" fill="'+edge+'" stroke="#192027" stroke-width="2"/>'+
  '<path d="M16 19L56 13 68 56 28 64Z" fill="'+base+'" stroke="'+edge+'" stroke-width="3"/>'+
  '<circle cx="29" cy="26" r="4" fill="'+light+'"/>'+
  '<path d="M30 27L52 51" stroke="'+light+'" stroke-width="4" opacity=".5"/>'+
  '<text x="36" y="46" font-size="10" font-weight="900" fill="#35404a">'+(id==='dog_tag'?'ID':id==='car_key'?'KEY':'MR')+'</text>';
 }else if(['cpu','tech_part'].includes(id)){
  shape='<path d="M24 19L59 10 74 53 39 68Z" fill="#18242b" stroke="'+edge+'" stroke-width="5"/>'+
  '<path d="M17 15L54 7 68 48 32 58Z" fill="'+base+'" stroke="'+edge+'" stroke-width="4"/>'+
  '<path d="M23 4L31 14M34 1L41 11M48 2L50 9M19 33L10 35M21 44L12 49M59 59L63 70" stroke="'+light+'" stroke-width="4"/>'+
  '<rect x="29" y="22" width="27" height="24" rx="4" fill="#243c50" stroke="'+light+'" stroke-width="2"/>'+
  '<text x="43" y="37" font-size="9" font-weight="900" text-anchor="middle" fill="#bfeaff">'+label+'</text>';
 }else if(['tablet','detector','signal_generator','video_tape'].includes(id)){
  shape='<path d="M17 14L59 5 76 65 33 76Z" fill="'+edge+'" stroke="#1b252b" stroke-width="4"/>'+
  '<path d="M12 9L56 1 71 61 27 70Z" fill="'+base+'" stroke="'+edge+'" stroke-width="3"/>'+
  '<path d="M21 18L51 11 61 52 31 59Z" fill="#1c3b4b" stroke="#b8eeff" stroke-width="2"/>'+
  '<path d="M29 43L38 31 44 38 52 22" stroke="#83f3f5" stroke-width="2" fill="none"/>'+
  '<text x="40" y="29" font-size="10" text-anchor="middle" font-weight="900" fill="#a3eeff">'+label+'</text>';
 }else if(id==='precision_blueprint'){
  shape='<path d="M14 15L70 9 77 62 21 70Z" fill="#e5d7b5" stroke="'+edge+'" stroke-width="4"/>'+
  '<path d="M20 21L64 16 69 57 26 63Z" fill="#e2d2ae" stroke="#876a4b" stroke-width="1"/>'+
  '<path d="M29 24L35 55M44 22L51 53M25 38L66 32M27 49L68 43" stroke="#6e8c9c" stroke-width="1.5"/>'+
  '<circle cx="45" cy="37" r="9" fill="none" stroke="#50778c" stroke-width="2"/>';
 }else if(id==='gold_bar'){
  shape='<path d="M12 45L53 18 79 37 37 65Z" fill="#e7b22d" stroke="#80511c" stroke-width="4"/>'+
  '<path d="M12 45L37 65 37 76 12 55Z" fill="#9e681d"/>'+
  '<path d="M37 65L79 37 79 50 37 76Z" fill="#be8226"/>'+
  '<path d="M30 42L53 26 67 37 43 53Z" fill="#ffe27b"/>'+
  '<text x="42" y="44" font-size="10" font-weight="900" fill="#935a15" text-anchor="middle">GOLD</text>';
 }else{
  shape='<path d="M12 43L50 16 77 38 39 65Z" fill="'+base+'" stroke="'+edge+'" stroke-width="4"/>'+
  '<path d="M12 43V53L39 74V65Z" fill="'+edge+'"/>'+
  '<path d="M39 65L77 38V52L39 74Z" fill="'+base+'"/>';
 }
 return '<svg class="farm-object-svg" viewBox="0 0 90 90" aria-hidden="true">'+
 '<ellipse cx="45" cy="81" rx="31" ry="7" fill="#000" opacity=".25"/>'+shape+'</svg>';
}
function farmItemSticker(item){
 return '<div class="farm-collectible" data-tier="'+esc(item.tier)+'" aria-label="'+esc(item.name)+'"><span class="farm-collectible-shine"></span><span class="farm-collectible-icon">'+farmVectorAsset(item)+'</span></div>'
}
function farmScene(d){
 return '<div class="farm-landscape stage-'+d.stage+'"><svg viewBox="0 0 790 344" preserveAspectRatio="xMidYMid slice" role="img" aria-label="Деревенская ферма, амбар, поле и деревянный забор">'+
 '<defs><linearGradient id="shxFarmSky" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#8ebccc"/><stop offset=".6" stop-color="#eed6a1"/><stop offset="1" stop-color="#f0be78"/></linearGradient>'+
 '<linearGradient id="shxFarmGrass" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#69834c"/><stop offset=".6" stop-color="#405b2c"/><stop offset="1" stop-color="#25391c"/></linearGradient>'+
 '<linearGradient id="shxFarmWood" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#b17e48"/><stop offset=".5" stop-color="#7d4b2c"/><stop offset="1" stop-color="#44271a"/></linearGradient>'+
 '<linearGradient id="shxFarmRoof" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#9a6545"/><stop offset=".55" stop-color="#623823"/><stop offset="1" stop-color="#39271e"/></linearGradient>'+
 '</defs>'+
 '<rect width="790" height="344" fill="url(#shxFarmSky)"/>'+
 '<circle cx="638" cy="73" r="46" fill="#fff0b3" opacity=".8"/><circle cx="638" cy="73" r="69" fill="#fff5c5" opacity=".16"/>'+
 '<path d="M0 160Q110 95 238 148Q367 98 504 156Q665 96 790 147V344H0Z" fill="#9ab080"/>'+
 '<path d="M0 194Q122 150 257 184Q400 143 528 180Q674 151 790 187V344H0Z" fill="#6e8553"/>'+
 '<path d="M0 226Q280 186 790 215V344H0Z" fill="url(#shxFarmGrass)"/>'+
 '<path d="M0 278Q390 235 790 269V344H0Z" fill="#654931" opacity=".8"/>'+
 '<path d="M-15 318Q230 269 790 315" stroke="#ac8050" stroke-width="12" opacity=".5" fill="none"/>'+
 '<path d="M40 344Q180 288 382 310M285 344Q400 307 555 308M520 344Q659 294 800 318" stroke="#271e13" stroke-width="8" opacity=".38" fill="none"/>'+
 '<g opacity=".76" fill="#344c2b"><path d="M35 179L62 99 99 179Z"/><path d="M78 185L123 86 168 185Z"/><path d="M661 185L710 87 758 185Z"/><path d="M731 200L780 109 826 200Z"/></g>'+
 '<g><path d="M105 262L109 171" stroke="#50391e" stroke-width="13"/><circle cx="105" cy="163" r="52" fill="#577044"/><circle cx="80" cy="175" r="37" fill="#6e844f"/><circle cx="124" cy="157" r="40" fill="#6b7e49"/></g>'+
 '<g transform="translate(300 93)"><path d="M-38 88L123 12 284 85V212H-38Z" fill="url(#shxFarmWood)" stroke="#452819" stroke-width="6"/>'+
 '<path d="M-69 89L123 -10 304 88 281 109 123 29 -42 112Z" fill="url(#shxFarmRoof)" stroke="#2c2018" stroke-width="7"/>'+
 '<path d="M-41 106L126 30 283 104" fill="none" stroke="#e6ae6c" stroke-width="3" opacity=".6"/>'+
 '<g stroke="#dca875" stroke-width="2" opacity=".35"><path d="M-13 101V208M14 87V207M42 72V207M67 59V207M92 44V207M140 46V205M168 60V207M196 73V207M224 86V208M250 100V208"/></g>'+
 '<path d="M76 212V129Q123 88 170 129V212Z" fill="#34251c" stroke="#dbad79" stroke-width="6"/>'+
 '<path d="M123 107V212" stroke="#ddaa69" stroke-width="5"/><path d="M90 144L158 194M154 144L91 194" stroke="#ae7344" stroke-width="8"/>'+
 '<rect x="195" y="127" width="49" height="44" fill="#362f21" stroke="#d6b180" stroke-width="7"/><path d="M218 129V170M197 148H244" stroke="#c7aa7d" stroke-width="5"/>'+
 '<path d="M-20 211H279" stroke="#694525" stroke-width="9"/></g>'+
 '<g transform="translate(112 253)"><path d="M0 20H226" stroke="#ad8858" stroke-width="10"/><path d="M16 -20V52M69 -18V50M122 -19V50M177 -20V50M215 -20V50" stroke="#d1a16c" stroke-width="11"/><path d="M0 -11H226" stroke="#a77942" stroke-width="6"/></g>'+
 '<g transform="translate(550 241)"><path d="M-12 37H165" stroke="#bb955b" stroke-width="11"/><path d="M10 0V77M55 0V77M100 0V77M151 0V77" stroke="#cfab74" stroke-width="11"/><path d="M-12 15H165" stroke="#98713f" stroke-width="8"/></g>'+
 '<g transform="translate(50 258)"><path d="M15 48L62 14 137 24 106 70Z" fill="#b28045" stroke="#5e4026" stroke-width="5"/>'+
 '<path d="M44 26L70 12 138 24 106 43Z" fill="#e5bc73"/><circle cx="46" cy="73" r="16" fill="#493626" stroke="#c39f67" stroke-width="5"/><circle cx="117" cy="78" r="16" fill="#493626" stroke="#c39f67" stroke-width="5"/></g>'+
 '<g fill="#86a45c" stroke="#385b27" stroke-width="3"><path d="M229 318Q211 274 200 292M233 317Q249 278 265 287M247 334Q255 294 281 305M670 339Q662 284 638 294M690 340Q700 296 722 312"/></g>'+
 '<g transform="translate(565 296)"><rect width="55" height="31" rx="5" fill="#c8a36e" stroke="#755236" stroke-width="3"/><path d="M0 12H55M17 0V30M37 0V30" stroke="#ad8455" stroke-width="2"/></g>'+
 '</svg><div class="farm-landscape-title"><span>Твоя деревенская ферма</span><span class="farm-stage-pill">УРОВЕНЬ '+d.level+' / '+d.max_level+' · ЭТАП '+d.stage+' / 10</span></div></div>';
}
function farmCatalogCards(d){
 const data=d||farmCachedData;
 if(!data)return '';
 const all=data.resources||[];

 const pool=all.filter(x=>farmCatalogFilter==='ALL'||x.tier===farmCatalogFilter).slice().sort((a,b)=>FARM_TIER_ORDER_JS.indexOf(a.tier)-FARM_TIER_ORDER_JS.indexOf(b.tier)||Number(a.coins)-Number(b.coins));
 return pool.map(x=>{
   const odds=Number((data.item_chances||{})[x.id]||0);
   const pct=odds===0?'0':odds<0.0001?odds.toFixed(8):odds<0.01?odds.toFixed(6):odds<1?odds.toFixed(4):odds.toFixed(2);
   return '<div class="farm-catalog-card" data-tier="'+esc(x.tier)+'">'+farmItemSticker(x)+
   '<h4>'+esc(x.name)+'</h4><span class="farm-rarity-label '+esc(x.tier)+'">'+tierLabel(x.tier)+'</span>'+
   farmPrice(x.coins)+'<span class="farm-chance-text">Шанс: '+pct+'% на ур. '+data.level+'</span></div>';
 }).join('') || '<div class="empty">Нет предметов этой редкости</div>';
}

async function farmCatalogPage(){
 const d=await api('/api/farm');farmCachedData=d;
 const filters=[['ALL','Все'],['GRAY','Серые'],['CYAN','Голубые'],['BLUE','Синие'],['PURPLE','Фиолетовые'],['PINK','Розовые'],['RED','Красные'],['GOLD','Реликтовые'],['RAINBOW','🌈 Уникальные']].map(([t,name])=>'<button data-farm-filter="'+t+'" class="'+(farmCatalogFilter===t?'active':'')+'">'+name+'</button>').join('');
 return '<div class="shx-farm-catalog"><div class="shx-page-title"><button class="shx-back" id="farmCatalogBack">← Ферма</button><h1>Каталог предметов</h1></div>'+
 '<div class="shx-panel"><div class="muted">Все '+(d.resources||[]).length+' предметов • цены за ShrekCOIN • качество и реальные шансы на уровне '+d.level+'</div></div>'+
 '<div class="farm-filterbar">'+filters+'</div><div class="farm-catalog-grid" id="farmCatalogGrid">'+farmCatalogCards(d)+'</div>'+
 '<div class="shx-panel"><div class="muted"></div></div></div>';
}
function bindFarmCatalogPage(){
 const back=document.getElementById('farmCatalogBack');if(back)back.addEventListener('click',()=>go('farm'));
 document.querySelectorAll('[data-farm-filter]').forEach(b=>b.addEventListener('click',()=>{
  farmCatalogFilter=b.dataset.farmFilter;
  document.querySelectorAll('[data-farm-filter]').forEach(x=>x.classList.toggle('active',x.dataset.farmFilter===farmCatalogFilter));
  const grid=document.getElementById('farmCatalogGrid');if(grid)grid.innerHTML=farmCatalogCards(farmCachedData);
 }));
}

async function farmHtml(){
 const d=await api('/api/farm');
 farmCachedData=d;
 const chanceOrder=FARM_TIER_ORDER_JS.map(t=>[t,Number((d.tier_weights||{})[t]||0)]);
 const chances=chanceOrder.filter(x=>x[1]>.0001).map(([t,p])=>'<span class="farm-chance '+tierClass(t)+'">'+tierLabel(t)+' '+Number(p).toFixed(p<1?2:1)+'%</span>').join('');
 const ucm=d.uc_mining||{daily_rate:1,ready:0,next_seconds:86400,reserve_available:0,claimable:0};
 const mineProgress=Number(ucm.ready||0)>0?100:Math.max(0,Math.min(100,100*(1-Number(ucm.next_seconds||0)*Number(ucm.daily_rate||1)/Number(ucm.period_seconds||86400))));
 const items=(d.inventory||[]).slice().filter(x=>farmInventoryFilter==='ALL'||(farmInventoryFilter==='LOCKED'?x.locked:farmInventoryFilter==='UNLOCKED'?!x.locked:x.tier===farmInventoryFilter)).sort((a,b)=>FARM_TIER_ORDER_JS.indexOf(a.tier)-FARM_TIER_ORDER_JS.indexOf(b.tier)||Number(a.coins)-Number(b.coins)).map(x=>
  '<div class="farm-item"><div class="farm-item-head"><div class="farm-item-icon">'+farmItemSticker(x)+'</div><div><div class="farm-item-name">'+esc(x.name)+'</div><span class="farm-rarity-label '+esc(x.tier)+'">'+tierLabel(x.tier)+'</span><div class="farm-item-meta">В наличии: '+x.qty+' шт.</div></div></div><div class="farm-item-meta">За шт.: '+farmPrice(x.coins)+'<br>Итого: '+farmPrice(x.total_coins)+'</div><button class="secondary" data-farm-lock="'+esc(x.id)+'" data-farm-locked="'+(x.locked?'1':'0')+'">'+(x.locked?'🔒 Разблокировать':'🔓 Заблокировать')+'</button><button class="secondary" data-farm-sell="'+esc(x.id)+'" data-farm-qty="'+x.qty+'" '+(x.locked?'disabled title="Предмет заблокирован"':'')+'>'+(x.locked?'🔒 Защищён от продажи':'Продать '+x.qty+' шт.')+'</button></div>'
 ).join('');
 const withdrawals=(d.withdrawals||[]).map(w=>'<div class="order"><div class="name">'+w.uc_amount+' UC • '+esc(w.status)+'</div><div class="mini">PUBG UID: '+esc(w.pubg_uid)+'</div></div>').join('');
 const modules=(d.coin_upgrades||[]).map(m=>{
 const maxed=m.level>=m.max_level;
 const controls=maxed
 ? '<div class="farm-max-label">✓ Максимальный уровень достигнут</div>'
 : '<div class="farm-bulk-selector"><select data-farm-qty="'+esc(m.id)+'" aria-label="Количество уровней">'+[1,2,5,10,20,50,100].map(n=>'<option value="'+n+'">+'+n+' ур.</option>').join('')+'<option value="max">МАКС</option></select></div><div class="farm-bulk-quote" data-farm-quote="'+esc(m.id)+'">Рассчитываем стоимость…</div><button class="secondary farm-upgrade-btn" data-farm-module="'+esc(m.id)+'" '+(d.shrek_coins<m.cost?'disabled':'')+'>УЛУЧШИТЬ · '+compactCurrency(m.cost)+' ShrekCOINS</button>';
 return '<div class="farm-module"><div class="farm-module-header"><span class="farm-module-icon">'+esc(m.icon)+'</span>'+esc(m.name)+'</div><div class="farm-module-desc">'+esc(m.description)+'</div><div class="mini">Уровень '+m.level+' / '+m.max_level+'</div><div class="farm-module-progress"><span style="width:'+(100*m.level/m.max_level)+'%"></span></div>'+controls+'</div>';
}).join('');
 const targets=(d.uc_targets||[]).map(t=>'<div class="farm-uc-target '+(t.need_more<=0?'farm-uc-complete':'')+'"><b>'+t.uc+' UC</b><span>Требуется '+t.required_credits+' UC Credits<br>'+(t.need_more<=0?'Можно подать заявку':('Не хватает '+t.need_more+' UC Credits'))+'</span></div>').join('');
 const ucMin=(d.uc_targets||[]).reduce((m,t)=>Math.min(m,Number(t.required_credits||t.uc)),Infinity);
 const minCredits=Number.isFinite(ucMin)?ucMin:120;
 const ucOptions=(d.uc_targets||[]).map(t=>'<option value="'+Number(t.uc)+'">'+Number(t.uc)+' UC — '+Number(t.required_credits)+' Credits</option>').join('')||'<option value="120">120 UC — 120 Credits</option>';
 const filters=[['ALL','Все'],['GRAY','Серые'],['CYAN','Голубые'],['BLUE','Синие'],['PURPLE','Фиолетовые'],['PINK','Розовые'],['RED','Красные'],['GOLD','Золотые']].map(([t,name])=>'<button data-farm-filter="'+t+'" class="'+(farmCatalogFilter===t?'active':'')+'">'+name+'</button>').join('');
 const catalog=farmCatalogExpanded?'<div id="farmCatalogDetails"><div class="farm-filterbar">'+filters+'</div><div class="farm-catalog-grid" id="farmCatalogGrid">'+farmCatalogCards(d)+'</div><div class="farm-aux" style="margin-top:12px"></div></div>':'';
 const next=d.available_cycles>0?'Добыча готова':(d.stored>=d.capacity?'Склад заполнен':'Следующая добыча через '+formatReset(d.next_cycle_seconds));
 const progress=d.available_cycles>0?100:(d.stored>=d.capacity?100:Math.max(0,100*(1-d.next_cycle_seconds/Math.max(1,d.interval_seconds))));
 return '<div class="farm-ui">'+
 '<div class="farm-lead"><div><span class="farm-eyebrow">SHREKSICH · METRO FARM</span><h1>Ферма ресурсов</h1><div class="muted"></div></div><div class="farm-lead-level">УРОВЕНЬ<br>'+d.level+' / '+d.max_level+'</div></div>'+
 farmScene(d)+
 '<div class="farm-overview"><div class="farm-wallet shr"><div class="farm-wallet-label">SHR</div><div class="farm-wallet-value"><span>'+compactCurrency(d.shr)+'</span></div></div>'+
 '<div class="farm-wallet"><div class="farm-wallet-label">SHREKCOIN</div><div class="farm-wallet-value">'+farmCoinIcon()+'<span>'+compactCurrency(d.shrek_coins)+'</span></div></div>'+
 '<div class="farm-wallet uc"><div class="farm-wallet-label">UC CREDITS</div><div class="farm-wallet-value">'+farmUcIcon()+'<span>'+compactCurrency(d.uc_available)+'</span></div></div></div>'+
 '<div class="farm-status"><div><span>Скорость добычи</span><b>1 предмет / '+Math.ceil(d.interval_seconds/60)+' мин</b></div><div><span>Склад</span><b>'+d.stored+' / '+d.capacity+' предметов</b></div><div><span>'+next+'</span><b>'+(d.available_cycles>0?d.available_cycles+' шт. можно забрать':'Ферма работает')+'</b></div><div><span>Редкость улучшается</span><b>с уровнем фермы</b></div><div class="farm-status-bar"><span style="width:'+progress.toFixed(1)+'%"></span></div></div>'+
 '<div class="farm-primary-actions"><button class="farm-primary" id="farmCollect" '+(d.available_cycles<=0?'disabled':'')+'>🧺 СОБРАТЬ • '+d.available_cycles+'</button><button class="secondary" id="farmUpgrade" '+(d.level>=d.max_level||d.shr<d.upgrade_cost?'disabled':'')+'>'+(d.level>=d.max_level?'МАКС. УРОВЕНЬ':d.shr<d.upgrade_cost?'НЕ ХВАТАЕТ '+compactCurrency(d.upgrade_cost-d.shr)+' SHR':'УЛУЧШИТЬ • '+compactCurrency(d.upgrade_cost)+' SHR')+'</button></div><div class="farm-upgrade-explainer">Основной уровень фермы улучшается за <b>SHR</b> · Цена: '+Number(d.upgrade_cost||0).toLocaleString('ru-RU')+' SHR · Баланс: '+Number(d.shr||0).toLocaleString('ru-RU')+' SHR. Модули ниже улучшаются отдельно за <b>ShrekCOINS</b>. Сокращённые суммы — только формат отображения.</div>'+

 '<section class="farm-uc-miner"><div class="farm-uc-miner-head"><div><div class="farm-eyebrow">UC MINING</div><div class="farm-uc-miner-label">🎮 Добыча UC Credits</div></div>'+farmUcIcon()+'</div>'+
 '<div class="farm-uc-miner-stats"><div class="farm-uc-miner-stat"><small>СКОРОСТЬ ФЕРМЫ</small><strong>+'+(Number(ucm.daily_rate||0)*86400/Number(ucm.period_seconds||86400)).toLocaleString('ru-RU',{maximumFractionDigits:2})+' UC/сутки</strong></div>'+
 '<div class="farm-uc-miner-stat"><small>ДОБЫТО</small><strong id="farmUcMineReady">'+ucm.ready+' UC Credits</strong></div>'+
 '<div class="farm-uc-miner-stat"><small>СЛЕДУЮЩИЙ UC</small><strong id="farmUcMineNext">'+(ucm.ready>=ucm.capacity?'ГОТОВО':formatReset(ucm.next_seconds))+'</strong></div></div>'+
 '<div class="farm-uc-miner-track"><span id="farmUcMineFill" style="width:'+mineProgress.toFixed(2)+'%"></span></div>'+
 '<div class="farm-uc-miner-foot"><span>Уровень '+d.level+' / '+d.max_level+'</span><span>Фонд: '+ucm.reserve_available+' UC</span></div>'+
 '<button class="farm-uc-miner-claim" id="farmUcMineClaim" '+(ucm.claimable>0?'':'disabled')+'>🎮 ЗАБРАТЬ '+ucm.claimable+' UC CREDITS</button>'+
 (ucm.reserve_available<=0?'<div class="farm-uc-paused">Выдача приостановлена: фонд UC Credits не пополнен</div>':'')+'</section>'+
 '<div class="farm-section wood"><div class="farm-section-head"><h3>🪵 Развитие фермы</h3><button type="button" class="secondary" id="farmDevelopmentToggle">'+(farmDevelopmentExpanded?'▲ Свернуть':'▼ Развернуть')+'</button></div><div class="farm-modules" id="farmDevelopmentContent" style="display:'+(farmDevelopmentExpanded?'':'none')+'">'+modules+'</div></div>'+
 '<div class="farm-section"><div class="farm-section-head"><h3>📚 Справочник ресурсов</h3><button class="farm-catalog-btn" id="farmCatalogToggle">'+(farmCatalogExpanded?'Скрыть':'Все предметы →')+'</button></div><div class="farm-aux">Все '+(d.resources||[]).length+' ресурсов, качество, цены продажи и реальные шансы для твоего уровня фермы.</div><div class="farm-tier-chances">'+chances+'</div>'+catalog+'</div>'+
 '<div class="farm-section"><div class="farm-section-head"><h3>📦 Склад добычи</h3><button class="secondary" id="farmSellAll" '+((d.inventory||[]).some(x=>!x.locked)?'':'disabled')+'>Продать всё незаблокированное</button></div><div class="farm-aux">🔒 Заблокированные ресурсы сохраняются при массовой продаже.</div><select id="farmInventoryFilter" aria-label="Фильтр склада"><option value="ALL">Все предметы</option><option value="LOCKED">🔒 Заблокированные</option><option value="UNLOCKED">🔓 Незаблокированные</option>'+FARM_TIER_ORDER_JS.map(t=>'<option value="'+t+'">'+tierLabel(t)+'</option>').join('')+'</select><div class="farm-inventory">'+(items||'<div class="empty">По выбранному фильтру предметов нет</div>')+'</div></div>'+
 '<div class="farm-activity"><div class="farm-section-head"><h3>🌱 Награды за активность</h3><span class="farm-rarity-label">Серия: '+d.activity_streak+' дн.</span></div><div class="farm-aux"></div><button class="buy" id="farmActivity" style="margin-top:12px;width:100%" '+(d.activity_ready&&ucm.reserve_available>=Number(d.daily_uc_credits||2)?'':'disabled')+'>'+(ucm.reserve_available<Number(d.daily_uc_credits||2)?'ФОНД UC НЕДОСТУПЕН':d.activity_ready?'ЗАБРАТЬ +'+d.daily_uc_credits+' UC CREDITS':'НАГРАДА НЕДОСТУПНА')+'</button></div>'+
 '<div class="farm-withdraw"><div class="farm-section-head"><h3>'+farmUcIcon()+' Вывод UC</h3></div><div class="farm-uc-need"><strong>Минимум для вывода: '+minCredits+' UC Credits → '+minCredits+' UC</strong><div style="margin-top:5px">Твой баланс: <strong>'+Number(d.uc_available)+' Credits</strong>. </div></div><div class="farm-aux"></div><div class="farm-uc-targets">'+targets+'</div><div class="farm-aux">Текущий баланс: '+d.uc_available+' UC Credits'+(d.uc_reserved>0?' • в ожидании: '+d.uc_reserved:'')+'.</div><div class="row" style="margin-top:11px"><input id="farmPubgUid" placeholder="PUBG UID" inputmode="numeric"><select id="farmUcAmount">'+ucOptions+'</select></div><div class="farm-uc-need" id="farmUcSelectedNeed">Для вывода выбранной суммы необходимо минимум '+minCredits+' UC Credits.</div><button class="buy" id="farmWithdraw" style="width:100%;margin-top:10px" '+(Number(d.uc_available)<minCredits?'disabled':'')+'>ОФОРМИТЬ ЗАЯВКУ НА UC</button></div>'+
 '<div class="farm-section"><h3>Последние заявки</h3>'+(withdrawals||'<div class="farm-aux" style="margin-top:8px">Заявок на вывод UC пока нет.</div>')+'</div>'+
 '</div>';
}

function refreshFarmUcNeed(){
 const amount=Number(document.getElementById('farmUcAmount')?.value||120);
 const farm=farmCachedData||{},targets=farm.uc_targets||[];
 const selected=targets.find(x=>Number(x.uc)===amount);
 const required=Number(selected?.required_credits||amount);
 const available=Number(farm.uc_available||0);
 const missing=Math.max(0,required-available);
 const label=document.getElementById('farmUcSelectedNeed'),button=document.getElementById('farmWithdraw');
 if(label)label.innerHTML='<strong>Для вывода '+amount+' UC нужно '+required+' UC Credits.</strong>'+
  '<div style="margin-top:5px">У тебя '+available+' Credits. '+(missing?'Не хватает '+missing+' UC Credits.':'Достаточно для заявки — укажи свой PUBG UID.')+'</div>';
 if(button)button.disabled=missing>0;
}

const FARM_TIER_ORDER_JS=['GRAY','CYAN','BLUE','PURPLE','PINK','RED','GOLD','RAINBOW'];
function bindFarm(){
 const devToggle=document.getElementById('farmDevelopmentToggle');
 if(devToggle)devToggle.onclick=()=>{farmDevelopmentExpanded=!farmDevelopmentExpanded;const content=document.getElementById('farmDevelopmentContent');if(content)content.style.display=farmDevelopmentExpanded?'':'none';devToggle.textContent=farmDevelopmentExpanded?'▲ Свернуть':'▼ Развернуть'};
 const invFilter=document.getElementById('farmInventoryFilter');
 if(invFilter){invFilter.value=farmInventoryFilter;invFilter.onchange=async()=>{farmInventoryFilter=invFilter.value;app.innerHTML=await farmHtml();bindFarm();addHomeExit()}}
 document.querySelectorAll('[data-farm-lock]').forEach(b=>b.onclick=async()=>{b.disabled=true;try{await api('/api/farm/lock',{method:'POST',body:JSON.stringify({resource_id:b.dataset.farmLock,locked:b.dataset.farmLocked!=='1'})});app.innerHTML=await farmHtml();bindFarm();addHomeExit()}catch(e){alert(e.message);b.disabled=false}});

 if(farmUcMineTicker){clearInterval(farmUcMineTicker);farmUcMineTicker=null}
 const mineState=farmCachedData?.uc_mining||null;
 if(mineState){
  const at=Date.now(),period=Math.ceil(Number(mineState.period_seconds||86400)/Math.max(1,Number(mineState.daily_rate||1)));
  const originalReady=Number(mineState.ready||0),toNext=Math.max(0,Number(mineState.next_seconds||period));
  const capacity=Math.max(1,Number(mineState.capacity||1));
  const reserve=Math.max(0,Number(mineState.reserve_available||0));
  const tick=()=>{
   if(tab!=='farm'){if(farmUcMineTicker)clearInterval(farmUcMineTicker);farmUcMineTicker=null;return}
   const passed=Math.floor((Date.now()-at)/1000);
   const earned=originalReady>=capacity?0:passed>=toNext?1+Math.floor((passed-toNext)/period):0;
   const ready=Math.min(capacity,originalReady+earned);
   const remaining=ready>=capacity?0:earned>0?Math.max(0,period-(passed-toNext)%period):Math.max(0,toNext-passed);
   const readyNode=document.getElementById('farmUcMineReady'),nextNode=document.getElementById('farmUcMineNext');
   const fill=document.getElementById('farmUcMineFill'),btn=document.getElementById('farmUcMineClaim');
   if(readyNode)readyNode.textContent=ready+' UC Credits';
   if(nextNode)nextNode.textContent=ready>=capacity?'ГОТОВО':formatReset(remaining)||'<1 мин';
   if(fill)fill.style.width=(ready>0?100:Math.max(0,Math.min(100,100*(1-remaining/period))))+'%';
   const claimable=Math.min(ready,reserve);
   if(btn){btn.disabled=claimable<1;btn.textContent='🎮 ЗАБРАТЬ '+claimable+' UC CREDITS'}
  };
  farmUcMineTicker=setInterval(tick,1000);
  tick();
 }
 const cat=document.getElementById('farmCatalogToggle');
 if(cat)cat.addEventListener('click',()=>go('farm-catalog'));
 document.querySelectorAll('[data-farm-filter]').forEach(b=>b.addEventListener('click',()=>{
  farmCatalogFilter=b.dataset.farmFilter;
  document.querySelectorAll('[data-farm-filter]').forEach(k=>k.classList.toggle('active',k.dataset.farmFilter===farmCatalogFilter));
  const grid=document.getElementById('farmCatalogGrid');if(grid)grid.innerHTML=farmCatalogCards(farmCachedData);
 }));
 const ucSelect=document.getElementById('farmUcAmount');
 if(ucSelect)refreshFarmUcNeed();
 if(ucSelect)ucSelect.addEventListener('change',()=>{
  refreshFarmUcNeed();
 });
 document.querySelectorAll('[data-farm-qty]').forEach(sel=>{
 const module=sel.dataset.farmQty,box=document.querySelector('[data-farm-quote="'+module+'"]'),btn=document.querySelector('[data-farm-module="'+module+'"]');
 let version=0;
 const refresh=async()=>{const v=++version;if(!box)return;box.textContent='Считаем точную стоимость…';
 try{const val=sel.value;const q=await api('/api/farm/coin-upgrade/quote?module='+encodeURIComponent(module)+'&levels='+(val==='max'?1:Number(val))+'&max_upgrade='+(val==='max'));
 if(v!==version)return;
 const num=n=>Number(n||0).toLocaleString('ru-RU');
 const money=n=>'<span title="'+num(n)+' ShrekCOINS">'+compactCurrency(n)+'</span>';
 box.innerHTML='Цена за '+q.requested+' ур.: <b>'+money(q.total_cost)+' ShrekCOINS</b><br>Доступно сейчас: <b>+'+q.affordable_levels+' ур.</b> за '+money(q.actual_cost)+'<br>Остаток: '+money(q.balance_after)+' ShrekCOINS';
 if(btn){btn.disabled=q.affordable_levels===0;btn.innerHTML=q.affordable_levels?'УЛУЧШИТЬ +'+q.affordable_levels+' ур. · '+compactCurrency(q.actual_cost)+' ShrekCOINS':'НЕДОСТАТОЧНО ShrekCOINS';}
 }catch(e){if(v===version)box.textContent='Ошибка расчёта: '+e.message}};
 sel.addEventListener('change',refresh);refresh();
});
 document.querySelectorAll('[data-farm-module]').forEach(b=>b.addEventListener('click',async()=>{b.disabled=true;try{const d=await api('/api/farm/coin-upgrade',{method:'POST',body:JSON.stringify({module:b.dataset.farmModule,levels:Number(document.querySelector('[data-farm-qty="'+b.dataset.farmModule+'"]')?.value)||1,max_upgrade:document.querySelector('[data-farm-qty="'+b.dataset.farmModule+'"]')?.value==='max'})});alert('Улучшено на '+d.levels_added+' ур. · Уровень '+d.level+' · -'+compactCurrency(d.spent)+' ShrekCOINS');app.innerHTML=await farmHtml();bindFarm();addHomeExit()}catch(e){alert(e.message);b.disabled=false}}));
 const collect=document.getElementById('farmCollect');if(collect&&!collect.disabled)collect.addEventListener('click',async()=>{collect.disabled=true;try{const d=await api('/api/farm/collect',{method:'POST'});alert('Ферма добыла '+d.count+' предмет(ов)');app.innerHTML=await farmHtml();bindFarm();addHomeExit()}catch(e){alert(e.message);collect.disabled=false}});
 const up=document.getElementById('farmUpgrade');if(up&&!up.disabled)up.addEventListener('click',async()=>{up.disabled=true;try{const d=await api('/api/farm/upgrade',{method:'POST'});alert('Ферма улучшена до '+d.level+' уровня');app.innerHTML=await farmHtml();bindFarm();addHomeExit()}catch(e){alert(e.message);up.disabled=false}});
 document.querySelectorAll('[data-farm-sell]').forEach(b=>b.addEventListener('click',async()=>{b.disabled=true;try{const d=await api('/api/farm/sell',{method:'POST',body:JSON.stringify({resource_id:b.dataset.farmSell,qty:Number(b.dataset.farmQty||1)})});sfxSell();alert('+'+d.coins_added+' ShrekCOINS');app.innerHTML=await farmHtml();bindFarm();addHomeExit()}catch(e){alert(e.message);b.disabled=false}}));
 const all=document.getElementById('farmSellAll');if(all&&!all.disabled)all.addEventListener('click',async()=>{if(!confirm('Продать все незаблокированные ресурсы за ShrekCOINS? Заблокированные предметы останутся на складе.'))return;all.disabled=true;try{const d=await api('/api/farm/sell-all',{method:'POST'});sfxSell();alert('Продано '+d.sold_qty+' предметов • +'+d.coins_added+' ShrekCOINS');app.innerHTML=await farmHtml();bindFarm();addHomeExit()}catch(e){alert(e.message);all.disabled=false}});
 const mineClaim=document.getElementById('farmUcMineClaim');if(mineClaim&&!mineClaim.disabled)mineClaim.addEventListener('click',async()=>{mineClaim.disabled=true;try{const result=await api('/api/farm/uc/claim',{method:'POST'});sfxSave();alert('🎮 +'+result.uc_credits_added+' UC Credits');app.innerHTML=await farmHtml();bindFarm();addHomeExit()}catch(e){alert(e.message);mineClaim.disabled=false}});
 const act=document.getElementById('farmActivity');if(act&&!act.disabled)act.addEventListener('click',async()=>{act.disabled=true;try{const d=await api('/api/farm/activity',{method:'POST'});alert('+'+d.uc_credits_added+' UC Credits'+(d.case_ticket?' • бесплатный билет '+d.case_ticket:''));app.innerHTML=await farmHtml();bindFarm();addHomeExit()}catch(e){alert(e.message);act.disabled=false}});
 const wd=document.getElementById('farmWithdraw');if(wd&&!wd.disabled)wd.addEventListener('click',async()=>{wd.disabled=true;try{const d=await api('/api/farm/withdraw',{method:'POST',body:JSON.stringify({pubg_uid:document.getElementById('farmPubgUid').value,uc_amount:Number(document.getElementById('farmUcAmount').value)})});alert('Заявка #'+d.id+' создана');app.innerHTML=await farmHtml();bindFarm();addHomeExit()}catch(e){alert(e.message);wd.disabled=false}})
}

async function referralHtml(){
 const r=await api('/api/referral');
 return '<section class="hero"><div class="cat">REFERRAL</div><h1>Приглашай друзей</h1><div class="muted">'+esc(r.reward_text)+'</div></section>'+
 '<div class="metrics"><div class="metric"><span class="mini">ПРИГЛАШЕНО</span><b>'+r.invited+'</b></div><div class="metric"><span class="mini">НАГРАЖДЕНО</span><b>'+r.rewarded+'</b></div><div class="metric"><span class="mini">БИЛЕТЫ</span><b>🎟 '+r.bonus_tickets+'</b></div><div class="metric"><span class="mini">SHR PTS</span><b>'+r.upgrade_points+'</b></div></div>'+
 '<div class="card" style="margin-top:12px"><div class="mini">ВАША ССЫЛКА</div><input id="refLink" readonly value="'+esc(r.link)+'"><button class="buy" id="copyRef">Скопировать ссылку</button></div>'
}
function bindReferral(){const b=document.getElementById('copyRef');if(b)b.addEventListener('click',async()=>{const v=document.getElementById('refLink').value;try{await navigator.clipboard.writeText(v);alert('Ссылка скопирована')}catch(_){document.getElementById('refLink').select()}})}

async function supportHtml(){const chats=await api('/api/uc-chats').catch(()=>[]);return '<div class="hero"><div class="cat">ПОДДЕРЖКА</div><h1>Чем помочь?</h1><div class="muted">Обращения попадают в Owner Panel. Бот не спамит автоматическими сообщениями.</div></div><div class="sticker-grid">'+sticker('Новости','@shreksi4PubgNEWS','news','st-gold','data-tg="https://t.me/shreksi4PubgNEWS"')+sticker('Наш чат','@chatshreksi4','chat','st-cyan','data-tg="https://t.me/chatshreksi4"')+'</div><div class="card"><h3>💬 Чаты с администрацией <span id="ucSupportUnread" class="shx-unread-badge"></span></h3><button type="button" class="secondary" id="ucMarkAllRead">✓ Прочесть все</button><div class="muted">Все ваши переписки по UC: открытые и закрытые. Нажмите на чат, чтобы увидеть сообщения.</div><div class="shx-chat-tabs"><button type="button" class="secondary" data-uc-chat-filter="all">Все ('+chats.length+')</button><button type="button" class="secondary" data-uc-chat-filter="open">Открытые ('+chats.filter(c=>c.status==='Открыт').length+')</button><button type="button" class="secondary" data-uc-chat-filter="closed">Закрытые ('+chats.filter(c=>c.status!=='Открыт').length+')</button></div>'+(chats.map(c=>'<details class="shx-uc-contact shx-user-chat" data-chat-status="'+(c.status==='Открыт'?'open':'closed')+'" data-uc-read-chat="'+c.id+'"><summary><b>💬 Чат по UC #'+c.withdrawal_id+' · '+c.uc_amount+' UC</b><span class="shx-chat-status '+(c.status==='Открыт'?'is-open':'is-closed')+'">'+esc(c.status)+'</span>'+(Number(c.unread||0)>0?'<span class="shx-unread-badge">'+c.unread+'</span>':'')+'</summary><b>Заявка #'+c.withdrawal_id+' · '+c.uc_amount+' UC · '+esc(c.status)+'</b>'+(c.messages||[]).map(m=>'<div class="shx-chat-msg"><b>'+(m.sender==='admin'?'Администратор':'Вы')+'</b> · '+esc(m.created_at)+'<p>'+esc(m.message)+'</p></div>').join('')+(c.status==='Открыт'?'<textarea id="ucUserReply'+c.id+'" maxlength="2000" placeholder="Ответить администратору"></textarea><button class="secondary" data-uc-user-reply="'+c.id+'">Отправить ответ</button>':'<p class="mini">Чат закрыт. Администратор может его открыть.</p>')+'</details>').join('')||'<p class="mini">Переписок пока нет. Когда администратор напишет вам по заявке UC, чат появится здесь.</p>')+'</div><div class="card"><select id="tc"><option>Вопрос по заказу</option><option>Оплата</option><option>Техническая проблема</option><option>Другое</option></select><textarea id="tm" placeholder="Опишите вопрос"></textarea><button class="buy" id="ticketBtn">Отправить</button></div>'}
async function sendTicket(){try{const d=await api('/api/support',{method:'POST',body:JSON.stringify({category:document.getElementById('tc').value,message:document.getElementById('tm').value})});alert('Обращение #'+d.id+' создано');document.getElementById('tm').value=''}catch(e){alert(e.message)}}
function bindSupport(){document.getElementById('ticketBtn').addEventListener('click',sendTicket);const allRead=document.getElementById('ucMarkAllRead');if(allRead)allRead.onclick=async()=>{try{await api('/api/uc-chats/read-all',{method:'POST'});go('support');refreshUCUnread()}catch(e){alert(e.message)}};document.querySelectorAll('[data-uc-read-chat]').forEach(el=>el.addEventListener('toggle',async()=>{if(!el.open)return;try{await api('/api/uc-chats/'+el.dataset.ucReadChat+'/read',{method:'POST'});el.querySelector('.shx-unread-badge')?.remove();refreshUCUnread()}catch(e){console.warn(e)}}));document.querySelectorAll('[data-uc-chat-filter]').forEach(b=>b.onclick=()=>{const filter=b.dataset.ucChatFilter;document.querySelectorAll('.shx-user-chat').forEach(chat=>{chat.style.display=filter==='all'||chat.dataset.chatStatus===filter?'':'none'});document.querySelectorAll('[data-uc-chat-filter]').forEach(btn=>btn.classList.toggle('shx-chat-filter-active',btn===b))});document.querySelector('[data-uc-chat-filter="all"]')?.classList.add('shx-chat-filter-active');document.querySelectorAll('[data-uc-user-reply]').forEach(b=>b.onclick=async()=>{const input=document.getElementById('ucUserReply'+b.dataset.ucUserReply),message=input.value.trim();if(!message)return alert('Введите сообщение');b.disabled=true;try{await api('/api/uc-chats/'+b.dataset.ucUserReply+'/messages',{method:'POST',body:JSON.stringify({message})});alert('Ответ отправлен');go('support')}catch(e){alert(e.message);b.disabled=false}});bindSocials()}

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
 const items=(d.items||[]).map(x=>'<div class="order"><div class="name">'+esc(x.reward_name)+'</div>'+rarityBar(x.reward_tier)+'<div class="mini" style="margin-top:9px">'+spinSourceLabel(x.source)+' • продажа '+shrAmount(x.points)+' SHR</div></div>').join('');
 return '<section class="hero"><div class="cat">ИСТОРИЯ ДРОПОВ</div><h1>Все выпадения</h1><div class="muted">Фильтруйте историю по времени и качеству кубика.</div></section>'+
 '<div class="history-filters"><div class="history-filter-grid"><select id="historyTier"><option value="ALL">Все редкости</option><option value="GRAY">Серый</option><option value="CYAN">Голубой</option><option value="BLUE">Синий</option><option value="PURPLE">Фиолетовый</option><option value="PINK">Розовый</option><option value="RED">Красный</option><option value="GOLD">Золотой</option></select><button class="secondary" id="historyApply">Применить фильтр</button><input id="historyFrom" type="datetime-local" aria-label="С даты"><input id="historyTo" type="datetime-local" aria-label="По дату"></div>'+
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

async function caseCatalogHtml(){
 spinState=await api('/api/spin/state');
 const cases=spinState.case_catalog||[];
 const html=cases.map(c=>{
  const allowed=new Set(c.contents||[]);
  const tiers=(c.tiers||[]).filter(t=>(spinState.rewards||[]).some(x=>x.tier===t.tier&&allowed.has(x.name)));
  return '<div class="case-guide-card"><div class="case-guide-head">'+caseIconMarkup(c.icon)+'<div><div class="case-guide-name">'+esc(c.name)+'</div><div class="mini">'+tiers.length+' качеств</div></div><div class="case-guide-price">'+esc(c.price_label)+'</div></div>'+
   '<div class="case-guide-desc">'+esc(c.description||'')+'</div>'+
   '<div class="case-tier-row">'+tiers.map(t=>'<button type="button" class="case-tier-btn" data-case-tier="'+esc(c.id)+'" data-tier="'+esc(t.tier)+'">'+caseLootSticker((spinState.rewards||[]).find(x=>x.tier===t.tier&&allowed.has(x.name))||{name:c.name,tier:t.tier},true)+'<div class="rarity-card-title '+tierClass(t.tier)+'">'+caseTierLabel(c.id,t.tier)+'</div><div class="rarity-card-chance">'+Number(t.chance||0)+'%</div></button>').join('')+'</div>'+
 '<div class="case-loot-preview"><div class="case-loot-preview-title">🎁 Предметы и их стоимость</div><div class="case-loot-grid">'+caseItemsOf(c).slice(0,6).map(caseLootCard).join('')+'</div></div>'+
 '<div class="case-guide-note"></div></div>'
 }).join('');
 return '<section class="hero"><div class="cat">КЕЙСЫ И ПРЕДМЕТЫ</div><h1>Каталог кейсов</h1><div class="muted"></div></section>'+
 '<div class="case-guide">'+html+'</div><div class="rarity-modal hide" id="caseTierModal"><div class="rarity-sheet" id="caseTierSheet"></div></div>'
}
function openCaseTier(caseId,tier){
 const cfg=(spinState.case_catalog||[]).find(x=>x.id===caseId);
 const tierCfg=cfg&&(cfg.tiers||[]).find(x=>x.tier===tier);
 const modal=document.getElementById('caseTierModal'),sheet=document.getElementById('caseTierSheet');
 if(!cfg||!tierCfg||!modal||!sheet)return;
 const allowed=new Set(cfg.contents||[]);
 const items=(spinState.rewards||[]).filter(x=>x.tier===tier&&allowed.has(x.name)).slice().sort((a,b)=>Number(a.value_stars||0)-Number(b.value_stars||0));
 sheet.innerHTML='<div class="rarity-sheet-head">'+caseLootSticker(items[0]||{name:cfg.name,tier},true)+'<div class="rarity-sheet-title"><h3 class="'+tierClass(tier)+'">'+caseTierLabel(caseId,tier)+'</h3><div class="muted">'+esc(cfg.name)+' • шанс '+Number(tierCfg.chance||0)+'% • '+items.length+' предметов</div></div><button type="button" class="rarity-close" id="caseTierClose">Закрыть</button></div>'+
 '<div class="case-loot-details">'+items.map(caseLootCard).join('')+'</div>';
  modal.classList.remove('hide');
 const close=()=>modal.classList.add('hide');
 document.getElementById('caseTierClose').addEventListener('click',close);
 modal.addEventListener('click',e=>{if(e.target===modal)close()},{once:true})
}
function bindCaseCatalog(){
 document.querySelectorAll('[data-case-tier]').forEach(b=>b.addEventListener('click',()=>openCaseTier(b.dataset.caseTier,b.dataset.tier)))
}

function settingsHtml(){
 const skip=localStorage.getItem('shx_skip_spin_animation')==='1';
 const sound=soundsEnabled();
 return '<section class="hero"><div class="cat">НАСТРОЙКИ</div><h1>Шрексич</h1><div class="muted"></div></section>'+
 '<div class="settings-grid"><div class="setting-card"><h3>Анимация SPIN</h3><div class="muted"></div><label class="switch-row"><span>Пропускать анимацию</span><input type="checkbox" id="settingsSkip" '+(skip?'checked':'')+'></label></div>'+
 '<div class="setting-card"><h3>Звуки эффектов</h3><div class="muted"></div><label class="switch-row"><span>Звуки включены</span><input type="checkbox" id="settingsSound" '+(sound?'checked':'')+'></label></div></div>'+
 '<div class="sticker-grid">'+sticker('Инвентарь','Предметы и SHR','inventory','st-cyan','data-go="inventory"')+sticker('Каталог наград','Кейсы, предметы, редкости и цены','cases','st-gold','data-go="case-catalog"')+sticker('История дропов','Фильтр по времени и редкости','history','st-purple','data-go="drop-history"')+sticker('Поддержка','Обращения и помощь','support','st-blue','data-go="support"')+'</div>'
}
function bindSettings(){
 const a=document.getElementById('settingsSkip');if(a)a.addEventListener('change',()=>localStorage.setItem('shx_skip_spin_animation',a.checked?'1':'0'));
 const s=document.getElementById('settingsSound');if(s)s.addEventListener('change',()=>{
  setSoundEnabled(s.checked);
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
  api('/api/admin/promos'),api('/api/admin/tickets'),api('/api/admin/spins'),api('/api/admin/upgrades'),api('/api/admin/referrals'),
  api('/api/admin/cases'),api('/api/admin/farm-withdrawals'),api('/api/admin/uc-fund'),
  api('/api/admin/sellers')
 ]);
 adminData={stats:r[0],orders:r[1],users:r[2],products:r[3],promos:r[4],tickets:r[5],spins:r[6],upgrades:r[7],referrals:r[8],cases:r[9],farmWithdrawals:r[10],ucFund:r[11],sellers:r[12]}
}
let adminUCUnread=0;async function refreshAdminUCUnread(){if(!ADMIN)return;try{const d=await api('/api/admin/uc-chats/unread');adminUCUnread=Number(d.unread||0);document.querySelectorAll('[data-admin="withdrawals"]').forEach(b=>{let badge=b.querySelector('.shx-unread-badge');if(adminUCUnread){if(!badge){badge=document.createElement('span');badge.className='shx-unread-badge';b.appendChild(badge)}badge.textContent=String(adminUCUnread)}else badge?.remove()});const sel=document.getElementById('shxAdminSectionSelect');if(sel){const opt=sel.querySelector('option[value="withdrawals"]');if(opt)opt.textContent='📊 Статистика UC'+(adminUCUnread?' 🔴 '+adminUCUnread+' непрочитано':'')}const notify=document.getElementById('shxAdminUnreadNotice');if(notify){notify.hidden=!adminUCUnread;notify.textContent=adminUCUnread?'🔴 Непрочитанные сообщения покупателей: '+adminUCUnread:''} const h=document.getElementById('adminUCUnread');if(h)h.textContent=adminUCUnread?String(adminUCUnread):'';const map=new Map((d.chats||[]).map(x=>[String(x.withdrawal_id),Number(x.unread)]));document.querySelectorAll('[data-uc-chat-open]').forEach(b=>{const n=map.get(b.dataset.ucChatOpen)||0;b.textContent='📜 История / закрыть / открыть'+(n?' · 🔴 '+n:'')})}catch(_){}}
function adminNav(){
const items=[['overview','♟','Главная'],['users','♟','Игроки'],['users','🎁','Выдача наград'],['orders','▤','Заказы'],['products','⚑','Товары'],['seller_applications','📩','Заявки'],['sellers','♟','Продавцы'],['cases','⬡','Кейсы'],['rewards','◉','Рулетки'],['promos','◆','Промокоды'],['ucfund','◈','Финансы'],['withdrawals','▥','Статистика UC'],['bot','✉','Рассылки'],['support','?','Поддержка'],['bot','⚙','Настройки'],['staff','🛡','Администраторы']];
const active=items.find(x=>x[0]===adminSection)||items[0];
return '<div class="shx-v4 shx-reference"><aside class="shx-v4-sidebar"><div class="shx-v4-brand"><span class="shx-crown">👑</span><div><b>SHREKSICH SHOP</b><small>АДМИН ПАНЕЛЬ</small></div></div><nav>'+items.map(x=>'<button data-admin="'+x[0]+'" class="'+(adminSection===x[0]?'active':'')+'"><span class="shx-menu-icon">'+x[1]+'</span>'+x[2]+'</button>').join('')+'</nav><div class="shx-v4-online">● Бот онлайн</div></aside><div class="shx-v4-main"><header class="shx-v4-header"><div><h1>'+(adminSection==='overview'?'Панель управления':active[2])+'</h1><span>'+(adminSection==='overview'?'Добро пожаловать в SHREKSICH SHOP':'Управление разделом · SHREKSICH SHOP')+'</span></div><div class="shx-header-pills"><b>🟢 Бот онлайн</b><b>◷ <span id="shxAdminClock">—</span></b></div></header><div id="shxAdminUnreadNotice" class="shx-admin-unread-notice" role="status" hidden></div><div class="shx-v4-mobile"><label for="shxAdminSectionSelect">РАЗДЕЛ АДМИН-ПАНЕЛИ</label><select id="shxAdminSectionSelect"><optgroup label="Основное"><option value="overview">🏠 Главная</option><option value="users">👥 Игроки и награды</option><option value="orders">📦 Заказы</option><option value="support">💬 Поддержка</option></optgroup><optgroup label="Магазин"><option value="products">🛍 Товары</option><option value="seller_applications">📩 Заявки продавцов</option><option value="sellers">🤝 Продавцы</option><option value="cases">🎁 Кейсы</option><option value="rewards">🎰 Рулетки</option><option value="promos">🎟 Промокоды</option></optgroup><optgroup label="Управление"><option value="ucfund">💰 Финансы</option><option value="withdrawals">📊 Статистика UC</option><option value="bot">📣 Рассылки и настройки</option><option value="staff">🛡 Администраторы</option></optgroup></select></div>';
}
function metric(label,val){return '<div class="metric"><span class="mini">'+label+'</span><b>'+val+'</b></div>'}
function adminOverview(){
const st=adminData.stats||{},orders=adminData.orders||[],users=adminData.users||[],products=adminData.products||[];
const metrics=[['👤','ПОЛЬЗОВАТЕЛИ',st.users||0],['🛒','ЗАКАЗЫ',st.orders||0],['⭐','ВЫРУЧКА (Stars)',stars(st.stars_revenue||0)],['◈','UC ВЫВЕДЕНО',st.uc_withdrawn||0],['👥','АКТИВНЫЕ ПРОДАВЦЫ',Array.isArray(adminData.sellers)?adminData.sellers.length:0],['📦','ОТКРЫТО КЕЙСОВ',st.cases_opened||0]];
const actions=[['🎁','Выдать награду','users'],['🔎','Найти игрока','users'],['📦','Создать товар','products'],['🎟️','Создать промокод','promos'],['➤','Сделать рассылку','bot'],['⚙️','Обнулить / изменить баланс','balance']];
const orderRows=orders.slice(0,4).map(o=>'<details class="shx-order-detail"><summary><span>📦 #'+esc(String(o.number||o.id))+' · '+esc(o.product_name||'Заказ')+'</span><b>'+stars(o.stars_amount||0)+' ⭐</b><em>'+esc(o.status||'Новый')+'</em></summary><div class="shx-order-fields"><div>Создан: '+esc(o.created_at||'—')+'</div><div>Последнее изменение: '+esc(o.updated_at||'—')+'</div><div>Завершён: '+(o.status==='Выполнен'?esc(o.updated_at||'—'):'Не завершён')+'</div><div>Покупатель: '+esc(o.buyer_username?'@'+o.buyer_username:o.buyer_name||o.user_token||'—')+'</div><div>Продавец: '+esc(o.seller_name||o.seller_username||'Магазин SHREKSICH')+'</div><div>Исполнитель: '+(o.seller_id?'Продавец заказа':'Не указан отдельно')+'</div><div class="shx-order-links">'+(o.buyer_username?'<a href="https://t.me/'+encodeURIComponent(o.buyer_username.replace(/^@/,''))+'" target="_blank" rel="noopener">Написать покупателю ↗</a>':'')+(o.seller_username?'<a href="https://t.me/'+encodeURIComponent(o.seller_username.replace(/^@/,''))+'" target="_blank" rel="noopener">Написать продавцу ↗</a>':'')+'</div></div></details>').join('')||'<p>Пока нет заказов</p>';
const userRows=users.slice(0,5).map((u,i)=>'<button type="button" class="shx-ref-user shx-player-detail-btn" data-player-details="'+esc(u.token||'')+'"><span>'+(i+1)+'</span><span class="shx-ref-avatar">👤</span><span class="shx-player-name"><b>'+esc(u.username?'@'+u.username:u.first_name||'Игрок')+'</b><small>'+esc(u.token||'—')+'</small></span><span class="shx-ref-bal">'+Number(u.upgrade_points||0)+' SHR</span><span>Подробнее ▾</span></button><div class="shx-player-detail-result" id="detail-'+esc(u.token||'')+'" hidden></div>').join('')||'<p>Пока нет игроков</p>';
return '<div class="shx-v4-metrics">'+metrics.map((m,i)=>'<div class="shx-v4-metric tone'+i+'"><div><span class="shx-metric-icon">'+m[0]+'</span><small>'+m[1]+'</small></div><strong>'+m[2]+'</strong><i>⌁⌁⌁</i></div>').join('')+'</div><div class="shx-ref-topgrid"><div><section class="shx-v4-panel"><h2>◉ Быстрые действия</h2><div class="shx-v4-actions">'+actions.map((a,i)=>'<button data-admin="'+a[2]+'" class="tone'+i+'"><span>'+a[0]+'</span>'+a[1]+'</button>').join('')+'</div></section><section class="shx-v4-panel"><h2>👥 Последние игроки <button data-admin="users">Все игроки →</button></h2><div class="shx-ref-userlist">'+userRows+'</div></section></div><div><section class="shx-v4-panel"><h2>◉ Последние заказы <button data-admin="orders">Все заказы →</button></h2>'+orderRows+'</section><div class="shx-ref-art"><span>SHREKSICH<br>METRO SHOP</span><span>📦</span></div></div></div><div class="shx-ref-bottom"><section class="shx-v4-panel"><h2>🎁 Выдача наград</h2><p>Быстрая выдача валют, билетов и предметов</p><button class="buy" data-admin="users">Выдать награду →</button></section><section class="shx-v4-panel"><h2>🛒 Управление товарами</h2><p>Товары в каталоге: '+products.length+'</p><button class="buy" data-admin="products">Открыть товары →</button></section><section class="shx-v4-panel"><h2>🎟️ Создание промокода</h2><p>Настройка наград и ограничений</p><button class="buy" data-admin="promos">Создать промокод →</button></section></div>';
}
function adminOrders(){
 return '<h2>Заказы</h2>'+adminData.orders.map(o=>{const st=['Ожидает оплаты','Истёк','Проверка оплаты','Оплачен','Принят','В работе','Ожидает клиента','Проверка выдачи','Выполнен','Отменён','Возврат'];return '<div class="admin-card"><div class="cat">#'+o.number+' • '+esc(o.user_token||'Без жетона')+'</div><div class="name">'+esc(o.product_name)+'</div><div>'+stars(o.stars_amount)+' • PUBG UID '+esc(o.uid)+(o.promo_code?' • '+esc(o.promo_code):'')+'</div><div class="adminline"><select id="os'+o.id+'">'+st.map(s=>'<option '+(s===o.status?'selected':'')+'>'+s+'</option>').join('')+'</select><button class="secondary" data-order-save="'+o.id+'">Сохранить</button></div></div>'}).join('')
}
function adminBalance(){
 return '<section class="shx-admin-grant"><div class="shx-admin-kicker">SHREKSICH · БЫСТРЫЕ ДЕЙСТВИЯ</div><h2>⚙️ Обнулить / изменить баланс</h2><p>По жетону игрока. Установка 0 обнуляет выбранную валюту или предмет. Новое значение заменяет старое, а не прибавляется.</p><label class="shx-grant-field">Жетон игрока<input id="setBalanceToken" placeholder="SHX-..."></label><label class="shx-grant-field">Что изменить<select id="setBalanceAsset"><option value="shrek_coins">ShrekCOINS</option><option value="shr">SHR</option><option value="tickets">Обычные билеты</option><option value="donation_tickets">Донат-билеты</option><option value="farm_item">Предмет фермы</option></select></label><label class="shx-grant-field">Установить количество<input id="setBalanceAmount" type="number" min="0" step="1" placeholder="0 = обнулить"></label><label class="shx-grant-field">ID предмета (только для предмета)<input id="setBalanceResource" placeholder="ID предмета"></label><label class="shx-grant-field">Донат-кейс (только для билетов)<input id="setBalanceCase" value="*" placeholder="* = общие билеты"></label><p>UC Credits защищены финансовым резервом и здесь не изменяются.</p><button class="buy" id="setBalanceBtn">Применить изменение</button></section>';
}
function adminUsers(){
 const cases=(adminData.cases&&adminData.cases.cases)||[];
 const fields=[['grantTickets','🎟 Обычные билеты','Бесплатные попытки рулетки'],['grantDonation','🔷 Донат-билеты','Для открытия донат-кейсов'],['grantPts','💠 SHR','Внутриигровые очки'],['grantCoins','🪙 ShrekCOINS','Валюта фермы']];
 const editor=fields.map(x=>'<label class="shx-grant-field"><span>'+x[1]+'</span><small>'+x[2]+'</small><input id="'+x[0]+'" type="number" inputmode="numeric" min="0" step="1" value="" placeholder="Введите количество"></label>').join('');
 return '<section class="shx-admin-grant"><div class="shx-admin-kicker">SHREKSICH · УПРАВЛЕНИЕ</div><h2>🎁 Выдача наград</h2><p>Выберите игрока, укажите валюту и подтвердите начисление. Пустые поля не изменяют баланс.</p><label class="shx-grant-field"><span>🔎 Найти игрока</span><input id="userSearch" placeholder="Ник, имя или жетон SHX-..."></label><label class="shx-grant-field"><span>🎫 Жетон получателя</span><input id="grantToken" placeholder="Выберите игрока ниже или вставьте жетон" autocomplete="off"></label><div class="shx-grant-grid">'+editor+'</div><label class="shx-grant-field"><span>🎁 Для какого кейса донат-билеты?</span><select id="grantDonationCase"><option value="*">Все донат-кейсы</option>'+cases.filter(c=>c.id!=='FREE').map(c=>'<option value="'+esc(c.id)+'">'+esc(c.name)+'</option>').join('')+'</select></label><div class="shx-grant-note">UC Credits выдаются отдельно через обеспеченный фонд — это защищает бюджет проекта.</div><button class="buy shx-grant-submit" id="grantBtn">✓ Подтвердить выдачу</button></section><div class="shx-admin-players-head"><h3>👥 Игроки</h3><span>'+adminData.users.length+' в списке</span></div>'+
 adminData.users.map(u=>'<div class="admin-card user-row shx-admin-player" data-search="'+esc(((u.token||'')+' '+(u.username||'')+' '+(u.first_name||'')).toLowerCase())+'"><div class="name">'+esc(u.first_name||u.username||'Игрок')+' '+(u.username?'@'+esc(u.username):'')+'</div><div class="shx-player-token"><button type="button" class="token-code" data-copy-token="'+esc(u.token||'')+'">📋 '+esc(u.token||'Без жетона')+'</button><button type="button" class="secondary" data-grant-player="'+esc(u.token||'')+'">Выбрать для выдачи ↑</button></div><div class="mini">Заказов: '+u.orders_count+' · Рефералов: '+u.referrals_count+' · Билеты: '+u.tickets+' · Донат: '+Number(u.donation_tickets||0)+' · SHR: '+u.upgrade_points+'</div><button class="secondary" data-message-user="'+esc(u.token||'')+'" style="margin-top:8px">✉ Написать игроку</button></div>').join('')
}
function shopCategorySelect(value,attr){
 const categories=[...new Set([...(adminData.products||[]).map(p=>p.category).filter(Boolean),'Metro Royale','Аккаунты','Буст','Услуги','Другое'])].sort((a,b)=>a.localeCompare(b,'ru'));
 return '<select '+attr+'>'+categories.map(v=>'<option value="'+esc(v)+'" '+(v===value?'selected':'')+'>'+esc(v)+'</option>').join('')+'</select>'
}
function adminProducts(){
 return '<h2>Товары</h2><div class="card"><input id="newPName" placeholder="Название">'+shopCategorySelect('', 'id="newPCat"')+'<textarea id="newPDesc" placeholder="Описание"></textarea><div class="row"><input id="newPStars" type="number" placeholder="Цена ⭐"><input id="newPSort" type="number" value="0" placeholder="Сортировка"></div><button class="buy" id="newPBtn">Добавить товар</button></div>'+
 adminData.products.map(p=>'<div class="admin-card" data-product-card="'+p.id+'"><input data-p="name" value="'+esc(p.name)+'">'+shopCategorySelect(p.category,'data-p="category"')+'<textarea data-p="description">'+esc(p.description)+'</textarea><div class="row"><input data-p="stars_price" type="number" value="'+p.stars_price+'"><input data-p="sort_order" type="number" value="'+p.sort_order+'"></div><label class="mini"><input data-p="active" type="checkbox" '+(p.active?'checked':'')+' style="width:auto"> Активен</label><div class="shx-product-actions"><button class="secondary" data-product-save="'+p.id+'">Сохранить</button><button type="button" class="shx-product-delete" data-product-delete="'+p.id+'" data-product-name="'+esc(p.name)+'" aria-label="Удалить товар навсегда">✕ Удалить</button></div></div>').join('')
}
function adminCases(){
 const payload=adminData.cases||{cases:[],rewards:[],tiers:[]},rewards=payload.rewards||[],tiers=payload.tiers||[];
 const iconOptions=[['crate','Ящик'],['helmet','Шлем'],['airdrop','Аирдроп'],['vault','Сейф'],['crown','Корона']];
 return '<h2>Кейсы</h2><div class="card"><div class="muted">Меняйте цену в Stars, включайте бесплатный режим, редактируйте проценты и конкретное содержимое. Сумма процентов включённых качеств должна быть 100%.</div></div>'+
 (payload.cases||[]).map(c=>{
  const tmap={};(c.tiers||[]).forEach(t=>tmap[t.tier]=Number(t.chance||0));
  const selected=new Set(c.contents||[]);
  const tierEditors=tiers.map(t=>'<label class="case-admin-tier"><input type="checkbox" data-case-tier-enabled="'+t+'" '+(tmap[t]!=null?'checked':'')+'><span class="'+tierClass(t)+'">'+caseTierLabel(c.id,t)+'</span><input type="number" min="0" max="100" step="0.1" data-case-tier-chance="'+t+'" value="'+(tmap[t]!=null?tmap[t]:0)+'"></label>').join('');
  const groups=tiers.map(t=>{const rr=rewards.filter(r=>r.tier===t);return '<details '+(tmap[t]!=null?'open':'')+'><summary class="'+tierClass(t)+'">'+caseTierLabel(c.id,t)+' • '+rr.length+' предметов</summary><div class="case-item-list">'+rr.map(r=>'<label><input type="checkbox" data-case-item="'+esc(r.name)+'" '+(selected.has(r.name)?'checked':'')+'><span>'+esc(r.name)+'</span><b>'+Number(r.value_stars||0)+' SHR</b></label>').join('')+'</div></details>'}).join('');
  return '<div class="admin-card case-admin-card" data-case-admin="'+esc(c.id)+'"><div class="cat">'+esc(c.id)+'</div><div class="case-admin-top"><input data-ca="name" value="'+esc(c.name)+'" placeholder="Название"><input data-ca="stars_price" type="number" min="0" value="'+Number(c.stars_price||0)+'" placeholder="Цена Stars"></div><textarea data-ca="description" placeholder="Описание">'+esc(c.description||'')+'</textarea><div class="case-admin-top"><select data-ca="icon">'+iconOptions.map(o=>'<option value="'+o[0]+'" '+(o[0]===c.icon?'selected':'')+'>'+o[1]+'</option>').join('')+'</select><input data-ca="sort_order" type="number" min="0" value="'+Number(c.sort_order||0)+'" placeholder="Сортировка"></div><div class="row"><label class="mini"><input data-ca="is_free" type="checkbox" '+(c.is_free?'checked':'')+' style="width:auto"> Бесплатный кейс</label><label class="mini"><input data-ca="active" type="checkbox" '+(c.active?'checked':'')+' style="width:auto"> Активен</label></div><div class="mini">Проценты качеств</div><div class="case-admin-tier-grid">'+tierEditors+'</div><div class="case-admin-items">'+groups+'</div><button class="buy" data-case-save="'+esc(c.id)+'" style="width:100%;margin-top:10px">Сохранить кейс</button></div>'
 }).join('')
}

function adminPromos(){
 const cases=(adminData.cases&&adminData.cases.cases)||[];
 const caseOptions='<option value="*">Все донат-кейсы</option>'+cases.filter(c=>c.id!=='FREE').map(c=>'<option value="'+esc(c.id)+'">'+esc(c.name)+'</option>').join('');
 return '<h2>Промокоды</h2><div class="card"><select id="promoTypeNew"><option value="discount">Скидка на покупку</option><option value="spin">Обычные SPIN-билеты</option><option value="donation">Синие Donation Tickets</option></select><input id="promoCodeNew" placeholder="Код"><div class="row"><input id="promoDiscountNew" type="number" min="0" max="90" placeholder="Скидка %"><input id="promoSpinNew" type="number" min="0" max="100" placeholder="SPIN-билетов"></div><div class="row"><input id="promoDonationNew" type="number" min="0" max="100" placeholder="Donation Tickets"><select id="promoDonationCaseNew">'+caseOptions+'</select></div><div class="row"><input id="promoUsesNew" type="number" value="0" placeholder="Участников (0=∞)"><input id="promoExpiryNew" placeholder="Срок: 2026-12-31 23:59:59"></div><div class="mini">Donation Ticket — отдельный синий тикет, открывающий донат-кейс без списания Stars.</div><button class="buy" id="promoCreateBtn" style="margin-top:10px">Создать промокод</button></div>'+
 adminData.promos.map(p=>{const type=String(p.promo_type||'').toLowerCase();const isDonation=(type==='donation_spin'||type==='donation')||Number(p.donation_tickets||0)>0;const isSpin=!isDonation&&(Number(p.spin_tickets||0)>0||type==='spin');const reward=isDonation?('🎟️ +'+Math.max(1,Number(p.donation_tickets||0))+' Donation'):isSpin?('🎟 +'+Math.max(1,Number(p.spin_tickets||0))+' SPIN'):('-'+p.discount_percent+'% ⭐');const typeText=isDonation?'Donation Ticket промокод'+(p.case_id&&p.case_id!=='*'?' • '+esc(p.case_id):' • все кейсы'):isSpin?'SPIN-промокод':'Скидочный промокод';return '<div class="admin-card"><div class="name">'+esc(p.code)+' • <span class="'+(isDonation?'blue-ticket':'')+'">'+reward+'</span></div><div class="mini">'+typeText+' • участников '+p.uses+(p.max_uses?' / '+p.max_uses:' / ∞')+(p.expires_at?' • до '+esc(p.expires_at):' • без срока')+'</div><div class="row" style="margin-top:8px"><button class="secondary" data-promo-toggle="'+p.id+'" data-active="'+p.active+'">'+(p.active?'Отключить':'Включить')+'</button><button class="danger" data-promo-del="'+p.id+'">Удалить</button></div></div>'}).join('')
}
let adminSpinFilterValue='all';
function adminRewards(){
 const filter=adminSpinFilterValue;
 const spin=adminData.spins.filter(x=>filter==='all'||(filter==='high'?['GOLD','RED','MYTHIC','LEGENDARY'].includes(x.reward_tier):x.reward_tier===filter)).slice(0,80).map(x=>'<div class="order"><span class="tier '+tierClass(x.reward_tier)+'">'+x.reward_tier+'</span><div class="name">'+esc(x.reward_name)+'</div><div class="mini">'+esc(x.user_token||'Без жетона')+' • '+esc(x.created_at)+'</div></div>').join('');
 const ups=adminData.upgrades.slice(0,80).map(x=>'<div class="order"><div class="name">'+esc(x.reward_name)+'</div><div class="mini">'+esc(x.user_token||'Без жетона')+' • '+x.points_spent+' pts • '+esc(x.created_at)+'</div></div>').join('');
 const refs=adminData.referrals.slice(0,80).map(x=>'<div class="order"><div class="name">'+esc(x.referrer_name||x.referrer_username||x.referrer_token||'Игрок')+' → '+esc(x.referred_name||x.referred_username||x.referred_token||'Игрок')+'</div><div class="mini">'+esc(x.referrer_token||'—')+' → '+esc(x.referred_token||'—')+' • '+(x.rewarded?'✅ Награда выдана':'⏳ Ждём первую оплату')+' • '+esc(x.created_at)+'</div></div>').join('');
 return '<h2>Выигрыши</h2><label class="muted">Фильтр по качеству<select id="adminSpinFilter"><option value="all">Все выигрыши</option><option value="high">Дорогие / редкие</option>'+[...new Set(adminData.spins.map(x=>x.reward_tier))].filter(Boolean).map(t=>'<option value="'+esc(t)+'" '+(filter===t?'selected':'')+'>'+esc(t)+'</option>').join('')+'</select></label>'+(spin||'<div class="empty">Нет</div>')+'<h2>Upgrade Lab</h2>'+(ups||'<div class="empty">Нет</div>')+'<h2>Рефералы</h2>'+(refs||'<div class="empty">Нет</div>')
}
function adminWithdrawals(){
 // PUBG UID is shown as a large tap-to-copy target on every withdrawal.
 const rows=adminData.farmWithdrawals||[];
 return '<h2>UC выводы <span id="adminUCUnread" class="shx-unread-badge">'+(adminUCUnread||'')+'</span></h2><div class="card"><div class="muted">После фактической выдачи UC в PUBG нажмите «Выполнен». Только тогда UC Credits окончательно списываются у игрока.</div></div>'+
 (rows.map(w=>'<div class="admin-card"><div class="cat">#'+w.id+' • '+esc(w.status)+'</div><div class="name">'+w.uc_amount+' UC • '+esc(w.token||'Без жетона')+'</div><div class="mini">'+esc(w.first_name||w.username||'Игрок')+(w.username?' @'+esc(w.username):'')+' • '+esc(w.created_at)+'</div><div class="shx-uc-uid-label">PUBG MOBILE · ID ПОЛУЧАТЕЛЯ</div><button type="button" class="shx-uc-uid-copy" data-copy-pubg-uid="'+esc(String(w.pubg_uid||''))+'" aria-label="Скопировать PUBG UID '+esc(String(w.pubg_uid||''))+'"><span class="shx-uc-uid-value">'+esc(String(w.pubg_uid||'—'))+'</span><span class="shx-uc-copy-action">📋 Копировать ID</span></button><details class="shx-uc-contact"><summary>💬 Связаться с игроком</summary><div class="mini">Сообщение придёт игроку в Telegram от бота SHREKSICH SHOP.</div><textarea id="ucMsg'+w.id+'" rows="3" maxlength="2000" placeholder="Например: Уточните PUBG UID для выдачи UC."></textarea><button type="button" class="secondary" data-uc-contact="'+w.id+'" >✉ Отправить в чат</button><button type="button" class="secondary" data-uc-chat-open="'+w.id+'">📜 История / закрыть / открыть</button><div id="ucChatHistory'+w.id+'"></div>'+(w.username?'<a href="https://t.me/'+encodeURIComponent(w.username.replace(/^@/,''))+'" target="_blank" rel="noopener noreferrer">Открыть @'+esc(w.username)+' ↗</a>':'')+'</details>'+(w.status==='Ожидает'?'<div class="row" style="margin-top:8px"><button class="buy" data-farm-wd-ok="'+w.id+'">Выполнен</button><button class="danger" data-farm-wd-no="'+w.id+'">Отклонить</button></div>':'')+'</div>').join('')||'<div class="empty">Заявок пока нет.</div>')
}
function adminSupport(){
 return '<h2>Обращения</h2>'+adminData.tickets.map(t=>'<div class="admin-card"><div class="cat">#'+t.id+' • '+esc(t.category)+' • '+esc(t.status)+'</div><div class="mini">👤 '+esc(t.first_name||'Пользователь')+(t.username?' · @'+esc(t.username):'')+' · 🕒 '+esc(t.created_at||'Дата не указана')+' UTC</div><div style="margin:8px 0">'+esc(t.message)+'</div><div class="token-code">'+esc(t.user_token||'Без жетона')+'</div><textarea id="tr'+t.id+'" placeholder="Ответ пользователю"></textarea><div class="row"><button class="blue" data-ticket-reply="'+t.id+'">Ответить</button><button class="secondary" data-ticket-close="'+t.id+'">Закрыть</button></div></div>').join('')
}
function adminBot(){
 return '<h2>Управление ботом</h2><div class="card"><h3>Сообщение пользователю</h3><input id="botUserToken" placeholder="Жетон SHX-..."><textarea id="botUserMsg" placeholder="Сообщение"></textarea><button class="buy" id="botSendBtn">Отправить</button></div><div class="card" style="margin-top:12px"><h3>Рассылка</h3><textarea id="broadcastMsg" placeholder="Сообщение всем зарегистрированным пользователям"></textarea><button class="danger" id="broadcastBtn">Запустить рассылку</button></div><div class="card" style="margin-top:12px"><div class="name">Команды бота</div><div class="muted">/start • /shop • /faq • /ref • /token • /help<br>Каждый пользователь имеет постоянный жетон SHX-.... Вся работа с пользователями идёт по жетонам.</div></div>'
}

function adminUcFunding(){
 const d=adminData.ucFund||{};
 return '<h2>🎮 Фонд добычи UC</h2>'+
 '<div class="metrics">'+metric('ДОСТУПНО',Number(d.available||0)+' UC')+
 metric('ВЫДЕЛЕНО',Number(d.funded||0)+' UC')+
 metric('ВЫДАНО',Number(d.issued||0)+' UC')+
 metric('ОПЛАТЫ ⭐ (ВАЛОВЫЕ)',Number(d.gross_stars||0)+' ⭐')+
 metric('UC НА БАЛАНСАХ',Number(d.existing_liability||0)+' UC')+
 metric('UC В ЗАЯВКАХ',Number(d.reserved_liability||0)+' UC')+'</div>'+
 '<div class="card" style="margin-top:12px;border-color:#3f8099"><h3>Выдать UC Credits игроку</h3><p class="muted">UC списываются из подтверждённого фонда и начисляются игроку по жетону. Только владелец.</p><input id="ucGrantToken" placeholder="Жетон игрока SHX-..."><input id="ucGrantAmount" type="number" min="1" max="100000" placeholder="Количество UC"><input id="ucGrantReason" maxlength="250" placeholder="Причина выдачи (минимум 5 символов)"><button class="buy" id="ucGrantBtn">Выдать UC</button></div>'+
 '<div class="card" style="margin-top:12px;border-color:#3f8099"><h3>Пополнение из подтверждённой прибыли</h3>'+
 '<div class="muted" style="line-height:1.6;margin-bottom:12px">Stars здесь показаны как валовая выручка. До пополнения вычти комиссии, возвраты, себестоимость выданного лута и покупки UC. Выделяй только UC Credits, которые уже покрыты реальной чистой прибылью. Пока фонд пуст, новые UC не выдаются.</div>'+
 '<input id="ucFundAmount" type="number" min="1" max="100000" placeholder="Количество UC Credits">'+
 '<input id="ucFundNote" maxlength="220" placeholder="Основание: чистая прибыль, период или заказ">'+
 '<label class="mini" style="display:flex;gap:10px;align-items:center;margin:13px 0"><input id="ucFundVerified" type="checkbox" style="width:auto;flex:0 0 auto"><span>Я проверил прибыль и покрытие всех затрат на эти UC</span></label>'+
 '<button class="buy" id="ucFundAdd" style="width:100%">Пополнить фонд UC</button></div>'+
 '<h3>Журнал пополнений</h3>'+(d.history||[]).map(x=>'<div class="order"><b>+'+Number(x.credited_amount)+' UC Credits</b><div class="mini">'+esc(x.note)+'</div></div>').join('')
}

function adminSellers(){
 const d=adminData.sellers||{sellers:[],listings:[],orders:[]};
 const sellers=(d.sellers||[]).filter(x=>x.status!=='removed'&&(adminSection==='seller_applications'?x.status==='pending':x.status!=='pending')),listings=d.listings||[],orders=d.orders||[],removals=d.removals||[];
 const outstanding=orders.filter(x=>x.status==='Выполнен'&&!x.settled_id);
 const totalSeller=orders.filter(x=>x.settled_id).reduce((v,x)=>v+Number(x.seller_share_stars||0),0);
 const completedOrders=orders.filter(x=>x.status==='Выполнен');
 const shopCut=completedOrders.reduce((v,x)=>v+Number(x.platform_share_stars||0)-Number(x.reserve_share_stars||0),0);
 const reserveCut=completedOrders.reduce((v,x)=>v+Number(x.reserve_share_stars||0),0);
 let html='<section class="seller-hero"><div class="seller-headline">OWNER PANEL · MARKETPLACE</div><h1>🤝 Продавцы</h1>'+
 '<div class="mini">Модерация товаров, распределение заказов и расчёты с поставщиками</div>'+
 '<div class="seller-feature-grid"><div><strong>'+sellers.length+'</strong><small>Заявки и продавцы</small></div>'+
 '<div><strong>'+listings.filter(x=>x.seller_status==='pending').length+'</strong><small>Товаров ждут проверки</small></div>'+
 '<div><strong>'+outstanding.length+'</strong><small>К расчёту</small></div></div></section>'+
 '<div class="seller-income-row"><div><span>РАСЧЁТЫ С ПРОДАВЦАМИ</span><b>'+totalSeller+' ⭐</b></div>'+
 '<div><span>МАГАЗИН · 20%</span><b>'+shopCut+' ⭐</b></div>'+
 '<div><span>РЕЗЕРВ · 10%</span><b>'+reserveCut+' ⭐</b></div>'+
 '<div><span>К ВЫПЛАТЕ ПРОДАВЦАМ</span><b>'+outstanding.reduce((v,x)=>v+Number(x.seller_share_stars||0),0)+' ⭐</b></div></div>'+
 '<div class="seller-help">Для новых заказов действует распределение 70% продавцу, 20% магазину и 10% в резерв. По старым заказам сохранены исходные условия. Резерв — отдельная учётная доля Stars, а не автоматически выведенные средства. Комиссии Telegram, возвраты и себестоимость отдельно. Кнопка расчёта только фиксирует реальную внешнюю выплату.</div>'+
 '<h3 style="margin-top:19px">'+(adminSection==='seller_applications'?'Заявки продавцов':'Действующие продавцы')+'</h3>';
 html+=(sellers.map(x=>'<div class="seller-admin-box" data-admin-seller="'+x.telegram_id+'">'+
 '<div class="row" style="align-items:center;justify-content:space-between"><b>'+esc(x.display_name)+'</b>'+
 '<span class="seller-status-pill '+esc(x.status)+'">'+esc(x.status)+'</span></div>'+
 '<div class="mini">'+esc(x.token||'')+' · '+esc(x.contact)+'</div>'+
 '<div class="mini">'+esc(x.experience||'')+'</div>'+
 '<div class="mini" style="margin-top:9px">Новые заказы: 70% продавцу · 20% магазину · 10% резерву</div>'+
 '<div class="mini">Telegram: '+(x.username?'@'+esc(x.username):'username не указан')+' · ID: '+x.telegram_id+'</div>'+ 
 '<div class="mini">⭐ Рейтинг: '+(x.avg_rating?Number(x.avg_rating).toFixed(2)+'/5':'Нет оценок')+' · Отзывов: '+Number(x.review_count||0)+' · Выговоров: '+Number(x.warning_count||0)+'</div>'+ 
 '<div class="seller-market-actions">'+(x.status==='pending'?'<button class="buy" data-seller-approve="'+x.telegram_id+'">✓ Одобрить заявку</button>':'<button class="secondary" data-seller-history="'+x.telegram_id+'">📋 Данные и отзывы</button><button class="secondary" data-seller-warning="'+x.telegram_id+'">⚠️ Выдать выговор</button>')+
 '<button class="secondary" data-seller-contact="'+x.telegram_id+'">💬 Написать продавцу</button>'+(x.username?'<a style="color:#9de8ff;padding:10px" href="https://t.me/'+encodeURIComponent(x.username)+'" target="_blank" rel="noopener noreferrer">Открыть @'+esc(x.username)+'</a>':'')+
 (x.status==='blocked'?'':'<button class="danger" data-seller-block="'+x.telegram_id+'">Заблокировать</button>')+'<button class="danger" data-seller-remove="'+x.telegram_id+'">🗑 Удалить продавца</button>'+'</div><div id="sellerHistory'+x.telegram_id+'"></div></div>').join('')||
 '<div class="empty">Заявок пока нет</div>');
 html+='<h3 style="margin:18px 0 9px">История удалений</h3>'+(removals.map(x=>'<div class="seller-admin-box"><b>'+esc(x.display_name)+'</b> · ID '+Number(x.seller_id)+'<div class="mini">Причина: '+esc(x.reason)+'</div><div class="mini">Дата и время (UTC): '+esc(x.removed_at)+'</div></div>').join('')||'<div class="mini">Удалений пока нет</div>');
 html+='<h3 style="margin:18px 0 9px">Модерация товаров</h3>'+
 (listings.slice().sort((a,b)=>(a.seller_status==='pending'?0:1)-(b.seller_status==='pending'?0:1)).map(x=>'<div class="seller-admin-box"><div class="row"><span class="seller-status-pill '+esc(x.seller_status)+'">'+esc(x.seller_status)+'</span>'+
 '<span class="seller-stock-tag">В наличии '+Number(x.seller_stock||0)+'</span></div>'+
 '<h3>'+esc(x.name)+'</h3><div class="mini">'+esc(x.seller_name||'')+
 ' · '+Number(x.stars_price||0)+' ⭐ · '+esc(x.category)+'</div>'+
 '<div class="mini">'+esc(x.description||'')+'</div>'+
 '<div class="seller-market-actions">'+(x.seller_status==='active'?'<span class="seller-chip">✓ В каталоге</span>':'<button class="buy" data-seller-listing-approve="'+x.id+'">В каталог</button>')+
 '<button class="secondary" data-seller-listing-pause="'+x.id+'">Скрыть</button>'+
 '<button class="danger" data-seller-listing-reject="'+x.id+'">Отклонить</button></div></div>').join('')||
 '<div class="empty">Продавцы пока не добавляли товары</div>');
 html+='<h3 style="margin:18px 0 9px">💸 Заявки на выплаты</h3>'+((d.payouts||[]).map(p=>'<div class="seller-admin-box"><b>#'+p.id+' · '+esc(p.display_name||String(p.seller_id))+' · '+p.amount+' ⭐ · '+esc(p.status)+'</b><div class="mini">Доказательства: '+esc(p.proof)+'</div><div class="mini">Реквизиты: '+esc(p.payment_details)+'</div>'+(p.available_at?'<div class="mini">Доступно не ранее: '+new Date(p.available_at*1000).toLocaleString('ru-RU')+'</div>':'')+(p.reason?'<div class="mini">Причина: '+esc(p.reason)+'</div>':'')+'<div class="seller-market-actions">'+(p.status==='pending'?'<button class="buy" data-payout-action="approve" data-payout-id="'+p.id+'">Одобрить · 24 суток</button>':'')+(['pending','approved','ready'].includes(p.status)?'<button class="danger" data-payout-action="freeze" data-payout-id="'+p.id+'">Заморозить</button>':'')+(p.status==='frozen'&&p.approved_at?'<button class="secondary" data-payout-action="unfreeze" data-payout-id="'+p.id+'">Разморозить</button>':'')+(['pending','approved','ready','frozen'].includes(p.status)?'<button class="danger" data-payout-action="reject" data-payout-id="'+p.id+'">Отклонить</button>':'')+(['approved','ready'].includes(p.status)&&Date.now()>=p.available_at*1000?'<button class="buy" data-payout-action="paid" data-payout-id="'+p.id+'">Подтвердить перевод</button>':'')+'</div></div>').join('')||'<div class="empty">Заявок на выплаты нет</div>');
 html+='<h3 style="margin:18px 0 9px">Оплаченные заказы продавцов</h3>'+
 (orders.map(x=>'<div class="seller-admin-box"><div class="mini">#'+x.number+
 ' · '+esc(x.seller_name)+' · '+esc(x.status)+'</div>'+
 '<h3>'+esc(x.product_name)+'</h3>'+
 '<div class="seller-market-actions"><span class="seller-chip">Оплачено '+Number(x.stars_amount)+' ⭐</span>'+
 '<span class="seller-chip">Продавцу '+Number(x.seller_share_stars)+' ⭐</span>'+
 '<span class="seller-chip">Магазину '+(Number(x.platform_share_stars||0)-Number(x.reserve_share_stars||0))+' ⭐</span>'+
 '<span class="seller-chip">Резерв '+Number(x.reserve_share_stars||0)+' ⭐</span></div>'+
 (x.seller_delivery_note?'<div class="mini" style="margin-top:8px">Подтверждение продавца: '+esc(x.seller_delivery_note)+'</div>':'')+
 (x.status==='Проверка выдачи'?'<button class="buy" data-seller-complete="'+x.id+'" style="width:100%;margin-top:8px">✓ Выдача подтверждена</button>':'')+
 (x.status==='Выполнен'&&!Number(x.settled_id)?'<div class="seller-inputs" style="margin-top:10px">'+
 '<input id="sellerSettleNote'+x.id+'" maxlength="400" placeholder="Способ и идентификатор реально проведённого расчёта">'+
 '<button class="secondary" data-seller-settle="'+x.id+'">Зафиксировать расчёт</button></div>':'')+
 (x.settled_id?'<div class="seller-status-pill approved" style="margin-top:8px">✓ Расчёт зафиксирован</div>':'')+
 '</div>').join('')||'<div class="empty">Оплаченных заказов нет</div>');
 return html;
}
function shopStaffHtml(){return '<section class="card"><h2>🛡 Управление администраторами</h2><p class="muted">Старший состав может управлять только нижестоящими. Владелец защищён от любых изменений.</p><input id="shopStaffId" inputmode="numeric" placeholder="Telegram ID"><select id="shopStaffRole"><option value="admin">Администратор</option><option value="head_admin">Старший администратор</option><option value="deputy_owner">Заместитель владельца</option><option value="co_owner">Совладелец</option></select><button id="shopStaffAdd" class="buy">Добавить / изменить роль</button><div id="shopStaffList" style="margin-top:16px">Загрузка…</div></section>'}
function adminSectionHtml(){if(adminSection==='staff')return shopStaffHtml();if(adminSection==='balance')return adminBalance();if(adminSection==='orders')return adminOrders();if(adminSection==='users')return adminUsers();if(adminSection==='products')return adminProducts();if(adminSection==='sellers'||adminSection==='seller_applications')return adminSellers();if(adminSection==='cases')return adminCases();if(adminSection==='promos')return adminPromos();if(adminSection==='rewards')return adminRewards();if(adminSection==='withdrawals')return adminWithdrawals();if(adminSection==='ucfund')return adminUcFunding();if(adminSection==='support')return adminSupport();if(adminSection==='bot')return adminBot();return adminOverview()}
async function adminHtml(){if(!adminData)await loadAdminData();return adminNav()+'<main class="shx-owner-content">'+adminSectionHtml()+'</main></div></div>'}
async function refreshAdmin(){adminData=null;app.innerHTML='<div class="empty">Обновляем…</div>';app.innerHTML=await adminHtml();bindAdmin()}
function bindAdmin(){
 const spinFilter=document.getElementById('adminSpinFilter');
 if(spinFilter)spinFilter.addEventListener('change',()=>{const value=spinFilter.value;adminSpinFilterValue=value;app.innerHTML=adminNav()+'<main class="shx-owner-content">'+adminSectionHtml()+'</main></div></div>';bindAdmin();const restored=document.getElementById('adminSpinFilter');if(restored)restored.value=value;});

 if(adminSection==='staff'){
  const list=document.getElementById('shopStaffList');
  api('/api/admin/staff').then(rows=>{if(list)list.innerHTML=rows.map(x=>{
   const name=esc(x.first_name||'Имя не указано'),user=x.username?'@'+esc(x.username):'Юзернейм не указан';
   const date=x.created_at?new Date(x.created_at.replace(' ','T')+'Z').toLocaleString('ru-RU',{dateStyle:'medium',timeStyle:'short'}):'Дата назначения владельца не фиксируется';
   return '<div class="order"><b>'+name+'</b><div class="muted">'+user+'</div><div>ID: '+esc(String(x.telegram_id))+' · '+esc(({owner:'Владелец',co_owner:'Совладелец',deputy_owner:'Заместитель владельца',head_admin:'Старший администратор',admin:'Администратор',moderator:'Модератор'}[x.role]||x.role))+'</div><div class="muted">Добавлен: '+date+'</div><div>⚠️ Выговоры: '+Number(x.warnings||0)+'</div>'+(x.role==='owner'?'<b>🔒 Владелец защищён</b>':'<div class="row" style="margin-top:10px"><button class="secondary" data-staff-edit="'+x.telegram_id+'" data-role="'+esc(x.role)+'">Роль</button><button class="secondary" data-staff-warnings="'+x.telegram_id+'">Выговоры</button><button class="danger" data-staff-remove="'+x.telegram_id+'">Удалить</button></div><div id="staffWarnings'+x.telegram_id+'"></div>')+'</div>'
  }).join('');
  document.querySelectorAll('[data-staff-edit]').forEach(b=>b.onclick=()=>{document.getElementById('shopStaffId').value=b.dataset.staffEdit;document.getElementById('shopStaffRole').value=b.dataset.role;document.getElementById('shopStaffId').scrollIntoView({behavior:'smooth',block:'center'});});
  document.querySelectorAll('[data-staff-remove]').forEach(b=>b.onclick=async()=>{if(!confirm('Удалить администратора?'))return;try{await api('/api/admin/staff/'+b.dataset.staffRemove,{method:'DELETE'});await refreshAdmin()}catch(e){alert(e.message)}});
  document.querySelectorAll('[data-staff-warnings]').forEach(b=>b.onclick=async()=>{
   const id=b.dataset.staffWarnings,box=document.getElementById('staffWarnings'+id);if(!box)return;
   try{const warnings=await api('/api/admin/staff/'+id+'/warnings');box.innerHTML='<div class="muted">История выговоров</div>'+warnings.map(w=>'<div class="order">'+esc(w.reason)+'<div class="muted">'+esc(w.created_at)+' · выдал '+w.issued_by+'</div><button class="secondary" data-staff-unwarn="'+w.id+'">Снять</button></div>').join('')+'<button class="buy" id="staffWarnAdd">Выдать выговор</button>';
   box.querySelectorAll('[data-staff-unwarn]').forEach(el=>el.onclick=async()=>{try{await api('/api/admin/staff/'+id+'/warnings/'+el.dataset.staffUnwarn,{method:'DELETE'});await refreshAdmin()}catch(e){alert(e.message)}});
   box.querySelector('#staffWarnAdd').onclick=async()=>{const reason=prompt('Причина выговора (от 5 символов):');if(reason===null)return;try{await api('/api/admin/staff/'+id+'/warnings',{method:'POST',body:JSON.stringify({reason})});await refreshAdmin()}catch(e){alert(e.message)}};
   }catch(e){alert(e.message)}
  });
  }).catch(e=>{if(list)list.textContent=e.message});
  const add=document.getElementById('shopStaffAdd');if(add)add.onclick=async()=>{const telegram_id=Number(document.getElementById('shopStaffId').value),role=document.getElementById('shopStaffRole').value;if(!Number.isSafeInteger(telegram_id)||telegram_id<=0){alert('Введите корректный Telegram ID');return}try{await api('/api/admin/staff',{method:'POST',body:JSON.stringify({telegram_id,role})});await refreshAdmin()}catch(e){alert(e.message)}};
 }

 document.querySelectorAll('[data-player-details]').forEach(btn=>btn.addEventListener('click',async()=>{
 const token=btn.dataset.playerDetails,box=document.getElementById('detail-'+token);if(!box)return;
 if(!box.hidden){box.hidden=true;return}box.hidden=false;box.textContent='Загружаем статистику игрока…';
 try{const d=await api('/api/admin/players/'+encodeURIComponent(token)+'/details');const f=d.farm||{},sp=d.spin||{};
 const fields=[['Уровень фермы',f.level||1],['ShrekCOINS',f.shrek_coins||0],['UC Credits',f.uc_credits||0],['Предметы на складе',d.inventory?.total||0],['Виды ресурсов',d.inventory?.types||0],['Серия активности',f.activity_streak||0],['SHR',sp.upgrade_points||0],['Обычные билеты',sp.tickets||0],['Донат-билеты',d.donation_tickets||0],['Кейсов открыто',d.cases?.total||0],['Прокруток рулетки',d.spins?.total||0],['Заказов',d.orders?.total||0],['Stars потрачено',d.stars_spent||0]];
 box.innerHTML='<div class="shx-player-detail-grid">'+fields.map(x=>'<div title="'+Number(x[1]||0).toLocaleString('ru-RU')+' '+esc(x[0])+'"><small>'+x[0]+'</small><b>'+compactCurrency(x[1])+'</b></div>').join('')+'</div><small>Наведите на сумму, чтобы увидеть точное значение. Расход Stars рассчитан по зарегистрированным платежам за заказы и кейсы.</small>';
 }catch(e){box.textContent='Не удалось загрузить статистику: '+e.message}
 }));

 document.querySelectorAll('[data-copy-token]').forEach(b=>b.addEventListener('click',async()=>{const value=b.dataset.copyToken;if(!value)return;try{if(navigator.clipboard&&window.isSecureContext){await navigator.clipboard.writeText(value)}else{const t=document.createElement('textarea');t.value=value;t.style.position='fixed';t.style.opacity='0';document.body.appendChild(t);t.select();if(!document.execCommand('copy'))throw Error('copy');t.remove()}const old=b.innerHTML;b.innerHTML='✓ Скопировано: '+value;setTimeout(()=>{if(b.isConnected)b.innerHTML=old},1400)}catch(e){prompt('Скопируйте жетон:',value)}}));
 const sectionSelect=document.getElementById('shxAdminSectionSelect');if(sectionSelect){sectionSelect.value=adminSection;sectionSelect.addEventListener('change',()=>{adminSection=sectionSelect.value;app.innerHTML=adminNav()+'<main class="shx-owner-content">'+adminSectionHtml()+'</main></div></div>';bindAdmin()})}
 document.querySelectorAll('[data-admin]').forEach(b=>b.addEventListener('click',()=>{adminSection=b.dataset.admin;app.innerHTML=adminNav()+'<main class="shx-owner-content">'+adminSectionHtml()+'</main></div></div>';bindAdmin()}));
 const ucGrantBtn=document.getElementById('ucGrantBtn');if(ucGrantBtn)ucGrantBtn.onclick=async()=>{const token=document.getElementById('ucGrantToken').value.trim(),credits=Number(document.getElementById('ucGrantAmount').value),reason=document.getElementById('ucGrantReason').value.trim();if(!token||!Number.isInteger(credits)||credits<1||credits>100000||reason.length<5){alert('Введите жетон, UC (1–100000) и причину от 5 символов');return}if(!confirm('Начислить '+credits+' UC игроку '+token+'? UC будут списаны из фонда.'))return;ucGrantBtn.disabled=true;try{await api('/api/admin/uc-grant',{method:'POST',body:JSON.stringify({token,credits,reason})});alert('UC начислены');await refreshAdmin()}catch(e){alert(e.message);ucGrantBtn.disabled=false}};
 const fundBtn=document.getElementById('ucFundAdd');if(fundBtn)fundBtn.addEventListener('click',async()=>{
  const credits=Number(document.getElementById('ucFundAmount').value);
  const note=document.getElementById('ucFundNote').value.trim();
  const profit_verified=!!document.getElementById('ucFundVerified').checked;
  if(!profit_verified){alert('Подтвердите, что UC покрыты чистой прибылью');return}
  if(!Number.isInteger(credits)||credits<1||credits>100000||note.length<4){alert('Укажите количество UC и основание');return}
  if(!confirm('Выделить '+credits+' UC Credits из подтверждённой чистой прибыли?'))return;
  fundBtn.disabled=true;
  try{await api('/api/admin/uc-fund',{method:'POST',body:JSON.stringify({credits,note,profit_verified})});await refreshAdmin()}catch(e){alert(e.message);fundBtn.disabled=false}
 });

 document.querySelectorAll('[data-payout-action]').forEach(b=>b.addEventListener('click',async()=>{const action=b.dataset.payoutAction,id=b.dataset.payoutId;let reason='',payment_reference='';if(['freeze','reject'].includes(action)){reason=prompt('Причина (не менее 5 символов):')||'';if(reason.length<5)return}if(action==='paid'){payment_reference=prompt('Идентификатор и подтверждение ФАКТИЧЕСКОГО перевода:')||'';if(payment_reference.length<6)return}if(!confirm('Подтвердить действие '+action+' для заявки #'+id+'?'))return;b.disabled=true;try{await api('/api/admin/seller-payouts/'+id,{method:'POST',body:JSON.stringify({action,reason,payment_reference})});await refreshAdmin()}catch(e){alert(e.message);b.disabled=false}}));
 const adminSellerChange=async(sellerId,status)=>{
  try{await api('/api/admin/sellers/'+sellerId,{method:'PATCH',body:JSON.stringify({status,commission_pct:30})});await refreshAdmin()}catch(e){alert(e.message)}
 };
 document.querySelectorAll('[data-seller-history]').forEach(b=>b.addEventListener('click',async()=>{try{const d=await api('/api/admin/sellers/'+b.dataset.sellerHistory+'/history');const el=document.getElementById('sellerHistory'+b.dataset.sellerHistory);if(el)el.innerHTML='<h4>Выговоры</h4>'+(d.warnings.map(x=>'<div class="mini">⚠️ '+esc(x.reason)+' · '+esc(x.created_at)+'</div>').join('')||'<div class="mini">Нет выговоров</div>')+'<h4>Отзывы покупателей</h4>'+(d.reviews.map(x=>'<div class="mini">⭐ '+Number(x.rating)+'/5 · '+esc(x.comment)+' · '+esc(x.created_at)+'</div>').join('')||'<div class="mini">Пока нет отзывов</div>')}catch(e){alert(e.message)}}));
 document.querySelectorAll('[data-seller-warning]').forEach(b=>b.addEventListener('click',async()=>{const reason=prompt('Укажите причину выговора (не менее 5 символов)');if(reason===null)return;if(reason.trim().length<5){alert('Причина должна содержать не менее 5 символов');return}try{await api('/api/admin/sellers/'+b.dataset.sellerWarning+'/warnings',{method:'POST',body:JSON.stringify({reason:reason.trim()})});await refreshAdmin()}catch(e){alert(e.message)}}));
 document.querySelectorAll('[data-seller-contact]').forEach(b=>b.addEventListener('click',async()=>{const message=prompt('Сообщение продавцу от администрации (придёт в Telegram-бот):');if(!message||!message.trim())return;try{await api('/api/admin/sellers/'+b.dataset.sellerContact+'/contact',{method:'POST',body:JSON.stringify({message:message.trim()})});alert('Сообщение отправлено продавцу в Telegram')}catch(e){alert(e.message)}}));
 document.querySelectorAll('[data-seller-remove]').forEach(b=>b.addEventListener('click',async()=>{const reason=prompt('Укажите причину удаления продавца (минимум 5 символов):');if(reason===null)return;if(reason.trim().length<5){alert('Укажите причину от 5 символов');return}if(!confirm('Удалить статус продавца? Все его объявления будут скрыты, а повторное вступление потребует новой заявки. История заказов сохранится.'))return;try{await api('/api/admin/sellers/'+b.dataset.sellerRemove+'/remove',{method:'POST',body:JSON.stringify({reason:reason.trim()})});await refreshAdmin()}catch(e){alert(e.message)}}));
 document.querySelectorAll('[data-seller-approve]').forEach(b=>b.addEventListener('click',()=>adminSellerChange(b.dataset.sellerApprove,'approved')));
 document.querySelectorAll('[data-seller-block]').forEach(b=>b.addEventListener('click',()=>{if(confirm('Отключить продавца от новых заказов?'))adminSellerChange(b.dataset.sellerBlock,'blocked')}));
 const listingChange=async(id,status)=>{
  try{await api('/api/admin/seller-listings/'+id,{method:'PATCH',body:JSON.stringify({status})});await refreshAdmin()}catch(e){alert(e.message)}
 };
 document.querySelectorAll('[data-seller-listing-approve]').forEach(b=>b.addEventListener('click',()=>listingChange(b.dataset.sellerListingApprove,'active')));
 document.querySelectorAll('[data-seller-listing-pause]').forEach(b=>b.addEventListener('click',()=>listingChange(b.dataset.sellerListingPause,'paused')));
 document.querySelectorAll('[data-seller-listing-reject]').forEach(b=>b.addEventListener('click',()=>listingChange(b.dataset.sellerListingReject,'rejected')));
 document.querySelectorAll('[data-seller-complete]').forEach(b=>b.addEventListener('click',async()=>{
  if(!confirm('Покупатель действительно получил товар?'))return;
  try{await api('/api/admin/orders/'+b.dataset.sellerComplete,{method:'PATCH',body:JSON.stringify({status:'Выполнен'})});await refreshAdmin()}catch(e){alert(e.message)}
 }));
 document.querySelectorAll('[data-seller-settle]').forEach(b=>b.addEventListener('click',async()=>{
  const id=b.dataset.sellerSettle;
  const note=document.getElementById('sellerSettleNote'+id).value.trim();
  if(!confirm('Подтвердите, что расчёт с продавцом реально выполнен вне бота. Это только запись в учёте.'))return;
  try{await api('/api/admin/seller-orders/'+id+'/settle',{method:'POST',body:JSON.stringify({note})});await refreshAdmin()}catch(e){alert(e.message)}
 }));
 document.querySelectorAll('[data-order-save]').forEach(b=>b.addEventListener('click',async()=>{const id=b.dataset.orderSave;try{await api('/api/admin/orders/'+id,{method:'PATCH',body:JSON.stringify({status:document.getElementById('os'+id).value})});alert('Статус сохранён')}catch(e){alert(e.message)}}));
 const qg=document.getElementById('adminQuickGrant');if(qg)qg.addEventListener('click',()=>{adminSection='users';app.innerHTML=adminNav()+'<main class="shx-owner-content">'+adminUsers()+'</main>';bindAdmin()});
 document.querySelectorAll('[data-grant-player]').forEach(b=>b.addEventListener('click',()=>{const field=document.getElementById('grantToken');if(!field)return;field.value=b.dataset.grantPlayer;document.querySelector('.shx-admin-grant')?.scrollIntoView({behavior:'smooth',block:'start'});field.style.borderColor='#f1bd55';field.blur()}));
 const grantLimits={grantTickets:1000000000,grantDonation:1000000000,grantPts:1000000000,grantCoins:1000000000000};
 Object.entries(grantLimits).forEach(([id,max])=>{
  const field=document.getElementById(id);if(!field)return;
  field.max=String(max);field.min='0';field.title='Максимум за одну выдачу: '+max.toLocaleString('ru-RU');
  const clamp=()=>{if(field.value.trim()==='')return;const raw=Number(field.value);if(!Number.isFinite(raw)){field.value='0';return;}const safe=Math.max(0,Math.min(max,Math.floor(raw)));if(safe!==raw)field.value=String(safe);};
  field.addEventListener('input',()=>{if(field.value!==''&&Number(field.value)>max)field.value=String(max)});
  field.addEventListener('change',clamp);field.addEventListener('blur',clamp);
 });
 const clampAllGrants=()=>Object.entries(grantLimits).forEach(([id,max])=>{const field=document.getElementById(id);if(!field||field.value.trim()==='')return;const raw=Number(field.value);field.value=String(Number.isFinite(raw)?Math.max(0,Math.min(max,Math.floor(raw))):0);});
 const setBtn=document.getElementById('setBalanceBtn');if(setBtn)setBtn.addEventListener('click',async()=>{
 const token=document.getElementById('setBalanceToken').value.trim(),asset=document.getElementById('setBalanceAsset').value,raw=document.getElementById('setBalanceAmount').value,amount=Number(raw);
 const limits={shrek_coins:1000000000000000,shr:1000000000,tickets:1000000000,donation_tickets:1000000000,farm_item:1000000000};
 if(!token||raw.trim()===''||!Number.isSafeInteger(amount)||amount<0){alert('Укажите жетон и целое количество от нуля');return}
 const safe=Math.min(amount,limits[asset]);document.getElementById('setBalanceAmount').value=String(safe);
 const resource_id=document.getElementById('setBalanceResource').value.trim(),case_id=document.getElementById('setBalanceCase').value.trim()||'*';
 if(asset==='farm_item'&&!resource_id){alert('Укажите ID предмета');return}
 if(!confirm('Жетон: '+token+'\\n'+asset+' = '+safe.toLocaleString('ru-RU')+'\\nЗаменить текущее количество?'))return;
 setBtn.disabled=true;try{await api('/api/admin/balances/set',{method:'POST',body:JSON.stringify({token,asset,amount:safe,resource_id,case_id})});alert('Количество изменено');refreshAdmin()}catch(e){alert(e.message);setBtn.disabled=false}
 });
 const gb=document.getElementById('grantBtn');if(gb)gb.addEventListener('click',async()=>{clampAllGrants();const token=document.getElementById('grantToken').value.trim();const values=[['Обычные билеты','grantTickets'],['Донат-билеты','grantDonation'],['SHR','grantPts'],['ShrekCOINS','grantCoins']].map(x=>[x[0],Number(document.getElementById(x[1]).value||0)]).filter(x=>x[1]>0);if(!token){alert('Сначала выберите игрока');return}if(!values.length){alert('Укажите количество хотя бы одной награды');return}if(!confirm('Получатель: '+token+'\\n'+values.map(x=>x[0]+': '+x[1].toLocaleString('ru-RU')).join('\\n')+'\\n\\nПодтвердить начисление?'))return;gb.disabled=true;try{await api('/api/admin/rewards/grant',{method:'POST',body:JSON.stringify({token:document.getElementById('grantToken').value,tickets:Number(document.getElementById('grantTickets').value||0),donation_tickets:Number(document.getElementById('grantDonation').value||0),donation_case_id:document.getElementById('grantDonationCase').value,upgrade_points:Number(document.getElementById('grantPts').value||0),shrek_coins:Number(document.getElementById('grantCoins').value||0)})});alert('Награда выдана');refreshAdmin()}catch(e){alert(e.message);gb.disabled=false}});
 document.querySelectorAll('[data-message-user]').forEach(b=>b.addEventListener('click',()=>{adminSection='bot';app.innerHTML=adminNav()+'<main class="shx-owner-content">'+adminBot()+'</main>';document.getElementById('botUserToken').value=b.dataset.messageUser;bindAdmin()}));
 const np=document.getElementById('newPBtn');if(np)np.addEventListener('click',async()=>{try{await api('/api/admin/products',{method:'POST',body:JSON.stringify({name:document.getElementById('newPName').value,category:document.getElementById('newPCat').value,description:document.getElementById('newPDesc').value,stars_price:Number(document.getElementById('newPStars').value),sort_order:Number(document.getElementById('newPSort').value||0),active:true})});alert('Товар добавлен');refreshAdmin()}catch(e){alert(e.message)}});
 document.querySelectorAll('[data-product-delete]').forEach(b=>b.addEventListener('click',async()=>{
 const id=b.dataset.productDelete,name=b.dataset.productName||'Товар';
 if(!confirm('Удалить «'+name+'» из каталога НАВСЕГДА? Он исчезнет у всех пользователей и из админки. История уже созданных заказов сохранится.'))return;
 if(!confirm('Подтвердить окончательное удаление товара «'+name+'»?'))return;
 b.disabled=true;b.textContent='Удаление…';
 try{await api('/api/admin/products/'+encodeURIComponent(id),{method:'DELETE'});await refreshAdmin();alert('Товар удалён из каталога для всех пользователей.')}
 catch(e){b.disabled=false;b.textContent='✕ Удалить';alert('Не удалось удалить товар: '+e.message)}
}));
 document.querySelectorAll('[data-product-save]').forEach(b=>b.addEventListener('click',async()=>{const id=b.dataset.productSave,card=document.querySelector('[data-product-card="'+id+'"]'),v=n=>card.querySelector('[data-p="'+n+'"]');try{await api('/api/admin/products/'+id,{method:'PATCH',body:JSON.stringify({name:v('name').value,category:v('category').value,description:v('description').value,stars_price:Number(v('stars_price').value),sort_order:Number(v('sort_order').value||0),active:v('active').checked})});alert('Товар сохранён')}catch(e){alert(e.message)}}));
 document.querySelectorAll('[data-case-save]').forEach(b=>b.addEventListener('click',async()=>{
  const card=document.querySelector('[data-case-admin="'+b.dataset.caseSave+'"]'),v=n=>card.querySelector('[data-ca="'+n+'"]');
  const tiers={};[...card.querySelectorAll('[data-case-tier-enabled]')].filter(x=>x.checked).forEach(x=>tiers[x.dataset.caseTierEnabled]=Number(card.querySelector('[data-case-tier-chance="'+x.dataset.caseTierEnabled+'"]').value||0));
  const contents=[...card.querySelectorAll('[data-case-item]:checked')].map(x=>x.dataset.caseItem);
  try{
   await api('/api/admin/cases/'+encodeURIComponent(b.dataset.caseSave),{method:'PATCH',body:JSON.stringify({name:v('name').value,description:v('description').value,icon:v('icon').value,stars_price:Number(v('stars_price').value||0),is_free:v('is_free').checked,active:v('active').checked,sort_order:Number(v('sort_order').value||0),tiers,contents})});
   alert('Кейс сохранён');refreshAdmin()
  }catch(e){alert(e.message)}
 }));
 const pc=document.getElementById('promoCreateBtn');if(pc)pc.addEventListener('click',async()=>{try{await api('/api/admin/promos',{method:'POST',body:JSON.stringify({code:document.getElementById('promoCodeNew').value,promo_type:document.getElementById('promoTypeNew').value,discount_percent:Number(document.getElementById('promoDiscountNew').value||0),spin_tickets:Number(document.getElementById('promoSpinNew').value||0),donation_tickets:Number(document.getElementById('promoDonationNew').value||0),case_id:document.getElementById('promoDonationCaseNew').value,max_uses:Number(document.getElementById('promoUsesNew').value||0),expires_at:document.getElementById('promoExpiryNew').value})});alert('Промокод создан');refreshAdmin()}catch(e){alert(e.message)}});
 document.querySelectorAll('[data-promo-toggle]').forEach(b=>b.addEventListener('click',async()=>{try{await api('/api/admin/promos/'+b.dataset.promoToggle,{method:'PATCH',body:JSON.stringify({active:!(Number(b.dataset.active)===1)})});refreshAdmin()}catch(e){alert(e.message)}}));
 document.querySelectorAll('[data-promo-del]').forEach(b=>b.addEventListener('click',async()=>{if(!confirm('Удалить промокод?'))return;try{await api('/api/admin/promos/'+b.dataset.promoDel,{method:'DELETE'});refreshAdmin()}catch(e){alert(e.message)}}));
 document.querySelectorAll('[data-ticket-reply]').forEach(b=>b.addEventListener('click',async()=>{const id=b.dataset.ticketReply;try{await api('/api/admin/tickets/'+id+'/reply',{method:'POST',body:JSON.stringify({message:document.getElementById('tr'+id).value})});alert('Ответ отправлен');refreshAdmin()}catch(e){alert(e.message)}}));
 document.querySelectorAll('[data-ticket-close]').forEach(b=>b.addEventListener('click',async()=>{try{await api('/api/admin/tickets/'+b.dataset.ticketClose+'/close',{method:'POST'});refreshAdmin()}catch(e){alert(e.message)}}));
 const bs=document.getElementById('botSendBtn');if(bs)bs.addEventListener('click',async()=>{try{await api('/api/admin/message',{method:'POST',body:JSON.stringify({token:document.getElementById('botUserToken').value,message:document.getElementById('botUserMsg').value})});alert('Сообщение отправлено')}catch(e){alert(e.message)}});
 const us=document.getElementById('userSearch');if(us){
 const players=Array.from(document.querySelectorAll('.user-row'));
 const hint=document.createElement('div');hint.id='adminSearchHint';hint.style.cssText='color:#9bc7df;font-size:13px;margin:-5px 0 14px;line-height:1.4';us.closest('.shx-grant-field')?.appendChild(hint);
 const search=()=>{
  const q=us.value.trim().toLocaleLowerCase('ru-RU').replace(/^@/,'');
  const found=players.filter(row=>{const name=String(row.dataset.search||'').toLocaleLowerCase('ru-RU');const match=!q||name.includes(q)||name.replace(/[-_\\s]/g,'').includes(q.replace(/[-_\\s]/g,''));row.style.display=match?'':'none';return match});
  const recipient=document.getElementById('grantToken');
  if(q&&found.length===1){const token=found[0].querySelector('[data-grant-player]')?.dataset.grantPlayer;if(token&&recipient)recipient.value=token}
  if(q&&found.length===0&&/^shx[-_]/i.test(us.value.trim())){if(recipient)recipient.value=us.value.trim().toUpperCase();hint.textContent='Игрок не найден в загруженном списке. Жетон подставлен для проверки при выдаче.'}
  else hint.textContent=q?(found.length?'Найдено игроков: '+found.length+(found.length===1?' · Жетон выбран автоматически':' · Нажмите «Выбрать для выдачи» у нужного игрока'):'Игрок не найден. Проверьте ник или жетон.'):'Введите ник, имя или жетон для поиска.';
 };
 us.addEventListener('input',search);search();
}
 document.querySelectorAll('[data-copy-pubg-uid]').forEach(b=>b.addEventListener('click',async()=>{const uid=b.dataset.copyPubgUid;if(!uid){alert('PUBG UID отсутствует в заявке');return}try{if(navigator.clipboard&&window.isSecureContext){await navigator.clipboard.writeText(uid)}else{const input=document.createElement('textarea');input.value=uid;input.style.position='fixed';input.style.opacity='0';document.body.appendChild(input);input.select();if(!document.execCommand('copy'))throw Error('copy failed');input.remove()}const label=b.querySelector('.shx-uc-copy-action');if(label){label.textContent='✓ ID скопирован';setTimeout(()=>{if(label.isConnected)label.textContent='📋 Копировать ID'},1800)}}catch(e){prompt('Скопируйте PUBG UID:',uid)}}));
 document.querySelectorAll('[data-uc-contact]').forEach(b=>b.addEventListener('click',async()=>{const token=b.dataset.ucToken,msg=document.getElementById('ucMsg'+b.dataset.ucContact),message=msg?.value.trim();if(!message){alert('Введите сообщение игроку');return}b.disabled=true;try{await api('/api/admin/uc-chats/'+b.dataset.ucContact+'/messages',{method:'POST',body:JSON.stringify({message})});msg.value='';alert('Сообщение отправлено в чат')}catch(e){alert(e.message)}finally{b.disabled=false}}));
 document.querySelectorAll('[data-uc-chat-open]').forEach(b=>b.addEventListener('click',async()=>{const id=b.dataset.ucChatOpen,target=document.getElementById('ucChatHistory'+id);if(target.dataset.expanded==='true'){target.replaceChildren();target.dataset.expanded='false';return}try{const d=await api('/api/admin/uc-chats/'+id),chat=d.chat;await api('/api/admin/uc-chats/'+id+'/read',{method:'POST'}).catch(()=>{});refreshAdminUCUnread();target.dataset.expanded='true';target.innerHTML='<div class="mini">Статус: '+esc(chat?.status||'Не создан')+'</div>'+(d.messages||[]).map(m=>'<div class="shx-chat-msg"><b>'+(m.sender==='admin'?'Администратор':'Игрок')+'</b> · '+esc(m.created_at)+'<p>'+esc(m.message)+'</p></div>').join('')+'<button type="button" class="secondary" data-uc-set-chat="'+id+'" data-next-status="'+(chat?.status==='Открыт'?'Закрыт':'Открыт')+'">'+(chat?.status==='Открыт'?'🔒 Закрыть чат':'🔓 Открыть чат')+'</button>';target.querySelector('[data-uc-set-chat]').onclick=async e=>{const btn=e.currentTarget;try{await api('/api/admin/uc-chats/'+id,{method:'PATCH',body:JSON.stringify({status:btn.dataset.nextStatus})});target.dataset.expanded='false';b.click()}catch(err){alert(err.message)}}}catch(e){alert(e.message)}}));
 document.querySelectorAll('[data-farm-wd-ok]').forEach(b=>b.addEventListener('click',async()=>{if(!confirm('Подтвердить, что UC уже выданы игроку?'))return;try{await api('/api/admin/farm-withdrawals/'+b.dataset.farmWdOk,{method:'PATCH',body:JSON.stringify({status:'Выполнен'})});refreshAdmin()}catch(e){alert(e.message)}}));
 document.querySelectorAll('[data-farm-wd-no]').forEach(b=>b.addEventListener('click',async()=>{try{await api('/api/admin/farm-withdrawals/'+b.dataset.farmWdNo,{method:'PATCH',body:JSON.stringify({status:'Отклонён'})});refreshAdmin()}catch(e){alert(e.message)}}));
 const br=document.getElementById('broadcastBtn');if(br)br.addEventListener('click',async()=>{if(!confirm('Отправить всем пользователям?'))return;try{await api('/api/admin/broadcast',{method:'POST',body:JSON.stringify({message:document.getElementById('broadcastMsg').value})});alert('Рассылка запущена')}catch(e){alert(e.message)}})
}

async function render(){
 updateNav();app.innerHTML='<div class="empty">Загрузка…</div>';
 try{
  if(ADMIN){app.innerHTML=await adminHtml();bindAdmin();return}
  if(tab==='home'){try{homeFarmData=await api('/api/farm')}catch(_){} app.innerHTML=home();bindHome()}
  else if(tab==='catalog'){products=await api('/api/catalog');app.innerHTML=marketplaceCatalogHtml();bindMarketplaceCatalog()}
  else if(tab==='seller'){app.innerHTML=await sellerHtml();bindSeller()}
  else if(tab==='spin'){app.innerHTML=await spinHtml();bindSpin()}
  else if(tab==='roulette'){app.innerHTML=await rouletteHtml();bindRoulette()}
  else if(tab==='orders'){app.innerHTML=await ordersHtml();bindOrders()}
  else if(tab==='inventory'){app.innerHTML=await inventoryHtml();bindInventory()}
  else if(tab==='farm'){app.innerHTML=await farmHtml();bindFarm()}
  else if(tab==='farm-catalog'){app.innerHTML=await farmCatalogPage();bindFarmCatalogPage()}
  else if(tab==='profile'){try{homeFarmData=await api('/api/farm')}catch(_){} try{const unread=await api('/api/uc-chats/unread');ucUnreadCount=Number(unread.unread||0)}catch(_){} app.innerHTML=profileHtml();bindProfile()}
  else if(tab==='referral'){app.innerHTML=await referralHtml();bindReferral()}
  else if(tab==='support'){app.innerHTML=await supportHtml();bindSupport()}
  else if(tab==='settings'){app.innerHTML=settingsHtml();bindSettings()}
  else if(tab==='case-catalog'){app.innerHTML=await caseCatalogHtml();bindCaseCatalog()}
  else if(tab==='drop-history'){app.innerHTML=await dropHistoryHtml();bindDropHistory()}
  addHomeExit()
  if(tab==='farm'&&farmJumpTarget){const target=farmJumpTarget;farmJumpTarget='';const node=document.querySelector(target==='uc'?'.farm-withdraw':'.farm-activity');if(node)node.scrollIntoView({behavior:'smooth',block:'start'})}
 }catch(e){showFatal(e.message)}
}
document.querySelectorAll('#nav button').forEach(b=>b.addEventListener('click',()=>go(b.dataset.tab)));

async function boot(){
 try{
  if(localStorage.getItem('shx_sound_repair_v5')!=='1'){
   localStorage.setItem('shx_sound_enabled','1');
   localStorage.setItem('shx_sound_repair_v5','1')
  }
  products=await api('/api/catalog');
  me=await api('/api/me');
  if(ADMIN&&!me.owner)throw new Error('Нет доступа');
  await loadWinsFeed();setInterval(loadWinsFeed,20000);await render();if(ADMIN){refreshAdminUCUnread();setInterval(refreshAdminUCUnread,15000)}else{refreshUCUnread();setInterval(refreshUCUnread,15000)}
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
