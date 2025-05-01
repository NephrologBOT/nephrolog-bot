import os
import hmac
import hashlib
import base64
import nest_asyncio
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor

# Перевірка змінних середовища
required_vars = ["BOT_TOKEN", "WAYFORPAY_ACCOUNT", "WAYFORPAY_SECRET_KEY", "PUBLIC_HOST", "GROUP_LINK"]
missing_vars = [var for var in required_vars if os.getenv(var) is None]

if missing_vars:
    raise ValueError(f"Environment variables missing: {', '.join(missing_vars)}. Please check Render settings.")

BOT_TOKEN = os.getenv("BOT_TOKEN")
WAYFORPAY_ACCOUNT = os.getenv("WAYFORPAY_ACCOUNT")
WAYFORPAY_SECRET_KEY = os.getenv("WAYFORPAY_SECRET_KEY")
PUBLIC_HOST = os.getenv("PUBLIC_HOST")
GROUP_LINK = os.getenv("GROUP_LINK")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
app = FastAPI()
nest_asyncio.apply()

@app.get("/", response_class=HTMLResponse)
async def root():
    return "Bot is running"

@app.get("/pay", response_class=HTMLResponse)
async def pay(uid: str, amount: int):
    order_reference = f"ORDER-{uid}-{os.urandom(4).hex()}"
    order_date = str(int(os.time.time()))
    currency = "UAH"
    product_name = ["Підписка на канал"]
    product_count = [1]
    product_price = [amount]

    fields = {
        "merchantAccount": WAYFORPAY_ACCOUNT,
        "merchantDomainName": PUBLIC_HOST,
        "orderReference": order_reference,
        "orderDate": order_date,
        "amount": amount,
        "currency": currency,
        "productName": product_name,
        "productCount": product_count,
        "productPrice": product_price,
        "clientFirstName": "User",
        "clientLastName": "Test",
        "clientEmail": "test@example.com",
        "returnUrl": f"https://t.me/{bot.me.username}"  # optional
    }

    def get_signature(data: dict) -> str:
        raw = ";".join([
            data["merchantAccount"],
            data["merchantDomainName"],
            data["orderReference"],
            data["orderDate"],
            str(data["amount"]),
            data["currency"],
            ",".join(data["productName"]),
            ",".join(map(str, data["productCount"])),
            ",".join(map(str, data["productPrice"])),
        ])
        return base64.b64encode(hmac.new(WAYFORPAY_SECRET_KEY.encode(), raw.encode(), hashlib.md5).digest()).decode()

    fields["merchantSignature"] = get_signature(fields)

    form = ""
    for k, v in fields.items():
        if isinstance(v, list):
            v = ",".join(map(str, v))
        form += f'<input type="hidden" name="{k}" value="{v}"/>'

    html = f"""
    <html>
        <body onload=\"document.forms[0].submit()\">
            <form method="POST" action="https://secure.wayforpay.com/pay">
                {form}
            </form>
        </body>
    </html>
    """
    return HTMLResponse(content=html)

@app.post("/wfp-callback")
async def callback(request: Request):
    data = await request.json()
    user_id = int(data.get("orderReference", "0").split("-")[1])
    try:
        await bot.send_message(user_id, "✅ Оплату підтверджено! Ось ваше посилання: " + GROUP_LINK)
    except Exception as e:
        print("Помилка надсилання повідомлення:", e)
    return {"status": "accept"}

@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    pay_link = f"{PUBLIC_HOST}/pay?uid={message.from_user.id}&amount=1"
    await message.answer(f"Привіт! Натисни кнопку нижче, щоб оформити підписку на канал.\n\n[Оплатити 1 грн]({pay_link})", parse_mode="Markdown")

if __name__ == "__main__":
    from multiprocessing import Process

    def run_fastapi():
        import uvicorn
        uvicorn.run("wfp_fastapi_bot:app", host="0.0.0.0", port=10000, reload=False)

    def run_telegram():
        executor.start_polling(dp, skip_updates=True)

    Process(target=run_fastapi).start()
    Process(target=run_telegram).start()
