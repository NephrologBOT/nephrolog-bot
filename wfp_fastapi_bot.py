import os
import uuid
import hmac
import hashlib
import time
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from aiogram import Bot, Dispatcher, types
from aiogram.types import Update
from dotenv import load_dotenv
import asyncio

load_dotenv()

API_TOKEN = os.getenv("API_TOKEN")
MERCHANT_ACCOUNT = os.getenv("MERCHANT_ACCOUNT")
MERCHANT_SECRET = os.getenv("MERCHANT_SECRET")
INVITE_LINK = os.getenv("INVITE_LINK")
DOMAIN_NAME = os.getenv("DOMAIN_NAME")

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)
app = FastAPI()

paid_refs = set()

# Генерація підпису

def generate_signature(data_list, secret_key):
    raw = ";".join(map(str, data_list))
    return hmac.new(secret_key.encode(), raw.encode(), hashlib.md5).hexdigest()

# HTML сторінка для редиректу на WayForPay

@app.get("/pay", response_class=HTMLResponse)
async def pay_page(uid: int):
    order_reference = f"order_{int(time.time())}"
    order_date = int(time.time())
    amount = 439
    product_name = ["NephroLog"]
    product_price = [amount]
    product_count = [1]

    signature_data = [
        MERCHANT_ACCOUNT,
        DOMAIN_NAME,
        order_reference,
        order_date,
        amount,
        "UAH",
        *product_name,
        *product_count,
        *product_price
    ]

    signature = generate_signature(signature_data, MERCHANT_SECRET)

    payload = {
        "transactionType": "CREATE_INVOICE",
        "merchantAccount": MERCHANT_ACCOUNT,
        "merchantAuthType": "SimpleSignature",
        "merchantDomainName": DOMAIN_NAME,
        "merchantSignature": signature,
        "apiVersion": 1,
        "orderReference": order_reference,
        "orderDate": order_date,
        "amount": amount,
        "currency": "UAH",
        "productName": product_name,
        "productPrice": product_price,
        "productCount": product_count,
        "clientEmail": "test@example.com",
        "serviceUrl": f"{DOMAIN_NAME}/wfp-callback",
        "language": "UA"
    }

    form = ""
    for k, v in payload.items():
        if isinstance(v, list):
            for item in v:
                form += f'<input type="hidden" name="{k}[]" value="{item}"/>'
        else:
            form += f'<input type="hidden" name="{k}" value="{v}"/>'

    html_content = f"""
    <html>
        <body onload=\"document.forms[0].submit()\">
            <form method=\"POST\" action=\"https://secure.wayforpay.com/pay\">
                {form}
            </form>
        </body>
    </html>
    """
    return HTMLResponse(content=html_content)

# Колбек від WayForPay

@app.post("/wfp-callback")
async def callback(request: Request):
    data = await request.json()
    status = data.get("transactionStatus")
    ref = data.get("orderReference")
    user_id = int(data.get("clientEmail", "0").split("@")[0].replace("user", ""))

    if status == "Approved" and ref not in paid_refs:
        paid_refs.add(ref)
        await bot.send_message(user_id, "✅ Оплату підтверджено! Ось ваше посилання:")
        await bot.send_message(user_id, INVITE_LINK)

    response_data = {
        "orderReference": ref,
        "status": "accept",
        "time": int(time.time()),
    }
    response_signature = generate_signature([
        response_data["orderReference"],
        response_data["status"],
        response_data["time"]
    ], MERCHANT_SECRET)
    response_data["signature"] = response_signature
    return response_data

# Команда /start у Telegram

@dp.message_handler(commands=["start"])
async def start_handler(message: types.Message):
    await message.answer(
        "\U0001F4A1 <b>Підписка на NephroLog</b>\n"
        "Тариф: 439 грн\n\n"
        "Отримай доступ до закритої групи з професійною інформацією.\n\n"
        "Натисни кнопку нижче, щоб оплатити:",
        parse_mode="HTML",
        reply_markup=types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton(
                "\U0001F4B3 Оплатити зараз",
                url=f"{DOMAIN_NAME}/pay?uid={message.from_user.id}"
            )
        )
    )

@app.post("/telegram")
async def telegram_webhook(request: Request):
    body = await request.json()
    update = Update.to_object(body)
    await dp.process_update(update)
    return {"status": "ok"}
