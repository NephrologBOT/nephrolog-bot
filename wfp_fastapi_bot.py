import logging
import time
import hmac
import hashlib
import base64
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from aiogram import Bot, Dispatcher, types
import nest_asyncio
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

# Load environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
WAYFORPAY_ACCOUNT = os.getenv("WAYFORPAY_ACCOUNT")
WAYFORPAY_SECRET_KEY = os.getenv("WAYFORPAY_SECRET_KEY")
GROUP_LINK = os.getenv("GROUP_LINK")
STANDARD_PRICE = os.getenv("STANDARD_PRICE")
DISCOUNT_PRICE = os.getenv("DISCOUNT_PRICE")
DISCOUNT_LIMIT = os.getenv("DISCOUNT_LIMIT")
GRACE_PERIOD_DAYS = os.getenv("GRACE_PERIOD_DAYS")
PUBLIC_HOST = os.getenv("PUBLIC_HOST")

required_vars = ["BOT_TOKEN", "WAYFORPAY_ACCOUNT", "WAYFORPAY_SECRET_KEY", "GROUP_LINK"]
missing_vars = [var for var in required_vars if globals().get(var) is None]
if missing_vars:
    raise ValueError(f"Environment variables missing: {', '.join(missing_vars)}. Please check Render settings.")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
app = FastAPI()
nest_asyncio.apply()

@app.on_event("startup")
async def startup():
    loop = asyncio.get_event_loop()
    loop.create_task(dp.start_polling())

@app.get("/pay")
async def pay(uid: int, amount: int):
    order_reference = f"order_{uid}_{int(time.time())}"
    order_date = int(time.time())
    amount_str = str(amount)

    data = {
        "merchantAccount": WAYFORPAY_ACCOUNT,
        "merchantDomainName": PUBLIC_HOST,
        "orderReference": order_reference,
        "orderDate": order_date,
        "amount": amount_str,
        "currency": "UAH",
        "productName": ["Telegram group access"],
        "productCount": ["1"],
        "productPrice": [amount_str],
        "clientFirstName": "Telegram",
        "clientLastName": "User",
        "clientEmail": "user@example.com",
        "language": "UA"
    }

    keys = [
        "merchantAccount", "merchantDomainName", "orderReference", "orderDate",
        "amount", "currency", "productName", "productCount", "productPrice"
    ]

    to_sign = ";".join(
        [",").join(v) if isinstance(v, list) else str(v) for k, v in data.items() if k in keys]
    )
    signature = base64.b64encode(
        hmac.new(
            WAYFORPAY_SECRET_KEY.encode(), to_sign.encode(), hashlib.md5
        ).digest()
    ).decode()
    data["merchantSignature"] = signature

    form_html = '<form id="paymentForm" method="POST" action="https://secure.wayforpay.com/pay">'
    for k, v in data.items():
        value = ",".join(map(str, v)) if isinstance(v, list) else v
        form_html += f'<input type="hidden" name="{k}" value="{value}"/>'
    form_html += '</form><script>document.getElementById("paymentForm").submit();</script>'

    return HTMLResponse(content=form_html)

@app.post("/wfp-callback")
async def callback(request: Request):
    body = await request.json()
    order_reference = body.get("orderReference")
    uid = int(order_reference.split("_")[1])

    logging.info("Received callback: %s", body)

    if body.get("transactionStatus") == "Approved":
        await bot.send_message(uid, "✅ Оплату підтверджено! Ось ваше посилання:")
        await bot.send_message(uid, GROUP_LINK)

    return {"status": "OK"}

@app.get("/")
async def root():
    return {"status": "running"}
