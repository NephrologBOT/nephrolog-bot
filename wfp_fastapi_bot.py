import hmac
import hashlib
import base64
import time
import os
import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from aiogram import Router, types, Bot
from aiogram.types import Update
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.dispatcher.dispatcher import Dispatcher
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from aiogram.filters import Command

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
WAYFORPAY_ACCOUNT = os.getenv("WAYFORPAY_ACCOUNT")
WAYFORPAY_SECRET_KEY = os.getenv("WAYFORPAY_SECRET_KEY")
GROUP_LINK = os.getenv("GROUP_LINK")
PRICE_UAH = os.getenv("STANDARD_PRICE") or "1"
DOMAIN = os.getenv("PUBLIC_HOST") or "nephrolog-bot.onrender.com"

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
router = Router()
app = FastAPI()

@app.get("/")
async def root():
    return {"status": "ok", "version": "v1"}

WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"https://{DOMAIN}{WEBHOOK_PATH}"

def create_invoice(uid: str, amount: str) -> str:
    order_reference = f"order-{uid}-{int(time.time())}"
    order_date = int(time.time())
    currency = "UAH"
    product_name = ["Telegram Premium Access"]
    product_price = [float(amount)]
    product_count = [1]

    data = {
        "transactionType": "CREATE_INVOICE",
        "merchantAccount": WAYFORPAY_ACCOUNT,
        "merchantAuthType": "SimpleSignature",
        "merchantDomainName": DOMAIN,
        "merchantSignature": "",  # Поки що порожній, далі оновимо
        "apiVersion": 1,
        "language": "ua",
        "serviceUrl": f"https://{DOMAIN}/wfp-callback",
        "orderReference": order_reference,
        "orderDate": order_date,
        "amount": float(amount),
        "currency": currency,
        "orderTimeout": 86400,
        "productName": product_name,
        "productPrice": product_price,
        "productCount": product_count,
        "clientFirstName": "User",
        "clientLastName": str(uid),
        "clientEmail": f"user{uid}@nephrolog.com"
    }

    # Формуємо SIGNATURE_STRING
    signature_parts = [
    data["merchantAccount"],
    data["merchantDomainName"],
    data["orderReference"],
    str(data["orderDate"]),
    str(int(data["amount"])) if float(data["amount"]).is_integer() else f"{data['amount']:.2f}",
    data["currency"],
    *data["productName"],
    *map(lambda x: str(int(x)), data["productCount"]),
    *map(lambda x: str(int(x)) if float(x).is_integer() else f"{x:.2f}", data["productPrice"]),
]
    signature_string = ";".join(signature_parts)
    print("SIGNATURE_STRING:", signature_string)

    # Створення підпису
    signature = hmac.new(
        WAYFORPAY_SECRET_KEY.encode(),
        signature_string.encode(),
        hashlib.md5
    ).hexdigest()
    print("SIGNATURE:", signature)

    # Додаємо підпис
    data["merchantSignature"] = signature

    # Запит до WayForPay
    try:
        response = requests.post("https://api.wayforpay.com/api", json=data)
        response.raise_for_status()
        result = response.json()
        print("WAYFORPAY RESPONSE:", result)
    except Exception as e:
        print("Error in WayForPay request:", e)
        raise

    if "invoiceUrl" not in result:
        raise ValueError(f"WayForPay error: {result.get('reason')} ({result.get('reasonCode')})")

    return result["invoiceUrl"]

@router.message(Command("start"))
async def start_handler(message: types.Message):
    uid = message.from_user.id
    pay_link = f"https://{DOMAIN}/pay?uid={uid}"
    kb = types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text="💳 Оплатити", url=pay_link)]])
    await message.answer("Привіт! Щоб оформити підписку, натисніть кнопку нижче 👇", reply_markup=kb)

@app.get("/pay")
async def pay_redirect(uid: str, amount: str = PRICE_UAH):
    invoice_url = create_invoice(uid, amount)
    return RedirectResponse(invoice_url)

@app.post("/wfp-callback")
async def callback(request: Request):
    payload = await request.json()
    status = payload.get("transactionStatus")
    email = payload.get("clientEmail")

    # Витягуємо Telegram user_id з email-у
    user_id = None
    if email and "@nephrolog.com" in email:
        try:
            user_id = int(email.split("@")[0])
        except ValueError:
            print("Invalid user ID in email")

    if status == "Approved" and user_id:
        try:
            kb = types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="🔗 Перейти до групи", url=GROUP_LINK)]
            ])
            await bot.send_message(user_id, "✅ Оплата успішна! Ось ваше посилання:", reply_markup=kb)
        except Exception as e:
            print(f"Failed to send message: {e}")
    else:
        print(f"Callback received but user_id not found or status not approved. Payload: {payload}")

    return {"code": 0}

@app.on_event("startup")
async def on_startup():
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    app.state.dp = dp
    await bot.set_webhook(WEBHOOK_URL)

@app.on_event("shutdown")
async def on_shutdown():
    await bot.session.close()

@app.post("/webhook")
async def telegram_webhook(update: dict):
    telegram_update = Update.model_validate(update)
    await app.state.dp.feed_update(bot, telegram_update)
    return {"ok": True}
