import hmac
import hashlib
import base64
import time
import os
from dotenv import load_dotenv

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

from aiogram import Bot, types
from aiogram.dispatcher import Dispatcher
from aiogram.utils import executor

import nest_asyncio

load_dotenv()
nest_asyncio.apply()

BOT_TOKEN = os.getenv("BOT_TOKEN")
WAYFORPAY_ACCOUNT = os.getenv("WAYFORPAY_ACCOUNT")
WAYFORPAY_SECRET_KEY = os.getenv("WAYFORPAY_SECRET_KEY")
GROUP_LINK = os.getenv("GROUP_LINK")
PRICE_UAH = os.getenv("STANDARD_PRICE") or "1"

required_env_vars = {
    "BOT_TOKEN": BOT_TOKEN,
    "WAYFORPAY_ACCOUNT": WAYFORPAY_ACCOUNT,
    "WAYFORPAY_SECRET_KEY": WAYFORPAY_SECRET_KEY,
    "GROUP_LINK": GROUP_LINK,
}

missing_vars = [k for k, v in required_env_vars.items() if not v]
if missing_vars:
    raise ValueError(f"Environment variables missing: {', '.join(missing_vars)}. Please check Render settings.")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
app = FastAPI()

@app.get("/pay", response_class=HTMLResponse)
async def pay_form(uid: str, amount: str = PRICE_UAH):
    order_reference = f"ORDER-{uid}-{int(time.time())}"
    order_date = str(int(time.time()))
    currency = "UAH"
    product_name = "Telegram Premium Access"
    product_price = amount
    product_count = "1"

    data = {
        "merchantAccount": WAYFORPAY_ACCOUNT,
        "merchantDomainName": "nephrolog-bot.onrender.com",
        "orderReference": order_reference,
        "orderDate": order_date,
        "amount": product_price,
        "currency": currency,
        "productName": [product_name],
        "productPrice": [float(product_price)],
        "productCount": [int(product_count)],
        "clientFirstName": "User",
        "clientLastName": uid,
        "clientEmail": f"user{uid}@nephrolog.com",
        "serviceUrl": "https://nephrolog-bot.onrender.com/wfp-callback",
    }

    keys = [
        "merchantAccount", "merchantDomainName", "orderReference", "orderDate",
        "amount", "currency", "productName", "productCount", "productPrice"
    ]

    signature_base = ";".join([
        ",".join(map(str, data[k])) if isinstance(data[k], list) else str(data[k])
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
        if k in keys + ["merchantSignature", "clientFirstName", "clientLastName", "clientEmail", "serviceUrl"]:
            if isinstance(v, list):
                value = ",".join(map(str, v))
            else:
                value = str(v)
            form_inputs += f'<input type="hidden" name="{k}" value="{value}"/>'

    html_form = (
        "<html><body>"
        "<form id='wfp-form' method='POST' action='https://secure.wayforpay.com/pay'>"
        f"{form_inputs}"
        "<noscript><input type='submit' value='Оплатити'></noscript>"
        "<button type='submit'>Перейти до оплати</button>"
        "</form>"
        "<script>document.getElementById('wfp-form').submit();</script>"
        "</body></html>"
    )
    return HTMLResponse(content=html_form)

@app.post("/wfp-callback")
async def callback(request: Request):
    payload = await request.json()
    user_id = payload.get("clientLastName")
    status = payload.get("transactionStatus")

    if status == "Approved":
        try:
            await bot.send_message(
                user_id,
                f"✅ Оплату підтверджено! Ось ваше посилання:",
                reply_markup=types.InlineKeyboardMarkup().add(
                    types.InlineKeyboardButton("Перейти до групи", url=GROUP_LINK)
                )
            )
        except Exception as e:
            print(f"Failed to send message: {e}")
    return {"code": 0}

@dp.message_handler(commands=["start"])
async def start_handler(message: types.Message):
    uid = message.from_user.id
    pay_link = f"https://nephrolog-bot.onrender.com/pay?uid={uid}"
    await message.answer(f"Привіт! Щоб оформити підписку, перейдіть за посиланням: {pay_link}")
