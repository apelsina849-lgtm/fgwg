"""Seller payout preview for Shreksich marketplace. No database mutations."""
from fastapi import HTTPException
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
