import hmac
import hashlib
import base64
import time
import os
import json
import requests
import asyncio
import sqlite3
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

PROCESSED_ORDERS_FILE = "processed_orders.json"

def load_processed_orders():
    if not os.path.exists(PROCESSED_ORDERS_FILE):
        return set()
    with open(PROCESSED_ORDERS_FILE, "r") as f:
        try:
            return set(json.load(f))
        except json.JSONDecodeError:
            return set()

def save_processed_orders(processed_orders):
    with open(PROCESSED_ORDERS_FILE, "w") as f:
        json.dump(list(processed_orders), f)

processed_orders = load_processed_orders()

GROUP_ID = -1002622123477 

load_dotenv()
# === Налаштування ===
DB_NAME = "subscriptions.db"
REMINDER_DELTA = timedelta(minutes=1)  # час до закінчення для нагадування
TRIAL_DURATION = timedelta(minutes=2)  # тривалість підписки (тестова)

# === Ініціалізація БД ===
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS subscriptions (
            user_id INTEGER PRIMARY KEY,
            start_time TEXT,
            end_time TEXT,
            notified INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

def is_subscription_active(user_id: int) -> bool:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT end_time FROM subscriptions WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        end_time = datetime.fromisoformat(row[0])
        return end_time > datetime.utcnow()
    return False

# === Додавання підписки ===
def add_subscription(user_id: int):
    now = datetime.utcnow()
    end = now + TRIAL_DURATION
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("REPLACE INTO subscriptions (user_id, start_time, end_time, notified) VALUES (?, ?, ?, 0)",
                   (user_id, now.isoformat(), end.isoformat()))
    conn.commit()
    conn.close()

# === Перевірка підписок ===
async def check_subscriptions(bot: Bot):
    while True:
        now = datetime.utcnow().replace(microsecond=0)
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        # Надіслати нагадування
        cursor.execute("SELECT user_id FROM subscriptions WHERE end_time <= ? AND notified = 0",
                       ((now + REMINDER_DELTA).isoformat(),))
        for row in cursor.fetchall():
            user_id = row[0]
            try:
                await bot.send_message(user_id, "⏳ Підписка закінчується менше ніж за 5 хвилин")
                cursor.execute("UPDATE subscriptions SET notified = 1 WHERE user_id = ?", (user_id,))
            except Exception as e:
                print(f"Failed to send reminder to {user_id}: {e}")

        # Видалити завершені підписки та користувачів з групи
        cursor.execute("SELECT user_id FROM subscriptions WHERE end_time <= ?", (now.isoformat(),))
        for row in cursor.fetchall():
            user_id = row[0]
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
                print(f"User {user_id} removed from group and notified")
            except Exception as e:
                print(f"Failed to remove user {user_id} from group: {e}")
            cursor.execute("DELETE FROM subscriptions WHERE user_id = ?", (user_id,))

        conn.commit()
        conn.close()
        await asyncio.sleep(60)
