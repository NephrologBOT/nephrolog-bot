import os
import uuid
import hmac
import hashlib
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.types import Update
from aiogram.dispatcher.webhook import get_new_configured_app
import logging

load_dotenv()

API_TOKEN = os.getenv("API_TOKEN")
WEBHOOK_PATH = "/webhook"
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")
WEBHOOK_URL = RENDER_EXTERNAL_URL + WEBHOOK_PATH

MERCHANT_ACCOUNT = os.getenv("MERCHANT_ACCOUNT")
MERCHANT_SECRET = os.getenv("MERCHANT_SECRET")
INVITE_LINK = os.getenv("INVITE_LINK")

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

# FastAPI app configured for aiogram webhook
app = get_new_configured_app(dispatcher=dp, bot=bot)

paid_refs = set()

def generate_signature(data: dict, secret: str) -> str:
    keys = sorted(data.keys())
    raw = ';'.join([str(data[k]) for k in keys])
    return hmac.new(secret.encode(), raw.encode(), hashlib.md5).hexdigest()

@app.on_event("startup")
async def on_startup():
    await bot.set_webhook(WEBHOOK_URL)

@app.on_event("shutdown")
async def on_shutdown():
    await bot.delete_webhook()

@app.get("/pay", response_class=HTMLResponse)
async def pay_page(uid: int, ref: str, amount: int):
    payload = {
        "account": MERCHANT_ACCOUNT,
        "amount": amount,
        "currency": "UAH",
        "orderReference": ref,
        "orderDate": 1700000000,
        "merchantAuthType": uid,
        "productName": "NephroLog",
        "productCount": "1",
        "productPrice": amount
    }
    signature = generate_signature(payload, MERCHANT_SECRET)
    payload["signature"] = signature

    form = "".join(
        f'<input type="hidden" name="{k}" value="{v}"/>' for k, v in payload.items()
    )

    return f"""<!DOCTYPE html>
<html>
  <body onload=\"document.forms[0].submit()\">
    <form method=\"POST\" action=\"https://secure.wayforpay.com/pay\">
      {form}
    </form>
  </body>
</html>"""

@app.post("/wfp-callback")
async def callback(request: Request):
    data = await request.json()
    status = data.get("transactionStatus")
    user_id = int(data.get("merchantAuthType", 0))
    ref = data.get("orderReference")

    if status == "Approved" and ref not in paid_refs:
        paid_refs.add(ref)
        await bot.send_message(user_id, "✅ Оплату підтверджено! Ось ваше посилання:")
        await bot.send_message(user_id, INVITE_LINK)

    return {"status": "ok"}

@dp.message_handler(commands=["start"])
async def start_handler(message: types.Message):
    await message.answer(
        "\U0001F4A1 <b>Підписка на NephroLog</b>\n"
        "Тариф: 439 грн\n\n"
        "Отримай доступ до закритої групи з професійною інформацією.\n\n"
        "Щоб оформити підписку, натисни кнопку нижче:",
        parse_mode="HTML",
        reply_markup=types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton(
                "\U0001F4B3 Оплатити зараз",
                url=f"{RENDER_EXTERNAL_URL}/pay?uid={message.from_user.id}&ref=sub-{uuid.uuid4()}&amount=439"
            )
        )
    )
