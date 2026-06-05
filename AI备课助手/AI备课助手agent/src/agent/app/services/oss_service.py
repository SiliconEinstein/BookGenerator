from __future__ import annotations
from pathlib import Path
import requests
from app.config import BACKEND_AUTH_TOKEN, BACKEND_BASE_URL, OSS_TOKEN_PATH, OSS_UPLOAD_URL

def get_oss_token(object_path: str) -> dict | None:
    if not BACKEND_BASE_URL:
        return None
    headers = {'Content-Type': 'application/json'}
    if BACKEND_AUTH_TOKEN:
        headers['Authorization'] = f'Bearer {BACKEND_AUTH_TOKEN}'
    response = requests.post(f"{BACKEND_BASE_URL.rstrip('/')}{OSS_TOKEN_PATH}", json={'path': object_path}, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()

def upload_file(local_path: str | Path, object_path: str) -> str | None:
    token_payload = get_oss_token(object_path)
    if not token_payload:
        return None
    auth = token_payload.get('data', {}).get('authorization') or token_payload.get('authorization') or token_payload.get('data', {}).get('token') or token_payload.get('token')
    x_storage_param = token_payload.get('data', {}).get('xStorageParam') or token_payload.get('xStorageParam')
    if not auth or not x_storage_param:
        raise ValueError('Invalid OSS token payload')
    with open(local_path, 'rb') as file_obj:
        response = requests.post(OSS_UPLOAD_URL, headers={'Accept': '*/*', 'Authorization': f'Bearer {auth}', 'x-storage-param': x_storage_param}, data=file_obj.read(), timeout=60)
    response.raise_for_status()
    return object_path
