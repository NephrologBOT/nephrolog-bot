import logging
import os
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor
from dotenv import load_dotenv
import uuid

load_dotenv()

API_TOKEN = os.getenv("API_TOKEN")
STANDARD_PRICE = int(os.getenv("STANDARD_PRICE", 549))
DISCOUNT_PRICE = int(os.getenv("DISCOUNT_PRICE", 439))
DISCOUNT_LIMIT = int(os.getenv("DISCOUNT_LIMIT", 10))
PUBLIC_HOST = os.getenv("PUBLIC_HOST")

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)

discount_counter = 0

@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    global discount_counter
    user_id = message.from_user.id
    order_ref = f"sub-{uuid.uuid4().hex[:10]}"

    if discount_counter < DISCOUNT_LIMIT:
        price = DISCOUNT_PRICE
        discount_counter += 1
        discount_note = " (знижка для перших 10 користувачів)"
    else:
        price = STANDARD_PRICE
        discount_note = ""

    pay_link = f"https://{PUBLIC_HOST}/pay?uid={user_id}&ref={order_ref}&amount={price}"

    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton(text=f"💳 Оплатити {price} грн", url=pay_link)
    )

    await message.answer(
        f"💡 <b>Підписка на NephroLog</b>\n"
        f"Тариф: {price} грн{discount_note}\n\n"
        "Отримай доступ до закритої групи з професійною інформацією.",
        reply_markup=markup
    )

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
