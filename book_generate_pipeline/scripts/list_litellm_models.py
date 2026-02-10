#!/usr/bin/env python3
"""列出当前配置的 LiteLLM Proxy 支持的模型（请求 /v1/models）。"""

import os
import sys
import json

# 保证可导入 src（项目根 = scripts 的上级）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils import get_config

try:
    import httpx
except ImportError:
    print("请安装: pip install httpx")
    sys.exit(1)


def main():
    config = get_config()
    cfg = config.get_provider_config("gemini")
    base_url = (cfg or {}).get("base_url") or ""
    api_key = (cfg or {}).get("api_key") or ""

    if not base_url:
        print("未配置 LITELLM_PROXY 的 base_url（gemini 的 base_url）。")
        sys.exit(1)

    base_url = base_url.rstrip("/")
    url = f"{base_url}/v1/models"
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    print(f"请求: {url}")
    try:
        r = httpx.get(url, headers=headers, timeout=15.0)
        r.raise_for_status()
        data = r.json()
    except httpx.HTTPStatusError as e:
        print(f"HTTP 错误: {e.response.status_code}")
        print(e.response.text[:500])
        sys.exit(1)
    except Exception as e:
        print(f"请求失败: {e}")
        sys.exit(1)

    # OpenAI 兼容返回格式: { "data": [ { "id": "model-id", ... }, ... ] }
    models = data.get("data") if isinstance(data.get("data"), list) else []
    if not models:
        print("未返回模型列表，原始 JSON：")
        print(json.dumps(data, indent=2, ensure_ascii=False)[:2000])
        return

    print(f"\nLiteLLM Proxy 当前支持 {len(models)} 个模型：\n")
    for m in models:
        mid = m.get("id") or m.get("model") or "(无 id)"
        print(f"  - {mid}")
    print()


if __name__ == "__main__":
    main()
