from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from aiogram import Bot, Dispatcher, types
from aiogram.types import ParseMode
from aiohttp import ClientSession
from starlette.responses import JSONResponse
from starlette.status import HTTP_200_OK
from dotenv import load_dotenv
import os
import hmac
import hashlib
import nest_asyncio
import time

nest_asyncio.apply()

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
WAYFORPAY_ACCOUNT = os.getenv("WAYFORPAY_ACCOUNT")
WAYFORPAY_SECRET_KEY = os.getenv("WAYFORPAY_SECRET_KEY")
GROUP_LINK = os.getenv("GROUP_LINK")
BASE_URL = os.getenv("BASE_URL")

required_vars = {
    "BOT_TOKEN": BOT_TOKEN,
    "WAYFORPAY_ACCOUNT": WAYFORPAY_ACCOUNT,
    "WAYFORPAY_SECRET_KEY": WAYFORPAY_SECRET_KEY,
    "GROUP_LINK": GROUP_LINK,
    "BASE_URL": BASE_URL
}

missing_vars = [key for key, value in required_vars.items() if not value]
if missing_vars:
    raise ValueError(f"Environment variables missing: {', '.join(missing_vars)}. Please check Render settings.")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
app = FastAPI()

@app.get("/pay", response_class=HTMLResponse)
async def pay(uid: str, amount: str):
    order_reference = f"ORDER-{uid}-{int(time.time())}"
    order_date = int(time.time())

    data = {
        "merchantAccount": WAYFORPAY_ACCOUNT,
        "merchantDomainName": BASE_URL,
        "orderReference": order_reference,
        "orderDate": order_date,
        "amount": amount,
        "currency": "UAH",
        "productName": ["Підписка NephroLog"],
        "productCount": [1],
        "productPrice": [amount],
        "clientFirstName": "User",
        "clientLastName": "Telegram",
        "clientEmail": "no@email.com",
        "language": "UA"
    }

    keys = [
        "merchantAccount", "merchantDomainName", "orderReference", "orderDate", "amount", "currency",
        "productName", "productCount", "productPrice"
    ]

    def get_string_to_sign(data: dict, keys: list) -> str:
        return ";".join(
            [";".join(v) if isinstance(v, list) else str(v) for k, v in data.items() if k in keys]
        )

    string_to_sign = get_string_to_sign(data, keys)
    signature = hmac.new(
        WAYFORPAY_SECRET_KEY.encode(),
        string_to_sign.encode(),
        hashlib.md5
    ).hexdigest()

    data["merchantSignature"] = signature

    inputs = "\n".join([
        f'<input type="hidden" name="{k}" value="{','.join(map(str, v)) if isinstance(v, list) else v}"/>'
        for k, v in data.items()
    ])

    form = f"""
    <html>
        <body onload=\"document.forms[0].submit()\">
            <form action="https://secure.wayforpay.com/pay" method="POST">
                {inputs}
            </form>
        </body>
    </html>
    """
    return HTMLResponse(content=form)

@app.post("/wfp-callback")
async def callback(request: Request):
    payload = await request.json()
    user_id = int(payload.get("orderReference", "0").split("-")[1])
    try:
        await bot.send_message(user_id, f"✅ Оплату підтверджено! Ось ваше посилання: {GROUP_LINK}", parse_mode=ParseMode.HTML)
    except Exception as e:
        return JSONResponse(status_code=200, content={"status": "error", "detail": str(e)})

    return JSONResponse(status_code=HTTP_200_OK, content={"status": "accept"})
