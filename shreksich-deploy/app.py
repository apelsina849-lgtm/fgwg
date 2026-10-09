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
        "id":row["id"],"name":row["name"],"description":row["description"],"icon":row["icon"],
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

FARM_MAX_LEVEL = 20
FARM_WITHDRAW_MIN_UC = 120
FARM_DAILY_UC_CREDITS = 2
FARM_TIER_ORDER = ("GRAY","CYAN","BLUE","PURPLE","PINK","RED","GOLD")

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
]
FARM_RESOURCE_BY_ID = {x["id"]:x for x in FARM_RESOURCES}

# Улучшения фермы за ShrekCOINS. Эти монеты нельзя обменять на Stars/UC.
FARM_COIN_MAX_LEVEL = 5
FARM_COIN_MODULES = {
    "drill": {"column":"drill_level", "name":"Фермерские инструменты", "icon":"🪓", "base":55,
              "description":"Качественные инструменты ускоряют сбор ресурсов на 9% за уровень."},
    "warehouse": {"column":"warehouse_level", "name":"Вместительный амбар", "icon":"🧺", "base":85,
                  "description":"Каждый уровень добавляет 24 места для добычи."},
    "trader": {"column":"trader_level", "name":"Торговая лавка", "icon":"⚖️", "base":120,
               "description":"Цена продажи добычи повышается на 15% за уровень."},
}

def farm_coin_upgrade_cost(module: str, level: int) -> int:
    spec = FARM_COIN_MODULES[module]
    return int(round(spec["base"] * (1.75 ** max(0, min(level, FARM_COIN_MAX_LEVEL)))))

