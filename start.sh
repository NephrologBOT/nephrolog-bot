#!/bin/bash
uvicorn wfp_fastapi_bot:app --host 0.0.0.0 --port 10000 &
python bot.py
