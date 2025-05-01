import os
import uuid
import hmac
import hashlib
import time
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.types import Update
import asyncio

# Завантаження .env
load_dotenv()

API_TOKEN = os.getenv("API_TOKEN")
MERCHANT_ACCOUNT = os.getenv("MERCHANT_ACCOUNT")
MERCHANT_SECRET = os.getenv("MERCHANT_SECRET")
INVITE_LINK = os.getenv("INVITE_LINK")
PUBLIC_HOST = os.getenv("RENDER_EXTERNAL_URL")

WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{PUBLIC_HOST}{WEBHOOK_PATH}"

# Telegram бот
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)
app = FastAPI()

# Список для зберігання оброблених платежів
paid_refs = set()

# Генерація підпису WayForPay

def generate_signature(data: list, secret: str) -> str:
    raw = ";".join(map(str, data))
    return hmac.new(secret.encode(), raw.encode(), hashlib.md5).hexdigest()

@app.get("/pay", response_class=HTMLResponse)
async def pay_page(uid: int):
    order_reference = f"order_{int(time.time())}"
    order_date = int(time.time())
    amount = 439
    currency = "UAH"
    product_name = ["NephroLog Test Access"]
    product_price = [amount]
    product_count = [1]

    signature_data = [
        MERCHANT_ACCOUNT,
        "nephrolog-bot.onrender.com",
        order_reference,
        order_date,
        amount,
        currency,
        *product_name,
        *product_count,
        *product_price
    ]
    signature = generate_signature(signature_data, MERCHANT_SECRET)

    payload = {
        "transactionType": "CREATE_INVOICE",
        "merchantAccount": MERCHANT_ACCOUNT,
        "merchantDomainName": "nephrolog-bot.onrender.com",
        "orderReference": order_reference,
        "orderDate": order_date,
        "amount": amount,
        "currency": currency,
        "productName": product_name,
        "productCount": product_count,
        "productPrice": product_price,
        "merchantSignature": signature,
        "clientEmail": "test@example.com",
        "clientPhone": "+380000000000",
        "language": "UA",
        "serviceUrl": f"{PUBLIC_HOST}/wfp-callback"
    }

   form = ""
for k, v in payload.items():
    value = ",".join(map(str, v)) if isinstance(v, list) else str(v)
    form += f'<input type="hidden" name="{k}" value="{value}"/>'
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
async def wfp_callback(request: Request):
    data = await request.json()
    status = data.get("transactionStatus")
    ref = data.get("orderReference")
    user_id = data.get("merchantAuthType")  # якщо передавати uid тут

    # Перевірка підпису
    signature_data = [
        data.get("merchantAccount"),
        data.get("orderReference"),
        data.get("amount"),
        data.get("currency"),
        data.get("authCode"),
        data.get("cardPan"),
        data.get("transactionStatus"),
        data.get("reasonCode")
    ]
    generated_signature = generate_signature(signature_data, MERCHANT_SECRET)
    if data.get("merchantSignature") != generated_signature:
        return {"status": "error", "reason": "invalid signature"}

    if status == "Approved" and ref not in paid_refs:
        paid_refs.add(ref)
        if user_id:
            await bot.send_message(int(user_id), "✅ Оплату підтверджено! Ось ваше посилання:")
            await bot.send_message(int(user_id), INVITE_LINK)

    now = int(time.time())
    callback_signature = generate_signature([ref, "accept", now], MERCHANT_SECRET)
    return {
        "orderReference": ref,
        "status": "accept",
        "time": now,
        "signature": callback_signature
    }

@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    body = await request.json()
    update = Update.to_object(body)
    await dp.process_update(update)
    return {"status": "ok"}

@app.on_event("startup")
async def on_startup():
    await bot.set_webhook(WEBHOOK_URL)

@app.on_event("shutdown")
async def on_shutdown():
    await bot.delete_webhook()

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
                url=f"{PUBLIC_HOST}/pay?uid={message.from_user.id}"
            )
        )
    )
