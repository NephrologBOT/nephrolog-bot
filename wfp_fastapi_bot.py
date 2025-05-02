import hmac
import hashlib
import base64
import time
import os
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from aiogram import Router, types, Bot
from aiogram.types import Update
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.dispatcher.dispatcher import Dispatcher
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
WAYFORPAY_ACCOUNT = os.getenv("WAYFORPAY_ACCOUNT")
WAYFORPAY_SECRET_KEY = os.getenv("WAYFORPAY_SECRET_KEY")
GROUP_LINK = os.getenv("GROUP_LINK")
PRICE_UAH = os.getenv("STANDARD_PRICE") or "1"
DOMAIN = os.getenv("PUBLIC_HOST") or "nephrolog-bot.onrender.com"

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
router = Router()
app = FastAPI()

WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"https://{DOMAIN}{WEBHOOK_PATH}"

from aiogram.filters import Command
@router.message(Command("start"))
async def start_handler(message: types.Message):
    uid = message.from_user.id
    pay_link = f"https://{DOMAIN}/pay?uid={uid}"
    kb = types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text="💳 Оплатити", url=pay_link)]])
    await message.answer("Привіт! Щоб оформити підписку, натисніть кнопку нижче 👇", reply_markup=kb)

@app.get("/pay", response_class=HTMLResponse)
async def pay_form(uid: str, amount: str = PRICE_UAH):
    order_reference = f"ORDER-{uid}-{int(time.time())}"
    order_date = str(int(time.time()))
    currency = "UAH"
    product_name = "Telegram Premium Access"
    product_price = str(int(float(amount)))
    amount = product_price
    product_count = "1"

    data = {
        "merchantAccount": WAYFORPAY_ACCOUNT,
        "merchantDomainName": DOMAIN,
        "orderReference": order_reference,
        "orderDate": order_date,
        "amount": amount,
        "currency": currency,
        "productName": [product_name],
        "productPrice": [int(product_price)],
        "productCount": [int(product_count)],
        "clientFirstName": "User",
        "clientLastName": str(uid),
        "clientEmail": f"user{uid}@nephrolog.com",
        "serviceUrl": f"https://{DOMAIN}/wfp-callback",
    }

    keys = [
        "merchantAccount", "merchantDomainName", "orderReference", "orderDate",
        "amount", "currency", "productName", "productCount", "productPrice"
    ]

    signature_base = ";".join([
        ",".join(str(x) for x in data[k]) if isinstance(data[k], list) else str(data[k])
        for k in keys
    ])
    hmac_signature = hmac.new(
        WAYFORPAY_SECRET_KEY.encode(),
        signature_base.encode(),
        hashlib.md5
    ).digest()
    merchant_signature = base64.b64encode(hmac_signature).decode()

    data["merchantSignature"] = merchant_signature

    form_inputs = ""
    for k, v in data.items():
        if isinstance(v, list):
            for item in v:
                form_inputs += f'<input type="hidden" name="{k}[]" value="{item}"/>'
        else:
            form_inputs += f'<input type="hidden" name="{k}" value="{v}"/>'

    html_form = f"""
    <!DOCTYPE html>
    <html>
      <head><meta charset=\"utf-8\"><title>Оплата</title></head>
      <body onload=\"document.forms[0].submit()\">
        <form method=\"POST\" action=\"https://secure.wayforpay.com/pay\">
          {form_inputs}
        </form>
      </body>
    </html>
    """
    return HTMLResponse(content=html_form)

@app.post("/wfp-callback")
async def callback(request: Request):
    payload = await request.json()
    user_id = payload.get("clientLastName")
    status = payload.get("transactionStatus")

    if status == "Approved":
        try:
            kb = types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text="🔗 Перейти до групи", url=GROUP_LINK)]])
            await bot.send_message(user_id, "✅ Оплату підтверджено! Ось ваше посилання:", reply_markup=kb)
        except Exception as e:
            print(f"Failed to send message: {e}")
    return {"code": 0}

@app.on_event("startup")
async def on_startup():
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    app.state.dp = dp
    await bot.set_webhook(WEBHOOK_URL)

@app.on_event("shutdown")
async def on_shutdown():
    await bot.session.close()

@app.post("/webhook")
async def telegram_webhook(update: dict):
    telegram_update = Update.model_validate(update)
    await app.state.dp.feed_update(bot, telegram_update, bot.loop)
    return {"ok": True}

