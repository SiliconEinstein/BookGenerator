"""LLM provider implementations using litellm and OpenAI clients."""

import os
import litellm
import httpx
from openai import OpenAI, AsyncOpenAI
from typing import Optional

# Default configuration - can be overridden by environment variables or config file
DEFAULT_API_KEY = "00u14bi9fo1k9h01000deu6szt7f07n5009w6vsv"
DEFAULT_LITELLM_PROXY_BASE = "http://8.219.58.57:4000"
DEFAULT_LITELLM_API_KEY = "sk-WNrS8wC5RXbYvAx6KKdyEw"
DEFAULT_GPUGEEK_BASE = "https://api.gpugeek.com/v1"


def _get_env_var(key: str, default: str) -> str:
    """Get environment variable or return default."""
    return os.environ.get(key, default)


# Initialize clients
_litellm_api_base = _get_env_var("LITELLM_PROXY_API_BASE", DEFAULT_LITELLM_PROXY_BASE)
_litellm_api_key = _get_env_var("LITELLM_PROXY_API_KEY", DEFAULT_LITELLM_API_KEY)
_gpugeek_api_key = _get_env_var("GPUGEEK_API_KEY", DEFAULT_API_KEY)

os.environ["LITELLM_PROXY_API_BASE"] = _litellm_api_base
os.environ["LITELLM_PROXY_API_KEY"] = _litellm_api_key

# Create async OpenAI client for GPUgeek API
_async_client = AsyncOpenAI(
    api_key=_gpugeek_api_key,
    base_url=DEFAULT_GPUGEEK_BASE,
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
