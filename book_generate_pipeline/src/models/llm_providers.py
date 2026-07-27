"""统一的 LLM 调用层，所有请求都走同一个 LiteLLM 网关。

按用途划分角色，具体模型名在 config/config.dev.yaml 里配置：

- writer   正文、摘要、前言、章节纠错、notebook 生成
- reviewer 大纲 battle 的对手模型
- utility  结构化输出、关键词扩展、插图选点
- vision   插图质量评估（多模态）
- image    插图生成
"""

import asyncio
import base64
import logging
import os
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

import httpx
import litellm
from pydantic import BaseModel

from src.utils import get_config

logger = logging.getLogger(__name__)

litellm.suppress_debug_info = True

_config = get_config()
_BASE_URL = _config.gateway_base_url
_API_KEY = _config.gateway_api_key

if not _BASE_URL or not _API_KEY:
    raise RuntimeError(
        "LiteLLM 网关未配置：请在 .env 中设置 LITELLM_PROXY_API_BASE 与 LITELLM_PROXY_API_KEY。"
    )

# litellm 的 litellm_proxy provider 从这两个环境变量读取网关地址与密钥
os.environ["LITELLM_PROXY_API_BASE"] = _BASE_URL
os.environ["LITELLM_PROXY_API_KEY"] = _API_KEY

# 正文类调用需要足够大的输出预算，否则整章会被截断
WRITER_MAX_TOKENS = int(os.environ.get("LLM_WRITER_MAX_TOKENS", "32000"))


def _qualified(model: str) -> str:
    return model if model.startswith("litellm_proxy/") else f"litellm_proxy/{model}"


def _api_url(path: str) -> str:
    base = _BASE_URL[:-3].rstrip("/") if _BASE_URL.endswith("/v1") else _BASE_URL
    return f"{base}/v1/{path.lstrip('/')}"


def model_for(role: str) -> str:
    """返回某个角色当前使用的模型名（不带 litellm_proxy/ 前缀）。"""
    return _config.get_model(role)


async def complete(
    prompt: str,
    model: str,
    temperature: float = 0.7,
    max_tokens: Optional[int] = None,
    **kwargs,
) -> str:
    """向网关发一次单轮对话请求。"""
    params: Dict[str, Any] = {
        "model": _qualified(model),
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
    }
    if max_tokens:
        params["max_tokens"] = max_tokens
    params.update(kwargs)
    response = await litellm.acompletion(**params)
    return response["choices"][0]["message"]["content"] or ""


async def writer_completion(prompt: str, temperature: float = 0.7, **kwargs) -> str:
    """主力写作模型；失败时按配置依次降级。"""
    models = [model_for("writer")] + _config.writer_fallback_models
    kwargs.setdefault("max_tokens", WRITER_MAX_TOKENS)
    last_error: Optional[Exception] = None
    for model in models:
        try:
            return await complete(prompt, model=model, temperature=temperature, **kwargs)
        except Exception as exc:
            last_error = exc
            logger.warning("writer 模型 %s 调用失败，尝试降级: %s", model, exc)
    raise RuntimeError(f"所有 writer 模型均调用失败，最后一个错误: {last_error}")


async def reviewer_completion(prompt: str, temperature: float = 0.7, **kwargs) -> str:
    kwargs.setdefault("max_tokens", WRITER_MAX_TOKENS)
    return await complete(prompt, model=model_for("reviewer"), temperature=temperature, **kwargs)


async def utility_completion(prompt: str, temperature: float = 0.7, **kwargs) -> str:
    return await complete(prompt, model=model_for("utility"), temperature=temperature, **kwargs)


def evaluator_completions() -> List[Callable[[str], Any]]:
    """返回大纲 battle 的评委调用函数列表。"""

    def _make(model: str) -> Callable[[str], Any]:
        async def _call(prompt: str, temperature: float = 0.7, **kwargs) -> str:
            kwargs.setdefault("max_tokens", WRITER_MAX_TOKENS)
            return await complete(prompt, model=model, temperature=temperature, **kwargs)

        _call.__name__ = f"evaluator_{model.replace('/', '_').replace('.', '_')}"
        return _call

    return [_make(m) for m in _config.evaluator_models]


async def structured_completion(
    system_prompt: str,
    user_prompt: str,
    response_format: Optional[type] = None,
    temperature: float = 1.0,
    max_tokens: int = 4096,
    model: Optional[str] = None,
) -> Tuple[str, Dict[str, Any]]:
    """需要 JSON schema 约束输出的调用，返回 (文本, 用量信息)。

    注意：Claude 系模型会忽略 response_format 并返回散文，请勿把它们配成 utility 角色。
    """
    target = model or model_for("utility")
    start = time.time()
    response = await litellm.acompletion(
        model=_qualified(target),
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": [{"type": "text", "text": user_prompt}]},
        ],
        response_format=response_format,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    content = response["choices"][0]["message"]["content"] or ""
    usage = response.get("usage") or {}
    if not isinstance(usage, dict):
        usage = getattr(usage, "__dict__", {}) or {}
    return content, {
        "model": target,
        "elapsed_time": time.time() - start,
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "total_tokens": usage.get("total_tokens", 0),
    }


async def vision_completion(prompt: str, image_path: str, max_tokens: int = 4096) -> str:
    """带图片输入的调用，用于插图质量评估。"""
    with open(image_path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("utf-8")
    response = await litellm.acompletion(
        model=_qualified(model_for("vision")),
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded}"}},
                ],
            }
        ],
        max_tokens=max_tokens,
    )
    return response["choices"][0]["message"]["content"] or ""


async def generate_images(
    prompt: str,
    n: int = 1,
    timeout_seconds: float = 300.0,
    max_attempts: int = 3,
) -> List[bytes]:
    """调用网关的 images/generations 生成插图，返回图片字节列表。

    出图接口偶发 429/5xx 与超时，这里做有限次退避重试；重试耗尽会抛异常，
    由调用方决定是否降级，避免静默产出空图。
    """
    url = _api_url("images/generations")
    headers = {"Authorization": f"Bearer {_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": model_for("image"), "prompt": prompt, "n": n}

    last_error: Optional[str] = None
    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        for attempt in range(1, max_attempts + 1):
            try:
                resp = await client.post(url, headers=headers, json=payload)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
            else:
                if resp.status_code == 200:
                    images = await _extract_images(resp.json(), client)
                    if images:
                        return images
                    last_error = f"响应中没有图片数据: {str(resp.json())[:200]}"
                else:
                    last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"

            if attempt < max_attempts:
                delay = min(2.0 * attempt, 8.0)
                logger.warning("出图第 %d 次失败（%s），%.0fs 后重试", attempt, last_error, delay)
                await asyncio.sleep(delay)

    raise RuntimeError(f"出图失败，已重试 {max_attempts} 次。最后一个错误: {last_error}")


async def _extract_images(payload: Dict[str, Any], client: httpx.AsyncClient) -> List[bytes]:
    """兼容 b64_json 与 url 两种返回形态。"""
    images: List[bytes] = []
    for item in payload.get("data", []) or []:
        if not isinstance(item, dict):
            continue
        b64 = item.get("b64_json")
        if b64:
            try:
                images.append(base64.b64decode(b64))
            except Exception:
                logger.warning("b64_json 解码失败，跳过一张图")
            continue
        url = item.get("url")
        if url:
            try:
                r = await client.get(url)
                if r.status_code == 200:
                    images.append(r.content)
            except Exception as exc:
                logger.warning("下载图片失败 %s: %s", url, exc)
    return images
