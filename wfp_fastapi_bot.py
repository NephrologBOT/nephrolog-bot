# ... (початок той самий до app = FastAPI())

from aiogram import types

app = FastAPI()

@dp.message_handler(commands=["start"])
async def start_handler(message: types.Message):
    uid = message.from_user.id
    link = f"https://nephrolog-bot.onrender.com/pay?uid={uid}"
    await message.answer(f"Привіт! Щоб оформити підписку, перейдіть за посиланням: {link}")

@app.get("/pay", response_class=HTMLResponse)
async def pay_form(uid: str, amount: str = PRICE_UAH):
    order_reference = f"ORDER-{uid}-{int(time.time())}"
    order_date = str(int(time.time()))
    currency = "UAH"
    product_name = "Telegram Premium Access"
    product_price = amount
    product_count = "1"

    data = {
        "merchantAccount": WAYFORPAY_ACCOUNT,
        "merchantDomainName": "nephrolog-bot.onrender.com",
        "orderReference": order_reference,
        "orderDate": order_date,
        "amount": product_price,
        "currency": currency,
        "productName": [product_name],
        "productPrice": [float(product_price)],
        "productCount": [int(product_count)],
        "clientFirstName": "User",
        "clientLastName": uid,
        "clientEmail": f"user{uid}@nephrolog.com",
        "serviceUrl": "https://nephrolog-bot.onrender.com/wfp-callback",
    }

    keys = [
        "merchantAccount",
        "merchantDomainName",
        "orderReference",
        "orderDate",
        "amount",
        "currency",
        "productName",
        "productCount",
        "productPrice",
    ]

    signature_base = ";".join([
        ",".join(map(str, data[k])) if isinstance(data[k], list) else str(data[k])
        for k in keys
    ])

    hmac_signature = hmac.new(
        WAYFORPAY_SECRET_KEY.encode(),
        signature_base.encode(),
        hashlib.md5
    ).digest()

    merchant_signature = base64.b64encode(hmac_signature).decode()
    data["merchantSignature"] = merchant_signature

    form_inputs = ''
    for k in data:
        value = ",".join(map(str, data[k])) if isinstance(data[k], list) else str(data[k])
        form_inputs += f'<input type="hidden" name="{k}" value="{value}"/>\n'

    html_form = f'''
    <html><body>
        <form id="wfp-form" method="POST" action="https://secure.wayforpay.com/pay">
            {form_inputs}
            <noscript><input type="submit" value="Сплатити"></noscript>
            <input type="submit" value="Оплатити зараз" />
        </form>
        <script>document.getElementById("wfp-form").submit();</script>
    </body></html>
    '''
    return HTMLResponse(content=html_form)

@app.post("/wfp-callback")
async def callback(request: Request):
    payload = await request.json()
    user_id = payload.get("clientLastName")
    status = payload.get("transactionStatus")

    if status == "Approved":
        try:
            await bot.send_message(user_id, "✅ Оплату підтверджено! Ось ваше посилання: \n" + GROUP_LINK)
        except Exception as e:
            print(f"Failed to send message: {e}")
    return {"code": 0}

# Run bot
import asyncio
loop = asyncio.get_event_loop()
loop.create_task(dp.start_polling())
