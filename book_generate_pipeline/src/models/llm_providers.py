"""LLM provider implementations using litellm and OpenAI clients."""

import os
import time
import asyncio
import litellm
import httpx
from openai import OpenAI, AsyncOpenAI
from typing import Optional, Any, List
from src.utils import get_config

# Configuration helpers
def _get_config_value(config: dict, key: str, env_key: Optional[str] = None, default: str = "") -> str:
    """Return value from config or environment fallback."""
    if config:
        value = config.get(key)
        if value:
            return value
    if env_key:
        return os.environ.get(env_key, default)
    return default


def _get_provider_model(config: dict, default: str) -> str:
    """Return provider model from config or default."""
    if config:
        value = config.get("model")
        if value:
            return value
    return default


# Initialize clients
_config = get_config()
_gemini_cfg = _config.get_provider_config("gemini")
_gpt5_cfg = _config.get_provider_config("gpt5")
_deepseek_cfg = _config.get_provider_config("deepseek")
_qwen_cfg = _config.get_provider_config("qwen")
_doubao_cfg = _config.get_provider_config("doubao")

_litellm_api_base = _get_config_value(_gemini_cfg, "base_url", "LITELLM_PROXY_API_BASE")
_litellm_api_key = _get_config_value(_gemini_cfg, "api_key", "LITELLM_API_KEY")
_gpugeek_api_base = _get_config_value(_gpt5_cfg, "base_url", "GPUGEEK_API_BASE")
_gpugeek_api_key = _get_config_value(_gpt5_cfg, "api_key", "GPUGEEK_API_KEY")
_gpugeek_image_base = os.environ.get("GPUGEEK_IMAGE_API_BASE", "https://api.gpugeek.com").rstrip("/")
_gpugeek_image_model = os.environ.get("GPUGEEK_IMAGE_MODEL", "Vendor2/Gemini-3-Pro-Image")

os.environ["LITELLM_PROXY_API_BASE"] = _litellm_api_base
os.environ["LITELLM_PROXY_API_KEY"] = _litellm_api_key
os.environ["LITELLM_API_KEY"] = _litellm_api_key

# Create async OpenAI client for GPUgeek API
_async_client = AsyncOpenAI(
    api_key=_gpugeek_api_key,
    base_url=_gpugeek_api_base,
    http_client=httpx.AsyncClient(
        limits=httpx.Limits(
            max_connections=100,
            max_keepalive_connections=50,
        ),
    ),
)


async def gemini_completion(prompt: str, **kwargs) -> str:
    """Gemini 3 Pro completion using litellm proxy."""
    messages = [{"role": "user", "content": prompt}]
    try:
        response = await litellm.acompletion(
            model="litellm_proxy/gemini-3-pro-preview",
            messages=messages,
            **kwargs
        )
    except Exception as e:
        raise RuntimeError(f"Evaluation failed: {e}")
    return response['choices'][0]['message']['content']


async def gpt_completion(prompt: str, temperature: float = 0.7, **kwargs) -> str:
    """GPT 5.2 completion using GPUgeek API."""
    messages = [{"role": "user", "content": prompt}]
    response = await _async_client.chat.completions.create(
        model="Vendor2/GPT-5.2",
        messages=messages,
        temperature=temperature,
        max_completion_tokens=65535,
        **kwargs
    )
    return response.choices[0].message.content


async def deepseek_completion(prompt: str, temperature: float = 0.7, **kwargs) -> str:
    """DeepSeek V3 completion using GPUgeek API."""
    messages = [{"role": "user", "content": prompt}]
    response = await _async_client.chat.completions.create(
        model="DeepSeek/DeepSeek-V3-0324",
        messages=messages,
        temperature=temperature,
        **kwargs
    )
    return response.choices[0].message.content


async def qwen_completion(prompt: str, temperature: float = 0.7, **kwargs) -> str:
    """Qwen VL completion using GPUgeek API."""
    messages = [{"role": "user", "content": prompt}]
    response = await _async_client.chat.completions.create(
        model="GpuGeek/Qwen3-VL-30B-A3B-Thinking",
        messages=messages,
        temperature=temperature,
        **kwargs
    )
    return response.choices[0].message.content


async def doubao_completion(prompt: str, temperature: float = 0.7, **kwargs) -> str:
    """Doubao completion using GPUgeek API."""
    messages = [{"role": "user", "content": prompt}]
    response = await _async_client.chat.completions.create(
        model="Volcengine/Doubao-Seed-1.6",
        messages=messages,
        temperature=temperature,
        **kwargs
    )
    return response.choices[0].message.content


