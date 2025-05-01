import os
import hmac
import time
import hashlib
import logging
import asyncio
from typing import Dict, Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from aiogram import Bot, Dispatcher, types
from aiogram.utils.executor import start_polling
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
MERCHANT_ACCOUNT = os.getenv("MERCHANT_ACCOUNT")
MERCHANT_SECRET_KEY = os.getenv("MERCHANT_SECRET_KEY")
PUBLIC_HOST = os.getenv("PUBLIC_HOST")  # наприклад: https://your-render-url.onrender.com

if not all([BOT_TOKEN, MERCHANT_ACCOUNT, MERCHANT_SECRET_KEY, PUBLIC_HOST]):
    raise ValueError("One or more environment variables are missing. Please check .env or Render settings.")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
app = FastAPI()
logging.basicConfig(level=logging.INFO)

# Оплата: HTML форма
@app.get("/pay", response_class=HTMLResponse)
async def pay(uid: str, amount: int):
    order_reference = f"test_order_{int(time.time())}"
    order_date = int(time.time())
    currency = "UAH"
    product_name = ["NephroLog Access"]
    product_price = [amount]
    product_count = [1]

    signature_data = [
        MERCHANT_ACCOUNT,
        "nephrolog.bot",
        order_reference,
        str(order_date),
        str(amount),
        currency,
        *product_name,
        *map(str, product_count),
        *map(str, product_price)
    ]
    signature_base = ";".join(signature_data)
    merchant_signature = hmac.new(
        MERCHANT_SECRET_KEY.encode(),
        signature_base.encode(),
        hashlib.md5
    ).hexdigest()

    form_fields = {
        "transactionType": "CREATE_INVOICE",
        "merchantAccount": MERCHANT_ACCOUNT,
        "merchantDomainName": "nephrolog.bot",
        "merchantSignature": merchant_signature,
        "orderReference": order_reference,
        "orderDate": order_date,
        "amount": amount,
        "currency": currency,
        "productName[]": product_name,
        "productCount[]": product_count,
        "productPrice[]": product_price,
        "clientFirstName": "Nephro",
        "clientLastName": "Log",
        "clientEmail": "client@email.com",
        "language": "UA",
        "serviceUrl": f"{PUBLIC_HOST}/wfp-callback"
    }

    form = ""
    for k, v in form_fields.items():
        if isinstance(v, list):
            for item in v:
                form += f'<input type="hidden" name="{k}" value="{item}"/>\n'
        else:
            form += f'<input type="hidden" name="{k}" value="{v}"/>\n'

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
    data: Dict[str, Any] = await request.json()
    order_reference = data.get("orderReference")
    transaction_status = data.get("transactionStatus")
    user_id = extract_user_id_from_reference(order_reference)

    if transaction_status == "Approved":
        try:
            await bot.send_message(user_id, "✅ Оплату підтверджено! Ось ваше посилання: https://t.me/+sU9cddiye25mOTFi")
        except Exception as e:
            logging.error(f"Помилка надсилання повідомлення: {e}")

    return {"orderReference": order_reference, "status": "accept", "time": int(time.time()), "signature": ""}

def extract_user_id_from_reference(reference: str) -> int:
    try:
        return int(reference.split("_")[-1])
    except (IndexError, ValueError):
        return 0

# Хендлер /start
@dp.message_handler(commands=["start"])
async def start_cmd(message: types.Message):
    pay_link = f"{PUBLIC_HOST}/pay?uid={message.from_user.id}&amount=1"
    await message.answer(f"Привіт! Щоб отримати доступ, оплати за посиланням: {pay_link}")

# Запуск бота
if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()

    loop = asyncio.get_event_loop()
    loop.create_task(dp.start_polling())
    import uvicorn
    uvicorn.run("wfp_fastapi_bot:app", host="0.0.0.0", port=10000, reload=False)
