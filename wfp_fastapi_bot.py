import os
import uuid
import hmac
import hashlib
import time
import nest_asyncio
import threading
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.types import Update
from aiogram.utils import executor

# Завантаження .env
load_dotenv()

API_TOKEN = os.getenv("API_TOKEN")
MERCHANT_ACCOUNT = os.getenv("MERCHANT_ACCOUNT")
MERCHANT_SECRET = os.getenv("MERCHANT_SECRET")
INVITE_LINK = os.getenv("INVITE_LINK")

# Telegram-бот
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

# FastAPI
app = FastAPI()
paid_refs = set()

# Підпис WayForPay
def generate_signature(data: dict, secret: str) -> str:
    keys = [
        "merchantAccount",
        "merchantDomainName",
        "orderReference",
        "orderDate",
        "amount",
        "currency",
        "productName[0]",
        "productCount[0]",
        "productPrice[0]"
    ]
    raw = ";".join([str(data[k]) for k in keys])
    return hmac.new(secret.encode(), raw.encode(), hashlib.md5).hexdigest()

# /pay сторінка
@app.get("/pay", response_class=HTMLResponse)
async def pay_page(uid: int, amount: int):
    order_reference = f"order_{int(time.time())}"
    payload = {
        "merchantAccount": MERCHANT_ACCOUNT,
        "merchantDomainName": "nephrologbot.render.com",
        "orderReference": order_reference,
        "orderDate": int(time.time()),
        "amount": amount,
        "currency": "UAH",
        "productName[0]": "NephroLog",
        "productCount[0]": "1",
        "productPrice[0]": amount,
    }
    payload["merchantSignature"] = generate_signature(payload, MERCHANT_SECRET)

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

# Callback WayForPay
@app.post("/wfp-callback")
async def callback(request: Request):
    data = await request.json()
    status = data.get("transactionStatus")
    user_id = int(data.get("clientPhone", "0"))
    ref = data.get("orderReference")

    if status == "Approved" and ref not in paid_refs:
        paid_refs.add(ref)
        await bot.send_message(user_id, "✅ Оплату підтверджено! Ось ваше посилання:")
        await bot.send_message(user_id, INVITE_LINK)

    return {"status": "ok"}

# /start обробка
@dp.message_handler(commands=["start"])
async def start_handler(message: types.Message):
    uid = message.from_user.id
    amount = 439
    pay_url = f"https://{os.getenv('PUBLIC_HOST')}/pay?uid={uid}&amount={amount}"

    markup = types.InlineKeyboardMarkup().add(
        types.InlineKeyboardButton("\U0001F4B3 Оплатити зараз", url=pay_url)
    )

    await message.answer(
        "\U0001F4A1 <b>Підписка на NephroLog</b>\n"
        "Тариф: 439 грн\n\n"
        "Отримай доступ до закритої групи з професійною інформацією.\n\n"
        "Щоб оформити підписку, натисни кнопку нижче:",
        parse_mode="HTML",
        reply_markup=markup
    )

# Запуск бота
nest_asyncio.apply()
def start_polling():
    executor.start_polling(dp, skip_updates=True)

threading.Thread(target=start_polling, daemon=True).start()
