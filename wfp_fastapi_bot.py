import asyncio
import hashlib
import hmac
import os
import html
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from aiogram import Bot, Dispatcher, types, executor
from dotenv import load_dotenv
import nest_asyncio

load_dotenv()
nest_asyncio.apply()

BOT_TOKEN = os.getenv("BOT_TOKEN")
WAYFORPAY_SECRET_KEY = os.getenv("WAYFORPAY_SECRET_KEY")
WAYFORPAY_ACCOUNT = os.getenv("WAYFORPAY_ACCOUNT")
GROUP_LINK = os.getenv("GROUP_LINK")
DEFAULT_PRICE = int(os.getenv("DEFAULT_PRICE", "1"))

required_vars = ["BOT_TOKEN", "WAYFORPAY_SECRET_KEY", "WAYFORPAY_ACCOUNT", "GROUP_LINK"]
missing_vars = [var for var in required_vars if not globals().get(var)]
if missing_vars:
    raise ValueError(f"Environment variables missing: {', '.join(missing_vars)}. Please check Render settings.")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
app = FastAPI()

@app.get("/", response_class=HTMLResponse)
async def root():
    return "OK"

@app.get("/pay", response_class=HTMLResponse)
async def pay(uid: str, amount: int = DEFAULT_PRICE):
    order_reference = f"INV{uid}{int(datetime.utcnow().timestamp())}"
    order_date = int(datetime.utcnow().timestamp())
    currency = "UAH"

    product_name = ["Підписка на канал NephroLog"]
    product_count = [1]
    product_price = [amount]

    fields_for_signature = [
        WAYFORPAY_ACCOUNT,
        order_reference,
        str(order_date),
        str(amount),
        currency,
        ",".join(product_name),
        ",".join(map(str, product_count)),
        ",".join(map(str, product_price)),
    ]
    sign_string = ";".join(fields_for_signature)
    signature = hmac.new(
        WAYFORPAY_SECRET_KEY.encode(),
        sign_string.encode(),
        hashlib.md5
    ).hexdigest()

    inputs = {
        "merchantAccount": WAYFORPAY_ACCOUNT,
        "merchantDomainName": "nephrolog.render.com",
        "merchantSignature": signature,
        "orderReference": order_reference,
        "orderDate": order_date,
        "amount": amount,
        "currency": currency,
        "productName[]": product_name,
        "productCount[]": product_count,
        "productPrice[]": product_price,
        "clientFirstName": "Telegram",
        "clientLastName": uid,
        "clientEmail": f"{uid}@t.me",
        "returnUrl": f"https://t.me/{(await bot.get_me()).username}"
    }

    form_inputs = "".join(
        f'<input type="hidden" name="{html.escape(k)}" value="{html.escape(str(v[0] if isinstance(v, list) else v))}">'
        for k, v in inputs.items()
    )

    html_form = f"""
    <html>
        <body onload='document.forms["payment"].submit()'>
            <form name='payment' action='https://secure.wayforpay.com/pay' method='POST'>
                {form_inputs}
            </form>
        </body>
    </html>
    """
    return HTMLResponse(content=html_form)

@app.post("/wfp-callback")
async def callback(request: Request):
    data = await request.json()

    signature_fields = [
        "merchantAccount",
        "orderReference",
        "amount",
        "currency",
        "authCode",
        "cardPan",
        "transactionStatus",
        "reasonCode"
    ]

    try:
        signature_base = ";".join(str(data[field]) for field in signature_fields)
    except KeyError as e:
        return {"code": 1, "message": f"Missing field in callback: {e}"}

    calculated_signature = hmac.new(
        WAYFORPAY_SECRET_KEY.encode(),
        signature_base.encode(),
        hashlib.md5
    ).hexdigest()

    if calculated_signature != data.get("merchantSignature"):
        return {"code": 2, "message": "Invalid signature"}

    if data.get("transactionStatus") == "Approved":
        user_id = int(data.get("clientLastName", 0))
        asyncio.create_task(bot.send_message(user_id, f"✅ Оплату підтверджено! Ось ваше посилання: {GROUP_LINK}"))

    return {"code": 0}

@dp.message_handler(commands=["start"])
async def start_handler(message: types.Message):
    await message.answer("Привіт! Щоб отримати доступ до каналу, скористайся кнопкою оплати на сайті або напиши /pay")

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
