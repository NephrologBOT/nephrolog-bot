import os
from aiogram import Bot, Dispatcher, types
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from aiogram.enums import ParseMode
from aiogram.utils.markdown import hbold
from dotenv import load_dotenv
import uuid

load_dotenv()

API_TOKEN = os.getenv("API_TOKEN")
PUBLIC_HOST = os.getenv("PUBLIC_HOST")
STANDARD_PRICE = int(os.getenv("STANDARD_PRICE", 549))
DISCOUNT_PRICE = int(os.getenv("DISCOUNT_PRICE", 439))
DISCOUNT_LIMIT = int(os.getenv("DISCOUNT_LIMIT", 10))

bot = Bot(token=API_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

counter = 0

@dp.message()
async def start_handler(msg: types.Message):
    global counter
    uid = msg.from_user.id
    ref = f"sub-{uuid.uuid4().hex[:10]}"
    amount = DISCOUNT_PRICE if counter < DISCOUNT_LIMIT else STANDARD_PRICE
    counter += 1

    pay_url = f"https://{PUBLIC_HOST}/pay?uid={uid}&ref={ref}&amount={amount}"

    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="💳 Оплатити")]], resize_keyboard=True)

    await msg.answer(
        f"💡 <b>Підписка на NephroLog</b>
"
        f"{hbold('Тариф')}: {amount} грн

"
        f"Отримай доступ до закритої групи з професійною інформацією.

"
        f"Натисни кнопку нижче 👇",
        reply_markup=kb
    )

@dp.message(lambda m: m.text == "💳 Оплатити")
async def pay_button(msg: types.Message):
    global counter
    uid = msg.from_user.id
    ref = f"sub-{uuid.uuid4().hex[:10]}"
    amount = DISCOUNT_PRICE if counter < DISCOUNT_LIMIT else STANDARD_PRICE
    counter += 1
    pay_url = f"https://{PUBLIC_HOST}/pay?uid={uid}&ref={ref}&amount={amount}"
    await msg.answer(f"🔗 Посилання для оплати:
{pay_url}")

if __name__ == "__main__":
    import asyncio
    dp.run_polling(bot)
