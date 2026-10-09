"""Seller commission calculator: read-only, no financial transfers."""
from fastapi import HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from app import app

class SellerQuote(BaseModel):
    price_stars: int = Field(ge=1, le=1000000)
    quantity: int = Field(default=1, ge=1, le=1000)

@app.post("/api/seller/commission-preview")
async def seller_commission_preview(quote: SellerQuote):
    gross = quote.price_stars * quote.quantity
    seller = gross * 70 // 100
    reserve = gross * 10 // 100
    shop = gross - seller - reserve
    return {"ok": True, "currency": "XTR", "gross_stars": gross,
            "seller_stars": seller, "shop_stars": shop,
            "reserve_stars": reserve,
            "split_percent": {"seller": 70, "shop": 20, "reserve": 10},
            "note": "Предварительный расчёт, не выплата и не подтверждение заказа."}

@app.get("/seller/calculator", response_class=HTMLResponse)
async def seller_calculator():
    return HTMLResponse('''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Шрексич — комиссия продавца</title><style>
:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:radial-gradient(ellipse at top,#1d3952,#08121f 65%);color:#e9f5ff;font:16px system-ui,sans-serif;min-height:100vh;padding:24px 14px}.wrap{max-width:520px;margin:auto}.eyebrow{color:#65d9f4;font-size:12px;font-weight:800;letter-spacing:.15em}h1{font-size:30px;margin:12px 0 8px}p{color:#9fb3c7;line-height:1.5}.card{background:#132439;border:1px solid #35536d;border-radius:20px;padding:20px;margin-top:22px;box-shadow:0 14px 45px #0005}label{display:block;font-size:13px;color:#b3c9dc;margin:14px 0 7px}input{width:100%;padding:14px;border-radius:12px;border:1px solid #41617a;background:#091726;color:white;font-size:18px}button{border:0;background:#50c6e6;color:#082030;font-weight:800;border-radius:12px;padding:14px;width:100%;font-size:16px;margin-top:18px}.line{display:flex;justify-content:space-between;gap:12px;padding:14px 0;border-bottom:1px solid #2a4057}.line:last-child{border:0}.line strong{white-space:nowrap}.seller{color:#8aefb0}.muted{font-size:13px;color:#8fa6b9}.error{color:#ff9b9b}a{color:#8adbf7}</style></head><body><main class="wrap"><div class="eyebrow">ШРЕКСИЧ · МАРКЕТПЛЕЙС</div><h1>Калькулятор продавца</h1><p>Узнай, сколько получит продавец и сколько останется магазину и резерву с продажи за Telegram Stars.</p><section class="card"><label for="price">Цена за один предмет · ⭐ Stars</label><input id="price" type="number" inputmode="numeric" min="1" max="1000000" value="100"><label for="qty">Количество предметов</label><input id="qty" type="number" inputmode="numeric" min="1" max="1000" value="1"><button id="calculate">Рассчитать</button><p id="error" class="error" role="alert"></p></section><section class="card" aria-live="polite"><div class="line"><span>Всего оплачено</span><strong id="gross">100 ⭐</strong></div><div class="line"><span>Продавец · 70%</span><strong class="seller" id="seller">70 ⭐</strong></div><div class="line"><span>Магазин · 20%</span><strong id="shop">20 ⭐</strong></div><div class="line"><span>Резерв · 10%</span><strong id="reserve">10 ⭐</strong></div><p class="muted">Расчёт справочный. Это не перевод Stars, не подтверждение продажи и не гарантия выплаты. При округлении остаток учитывается в доле магазина.</p></section></main><script>
const $=id=>document.getElementById(id);async function calculate(){const price=Number($('price').value),qty=Number($('qty').value);$('error').textContent='';if(!Number.isSafeInteger(price)||price<1||price>1000000||!Number.isSafeInteger(qty)||qty<1||qty>1000){$('error').textContent='Укажите корректные цену и количество';return}try{const r=await fetch('/api/seller/commission-preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({price_stars:price,quantity:qty})});if(!r.ok)throw Error('Ошибка расчёта');const d=await r.json();for(const k of ['gross','seller','shop','reserve'])$(k).textContent=Number(d[k+'_stars']).toLocaleString('ru-RU')+' ⭐'}catch(e){$('error').textContent=e.message}}$('calculate').addEventListener('click',calculate);for(const id of ['price','qty'])$(id).addEventListener('input',calculate);calculate();</script></body></html>''')
