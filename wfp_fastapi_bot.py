import hmac
import hashlib
import base64
import time
import os
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
import nest_asyncio
import asyncio
import threading

# Завантаження змінних середовища
load_dotenv()
nest_asyncio.apply()

# Обов'язкові змінні середовища
BOT_TOKEN = os.getenv("BOT_TOKEN")
WAYFORPAY_ACCOUNT = os.getenv("WAYFORPAY_ACCOUNT")
WAYFORPAY_SECRET_KEY = os.getenv("WAYFORPAY_SECRET_KEY")
GROUP_LINK = os.getenv("GROUP_LINK")
PRICE_UAH = os.getenv("PRICE_UAH") or "1"

required_env_vars = {
    "BOT_TOKEN": BOT_TOKEN,
    "WAYFORPAY_ACCOUNT": WAYFORPAY_ACCOUNT,
    "WAYFORPAY_SECRET_KEY": WAYFORPAY_SECRET_KEY,
    "GROUP_LINK": GROUP_LINK,
}

missing_vars = [k for k, v in required_env_vars.items() if not v]
if missing_vars:
    raise ValueError(f"Environment variables missing: {', '.join(missing_vars)}. Please check Render settings.")

# Ініціалізація бота та FastAPI
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
app = FastAPI()

# Команда /start
@dp.message_handler(commands=["start"])
async def start_handler(message: types.Message):
    await message.answer("Привіт! Щоб оформити підписку, перейдіть за посиланням: https://nephrolog-bot.onrender.com/pay?uid=" + str(message.from_user.id))

# Маршрут /pay
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
        "merchantAccount",
        "merchantDomainName",
        "orderReference",
        "orderDate",
        "amount",
        "currency",
        "productName",
        "productCount",
        "productPrice",
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

    form_inputs = ''.join([
        f'<input type="hidden" name="{k}" value="{",".join(map(str, v)) if isinstance(v, list) else v}"/>'
        for k, v in data.items() if k in keys + ["merchantSignature", "clientFirstName", "clientLastName", "clientEmail", "serviceUrl"]
    ])

    html_form = f'''
    <html><body>
        <form id="wfp-form" method="POST" action="https://secure.wayforpay.com/pay">
            {form_inputs}
            <noscript><input type="submit" value="Pay"></noscript>
        </form>
        <script>document.getElementById("wfp-form").submit();</script>
    </body></html>
    '''
    return HTMLResponse(content=html_form)

# Callback від WayForPay
@app.post("/wfp-callback")
async def callback(request: Request):
    payload = await request.json()
    user_id = payload.get("clientLastName")
    status = payload.get("transactionStatus")

    if status == "Approved":
        try:
            await bot.send_message(user_id, f"✅ Оплату підтверджено! Ось ваше посилання на групу:\n{GROUP_LINK}")
        except Exception as e:
            print(f"Failed to send message: {e}")
    return {"code": 0}

# Запуск Telegram-бота в окремому потоці
def start_telegram_bot():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    executor.start_polling(dp, skip_updates=True)

threading.Thread(target=start_telegram_bot).start()
