import asyncio
import json
import requests
from app.config import GPUGEEK_API_BASE, GPUGEEK_API_KEY

def _llm_retry(func):
    async def wrapper(*args, **kwargs):
        last_error = None
        for attempt in range(3):
            try:
                return await func(*args, **kwargs)
            except Exception as exc:
                last_error = exc
                if attempt < 2:
                    await asyncio.sleep(0.8 * (attempt + 1))
        raise last_error
    return wrapper

@_llm_retry
async def gpt_completion(prompt: str, temperature: float = 0.7, **kwargs) -> str:
    if not GPUGEEK_API_KEY or not GPUGEEK_API_BASE:
        raise RuntimeError('GPUGeek API not configured')
    payload = {
        'model': 'Vendor2/GPT-5.2',
        'messages': [{'role': 'user', 'content': prompt}],
        'temperature': temperature,
        'max_completion_tokens': kwargs.pop('max_tokens', 65535),
        **kwargs,
    }
    response = requests.post(
        f"{GPUGEEK_API_BASE.rstrip('/')}/chat/completions",
        headers={
            'Authorization': f'Bearer {GPUGEEK_API_KEY}',
            'Content-Type': 'application/json',
        },
        json=payload,
        timeout=120,
    )
    response.raise_for_status()
    data = response.json()
    return data['choices'][0]['message']['content'] or ''

def parse_json_object(text: str) -> dict:
    cleaned = text.strip().removeprefix('```json').removeprefix('```').removesuffix('```').strip()
    start = cleaned.find('{')
    end = cleaned.rfind('}')
    if start == -1 or end == -1:
        raise ValueError('No JSON object found in LLM response')
    return json.loads(cleaned[start:end + 1])
