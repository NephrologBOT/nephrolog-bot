import os
import uuid
import hmac
import hashlib
import time
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
import asyncio

# Завантаження .env
load_dotenv()

API_TOKEN = os.getenv("API_TOKEN")
MERCHANT_ACCOUNT = os.getenv("MERCHANT_ACCOUNT")
MERCHANT_SECRET = os.getenv("MERCHANT_SECRET")
INVITE_LINK = os.getenv("INVITE_LINK")

# Ініціалізація Telegram-бота
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)
app = FastAPI()

paid_refs = set()

# Генерація підпису WayForPay для callback
def generate_callback_signature(data: dict, secret: str) -> str:
    keys = ["merchantAccount", "orderReference", "amount", "currency", "authCode", "cardPan", "transactionStatus", "reasonCode"]
    raw = ";".join([str(data.get(k, "")) for k in keys])
    return hmac.new(secret.encode(), raw.encode(), hashlib.md5).hexdigest()

# Генерація підпису для інвойсу
def generate_invoice_signature(data: dict, secret: str) -> str:
    fields = [
        "merchantAccount", "merchantDomainName", "orderReference", "orderDate",
        "amount", "currency"
    ]
    fields += data["productName"] + [str(c) for c in data["productCount"]] + [str(p) for p in data["productPrice"]]
    raw = ";".join(fields)
    return hmac.new(secret.encode(), raw.encode(), hashlib.md5).hexdigest()

@app.get("/pay", response_class=HTMLResponse)
async def pay_page(uid: int):
    now = int(time.time())
    ref = f"order_{uid}_{now}"
    data = {
        "transactionType": "CREATE_INVOICE",
        "merchantAccount": MERCHANT_ACCOUNT,
        "merchantAuthType": "SimpleSignature",
        "merchantDomainName": "nephrolog-bot.onrender.com",
        "orderReference": ref,
        "orderDate": now,
        "amount": "439",
        "currency": "UAH",
        "productName": ["NephroLog"],
        "productCount": ["1"],
        "productPrice": ["439"]
    }
    signature = generate_invoice_signature(data, MERCHANT_SECRET)
    data["merchantSignature"] = signature
    data["apiVersion"] = 1
    form = ""
    for k, v in data.items():
        if isinstance(v, list):
            for item in v:
                form += f'<input type="hidden" name="{k}[]" value="{item}"/>'
        else:
            form += f'<input type="hidden" name="{k}" value="{v}"/>'

    return f"""<!DOCTYPE html>
<html>
  <body onload=\"document.forms[0].submit()\">
    <form method=\"POST\" action=\"https://api.wayforpay.com/api\">
      {form}
    </form>
  </body>
</html>"""

# Callback від WayForPay
@app.post("/wfp-callback")
async def wfp_callback(request: Request):
    data = await request.json()
    signature = data.get("merchantSignature")
    expected = generate_callback_signature(data, MERCHANT_SECRET)
    if signature != expected:
        return {"status": "invalid signature"}

    if data.get("transactionStatus") == "Approved":
        user_id = int(data.get("orderReference", "0").split("_")[1])
        ref = data.get("orderReference")
        if ref not in paid_refs:
            paid_refs.add(ref)
            await bot.send_message(user_id, "✅ Оплату підтверджено! Ось доступ до групи:")
            await bot.send_message(user_id, INVITE_LINK)

    return {
        "orderReference": data.get("orderReference"),
        "status": "accept",
        "time": int(time.time()),
        "signature": hmac.new(
            MERCHANT_SECRET.encode(),
            f"{data.get('orderReference')};accept;{int(time.time())}".encode(),
            hashlib.md5
        ).hexdigest()
    }

# Хендлер /start
@dp.message_handler(commands=["start"])
async def start_handler(message: types.Message):
    url = f"https://nephrolog-bot.onrender.com/pay?uid={message.from_user.id}"
    btn = types.InlineKeyboardMarkup().add(
        types.InlineKeyboardButton("💳 Оплатити 439 грн", url=url)
    )
    await message.answer(
        "<b>Підписка на NephroLog</b>\nТариф: 439 грн\n\nОтримай доступ до закритої групи з професійною інформацією.",
        parse_mode="HTML",
        reply_markup=btn
    )

# Запуск Telegram polling
if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    from aiogram import executor
    executor.start_polling(dp, skip_updates=True)
