import os
import uuid
import hmac
import hashlib
import asyncio
import nest_asyncio
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.types import Update

# Застосування nest_asyncio для коректної роботи у FastAPI
nest_asyncio.apply()

# Завантаження .env
load_dotenv()

API_TOKEN = os.getenv("API_TOKEN")
MERCHANT_ACCOUNT = os.getenv("MERCHANT_ACCOUNT")
MERCHANT_SECRET = os.getenv("MERCHANT_SECRET")
INVITE_LINK = os.getenv("INVITE_LINK")
PUBLIC_HOST = os.getenv("PUBLIC_HOST")

# Налаштування шляху вебхука (не використовується)
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{PUBLIC_HOST}{WEBHOOK_PATH}"

# Ініціалізація Telegram-бота
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)
app = FastAPI()

paid_refs = set()

# Генерація підпису для WayForPay
def generate_signature(data: list, secret: str) -> str:
    raw = ';'.join(str(item) for item in data)
    return hmac.new(secret.encode(), raw.encode(), hashlib.md5).hexdigest()

# Сторінка з формою оплати
@app.get("/pay", response_class=HTMLResponse)
async def pay_page(uid: int):
    order_ref = f"sub-{uuid.uuid4()}"
    order_date = int(datetime.now().timestamp())
    amount = 1  # тестова сума 1 грн

    data = [
        MERCHANT_ACCOUNT,
        "nephrolog-bot.render.com",
        order_ref,
        order_date,
        amount,
        "UAH",
        "NephroLog",
        "1",
        "1"
    ]

    signature = generate_signature(data, MERCHANT_SECRET)

    payload = {
        "transactionType": "CREATE_INVOICE",
        "merchantAccount": MERCHANT_ACCOUNT,
        "merchantDomainName": "nephrolog-bot.render.com",
        "orderReference": order_ref,
        "orderDate": order_date,
        "amount": amount,
        "currency": "UAH",
        "productName": ["NephroLog"],
        "productCount": [1],
        "productPrice": [amount],
        "merchantSignature": signature,
        "apiVersion": 1,
        "language": "UA",
        "serviceUrl": f"{PUBLIC_HOST}/wfp-callback",
        "merchantAuthType": "SimpleSignature"
    }

    inputs = "".join(
        f'<input type="hidden" name="{k}" value="{v if not isinstance(v, list) else ','.join(map(str, v))}"/>'
        for k, v in payload.items()
    )

    return f"""<!DOCTYPE html>
<html>
  <body onload=\"document.forms[0].submit()\">
    <form method=\"POST\" action=\"https://secure.wayforpay.com/pay\">
      {inputs}
    </form>
  </body>
</html>"""

# Колбек від WayForPay
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

    return {"orderReference": ref, "status": "accept", "time": int(datetime.now().timestamp()),
            "signature": generate_signature([ref, "accept", int(datetime.now().timestamp())], MERCHANT_SECRET)}

# Обробник команди /start
@dp.message_handler(commands=["start"])
async def start_handler(message: types.Message):
    await message.answer(
        "\U0001F4A1 <b>Підписка на NephroLog</b>\n"
        "Тестова підписка: 1 грн\n\n"
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
