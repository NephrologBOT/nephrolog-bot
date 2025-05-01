import hashlib
import hmac
import os
import time
import aiohttp
import asyncio
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types
from starlette.responses import HTMLResponse
import nest_asyncio

load_dotenv()
nest_asyncio.apply()

# Load environment variables
required_vars = [
    "BOT_TOKEN", "WAYFORPAY_ACCOUNT", "WAYFORPAY_SECRET_KEY",
    "GROUP_LINK", "PUBLIC_HOST", "STANDARD_PRICE"
]
missing_vars = [var for var in required_vars if not os.getenv(var)]
if missing_vars:
    raise ValueError(f"Environment variables missing: {', '.join(missing_vars)}. Please check Render settings.")

BOT_TOKEN = os.getenv("BOT_TOKEN")
MERCHANT_ACCOUNT = os.getenv("WAYFORPAY_ACCOUNT")
MERCHANT_SECRET = os.getenv("WAYFORPAY_SECRET_KEY")
GROUP_LINK = os.getenv("GROUP_LINK")
PUBLIC_HOST = os.getenv("PUBLIC_HOST")
STANDARD_PRICE = int(os.getenv("STANDARD_PRICE"))

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
app = FastAPI()

@app.get("/pay")
async def pay(uid: str, amount: int):
    order_reference = f"order_{uid}_{int(time.time())}"
    order_date = int(time.time())

    data = {
        "merchantAccount": MERCHANT_ACCOUNT,
        "merchantDomainName": PUBLIC_HOST,
        "orderReference": order_reference,
        "orderDate": order_date,
        "amount": amount,
        "currency": "UAH",
        "productName": ["Підписка NephroLog"],
        "productPrice": [amount],
        "productCount": [1],
        "clientFirstName": "Підписник",
        "clientLastName": "NephroLog",
        "clientEmail": "test@example.com",
        "clientPhone": "+380000000000",
        "language": "UA",
        "serviceUrl": f"{PUBLIC_HOST}/wfp-callback"
    }

    sorted_data = [
        MERCHANT_ACCOUNT,
        PUBLIC_HOST,
        order_reference,
        str(order_date),
        str(amount),
        "UAH",
        "Підписка NephroLog",
        "1",
        str(amount)
    ]
    signature_str = ";".join(sorted_data)
    sign = hmac.new(MERCHANT_SECRET.encode(), signature_str.encode(), hashlib.md5).hexdigest()
    data["merchantSignature"] = sign

    inputs = "\n".join([
        f'<input type="hidden" name="{k}" value="{','.join(map(str, v)) if isinstance(v, list) else v}"/>'
        for k, v in data.items()
    ])

    html_content = f"""
    <html><body>
    <form id="wfp_form" method="POST" action="https://secure.wayforpay.com/pay">
        {inputs}
    </form>
    <script>document.getElementById('wfp_form').submit();</script>
    </body></html>
    """
    return HTMLResponse(content=html_content)

@app.post("/wfp-callback")
async def callback(request: Request):
    payload = await request.json()
    received_sign = payload.get("merchantSignature")

    keys_for_sign = [
        "merchantAccount", "orderReference", "amount", "currency",
        "authCode", "cardPan", "transactionStatus", "reasonCode"
    ]
    sign_string = ";".join([str(payload.get(k, "")) for k in keys_for_sign])
    expected_sign = hmac.new(MERCHANT_SECRET.encode(), sign_string.encode(), hashlib.md5).hexdigest()

    if received_sign != expected_sign or payload.get("transactionStatus") != "Approved":
        return {"code": 0, "message": "Invalid signature or transaction not approved"}

    user_id = int(payload.get("orderReference").split("_")[1])
    try:
        await bot.send_message(user_id, f"✅ Оплату підтверджено! Ось ваше посилання: {GROUP_LINK}")
    except Exception as e:
        print("Error sending message:", e)

    return {"code": 1, "message": "Payment confirmed"}

@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    try:
        url = f"{PUBLIC_HOST}/pay?uid={message.from_user.id}&amount={STANDARD_PRICE}"
        await message.reply(f"👋 Привіт! Щоб отримати доступ до закритого каналу, натисни кнопку нижче для оплати.\n\n{url}")
    except Exception as e:
        await message.reply("Сталася помилка, спробуй пізніше.")
        print("Start command error:", e)

async def on_startup(_):
    print("Bot started")

loop = asyncio.get_event_loop()
loop.create_task(dp.start_polling())
