import os
import hmac
import uuid
import hashlib
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from aiogram import Bot
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()
bot = Bot(token=os.getenv("API_TOKEN"))

MERCHANT_ACCOUNT = os.getenv("MERCHANT_ACCOUNT")
MERCHANT_SECRET = os.getenv("MERCHANT_SECRET")
INVITE_LINK = os.getenv("INVITE_LINK")

paid_refs = set()

def generate_signature(data: dict, secret: str) -> str:
    keys = sorted(data.keys())
    raw = ';'.join([str(data[k]) for k in keys])
    return hmac.new(secret.encode(), raw.encode(), hashlib.md5).hexdigest()

@app.get("/")  # <--- новий обробник кореневої сторінки
async def root():
    return {"status": "ok"}

@app.get("/pay", response_class=HTMLResponse)
async def pay_page(uid: int, ref: str, amount: int):
    payload = {
        "account": MERCHANT_ACCOUNT,
        "amount": amount,
        "currency": "UAH",
        "orderReference": ref,
        "orderDate": 1700000000,
        "merchantAuthType": uid,
        "productName": "NephroLog",
        "productCount": "1",
        "productPrice": amount
    }
    signature = generate_signature(payload, MERCHANT_SECRET)
    payload["signature"] = signature

    form = "".join(
        f'<input type="hidden" name="{k}" value="{v}"/>' for k, v in payload.items()
    )

    return f"""<!DOCTYPE html>
<html>
  <body onload="document.forms[0].submit()">
    <form method="POST" action="https://secure.wayforpay.com/pay">
      {form}
    </form>
  </body>
</html>"""

@app.post("/wfp-callback")
async def callback(request: Request):
    data = await request.json()
    status = data.get("transactionStatus")
    user_id = int(data.get("merchantAuthType", 0))
    ref = data.get("orderReference")

    if status == "Approved" and ref not in paid_refs:
        paid_refs.add(ref)
        await bot.send_message(user_id, "✅ Оплату підтверджено! Ось ваше посилання:")
        await bot.send_message(user_id, INVITE_LINK)

    return {"status": "ok"}
