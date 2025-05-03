import hmac
import hashlib
import base64
import time
import os
import json
import requests
import asyncio
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
from aiogram import Bot, types
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

GROUP_ID = -1002622123477 

load_dotenv()
# === Налаштування ===
REMINDER_DELTA = timedelta(minutes=1)  # час до закінчення для нагадування
TRIAL_DURATION = timedelta(minutes=2)  # тривалість підписки (тестова)

def get_pg_connection():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        dbname=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD")
    )

# === Ініціалізація БД ===
def init_db():
    conn = get_pg_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS subscriptions (
            user_id BIGINT PRIMARY KEY,
            start_time TIMESTAMPTZ,
            end_time TIMESTAMPTZ,
            notified BOOLEAN DEFAULT FALSE
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS processed_orders (
            order_reference TEXT PRIMARY KEY
        )
    ''')
    conn.commit()
    conn.close()

def is_order_processed(order_reference: str) -> bool:
    conn = get_pg_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM processed_orders WHERE order_reference = %s", (order_reference,))
    result = cursor.fetchone()
    conn.close()
    return result is not None

def mark_order_as_processed(order_reference: str):
    conn = get_pg_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO processed_orders (order_reference) VALUES (%s) ON CONFLICT DO NOTHING", (order_reference,))
    conn.commit()
    conn.close()

def is_subscription_active(user_id: int) -> bool:
    conn = get_pg_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT end_time FROM subscriptions WHERE user_id = %s", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        end_time = row[0]
        return end_time > datetime.utcnow()
    return False

def add_subscription(user_id: int):
    now = datetime.utcnow()
    end = now + TRIAL_DURATION
    conn = get_pg_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO subscriptions (user_id, start_time, end_time, notified)
        VALUES (%s, %s, %s, FALSE)
        ON CONFLICT (user_id) DO UPDATE
        SET start_time = EXCLUDED.start_time,
            end_time = EXCLUDED.end_time,
            notified = FALSE
    ''', (user_id, now, end))
    conn.commit()
    conn.close()
async def check_subscriptions(bot: Bot):
    print("🔄 Перевірка підписок активна")
    while True:
        now = datetime.utcnow().replace(microsecond=0)
        conn = get_pg_connection()
        cursor = conn.cursor()

        # Надіслати нагадування
        cursor.execute("""
            SELECT user_id FROM subscriptions
            WHERE end_time <= %s AND notified = FALSE
        """, (now + REMINDER_DELTA,))
        for row in cursor.fetchall():
            user_id = row[0]
            print(f"⏰ Перевірка нагадування для {user_id}")
            try:
                await bot.send_message(user_id, "⏳ Підписка закінчується менше ніж за 5 хвилин")
                cursor.execute("UPDATE subscriptions SET notified = TRUE WHERE user_id = %s", (user_id,))
            except Exception as e:
                print(f"⚠️ Failed to send reminder to {user_id}: {e}")

        # Видалити завершені підписки та користувачів з групи
        cursor.execute("SELECT user_id FROM subscriptions WHERE end_time <= %s", (now,))
        for row in cursor.fetchall():
            user_id = row[0]
            print(f"❌ Перевірка на завершення для {user_id}")
            try:
                await bot.ban_chat_member(GROUP_ID, user_id)
                await bot.unban_chat_member(GROUP_ID, user_id)

                pay_link = f"https://{DOMAIN}/pay?uid={user_id}"
                kb = types.InlineKeyboardMarkup(inline_keyboard=[
                    [types.InlineKeyboardButton(text="🔄 Продовжити підписку", url=pay_link)]
                ])
                await bot.send_message(
                    user_id,
                    "❌ Ваша підписка завершилась. Дякуємо, що були з нами!",
                    reply_markup=kb
                )
                print(f"✅ User {user_id} removed from group and notified")
            except Exception as e:
                print(f"⚠️ Failed to remove user {user_id} from group: {e}")

            cursor.execute("DELETE FROM subscriptions WHERE user_id = %s", (user_id,))

        conn.commit()
        conn.close()
        await asyncio.sleep(60)

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
        "clientEmail": f"{uid}@nephrolog.com"
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
    order_reference = payload.get("orderReference", "")

    user_id = None
    if order_reference.startswith("order-"):
        try:
            user_id = int(order_reference.split("-")[1])
        except (IndexError, ValueError):
            print(f"Cannot extract user_id from orderReference: {order_reference}")

    if is_order_processed(order_reference):
        print(f"Order already processed: {order_reference}")
        return {"code": 0}

    if status == "Approved" and user_id:
        try:
            if is_subscription_active(user_id):
                print(f"User {user_id} already has active subscription — skipping invite")
            else:
                kb = types.InlineKeyboardMarkup(inline_keyboard=[
                    [types.InlineKeyboardButton(text="🔗 Перейти до групи", url=GROUP_LINK)]
                ])
                await bot.send_message(user_id, "✅ Оплата успішна! Ось ваше посилання:", reply_markup=kb)
                add_subscription(user_id)

            # 💾 ОБОВ'ЯЗКОВО ставимо як опрацьоване — незалежно від статусу підписки
            mark_order_as_processed(order_reference)

        except Exception as e:
            print(f"Failed to process approved payment: {e}")

    else:
        print(f"Callback received but user_id not found or status not approved. Payload: {payload}")

    return {"code": 0}

@app.on_event("startup")
async def on_startup():
    init_db()  # ініціалізація БД
    dp = Dispatcher(bot=bot, storage=MemoryStorage())
    dp.include_router(router)
    app.state.dp = dp
    await bot.set_webhook(WEBHOOK_URL)
    asyncio.create_task(check_subscriptions(bot))  # запуск перевірки підписок

@app.on_event("shutdown")
async def on_shutdown():
    await bot.session.close()

@app.post("/webhook")
async def telegram_webhook(update: dict):
    telegram_update = Update.model_validate(update)
    await app.state.dp.feed_update(bot, telegram_update)
    return {"ok": True}