def farm_mining_interval(level: int, drill_level: int = 0) -> int:
    return max(90, farm_interval_seconds(level) * (100 - 9 * max(0,min(FARM_COIN_MAX_LEVEL,int(drill_level)))) // 100)

def farm_total_capacity(level: int, warehouse_level: int = 0) -> int:
    return farm_capacity(level) + 24 * max(0,min(FARM_COIN_MAX_LEVEL,int(warehouse_level)))

def farm_sale_price(item: dict, trader_level: int = 0) -> int:
    return max(1, int(round(int(item["coins"]) * (100 + 15 * max(0,min(FARM_COIN_MAX_LEVEL,int(trader_level)))) / 100)))

def farm_coin_modules(state) -> list[dict]:
    results = []
    for key, spec in FARM_COIN_MODULES.items():
        level = max(0, min(FARM_COIN_MAX_LEVEL, int(state[spec["column"]] or 0)))
        results.append({
            "id":key, "name":spec["name"], "icon":spec["icon"],
            "description":spec["description"], "level":level,
            "max_level":FARM_COIN_MAX_LEVEL,
            "cost":farm_coin_upgrade_cost(key,level) if level<FARM_COIN_MAX_LEVEL else 0
        })
    return results

def farm_upgrade_cost(level: int) -> int:
    level = max(1,min(FARM_MAX_LEVEL,int(level)))
    if level >= FARM_MAX_LEVEL:
        return 0
    return int(round(25 * (1.48 ** (level - 1))))

def farm_interval_seconds(level: int) -> int:
    level = max(1,min(FARM_MAX_LEVEL,int(level)))
    return max(180, 600 - (level - 1) * 22)

def farm_capacity(level: int) -> int:
    level = max(1,min(FARM_MAX_LEVEL,int(level)))
    return 36 + level * 12

def farm_stage(level: int) -> int:
    return min(5, 1 + (max(1,int(level)) - 1)//4)

def farm_tier_weights(level: int) -> dict[str,float]:
    p = (max(1,min(FARM_MAX_LEVEL,int(level))) - 1) / max(1,FARM_MAX_LEVEL - 1)
    # Редкие ресурсы действительно редкие. Веса меняются с уровнем, сумма всегда 100%.
    # lvl 1: 78 / 16 / 5 / 1 / 0 / 0 / 0
    # lvl 20: 65 / 20 / 9 / 4 / 1.2 / 0.5 / 0.3
    starting = {"GRAY":78, "CYAN":16, "BLUE":5, "PURPLE":1, "PINK":0, "RED":0, "GOLD":0}
    ending = {"GRAY":65, "CYAN":20, "BLUE":9, "PURPLE":4, "PINK":1.2, "RED":0.5, "GOLD":0.3}
    weights = {tier:starting[tier] + (ending[tier] - starting[tier])*p for tier in FARM_TIER_ORDER}
    total = sum(weights.values()) or 1
    return {k:round(v*100/total,3) for k,v in weights.items()}

def pick_farm_resource(level: int) -> dict:
    weights = farm_tier_weights(level)
    tiers = list(FARM_TIER_ORDER)
    tier = random.choices(tiers,weights=[weights[t] for t in tiers],k=1)[0]
    pool = [x for x in FARM_RESOURCES if x["tier"] == tier]
    return random.choice(pool)

async def ensure_farm_state(conn, uid: int):
    row = await (await conn.execute("SELECT * FROM farm_state WHERE telegram_id=?",(uid,))).fetchone()
    if row:
        return row
    now = int(time.time())
    await conn.execute(
        "INSERT INTO farm_state(telegram_id,level,shrek_coins,uc_credits,uc_reserved,last_mine_at,last_collect_at,last_activity_at,activity_streak,activity_total) "
        "VALUES(?,1,0,0,0,?,?,0,0,0)",
        (uid,now-farm_interval_seconds(1),0)
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
        "drill_level":"INTEGER NOT NULL DEFAULT 0",
        "warehouse_level":"INTEGER NOT NULL DEFAULT 0",
        "trader_level":"INTEGER NOT NULL DEFAULT 0",
    }.items():
        if col not in farm_cols:
            await conn.execute(f"ALTER TABLE farm_state ADD COLUMN {col} {ddl}")

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
                 {"text":"🎰 Рулетки","web_app":{"url":BASE_URL + "/?tab=spin"}}])
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
        "🎰 <b>SPIN:</b> до 3 бесплатных вращений за 24 часа + бонусные билеты от админа и рефералов.\n"
        "🎟 <b>Промокоды:</b> вводятся при оформлении заказа и уменьшают цену в Stars.\n"
        "👥 <b>Рефералы:</b> после первой оплаченной покупки приглашённого вы получаете 1 бонусный SPIN-билет и 3 SHR.\n"
        "🌾 <b>Ферма:</b> команда /farm откроет добычу ресурсов, склад и улучшения за ShrekCOINS.\n"
        "💬 <b>Поддержка:</b создайте обращение в Mini App или напишите в нашем чате."
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
    if msg and text.split("@")[0].split(" ")[0] == "/farm":
        await send_farm(int(msg["chat"]["id"]))
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
                    await conn.execute(
                        "UPDATE orders SET status='Оплачен',payment_method='Telegram Stars',telegram_charge_id=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                        (charge_id,oid)
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
    donation_tickets: int = Field(default=0, ge=0, le=100)
    donation_case_id: str = Field(default="*", max_length=32)
    upgrade_points: int = Field(default=0, ge=0, le=10000)


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
    allowed_tiers = {"ALL","GRAY","CYAN","BLUE","PURPLE","PINK","RED","GOLD","COMMON","RARE","EPIC","LEGENDARY","MYTHIC"}
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
            "SELECT resource_id,qty FROM farm_inventory WHERE telegram_id=? AND qty>0 ORDER BY updated_at DESC",
            (uid,)
        )).fetchall()
        spin = await (await conn.execute("SELECT upgrade_points FROM spin_state WHERE telegram_id=?",(uid,))).fetchone()
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
    cap = farm_total_capacity(level,warehouse_level)
    available_cycles = max(0,min(cap-stored,(now-int(state["last_mine_at"] or now))//interval))
    inventory = []
    for r in inv_rows:
        item = FARM_RESOURCE_BY_ID.get(r["resource_id"])
        if item:
            inventory.append({**item,"coins":farm_sale_price(item,trader_level),"qty":int(r["qty"] or 0),"total_coins":int(r["qty"] or 0)*farm_sale_price(item,trader_level)})
    activity_ready = bool(int(state["last_collect_at"] or 0) > int(state["last_activity_at"] or 0) and now-int(state["last_activity_at"] or 0)>=20*3600)
    return {
        "level":level,"max_level":FARM_MAX_LEVEL,"stage":farm_stage(level),
        "shr":int(spin["upgrade_points"] or 0) if spin else 0,
        "shrek_coins":int(state["shrek_coins"] or 0),
        "uc_credits":int(state["uc_credits"] or 0),
        "uc_reserved":int(state["uc_reserved"] or 0),
        "uc_available":max(0,int(state["uc_credits"] or 0)-int(state["uc_reserved"] or 0)),
        "withdraw_min_uc":FARM_WITHDRAW_MIN_UC,
        "daily_uc_credits":FARM_DAILY_UC_CREDITS,
        "interval_seconds":interval,"capacity":cap,"stored":stored,
        "available_cycles":int(available_cycles),
        "next_cycle_seconds":(0 if available_cycles>0 else max(0,interval-max(0,now-int(state["last_mine_at"] or now))%interval)) if stored<cap else 0,
        "upgrade_cost":farm_upgrade_cost(level),
        "coin_upgrades":farm_coin_modules(state),
        "tier_weights":farm_tier_weights(level),
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
            capacity = farm_total_capacity(level,int(state["warehouse_level"] or 0))
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
                item = pick_farm_resource(level)
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
                "SELECT resource_id,qty FROM farm_inventory WHERE telegram_id=? AND qty>0",(uid,)
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
                raise HTTPException(409,"Склад пуст")
            await conn.execute("UPDATE farm_inventory SET qty=0,updated_at=CURRENT_TIMESTAMP WHERE telegram_id=?",(uid,))
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
            await conn.execute("UPDATE spin_state SET upgrade_points=upgrade_points-? WHERE telegram_id=?",(cost,uid))
            await conn.execute("UPDATE farm_state SET level=level+1,updated_at=CURRENT_TIMESTAMP WHERE telegram_id=?",(uid,))
            await conn.execute("INSERT INTO farm_log(telegram_id,action,details) VALUES(?,?,?)",(uid,"upgrade",json.dumps({"from":level,"to":level+1,"shr":cost})))
            await conn.commit()
        finally:
            await conn.close()
    return {"ok":True,"level":level+1,"cost":cost}


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
            if old_level >= FARM_COIN_MAX_LEVEL:
                await conn.rollback()
                raise HTTPException(409,"Модуль уже максимально улучшен")
            cost = farm_coin_upgrade_cost(module,old_level)
            if int(state["shrek_coins"] or 0) < cost:
                await conn.rollback()
                raise HTTPException(409,f"Нужно {cost} ShrekCOINS")
            if module == "drill":
                now = int(time.time())
                base_level = int(state["level"] or 1)
                previous_interval = farm_mining_interval(base_level,old_level)
                improved_interval = farm_mining_interval(base_level,old_level+1)
                elapsed = max(0,now-int(state["last_mine_at"] or now))
                complete_cycles, part_seconds = divmod(elapsed,previous_interval)
                adjusted_elapsed = complete_cycles*improved_interval + part_seconds*improved_interval//previous_interval
                await conn.execute("UPDATE farm_state SET last_mine_at=? WHERE telegram_id=?",(now-adjusted_elapsed,uid))
            column = spec["column"]  # Только фиксированные серверные имена, не данные запроса.
            await conn.execute(
                f"UPDATE farm_state SET shrek_coins=shrek_coins-?,{column}={column}+1,updated_at=CURRENT_TIMESTAMP WHERE telegram_id=?",
                (cost,uid)
            )
            await conn.execute("INSERT INTO farm_log(telegram_id,action,details) VALUES(?,?,?)",
                               (uid,"coin_upgrade",json.dumps({"module":module,"from":old_level,"to":old_level+1,"coins":cost})))
            await conn.commit()
        finally:
            await conn.close()
    return {"ok":True,"module":module,"level":old_level+1,"spent":cost}


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
            if not item or item["tier"] not in ("PURPLE","PINK","RED","GOLD"):
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
            "COALESCE((SELECT SUM(d.tickets) FROM donation_ticket_balances d WHERE d.telegram_id=u.telegram_id),0) donation_tickets,"
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
    if body.tickets <= 0 and body.donation_tickets <= 0 and body.upgrade_points <= 0:
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
        "donation_case_id":target_case,"upgrade_points_added":body.upgrade_points
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
.wins-track{display:flex;align-items:center;gap:28px;white-space:nowrap;width:max-content;padding-left:65px;animation:ticker 24s linear infinite;will-change:transform}
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
function setSpinNavigationLocked(on){
 spinNavigationLocked=!!on;
 if(navEl)navEl.classList.toggle('spin-locked',spinNavigationLocked);
 document.querySelectorAll('#nav button').forEach(b=>b.disabled=spinNavigationLocked);
 const home=document.getElementById('pageHomeBtn');if(home)home.disabled=spinNavigationLocked;
 const note=document.getElementById('spinLockNote');if(note)note.classList.toggle('show',spinNavigationLocked)
}
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
 '<section class="shx-profile"><div class="shx-profile-top"><div class="shx-avatar">'+esc(display.replace(/^@/,'').charAt(0).toUpperCase()||'S')+'</div><div><div class="shx-username">'+esc(display)+'</div><div class="shx-user-sub">Жетон '+esc(u.token||'—')+'</div></div><button class="shx-profile-quick" data-go="profile" aria-label="Профиль">⚙</button></div>'+
 '<div class="shx-wallets"><div class="shx-wallet">'+farmCoinIcon()+'<div><div class="shx-wallet-count">'+Number(f.shrek_coins||0).toLocaleString('ru-RU')+'</div><div class="shx-wallet-name">ShrekCOIN</div></div></div>'+
 '<div class="shx-wallet">'+farmUcIcon()+'<div><div class="shx-wallet-count">'+Number(f.uc_available||0).toLocaleString('ru-RU')+'</div><div class="shx-wallet-name">UC Credits</div></div></div>'+
 '<div class="shx-wallet"><div class="shx-star">✦</div><div><div class="shx-wallet-count">'+Number(f.shr||0).toLocaleString('ru-RU')+'</div><div class="shx-wallet-name">SHR</div></div></div></div></section>'+
 '<div class="shx-caption">PUBG MOBILE · METRO ROYALE · ШРЕКСИЧ SHOP</div>'+
 '<div class="shx-tiles">'+
 homeTile('Каталог','Товары и услуги','catalog','catalog')+
 homeTile('Кейсы','Открывай за Stars','cases','spin')+
 homeTile('Рулетки','Крути колесо','spin','roulette')+
 homeTile('Ферма','Добывай ресурсы','farm','farm','','НОВИНКА')+
 homeTile('Награды','Активность и UC','tasks','farm','activity')+
 homeTile('Промокоды','Бонусные билеты','promo','spin')+
 homeTile('Вывод UC','Обмен UC Credits','uc','farm','uc')+
 homeTile('Поддержка','Помощь и вопросы','help','support')+
 '</div>'+
 '<section class="shx-live"><div class="shx-live-head"><span>LIVE ДРОПЫ</span><small><span class="shx-online"></span>Реальные находки игроков</small></div><div id="homeLiveCards">'+homeWinsHtml()+'</div></section>'+
 '<div class="shx-panel"><h3>Другие разделы</h3><div class="shx-profile-actions"><button data-go="inventory">🎒 Инвентарь</button><button data-go="orders">📦 Мои заказы</button><button data-go="referral">👥 Пригласить друзей</button><button data-go="settings">⚙ Настройки</button></div></div>'+
 '</div>';
}
function bindHome(){
 document.querySelectorAll('[data-go]').forEach(b=>b.addEventListener('click',()=>{farmJumpTarget=b.dataset.goSection||'';go(b.dataset.go)}));
}
function profileHtml(){
 const u=me||{},f=homeFarmData||farmCachedData||{},display=String(u.username?'@'+u.username:u.first_name||'Игрок');
 return '<div class="shx-page-title"><button class="shx-back" data-go="home">← Главная</button><h1>Профиль</h1></div>'+
 '<section class="shx-profile"><div class="shx-profile-top"><div class="shx-avatar">'+esc(display.replace(/^@/,'').charAt(0).toUpperCase()||'S')+'</div><div><div class="shx-username">'+esc(display)+'</div><div class="shx-user-sub">Жетон: '+esc(u.token||'—')+'</div></div></div>'+
 '<div class="shx-wallets"><div class="shx-wallet">'+farmCoinIcon()+'<div><div class="shx-wallet-count">'+Number(f.shrek_coins||0)+'</div><div class="shx-wallet-name">ShrekCOIN</div></div></div><div class="shx-wallet">'+farmUcIcon()+'<div><div class="shx-wallet-count">'+Number(f.uc_available||0)+'</div><div class="shx-wallet-name">UC Credits</div></div></div><div class="shx-wallet"><div class="shx-star">✦</div><div><div class="shx-wallet-count">'+Number(f.shr||0)+'</div><div class="shx-wallet-name">SHR</div></div></div></div></section>'+
 '<section class="shx-panel"><h3>Управление аккаунтом</h3><div class="shx-profile-actions"><button data-go="orders">📦 Мои заказы</button><button data-go="inventory">🎒 Инвентарь</button><button data-go="farm">🌾 Моя ферма</button><button data-go="referral">👥 Рефералы</button><button data-go="settings">⚙ Настройки</button><button data-go="support">💬 Поддержка</button></div></section>';
}
function bindProfile(){document.querySelectorAll('[data-go]').forEach(b=>b.addEventListener('click',()=>go(b.dataset.go)));}

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
 if(!reward||!['RED','GOLD','LEGENDARY','MYTHIC'].includes(reward.tier))return;
 const top=reward.tier==='GOLD'||reward.tier==='LEGENDARY';
 try{if(tg&&tg.HapticFeedback){tg.HapticFeedback.notificationOccurred('success');tg.HapticFeedback.impactOccurred('heavy')}}catch(_){}
 const fx=document.createElement('div');fx.className='drop-fx '+reward.tier.toLowerCase();
 fx.innerHTML='<div class="drop-card"><div class="drop-content"><h2>'+(top?'GOLD DROP!':'RED DROP!')+'</h2><div class="drop-name">'+esc(reward.name)+'</div>'+rarityBar(reward.tier)+'<div class="muted" style="margin-top:12px">Продажа: '+reward.points+' SHR</div><button class="buy" id="closeDrop" style="margin-top:18px">ЗАБРАТЬ</button></div></div>';
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
 const labels={GRAY:'СЕРЫЙ',CYAN:'ГОЛУБОЙ',BLUE:'СИНИЙ',PURPLE:'ФИОЛЕТОВЫЙ',PINK:'РОЗОВЫЙ',RED:'КРАСНЫЙ',GOLD:'ЗОЛОТОЙ',COMMON:'COMMON',RARE:'RARE',EPIC:'EPIC',LEGENDARY:'LEGENDARY',MYTHIC:'MYTHIC'};
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
 if(s==='ticket')return '🎟 Бонусный билет';
 if(s==='free')return '🕐 Бесплатный SPIN';
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
 return '<section class="rarity-catalog"><div class="rarity-catalog-head"><h3>Качество кубиков</h3><div class="mini">Нажмите на кубик<br>чтобы посмотреть содержимое</div></div><div class="rarity-scroll">'+
 tiers.map(t=>{
   const count=(spinState.rewards||[]).filter(x=>x.tier===t).length;
   return '<button type="button" class="rarity-card" data-rarity-open="'+t+'"><div class="loot-cube '+cubeClass(t)+'"><span>?</span></div><div class="rarity-card-title '+tierClass(t)+'">'+tierLabel(t)+'</div><div class="rarity-card-chance">'+tierChance(t)+'%</div><div class="rarity-card-count">'+count+' предметов</div></button>'
 }).join('')+'</div></section><div class="rarity-modal hide" id="rarityModal"><div class="rarity-sheet" id="raritySheet"></div></div>'
}
function openRarityModal(tier){
 const modal=document.getElementById('rarityModal'),sheet=document.getElementById('raritySheet');
 if(!modal||!sheet)return;
 const items=(spinState.rewards||[]).filter(x=>x.tier===tier).slice().sort((a,b)=>Number(a.value_stars||0)-Number(b.value_stars||0));
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
function spinSourceLabel(source){
 const s=String(source||'');
 if(s==='ticket')return '🎟 Бонусный билет';
 if(s==='free')return '🕐 Бесплатный SPIN';
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
 }).join('')+'</div><div class="spin-case-note">Платные кейсы открываются за Telegram Stars. Синий Donation Ticket открывает донат-кейс без списания Stars.</div></section>'
}
function bindSpinCasePicker(){
 document.querySelectorAll('[data-spin-case]').forEach(b=>b.addEventListener('click',async()=>{
  if(spinNavigationLocked||spinState?.pending_drop)return;
  selectedCaseId=b.dataset.spinCase||'CASE29';
  localStorage.setItem('shx_selected_case',selectedCaseId);
  app.innerHTML=await spinHtml();bindSpin();addHomeExit()
 }))
}
function selectedCaseIdleStrip(){
 const cfg=selectedCase();
 if(!cfg||!cfg.tiers||!cfg.tiers.length)return idleCubeStrip();
 let arr=[];
 for(const t of cfg.tiers){
  const copies=Math.max(1,Math.round(Number(t.chance||0)/10));
  for(let i=0;i<copies;i++)arr.push(t.tier)
 }
 if(!arr.length)arr=['GRAY'];
 while(arr.length<9)arr=arr.concat(arr);
 return arr.slice(0,9).map(t=>cubeHtml(t)).join('')
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
async function rouletteHtml(){
 spinState=await api('/api/spin/state');
 const cfg=spinState.roulette,enabled=!!(cfg&&cfg.active),pending=spinState.pending_drop,paid=spinState.paid_case_opening;
 const wheel=makeRouletteWheel(cfg);rouletteSlices=wheel.slices;
 const free=Number(spinState.free_remaining||0),ticket=Number(spinState.bonus_tickets||0);
 const ready=enabled&&!pending&&!paid&&(free+ticket)>0;
 const note=pending?'Приз уже выпал: сначала сохраните или продайте его.':paid?'Сначала заберите оплаченный кейс во вкладке «Кейсы».':!enabled?'Рулетка отключена администратором.':free>0?'Вращение бесплатное. Результат выбирает сервер.':ticket>0?'Будет использован один бонусный билет.':'Следующая бесплатная прокрутка через '+formatReset(spinState.next_reset_seconds);
 const history=(spinState.history||[]).filter(x=>x.source==='free'||x.source==='ticket').slice(0,5).map(x=>'<div class="order"><div class="name">'+esc(x.reward_name)+'</div><div class="mini">'+tierLabel(x.reward_tier)+' · '+formatDropDate(x.created_at)+'</div></div>').join('');
 return '<div class="roul-page"><section class="hero roul-hero"><div class="cat">МЕТРО · КОЛЕСО ФОРТУНЫ</div><h1>Бесплатная <span class="gold">рулетка</span></h1><div class="muted">Настоящее круглое колесо, случайные призы и честные шансы.</div></section>'+
 '<section class="roul-box"><div class="roul-stage"><div class="roul-wheel" id="roulWheel" style="background:'+wheel.bg+';transform:rotate('+(rouletteLastAngle%360)+'deg)">'+wheel.labels+'</div><div class="roul-hub">ШРЕКСИЧ<small>METRO SPIN</small></div><div class="roul-pointer"></div></div>'+
 '<div class="roul-legend">'+wheel.legend+'</div>'+
 '<div class="roul-stats"><div class="roul-stat"><small>БЕСПЛАТНО</small><b>'+free+' / '+Number(spinState.max_free_spins||0)+'</b></div><div class="roul-stat"><small>БИЛЕТЫ</small><b>🎟 '+ticket+'</b></div><div class="roul-stat"><small>SHR</small><b>'+Number(spinState.shr||0)+'</b></div></div>'+
 '<button id="roulSpin" class="roul-go" '+(ready?'':'disabled')+'>'+(pending?'ЗАБЕРИТЕ ПРИЗ':free>0?'🎡 КРУТИТЬ БЕСПЛАТНО':ticket>0?'🎟 КРУТИТЬ ЗА БИЛЕТ':'ВРАЩЕНИЙ НЕТ')+'</button>'+
 '<div class="spin-lock-note" id="spinLockNote">Колесо вращается — дождитесь награды.</div><div class="roul-hint">'+note+'</div><div class="roul-result" id="roulResult"></div></section>'+
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
function bindRoulette(){
 const play=document.getElementById('roulSpin');if(play&&!play.disabled)play.addEventListener('click',rollRoulette);
 const cases=document.getElementById('roulCases');if(cases)cases.addEventListener('click',()=>go('spin'));
 const promo=document.getElementById('spinPromoBtn');if(promo)promo.addEventListener('click',applySpinPromo);
 const p=spinState?.pending_drop;
 if(p?.reward){
  const wheel=document.getElementById('roulWheel'),result=document.getElementById('roulResult');
  rouletteLastAngle=rouletteAngleFor(p.reward.tier);
  if(wheel)wheel.style.transform='rotate('+rouletteLastAngle+'deg)';
  if(result)revealReward(result,p);
 }
}
async function rollRoulette(){
 const btn=document.getElementById('roulSpin'),wheel=document.getElementById('roulWheel'),result=document.getElementById('roulResult');
 if(!btn||btn.disabled||!wheel||!result||spinNavigationLocked)return;
 btn.disabled=true;btn.textContent='ОПРЕДЕЛЯЕМ ПРИЗ…';
 setSpinNavigationLocked(true);
 let playing=false;
 try{
  const d=await api('/api/spin/free',{method:'POST'});
  if(!d?.reward?.tier)throw Error('Сервер не вернул приз');
  lastSpinReward=d.reward;
  const start=rouletteLastAngle%360,angle=rouletteAngleFor(d.reward.tier);
  const correction=((angle-start)%360+360)%360;
  const end=start+360*9+correction;
  const skip=localStorage.getItem('shx_skip_spin_animation')==='1';
  if(!skip){
   await ensureAudioReady();
   startSpinSound(8500);playing=true;
   if(wheel.animate){
    const anim=wheel.animate([{transform:'rotate('+start+'deg)'},{transform:'rotate('+end+'deg)'}],{duration:8500,easing:'cubic-bezier(.12,.66,.08,1)',fill:'forwards'});
    await anim.finished.catch(()=>{});
    wheel.style.transform='rotate('+angle+'deg)';
    anim.cancel();
   }else{
    wheel.style.transition='transform 8.5s cubic-bezier(.12,.66,.08,1)';
    void wheel.offsetWidth;
    wheel.style.transform='rotate('+end+'deg)';
    await sleep(8550);
    wheel.style.transition='';
    wheel.style.transform='rotate('+angle+'deg)';
   }
   stopSpinSound();playing=false;
  }else wheel.style.transform='rotate('+angle+'deg)';
  rouletteLastAngle=angle;
  sfxDrop(d.reward.tier);revealReward(result,d);
  btn.textContent='🎁 ПРИЗ ВЫПАЛ';
  loadWinsFeed();
  if(['RED','GOLD','LEGENDARY','MYTHIC'].includes(d.reward.tier))showDropFx(d.reward);
 }catch(e){
  if(!e.silent)alert(e.message);
  try{app.innerHTML=await rouletteHtml();bindRoulette();addHomeExit()}catch(_){}
 }finally{if(playing)stopSpinSound();setSpinNavigationLocked(false)}
}

async function spinHtml(){
 spinState=await api('/api/spin/state');
 const paidReady=spinState.paid_case_opening||null;
 if(paidReady){selectedCaseId=paidReady.case_id;localStorage.setItem('shx_selected_case',selectedCaseId)}
 const history=(spinState.history||[]).map(x=>'<div class="order"><div class="name">'+esc(x.reward_name)+'</div>'+rarityBar(x.reward_tier)+'<div class="mini" style="margin-top:9px">'+spinSourceLabel(x.source)+' • продажа '+x.points+' SHR</div><div class="history-time">📅 '+formatDropDate(x.created_at)+'</div></div>').join('');
 const claims=(spinState.upgrade_rewards||[]).map(x=>'<button class="claim" data-claim="'+x.points+'" '+(Number(spinState.shr)>=Number(x.points)?'':'disabled')+'>'+esc(x.name)+' • '+x.points+' SHR</button>').join('');
 const total=Number(spinState.remaining_spins||0),pending=spinState.pending_drop||null,cfg=selectedCase();
 const baseFree=!cfg||cfg.id==='FREE',adminFree=!!(cfg&&!baseFree&&cfg.is_free),donation=Number(cfg&&cfg.donation_tickets||0);
 const paidForSelected=!!(paidReady&&cfg&&paidReady.case_id===cfg.id);
 let buttonText='КРУТИТЬ',canOpen=!pending&&!!cfg;
 if(pending){buttonText='СНАЧАЛА РАЗБЕРИТЕ ДРОП';canOpen=false}
 else if(paidForSelected){buttonText='ОТКРЫТЬ ОПЛАЧЕННЫЙ КЕЙС'}
 else if(baseFree){buttonText=spinState.free_remaining>0?'БЕСПЛАТНЫЙ SPIN':spinState.bonus_tickets>0?'SPIN ЗА БОНУСНЫЙ БИЛЕТ':'ЛИМИТ ИСЧЕРПАН';canOpen=total>0}
 else if(adminFree){buttonText='ОТКРЫТЬ БЕСПЛАТНО'}
 else if(donation>0){buttonText='ОТКРЫТЬ ЗА DONATION TICKET'}
 else if(Number(cfg.stars_price||0)>0){buttonText='ОТКРЫТЬ ЗА '+Number(cfg.stars_price)+' ⭐'}
 else{buttonText='КЕЙС НЕДОСТУПЕН';canOpen=false}
 const skip=localStorage.getItem('shx_skip_spin_animation')==='1';
 let modeNote='';
 if(baseFree)modeNote=spinState.free_remaining>0?'Бесплатное вращение доступно':spinState.bonus_tickets>0?'Будет использован обычный бонусный билет':'Следующий бесплатный SPIN через '+formatReset(spinState.next_reset_seconds);
 else if(paidForSelected)modeNote='Оплата уже подтверждена. Нажмите кнопку, чтобы прокрутить кейс.';
 else if(adminFree)modeNote='Этот кейс отмечен бесплатным в админ-панели.';
 else if(donation>0)modeNote='Будет использован синий Donation Ticket. Stars не спишутся.';
 else modeNote='Стоимость открытия: '+Number(cfg&&cfg.stars_price||0)+' Telegram Stars.';
 return '<section class="hero"><div class="cat">МЕТРО-КЕЙСЫ</div><h1>Платные <span class="gold">кейсы</span></h1><div class="muted">Кейсы открываются за Telegram Stars или синие Donation Tickets. Бесплатная круглая рулетка находится в отдельном разделе.</div></section>'+
 spinCasePickerHtml()+
 '<div class="spin-stats"><div class="spin-stat donation-stat"><div class="mini blue-ticket">DONATION TICKETS</div><div class="price blue-ticket">🎫 '+Number(spinState.donation_tickets_total||0)+'</div></div><div class="spin-stat"><div class="mini">SHR</div><div class="price">'+spinState.shr+'</div></div></div>'+
 '<div class="spin-shell"><div class="reel-window" id="reelWindow"><div class="reel-track" id="reelTrack">'+selectedCaseIdleStrip()+'</div><div class="reel-marker"></div></div><div class="spin-result" id="spinResult"></div><button class="buy" id="spinBtn" style="margin-top:12px" '+(canOpen?'':'disabled')+'>'+buttonText+'</button><div class="spin-lock-note" id="spinLockNote">Дождитесь полной остановки рулетки</div>'+
 '<div class="spin-options-grid"><label class="spin-options"><input type="checkbox" id="skipSpinAnimation" '+(skip?'checked':'')+'><span>Пропустить анимацию</span></label></div>'+
 '<div class="muted" style="margin-top:10px">'+modeNote+'</div></div>'+
 '<div class="card"><div class="cat">ПРОМОКОД НА ПРОКРУТКИ</div><div class="muted">Промокод может выдать обычные SPIN-билеты или отдельные синие Donation Tickets для донат-кейсов.</div><div class="row"><input id="spinPromoCode" placeholder="Промокод"><button class="secondary" id="spinPromoBtn">Активировать</button></div><div class="mini" id="spinPromoInfo"></div></div>'+
 '<h3>SHR MARKET</h3><div class="card"><div class="muted">SHR можно получить за продажу выпавших предметов и обменять на гарантированные награды.</div>'+claims+'</div><h3>Последние 5 выпадений</h3>'+(history||'<div class="empty">История пока пустая.</div>')
}
function bindSpin(){
 bindSpinCasePicker();
 const b=document.getElementById('spinBtn');if(b&&!b.disabled)b.addEventListener('click',spinOnce);
 const p=document.getElementById('spinPromoBtn');if(p)p.addEventListener('click',applySpinPromo);
 const skip=document.getElementById('skipSpinAnimation');if(skip)skip.addEventListener('change',()=>localStorage.setItem('shx_skip_spin_animation',skip.checked?'1':'0'));
 if(spinState&&spinState.pending_drop)restorePendingDrop(spinState.pending_drop);
 document.querySelectorAll('[data-claim]').forEach(b=>b.addEventListener('click',()=>claimUpgrade(Number(b.dataset.claim))))
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
 setSpinNavigationLocked(false);
 try{
  const d=await api('/api/inventory/'+itemId+'/resolve',{method:'POST',body:JSON.stringify({action})});
  if(action==='save'){sfxSave();tab='inventory';await render()}
  else{
   sfxSell();
   alert('Продано. Баланс: '+d.shr+' SHR');
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
 if(!cfg||cfg.id==='FREE')return await api('/api/spin/free',{method:'POST'});
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


let farmCatalogExpanded=false;
let farmCatalogFilter='ALL';
let farmCachedData=null;
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
 const c={GRAY:'#baa981',CYAN:'#78cad1',BLUE:'#79a5e9',PURPLE:'#c88af4',PINK:'#e78cbf',RED:'#f28764',GOLD:'#f8cf5d'}[item.tier]||'#b7c6bb';
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
 '</svg><div class="farm-landscape-title"><span>Твоя деревенская ферма</span><span class="farm-stage-pill">ЭТАП '+d.stage+' / 5</span></div></div>';
}
function farmCatalogCards(d){
 const data=d||farmCachedData;
 if(!data)return '';
 const all=data.resources||[];
 const counts={};all.forEach(x=>{counts[x.tier]=(counts[x.tier]||0)+1});
 const pool=all.filter(x=>farmCatalogFilter==='ALL'||x.tier===farmCatalogFilter).slice().sort((a,b)=>FARM_TIER_ORDER_JS.indexOf(a.tier)-FARM_TIER_ORDER_JS.indexOf(b.tier)||Number(a.coins)-Number(b.coins));
 return pool.map(x=>{
   const odds=Number((data.tier_weights||{})[x.tier]||0)/(counts[x.tier]||1);
   const pct=odds===0?'0':odds<.01?odds.toFixed(4):odds<1?odds.toFixed(3):odds.toFixed(2);
   return '<div class="farm-catalog-card" data-tier="'+esc(x.tier)+'">'+farmItemSticker(x)+
   '<h4>'+esc(x.name)+'</h4><span class="farm-rarity-label '+esc(x.tier)+'">'+tierLabel(x.tier)+'</span>'+
   farmPrice(x.coins)+'<span class="farm-chance-text">Шанс: '+pct+'% на ур. '+data.level+'</span></div>';
 }).join('') || '<div class="empty">Нет предметов этой редкости</div>';
}

async function farmCatalogPage(){
 const d=await api('/api/farm');farmCachedData=d;
 const filters=[['ALL','Все'],['GRAY','Серые'],['CYAN','Голубые'],['BLUE','Синие'],['PURPLE','Фиолетовые'],['PINK','Розовые'],['RED','Красные'],['GOLD','Gold']].map(([t,name])=>'<button data-farm-filter="'+t+'" class="'+(farmCatalogFilter===t?'active':'')+'">'+name+'</button>').join('');
 return '<div class="shx-farm-catalog"><div class="shx-page-title"><button class="shx-back" id="farmCatalogBack">← Ферма</button><h1>Каталог предметов</h1></div>'+
 '<div class="shx-panel"><div class="muted">Все '+(d.resources||[]).length+' предметов • цены за ShrekCOIN • качество и реальные шансы на уровне '+d.level+'</div></div>'+
 '<div class="farm-filterbar">'+filters+'</div><div class="farm-catalog-grid" id="farmCatalogGrid">'+farmCatalogCards(d)+'</div>'+
 '<div class="shx-panel"><div class="muted">Вероятность отдельного предмета = вероятность его редкости ÷ количество предметов той же редкости. Торговый бонус учитывается в ценах.</div></div></div>';
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
 const items=(d.inventory||[]).slice().sort((a,b)=>FARM_TIER_ORDER_JS.indexOf(a.tier)-FARM_TIER_ORDER_JS.indexOf(b.tier)||Number(a.coins)-Number(b.coins)).map(x=>
  '<div class="farm-item"><div class="farm-item-head"><div class="farm-item-icon">'+farmItemSticker(x)+'</div><div><div class="farm-item-name">'+esc(x.name)+'</div><span class="farm-rarity-label '+esc(x.tier)+'">'+tierLabel(x.tier)+'</span><div class="farm-item-meta">В наличии: '+x.qty+' шт.</div></div></div><div class="farm-item-meta">За шт.: '+farmPrice(x.coins)+'<br>Итого: '+farmPrice(x.total_coins)+'</div><button class="secondary" data-farm-sell="'+esc(x.id)+'" data-farm-qty="'+x.qty+'">Продать '+x.qty+' шт.</button></div>'
 ).join('');
 const withdrawals=(d.withdrawals||[]).map(w=>'<div class="order"><div class="name">'+w.uc_amount+' UC • '+esc(w.status)+'</div><div class="mini">UID '+esc(w.pubg_uid)+' • '+formatDropDate(w.created_at)+'</div></div>').join('');
 const modules=(d.coin_upgrades||[]).map(m=>'<div class="farm-module"><div class="farm-module-header"><span class="farm-module-icon">'+esc(m.icon)+'</span>'+esc(m.name)+'</div><div class="farm-module-desc">'+esc(m.description)+'</div><div class="mini">Уровень '+m.level+' / '+m.max_level+'</div><div class="farm-module-progress"><span style="width:'+(100*m.level/m.max_level)+'%"></span></div><button class="secondary" data-farm-module="'+esc(m.id)+'" '+(m.level>=m.max_level||d.shrek_coins<m.cost?'disabled':'')+'>'+(m.level>=m.max_level?'МАКС. УРОВЕНЬ':'УЛУЧШИТЬ • '+m.cost+' монет')+'</button></div>').join('');
 const targets=(d.uc_targets||[]).map(t=>'<div class="farm-uc-target '+(t.need_more<=0?'farm-uc-complete':'')+'"><b>'+t.uc+' UC</b><span>Нужно '+t.required_credits+' UC Credits<br>'+(t.need_more<=0?'Доступно для заявки':('Осталось '+t.need_more+' • ≈'+t.days_at_daily_rate+' дн. при ежедневном бонусе'))+'</span></div>').join('');
 const filters=[['ALL','Все'],['GRAY','Серые'],['CYAN','Голубые'],['BLUE','Синие'],['PURPLE','Фиолетовые'],['PINK','Розовые'],['RED','Красные'],['GOLD','Золотые']].map(([t,name])=>'<button data-farm-filter="'+t+'" class="'+(farmCatalogFilter===t?'active':'')+'">'+name+'</button>').join('');
 const catalog=farmCatalogExpanded?'<div id="farmCatalogDetails"><div class="farm-filterbar">'+filters+'</div><div class="farm-catalog-grid" id="farmCatalogGrid">'+farmCatalogCards(d)+'</div><div class="farm-aux" style="margin-top:12px">Шанс для каждого отдельного предмета рассчитан по вероятности качества, разделённой на число предметов данного качества. Улучшения торговой лавки учтены в ценах.</div></div>':'';
 const next=d.available_cycles>0?'Добыча готова':(d.stored>=d.capacity?'Склад заполнен':'Следующая добыча через '+formatReset(d.next_cycle_seconds));
 const progress=d.available_cycles>0?100:(d.stored>=d.capacity?100:Math.max(0,100*(1-d.next_cycle_seconds/Math.max(1,d.interval_seconds))));
 return '<div class="farm-ui">'+
 '<div class="farm-lead"><div><span class="farm-eyebrow">SHREKSICH · METRO FARM</span><h1>Ферма ресурсов</h1><div class="muted">Твоя уютная ферма, добыча и торговля</div></div><div class="farm-lead-level">УРОВЕНЬ<br>'+d.level+' / '+d.max_level+'</div></div>'+
 farmScene(d)+
 '<div class="farm-overview"><div class="farm-wallet shr"><div class="farm-wallet-label">SHR</div><div class="farm-wallet-value"><span>'+d.shr+'</span></div></div>'+
 '<div class="farm-wallet"><div class="farm-wallet-label">SHREKCOIN</div><div class="farm-wallet-value">'+farmCoinIcon()+'<span>'+d.shrek_coins+'</span></div></div>'+
 '<div class="farm-wallet uc"><div class="farm-wallet-label">UC CREDITS</div><div class="farm-wallet-value">'+farmUcIcon()+'<span>'+d.uc_available+'</span></div></div></div>'+
 '<div class="farm-status"><div><span>Скорость добычи</span><b>1 предмет / '+Math.ceil(d.interval_seconds/60)+' мин</b></div><div><span>Склад</span><b>'+d.stored+' / '+d.capacity+' предметов</b></div><div><span>'+next+'</span><b>'+(d.available_cycles>0?d.available_cycles+' шт. можно забрать':'Ферма работает')+'</b></div><div><span>Редкость улучшается</span><b>с уровнем фермы</b></div><div class="farm-status-bar"><span style="width:'+progress.toFixed(1)+'%"></span></div></div>'+
 '<div class="farm-primary-actions"><button class="farm-primary" id="farmCollect" '+(d.available_cycles<=0?'disabled':'')+'>🧺 СОБРАТЬ • '+d.available_cycles+'</button><button class="secondary" id="farmUpgrade" '+(d.level>=d.max_level||d.shr<d.upgrade_cost?'disabled':'')+'>'+(d.level>=d.max_level?'МАКС. УРОВЕНЬ':'УЛУЧШИТЬ • '+d.upgrade_cost+' SHR')+'</button></div>'+
 '<div class="farm-section wood"><div class="farm-section-head"><h3>🪵 Развитие фермы</h3></div><div class="farm-aux">Улучшайте инструменты, амбар и торговую лавку за заработанные ShrekCOINS. Улучшения остаются навсегда.</div><div class="farm-modules">'+modules+'</div></div>'+
 '<div class="farm-section"><div class="farm-section-head"><h3>📚 Справочник ресурсов</h3><button class="farm-catalog-btn" id="farmCatalogToggle">'+(farmCatalogExpanded?'Скрыть':'Все предметы →')+'</button></div><div class="farm-aux">Все '+(d.resources||[]).length+' ресурсов, качество, цены продажи и реальные шансы для твоего уровня фермы.</div><div class="farm-tier-chances">'+chances+'</div>'+catalog+'</div>'+
 '<div class="farm-section"><div class="farm-section-head"><h3>📦 Склад добычи</h3><button class="secondary" id="farmSellAll" '+((d.inventory||[]).length?'':'disabled')+'>Продать всё</button></div><div class="farm-inventory">'+(items||'<div class="empty">Склад пуст. Дождись готовой добычи и нажми «Собрать».</div>')+'</div></div>'+
 '<div class="farm-activity"><div class="farm-section-head"><h3>🌱 Награды за активность</h3><span class="farm-rarity-label">Серия: '+d.activity_streak+' дн.</span></div><div class="farm-aux">Собери хотя бы один ресурс, затем забери +'+d.daily_uc_credits+' UC Credits. Награда доступна раз в 20 часов. Каждый 7-й день серии — билет CASE29, каждый 30-й — билет CASE79.</div><button class="buy" id="farmActivity" style="margin-top:12px;width:100%" '+(d.activity_ready?'':'disabled')+'>'+(d.activity_ready?'ЗАБРАТЬ ЕЖЕДНЕВНУЮ НАГРАДУ':'СОБЕРИ ДОБЫЧУ ИЛИ ДОЖДИСЬ НАГРАДЫ')+'</button></div>'+
 '<div class="farm-withdraw"><div class="farm-section-head"><h3>'+farmUcIcon()+' Вывод UC</h3></div><div class="farm-aux">UC Credits — бонусы за активность, не ShrekCOINS и не Telegram Stars. Один UC Credit учитывается как один UC для заявки. Для получения награды нужен указанный баланс и PUBG UID. Выдачу подтверждает администратор.</div><div class="farm-uc-targets">'+targets+'</div><div class="farm-aux">Текущий баланс: '+d.uc_available+' UC Credits'+(d.uc_reserved>0?' • в ожидании: '+d.uc_reserved:'')+'. Расчёт дней предполагает ежедневное получение '+d.daily_uc_credits+' Credits без пропусков и дополнительных бонусов.</div><div class="row" style="margin-top:11px"><input id="farmPubgUid" placeholder="PUBG UID" inputmode="numeric"><select id="farmUcAmount"><option value="120">120 UC</option><option value="325">325 UC</option><option value="660">660 UC</option><option value="1800">1800 UC</option></select></div><button class="buy" id="farmWithdraw" style="width:100%;margin-top:10px" '+(Number(d.uc_available)<120?'disabled':'')+'>ОФОРМИТЬ ЗАЯВКУ НА UC</button></div>'+
 '<div class="farm-section"><h3>Последние заявки</h3>'+(withdrawals||'<div class="farm-aux" style="margin-top:8px">Заявок на вывод UC пока нет.</div>')+'</div>'+
 '</div>';
}
const FARM_TIER_ORDER_JS=['GRAY','CYAN','BLUE','PURPLE','PINK','RED','GOLD'];
function bindFarm(){
 const cat=document.getElementById('farmCatalogToggle');
 if(cat)cat.addEventListener('click',()=>go('farm-catalog'));
 document.querySelectorAll('[data-farm-filter]').forEach(b=>b.addEventListener('click',()=>{
  farmCatalogFilter=b.dataset.farmFilter;
  document.querySelectorAll('[data-farm-filter]').forEach(k=>k.classList.toggle('active',k.dataset.farmFilter===farmCatalogFilter));
  const grid=document.getElementById('farmCatalogGrid');if(grid)grid.innerHTML=farmCatalogCards(farmCachedData);
 }));
 const ucSelect=document.getElementById('farmUcAmount');
 if(ucSelect)ucSelect.addEventListener('change',()=>{
  const bt=document.getElementById('farmWithdraw');
  if(bt&&farmCachedData)bt.disabled=Number(ucSelect.value)>Number(farmCachedData.uc_available||0);
 });
 document.querySelectorAll('[data-farm-module]').forEach(b=>b.addEventListener('click',async()=>{b.disabled=true;try{const d=await api('/api/farm/coin-upgrade',{method:'POST',body:JSON.stringify({module:b.dataset.farmModule})});alert('Модуль улучшен до '+d.level+' уровня • -'+d.spent+' ShrekCOINS');app.innerHTML=await farmHtml();bindFarm();addHomeExit()}catch(e){alert(e.message);b.disabled=false}}));
 const collect=document.getElementById('farmCollect');if(collect&&!collect.disabled)collect.addEventListener('click',async()=>{collect.disabled=true;try{const d=await api('/api/farm/collect',{method:'POST'});alert('Ферма добыла '+d.count+' предмет(ов)');app.innerHTML=await farmHtml();bindFarm();addHomeExit()}catch(e){alert(e.message);collect.disabled=false}});
 const up=document.getElementById('farmUpgrade');if(up&&!up.disabled)up.addEventListener('click',async()=>{up.disabled=true;try{const d=await api('/api/farm/upgrade',{method:'POST'});alert('Ферма улучшена до '+d.level+' уровня');app.innerHTML=await farmHtml();bindFarm();addHomeExit()}catch(e){alert(e.message);up.disabled=false}});
 document.querySelectorAll('[data-farm-sell]').forEach(b=>b.addEventListener('click',async()=>{b.disabled=true;try{const d=await api('/api/farm/sell',{method:'POST',body:JSON.stringify({resource_id:b.dataset.farmSell,qty:Number(b.dataset.farmQty||1)})});sfxSell();alert('+'+d.coins_added+' ShrekCOINS');app.innerHTML=await farmHtml();bindFarm();addHomeExit()}catch(e){alert(e.message);b.disabled=false}}));
 const all=document.getElementById('farmSellAll');if(all&&!all.disabled)all.addEventListener('click',async()=>{if(!confirm('Продать весь склад за ShrekCOINS?'))return;all.disabled=true;try{const d=await api('/api/farm/sell-all',{method:'POST'});sfxSell();alert('Продано '+d.sold_qty+' предметов • +'+d.coins_added+' ShrekCOINS');app.innerHTML=await farmHtml();bindFarm();addHomeExit()}catch(e){alert(e.message);all.disabled=false}});
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
 const items=(d.items||[]).map(x=>'<div class="order"><div class="name">'+esc(x.reward_name)+'</div>'+rarityBar(x.reward_tier)+'<div class="mini" style="margin-top:9px">'+spinSourceLabel(x.source)+' • продажа '+x.points+' SHR</div><div class="history-time">📅 '+formatDropDate(x.created_at)+'</div></div>').join('');
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
   '<div class="case-tier-row">'+tiers.map(t=>'<button type="button" class="case-tier-btn" data-case-tier="'+esc(c.id)+'" data-tier="'+esc(t.tier)+'"><div class="loot-cube '+cubeClass(t.tier)+'"><span>?</span></div><div class="rarity-card-title '+tierClass(t.tier)+'">'+caseTierLabel(c.id,t.tier)+'</div><div class="rarity-card-chance">'+Number(t.chance||0)+'%</div></button>').join('')+'</div>'+
   '<div class="case-guide-note">Нажмите на качество, чтобы посмотреть только предметы этого кейса. Цены идут по возрастанию.</div></div>'
 }).join('');
 return '<section class="hero"><div class="cat">КЕЙСЫ И ПРЕДМЕТЫ</div><h1>Каталог кейсов</h1><div class="muted">У каждого кейса свои качества, проценты и содержимое. Всё редактируется из админ-панели.</div></section>'+
 '<div class="case-guide">'+html+'</div><div class="rarity-modal hide" id="caseTierModal"><div class="rarity-sheet" id="caseTierSheet"></div></div>'
}
function openCaseTier(caseId,tier){
 const cfg=(spinState.case_catalog||[]).find(x=>x.id===caseId);
 const tierCfg=cfg&&(cfg.tiers||[]).find(x=>x.tier===tier);
 const modal=document.getElementById('caseTierModal'),sheet=document.getElementById('caseTierSheet');
 if(!cfg||!tierCfg||!modal||!sheet)return;
 const allowed=new Set(cfg.contents||[]);
 const items=(spinState.rewards||[]).filter(x=>x.tier===tier&&allowed.has(x.name)).slice().sort((a,b)=>Number(a.value_stars||0)-Number(b.value_stars||0));
 sheet.innerHTML='<div class="rarity-sheet-head"><div class="loot-cube '+cubeClass(tier)+'"><span>?</span></div><div class="rarity-sheet-title"><h3 class="'+tierClass(tier)+'">'+caseTierLabel(caseId,tier)+'</h3><div class="muted">'+esc(cfg.name)+' • шанс '+Number(tierCfg.chance||0)+'% • '+items.length+' предметов</div></div><button type="button" class="rarity-close" id="caseTierClose">Закрыть</button></div>'+
 items.map(x=>'<div class="rarity-item-row"><div class="rarity-item-name">'+esc(x.name)+'</div><div class="rarity-item-price">🪙 '+Number(x.value_stars||0).toLocaleString('ru-RU')+' / '+Number(x.value_stars||0).toLocaleString('ru-RU')+' SHR</div></div>').join('');
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
 return '<section class="hero"><div class="cat">НАСТРОЙКИ</div><h1>Шрексич</h1><div class="muted">Управляйте анимацией, звуками и быстрыми разделами.</div></section>'+
 '<div class="settings-grid"><div class="setting-card"><h3>Анимация SPIN</h3><div class="muted">Обычный прокрут длится 30 секунд: быстрый старт и плавное замедление до полной остановки.</div><label class="switch-row"><span>Пропускать анимацию</span><input type="checkbox" id="settingsSkip" '+(skip?'checked':'')+'></label></div>'+
 '<div class="setting-card"><h3>Звуки эффектов</h3><div class="muted">Прокрут, остановка, выпадение, продажа и сохранение. SFX генерируются внутри приложения.</div><label class="switch-row"><span>Звуки включены</span><input type="checkbox" id="settingsSound" '+(sound?'checked':'')+'></label></div></div>'+
 '<div class="sticker-grid">'+sticker('Инвентарь','Предметы и SHR','inventory','st-cyan','data-go="inventory"')+sticker('Кубики и предметы','Кейсы, качества и цены','cases','st-gold','data-go="case-catalog"')+sticker('История дропов','Фильтр по времени и редкости','history','st-purple','data-go="drop-history"')+sticker('Поддержка','Обращения и помощь','support','st-blue','data-go="support"')+'</div>'
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
  api('/api/admin/cases'),api('/api/admin/farm-withdrawals')
 ]);
 adminData={stats:r[0],orders:r[1],users:r[2],products:r[3],promos:r[4],tickets:r[5],spins:r[6],upgrades:r[7],referrals:r[8],cases:r[9],farmWithdrawals:r[10]}
}
function adminNav(){
 const items=[['overview','Обзор'],['orders','Заказы'],['users','Игроки'],['products','Товары'],['cases','Кейсы'],['promos','Промо'],['rewards','Награды'],['withdrawals','UC выводы'],['support','Поддержка'],['bot','Бот']];
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
 const cases=(adminData.cases&&adminData.cases.cases)||[];
 return '<h2>Игроки и бонусы</h2><div class="card"><input id="userSearch" placeholder="Поиск по жетону, нику или имени"><div class="adminline"><input id="grantToken" placeholder="Жетон SHX-..."><input id="grantTickets" type="number" min="0" value="0" placeholder="Обычные билеты"><input id="grantDonation" type="number" min="0" value="0" placeholder="Синие Donation Tickets"><input id="grantPts" type="number" min="0" value="0" placeholder="SHR"></div><select id="grantDonationCase"><option value="*">Donation Ticket: любой донат-кейс</option>'+cases.filter(c=>c.id!=='FREE').map(c=>'<option value="'+esc(c.id)+'">Только '+esc(c.name)+'</option>').join('')+'</select><button class="buy" id="grantBtn">Выдать</button></div>'+
 adminData.users.map(u=>'<div class="admin-card user-row" data-search="'+esc(((u.token||'')+' '+(u.username||'')+' '+(u.first_name||'')).toLowerCase())+'"><div class="name">'+esc(u.first_name||u.username||'Игрок')+' '+(u.username?'@'+esc(u.username):'')+'</div><div class="token-code">'+esc(u.token||'Без жетона')+'</div><div class="mini">заказов '+u.orders_count+' • рефералов '+u.referrals_count+' • 🎟 '+u.tickets+' • <span class="blue-ticket">🎟️ Donation '+Number(u.donation_tickets||0)+'</span> • SHR '+u.upgrade_points+'</div><button class="secondary" data-message-user="'+esc(u.token||'')+'" style="margin-top:8px">Написать по жетону</button></div>').join('')
}
function adminProducts(){
 return '<h2>Товары</h2><div class="card"><input id="newPName" placeholder="Название"><input id="newPCat" placeholder="Категория"><textarea id="newPDesc" placeholder="Описание"></textarea><div class="row"><input id="newPStars" type="number" placeholder="Цена ⭐"><input id="newPSort" type="number" value="0" placeholder="Сортировка"></div><button class="buy" id="newPBtn">Добавить товар</button></div>'+
 adminData.products.map(p=>'<div class="admin-card" data-product-card="'+p.id+'"><input data-p="name" value="'+esc(p.name)+'"><input data-p="category" value="'+esc(p.category)+'"><textarea data-p="description">'+esc(p.description)+'</textarea><div class="row"><input data-p="stars_price" type="number" value="'+p.stars_price+'"><input data-p="sort_order" type="number" value="'+p.sort_order+'"></div><label class="mini"><input data-p="active" type="checkbox" '+(p.active?'checked':'')+' style="width:auto"> Активен</label><button class="secondary" data-product-save="'+p.id+'" style="width:100%;margin-top:8px">Сохранить</button></div>').join('')
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
function adminRewards(){
 const spin=adminData.spins.slice(0,80).map(x=>'<div class="order"><span class="tier '+tierClass(x.reward_tier)+'">'+x.reward_tier+'</span><div class="name">'+esc(x.reward_name)+'</div><div class="mini">'+esc(x.user_token||'Без жетона')+' • '+esc(x.created_at)+'</div></div>').join('');
 const ups=adminData.upgrades.slice(0,80).map(x=>'<div class="order"><div class="name">'+esc(x.reward_name)+'</div><div class="mini">'+esc(x.user_token||'Без жетона')+' • '+x.points_spent+' pts • '+esc(x.created_at)+'</div></div>').join('');
 const refs=adminData.referrals.slice(0,80).map(x=>'<div class="order"><div class="name">'+esc(x.referrer_name||x.referrer_username||x.referrer_token||'Игрок')+' → '+esc(x.referred_name||x.referred_username||x.referred_token||'Игрок')+'</div><div class="mini">'+esc(x.referrer_token||'—')+' → '+esc(x.referred_token||'—')+' • '+(x.rewarded?'✅ Награда выдана':'⏳ Ждём первую оплату')+' • '+esc(x.created_at)+'</div></div>').join('');
 return '<h2>Выигрыши</h2>'+(spin||'<div class="empty">Нет</div>')+'<h2>Upgrade Lab</h2>'+(ups||'<div class="empty">Нет</div>')+'<h2>Рефералы</h2>'+(refs||'<div class="empty">Нет</div>')
}
function adminWithdrawals(){
 const rows=adminData.farmWithdrawals||[];
 return '<h2>UC выводы</h2><div class="card"><div class="muted">После фактической выдачи UC в PUBG нажмите «Выполнен». Только тогда UC Credits окончательно списываются у игрока.</div></div>'+
 (rows.map(w=>'<div class="admin-card"><div class="cat">#'+w.id+' • '+esc(w.status)+'</div><div class="name">'+w.uc_amount+' UC • '+esc(w.token||'Без жетона')+'</div><div class="mini">'+esc(w.first_name||w.username||'Игрок')+(w.username?' @'+esc(w.username):'')+' • PUBG UID '+esc(w.pubg_uid)+' • '+esc(w.created_at)+'</div>'+(w.status==='Ожидает'?'<div class="row" style="margin-top:8px"><button class="buy" data-farm-wd-ok="'+w.id+'">Выполнен</button><button class="danger" data-farm-wd-no="'+w.id+'">Отклонить</button></div>':'')+'</div>').join('')||'<div class="empty">Заявок пока нет.</div>')
}
function adminSupport(){
 return '<h2>Обращения</h2>'+adminData.tickets.map(t=>'<div class="admin-card"><div class="cat">#'+t.id+' • '+esc(t.category)+' • '+esc(t.status)+'</div><div style="margin:8px 0">'+esc(t.message)+'</div><div class="token-code">'+esc(t.user_token||'Без жетона')+'</div><textarea id="tr'+t.id+'" placeholder="Ответ пользователю"></textarea><div class="row"><button class="blue" data-ticket-reply="'+t.id+'">Ответить</button><button class="secondary" data-ticket-close="'+t.id+'">Закрыть</button></div></div>').join('')
}
function adminBot(){
 return '<h2>Управление ботом</h2><div class="card"><h3>Сообщение пользователю</h3><input id="botUserToken" placeholder="Жетон SHX-..."><textarea id="botUserMsg" placeholder="Сообщение"></textarea><button class="buy" id="botSendBtn">Отправить</button></div><div class="card" style="margin-top:12px"><h3>Рассылка</h3><textarea id="broadcastMsg" placeholder="Сообщение всем зарегистрированным пользователям"></textarea><button class="danger" id="broadcastBtn">Запустить рассылку</button></div><div class="card" style="margin-top:12px"><div class="name">Команды бота</div><div class="muted">/start • /shop • /faq • /ref • /token • /help<br>Каждый пользователь имеет постоянный жетон SHX-.... Вся работа с пользователями идёт по жетонам.</div></div>'
}
function adminSectionHtml(){if(adminSection==='orders')return adminOrders();if(adminSection==='users')return adminUsers();if(adminSection==='products')return adminProducts();if(adminSection==='cases')return adminCases();if(adminSection==='promos')return adminPromos();if(adminSection==='rewards')return adminRewards();if(adminSection==='withdrawals')return adminWithdrawals();if(adminSection==='support')return adminSupport();if(adminSection==='bot')return adminBot();return adminOverview()}
async function adminHtml(){if(!adminData)await loadAdminData();return adminNav()+adminSectionHtml()}
async function refreshAdmin(){adminData=null;app.innerHTML='<div class="empty">Обновляем…</div>';app.innerHTML=await adminHtml();bindAdmin()}
function bindAdmin(){
 document.querySelectorAll('[data-admin]').forEach(b=>b.addEventListener('click',()=>{adminSection=b.dataset.admin;app.innerHTML=adminNav()+adminSectionHtml();bindAdmin()}));
 document.querySelectorAll('[data-order-save]').forEach(b=>b.addEventListener('click',async()=>{const id=b.dataset.orderSave;try{await api('/api/admin/orders/'+id,{method:'PATCH',body:JSON.stringify({status:document.getElementById('os'+id).value})});alert('Статус сохранён')}catch(e){alert(e.message)}}));
 const gb=document.getElementById('grantBtn');if(gb)gb.addEventListener('click',async()=>{try{await api('/api/admin/rewards/grant',{method:'POST',body:JSON.stringify({token:document.getElementById('grantToken').value,tickets:Number(document.getElementById('grantTickets').value||0),donation_tickets:Number(document.getElementById('grantDonation').value||0),donation_case_id:document.getElementById('grantDonationCase').value,upgrade_points:Number(document.getElementById('grantPts').value||0)})});alert('Награда выдана');refreshAdmin()}catch(e){alert(e.message)}});
 document.querySelectorAll('[data-message-user]').forEach(b=>b.addEventListener('click',()=>{adminSection='bot';app.innerHTML=adminNav()+adminBot();document.getElementById('botUserToken').value=b.dataset.messageUser;bindAdmin()}));
 const np=document.getElementById('newPBtn');if(np)np.addEventListener('click',async()=>{try{await api('/api/admin/products',{method:'POST',body:JSON.stringify({name:document.getElementById('newPName').value,category:document.getElementById('newPCat').value,description:document.getElementById('newPDesc').value,stars_price:Number(document.getElementById('newPStars').value),sort_order:Number(document.getElementById('newPSort').value||0),active:true})});alert('Товар добавлен');refreshAdmin()}catch(e){alert(e.message)}});
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
 const us=document.getElementById('userSearch');if(us)us.addEventListener('input',()=>{const q=us.value.trim().toLowerCase();document.querySelectorAll('.user-row').forEach(r=>r.style.display=!q||String(r.dataset.search||'').includes(q)?'':'none')});
 document.querySelectorAll('[data-farm-wd-ok]').forEach(b=>b.addEventListener('click',async()=>{if(!confirm('Подтвердить, что UC уже выданы игроку?'))return;try{await api('/api/admin/farm-withdrawals/'+b.dataset.farmWdOk,{method:'PATCH',body:JSON.stringify({status:'Выполнен'})});refreshAdmin()}catch(e){alert(e.message)}}));
 document.querySelectorAll('[data-farm-wd-no]').forEach(b=>b.addEventListener('click',async()=>{try{await api('/api/admin/farm-withdrawals/'+b.dataset.farmWdNo,{method:'PATCH',body:JSON.stringify({status:'Отклонён'})});refreshAdmin()}catch(e){alert(e.message)}}));
 const br=document.getElementById('broadcastBtn');if(br)br.addEventListener('click',async()=>{if(!confirm('Отправить всем пользователям?'))return;try{await api('/api/admin/broadcast',{method:'POST',body:JSON.stringify({message:document.getElementById('broadcastMsg').value})});alert('Рассылка запущена')}catch(e){alert(e.message)}})
}

async function render(){
 updateNav();app.innerHTML='<div class="empty">Загрузка…</div>';
 try{
  if(ADMIN){app.innerHTML=await adminHtml();bindAdmin();return}
  if(tab==='home'){try{homeFarmData=await api('/api/farm')}catch(_){} app.innerHTML=home();bindHome()}
  else if(tab==='catalog'){app.innerHTML='<h2>Каталог</h2>'+cards(products);bindProductButtons()}
  else if(tab==='spin'){app.innerHTML=await spinHtml();bindSpin()}
  else if(tab==='roulette'){app.innerHTML=await rouletteHtml();bindRoulette()}
  else if(tab==='orders'){app.innerHTML=await ordersHtml()}
  else if(tab==='inventory'){app.innerHTML=await inventoryHtml();bindInventory()}
  else if(tab==='farm'){app.innerHTML=await farmHtml();bindFarm()}
  else if(tab==='farm-catalog'){app.innerHTML=await farmCatalogPage();bindFarmCatalogPage()}
  else if(tab==='profile'){try{homeFarmData=await api('/api/farm')}catch(_){} app.innerHTML=profileHtml();bindProfile()}
  else if(tab==='referral'){app.innerHTML=await referralHtml();bindReferral()}
  else if(tab==='support'){app.innerHTML=supportHtml();bindSupport()}
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
