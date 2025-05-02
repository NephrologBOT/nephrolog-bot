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
    import time
    import hmac
    import hashlib
    import requests

    order_reference = f"order-{uid}-{int(time.time())}"
    order_date = int(time.time())
    product_name = ["Telegram Premium Access"]
    product_price = [float(amount)]
    product_count = [1]

    data = {
        "transactionType": "CREATE_INVOICE",
        "merchantAccount": WAYFORPAY_ACCOUNT,
        "merchantAuthType": "SimpleSignature",
        "merchantDomainName": DOMAIN,
        "apiVersion": 1,
        "orderReference": order_reference,
        "orderDate": order_date,
        "amount": float(amount),
        "currency": "UAH",
        "productName": product_name,
        "productCount": product_count,
        "productPrice": product_price,
        "language": "ua",
        "serviceUrl": f"https://{DOMAIN}/wfp-callback",
        "clientFirstName": "User",
        "clientLastName": str(uid),
        "clientEmail": f"user{uid}@nephrolog.com",
    }

    # Створення контрольного підпису
    keys = [
        data["merchantAccount"],
        data["merchantDomainName"],
        data["orderReference"],
        str(data["orderDate"]),
        f"{data['amount']:.2f}",
        data["currency"],
        *data["productName"],
        *map(str, data["productCount"]),
        *map(lambda x: str(int(x)) if float(x).is_integer() else f"{x:.2f}", data["productPrice"])
    ]

    signature_string = ";".join(keys)
    signature = hmac.new(
        WAYFORPAY_SECRET_KEY.encode(),
        signature_string.encode("utf-8"),
        hashlib.md5
    ).hexdigest()

    data["merchantSignature"] = signature

    print("SIGNATURE_STRING:", signature_string)
    print("SIGNATURE:", signature)

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
    user_id = payload.get("clientLastName")
    status = payload.get("transactionStatus")

    if status == "Approved":
        try:
            kb = types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text="🔗 Перейти до групи", url=GROUP_LINK)]])
            await bot.send_message(user_id, "✅ Оплату підтверджено! Ось ваше посилання:", reply_markup=kb)
        except Exception as e:
            print(f"Failed to send message: {e}")
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
