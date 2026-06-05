import requests
from app.config import CALLBACK_AUTH_TOKEN

def send_task_callback(callback_url: str | None, payload: dict) -> None:
    if not callback_url:
        return
    headers = {'Content-Type': 'application/json'}
    if CALLBACK_AUTH_TOKEN:
        headers['Authorization'] = f'Bearer {CALLBACK_AUTH_TOKEN}'
    requests.post(callback_url, json=payload, headers=headers, timeout=30)
