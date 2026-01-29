"""LLM provider implementations using litellm and OpenAI clients."""

import os
import litellm
import httpx
from openai import OpenAI, AsyncOpenAI
from typing import Optional
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
