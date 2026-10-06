import asyncio
import hashlib
import hmac
import json
import os
import time
from urllib.parse import urlencode

import httpx
import app


def make_init_data(user_id: int) -> str:
    user = json.dumps(
        {"id": user_id, "first_name": "Smoke", "username": "shreksich_smoke"},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    pairs = {"auth_date": str(int(time.time())), "user": user}
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", os.environ["BOT_TOKEN"].encode(), hashlib.sha256).digest()
    digest = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    return urlencode({**pairs, "hash": digest})


async def expect(resp: httpx.Response, status: int = 200):
    if resp.status_code != status:
        raise AssertionError(f"{resp.request.method} {resp.request.url.path}: {resp.status_code} {resp.text}")
    return resp.json()


async def main():
    try:
        os.remove(app.DB_PATH)
    except FileNotFoundError:
        pass

    await app.init_db()
    headers = {"X-Telegram-Init-Data": make_init_data(app.OWNER_ID)}
    transport = httpx.ASGITransport(app=app.app)

    async with httpx.AsyncClient(transport=transport, base_url="http://smoke") as client:
        state = await expect(await client.get("/api/spin/state", headers=headers))
        assert len(state["case_catalog"]) >= 5
        assert any(c["id"] == "CASE499" for c in state["case_catalog"])

        admin = await expect(await client.get("/api/admin/cases", headers=headers))
        case29 = next(c for c in admin["cases"] if c["id"] == "CASE29")
        original = {
            "name": case29["name"],
            "description": case29["description"],
            "icon": case29["icon"],
            "stars_price": case29["stars_price"],
            "is_free": case29["is_free"],
            "active": case29["active"],
            "sort_order": case29["sort_order"],
            "tiers": {t["tier"]: t["chance"] for t in case29["tiers"]},
            "contents": case29["contents"],
        }

        test_case = dict(original)
        test_case["stars_price"] = 31
        test_case["is_free"] = True
        saved = await expect(await client.patch("/api/admin/cases/CASE29", headers=headers, json=test_case))
        assert saved["case"]["stars_price"] == 31
        assert saved["case"]["is_free"] is True

        opened = await expect(await client.post("/api/spin/case/start", headers=headers, json={"case_id": "CASE29"}))
        assert opened["mode"] == "free"
        assert opened["reward"]["name"]
        await expect(await client.post(
            f"/api/inventory/{opened['inventory_item_id']}/resolve",
            headers=headers,
            json={"action": "sell"},
        ))

        restored = await expect(await client.patch("/api/admin/cases/CASE29", headers=headers, json=original))
        assert restored["case"]["stars_price"] == original["stars_price"]
        assert restored["case"]["is_free"] == original["is_free"]

        promo_code = "SMOKE_DONATION_CASE29"
        created = await expect(await client.post("/api/admin/promos", headers=headers, json={
            "code": promo_code,
            "promo_type": "donation",
            "discount_percent": 0,
            "spin_tickets": 0,
            "donation_tickets": 1,
            "case_id": "CASE29",
            "max_uses": 1,
            "expires_at": "",
        }))
        promo_id = created["id"]

        activated = await expect(await client.post("/api/spin/promo", headers=headers, json={"code": promo_code}))
        assert activated["promo_type"] == "donation"
        assert activated["donation_tickets_added"] == 1

        ticket_open = await expect(await client.post("/api/spin/case/start", headers=headers, json={"case_id": "CASE29"}))
        assert ticket_open["mode"] == "ticket"
        assert ticket_open["reward"]["name"]
        await expect(await client.post(
            f"/api/inventory/{ticket_open['inventory_item_id']}/resolve",
            headers=headers,
            json={"action": "sell"},
        ))

        await expect(await client.delete(f"/api/admin/promos/{promo_id}", headers=headers))

        final_state = await expect(await client.get("/api/spin/state", headers=headers))
        assert final_state["donation_tickets_total"] == 0

    print("SHREKSICH_SMOKE_OK: cases/admin/free/donation-ticket API passed")


if __name__ == "__main__":
    asyncio.run(main())
