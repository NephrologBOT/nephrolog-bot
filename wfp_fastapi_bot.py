import hashlib
import hmac
import time
import nest_asyncio
import uvicorn
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
MERCHANT_ACCOUNT = os.getenv("MERCHANT_ACCOUNT")
MERCHANT_SECRET_KEY = os.getenv("MERCHANT_SECRET_KEY")
PUBLIC_HOST = os.getenv("PUBLIC_HOST")
INVITE_LINK = os.getenv("INVITE_LINK")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

if not all([BOT_TOKEN, MERCHANT_ACCOUNT, MERCHANT_SECRET_KEY, PUBLIC_HOST, INVITE_LINK, OWNER_ID]):
    raise ValueError("One or more environment variables are missing. Please check .env or Render settings.")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
app = FastAPI()
nest_asyncio.apply()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "WayForPay bot is running."}

@app.get("/pay", response_class=HTMLResponse)
async def create_invoice(uid: int, amount: float):
    order_reference = f"order_{uid}_{int(time.time())}"
    order_date = int(time.time())

    data = {
        "merchantAccount": MERCHANT_ACCOUNT,
        "merchantDomainName": PUBLIC_HOST.replace("https://", ""),
        "merchantAuthType": "SimpleSignature",
        "apiVersion": 1,
        "orderReference": order_reference,
        "orderDate": order_date,
        "amount": amount,
        "currency": "UAH",
        "productName": ["NephroLog Subscription"],
        "productPrice": [amount],
        "productCount": [1],
        "clientFirstName": "Vet",
        "clientLastName": "Doctor",
        "clientEmail": "user@example.com",
        "clientPhone": "380000000000",
        "serviceUrl": f"{PUBLIC_HOST}/wfp-callback",
        "language": "ua",
    }

    signature_fields = [
        data["merchantAccount"],
        data["merchantDomainName"],
        data["orderReference"],
        str(data["orderDate"]),
        str(data["amount"]),
        data["currency"],
        data["productName"][0],
        str(data["productPrice"][0]),
        str(data["productCount"][0])
    ]

    signature_string = ";".join(signature_fields)
    data["merchantSignature"] = hmac.new(
        MERCHANT_SECRET_KEY.encode(),
        signature_string.encode(),
        hashlib.md5
    ).hexdigest()

    form = ""
    for k, v in data.items():
        value = ",".join(map(str, v)) if isinstance(v, list) else v
        form += f'<input type="hidden" name="{k}" value="{value}"/>'

    html_form = f"""
    <html>
        <body onload=\"document.forms[0].submit()\">
            <form method="POST" action="https://secure.wayforpay.com/pay">
                {form}
            </form>
        </body>
    </html>
    """
    return HTMLResponse(content=html_form)

@app.post("/wfp-callback")
async def callback(request: Request):
    body = await request.json()
    user_id = int(body.get("orderReference", "").split("_")[1])

    try:
        await bot.send_message(user_id, "✅ Оплату підтверджено! Ось ваше посилання:")
        await bot.send_message(user_id, INVITE_LINK)
    except Exception as e:
        await bot.send_message(OWNER_ID, f"❌ Не вдалося надіслати повідомлення користувачу {user_id}: {e}")

    return {"status": "accepted"}

if __name__ == "__main__":
    uvicorn.run("wfp_fastapi_bot:app", host="0.0.0.0", port=10000)
