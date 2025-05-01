import time
import hmac
import hashlib
import json
import nest_asyncio
from typing import Dict, Any
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
import os
from dotenv import load_dotenv

load_dotenv()
nest_asyncio.apply()

# --- Конфігурація ---
MERCHANT_ACCOUNT = os.getenv("MERCHANT_ACCOUNT", "test_merch_n1")
MERCHANT_SECRET_KEY = os.getenv("MERCHANT_SECRET_KEY", "flk3409refn54t54t*FNJRET")
MERCHANT_DOMAIN = os.getenv("MERCHANT_DOMAIN", "nephrologbot.render.com")
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_LINK = os.getenv("GROUP_LINK", "https://t.me/+sU9cddiye25mOTFi")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
app = FastAPI()

@app.get("/", response_class=HTMLResponse)
def root():
    return "Bot is running"

@app.get("/pay", response_class=HTMLResponse)
def pay(uid: int, amount: int = 1):  # за замовчуванням 1 грн для тесту
    order_reference = f"test_order_{int(time.time())}"
    order_date = int(time.time())

    payload = {
        "transactionType": "CREATE_INVOICE",
        "merchantAccount": MERCHANT_ACCOUNT,
        "merchantAuthType": "SimpleSignature",
        "merchantDomainName": MERCHANT_DOMAIN,
        "apiVersion": 1,
        "orderReference": order_reference,
        "orderDate": order_date,
        "amount": amount,
        "currency": "UAH",
        "productName": ["NephroLog"],
        "productCount": [1],
        "productPrice": [amount],
        "clientFirstName": "User",
        "clientLastName": str(uid),
        "serviceUrl": f"https://{MERCHANT_DOMAIN}/wfp-callback"
    }

    signature_string = ";".join([
        payload["merchantAccount"],
        payload["merchantDomainName"],
        payload["orderReference"],
        str(payload["orderDate"]),
        str(payload["amount"]),
        payload["currency"],
        payload["productName"][0],
        str(payload["productCount"][0]),
        str(payload["productPrice"][0])
    ])

    payload["merchantSignature"] = hmac.new(
        MERCHANT_SECRET_KEY.encode(),
        signature_string.encode(),
        hashlib.md5
    ).hexdigest()

    form = ""
    for k, v in payload.items():
        form += f'<input type="hidden" name="{k}" value="{",".join(map(str, v)) if isinstance(v, list) else v}"/>'

    html = f"""
    <html>
        <body onload=\"document.forms[0].submit()\">
            <form method="POST" action="https://secure.wayforpay.com/pay">
                {form}
            </form>
        </body>
    </html>
    """
    return HTMLResponse(content=html)

@app.post("/wfp-callback")
async def callback(request: Request):
    data = await request.json()

    try:
        user_id = int(data["clientLastName"])
        if data.get("transactionStatus") == "Approved":
            await bot.send_message(user_id, "✅ Оплату підтверджено! Ось ваше посилання:")
            await bot.send_message(user_id, GROUP_LINK)
    except Exception as e:
        print(f"Помилка в callback: {e}")
    return {"orderReference": data.get("orderReference"), "status": "accept", "time": int(time.time())}

# Запуск бота
@dp.message_handler(commands=['start'])
async def start_handler(message: types.Message):
    await message.answer("Привіт! Натисни /pay щоб оформити підписку.")

@dp.message_handler(commands=['pay'])
async def pay_handler(message: types.Message):
    pay_url = f"https://{MERCHANT_DOMAIN}/pay?uid={message.from_user.id}&amount=1"
    await message.answer(f"🔗 Натисни для оплати: {pay_url}")

@app.on_event("startup")
async def on_startup():
    import asyncio
    loop = asyncio.get_event_loop()
    loop.create_task(dp.start_polling())
