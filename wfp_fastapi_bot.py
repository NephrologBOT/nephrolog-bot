import hmac
import hashlib
import base64
import time
import os
import asyncio
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from aiogram import Bot, types, Dispatcher
from aiogram.types import Update
from aiogram.dispatcher.webhook import get_new_configured_app
import nest_asyncio

# --- Завантаження змінних ---
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
    raise ValueError(f"Environment variables missing: {', '.join(missing_vars)}")

# --- Ініціалізація бота ---
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
app = FastAPI()

WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"https://nephrolog-bot.onrender.com{WEBHOOK_PATH}"

# --- Хендлер /start ---
@dp.message_handler(commands=["start"])
async def start_handler(message: types.Message):
    uid = message.from_user.id
    pay_link = f"https://nephrolog-bot.onrender.com/pay?uid={uid}"
    await message.answer(
        "Привіт! Щоб оформити підписку, натисніть кнопку нижче 👇",
        reply_markup=types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton("💳 Оплатити", url=pay_link)
        )
    )

# --- Обробка webhook (вхідні повідомлення від Telegram) ---
@app.post(WEBHOOK_PATH)
async def telegram_webhook(update: dict):
    telegram_update = Update.to_object(update)
    await dp.process_update(telegram_update)
    return {"ok": True}

# --- Генерація форми оплати WayForPay ---
@app.get("/pay", response_class=HTMLResponse)
async def pay_form(uid: str, amount: str = PRICE_UAH):
    order_reference = f"ORDER-{uid}-{int(time.time())}"
    order_date = str(int(time.time()))
    currency = "UAH"
    product_name = "Telegram Premium Access"
    product_price = str(int(float(amount)))  # гарантія, що буде ціле число
    amount = product_price  # синхронізуємо
    product_count = "1"

    data = {
        "merchantAccount": WAYFORPAY_ACCOUNT,
        "merchantDomainName": "nephrolog-bot.onrender.com",
        "orderReference": order_reference,
        "orderDate": order_date,
        "amount": amount,
        "currency": currency,
        "productName": [product_name],
        "productPrice": [int(product_price)],  # ціле число
        "productCount": [int(product_count)],
        "clientFirstName": "User",
        "clientLastName": str(uid),  # обов'язково str!
        "clientEmail": f"user{uid}@nephrolog.com",
        "serviceUrl": "https://nephrolog-bot.onrender.com/wfp-callback",
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
      <head><meta charset="utf-8"><title>Оплата</title></head>
      <body onload="document.forms[0].submit()">
        <form method="POST" action="https://secure.wayforpay.com/pay">
          {form_inputs}
        </form>
      </body>
    </html>
    """

    return HTMLResponse(content=html_form)

# --- Обробка підтвердження оплати ---
@app.post("/wfp-callback")
async def callback(request: Request):
    payload = await request.json()
    user_id = payload.get("clientLastName")
    status = payload.get("transactionStatus")

    if status == "Approved":
        try:
            button = types.InlineKeyboardMarkup()
            button.add(types.InlineKeyboardButton("🔗 Перейти до групи", url=GROUP_LINK))
            await bot.send_message(
                user_id,
                "✅ Оплату підтверджено! Ось ваше посилання:",
                reply_markup=button
            )
        except Exception as e:
            print(f"Failed to send message: {e}")
    return {"code": 0}

# --- Під час запуску автоматично встановлюємо webhook ---
@app.on_event("startup")
async def on_startup():
    await bot.set_webhook(WEBHOOK_URL)