async def gpugeek_image_generation(
    prompt: str,
    aspect_ratio: str = "16:9",
    image_size: str = "1K",
    images: Optional[List[str]] = None,
    poll_interval_seconds: float = 2.0,
    timeout_seconds: float = 180.0,
    submit_retry_times: int = 3,
) -> List[Any]:
    """
    Generate image via GPUGeek predictions API (async submit + poll).

    Returns:
        prediction output payload list/object normalized to a list.
    """
    api_key = (_gpugeek_api_key or os.environ.get("GPUGEEK_API_KEY", "")).strip()
    if not api_key:
        raise RuntimeError("Missing GPUGEEK_API_KEY for image generation.")

    prediction_url = f"{_gpugeek_image_base}/predictions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Prefer": "respond-async",
    }
    payload = {
        "model": _gpugeek_image_model,
        "input": {
            "aspectRatio": aspect_ratio,
            "imageSize": image_size,
            "images": images or [],
            "prompt": prompt or "",
        },
    }

    timeout = httpx.Timeout(connect=10.0, read=60.0, write=20.0, pool=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        submit_res = None
        last_submit_error: Optional[Exception] = None
        for attempt in range(1, max(1, submit_retry_times) + 1):
            try:
                submit_res = await client.post(prediction_url, headers=headers, json=payload)
                break
            except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.ConnectError) as exc:
                last_submit_error = exc
                if attempt >= submit_retry_times:
                    break
                await asyncio.sleep(min(2.0 * attempt, 5.0))

        if submit_res is None:
            raise RuntimeError(f"Image submit request failed after retries: {last_submit_error}")
        if submit_res.status_code not in {200, 202}:
            raise RuntimeError(
                f"Image submit failed: status={submit_res.status_code}, body={submit_res.text}"
            )

        submit_payload = submit_res.json() if submit_res.content else {}

        # 一些服务端会直接同步返回最终结果（200 + output），无需轮询。
        if submit_res.status_code == 200:
            direct_output = (submit_payload or {}).get("output")
            if isinstance(direct_output, list):
                return direct_output
            if direct_output is None:
                return []
            return [direct_output]

        prediction_id = (submit_payload or {}).get("id")
        if not prediction_id:
            raise RuntimeError(f"Image submit missing prediction id: {submit_res.text}")

        query_url = f"{prediction_url}/{prediction_id}"
        query_headers = {"Authorization": f"Bearer {api_key}"}
        deadline = time.time() + timeout_seconds

        while time.time() < deadline:
            try:
                poll_res = await client.get(query_url, headers=query_headers)
            except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.ConnectError):
                # 接口偶发慢响应或网络抖动时，保留任务并继续轮询，避免直接失败。
                await asyncio.sleep(poll_interval_seconds)
                continue

            poll_payload = poll_res.json() if poll_res.content else {}
            status = (poll_payload or {}).get("status", "")
            output = (poll_payload or {}).get("output")

            if poll_res.status_code == 200 and status not in {"processing", "starting", ""}:
                if status in {"failed", "canceled", "cancelled"}:
                    raise RuntimeError(f"Image generation {status}: {poll_payload}")
                if isinstance(output, list):
                    return output
                if output is None:
                    return []
                return [output]

            await asyncio.sleep(poll_interval_seconds)

    raise TimeoutError(f"Image generation timed out after {timeout_seconds}s.")


# Sync wrapper for compatibility with eval.py
def eval_sync(prompt: str, image_path: Optional[str] = None) -> str:
    """Synchronous evaluation with optional image support."""
    try:
        if image_path is None:
            messages = [{"role": "user", "content": prompt}]
        else:
            import base64
            with open(image_path, "rb") as image_file:
                encoded_image = base64.b64encode(image_file.read()).decode('utf-8')
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{encoded_image}"}
                        }
                    ]
                }
            ]
        response = litellm.completion(
            model="litellm_proxy/gemini-3-pro-preview",
            messages=messages,
        )
        return response['choices'][0]['message']['content']
    except Exception as e:
        raise RuntimeError(f"Evaluation failed: {e}")


async def main():
    """Test function for providers."""
    res = await doubao_completion("介绍一下什么是人工智能")
    print(res)


if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
